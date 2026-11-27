# Major Versions, Minor Versions, and Reading Version-Accurate PostgreSQL Documentation

When learning or operating PostgreSQL, an SQL statement can run on one machine yet fail on another even though both run PostgreSQL. Often the cause is not a syntax typo, but a **version difference**: a new feature exists only from a specific major version onward, the open documentation describes a different version, or one environment has applied bug fixes that the other lacks.

PostgreSQL follows a clear numbering convention for **major versions** and **minor versions**. Understanding this convention answers practical questions:

- Which PostgreSQL version is the server running? Does it match the local `psql` tool's version?
- When reading an example using `MERGE`, is it guaranteed to work on your server?
- How does updating from `16.4` to `16.5` differ from upgrading from `16.4` to `17.0`?
- Does a documentation page labeled `current` on the website apply to your production server?
- When troubleshooting a post-upgrade issue, which release notes, extensions, and upgrade guides should you consult?

In this lesson, version numbers such as `9.6.24`, `15.8`, `16.4`, `17.2`, `17.5`, and `18.1` are used **to illustrate numbering rules**, not to declare which release is newest at the time of reading. Always verify live release and support status on the official PostgreSQL project website.

## 1. Why Does the PostgreSQL Version Matter?

A database management system evolves over time. Across versions, PostgreSQL adds or changes:

1. **SQL language and features:** syntax, data types, functions, privileges, indexing mechanisms, partitioning, JSON, and query features.
2. **Optimizer and execution behavior:** plan choices, statistics, parallelism, and expression evaluation.
3. **Administration and operations:** backups, recovery, monitoring, replication, upgrades, and configuration parameters.
4. **Bug fixes and security:** patches can alter input validation, privilege checks, correctness, or stability.
5. **Ecosystem compatibility:** extensions, JDBC drivers, client libraries, migration tools, and operating system platforms.

For example, `MERGE` was introduced in PostgreSQL **major version 15**. A tutorial using `MERGE` written for PostgreSQL 15+ cannot be applied verbatim on PostgreSQL 14. Conversely, a simple `SELECT` usually works across many versions, yet that does not mean every SQL statement and feature is compatible.

Therefore, before copying commands from documentation, identify **the server version actually executing those commands**.

## 2. Distinguishing Major Versions and Minor Versions

PostgreSQL changed its versioning scheme starting with **PostgreSQL 10**. This is a critical distinction when reading older docs and history.

### 2.1. From PostgreSQL 10 Onward

Versions take the form:

```text
MAJOR.MINOR

17.5
│  └── minor version = 5
└───── major version = 17
```

Examples:

| Version | Major | Minor | Interpretation |
| --- | ---: | ---: | --- |
| `15.8` | 15 | 8 | A bug-fix release in major branch 15. |
| `16.4` | 16 | 4 | Major version 16, minor version 4. |
| `16.5` | 16 | 5 | Same major branch 16, newer minor than `16.4`. |
| `17.2` | 17 | 2 | Major version 17, minor version 2. |
| `18.1` | 18 | 1 | Major version 18, minor version 1. |

Under this numbering, **moving `16.4 → 16.5` is a minor update**, whereas **`16.4 → 17.0` is a major upgrade**.

A new release within the same major branch focuses on bug fixes and security patches, whereas a new major version can introduce new features, behavior changes, or storage format changes requiring an explicit upgrade procedure.

### 2.2. Before PostgreSQL 10

Older versions used a **three-part `MAJOR_MAJOR.MINOR` format**, where **the first two numbers together form the major version**:

```text
9.6.24
│ │  └── minor version = 24
└─┴───── major version = 9.6
```

Examples:

| Version | True Major | True Minor |
| --- | --- | ---: |
| `9.4.26` | 9.4 | 26 |
| `9.5.25` | 9.5 | 25 |
| `9.6.24` | 9.6 | 24 |
| `10.0` | 10 | 0 |
| `10.23` | 10 | 23 |

For PostgreSQL 9.6, never say `9` is major and `6` is minor. Under the legacy scheme, **`9.5 → 9.6` is a major upgrade**, while **`9.6.23 → 9.6.24` is a minor update**.

From PostgreSQL 10 onward, the first number alone is the major version. There is no single rule that "everything after the first dot is always the minor version" across all of PostgreSQL history.

### 2.3. Do Not Treat Versions as Decimal Numbers

