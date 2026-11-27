# DESCRIBE, USE, SOURCE, and Keyspace Context Management

## 1. Why Manage Keyspace Context?

In Apache Cassandra, a **keyspace** is a namespace containing tables and schema objects, while also declaring the replication strategy. When working via **cqlsh**, we usually need to know three things:

1. **Which cluster/node are we connected to?** To avoid operating on the wrong environment.
2. **What is the structure of the tables and keyspaces?** To write CQL with the correct partition keys, clustering keys, and data types.
3. **Where will statements without an explicit keyspace name take effect?** To avoid accidentally reading from or writing to a table with the same name in a different keyspace.

Three important tools are:

- **`DESCRIBE`**: views the structure of keyspaces, tables, and CQL objects; very useful when exploring schemas and diagnosing errors.
- **`USE`**: selects the default keyspace in the **current connection session**, allowing table names to be written without a keyspace prefix.
- **`SOURCE`**: instructs cqlsh to read and execute statements from a script file accessible from the machine running cqlsh.

This is part of the **Tools and Connections** topic in the Cassandra module. Proper keyspace management helps make CQL practice, partition-key querying, replication inspection, and Java application connection setup safe and easy to verify.

**Objective:** after this lesson, you will be able to describe the context of a cqlsh session, use `DESCRIBE` to inspect schemas, switch keyspaces with `USE`, execute `.cql` files with `SOURCE`, and avoid errors caused by mixing up keyspaces across sessions or scripts.

## 2. The Three Commands and Their Scope

| Command | Typical Syntax | Effect | Scope |
| --- | --- | --- | --- |
| `DESCRIBE` / `DESC` | `DESCRIBE KEYSPACE demo;` | Displays schema definitions; does not modify data. | Reads schema information accessible to the session. |
| `USE` | `USE demo;` | Sets the default keyspace for unqualified table names. | Current connection session. |
| `SOURCE` | `SOURCE 'setup.cql';` | Reads a file and sequentially executes the statements inside it. | The cqlsh session that invokes `SOURCE`. |

`USE` is a **CQL statement** for keyspace context; `SOURCE` is a **cqlsh command**, not a CQL statement to be sent verbatim from the Java Driver. `DESCRIBE` is a convenient schema lookup interface in cqlsh; how `DESCRIBE` is handled across clients or servers can depend on the version, so Java applications should use the driver's metadata API when schema discovery is needed.

Some foundational rules:

- CQL statements use a semicolon (`;`) as a terminator. Examples in this lesson also terminate cqlsh commands with `;` for consistency.
- A fully qualified table name has the form `keyspace.table`. This name explicitly specifies the target, even when the session has `USE` set to a different keyspace.
- Switching `USE` **does not move data**, does not change the keyspace's replication, and does not automatically alter consistency.
- A new session does not inherit the `USE` context of an earlier session. For independently run scripts, include the appropriate `USE` in each script or write full `keyspace.table` names.
- In Cassandra, tables are typically designed **around queries**: `DESCRIBE TABLE` helps verify partition keys and clustering columns before writing a `SELECT`.

## 3. Checking Connections and Exploring Schemas with DESCRIBE

### 3.1. Identifying the Connection Endpoint

Open a cqlsh session (for example, when Cassandra is listening on `127.0.0.1:9042`):

~~~bash
cqlsh 127.0.0.1 9042
~~~

At the `cqlsh>` prompt, try:

~~~sql
SHOW HOST;
SHOW VERSION;
DESCRIBE KEYSPACES;
~~~

`SHOW HOST` confirms the current connection, `SHOW VERSION` helps detect version mismatches, and `DESCRIBE KEYSPACES` lists visible keyspaces. A cluster usually contains internal keyspaces such as `system` or `system_schema`; **do not modify system tables for practice**.

**Distinguishing node and keyspace:** cqlsh connects to a single node acting as coordinator. A keyspace is a logical namespace and replication configuration; selecting a keyspace does not mean accessing data on only one specific node.

### 3.2. Commonly Used Forms of DESCRIBE

~~~sql
-- List accessible keyspaces.
DESCRIBE KEYSPACES;

-- When a keyspace already exists, view its definition statement.
DESCRIBE KEYSPACE cql_context_lab;

-- View a table's structure using its fully qualified name.
DESCRIBE TABLE cql_context_lab.events_by_device;

-- View the list of tables; display format may vary by cqlsh version.
DESCRIBE TABLES;

-- View cqlsh command help when confirming syntax variants.
HELP DESCRIBE;
~~~

`DESCRIBE KEYSPACE` typically displays the `replication` configuration and objects within the keyspace, while `DESCRIBE TABLE` lets you inspect column names, data types, `PRIMARY KEY`, clustering order, and table options. Exact output depends on the Cassandra/cqlsh version and access permissions.

