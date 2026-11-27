# Neo4j Admin Import and Conditions for High-Volume Bulk Loading

## 1. When should you use Neo4j Admin Import?

In a system using a **property graph**, data consists not only of nodes such as `Customer`, `Company`, and `Product`, but also of large numbers of relationships such as `PURCHASED`, `MEMBER_OF`, and `SUPPLIES`. With millions to billions of nodes or relationships, sending individual `CREATE` statements over Cypher can be slow due to transaction overhead, endpoint lookups, index updates, and client/server protocol round trips.

`neo4j-admin database import` is a command-line tool for **bulk-loading large volumes of data directly into Neo4j's storage format**. It reads normalized inputs, builds nodes, and wires relationships using identifiers from the source data. Instead of opening millions of Cypher transactions, the importer optimizes building a database from the input dataset.

Choose `neo4j-admin database import full` primarily when:

- You need an **initial bulk load** into a database that does not yet exist or holds no data that must be retained.
- The volume of entities and links is large enough that import throughput is a major factor.
- You have **administrative privileges to run tools on the Neo4j server** and an appropriate operational window.
- Input data can be cleaned, node keys defined, and cross-table references validated before execution.
- You want to build a large graph from another system such as a relational database, data warehouse, or CSV/Parquet files.

**Do not use full import to append a few records to a live application database.** Full mode is designed for initial loading; if forced to overwrite an existing database, target data can be completely replaced. For continuously changing data, prefer batched `LOAD CSV`, the Java Driver, Spring Data Neo4j, or a supported incremental import workflow.

## 2. Comparing data import methods

| Method | Mechanism | When suitable | Notable conditions |
| --- | --- | --- | --- |
| `neo4j-admin database import full` | Builds Neo4j store files from source data | Initial load of millions/billions of entities | Server access; target database does not exist yet or is handled offline |
| `neo4j-admin database import incremental` | Adds or updates large datasets via a dedicated workflow | Existing database needing large-scale supplemental imports | **Enterprise Edition**, appropriate constraints, maintenance phases; version/format limits apply |
| `LOAD CSV ... CALL { ... } IN TRANSACTIONS` | Cypher reads CSV and commits in batches | Medium/large data; requires `MERGE`, transforms, or updating an existing graph | Execute in an **implicit transaction**; must design retries for partial commits |
| Java Driver / Spring Data Neo4j | Application sends Cypher over Bolt and manages transactions | Continuous business writes, APIs, events, and rule-heavy batches | Optimize call count, transaction size, and indexes |
| UI import tools / managed services | Map files and data via UI/connectors | Interactive imports, or services without `neo4j-admin` access | Capabilities and limits depend on the service |

**Admin import is not a Cypher statement.** You cannot run `neo4j-admin database import full` inside `session.run(...)`, `@Query`, or Neo4j Browser. It runs from a terminal in an environment where Neo4j is installed; the Java Driver or Spring Data Neo4j is used **after the database is online** to query and verify the graph.

## 3. Full import mechanics and mandatory preconditions

### 3.1. Writing directly to the store

Conceptual flow:

```text
Data sources
    |
    +-- users.csv        --> :User nodes
    +-- companies.csv    --> :Company nodes
    +-- memberships.csv  --> :MEMBER_OF relationships
    |
    v
Normalize headers, data types, ID spaces, and integrity
    |
    v
neo4j-admin database import full
    |
    +-- Create nodes + map source IDs
    +-- Link relationships by START_ID/END_ID
    +-- Write data to Neo4j native store
    |
    v
Database can be registered/started
    |
    v
Verify counts, relationships, schema, and Cypher queries
```

A clean dataset and a clear ID model matter far more than blindly cranking up import thread counts.

### 3.2. Requirements on the target database

