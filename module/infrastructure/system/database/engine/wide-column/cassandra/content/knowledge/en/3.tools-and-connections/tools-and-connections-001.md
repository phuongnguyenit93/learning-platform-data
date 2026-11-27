# Using cqlsh to Run Queries and Scripts

## 1. Purpose and Role of cqlsh

**cqlsh (Cassandra Query Language shell)** is the command-line tool bundled with Apache Cassandra, used to connect to a node over the native protocol (typically port 9042), send CQL statements, and view results. It is a convenient tool for learning CQL, inspecting schemas, testing queries, running initialization files, and troubleshooting connection issues. Java applications in production environments typically use the **Apache Cassandra Java Driver** to manage connection sessions and execute queries; cqlsh is primarily used for manual operations and simple administrative scripts.

After this lesson, learners will be able to:

- Connect using cqlsh and distinguish between **CQL statements** and **cqlsh-specific commands**.
- Create a keyspace/table, write and read data using queries aligned with the **partition key**.
- Run a single command using the `-e` option, or run a file using `-f` or `SOURCE`.
- Adjust session consistency, export/import CSV, and handle common errors when running scripts.

**Boundary to remember:** cqlsh connects to a node acting as the coordinator; how data is distributed and replicated to other nodes is handled by Cassandra. Being able to run a command through one node does not mean the data resides only on that node.

## 2. Preparation and Connection

Prerequisites for hands-on practice:

1. A running Cassandra instance, with the node address and native transport port (default **9042**).
2. The `cqlsh` program, preferably the version bundled with the Cassandra version in use to avoid compatibility errors.
3. Account credentials and TLS settings if the cluster enables authentication or encrypted connections.
4. A dedicated test keyspace; do not run schema-modifying commands on a production system without knowing their impact.

Open a terminal on the machine where cqlsh is installed:

~~~bash
# Connect to the node on the current machine.
cqlsh

# Specify host and port (replace the hostname according to your environment).
cqlsh db.example.internal 9042

# Example when the server requires TLS and a username.
cqlsh db.example.internal 9042 --ssl -u student

# View the options supported by your version of cqlsh.
cqlsh --help
~~~

If cqlsh runs inside a container, script files are read from the **filesystem of the environment running cqlsh**. For example, if running cqlsh in a container, you must place the file at a path the container can read, not just on the host machine. Depending on the environment, you can open a session with `docker exec -it <container-name> cqlsh`.

For clusters with authentication, configure certificates and login credentials according to system policy. Avoid passing passwords directly in the shell `-p` parameter, as they may be exposed via command history or process lists. cqlsh supports `cqlshrc` configuration and credentials files with appropriate permissions; `--ssl` does not replace the requirement for proper certificate verification.

When the `cqlsh>` prompt appears, try:

~~~sql
SHOW VERSION;
SHOW HOST;
DESCRIBE KEYSPACES;
HELP;
~~~

| Command | Meaning |
| --- | --- |
| `SHOW VERSION` | View the cqlsh, Cassandra, CQL, and protocol versions in use. |
| `SHOW HOST` | Confirm the node and cluster the session is connected to. |
| `DESCRIBE KEYSPACES` | List the keyspaces visible from the session. |
| `DESCRIBE KEYSPACE <name>` | Display the schema definition of a keyspace. |
| `HELP` or `HELP <topic>` | Look up syntax and supported commands. |
| `EXIT` or `QUIT` | Close the cqlsh session. |

**Syntax notes:** CQL uses a semicolon (`;`) to terminate statements; cqlsh commands such as `SOURCE`, `SHOW`, or `CONSISTENCY` are shell utilities, not CQL statements to be sent verbatim from the Java Driver. CQL strings are enclosed in single quotes; to include a single quote inside a string, double it (for example, `'I''m ready'`). Ordinary table/column names do not need double quotes; avoid arbitrarily using case-sensitive uppercase names.

## 3. CQL Practice: Query-Driven Table Design

Suppose a system receives device events and needs to look up **events of a device on a given day, newest first**. With Cassandra, we design the table around this query rather than starting from a normalized relational model.

At the cqlsh prompt, run:

~~~sql
-- Single-node keyspace for the lab; DO NOT use this configuration to simulate production.
CREATE KEYSPACE IF NOT EXISTS cqlsh_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cqlsh_lab;

CREATE TABLE IF NOT EXISTS events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  event_note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE cqlsh_lab.events_by_device_day;
~~~

In the primary key above:

- `(device_id, event_day)` is the **composite partition key**: events for the same device and the same day belong to the same logical partition. Splitting by day helps bound partition size along the event stream.
- `event_time` and `event_id` are **clustering columns**: they determine the order of rows within a partition and distinguish events that occur at the same timestamp.
- `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` supports reading the newest data first without client-side re-sorting.

