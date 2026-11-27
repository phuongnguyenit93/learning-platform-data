# Authentication Plugins, SQL Mode, and Collation After Upgrade

After upgrading MySQL, applications may fail to connect even though usernames and passwords did not change; SQL queries that previously succeeded may begin throwing errors; and string comparison or sort results may differ from before. Three areas that must be checked early are account authentication plugins, server/session `sql_mode`, and schema character sets/collations.

Default changes across major versions do not automatically convert every existing account or column to the new configuration. Some differences surface only when creating new objects, some appear only when applications open new connections, and others emerge only when queries run against specific edge-case data. Therefore, post-upgrade checks must compare old and new configurations, test with the exact application drivers, and inspect data at risk of colliding under a new collation.

## 1. Three Compatibility Layers to Verify

| Layer | Components | Symptoms of Incompatibility |
|---|---|---|
| Authentication | MySQL account plugins, auth protocols, and TLS/RSA | Clients fail to log in, unsupported plugin errors, or key exchange failures |
| SQL semantics | `sql_mode` at GLOBAL/SESSION level and modes stored with stored programs | Queries rejected, date/numeric values handled differently, altered SQL behavior |
| Strings and comparisons | Character set, collation at server/database/table/column levels, and connection collation | Different sort order, different comparisons, unique key collisions, or index creation failures |

Do not address all three with a single blanket configuration change. Each layer must be inspected and transitioned according to its own compatibility goals.

## 2. Authentication Plugin Changes Across Versions

An authentication plugin governs how MySQL verifies an account's login credentials. Plugins are bound to each account—that is, each `user` and `host` pair; two accounts with the same username but different hosts can use different plugins or policies.

A critical difference when upgrading:

- MySQL 5.7 commonly uses `mysql_native_password` as the default plugin.
- Starting in MySQL 8.0.4, `caching_sha2_password` became the default authentication plugin.
- `mysql_native_password` was deprecated in MySQL 8.0.34, disabled by default in MySQL 8.4, and removed in MySQL 9.0.

Consequently, an older application that supports only `mysql_native_password` might still connect on certain MySQL 8.0 configurations yet fail when upgrading to 8.4 or 9.x. Re-enabling the legacy plugin should not be treated as a long-term solution; upgrade drivers and migrate accounts to a supported plugin.

### How Does caching_sha2_password Work?

`caching_sha2_password` uses SHA-256 authentication with a server-side cache to reduce repeated authentication overhead. A connection can use fast authentication if the required credentials are cached; if full authentication is required, the client and server must exchange credentials securely.

For full authentication, use TLS to protect the connection. Without TLS, the client may require RSA key exchange and must trust the server's genuine public key. Flags for automatic public key retrieval can be convenient in test environments, but production should verify server identity and secure the channel with TLS.

An authentication plugin does not replace TLS. Using `caching_sha2_password` on an account does not mean SQL traffic after login is encrypted in transit. TLS configuration and certificate verification remain separate connection policies.

## 3. Inventorying Accounts and Clients Before Upgrading

Before changing plugins, list existing accounts, allowed connection hosts, active plugins, and the owning applications. You can inspect account details with:

```sql
SELECT
  User,
  Host,
  plugin
FROM mysql.user
ORDER BY User, Host;
```

`mysql.user` is a system object provided by MySQL for viewing account metadata; read only what is needed and never update system tables directly. To inspect the definition and security requirements of a specific account, run:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.%';
SHOW GRANTS FOR 'orders_app'@'10.20.30.%';
```

Check which authentication plugins are loaded:

```sql
SELECT
  PLUGIN_NAME,
  PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_TYPE = 'AUTHENTICATION';
