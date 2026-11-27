# Recording Statements, Session Settings, and Results to Reproduce Experiments

## 1. What Does Reproducing a Cassandra Experiment Mean?

Apache Cassandra is a **distributed wide-column database**. A `SELECT` or `INSERT` run via `cqlsh` or the Java Driver does not depend solely on the CQL text: the outcome also depends on **schema, partition key, input data, replication factor (RF), consistency level (CL), coordinator, Cassandra version, and replica state**. Therefore, pasting a single statement into a chat thread is not enough for someone else to reproduce an experiment.

In the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this skill builds the foundation for CQL labs, choosing partition keys, evaluating read/write consistency levels, observing compaction/repair, troubleshooting timeouts, and Java application connectivity.

An experiment is considered **reproducible** when someone else receives all information needed to:

1. Prepare an equivalent **environment and initial data state**.
2. Execute the **exact operations in the exact order**, with known session settings.
3. Obtain the **expected results** or clearly know the acceptable tolerances for variance.
4. Distinguish differences caused by **experiment mistakes** from normal distributed-system variance.

Not every number will be identical across runs. Execution time, selected coordinator, SSTable count, cache state, tracing session UUIDs, and background load can vary. What must be reproduced are the **inputs, semantics, and measurement conditions**, while variable quantities must specify how they are measured and compared.

**Lesson objectives:**

- Capture CQL scripts, cqlsh settings, and client/server/native protocol versions.
- Deliberately use `SHOW VERSION`, `SHOW HOST`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, `SOURCE`, `CAPTURE`, and the `-f`/`-e` options.
- Collect output for **both successes and errors**, without mistaking `CAPTURE` for a complete transcript.
- Build a lab with **fixed primary keys, explicit timestamps, and verifiable expected results**.
- Record manifests, run logs, and checksums, redact sensitive information, and guide others to re-run.
- Compare cqlsh results with how experiments are recorded in the Java Driver.

## 2. Required Components of an Experiment Record

A solid reproducibility record includes the following groups:

| Group | Information to Record | Why It Matters |
| --- | --- | --- |
| **Objective / hypothesis** | E.g., "SELECT by partition key returns 2 rows, ordered by clustering order DESC" | Clarifies what is being tested rather than running ad-hoc checks. |
| **Environment** | Cassandra, cqlsh, and native protocol versions, OS/container image, UTC timestamp | Helps explain differences in syntax, protocol, and behavior. |
| **Topology** | Cluster/DC, relevant node list, keyspace RF, replica states | Separates single-node vs. multi-node cluster differences. |
| **Initial schema** | `CREATE KEYSPACE`, `CREATE TABLE`, partition/clustering keys, table options | The same query on a differently defined table can behave differently. |
| **Input data** | Values, UUIDs, timestamps, how fixtures are generated, and how the lab is reset | Prevents leftover data from earlier runs. |
| **cqlsh session** | Contact point, `USE`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, timezone, timeout | Avoids relying on hidden shell defaults. |
| **Operations** | Verbatim scripts, execution order, parameters, tool versions | Enables exact step-by-step re-execution. |
| **Observations** | stdout, stderr/errors, exit status, results, trace ID if tracing was enabled | Sufficient for analysis when expectations are not met. |
| **Evaluation** | Expected vs. actual, row/value checks, conclusion, limitations | Distinguishes "script exited" from "experiment passed." |
| **Integrity and security** | File hashes, operator/host, artifact access controls, redacted secrets | Prevents file mix-ups and credential/data leaks. |

**Principle:** a passing `SELECT` result does not prove replication settings, peer health, or consistency were configured properly. To claim "read at `LOCAL_QUORUM`," record **RF, DC, and CL** rather than merely pasting a few output lines.

### 2.1. Input → Execution → Evidence Model

~~~mermaid
flowchart TD
    ENV["Environment: version, topology, auth/TLS"] --> RUN["cqlsh or Java session"]
    SCHEMA["Schema + fixture data"] --> RUN
    SESSION["CL, serial CL, paging, tracing, timeout"] --> RUN
    SCRIPT["Ordered scripts, input hashes"] --> RUN
    RUN --> OUTPUT["stdout/stderr, CQL results, trace"]
    OUTPUT --> CHECK["Compare expected vs. actual"]
    ENV --> MANIFEST["Run manifest + timestamp + checksums"]
    SCRIPT --> MANIFEST
    CHECK --> MANIFEST
~~~