Version strings are not floating-point numbers to compare like `16.10` vs. `16.9` using decimal math. By component ordering:

```text
16.9  < 16.10
```

because minor `10` is newer than minor `9`. Version-checking code should parse version components or use PostgreSQL's numeric version setting rather than casting `'16.10'` to float `16.1`.

## 3. Major Releases and Minor Releases Serve Different Goals

### 3.1. Major Releases: Features and Changes That Can Affect Applications

A new major version can include:

- New SQL features or database objects.
- New query and optimizer capabilities.
- Changes to default settings, administration, replication, or logging.
- Behavioral changes requiring backward-compatibility review.
- Internal storage format changes requiring a database cluster upgrade procedure.

Thus, when planning `16 → 17`, operations must ask more than "will the server start?"—you must check:

1. PostgreSQL 17 release notes and **migration** highlights.
2. Whether existing SQL and ORM queries still behave properly.
3. Whether extensions are compatible with PostgreSQL 17.
4. The data migration procedure to the new major version.
5. Rollback plans, backups, and restore drills.

### 3.2. Minor Releases: Patches Within the Same Major Branch

A minor release typically focuses on:

- Fixing bugs affecting query correctness or stability.
- Patching security vulnerabilities.
- Resolving discovered incorrect behaviors.
- Necessary maintenance fixes for an active major branch.

For example, `16.4 → 16.5` is a **minor update**. In principle, PostgreSQL preserves compatibility within a major branch so minor updates do not require converting on-disk formats via `pg_upgrade` or full dump/restore.

That **does not mean minor updates never have side effects**. A bug fix can change results for a previously mishandled edge case, a security patch can tighten permission checks, and release notes occasionally call out follow-up actions. Always read the release notes for the exact minor version you plan to install.

### 3.3. Comparison Table

| Criterion | Minor Update | Major Upgrade |
| --- | --- | --- |
| Example | `16.4 → 16.5` | `16.4 → 17.0` |
| Primary purpose | Bug fixes, security patches | New features, major changes, and bug fixes |
| Major branch | Unchanged | Changes |
| Storage format | Normally compatible within same major | May change |
| Needs `pg_upgrade`? | Normally no | Needs a major upgrade method such as `pg_upgrade`, dump/restore, or logical replication |
| Read release notes? | Yes, especially bug fixes and patch instructions | Yes, including breaking changes and migration sections |
| Testing scope | Regression and operational verification | Broad compatibility, performance, extension, and migration testing |
| Server restart required? | Usually yes when replacing PostgreSQL binaries per packaging workflow | Yes, as part of switching to the new major version |

Both major and minor releases can be security-critical. Never skip minor updates simply because they "don't add features."

## 4. Checking the Running Server Version via SQL

This is the first step before picking documentation.

### 4.1. `SHOW server_version`

Connect to the target PostgreSQL server and run:

```sql
SHOW server_version;
```

An illustrative result might be:

```text
 server_version
----------------
 16.4
```

In some distributions or packages, the string may include packaging or vendor suffixes. The value needed to pick documentation is the **PostgreSQL major version**—`16` in this example.

### 4.2. `SELECT version()`

```sql
SELECT version();
```

This function returns a longer string containing the PostgreSQL version, OS architecture, compiler, and build info. It is helpful for environment diagnostics, though less convenient than `SHOW server_version` when you only want the version number.

Example output format:

```text
PostgreSQL 16.4 on x86_64-..., compiled by ..., 64-bit
```

Exact output depends on the machine and how PostgreSQL was built/packaged.

### 4.3. `server_version_num`: Integer for Comparisons

PostgreSQL also exposes:

```sql
SHOW server_version_num;
```

For `16.4`, the output is:

```text
160004
```

From PostgreSQL 10 onward, this number follows the general formula:

```text
major * 10000 + minor

16.4  -> 16 * 10000 + 4 = 160004
17.5  -> 17 * 10000 + 5 = 170005
```

For legacy releases prior to 10, the integer encodes three parts—for instance, `9.6.24 → 90624`. Therefore, do not apply the PG10+ formula blindly to every historical version.

In SQL, you can query:

```sql
SELECT
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS server_version_num;
```

Example checking whether a feature exists by version:

```sql
SELECT
    current_setting('server_version_num')::integer >= 150000
        AS supports_merge_since_pg15;
```