```

Then cross-check against the client matrix:

- Versions of MySQL Connector/J, Connector/NET, Connector/Python, C API clients, or equivalent drivers.
- Actual framework and connection library versions packaged inside the application.
- TLS settings, CAs, hostname verification, and RSA public keys if applicable.
- Accounts used by applications, batch jobs, monitoring, backups, migrations, and operational tools.
- External authentication mechanisms such as LDAP, PAM, sockets, or custom organization plugins.

Do not mass-convert accounts without identifying owners first. Monitoring, backup, or legacy application accounts may run on separate hosts with different connector versions.

## 4. Migrating Accounts to caching_sha2_password

For accounts using standard MySQL passwords, you can switch the plugin and reset the password with `ALTER USER`:

```sql
ALTER USER 'orders_app'@'10.20.30.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_NEW_SECRET';
```

Replace the placeholder string with a password generated and stored via a secret manager per organizational policy. Never commit production passwords into repositories, shared migration scripts, tickets, or shell history. Changing a password may require updating application secrets and cycling connection pools.

If the version supports random password generation, MySQL can generate the password:

```sql
ALTER USER 'orders_app'@'10.20.30.%'
  IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD;
```

Save the returned password immediately in the secret manager. Verify syntax and required privileges on the exact version before using this.

After the change:

1. Run `SHOW CREATE USER` to confirm the plugin for the exact `user`/`host` pair.
2. Update the secret in the application or secret manager.
3. Open a fresh connection using the exact production driver version.
4. Verify TLS and server certificate validation.
5. Run queries verifying privileges, transactions, and required write operations.
6. Confirm connection pools recreate connections rather than continuing to reuse old sessions.

Already-open sessions typically keep running with their established authentication state; tests must open brand-new connections to prove drivers can re-authenticate. Never rely solely on existing connections after changing a plugin.

### When Legacy Clients Remain

During a transition period, MySQL 8.4 can re-enable `mysql_native_password` via the server setting `mysql_native_password=ON`, if the organization accepts the risk and needs time to upgrade clients. This must only be a time-bound temporary measure with a tracked list of dependent accounts and a retirement plan. MySQL 9.0 removed this plugin entirely, so that workaround cannot be relied upon when upgrading to 9.x.

Do not downgrade the entire server or revert all accounts to the legacy plugin solely so one un-updated application can keep running. Upgrading the driver is usually the sustainable fix.

## 5. TLS, RSA, and Common Login Errors

Post-upgrade authentication errors commonly stem from the client or how credentials are exchanged:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Client reports unsupported authentication plugin | Old driver does not implement `caching_sha2_password` | Upgrade connector/driver and test in staging |
| Full authentication fails without TLS | Client lacks the matching RSA public key or required key exchange support | Prefer TLS; if using RSA, distribute and verify the public key per policy |
| Fast authentication works, but new connections fail | Old connections used the cache; new connections must perform full authentication | Check TLS/RSA and test opening new connections after cache expiry or with a test account |
| Correct username still rejected | MySQL matched a different account due to host matching or the account uses a different plugin | Verify exact `user`/`host` pair, `SHOW CREATE USER`, and auth logs |
| Application fails after plugin switch | Un-updated secret, pool holding old sessions, or incompatible connector | Update secret, recycle pool, and check connector |
| Login succeeds, but traffic is unencrypted | Authentication plugin does not enable TLS automatically | Configure TLS separately and verify `Ssl_version`, `Ssl_cipher` in session |

Check the TLS status of a connection session:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

If `Ssl_cipher` is empty, the current session is not using TLS. Test using a new TCP connection matching how the application connects; local Unix sockets may not show a TLS cipher.

## 6. SQL Mode Can Alter Statement Behavior

`sql_mode` is a set of modes controlling how MySQL parses and executes SQL. An upgrade can change default values, remove legacy modes, or expose statements that relied on non-standard behavior.

Check both GLOBAL and SESSION values:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

The GLOBAL value sets the default for new sessions. Applications or connection pools may override the session mode upon connecting, so you cannot look only at `@@GLOBAL.sql_mode` to know which modes production queries actually run under.

Modes requiring special attention:

| Mode | Effect | Issues Exposed After Upgrade |
|---|---|---|
| `STRICT_TRANS_TABLES` | Rejects or warns on invalid/missing values per strict rules | Legacy INSERT/UPDATEs may fail because invalid data was previously coerced or defaulted |
| `STRICT_ALL_TABLES` | Applies strict behavior to more storage engines | Batch imports or non-transactional tables may handle errors differently |
| `ONLY_FULL_GROUP_BY` | Requires non-aggregated SELECT columns to satisfy GROUP BY or functional dependency rules | Reporting queries that used to run may error out for selecting indeterminate columns |
| `ANSI_QUOTES` | Double quotes are treated as identifier quotes | SQL using `"` to quote string literals may fail |
| `PIPES_AS_CONCAT` | `||` is treated as string concatenation rather than OR | Legacy boolean expressions may change meaning |
| `NO_ZERO_DATE`, `NO_ZERO_IN_DATE` | Controls dates with zero components; status and defaults vary by version | Old date data or imports containing zero dates may emit warnings/errors |
| `NO_AUTO_CREATE_USER` | Legacy mode related to GRANT creating users | Removed in MySQL 8.0.11; configs still containing it may be incompatible |