When sharing an experiment, provide the **scripts and manifest** alongside sanitized results. Never send only a screenshot missing timestamps, versions, and the CQL statements executed.

## 3. Organizing Experiment Directories Without Mixing Inputs and Outputs

A reference layout:

~~~text
cassandra-experiment/
  README.md                # objective, prerequisites, how to run, and expected results
  input/
    00-schema-and-seed.cql # create schema and fixture data
    10-checks.cql          # session settings and verification queries
  runs/
    run-20261121T020000Z/
      manifest.yml         # versions/topology/config (no secrets)
      setup.log            # stdout+stderr during setup
      checks.log           # stdout+stderr during verification
      query-results.txt    # output created by CAPTURE (if used)
      expected-vs-actual.md
      checksums.sha256
~~~

This is an **example directory structure**, not files automatically generated by Cassandra. `input/*.cql` files should be reviewed and version-controlled; `runs/*` can be stored in an access-controlled artifact store. If outputs contain customer data, tokens, internal IPs, or usernames, **anonymize or restrict access** before sharing.

Never record real passwords, private keys, secret manager contents, or full copies of `credentials`/`cqlshrc` containing secrets inside experiment records. For TLS, usually only **"TLS enabled, CA profile X"** and a separately managed configuration reference are needed.

### 3.1. Why Should Each Run Have Its Own Directory?

- `CAPTURE` **appends** to the specified file; reusing an old file mixes previous and new results.
- Logs/traces and timestamps change on every run.
- A/B run comparisons are easier when each result set has its own manifest, checksums, and measurement conditions.
- When investigating failures, you need to know which output corresponds to which **script hash and session config**.

If reusing the same output filenames, explicitly **create a new file, archive, or clean old lab outputs** before running. Never delete production data or logs to clean up an experiment.

## 4. Recording the Environment and cqlsh Version

### 4.1. Information from the cqlsh Session

Open the shell in the lab:

~~~bash
# Open cqlsh to the lab node on the default native port.
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
-- cqlsh-specific commands, not Java application CQL queries.
SHOW VERSION;
SHOW HOST;

SELECT cluster_name, data_center, rack, release_version
FROM system.local;
~~~

`SHOW VERSION` records the **cqlsh, Cassandra, CQL spec, and connected native protocol versions**. `SHOW HOST` identifies the node/port **this cqlsh session** is connected to; it is not a list of the entire cluster.

When cqlsh and the server differ in version, some special commands and options may be incompatible. Per official documentation, cqlsh is generally **guaranteed compatible** only with its bundled Cassandra release; therefore record both versions rather than writing merely "Cassandra 4.x."

### 4.2. Schema and Topology Metadata

~~~sql
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE repro_lab;

-- Run after creating repro_lab in Section 6.
SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repro_lab';

SELECT cluster_name, data_center, rack, release_version, schema_version
FROM system.local;
~~~

`DESCRIBE KEYSPACE` returns DDL describing the schema; `system_schema.keyspaces` shows the replication map, which is vital when explaining results of `ONE`, `QUORUM`, or `LOCAL_QUORUM`. If running these queries **before** creating the lab, omit the `repro_lab` queries or explicitly note `keyspace does not exist yet`; do not hide schema creation steps.

From an authorized admin machine with JMX access, also capture:

~~~bash
# Execute via nodetool on an authorized node, not inside cqlsh.
nodetool status
nodetool describecluster
~~~

`nodetool status` is a **cluster status snapshot** from the queried node's viewpoint; it does not guarantee every replica can serve requests throughout the experiment. Record the snapshot timestamp, especially during bootstrap, repair, or topology changes.

### 4.3. Environment Parameters That Are Easily Overlooked

| Factor | How to Record / Verify | Consequence If Omitted |
| --- | --- | --- |
| Datacenter and RF | `system.local.data_center` + `system_schema.keyspaces.replication` | `LOCAL_QUORUM` can require different replica counts. |
| Native endpoint | `SHOW HOST`, DNS/IP/port, and TLS enabled/disabled | May have connected to the wrong cluster or a different node. |
| Timezone / locale | `cqlshrc` settings, UTC timestamp, input timestamp format | Formatted timestamp strings and displayed output differ. |
| Driver / cqlsh version | `SHOW VERSION`, Java Driver dependency | Differences in native protocol, serialization, and paging. |
| Schema state | `DESCRIBE TABLE` + schema version / DDL hash | Old queries may be incompatible with a newer schema. |
| Cache / compaction / repair | Timestamped metrics/logs/snapshots | Can cause latency fluctuations even with identical logical data. |
| Auth / TLS | Security mode and config profile **with secrets redacted** | Handshake/auth failures cannot be explained by CQL text alone. |