- **A database that does not yet exist** is the simplest case for learning and running full import. After the importer writes store files, you must create/register the database with the appropriate admin command; the import tool **does not automatically register the database in the system catalog**.
- If the database already exists, the tool only allows replacement when `--overwrite-destination` is enabled. That option **deletes existing target database files before importing**. Use it only under an approved replacement plan with backups and an offline window.
- If the target already exists, you must **stop that database** before full import. Running the tool while the DBMS serves other databases may be possible depending on deployment, but the target database must never be written to and have its store replaced simultaneously.
- The importer needs read permissions on sources and write permissions on the corresponding data/log directories. It runs in the server environment and does not automatically see files on a personal machine running Neo4j Browser.
- Neo4j AuraDB and managed services generally **do not grant terminal/`neo4j-admin` access** to users; choose an import mechanism supported by the service.

This lesson uses a **non-existent `supplygraph` database** to avoid affecting existing data. Shell commands are illustrative examples for a test environment with admin privileges; do not run them directly on production without verifying paths, edition, target database, and backups.

### 3.3. Full and incremental modes are not interchangeable

`neo4j-admin database import incremental` is a separate mode, **available only in Enterprise Edition**. It requires an **existing** target database, identifying keys with appropriate uniqueness constraints, and `--force` per product documentation. It can run as a single command while the database is stopped, or be split into `prepare` → `build` → `merge` stages.

With staged incremental import, `prepare` and `merge` require the database to be stopped; `build` can run while the database is in read-only mode. Depending on version and record format, incremental mode also has restrictions on updating/deleting nodes, labels, relationships, and properties; do not assume it behaves like online Cypher `MERGE`. Update/delete features via `:ACTION` introduced in Neo4j 2025.01 support only **block format**.

**Take a full backup before incremental import.** Failure or cancellation during the merge phase can leave the database inconsistent. This lesson focuses on **full import**, while incremental import requires dedicated operational procedures and reading the documentation for your exact version.

## 4. Preparing CSVs for nodes and relationships

### 4.1. Sample graph

Suppose a B2B platform manages employees and companies:

```text
(:User {userId, name})-[:MEMBER_OF {since}]->(:Company {companyId, name})
```

We have three users and two companies. The `MEMBER_OF` relationship carries a `since` start-date property.

A major difference between admin import and `LOAD CSV`: the importer **does not use `MATCH` to look up relationship endpoints**. Instead, node files declare keys with `:ID`, and relationship files declare `:START_ID` and `:END_ID`.

### 4.2. `users.csv`: User nodes

```csv
userId:ID(UserIds),name,:LABEL
u001,An,User
u002,Binh,User
u003,Chi,User
```

Header definitions:

- `userId:ID(UserIds)`: the node's ID column, belonging to **ID space `UserIds`**; because it is named `userId`, this value is also stored as the node's `userId` property.
- `name`: string property `name`.
- `:LABEL`: node label, here `User`. If a node has multiple labels, use the appropriate array delimiter, `;` by default.

### 4.3. `companies.csv`: Company nodes

```csv
companyId:ID(CompanyIds),name,:LABEL
c001,Acme,Company
c002,Northwind,Company
```

Using **separate ID spaces** distinguishes `UserIds` from `CompanyIds`, especially if both sources use auto-incrementing numeric keys `1`, `2`, `3`. Do not confuse an ID space with a label or a property name: they serve three distinct purposes.

### 4.4. `memberships.csv`: relationships

```csv
:START_ID(UserIds),:END_ID(CompanyIds),:TYPE,since:date
u001,c001,MEMBER_OF,2024-01-15
u002,c001,MEMBER_OF,2024-03-01
u003,c002,MEMBER_OF,2025-06-10
```

Meaning:

| Header | Role | Example |
| --- | --- | --- |
| `:START_ID(UserIds)` | Identifies start node, looked up in ID space `UserIds` | `u001` |
| `:END_ID(CompanyIds)` | Identifies end node, looked up in ID space `CompanyIds` | `c001` |
| `:TYPE` | Relationship type | `MEMBER_OF` |
| `since:date` | `since` property of type date | `2024-01-15` |

The identifier inside `:START_ID(UserIds)` must match the node file's ID space exactly. If `u001` was not declared in the User file, the corresponding relationship cannot be wired properly.

### 4.5. Common column types and formats