**Example:** with `PRIMARY KEY ((device_id), event_time)`, `device_id` is the partition key and `event_time` is the clustering column. Querying for a device with `WHERE device_id = 'sensor-01'` is a natural query pattern; searching across all records by another regular column is not, without an appropriate data model or index.

## 4. Lab: Two Keyspaces with Identically Named Tables

This example uses **two independent test keyspaces** to demonstrate the effect of `USE`. The examples assume a single-node Cassandra instance with schema creation privileges. If practicing on an organizational cluster, use an authorized lab keyspace/account.

### 4.1. Creating Keyspaces and Tables

In cqlsh, run:

~~~sql
-- Use SimpleStrategy, RF=1 only for a single-node lab.
CREATE KEYSPACE IF NOT EXISTS cql_context_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE KEYSPACE IF NOT EXISTS cql_context_staging
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cql_context_lab.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS cql_context_staging.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

In both tables, the partition key is `device_id`; within a partition, rows are ordered by `event_time` descending, followed by `event_id`. Having the same table name **does not mean the same table**: `cql_context_lab.events_by_device` and `cql_context_staging.events_by_device` are two separate objects.

`SimpleStrategy` with RF = 1 simply keeps the lab straightforward. In real systems, `NetworkTopologyStrategy` and replication factors per actual datacenter are typically configured; this is an operational decision that balances fault tolerance and consistency levels.

### 4.2. Writing Data to Two Separate Tables

~~~sql
INSERT INTO cql_context_lab.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES (
  'sensor-01', '2026-11-21T01:00:00Z',
  11111111-1111-4111-8111-111111111111,
  'temperature', 'lab: 25.1 C'
);

INSERT INTO cql_context_staging.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES (
  'sensor-01', '2026-11-21T01:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'temperature', 'staging: 24.8 C'
);
~~~

The two `INSERT` statements use fully qualified table names to specify their targets. The `device_id` and `event_time` values are identical, but the data resides in **two different keyspaces**.

### 4.3. Switching Context with USE

~~~sql
USE cql_context_lab;

-- Unqualified table name: cql_context_lab.events_by_device.
SELECT device_id, event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

DESCRIBE TABLE events_by_device;

USE cql_context_staging;

-- Same SELECT query, but this time reading data from staging.
SELECT device_id, event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

-- Override the staging context by explicitly specifying the keyspace.
SELECT device_id, event_time, details
FROM cql_context_lab.events_by_device
WHERE device_id = 'sensor-01';
~~~

Expected results:

| Query | Keyspace Actually Accessed | `details` Value |
| --- | --- | --- |
| `SELECT ... FROM events_by_device` right after `USE cql_context_lab` | `cql_context_lab` | `lab: 25.1 C` |
| Same query right after `USE cql_context_staging` | `cql_context_staging` | `staging: 24.8 C` |
| `SELECT ... FROM cql_context_lab.events_by_device` while `USE` staging is active | `cql_context_lab` | `lab: 25.1 C` |

In many cqlsh versions, the prompt changes from `cqlsh>` to something like `cqlsh:cql_context_lab>` when `USE` succeeds. **Do not rely solely on the prompt**: in scripts, writing `keyspace.table` in critical queries helps readers be certain of the target.

### 4.4. What Happens When No Keyspace or the Wrong Keyspace Is Selected?

If you open a new cqlsh session and run `SELECT ... FROM events_by_device` before `USE`, cqlsh typically reports an error because no keyspace has been specified. An unqualified table name can only be resolved when a default keyspace is set.

If `USE cql_context_staging` is active, every `SELECT`, `INSERT`, `UPDATE`, or `DELETE` using the name `events_by_device` will target the staging table. This is a greater risk than a syntax error: **the statement can still succeed while affecting the wrong object**.

To verify quickly:

~~~sql
SHOW HOST;
DESCRIBE KEYSPACES;
DESCRIBE TABLE cql_context_lab.events_by_device;
DESCRIBE TABLE cql_context_staging.events_by_device;
~~~

## 5. SOURCE: Moving Statements into `.cql` Files

`SOURCE` accepts a filename (or path) on the **machine/environment running cqlsh**, reads its contents, and executes them in the **current cqlsh session**. As a result, `USE` statements inside the file affect subsequent statements in that same session.

Example creating two files (the contents shown below are files **created by the learner**, requiring no changes to files outside the lesson).

### 5.1. File `01_setup.cql`

~~~sql
-- Standalone initialization, independent of cqlsh's default keyspace.
CREATE KEYSPACE IF NOT EXISTS cql_context_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE KEYSPACE IF NOT EXISTS cql_context_staging
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS cql_context_lab.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS cql_context_staging.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO cql_context_lab.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES ('sensor-01', '2026-11-21T01:00:00Z',
  11111111-1111-4111-8111-111111111111, 'temperature', 'lab: 25.1 C');