This returns `true` on PostgreSQL 15+ and `false` on majors before 15. It checks only the **minimum version requirement**, not privileges, extensions, configuration, or actual application SQL validity.

### 4.4. Confirming You Are Connected to the Right Database and Server

Across local, test, staging, and production environments, the same `SHOW server_version` query can return different answers. Record connection context alongside version:

```sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
```

Over a Unix-domain socket, TCP address and port functions return `NULL`. That does not indicate a server error; verify the endpoint via your client or management tool.

In `psql`, the command:

```text
\conninfo
```

displays which database, user, host, or socket the client is currently connected to.

> **Rule:** Confirm the version only after verifying your SQL is running on **the exact instance you intend to study, deploy to, or diagnose**.

## 5. Distinguishing PostgreSQL Server Versions from Client Tool Versions

A developer machine can have several PostgreSQL components installed, each with its own version:

| Component | Inspection Command / Method | Meaning |
| --- | --- | --- |
| PostgreSQL Server | `SHOW server_version;` | Version of the engine executing SQL and storing data. |
| `psql` | `psql --version` in terminal | Version of the CLI client binary on the local machine. |
| `pg_dump` | `pg_dump --version` | Version of the dump utility. |
| `pg_restore` | `pg_restore --version` | Version of the archive restore utility. |
| `postgres` executable | `postgres --version` if binary access allowed | Version of the local binary, not necessarily the remote connected server. |
| PostgreSQL JDBC Driver | Dependency version like `org.postgresql:postgresql` | Java driver version, with its own lifecycle separate from PostgreSQL Server. |
| Extension, e.g., PostGIS | `SELECT extname, extversion FROM pg_extension;` | Version of the extension installed in the database, not the server version. |

Example:

```bash
psql --version
pg_dump --version
```

On a developer's laptop, `psql --version` might print `psql (PostgreSQL) 17.2`, while after connecting to the server:

```sql
SHOW server_version;
-- Example: 16.4
```

There is no contradiction: **the client is 17.2 and the server is 16.4**. When looking up SQL syntax supported by the server, prioritize **PostgreSQL 16** documentation—do not consult PostgreSQL 17 docs just because your laptop has `psql` 17.

### 5.1. Why Does `pg_dump` Version Matter?

Logical backup utilities face stricter compatibility limits than `psql`:

- `pg_dump` can typically back up servers **older than or equal to** the utility's own version.
- A `pg_dump` from an **older major version than the server** cannot be expected to understand newer server structures/syntax and will normally refuse to run.
- When planning backup/restore workflows, pick a tool version supported for both **source and target versions**, and test an actual restore.

For example, an admin host with `pg_dump` 16 pointing at a PostgreSQL 17 server is a mismatch to catch immediately—never assume dumps work just because `psql` connects fine.

### 5.2. Extensions Have Their Own Versions

```sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
```

Example output:

```text
 extname  | extversion
----------+-----------
 plpgsql  | 1.0
 ...
```

An extension's `extversion` is not the PostgreSQL Server version. During major upgrades, verify that both the extension and its compiled binaries support the new major version. Some extensions also require `ALTER EXTENSION ... UPDATE` per the extension's upgrade instructions; never run it blindly without reading the extension docs.

In Java, the PostgreSQL JDBC driver follows its own release cycle. Certain protocol features or data types may require a sufficiently recent driver, yet the driver version **does not determine** whether the server supports `MERGE` or another SQL feature.

## 6. Reading Version-Matched PostgreSQL Documentation

Official PostgreSQL documentation is organized by **major version**. The project website publishes documentation under URLs structured as:

```text
https://www.postgresql.org/docs/current/
https://www.postgresql.org/docs/17/
https://www.postgresql.org/docs/16/
https://www.postgresql.org/docs/15/
https://www.postgresql.org/docs/9.6/
```

These URLs highlight a key rule:

- `/docs/current/` points to **the major version currently designated as current by the project**. Its target shifts whenever a new major version is released.
- `/docs/16/` points permanently to **major 16**. Even after newer majors release, the numbered major URL stays accurate for servers running 16.
- `/docs/9.6/` illustrates how documentation for **9.6** is addressed under the legacy two-part major scheme.

**If your server runs 16.4, open `https://www.postgresql.org/docs/16/` first.** If it runs 17.5, open `https://www.postgresql.org/docs/17/`. When researching a feature introduced in a newer major, you can read newer docs to learn about it, while keeping clear which parts are unsupported on your current server.