For performance analysis, also record CPU/RAM/disk resources, concurrent requests, page size, request timeout, warm/cold cache state, and background compaction activity; **a single run is insufficient for benchmark conclusions**.

## 5. Explicitly Recording Session Settings: Never Rely on Defaults

The following cqlsh commands modify the **active session**:

~~~sql
-- Set session context explicitly.
USE repro_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
PAGING OFF;
TRACING OFF;
~~~

Meaning:

| Command | Controls | Scope and Notes |
| --- | --- | --- |
| `USE repro_lab` | Default keyspace for unqualified table names | Session-only; use `repro_lab.table` to avoid context dependence. |
| `CONSISTENCY ONE` | CL for subsequent cqlsh requests | Does not alter Java Driver defaults or other cqlsh sessions. |
| `SERIAL CONSISTENCY SERIAL` | Serial CL for conditional `IF` writes (LWT/Paxos) | Does not change regular CL; does not affect regular `SELECT` semantics. |
| `PAGING OFF` | Disables interactive pagination for small queries | Avoids pagination prompts on small results; do not turn off paging for large sets. |
| `TRACING OFF` | Disables per-query trace printing | Tracing adds overhead and alters latency characteristics. |

With RF = 1 in the lab below, `CONSISTENCY ONE` is meaningful and reads/writes require only one replica. **Do not change production CL just to "make errors disappear" for comparison** when a cluster cannot meet quorum.

### 5.1. Recording What CLI Flags and `cqlshrc` Control

Examples of options that affect a run:

~~~bash
# View options supported by your current cqlsh version.
cqlsh --help
cqlsh --version

# Example script invocation with explicit timeouts on a supported version.
cqlsh 127.0.0.1 9042 --no-color \
  --connect-timeout=5 \
  --request-timeout=10 \
  -f input/10-checks.cql
~~~

The values `5` and `10` are **illustrative** choices only, not general production recommendations. Record both CLI flags and the path to any `cqlshrc` config file used. The default config file is typically `~/.cassandra/cqlshrc`, or specified via `--cqlshrc`; usernames/passwords may come from a separate credentials file protected by file permissions.

**Never copy a credentials file verbatim** into artifacts to prove reproducibility. Instead, record `"auth provider: PasswordAuthenticator; credential reference: secret-id (redacted)"` and instruct authorized operators to supply credentials themselves.

### 5.2. `PAGING` and `TRACING` Can Alter Observations

Separate interactive example:

~~~sql
PAGING 2;
TRACING ON;

SELECT event_time, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

TRACING OFF;
PAGING OFF;
~~~

`PAGING 2` fetches results in small pages; interactively, it may prompt the user to advance to the next page. In automated scripts, verify **all pages were read** before comparing outputs. `TRACING ON` prints execution details and generates a **trace session ID**; timings and IDs change on every run.

Therefore, separate runs into:

- **Functional run**: `PAGING OFF` for small datasets, `TRACING OFF`, verify values.
- **Diagnostic run**: enable tracing or custom page sizes and clearly note the output is observational, not for byte-for-byte comparison with functional runs.

## 6. Lab: CQL Scripts with Fixed Data and Expected Results

This entire section assumes **a single-node Cassandra lab, RF = 1, and no production data**. You will create **two CQL files** as described below inside your experiment's `input/` directory.

### 6.1. File `input/00-schema-and-seed.cql`

~~~sql
-- 00-schema-and-seed.cql
-- Isolated lab. RF=1 is strictly for practicing on one node.
CREATE KEYSPACE IF NOT EXISTS repro_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS repro_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  metric text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- WARNING: TRUNCATE deletes all data in the table!
-- Permitted only in a standalone lab after verifying cluster and keyspace.
-- This reset step ensures every run starts from the exact same dataset.
TRUNCATE repro_lab.events_by_device_day;

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.4);

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:02:00Z',
        33333333-3333-4333-8333-333333333333, 'humidity', 61.0);
~~~

Keep **primary keys and timestamps in fixture data** fixed to avoid "random" records. `TRUNCATE` is solely for **resetting the lab table** and is **unsafe on shared/production tables**. Before running, verify `SHOW HOST`/cluster and table names; if you lack `TRUNCATE` permission, create a fresh lab keyspace intentionally rather than escalating privileges.