Do not copy a raw `sql_mode` string from an older server to a new version without verifying every mode is still supported. A removed mode can cause the server to reject the configuration at startup or when setting the variable.

### Checking Affected Queries

Under `ONLY_FULL_GROUP_BY`, the following query may be rejected if `customer_name` is not functionally dependent on `customer_id` in the schema:

```sql
SELECT customer_id, customer_name, SUM(amount)
FROM sales.orders
GROUP BY customer_id;
```

The proper fix is usually grouping by the column as well, applying an appropriate aggregate function, or ensuring a key/unique constraint expresses the functional dependency:

```sql
SELECT customer_id, MAX(customer_name) AS customer_name,
       SUM(amount) AS total_amount
FROM sales.orders
GROUP BY customer_id;
```

Use `MAX(customer_name)` only if all rows for the same `customer_id` truly share the same name or the business logic accepts picking the maximum value under collation order. Never add an aggregate function merely to silence an error without understanding the data semantics.

For strict mode, inspect INSERT/UPDATE statements, CSV imports, ETL jobs, and code relying on implicit string-to-number or date coercion. Fix source data or mappings to be valid rather than disabling strict mode server-wide.

## 7. Reconciling and Configuring SQL Mode Post-Upgrade

Before upgrading, save `@@GLOBAL.sql_mode` and application session modes. After upgrading, compare the new values and identify any modes that changed or are no longer supported.

If changes are required, set a tested mode string. Example illustrating strict mode with required modes:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

The command above is a policy example only; the actual list must fit your applications and version. Changing GLOBAL does not alter existing sessions. For persistent changes, manage them in configuration files or your organization's persistence mechanism after testing:

```sql
SET PERSIST sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Do not strip `ONLY_FULL_GROUP_BY` or strict mode merely to keep legacy queries running without inspecting the data and query semantics. If you must temporarily relax a mode for a controlled import session, restore it immediately afterward and document the reason and expiration.

### Stored Routines and Triggers Can Retain Old SQL Modes

MySQL saves the `sql_mode` active at creation time for stored procedures, stored functions, triggers, and events. When these objects execute, they use the mode stored with the object rather than automatically inheriting all new server modes.

As a result, two different SQL behaviors can coexist post-upgrade: ad-hoc statements use the new session mode, while legacy routines or triggers continue using the mode captured at creation. Inspect object metadata and plan to recreate them if they need the new mode. Before running `DROP`/`CREATE` or redeploying, save full definitions, `DEFINER`, privileges, and event schedules so security and operational semantics are not lost.

## 8. Character Set and Collation After Upgrade

A character set defines how characters are encoded; a collation defines how strings are compared and sorted. These two concepts are related but distinct.

- Character set defines the character repertoire and byte representation. `utf8mb4` supports up to four bytes per Unicode character.
- Collation defines comparison rules: case sensitivity, accent sensitivity, character equivalence, and trailing spaces.

In MySQL 8.0, the new server default switched to `utf8mb4` with default collation `utf8mb4_0900_ai_ci`. MySQL 5.7 installations often used `latin1` and `latin1_swedish_ci` by default. However, upgrading the server does not automatically convert existing databases, tables, and columns to `utf8mb4`; objects with explicitly declared charsets/collations retain their properties until explicitly converted.

Therefore, after an upgrade, the following may coexist simultaneously:

- Older tables using `latin1` or `utf8mb4_unicode_ci`.
- Newly created tables without an explicit charset using the new server default.
- Certain columns having a column-level collation differing from the table collation.
- Client connections using `character_set_client`, `character_set_connection`, or `collation_connection` differing from the schema.

Inspect server defaults and session settings:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
SHOW VARIABLES LIKE 'character_set_database';
SHOW VARIABLES LIKE 'collation_database';
SHOW VARIABLES LIKE 'character_set_client';
SHOW VARIABLES LIKE 'character_set_connection';
SHOW VARIABLES LIKE 'collation_connection';
```