### 6.1. The Major Version in the URL Is Decisive

Consider two `SELECT` reference pages:

```text
https://www.postgresql.org/docs/current/sql-select.html
https://www.postgresql.org/docs/16/sql-select.html
```

The first URL can change to describe a different major version once `current` moves. The second URL stays pinned to the 16 branch.

For internal engineering docs meant to stay accurate long-term, **link to URLs with an explicit major version** rather than `current`, unless intentionally discussing the latest release.

### 6.2. Major-Level Docs Are Not a Snapshot of Each Minor Release

The `/docs/16/` manual is not necessarily a frozen snapshot of `16.4` specifically. A major branch's documentation is updated as minor releases are maintained and published.

Therefore:

- To check **core syntax and features**: use the manual for your running major version.
- To check **which minor fixed a specific bug**: read the corresponding release notes.
- To reconstruct **behavior in an older minor**: compare release notes between that minor and subsequent minors; do not assume the live major manual reflects every historical detail.

This is why you need both documentation types: the **major manual** and **per-release release notes**.

## 7. Finding the Right Section of the Manual

Once you open the right major's manual, look in these sections:

| Need | Manual Section to Check | Examples |
| --- | --- | --- |
| SQL statement syntax | SQL Commands / SQL Language | `SELECT`, `INSERT`, `MERGE`, `CREATE TABLE`. |
| Data types and functions | Data Types, Functions and Operators | `timestamp`, `jsonb`, `date_trunc`. |
| Transactions and locking | Concurrency Control | Isolation levels, MVCC, row locking. |
| Indexes and performance | Indexes, Performance Tips | B-tree, `EXPLAIN`, statistics. |
| Server configuration | Server Configuration | `postgresql.conf`, memory, logging. |
| Client tools | Client Applications | `psql`, `pg_dump`, `pg_restore`. |
| Upgrading | Upgrading a PostgreSQL Cluster, `pg_upgrade` | Major upgrade methods. |
| Release changes | Release Notes | New features, patches, bug fixes, and migration notes. |

Illustrative URLs pinned to major 16:

```text
Major 16 manual:
https://www.postgresql.org/docs/16/

SELECT in major 16:
https://www.postgresql.org/docs/16/sql-select.html

psql application in major 16:
https://www.postgresql.org/docs/16/app-psql.html

pg_upgrade in major 16:
https://www.postgresql.org/docs/16/pgupgrade.html
```

To jump from major 16 docs to major 17 docs for an SQL topic, you can usually switch version in the navigation bar on the website. Still, **never assume every page or option exists across all majors**, since table-of-contents layout and features evolve.

### How to Read a Documentation Page with SQL Examples

Before using an example:

1. Check the major version label in the URL or website version selector.
2. Confirm **which version** introduced the command or clause.
3. Read the **Notes**, **Compatibility**, and feature limitation sections.
4. If behavior differs from the docs, check release notes for your running minor and relevant patches.
5. In Java/ORM projects, also check the SQL generated by your framework and your ORM's configured PostgreSQL dialect version.

Never read only the synopsis syntax line and assume every option works on your server.

## 8. Release Notes: Where Exact Per-Release Changes Live

The manual explains how features work. **Release notes** answer different questions:

- What features did a new major release add or change?
- Which bugs—especially security vulnerabilities—did a minor release fix?
- Are any extra migration steps, reindexing, or config adjustments recommended?
- Has a known bug already been fixed in this release?
- Are there compatibility or operational impacts?

An example release notes URL for a specific release looks like:

```text
https://www.postgresql.org/docs/17/release-17-5.html
```

Here `17` is the **major docs branch**, and `17-5` in the page name denotes **release 17.5**. Treat this URL as an illustration of release-note URL structure, not as a claim that 17.5 is the latest release.

### 8.1. What to Read Before a Minor Update

Suppose you are updating `16.4 → 16.5`:

1. Read the release notes for `16.5`.
2. Scan entries related to security fixes and bugs affecting your workload.
3. Check extra instructions for patches, extensions, or OS packaging.
4. Identify whether any special manual follow-up steps are required.
5. Perform the update per your packaging workflow and verify `SHOW server_version` after restarting.