Note: `IF NOT EXISTS` **does not modify an existing schema that differs**. If `repro_lab.events_by_device_day` already existed with a different structure, `CREATE TABLE IF NOT EXISTS` will not fix it; compare `DESCRIBE TABLE` against the script. `TRUNCATE` clears existing rows in a table; it is not a schema-creation CQL statement.

### 6.2. File `input/10-checks.cql`

~~~sql
-- 10-checks.cql
-- Explicit session config: avoid relying on cqlshrc defaults.
USE repro_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
PAGING OFF;
TRACING OFF;

SHOW HOST;
SHOW VERSION;

DESCRIBE TABLE repro_lab.events_by_device_day;

SELECT cluster_name, data_center, release_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repro_lab';

-- Primary query: specify the full composite partition key.
SELECT event_time, event_id, metric, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;

-- Check row count for a single partition without scanning the entire table.
SELECT COUNT(*)
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

**Logical results that must match:**

| Check | Expected After Successful Reset / Seed |
| --- | --- |
| Schema | Table has composite partition key `(device_id, event_day)` and clustering `event_time DESC, event_id ASC`. |
| Query `sensor-01` | Exactly **2 rows**, in order `01:05:00Z / 25.4` and `01:00:00Z / 25.1`. |
| `COUNT(*)` for `sensor-01`, `2026-11-21` | Equals **2**. |
| Query `sensor-02` if also run | One row `humidity / 61.0` at `01:02:00Z`. |
| Metadata | Keyspace `repro_lab` has `SimpleStrategy`, RF = 1. |
| `SHOW HOST` / `SHOW VERSION` | Contains **actual** endpoint and version, not hardcoded to match the author's machine. |

Do not use full-table `SELECT COUNT(*) FROM repro_lab.events_by_device_day` as a default verification check on large datasets: full-table counts scan many partitions. This lab counts only a small, explicitly keyed partition.

### 6.3. Running Both Files with `cqlsh -f`

In a **Linux/macOS** terminal inside the prepared experiment directory:

~~~bash
# Run on the exact machine/container that has cqlsh and the input files.
# Update the run name and output directory before each execution.
mkdir -p runs/run-001

# Capture BOTH stdout and stderr, including errors outside CQL result tables.
cqlsh 127.0.0.1 9042 --no-color \
  -f input/00-schema-and-seed.cql \
  > runs/run-001/setup.log 2>&1
setup_status=$?

cqlsh 127.0.0.1 9042 --no-color \
  -f input/10-checks.cql \
  > runs/run-001/checks.log 2>&1
checks_status=$?

printf 'setup_exit=%s\nchecks_exit=%s\n' "$setup_status" "$checks_status"
~~~

`-f` runs all statements in a file and exits; `-e` runs a single statement and exits, for example:

~~~bash
cqlsh 127.0.0.1 9042 -e "SHOW VERSION;"
cqlsh 127.0.0.1 9042 -e "SELECT data_center FROM system.local;"
~~~

Important when evaluating:

- Run `10-checks.cql` **only after** `00-schema-and-seed.cql` finishes and its setup log has been checked.
- Read **both `setup.log` and `checks.log`**, confirming there are no `SyntaxException`, `Unauthorized`, `Unavailable`, `ReadTimeout`, or parse/type errors.
- Record the **exit status**, yet **never treat exit status = 0 as sole proof** that every CQL statement or business assertion succeeded. Depending on cqlsh version and execution mode, inspecting logs and verifying data remain essential.
- `-f` files and output paths are resolved on the **machine running cqlsh**. If cqlsh runs inside a container, files must exist inside the container or a mounted volume.
- `-f`/`SOURCE` **do not create a multi-statement transaction**. If a statement fails mid-file, earlier writes do not automatically roll back; re-run from a controlled state.
- Timeout/TLS/auth flags and log file permissions must match the real environment; never place passwords on the command line or in logs.

`SOURCE` is the conceptual counterpart inside an **interactive cqlsh session**:

~~~sql
-- Run only in a lab environment after verifying you are on the right cluster!
SOURCE 'input/00-schema-and-seed.cql';
SOURCE 'input/10-checks.cql';
~~~

`SOURCE` and `-f` re-execute the **original commands**, whereas `HISTORY` only recalls typed lines without guaranteeing complete parameters or inputs for reproduction.

## 7. `CAPTURE`, stdout/stderr, and `HISTORY`: Three Different Kinds of "Recording"

### 7.1. `CAPTURE` Does Not Record the Full Transcript