Inspect schema, table, and column charsets/collations via `information_schema`:

```sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';

SELECT
  TABLE_NAME,
  TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales';

SELECT
  TABLE_NAME,
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND CHARACTER_SET_NAME IS NOT NULL;
```

Do not rely on `collation_server` to infer the actual collation of every column. A column can override table defaults, and a table can override database defaults.

## 9. Collation Differences Can Alter Query Results

Collation names typically contain suffixes indicating comparison rules:

- `_ai_ci`: accent-insensitive, case-insensitive; generally ignores accents and letter case.
- `_as_cs`: accent-sensitive, case-sensitive; distinguishes accents and letter case.
- `_bin`: compares binary character values according to the charset.
- Collations with the `_0900` suffix use the Unicode Collation Algorithm version 9.0 rules introduced in MySQL 8.0.

An important difference is trailing-space padding during string comparisons. Many older collations use `PAD SPACE`, meaning trailing spaces are padded for comparison. UCA 9.0 collations such as `utf8mb4_0900_ai_ci` use `NO PAD`, where trailing spaces can distinguish two values. This affects `=` comparisons, `GROUP BY`, `DISTINCT`, joins, and unique indexes.

For example, under an accent- and case-insensitive collation, strings like `Cafe`, `cafe`, and `café` may be treated as equivalent by collation rules. Under a sensitive collation, they can be distinct values. Exact outcomes depend on the chosen collation and should not be guessed from visual rendering alone.

### Unique Index Risk When Changing Collation

Suppose a users table stores two email values considered distinct by an old collation. When switching to a case- or accent-insensitive collation, those two values can become equivalent and can no longer coexist in a unique index.

Before converting, find groups of values that would collide under the target collation. If the column already uses `utf8mb4`, you can check with:

```sql
SELECT
  email COLLATE utf8mb4_0900_ai_ci AS email_under_new_collation,
  COUNT(*) AS occurrences
FROM users
GROUP BY email_under_new_collation
HAVING COUNT(*) > 1;
```

Test on real data and confirm the target collation exists in your server version. If the column uses a different charset, convert/`CAST` to the target charset in the check query. Resolve duplicates according to business rules before creating unique indexes or altering the collation.

Beyond unique keys, a new collation can alter `ORDER BY` ordering, `LIKE` matches, `JOIN` comparisons, `GROUP BY` grouping, and pagination order. If an application uses `ORDER BY name LIMIT ... OFFSET ...`, order changes can alter page results even when data has not changed.

## 10. Selecting and Converting Collations Safely

Not every system should convert all columns to the same collation. For example, person names may require accent-insensitive search, while identifiers, tokens, or byte-sensitive strings may require binary collations or stricter rules.

Check collations supported by the server:

```sql
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
SHOW COLLATION LIKE 'utf8mb4_unicode_ci';
SHOW COLLATION LIKE 'utf8mb4_bin';
```

On MySQL 8.0, you can also inspect padding attributes in `SHOW COLLATION` or `INFORMATION_SCHEMA.COLLATIONS` depending on version. Do not adopt a `_0900` collation if a replica or downstream environment does not yet support it.

Changing a database default affects only newly created objects or altered objects that omit explicit attributes; it does not automatically convert existing columns:

```sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Converting an entire table and its character columns to a new charset/collation may require a rebuild and data conversion:

```sql
ALTER TABLE sales.customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

The command above can consume significant I/O, disk space, time, and metadata locks; it may also widen text column types to preserve character capacity. Check index lengths, duplicates, foreign keys, applications, and replication before running it. For large tables, treat it as a schema migration with its own maintenance plan.

If changing only a single column's collation, use `MODIFY` or `CHANGE` while restating the full data type and column attributes. Preserve `NULL`/`NOT NULL`, defaults, comments, generated expressions, and other attributes; omitting them can cause DDL to drop existing column properties.

### utf8 and utf8mb4

In MySQL, the name `utf8` is a historical alias for `utf8mb3`, supporting at most three bytes per character. `utf8mb3` was deprecated in MySQL 8.0. For new Unicode data, explicitly design with `utf8mb4` and an appropriate collation. However, converting legacy data requires verifying actual byte encoding; declaring a different charset will not repair bytes that were previously misencoded.

## 11. Collation Between Connection and Column

Even when a table uses the desired collation, application connections may use a different charset/collation. MySQL converts strings between client and connection according to session variables; expressions mixing multiple collations can run into coercibility rules or `illegal mix of collations` errors.

Inspect session configuration:

```sql
SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
```

Applications should configure their connector to use `utf8mb4` per driver documentation. Avoid issuing manual `SET NAMES` calls in multiple places when the connector already manages charsets, as this can desynchronize client and server state. If you encounter `Illegal mix of collations`, inspect the charset/collation of each column, literal, variable, and expression in `JOIN`/`UNION`; use explicit `COLLATE` only after confirming business semantics.

Example forcing comparison under a specific collation:

```sql
SELECT customer_id
FROM customers
WHERE customer_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci;
```

This example assumes both column and literal are compatible with the `utf8mb4` charset. Do not force collations just to hide design flaws when columns represent semantically different data.

## 12. Post-Upgrade Compatibility Plan

A practical plan should be divided into phases:

### Pre-Upgrade

1. Record the MySQL version, authentication plugins for all accounts, drivers, and application connectors.
2. Save `@@GLOBAL.sql_mode`, actual application session modes, and connection pool configs.
3. Export lists of databases/tables/columns along with their character sets and collations.
4. Identify accounts using `mysql_native_password` and clients not yet supporting `caching_sha2_password`.
5. Identify queries relying on old SQL modes, zero dates, non-standard `GROUP BY`, and double quotes.
6. Identify unique indexes, `JOIN` operations, and pagination logic sensitive to collation.
7. Build a staging clone matching production data, accounts, routines, and configuration closely.

### Post-Upgrade on Staging

1. Confirm the server starts and required plugins load.
2. Open new connections using each driver type with representative accounts; verify TLS.
3. Set session modes matching production and run the SQL test suite.
4. Check stored procedures, functions, triggers, and events with pre-captured SQL modes.
5. Compare charset/collation at server, database, table, column, and connection levels.
6. Run duplicate queries under the target collation and test creating indexes on the clone.
7. Cross-check `ORDER BY`, `LIKE`, `JOIN`, `GROUP BY`, `DISTINCT`, and pagination.
8. Verify replication and cross-version compatibility across the topology.

### After Production Deployment

- Monitor authentication errors, failed connection counts, and TLS handshake errors.
- Monitor SQL errors such as `ONLY_FULL_GROUP_BY`, incorrect date, and data truncation.
- Monitor duplicate key errors or illegal mix of collations errors.
- Confirm all pools created fresh connections and received the expected session variables.
- Document any accounts still using legacy plugins along with owners and retirement deadlines.
- Convert collations or data in batches of tables only after full reconciliation.

## 13. Post-Upgrade Troubleshooting