If moving from `16.2` to `16.5`, do not read only `16.5` and skip intermediate releases. Review **16.3, 16.4, and 16.5** release notes—especially notices applying across that upgrade span.

### 8.2. What to Read Before a Major Upgrade

Suppose you are planning `16.x → 17.x`. Beyond the new-features list, read **Migration to Version 17** (or the equivalent migration section) in the major 17 release notes, along with `pg_upgrade` docs or your chosen migration method.

New features draw attention, yet changed defaults, renamed parameters, incompatible extensions, or planner shifts often have a far larger impact on production cutovers.

## 9. Illustration: Using a Feature Available Only in Certain Majors

### 9.1. `MERGE` in PostgreSQL 15 and Later

`MERGE` clearly shows why **a newer manual does not automatically fit an older server**. This statement arrived in PostgreSQL 15.

Example:

```sql
CREATE TABLE stock_balances (
    sku text PRIMARY KEY,
    available_quantity integer NOT NULL
);

CREATE TABLE stock_changes (
    sku text PRIMARY KEY,
    incoming_quantity integer NOT NULL
);

INSERT INTO stock_balances (sku, available_quantity)
VALUES ('BOOK-SQL', 10);

INSERT INTO stock_changes (sku, incoming_quantity)
VALUES
    ('BOOK-SQL', 3),
    ('BOOK-JAVA', 5);

MERGE INTO stock_balances AS target
USING stock_changes AS source
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET available_quantity =
        target.available_quantity + source.incoming_quantity
WHEN NOT MATCHED THEN
    INSERT (sku, available_quantity)
    VALUES (source.sku, source.incoming_quantity);
```

On PostgreSQL 15+, `MERGE` updates or inserts based on key matching. On a PostgreSQL 14 server, this `MERGE` syntax is not supported.

**How to verify before studying or applying:**

```sql
SHOW server_version;
SHOW server_version_num;
```

If major is below 15, look for a version-compatible alternative such as `INSERT ... ON CONFLICT` for appropriate upsert cases, rather than copying `MERGE` verbatim.

### 9.2. Identical Syntax Can Still Behave Differently

Differences are not limited to brand-new keywords. Major versions can alter how the optimizer handles identical SQL. For instance, starting in PostgreSQL 12, CTE optimization changed significantly regarding eligible CTE *inlining/folding* compared to older versions.

Example:

```sql
WITH recent_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    WHERE created_at >= DATE '2026-01-01'
)
SELECT customer_id, COUNT(*)
FROM recent_orders
GROUP BY customer_id;
```

The SQL runs across many majors, yet execution plans need not match. When reading older tuning articles claiming "CTEs always materialize" or "CTEs are always optimization fences," verify against your major's manual and inspect `EXPLAIN` instead of treating old-version rules as universal.

## 10. Minor Updates: Basic Operational Workflow

Suppose a server runs PostgreSQL `16.4` and operations wants to apply a newer minor in branch 16. A general workflow:

### Before Updating

1. Confirm the running version with `SHOW server_version` and record OS/package details.
2. Read release notes for all intervening minor releases.
3. Verify recent backups and restore readiness.
4. Check extensions, drivers, native libraries, and distribution-specific notes.
5. Schedule the restart or switchover window, especially with primary/standby setups.

### During the Update

1. Use trusted package repositories or approved binary deployment pipelines.
2. Follow instructions for your OS, distribution, and replication topology.
3. Manage downtime or switchover windows per SLA.
4. Never assume a "minor update" swaps files without restarting; most binary updates require restarting the server process so the new binaries take effect.

### After Updating

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Then run application smoke tests and inspect logs, connection health, replication metrics, and key queries.

**What not to do:** run `pg_upgrade` for routine minor patches unless documentation explicitly calls for it. `pg_upgrade` converts between PostgreSQL major versions; minor updates within the same branch follow a different path.

### Systems with Streaming Replication

With primary and standby nodes, updates may be coordinated node by node to minimize disruption. However, never assume every arbitrary minor-version combination supports blind rolling updates. Follow official PostgreSQL, packaging, and HA orchestrator guidance, and verify replication health and failover readiness afterward.

## 11. Major Upgrades: More Than Overwriting Binaries

Upgrading PostgreSQL major versions involves **the database cluster's stored data**, not simply bumping a displayed version string.

For `16 → 17`, choose a PostgreSQL-supported upgrade path:

| Method | Idea | Factors to Evaluate |
| --- | --- | --- |
| `pg_upgrade` | Uses PostgreSQL's major upgrade utility on compatible clusters | Old/new binaries, extensions, disk space, downtime, rollback, post-upgrade checks. |
| Logical dump/restore | Logical export from old version, restore into new version | Dump/restore duration, size, privileges, sequences, extensions, SQL/schema compatibility. |
| Logical replication approach | Sync data from old major to new major, then cut over app | Table structures, sequences, DDL, lag, cutover point, consistency, and specific constraints. |

Never confuse **physical streaming replication** with an arbitrary major upgrade tool. You cannot build a PostgreSQL 17 standby via physical streaming replication from a PostgreSQL 16 primary as a supported upgrade path.

### 11.1. Role of `pg_upgrade`

`pg_upgrade` migrates data between PostgreSQL major versions within supported version compatibility. It does not automatically make third-party extensions compatible or replace functional testing.

Terminal check example:

```bash
pg_upgrade --version
```

This only prints **the `pg_upgrade` tool's version**; it does not perform an upgrade. An actual upgrade requires old/new binaries, old/new data directories, and strict preconditions—never run `pg_upgrade` with guessed paths on production.

When planning a major upgrade, read the **`pg_upgrade` documentation for the target version** and its migration release notes, not just the source version's manual.

### 11.2. What to Verify After a Major Upgrade?

Common checklist items:

- Do data, schemas, row counts, constraints, privileges, and objects match?
- Are compatible extension versions installed and updated as required?
- Have optimizer statistics been refreshed per upgrade instructions?
- Do critical SQL queries show plan regressions, syntax errors, or permission errors?
- Do connection pools, JDBC drivers, and migration tools need config or version updates?
- Have standbys, backups, monitoring, and recovery workflows been rebuilt or verified?

Only after thorough verification can a major upgrade be declared operationally ready. A newly started PostgreSQL server alone does not prove application compatibility.

## 12. Support Lifecycle of PostgreSQL Versions

The PostgreSQL project maintains multiple major branches in parallel. Under its standard release policy, **each major version receives roughly five years of support** from initial release, including minor bug-fix and security releases during that window.

When a branch reaches **end of life (EOL)**:

- The project no longer publishes official bug fixes or security patches for that branch under standard policy.
- Newly disclosed vulnerabilities may never receive an official fix for expired majors.
- Continuing to run it requires explicit risk assessment and a major upgrade plan; never rely on "the server is still running fine."

Check official policy and the live supported-versions table at:

```text
https://www.postgresql.org/support/versioning/
```

**Never hard-memorize "the latest current major" from a static lesson.** Supported versions, EOL dates, and new minor releases continuously advance over time. Always verify against official project pages when maintaining systems.

### 12.1. Should You Always Run the Latest Major?

Not necessarily. Balance:

- Need for new features.
- Remaining support lifetime of your current major.
- Extension, driver, and library compatibility.
- Organizational operational maturity and testing capacity.
- Security exposure if lingering on an unsupported branch.

A brand-new major might offer appealing features before the surrounding ecosystem is ready. Conversely, clinging to an ancient major "for safety" increases security exposure and loses support. A better practice is a **regular major-upgrade cadence** combined with **timely minor updates** on a supported branch.

## 13. Comparing Versions Across Environments

In a Java project, multiple environments often coexist:

```text
Developer laptop    -> PostgreSQL 17.2
CI integration test -> PostgreSQL 16.4
Staging             -> PostgreSQL 16.5
Production          -> PostgreSQL 16.4
```

These numbers illustrate drift. Consequences:

- A developer may write SQL using a feature added in 17 while CI and production run major 16.
- Staging and production share major 16 yet differ in minor version, so a bug patched in staging may still exist in production.
- A migration that "works on my machine" is not guaranteed to run on an older major server.

### 13.1. Choosing Versions for Test Environments

When verifying code bound for production:

1. Run **compatibility tests** on production's exact major version.
2. When production and staging differ on minor versions, understand the gap—especially when validating a bug fix.
3. Add early test runs on a newer major to prepare upgrades, without replacing tests against production's current major.
4. Pin container images, package versions, and running server versions explicitly; mutable tags like `latest` break reproducibility.

### 13.2. Startup Version Check Example