In an interactive cqlsh session:

~~~sql
CAPTURE 'runs/run-001/query-results.txt';

SELECT event_time, event_id, metric, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

CAPTURE OFF;
CAPTURE;
~~~

Per cqlsh documentation:

1. `CAPTURE 'file';` starts **appending** CQL query results to the file, **without overwriting** prior content.
2. While capturing, query output does not print normally to the terminal.
3. `CAPTURE OFF;` stops capturing and returns output display to the shell.
4. `CAPTURE;` with no arguments checks capture status.
5. **Only query results are captured. Errors and output from cqlsh-specific commands** (such as `SHOW VERSION`, `CONSISTENCY`, `DESCRIBE`, `TRACING`) **are not fully captured by `CAPTURE`**; they may still appear in the interactive session.

Therefore, **a capture file is not an audit log**. For experiments, save the **scripts** and **stdout/stderr transcripts** from non-interactive runs or controlled logging mechanisms. When errors occur, never conclude "no errors happened" merely because `query-results.txt` contains no error lines.

### 7.2. Comparing the Three Recording Methods

| Method | What It Records | What It Cannot Replace |
| --- | --- | --- |
| `CAPTURE 'path'` | CQL query results printed by cqlsh while capture is active | Does not fully record errors, special commands, or source scripts. |
| Shell redirect `> run.log 2>&1` with `cqlsh -f` | stdout/stderr output of the **cqlsh process** | Does not prove expected/actual checks on its own or preserve server state. |
| `HISTORY 20` / cql history file | Prior interactive statements (depending on version/config) | Not a manifest; lacks fixture data, RF/CL, and full stdout. |

If an interactive transcript of both input and output is needed, use an approved terminal recorder, while controlling **credential prompts, secrets, and sensitive data**. Any video/terminal capture must still be accompanied by **scripts + manifest** so others can re-run without manual typing.

### 7.3. `HISTORY` and Secret Exposure Risks

~~~sql
-- View recent command history as supported by your cqlsh version.
HISTORY 20;
~~~

Per current documentation, cqlsh typically saves history at `~/.cassandra/cql_history`. On Cassandra 4.0 and newer, history recording can be disabled via `--disable-history`, `cqlshrc` settings, or redirected via `CQL_HISTORY` depending on OS/config; verify support in your running version.

**Command history is not safe for storing passwords.** In particular, statements such as `CREATE ROLE ... PASSWORD '...'` embed secrets in CQL text, which can leak into history, logs, clipboards, or artifacts. Manage roles/credentials through approved security workflows and never attach raw history to experiment outputs.

## 8. Creating Manifests and Checksums So Others Know What Ran

A **reference** manifest for `run-001`, containing no secrets:

~~~yaml
experiment_id: cassandra-repro-lab-001
purpose: "Verify partition key and clustering order"
run_id: run-001
started_at_utc: "2026-11-21T02:00:00Z" # sample timestamp, replace with actual
client:
  tool: cqlsh
  version: "RECORD_FROM_SHOW_VERSION"
  native_protocol: "RECORD_FROM_SHOW_VERSION"
  contact_point: "127.0.0.1:9042"
  tls: false # local lab example only
server:
  cassandra_release: "RECORD_FROM_SYSTEM_LOCAL"
  cluster_name: "RECORD_FROM_SYSTEM_LOCAL"
  datacenter: "RECORD_FROM_SYSTEM_LOCAL"
  replication: "SimpleStrategy/RF=1"
session:
  keyspace: repro_lab
  consistency: ONE
  serial_consistency: SERIAL
  paging: OFF
  tracing: OFF
files:
  schema_and_seed: input/00-schema-and-seed.cql
  checks: input/10-checks.cql
  setup_log: runs/run-001/setup.log
  checks_log: runs/run-001/checks.log
expected:
  sensor_01_rows: 2
  sensor_01_latest_value: 25.4
validation: "RECORD_PASS_OR_FAIL_AFTER_VERIFICATION"
~~~

The `RECORD_FROM_...` values are **explanatory placeholders** and must be replaced with real values before sharing. `started_at_utc` above is not the timestamp of an actual experiment run. If using a tool to generate manifests automatically, it should record **script hashes, actual timestamps, client/server versions, exit codes, and verification outcomes**.

### 8.1. Hashing Input Files

On Linux (or macOS with GNU coreutils installed), after creating the experiment files:

~~~bash
# Hash proving exact input bytes used.
sha256sum input/00-schema-and-seed.cql input/10-checks.cql \
  > runs/run-001/checksums.sha256