| Header syntax | Data type | Example |
| --- | --- | --- |
| `name:string` or `name` | String | `An` |
| `age:int` | Integer | `25` |
| `price:float` | Floating-point | `149.5` |
| `active:boolean` | Boolean | `true` |
| `createdAt:datetime` | Datetime | `2026-01-15T09:30:00+07:00` |
| `tags:string[]` | String array | `neo4j;cypher;graph` |
| `location:point` | Spatial point | Requires valid point syntax and supported CRS |

In importer CSV files, **the ID column used to wire relationships is not Neo4j's internal `elementId()`**. It is a source key you define for the importer to look up when constructing relationships. If you want to query that key later, put a property name before `:ID`; if the header is bare `:ID`, the ID still serves the import but is not necessarily stored as a node property.

**Pre-import data normalization:**

1. Every node ID must be **unique within its ID space**.
2. Every `:START_ID` and `:END_ID` in relationships must resolve to a declared node.
3. Column types in headers must match actual values; for example, `price:float` cannot ingest the string `'one hundred'` as a number.
4. Files must use proper encoding (typically UTF-8), delimiters, quote escaping, and array delimiters. Values containing commas must be enclosed in quotes.
5. Never accidentally leave **two header rows** inside the same file group. The importer reads the header at the start of the group; a second header row can be interpreted as a data record.

## 5. Trying `neo4j-admin database import full`

### 5.1. Environment assumptions

The steps below illustrate **Neo4j installed on Linux/macOS from a distribution with a `bin/` directory**, with the terminal in `NEO4J_HOME`, database `supplygraph` not yet existing, and the three input files placed at:

```text
<NEO4J_HOME>/
├── bin/
│   ├── neo4j-admin
│   └── cypher-shell
└── import/
    ├── users.csv
    ├── companies.csv
    └── memberships.csv
```

On Windows, Docker, Kubernetes, or Neo4j Desktop, binary paths, file mounts, and service management differ; adapt accordingly. All data paths here are read by Neo4j's **server-side process**, not `file:///` URIs of a `LOAD CSV` statement.

### 5.2. Checking syntax on your installed version

```bash
bin/neo4j-admin database import full --help
```

Check `--help` before using new flags. For example, `--dry-run` was added in **Neo4j 2026.02**; do not assume older Neo4j 5.x versions accept this flag.

### 5.3. Dry run when supported by your version

```bash
bin/neo4j-admin database import full \
  --dry-run=true \
  --id-type=string \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

`--dry-run=true` validates arguments and input sources while estimating import scale **without writing the graph**. It does not guarantee every business rule is valid or every relationship resolves: you still need to check keys, types, and test-import in an isolated environment.

### 5.4. Running full import into a new database

```bash
bin/neo4j-admin database import full \
  --id-type=string \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

Parameters:

- `--id-type=string`: IDs ingested as strings (e.g., `u001`). This is the common default; specifying it explicitly avoids ambiguity when reading examples.
- `--nodes`: declares one node file group per flag; a group can contain a separate header file and multiple data files.
- `--relationships`: declares one or more relationship file groups, looking up IDs defined in the node files.
- `supplygraph`: target database name; placed **at the end of the command** per current syntax.

A successful import creates **the store files** for `supplygraph`. If the database did not already exist in the system catalog, run the database creation step below; do not assume Bolt clients can connect immediately just because the import exited with code 0.

### 5.5. Registering the database and verifying

When the DBMS is ready, connect to `system` with an appropriate admin tool (e.g., `cypher-shell -d system -u neo4j`, entering your password as prompted), then run:

```cypher
CREATE DATABASE supplygraph IF NOT EXISTS;
```

If your distribution/edition or database management setup restricts database creation, follow your environment's database initialization workflow. Once the database is `ONLINE`, connect directly to `supplygraph` and verify:

```cypher
MATCH (u:User)
RETURN count(u) AS users;
```

```cypher
MATCH (c:Company)
RETURN count(c) AS companies;
```

```cypher
MATCH (u:User)-[r:MEMBER_OF]->(c:Company)
RETURN u.userId AS userId,
       c.companyId AS companyId,
       r.since AS memberSince
ORDER BY userId;
```