A Java service can read `server_version_num` and refuse to start if a minimum major is required, or log warnings on environment mismatch.

Example SQL check:

```sql
SELECT current_setting('server_version_num')::integer
       >= 150000 AS meets_minimum_pg15;
```

If the application relies on `MERGE`, checking for minimum version 15 catches misconfigured environments early. Still, treat version checks as **one precondition**, not a replacement for verifying schemas, extensions, privileges, and migrations.

A helpful CI practice is testing against the lowest major version your product claims to support alongside running a parallel suite on your next target upgrade major.

## 14. Reading Online Answers Without Getting Tripped Up by Versions

Blog posts, forum answers, and snippets come from different years and major versions. When searching PostgreSQL topics online, check:

1. **Publication and last-updated dates** of the post.
2. **Major version** referenced by the author.
3. Whether syntax and behavior match the official manual for your major.
4. Comments or updates noting features added in a later release.
5. Whether the author used standard PostgreSQL or a PostgreSQL-compatible product with different limits.

For example, an article might state:

> "PostgreSQL does not support MERGE; use INSERT ON CONFLICT."

That statement was accurate when written for majors before 15, yet is no longer true as a general statement for PostgreSQL 15+. Always read by asking **which major version the post describes**.

Similarly, old advice like "CTEs are always materialized" must be read in version context, as PostgreSQL's optimizer evolved across major releases.

## 15. Common Pitfalls

| Misconception | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| `9.6.24` has major 9, minor 6 | Before PG10, major comprises the first two parts | Major is `9.6`; minor is `24`. |
| `17.2` has major 17.2 | From PG10, major is the first number | Major `17`; minor `2`. |
| `16.10` is older than `16.9` because 16.10 equals 16.1 | Versions are not decimal numbers | Compare minor component 10 vs. 9. |
| `psql --version` is the server version | That checks the local client binary | Run `SHOW server_version` on the target connection. |
| `/docs/current/` always matches every server | `current` shifts when new majors release | Open `/docs/{major}/` matching your server. |
| Major 16 supports every feature in major 17 docs | Features may be introduced later | Check "introduced in version" and the major 16 manual. |
| Minor updates are the same as major upgrades | Goals and storage compatibility differ | Distinguish in-branch patches from major conversions. |
| Minor updates don't need release notes | Patches can include critical notes | Read release notes for all intervening minor updates. |
| A newer driver guarantees server SQL features | Drivers and servers have separate lifecycles | Check server version and test SQL on the target server. |
| A running server must still be supported | EOL follows project lifecycle policy | Check the official support/versioning table. |

### Pitfall 1. Picking Documentation by Client Version

Situation:

```bash
psql --version
# psql (PostgreSQL) 17.2
```

Yet the server reports:

```sql
SHOW server_version;
-- 16.4
```

**Conclusion:** for server-supported SQL syntax, read the PostgreSQL 16 manual. For `psql` CLI flags and meta-commands on your laptop, consult `psql` docs matching client 17.

### Pitfall 2. Reading Only Major Release Notes and Skipping Minors

A project running `16.2` wants to update to `16.5`. Reading only "PostgreSQL 16 new features" misses bugs fixed in `16.3`, `16.4`, and `16.5`. To evaluate bug fixes or security patches, read the release notes for all relevant minor versions.

### Pitfall 3. Trusting Translations or Blogs Without Checking Primary Sources

Translations, internal wikis, and blogs are great for learning, yet go stale. Before using SQL in production, verify against official documentation for your exact version. Never copy schema-altering or upgrade commands just because a short snippet worked in someone else's test environment.

## 16. Practice Exercises

### Exercise 1. Classify Major and Minor

Fill in the table yourself:

| Version | Major | Minor |
| --- | --- | --- |
| `9.6.24` | ? | ? |
| `10.23` | ? | ? |
| `16.4` | ? | ? |
| `17.2` | ? | ? |

**Answer:**

| Version | Major | Minor |
| --- | --- | --- |
| `9.6.24` | 9.6 | 24 |
| `10.23` | 10 | 23 |
| `16.4` | 16 | 4 |
| `17.2` | 17 | 2 |

### Exercise 2. Find the Exact Version from Your Current Connection

Run:

```sql
SELECT
    current_database(),
    current_user,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num;
```

**Task:** record the server's major/minor, database name, and login role. Then compare against your terminal output:

```bash
psql --version
```