# When verifying, run from the same directory layout.
sha256sum -c runs/run-001/checksums.sha256
~~~

On default macOS without GNU `sha256sum`, substitute `shasum -a 256`:

~~~bash
shasum -a 256 input/00-schema-and-seed.cql input/10-checks.cql \
  > runs/run-001/checksums.sha256
shasum -a 256 -c runs/run-001/checksums.sha256
~~~

On Windows PowerShell, you can use:

~~~powershell
Get-FileHash -LiteralPath .\input\00-schema-and-seed.cql -Algorithm SHA256
Get-FileHash -LiteralPath .\input\10-checks.cql -Algorithm SHA256
~~~

Hashes detect modified input files, but **do not prove cluster data remained unchanged**. To ensure reproducibility, the manifest must also record data source state, schema, reset policy, and operational conditions. When input data comes from a large CSV, hash both the **source CSV and mapping scripts**.

### 8.2. Comparing Expected vs. Actual

Example post-run record:

~~~text
Run: run-001 (lab local)
Input: 00-schema-and-seed.cql + 10-checks.cql
Session: ONE / SERIAL / PAGING OFF / TRACING OFF
Expected: 2 rows for (sensor-01, 2026-11-21)
Observed: 2 rows, 01:05Z=25.4; 01:00Z=25.1
Result: PASS
Notes: Latency not measured; multi-node replication not verified.
~~~

This is a **record template**, not output from a Cassandra instance actually executed in this article. If you observe only 1 row, never edit `expected` to make it match: investigate ingestion logs, schema, primary keys, timezones, write errors, or whether you connected to the wrong cluster.

## 9. Reproducing Consistency, Paging, and Tracing Experiments

A report saying only "`SELECT` succeeded" is insufficient when investigating distributed consistency. Categorize carefully:

### 9.1. Read Experiments Across Consistency Levels

| Variable to Hold Constant | How to Record |
| --- | --- |
| Keyspace + RF/DC | `DESCRIBE KEYSPACE` or `system_schema.keyspaces` |
| Dataset + partition | Known primary keys and fixture values |
| Query text | Versioned CQL script |
| CL | `CONSISTENCY ONE`, `QUORUM`, `LOCAL_QUORUM`... |
| Available nodes / replicas | Timestamped `nodetool status` and logs |
| Timestamp, run count | UTC timestamp and run ID |

**Theoretical example:** in a datacenter with RF = 3, `LOCAL_QUORUM` requires 2 replicas to respond. In an RF = 1 lab, `LOCAL_QUORUM` needs only 1 replica in that DC. To measure a scenario where one replica is unavailable, use a **multi-node lab cluster** and controlled fault experiments; never shut down a production node to produce screenshots for a lesson.

### 9.2. LWT Experiments Must Record Two Consistency Levels

~~~sql
-- Settings used for LWT queries when IF is present.
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
~~~

**Regular consistency** and **serial consistency** are two distinct values. `SERIAL CONSISTENCY` applies only to the serial/Paxos phase of conditional `IF` operations. When comparing LWTs, also record the **initial row state**, because `INSERT ... IF NOT EXISTS` returns `[applied] = true` on the first run and may return `false` on re-runs. You cannot claim "not reproducible" simply because the input state itself changed.

### 9.3. Paging and Timing Measurements

With `PAGING 2`, cqlsh may prompt the user for subsequent pages. If only the first page is recorded, results may appear **missing rows** rather than actually missing data. For timing measurements, distinguish:

- **Coordinator request time**.
- **Client-side time** (including network, deserialization, page fetches, and prompt wait time).
- **Full script runtime** (including connection setup, schema creation, seeding, and terminal printing).

`TRACING ON` adds overhead and trace events depend on the handling coordinator/replicas. Latency comparisons should use multiple runs, warm-up where appropriate, percentiles, and comparable background configurations. **Never compare a traced query directly against an untraced query as an objective benchmark.**

## 10. Recording When an Experiment Fails

### 10.1. Errors Are Valid Observations Too

If the goal is testing `CONSISTENCY TWO` on an RF = 1 lab, an `Unavailable` error is an **expected** observation, not proof of a broken script. Conversely, if a partition-key `SELECT` expected to succeed returns `Unauthorized`, the experiment failed its login/permission prerequisites.