`SimpleStrategy` with a replication factor of 1 is only meant to make the example run on a single-node environment. For multi-node/multi-datacenter clusters, use `NetworkTopologyStrategy` and a replica count matching the **actual datacenter names**; choosing the strategy and RF is a separate architectural decision and lab settings should not be copied.

Insert two records:

~~~sql
INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
   11111111-1111-4111-8111-111111111111, 'temperature', '25.1 C');

INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
   22222222-2222-4222-8222-222222222222, 'temperature', '25.3 C');

SELECT event_time, event_id, event_type, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Expected result: **2 rows**, with the event at `01:05:00Z` appearing before the event at `01:00:00Z`. The query specifies the full partition key, so the coordinator knows which partition to read. Conversely, a query filtering only by `event_type = 'temperature'` does not match the table's query model and may be rejected because it requires a broad data scan/filter. Do not add `ALLOW FILTERING` just to bypass a design issue; design another table for a different query pattern when needed.

In Cassandra, `INSERT` is an **upsert** operation: writing with the same primary key can update existing data. Therefore, re-running a seed script with the same keys does not create additional records, but not every write script should be assumed safe to re-run (especially when using TTL, write timestamps, `UPDATE`, or `DELETE`).

## 4. Three Ways to Run Commands and Scripts

### 4.1. Direct Interactive Mode

Enter individual CQL statements at the `cqlsh>` prompt; a single statement can span multiple lines and ends with `;`. Suitable for exploring schemas or testing queries before saving them to a file.

~~~sql
USE cqlsh_lab;
SELECT event_time, event_note
FROM events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
~~~

### 4.2. Run a Single Statement and Exit with `-e`

`-e` is useful for simple checks in a terminal or lightweight automation:

~~~bash
cqlsh 127.0.0.1 9042 -e "SHOW VERSION;"

cqlsh 127.0.0.1 9042 -e "SELECT event_time, event_note FROM cqlsh_lab.events_by_device_day WHERE device_id = 'sensor-01' AND event_day = '2026-11-21' LIMIT 10;"
~~~

The string passed to `-e` is subject to the quoting rules of the shell in use. Long CQL statements or multi-step operations should be placed in a `.cql` file for easier inspection, version control, and re-execution.

### 4.3. Run `.cql` Files with `-f` or `SOURCE`

Example split into two files with **illustrative content** as follows.

File `01_schema.cql`:

~~~sql
-- Create the structure to serve event queries by device/day.
CREATE KEYSPACE IF NOT EXISTS cqlsh_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS cqlsh_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  event_note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

File `02_seed.cql`:

~~~sql
-- Always specify the keyspace explicitly so it does not depend on a USE statement from another session.
INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
   11111111-1111-4111-8111-111111111111, 'temperature', '25.1 C');

INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
   22222222-2222-4222-8222-222222222222, 'temperature', '25.3 C');
~~~

From the terminal, inside the directory containing both files:

~~~bash
cqlsh 127.0.0.1 9042 -f 01_schema.cql
cqlsh 127.0.0.1 9042 -f 02_seed.cql
~~~

Or from an open cqlsh session:

~~~sql
SOURCE '01_schema.cql';
SOURCE '02_seed.cql';
~~~

| Execution Method | When to Use | What to Remember |
| --- | --- | --- |
| Typing at `cqlsh>` | Testing individual statements, checking results immediately | Must maintain the correct keyspace context for the session. |
| `-e "..." ` | A short query or command | Be careful with terminal escaping rules. |
| `-f path/file.cql` | Schema initialization, data seeding, repeatable operations | cqlsh runs the statements in the file and then exits. |
| `SOURCE 'path/file.cql'` | Running a file directly inside an interactive session | The path must be accessible from where cqlsh is running. |

**Order matters:** the keyspace and table must be created before inserting data. The two `cqlsh -f` commands in the example run in **two independent sessions**, so the seed file uses the fully qualified table name. A script file containing multiple statements is **not a global transaction**: if a later statement fails, earlier statements may have already completed and will not automatically roll back. When integrating into a deployment workflow, manage schema versions, log results, and verify data after execution; `IF NOT EXISTS` does not automatically update an existing schema if its definition has changed.

## 5. cqlsh Commands for Inspection and Diagnostics

The commands below run inside cqlsh:

~~~sql
-- Inspect the existing structure.
DESCRIBE KEYSPACE cqlsh_lab;
DESCRIBE TABLE cqlsh_lab.events_by_device_day;

-- Maximum 20 rows per page; keep pagination enabled when viewing large datasets.
PAGING 20;

-- Display each row vertically when there are many columns or long values.
EXPAND ON;
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
EXPAND OFF;

-- Temporarily enable tracing to observe the query execution path.
TRACING ON;
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21'
LIMIT 10;
TRACING OFF;
~~~