**Question:** Do the two versions match? If they differ, which version determines whether `MERGE` can run?

**Answer:** the **server** version determines SQL support, because the server parses and executes the statement. The client version only identifies your local tool.

### Exercise 3. Choose the Right Documentation

An application connects to PostgreSQL `16.4`. You have three links:

```text
A. https://www.postgresql.org/docs/current/
B. https://www.postgresql.org/docs/16/
C. https://www.postgresql.org/docs/17/
```

**Question:** Which is the best starting point for reading SQL syntax and server behavior?

**Answer:** **B**, because the server belongs to major 16. Link A is only appropriate when intentionally reading whatever major is `current` at the moment; link C documents major 17, not the default reference for a 16 server.

### Exercise 4. Minor Update or Major Upgrade?

Classify:

1. `16.4 → 16.5`.
2. `16.4 → 17.0`.
3. `9.6.23 → 9.6.24`.
4. `9.5.25 → 9.6.0`.

**Answer:** 1 is minor, 2 is major, 3 is minor, 4 is major. Case 4 follows PostgreSQL's pre-10 two-number major convention.

### Exercise 5. Predict `MERGE` Compatibility

```sql
MERGE INTO stock_balances AS target
USING stock_changes AS source
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET available_quantity = source.incoming_quantity
WHEN NOT MATCHED THEN
    INSERT (sku, available_quantity)
    VALUES (source.sku, source.incoming_quantity);
```

**Question:** Can this run verbatim on PostgreSQL 14?

**Answer:** No. `MERGE` was added in PostgreSQL 15. On a 14 server, rewrite using a compatible pattern or plan a major upgrade if business and operational schedules allow.

### Exercise 6. Investigating a Post-Update Bug

Suppose production `16.2` exhibits a query bug that staging `16.5` does not reproduce. You should:

1. Confirm both are truly PostgreSQL Server major 16, without confusing client versions.
2. Read release notes from `16.3` through `16.5` looking for relevant fixes.
3. Compare configurations, extensions, workloads, and data across both environments.
4. Test in a controlled environment before deploying the minor update to production.

Differing minor versions alone do not prove the bug is fixed there, yet they provide a concrete lead to investigate.

## 17. A Quick Daily Lookup Workflow

Whenever starting a PostgreSQL topic or troubleshooting in practice:

```text
1. Identify target server and database
           │
           v
2. SHOW server_version;
   SHOW server_version_num;
           │
           v
3. Split major/minor by rule:
   - >= PostgreSQL 10: major = first number
   - <  PostgreSQL 10: major = first two numbers
           │
           v
4. Read /docs/<major>/ manual for features/syntax
           │
           v
5. Read release notes for relevant minors/majors
           │
           v
6. Cross-check client, extensions, drivers, and environment
           │
           v
7. Test on the exact target version before deploying
```

Practical example:

```sql
-- In an SQL connection to production:
SHOW server_version;
-- Suppose output is: 16.4

SHOW server_version_num;
-- Suppose output is: 160004
```

From this:

- **Major:** 16.
- **Minor:** 4.
- **Primary manual:** `https://www.postgresql.org/docs/16/`.
- **Looking for a bug or security fix:** check release notes in branch 16 and relevant minor versions.
- **Testing a major 17 feature:** read 17 docs/release notes as well, without applying them blindly to server 16.
- **Planning a major upgrade:** follow the target version's upgrade documentation, checking extensions and data migration strategy.

## 18. Conclusion

In PostgreSQL, distinguish carefully:

- **From PostgreSQL 10:** version `X.Y` has major `X` and minor `Y`.
- **Before PostgreSQL 10:** version `X.Y.Z` has major `X.Y` and minor `Z`.
- **Minor updates** primarily deliver bug and security fixes within the same major; **major upgrades** can add features and require a dedicated data migration procedure.
- **Server version** governs supported SQL—never substitute `psql --version`, JDBC driver versions, or extension versions.
- **Version-pinned official manuals** are the starting point for syntax, while **per-release release notes** explain bug fixes, behavior changes, and migration caveats.
- `/docs/current/` shifts majors over time. For a pinned server, prefer `/docs/{major}/` and verify official support timelines.

Reading version-accurate documentation does more than prevent syntax errors while learning. It underpins application compatibility, incident triage, security patching, and controlled PostgreSQL upgrades.