With **only the sample data** and no other records, expect **3 Users, 2 Companies, and 3 `MEMBER_OF` relationships**. Verify relationship direction and `since` values rather than looking only at total node counts.

## 6. Creating constraints and indexes after full import

Across many versions/formats, the standard workflow is **import data first, create schema second**. On `supplygraph`, for example:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;
```

```cypher
CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.companyId IS UNIQUE;
```

```cypher
CREATE RANGE INDEX idx_member_since IF NOT EXISTS
FOR ()-[r:MEMBER_OF]-() ON (r.since);
```

Verify:

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
```

`CREATE CONSTRAINT ... IS UNIQUE` verifies keys are unique and creates the backing index. If imported data actually contains duplicate keys, constraint creation fails: that is a signal to fix the data, **not a reason to skip constraints**.

**Version exception:** starting in **Neo4j 2025.02**, **Enterprise Edition using block format** can create indexes/constraints during import via `--schema`. Do not extrapolate that capability to Community Edition, other formats, or older versions; for the examples above, creating schema after import is straightforward to verify.

## 7. Performance tuning for large data imports

### 7.1. Determining resources

| Factor | Impact | How to handle |
| --- | --- | --- |
| Disk speed and I/O | Reading CSV/Parquet, writing store, creating and linking relationships | Use sufficient-bandwidth storage; monitor throughput and I/O wait |
| Free disk space | Target store and temporary files can be large | Reserve headroom for output, temp data, and logs |
| RAM/off-heap | Building ID lookup structures, managing import memory | Tune `--max-off-heap-memory` from real RAM; leave memory for the OS |
| Admin process JVM heap | Parsing, management structures, and on-heap processing | Configure heap separately for the admin command per version docs |
| Worker count `--threads` | Concurrency across import stages | Scale to actual CPU/I/O; too many threads can saturate disk or RAM |
| Data cleanliness | Duplicate IDs, missing endpoints, bad types cause failures or error logs | Clean before import, set acceptable error thresholds |
| Input ID structure | Lookup and relationship wiring | Use proper ID spaces, avoid collisions and unnecessary casting |

`--max-off-heap-memory` controls the importer's **off-heap** working memory budget. Do not confuse this flag with `server.memory.pagecache.size`: the DBMS page cache setting **does not directly dictate the import memory budget**.

Syntax example—adjust to available RAM:

```bash
bin/neo4j-admin database import full \
  --max-off-heap-memory=8G \
  --threads=8 \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

**The numbers `8G` and `8` illustrate syntax only, not a universally optimal configuration.** If the target database was already imported in the previous step, do not rerun this command against the same target as a benchmark; use a fresh test database or an intentional replacement procedure.

### 7.2. Splitting source files properly

A `--nodes` or `--relationships` group can consist of one header file and multiple data files. Example:

```bash
bin/neo4j-admin database import full \
  --nodes=import/users-header.csv,import/users-part1.csv,import/users-part2.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

In this case, `users-header.csv` contains **only the header**, while `users-part1.csv` and `users-part2.csv` must share the exact column structure and **contain no repeated header**. Place the header file first in the group. File patterns can be used on supported versions, provided you understand the ordering and `regex`/`glob` pattern; avoid patterns that accidentally include header files among data files.

### 7.3. Formats and newer version features

Current Neo4j documentation supports **CSV** and **Parquet** inputs via `--input-type=csv|parquet`. For large datasets, Parquet is helpful when sources are already columnar, though headers/schema still need proper mapping to the importer format.

Neo4j has multiple **store formats**, among which `block` offers Enterprise-specific capabilities. Do not force `--format=block` unless your deployment/edition supports it; check compatibility with your version and post-import operational goals.

**There is no universal "X million nodes/second" figure across systems.** Throughput depends on property sizes, relationship counts, endpoint distribution, storage hardware, thread count, record format, and source errors. Benchmark on a representative dataset and measure actual elapsed time and resource usage.

## 8. Input cleaning and handling bad records