| Error | Additional Evidence to Record | What to Avoid |
| --- | --- | --- |
| `SyntaxException`, `InvalidRequest` | Query, line/token, `DESCRIBE TABLE`, version | Do not edit the query without updating the script hash/version. |
| `AuthenticationException` | Secret-redacted TLS/auth config, role name if permitted, endpoint | Do not print passwords to run logs; do not brute-force. |
| `Unauthorized` | Granted permissions, active role, table/command | Do not disable the authorizer or switch to admin to fake a PASS. |
| `Unavailable` | CL, RF, DC, required/alive replica counts, `nodetool status` | Do not lower production CL just to make the report look clean. |
| `ReadTimeout` | Request timeout, CL, query pattern, tombstones/latency, replica state | Do not treat timeout as "0 rows." |
| `WriteTimeout` | Primary key, idempotency, responding replicas, data read back | Do not blindly retry; the operation may have written partially/fully. |
| `AllNodesFailedException` | Contact points, peer addresses, DNS/TCP/TLS/native protocol, local DC | Do not blame CQL query syntax when the session never connected. |

When a run fails, keep the **original scripts immutable** and create a **new run** after fixing rather than overwriting results in the old run directory. Document clearly: "Attempt 1 hit error X; Attempt 2 fixed Y; Result Z."

### 10.2. Discrepancy Analysis Workflow

~~~mermaid
flowchart TD
    A["Re-run result differs from expected"] --> B{"Are scripts and initial data identical?"}
    B -->|"No"| C["Check hashes, fixtures, reset, keyspace"]
    B -->|"Yes"| D{"Are versions/schema/session identical?"}
    D -->|"No"| E["Compare SHOW VERSION, DDL, CL, paging, timeout"]
    D -->|"Yes"| F{"Permission/TLS or replica error?"}
    F -->|"Yes"| G["Check auth, node status, RF, internode"]
    F -->|"No"| H{"Logical mismatch or only latency/trace?"}
    H -->|"Logical"| I["Investigate concurrent writes, TTL, timestamps, LWT"]
    H -->|"Latency"| J["Controlled repeats, metrics, GC, compaction, load"]
~~~

In Cassandra, **identical schemas** do not guarantee identical data: replicas may be in different states, or concurrent writers, TTL/tombstones, or topology changes may be involved. Never tamper directly with `system_schema`/`system` to "sync" an experiment.

## 11. Java Driver: Recording Experiments at the Statement Level

`CONSISTENCY`, `PAGING`, `CAPTURE`, and `SHOW VERSION` belong to **cqlsh** and do not automatically apply to separate Java sessions. In Java Driver 4.x, each statement can specify consistency, page size, and timeout so experiments do not depend on implicit defaults.

Example using the **table and fixtures** created in Section 6; requires the `com.datastax.oss.driver` dependency compatible with your project's Cassandra/Java versions:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;

public class ReproduceCassandraQuery {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        Instant startedAt = Instant.now();
        System.out.println("started_at_utc=" + startedAt);
        System.out.println("contact_point=" + host + ":9042");
        System.out.println("local_dc=" + dc);

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, metric, value " +
                "FROM repro_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement statement = prepared.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int count = 0;
            for (Row row : session.execute(statement)) {
                count++;
                System.out.println(
                    row.getInstant("event_time") + "," +
                    row.getUuid("event_id") + "," +
                    row.getString("metric") + "," +
                    row.getDouble("value"));
            }
            System.out.println("row_count=" + count);
            if (count != 2) {
                throw new IllegalStateException("Expected 2 rows");
            }
        }
    }
}
~~~

**Notes when comparing with cqlsh:**

- `datacenter1` is an **example**; find the actual datacenter name via `SELECT data_center FROM system.local;` and set `CASSANDRA_DC` accurately.
- The Java Driver may pick a different coordinator than cqlsh and may discover native peers beyond the contact point; logs/metrics should record relevant endpoints when investigating topology issues.
- `setConsistencyLevel(ONE)`, `setPageSize(100)`, and `setTimeout(5 seconds)` are set on the **Java statement**. They **do not inherit** settings from any separate cqlsh session.
- This sample code does not configure auth/TLS; when the server requires them, add an auth provider and a CA-trusting SSL context rather than disabling security to run a demo.
- `Instant.now()` records the **actual execution time**, not a logical output expected to match previous runs identically.
- Checking `count == 2` verifies only one condition; in practice, validate **values, ordering, metadata, and errors** according to your goal.
- This snippet is not a benchmark. With multiple pages, ensure **all expected pages** are consumed; for performance testing, execute multiple runs and collect percentiles.