`TRACING` should only be enabled when investigating issues because it incurs processing overhead and stores trace information. `PAGING` prevents cqlsh from fetching and printing all results at once, but it **does not turn a wide scan query into a good query**.

### 5.1. Adjusting Session Consistency

~~~sql
-- Suitable for a lab with only one replica.
CONSISTENCY ONE;

-- Example when running on a suitable cluster with enough replicas in the datacenter.
CONSISTENCY LOCAL_QUORUM;

-- For conditional updates using IF (lightweight transactions) when needed.
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

`CONSISTENCY` changes the consistency level for subsequent operations **in the current cqlsh session**; it does not change the keyspace's replication factor and does not automatically affect any Java clients. At `LOCAL_QUORUM`, with RF = 3 in a datacenter, responses from at least **2 replicas** in that datacenter are typically required. On an RF = 1 lab cluster, `ONE` is sufficient for practice; increasing consistency cannot create missing replicas. `SERIAL CONSISTENCY` applies only to the coordination phase of conditional writes using `IF`.

### 5.2. Saving Output and Exporting/Importing CSV

~~~sql
-- Capture only query results into a file on the machine running cqlsh.
CAPTURE 'query-output.txt';
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
CAPTURE OFF;

-- Export table data to CSV with a header row.
COPY cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
TO 'events.csv' WITH HEADER = TRUE;

-- Import CSV into an existing table with a compatible schema.
COPY cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
FROM 'events.csv' WITH HEADER = TRUE;
~~~

`CAPTURE` records **query output**, not all error messages or output from special commands. `COPY TO` reads the entire table's data and can be resource-intensive; `COPY FROM` writes data from CSV into an existing table. Verify column order, data types, empty values, date/time formats, and error files when importing. `COPY` is suitable for small datasets and testing purposes; for large volumes of data, consider dedicated bulk tools (such as DSBulk) and proper backup/restore procedures. Exporting to CSV does not replace a full cluster backup.

## 6. Common Errors When Running cqlsh and Scripts

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| Cannot connect to host/port 9042 | Node not ready, wrong host/port, DNS or firewall, native transport configuration | Check the Cassandra service, endpoint, and network connectivity from the machine running cqlsh. |
| Authentication or authorization error | Wrong credentials or account lacks CQL permissions | Check auth configuration, roles, and keyspace/table permissions. |
| TLS/SSL handshake error | Server requires TLS, CA trust/certificate configuration mismatch | Use the proper `--ssl` mode and certificate configuration matching the cluster. |
| `SyntaxException` | Missing `;`, incorrect single quotes, wrong column name, or CQL syntax error | Re-run statements individually; check `HELP`, `DESCRIBE TABLE`, and string literals. |
| Table/keyspace does not exist | Seed run before schema, wrong environment, forgot `USE` | Check `SHOW HOST` and `DESCRIBE`; use `keyspace.table` names. |
| Query cannot execute without additional filtering | `WHERE` does not align with partition key/clustering columns | Adjust the query pattern and design the table for the query to be served. |
| `Unavailable`, `ReadTimeout`, `WriteTimeout` | Insufficient replicas responding for consistency, or overloaded nodes/network | Check replica status, RF, consistency, and system root causes; avoid merely increasing timeouts. |
| `SOURCE`/`-f` file not found | File is not in the environment/path readable by cqlsh | Verify working directory, read permissions, and path on the executing host/container. |
| Errors during CSV import | Wrong header, column order, data types, timestamp/UUID format | Cross-check schema, inspect the import error file, and test with a few rows first. |

If a script runs partially and then fails, identify **which statements already succeeded** before re-running it. Check `DESCRIBE`, `SELECT` by partition key, and cqlsh messages; do not assume all changes will be rolled back.

## 7. Self-Practice Exercises

1. Connect and record the output of `SHOW HOST` and `SHOW VERSION`. Explain whether the node receiving the connection stores all of the data.
2. Create the two files `01_schema.cql` and `02_seed.cql` as shown above, run them with `-f`, and verify the results with `-e`.
3. Re-run `01_schema.cql` and explain the effect of `IF NOT EXISTS`. Re-run the seed file and check why the row count does not increase if the primary key does not change.
4. In cqlsh, run the same query with `PAGING 20` and `EXPAND ON`; enable `TRACING ON` temporarily and turn it off immediately after observing.
5. Export the table to CSV, inspect the header/columns; only test importing into a lab environment with a compatible table. Explain why `COPY TO` is not a cluster backup.

**Completion criteria:** read and write two events in the right partition, execute scripts using both `-f` and `SOURCE`, distinguish cqlsh commands from CQL, understand the impact of consistency, and identify common causes when a script fails.

## References

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): connection options, `SOURCE`, `CONSISTENCY`, `COPY`, `CAPTURE`, `PAGING`, and `TRACING`.
- [Apache Cassandra — Cassandra Query Language (CQL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): schema syntax, data types, primary keys, and queries.