### 8.1. Common error classes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Duplicate node ID | Two nodes share an ID within the **same ID space** | Deduplicate input or fix key modeling |
| Relationship points to non-existent node | Wrong `:START_ID`, `:END_ID`, ID space, or missing node file | Reconcile source keys before importing |
| Wrong `int`, `float`, `date` type | Header expects a different type than the input value | Normalize data or fix header |
| Header parsed as data | Data file contains a repeated header after the group header | Remove repeated headers, check file ordering |
| Garbled Unicode | Source file uses wrong encoding, quoting, or delimiter | Convert to UTF-8 and verify parser settings |
| Import refuses to run because target exists | Full import does not overwrite existing DBs by default | Pick a new database; overwrite only per replacement plan |
| Out of disk or resources | Store, temp files, logs, or lookup structures exceed free space/RAM | Estimate capacity, inspect disk, RAM, and thread limits |

Options `--skip-duplicate-nodes` and `--skip-bad-relationships` let the importer skip certain bad rows, yet **they do not fix the underlying data inconsistency**. When enabled, output can silently miss business-critical nodes or relationships. Never set `--bad-tolerance` arbitrarily high just to make the import report success.

### 8.2. Strict validation policy during initial load

You can instruct the importer to fail on bad records in environments requiring high correctness:

```bash
bin/neo4j-admin database import full \
  --bad-tolerance=0 \
  --strict=true \
  --report-file=import-errors.log \
  --nodes=import/users.csv \
  --nodes=import/companies.csv \
  --relationships=import/memberships.csv \
  supplygraph
```

- `--bad-tolerance=0`: explicitly sets the threshold of ignorable bad records, **rather than relying on defaults that vary across versions**.
- `--strict=true`: strictly checks relationship references to nodes; may be slower.
- `--report-file`: writes bad-record/error details for analysis; inspect the report file before sign-off.

Not every error is covered by tolerance: data-type parsing failures, malformed CSV files, or resource exhaustion can fail the entire import. If an import fails, **do not serve the target graph to applications** until the data has been fixed and re-verified.

## 9. Verifying completeness and correctness after import

An import reporting exit success is only the **initial technical precondition**. For connected data, verify counts, IDs, and relationship quality:

### 9.1. Count reconciliation

```cypher
MATCH (u:User)
RETURN count(u) AS users;
```

```cypher
MATCH (c:Company)
RETURN count(c) AS companies;
```

```cypher
MATCH ()-[r:MEMBER_OF]->()
RETURN count(r) AS memberships;
```

Compare results against **valid data rows in the source files**, not physical line counts if files contain headers or filtered records. For very large datasets, combine per-label/per-type checks with targeted sample queries, and archive metrics from the importer report.

### 9.2. Checking keys and business logic

```cypher
MATCH (u:User)
WITH u.userId AS id, count(*) AS occurrences
WHERE occurrences > 1
RETURN id, occurrences
ORDER BY occurrences DESC;
```

```cypher
MATCH (u:User)-[:MEMBER_OF]->(c:Company)
RETURN c.companyId AS companyId,
       count(u) AS memberCount
ORDER BY companyId;
```

Understand the model when interpreting results: one `User` may have multiple historical `MEMBER_OF` relationships, so `count(u)` counts **matching relationships**, not always distinct users. To count distinct users, use `count(DISTINCT u)`.

### 9.3. Checking schema and read performance

After creating constraints/indexes:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties;
```

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent;
```

Indexes created after import may initially be `POPULATING`. Before benchmarking or opening heavy traffic, wait for them to become `ONLINE`; run `EXPLAIN`/`PROFILE` on representative queries to verify index usage, `Rows`, and `DB Hits`.

## 10. Integrating into Java/Spring Data Neo4j workflows

### 10.1. Role of the application

A Java/Spring application typically handles three distinct responsibilities:

1. **Preparing source data** from business systems: exporting CSV/Parquet, normalizing IDs, and filtering bad records.
2. **Operational orchestration** at the job/CI/CD or admin tooling layer: running `neo4j-admin` in an environment with store-file access, monitoring logs and exit codes.
3. **Verifying and querying the graph** after the database is `ONLINE`: using the Java Driver or Spring Data Neo4j for queries, schema migrations, or business logic.