In a production service, use logging and correlation IDs according to policy, keep cardinality bounded, and avoid logging full bind values, user data, credentials, or stack traces containing sensitive details. `CqlSession` should be reused across the service lifecycle rather than created per request.

## 12. Checklist Before Publishing or Handing Off an Experiment

| Check | Passing Criteria |
| --- | --- |
| **Lab scope** | Verified target cluster/keyspace, non-production data, `TRUNCATE` explicitly permitted. |
| **Objective** | Clear hypothesis or concrete, measurable expected output. |
| **Environment** | Includes Cassandra/cqlsh/native protocol versions, endpoint, DC, RF, and UTC timestamps. |
| **Schema** | Includes DDL/scripts and `DESCRIBE` matching the schema before running. |
| **Data** | Includes fixtures or safe reset steps; does not rely on random UUIDs or leftover rows. |
| **Session** | Records CL, serial CL, paging, tracing, timezone, timeout, and TLS/auth mode (secrets redacted). |
| **Commands** | Ordered scripts with file hashes, not just screenshots. |
| **Output** | Includes stdout+stderr, exit status, results, row counts, and errors if any. |
| **Comparison** | Includes expected vs. actual and classifies metrics permitted to vary. |
| **Security** | No passwords, private keys, tokens, or sensitive data exposed in repos/artifacts. |
| **Operations** | No unapproved destructive/repair/compact commands or fault injection on production. |

### 12.1. Five Common Mistakes That Make Experiments Unreproducible

1. **Capturing only `SELECT` output** without saving DDL, source fixtures, or consistency levels.
2. **Using `CAPTURE` as the sole log**, while errors and many special commands are not captured.
3. **Not separating outputs across runs**, causing appended files to look like more rows than actually exist.
4. **Overlooking stateful operations**: LWT `IF NOT EXISTS`, counters, TTLs, stale data, and caches make the second run differ from the first.
5. **Failing to protect secrets**: committing a `cqlshrc` with passwords or command histories containing role-creation passwords into repositories.

## 13. Self-Practice Exercises

1. State the objective "read exactly 2 rows for `sensor-01` on `2026-11-21` ordered by `event_time DESC`," then list at least six components that must be saved for someone else to reproduce it.
2. Create the two files `input/00-schema-and-seed.cql` and `input/10-checks.cql` from this lesson and run them with `cqlsh -f` in a **lab cluster**. Verify the cluster before running a script containing `TRUNCATE`.
3. Use `SHOW VERSION`, `SHOW HOST`, `system.local`, and `system_schema.keyspaces` to populate a manifest with real values.
4. Re-run inside a new run directory, verify both rows by primary key, check values/ordering, and verify input hashes against the earlier run.
5. Use `CAPTURE` on a `SELECT` and then trigger an intentional syntax error in the lab. Explain why the capture file may not contain the error.
6. Use `HISTORY 20` to inspect typed commands, then explain why raw history should not be archived or used as a substitute for CQL scripts.
7. Replace `PAGING OFF` with `PAGING 2` on a partition with more than two rows. Verify all pages are read before comparing total row counts.
8. Enable `TRACING ON` for a small query and then disable it. List which trace ID/latency details differ between two runs and why.
9. In a multi-node lab cluster, test `LOCAL_QUORUM` with an appropriate RF and save a `nodetool status` snapshot. Explain why CL cannot be deduced from a bare `SELECT` screenshot.
10. Use the Java Driver with a `ONE` statement, fixed page size/timeout, and log the row count. Distinguish Java's configuration from cqlsh commands in another terminal.
11. Suppose Run 1 reports two rows and Run 2 reports three. Outline a step-by-step check covering fixtures, script hashes, schema, reset, keys, and connection endpoints.
12. Design a manifest version free of sensitive data that still contains enough information for an authorized engineer to re-run on staging.

**Completion criteria:** maintain a clean set of input scripts, explicitly recorded session settings, separated logs/manifests/checksums, verified expected/actual outputs with no exposed secrets; and clearly understand that **reproducing logical data** differs from expecting **identical timings/traces** in a distributed system.

## References

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `SOURCE`, `CAPTURE`, `HISTORY`, `SHOW VERSION`, `SHOW HOST`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, `-f`/`-e`, and `cqlshrc`.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): DDL, partition keys, clustering order, `SELECT`, `INSERT`, and data types.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): coordinators, replicas, replication, and cluster topology.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `describecluster`, and node observation.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): statement-level consistency, paging, timeouts, sessions, and metadata.