INSERT INTO cql_context_staging.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES ('sensor-01', '2026-11-21T01:00:00Z',
  22222222-2222-4222-8222-222222222222, 'temperature', 'staging: 24.8 C');
~~~

Schema creation statements use `IF NOT EXISTS` so re-running them does not fail merely because the keyspace/table already exists; however, `IF NOT EXISTS` **does not update an existing structure** if the current schema differs from the file. `INSERT` in Cassandra behaves as an upsert by primary key, so re-running sample data with the same primary key does not create new rows.

### 5.2. File `02_inspect.cql`

~~~sql
-- SOURCE uses the same cqlsh session that invokes it.
USE cql_context_lab;
DESCRIBE TABLE events_by_device;
SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

USE cql_context_staging;
SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';
~~~

The two `SELECT` statements query two different tables, even though both say `FROM events_by_device`. Once `SOURCE` finishes, the **remaining default keyspace in the session** is `cql_context_staging`, because that was the last `USE` statement.

### 5.3. Executing at the cqlsh Prompt

~~~sql
SOURCE '01_setup.cql';
SOURCE '02_inspect.cql';

-- After SOURCE, an unqualified name still points to staging.
DESCRIBE TABLE events_by_device;

-- Explicitly reset the context if continuing work in lab.
USE cql_context_lab;
~~~

You can also pass an absolute path when needed, such as `SOURCE '/workspace/scripts/01_setup.cql';` on environments that support it. If cqlsh runs inside a container, the file must be mounted or copied into the **container**, not only placed on the host machine. For relative paths, check the working directory used by the **cqlsh process**; do not assume it is the Cassandra server directory.

### 5.4. Comparing SOURCE, -f, and -e

In addition to `SOURCE` inside an interactive session, you can invoke cqlsh from the terminal:

~~~bash
# Each invocation below is an independent cqlsh session.
cqlsh 127.0.0.1 9042 -f 01_setup.cql
cqlsh 127.0.0.1 9042 -f 02_inspect.cql

# Short query: explicitly specify the keyspace name to avoid context dependency.
cqlsh 127.0.0.1 9042 -e "SELECT event_time, details FROM cql_context_lab.events_by_device WHERE device_id = 'sensor-01';"
~~~

| Execution Method | Execution Session | Effect on `USE` |
| --- | --- | --- |
| Typing directly at `cqlsh>` | Current session | Takes effect for subsequent statements in the session. |
| `SOURCE 'script.cql';` | Current session | `USE` inside the file remains in effect after the file finishes running. |
| `cqlsh ... -f script.cql` | New session, runs file then exits | `USE` persists only within that file's session and does not carry over to another `-f` command. |
| `cqlsh ... -e "CQL"` | New session, runs statement then exits | Use `keyspace.table` for standalone operations to avoid context dependency. |

**Note on partial failures:** `SOURCE` or `-f` does not turn the entire file into a transaction. If one statement fails, previously succeeded changes are not automatically rolled back. Check messages, outputs, and schema/data state before re-running. Do not rely on `SOURCE` to guarantee atomic migrations.

## 6. Strategies for Managing Keyspace Context

### 6.1. Use Fully Qualified Names for High-Impact Statements

In scripts shared across multiple environments, prefer writing:

~~~sql
-- Explicit target regardless of which keyspace the session currently uses.
SELECT event_time, details
FROM cql_context_lab.events_by_device
WHERE device_id = 'sensor-01';
~~~

This allows code reviewers to determine where a query executes without tracing back every preceding `USE`. This is especially useful when scripts contain multiple `SOURCE` calls or are split across files.

### 6.2. If Using USE, Set It Explicitly at the Top of the File

~~~sql
-- Example of a file dedicated to a specific keyspace.
USE cql_context_lab;

SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';
~~~

This practice allows the file to run standalone, though you still need to control the connection environment. For a script that creates a keyspace, it must create it before `USE`. If a file might be reused across multiple clusters, **verify the endpoint and permissions** before executing.

### 6.3. Distinguishing Default Keyspace, Replication, and Consistency

| Concept | Example | Effect |
| --- | --- | --- |
| Default keyspace | `USE cql_context_lab;` | Determines how unqualified table names are resolved in the session. |
| Keyspace replication | `replication_factor: 3` in the keyspace definition | Defines the number of replicas according to the replication strategy; a schema configuration. |
| Operation consistency | `CONSISTENCY LOCAL_QUORUM;` in cqlsh | Sets read/write acknowledgment requirements for the cqlsh session, depending on replica count and datacenter. |
| Partition key | `PRIMARY KEY ((device_id), ...)` | Determines data partitioning and the primary routing path for queries. |