Never embed `neo4j-admin database import full` inside a `@Query` repository method; it is a shell command that can replace an entire database. Instead, isolate bulk loading as an **orchestrated deployment workflow** with backups, stop/start gates, and reconciliation.

### 10.2. Java Driver example to verify imported data

Assuming `Driver driver` has been initialized with Neo4j connection settings:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

try (Session session = driver.session(
        SessionConfig.forDatabase("supplygraph"))) {

    var records = session.executeRead(tx ->
        tx.run(
            """
            MATCH (u:User)-[:MEMBER_OF]->(c:Company)
            WHERE c.companyId = $companyId
            RETURN u.userId AS userId, u.name AS name
            ORDER BY userId
            """,
            Values.parameters("companyId", "c001")
        ).list()
    );

    records.forEach(record -> System.out.println(
        record.get("userId").asString() + ": " +
        record.get("name").asString()
    ));
}
```

`executeRead` fits because this is a post-import read-only query. This example assumes the database has already been created/started and is accessible. If executed right after file import completes while the database is not yet `ONLINE`, the driver cannot query it yet.

### 10.3. Spring Data Neo4j

In Spring Data Neo4j, `User`, `Company`, and `MEMBER_OF` can be mapped to appropriate entity/relationship classes. However:

- Neo4j Admin Import **does not invoke lifecycle callbacks** or application repository/entity validation logic; data must be normalized beforehand.
- If entity mapping expects an `id` property while the CSV imported `userId`, the application may not map entities as expected. Align field names across CSV headers, constraints, and `@Property`/`@Id` in Java.
- Spring Data Neo4j does not automatically establish every constraint/index just because Java entities exist; manage schema explicitly in migrations.
- After import, verify traversal queries, paging, aggregations, and `date`/other property mappings to ensure the application works cleanly against the loaded graph.

## 11. Limitations to understand before choosing Admin Import

### 11.1. Not an online record-by-record write tool

`full import` operates on store files; it does not serve real-time API updates and does not provide `MERGE` semantics against a running graph. If users continuously create orders or relationships, build a separate write path using Cypher/driver transactions.

### 11.2. Changes from admin import do not flow through normal CDC

Neo4j Change Data Capture (CDC) **does not capture changes produced by `neo4j-admin database import`** as a stream of online write transactions. If downstream systems need change events, design a snapshot/reconciliation publication mechanism or appropriate post-import reload; do not expect CDC subscribers to receive every node/relationship created during offline bulk loading.

### 11.3. Relationships and source ordering matter

The importer needs IDs to know which nodes a relationship connects. Missing `:START_ID`, `:END_ID`, or mismatched ID spaces break graph wiring. Never infer relationships merely because two nodes share the same `name`; identity and relationship semantics must be designed upfront.

### 11.4. Scale is more than row count

A graph with 10 million nodes and a few small properties can be dramatically cheaper than 10 million nodes with large text payloads and hundreds of millions of relationships. When capacity planning, account for:

- Node counts per label and relationship counts per type.
- Number and size of properties per entity.
- Relationship *degree* distribution, especially supernodes connected to millions of endpoints.
- Cost of building indexes/constraints after loading, downtime windows, and verification steps.

## 12. Recommended operational workflow

| Stage | Work to complete | Exit criterion |
| --- | --- | --- |
| Design | Define nodes, labels, relationships, directions, ID spaces, property types | Source and target schemas clearly specified |
| Preparation | Export data, clean duplicates/missing endpoints, normalize encoding | Consistent CSV/Parquet with reconciliation counts |
| Assessment | Choose full/incremental/Cypher by volume and offline window | Tool matches edition and update requirements |
| Safety | Use a new database, backup if replacing an old DB, verify directory permissions | Recovery plan and exact paths verified |
| Testing | Dry run (if available), test import on small/representative sample | Report has zero unacceptable errors |
| Import | Run `neo4j-admin database import full`, monitor logs/resources | Command finishes, store files ready |
| Registration | Create/start database per environment | Database `ONLINE` and reachable |
| Finalization | Create required schema or verify imported schema | Indexes/constraints valid, indexes `ONLINE` |
| Acceptance | Compare node/relationship totals, sample queries, Java performance | Data and business query results verified |

## 13. Common misconceptions

**"Admin Import is like `LOAD CSV`, just faster."** Both read external data, but they differ in operational boundaries: `LOAD CSV` executes via Cypher on a running database, whereas full import writes directly to the store and targets initial loading.

**"Full import can append to a running database."** Full import is not an incremental update; replacing an existing database requires stopping it and passing `--overwrite-destination`, which can delete existing data.

**"A CSV with a `userId` column is enough to wire relationships."** Admin Import requires `:ID` and relationship `:START_ID`/`:END_ID` columns; across distinct sources, consistent ID spaces are required.

**"Just skip bad records to import quickly."** Dropping duplicate nodes or relationships with missing endpoints can corrupt the graph. Missing relationships are often more dangerous than node-count discrepancies; reconcile and inspect reports.

**"Import succeeded means the app can serve traffic immediately."** You still need to register/start the database, create/verify constraints and indexes, reconcile data, and run business validation queries.

**"`--max-off-heap-memory` is the DBMS page cache size."** The importer manages its own memory budget; check admin process configuration and actual available hardware resources.

**"You can run `neo4j-admin` from any Java client."** The CLI requires filesystem access and a Neo4j installation environment; the Java Driver connects only over the query protocol.

## 14. Practice exercises

1. Using `users.csv`, `companies.csv`, and `memberships.csv` above, explain why `:START_ID(UserIds)` must not be changed to `:START_ID(CompanyIds)`.
2. If both `User` and `Company` have ID `1`, design CSV headers to avoid collisions and write three sample node/relationship data rows.
3. A `memberships.csv` file references `u999`, which does not exist. Name two ways to handle this and the consequence of enabling `--skip-bad-relationships`.
4. Design a workflow to import 50 million nodes and 150 million relationships into a **non-existent** database. List the measurements and checks required before accepting the database.
5. Explain why `@Transactional` in Spring Data Neo4j cannot wrap `neo4j-admin database import full` as a business transaction.
6. Compare downtime requirements for full import, staged incremental import, and `LOAD CSV ... IN TRANSACTIONS` when the system must ingest orders continuously.
7. Why can't a CDC subscriber automatically receive node/relationship creation events from a full import?

## 15. Key takeaways

- **`neo4j-admin database import full`** fits initial loading of very large graphs, requiring admin access and operating directly on storage files.
- Preparing **CSV headers, `:ID`, ID spaces, `:START_ID`, `:END_ID`, `:TYPE`**, and accurate property types is essential for building a valid property graph.
- **A non-existent database** is the safest scenario for learning and testing full import; afterward, register/start the DB, create indexes/constraints, and reconcile the graph.
- **Never use `--overwrite-destination` casually**: it replaces database files and can wipe existing data.
- **Incremental import is a dedicated Enterprise Edition workflow** with specific schema, backup, and database-state requirements.
- For frequent updates on a live graph, use **batched Cypher `LOAD CSV`, the Java Driver, or Spring Data Neo4j** as appropriate for business rules.
- Judge import quality by **relationship accuracy, counts, keys, schema, and business queries**, not exit codes or raw speed alone.

### Official references

- [Neo4j Operations Manual — Import](https://neo4j.com/docs/operations-manual/current/import/)
- [Neo4j Operations Manual — Full import](https://neo4j.com/docs/operations-manual/current/import/full-import/)
- [Neo4j Operations Manual — Full data import tutorial](https://neo4j.com/docs/operations-manual/current/tutorial/neo4j-admin-import/)
- [Neo4j Operations Manual — CSV header format](https://neo4j.com/docs/operations-manual/current/import/header-format/)
- [Neo4j Operations Manual — Incremental import](https://neo4j.com/docs/operations-manual/current/import/incremental-import/)
- [Neo4j Data Ingestion Guide — Offline bulk loading](https://neo4j.com/docs/data-ingestion-guide/ingestion-methods/admin-import/)