| Symptom | First Check | Remediation |
|---|---|---|
| Some applications cannot log in | Account plugin, host match, connector version, TLS/RSA | Upgrade driver, migrate account per plan, verify CA/hostname |
| Only new connections fail | Full authentication, cache, secrets, and connection pool | Test a fresh connection with TLS and current secret; recycle pool |
| GROUP BY queries fail | `@@SESSION.sql_mode`, `ONLY_FULL_GROUP_BY` | Rewrite query per aggregate/functional dependency semantics |
| Legacy date imports fail | Strict mode, zero dates, file formatting | Normalize source data and handle invalid date values |
| Unique index DDL fails | Duplicate values under target collation | Find and resolve duplicates per business rules before creating index |
| ORDER BY or searches return different results | Actual column and connection collations | Compare old/new collations, test case/accent/padding rules |
| Illegal mix of collations | Operands in expression use different collations | Standardize schema/connection or use explicit `COLLATE` matching business rules |
| Replica stops when applying DDL | Replica lacks collation/plugin support or schema differs | Check version and applier logs; deploy compatibility before issuing DDL |

Do not apply quick fixes by changing global SQL mode, converting all columns to a default collation, or enabling legacy authentication plugins across all servers. First pinpoint the exact account, session, query, or column causing the failure; then apply a narrowly scoped change and retest.

## 14. Practical Scenario

A system is upgrading from MySQL 5.7 to MySQL 8.4. A legacy Java application, an ETL job, and a dashboard use connectors of varying versions. The database contains a unique email column, multiple stored procedures, and several older tables using `latin1`.

**Step 1 — Inventory authentication.** List accounts and plugins, identifying which accounts still use `mysql_native_password`. Build an owner/driver table for each account, including ETL and the dashboard.

**Step 2 — Upgrade connectors.** Upgrade the Java driver and remaining clients to support `caching_sha2_password`. In staging, open fresh TLS connections and verify hostnames for each account.

**Step 3 — Migrate accounts.** Migrate accounts application by application with `ALTER USER`, update secrets, and restart pools. Keep a tested administrative account ready in case an application encounters errors.

**Step 4 — Compare SQL modes.** Record old/new modes and run all reporting and ETL queries. Fix `GROUP BY` queries and invalid date values; inspect modes stored inside routines and triggers.

**Step 5 — Evaluate collations.** Inventory email columns and search for duplicates under the target collation. Check trailing spaces, case/accent sensitivity, and search queries. Convert tables only after business decisions are made for duplicates.

**Step 6 — Roll out in phases.** Upgrade replicas and verify compatibility before issuing DDL using new collations. Run migrations on small tables first, then large tables per space/lag plans. Monitor application errors and reconcile results after each step.

There is no need to convert every `latin1` table to `utf8mb4` inside the same upgrade window. Prioritize tables with clear Unicode needs, verify actual encodings, and schedule separate plans for large tables or collation-sensitive unique indexes.

## 15. Production Checklist

- [ ] Inventoried accounts by `user`/`host` pair, plugin, and owning application.
- [ ] All required connectors support `caching_sha2_password`.
- [ ] Tested full authentication on fresh connections and verified TLS.
- [ ] No open-ended dependencies remain on `mysql_native_password`.
- [ ] Saved and compared `@@GLOBAL.sql_mode` and actual session modes.
- [ ] Reviewed queries for `GROUP BY`, strict mode, zero dates, and removed modes.
- [ ] Checked SQL modes stored in procedures, functions, triggers, and events.
- [ ] Inventoried charsets/collations at server, database, table, column, and connection levels.
- [ ] Checked for duplicates under the target collation before changing unique indexes or collations.
- [ ] Tested `ORDER BY`, `JOIN`, `LIKE`, `GROUP BY`, `DISTINCT`, and pagination.
- [ ] Verified replicas support plugins/collations and compatible versions before issuing changes.
- [ ] Have phased transition, reconciliation, and recovery/forward-fix plans ready.

Safe MySQL upgrades require verifying how clients log in, how the server interprets SQL, and how string data is compared. Migrating accounts to supported plugins, controlling `sql_mode` per session, and evaluating collations before converting data prevents bugs that only appear when applications open fresh connections or process edge-case values in production.