For example, even after running `USE cql_context_lab`, a `SELECT` by `device_id` is still routed by Cassandra to the replicas responsible for that partition. `USE` **does not** select a node to store data, nor does it substitute for proper partition key design.

## 7. Connection to Java Applications

In cqlsh, `USE` helps test statements quickly. With the Apache Cassandra Java Driver, specify the keyspace via session configuration or use fully qualified table names in CQL statements. Illustrative example with DataStax/Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("datacenter1") // Replace with the actual datacenter.
    .withKeyspace(CqlIdentifier.fromCql("cql_context_lab"))
    .build()) {

    // Default keyspace is configured on the session.
    var rows = session.execute(
        "SELECT event_time, details " +
        "FROM events_by_device WHERE device_id = 'sensor-01'");
    rows.forEach(row -> System.out.println(row.getString("details")));
}
~~~

`withKeyspace` belongs to the Java Driver session configuration and does not depend on any `USE` ever run in cqlsh. The datacenter name must match the configuration of the cluster being connected to. In production applications, use **prepared statements** for query parameters, and consider writing `keyspace.table` to make targets explicit for critical statements. To inspect schemas from Java, prefer the driver's metadata API instead of assuming every cqlsh utility command can be sent via `session.execute()`.

## 8. Common Errors and Troubleshooting

| Symptom | Common Causes | How to Check / Fix |
| --- | --- | --- |
| `No keyspace has been specified` or equivalent message | Querying an unqualified table name before `USE` | Run `USE <keyspace>;` or change to `keyspace.table`. |
| `Keyspace ... does not exist` | Typo, keyspace not created yet, or connected to the wrong cluster | Run `SHOW HOST;`, `DESCRIBE KEYSPACES;`, check the schema creation script. |
| `Table ... does not exist` | Table is not in the current keyspace or creation script has not run | Run `DESCRIBE TABLE keyspace.table;`, use the fully qualified name. |
| Valid syntax but wrong data returned | `USE` switched to another keyspace with an identically named table | Check all `USE` statements in the session/file and test querying `keyspace.table`. |
| `SOURCE` reports file not found | Wrong path, or cqlsh is running in a container/different working directory | Switch to an absolute path, verify read permissions and file location inside the cqlsh environment. |
| `SOURCE` runs partially then fails | Syntax error, data run before schema, insufficient permissions, or cluster error | Locate the failing statement, check which statements succeeded, and retry incrementally. |
| `DESCRIBE` does not show object | Wrong name/keyspace, permissions, or version differences | Use the full name, check `HELP DESCRIBE` and existing schema. |
| `Unauthorized` | Account lacks permission to view/modify schema or data | Check roles and grant appropriate permissions for the keyspace/table. |
| `Unavailable` / timeout | Insufficient replicas or system issues for the requested consistency | Check cluster, replication factor, consistency, and nodes; do not immediately blame `USE`. |

In environments with multiple clusters (local, staging, production), follow the verification order: **endpoint → keyspace → schema → statement → data**. Before any write or schema change, verify both the endpoint and the keyspace.

## 9. Self-Practice Exercises

1. Connect cqlsh, run `SHOW HOST` and `DESCRIBE KEYSPACES`, and explain why selecting a keyspace does not mean selecting a node to store data.
2. Create two keyspaces and two tables with the same name following Section 4, then use `DESCRIBE KEYSPACE` and `DESCRIBE TABLE` to identify the partition key and clustering columns.
3. Run two `SELECT ... FROM events_by_device` queries after two different `USE` statements. Explain why the result changes even though the SQL/CQL query stays identical.
4. Create `01_setup.cql` and `02_inspect.cql`, run them via `SOURCE`, and check which keyspace remains active after `02_inspect.cql` finishes.
5. Run the two files with two separate `cqlsh -f` commands. Explain why `USE` from the first file does not carry over to the session running the next file.
6. Update the query in the second file to `FROM cql_context_lab.events_by_device`; verify that it reads the lab table even after `USE cql_context_staging` has run.

**Completion criteria:** you can inspect schemas on your own with `DESCRIBE`, accurately identify the target keyspace of a query, distinguish how `USE` persists across `SOURCE` versus `-f`, and explain how to reduce accidental cross-keyspace operations in both cqlsh and Java applications.

## References

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): cqlsh commands, running files, and schema inspection.
- [Apache Cassandra — Cassandra Query Language (CQL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): schemas, keyspaces, primary keys, and CQL statements.
- [Apache Cassandra Java Driver](https://docs.datastax.com/en/developer/java-driver/4.17/): session configuration, keyspaces, and querying from Java.
