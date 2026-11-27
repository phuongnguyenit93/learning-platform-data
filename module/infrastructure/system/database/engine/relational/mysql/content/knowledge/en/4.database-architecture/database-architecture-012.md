# Legacy Query Cache Mechanism and Limitations During Version Upgrades

This lesson belongs to the **Architecture** chapter of the `DATABASE_MYSQL` module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and relational database operations. The Query Cache is a historical query optimization mechanism in MySQL that remains relevant when reading and maintaining legacy systems or planning upgrades.

After this lesson, you will be able to explain how the Query Cache used to work, identify suitable workloads and causes of cache ineffectiveness, distinguish the Query Cache from other caches, and prepare applications and configurations when migrating from MySQL 5.7 to MySQL 8.0 and later.

## 1. What Is the Query Cache?

**MySQL Query Cache** is a cache for query results. In older MySQL versions that supported it, the server stored the text of a SELECT statement together with the returned result set. Upon receiving an identical, cache-eligible SELECT statement, the server could return the stored result set without re-parsing and re-executing the query.

The Query Cache was shared across sessions. For instance, session A executed an eligible SELECT statement and populated a cache entry; session B could receive that exact result when sending the same query under the same cache context.

The goal of this mechanism was to reduce latency and repeated processing in systems with many identical read queries over infrequently changing data. An example is a product category list or configuration catalog read repeatedly by many requests.

The Query Cache was not the only data cache in MySQL. It is important to distinguish:

| Mechanism | What it stores | Effect |
|---|---|---|
| Legacy Query Cache | SELECT text and entire result set | Returns existing query results without re-executing the SELECT |
| InnoDB Buffer Pool | InnoDB data and index pages | Reduces reading data and indexes from storage devices |
| Prepared Statement | Prepared statement structure for reuse | Reduces statement preparation/parsing cost across executions |
| Application or proxy cache | Data or results keyed by system-defined identifiers | Reduces how often the application must query the database |

When the Query Cache was removed, the InnoDB Buffer Pool remained intact. MySQL still caches data and index pages; only the server-level Query Cache storing full SELECT results was removed.

## 2. Version History and Removal Milestones

Know the exact version boundaries when reading legacy configurations:

| Version | Query Cache status |
|---|---|
| MySQL 5.5 and earlier supported versions | Query Cache available |
| MySQL 5.6 | Available, but disabled by default |
| MySQL 5.7 prior to 5.7.20 | Usable; disabled by default |
| MySQL 5.7.20 and later | Query Cache marked deprecated; still present in the 5.7 series |
| MySQL 8.0 and later | Query Cache removed |

Starting in MySQL 5.7.20, Query Cache components were marked deprecated. The MySQL 8.0 series no longer supports this mechanism. Newer MySQL releases continue without the Query Cache.

This means:

- You cannot enable the Query Cache by increasing memory sizes on MySQL 8.0 or later.
- Variables such as `query_cache_size`, `query_cache_type`, `query_cache_limit`, and `query_cache_min_res_unit` are no longer valid Query Cache configuration options in MySQL 8.0.
- Status counters `Qcache_*` and administrative statements `FLUSH QUERY CACHE` and `RESET QUERY CACHE` were removed.
- The `SQL_CACHE` modifier is no longer supported. In MySQL 8.0 documentation, `SQL_NO_CACHE` remains in a deprecated state with no effect; do not rely on this modifier in new code.

Therefore, when reading a legacy MySQL configuration file, identify the target version before copying Query Cache parameters.

## 3. How Did the Query Cache Work in MySQL 5.7?

The lifecycle of a query can be visualized as follows:

~~~mermaid
flowchart TD
    A[Client sends SELECT] --> B{Query Cache enabled?}
    B -- No --> C[Parse, optimize, and execute]
    B -- Yes --> D[Match query and context]
    D --> E{Valid entry exists?}
    E -- Yes --> F[Check SELECT privilege]
    F --> G[Return cached result]
    E -- No --> C
    C --> H[Return result to client]
    H --> I{Query eligible for caching?}
    I -- Yes --> J[Store query and result]
    I -- No --> K[Done]
    J --> K
~~~

Main steps:

1. The server receives the SELECT statement and checks the Query Cache before parsing the statement.
2. If a matching entry is found, the server verifies the current account's SELECT privilege on the involved databases and tables.
3. If privileges are valid and the entry is still valid, the server sends the stored result to the client.
4. If no matching entry exists, the statement goes through normal parsing, optimization, and execution.
5. For eligible queries, the result is stored in the Query Cache while sending data to the client.
6. Whenever an involved table is modified, cache entries depending on that table are invalidated and removed.

The Query Cache was not designed to serve stale data. It proactively invalidated related results whenever a table changed. However, this table-level invalidation could drastically reduce cache hit rates in write-heavy systems.

### Exact Query Text Matching

The legacy Query Cache compared queries prior to parsing. The following two statements were considered different:

~~~sql
SELECT * FROM products;
select * from products;
~~~

Even a difference in letter case produced two distinct query texts. Differences in whitespace, comments, or formatting also created separate entries.

Beyond query text, differing contexts prevented sharing entries, such as:

- Different default databases.
- Different protocol versions.
- Different default character sets.

Consequently, applications generating SQL with inconsistent formatting suffered low cache hit rates even when queries were logically equivalent.

For prepared statements using the binary protocol, MySQL 5.7 applied separate matching rules: content was evaluated after parameter expansion, and only matched against statements cached via the binary protocol. Do not assume prepared statements automatically shared entries with SQL sent over the text protocol.

### Privileges Were Still Checked

The Query Cache did not bypass access control. Before returning a cached result, MySQL verified that the user held SELECT privilege on all involved databases and tables. If privileges were insufficient, the cached result was not used.

This allowed the Query Cache to share results across sessions while still enforcing MySQL privilege rules.

## 4. Conditions and Limits on Cacheable Queries

Not every SELECT entered the Query Cache. Besides requiring the Query Cache to be enabled, a query had to satisfy the rules of the running version.

Several categories of queries were not cached in MySQL 5.7:

- Subqueries nested inside an outer query.
- Queries executed inside stored functions, triggers, or events.
- Queries using temporary tables.
- Queries referencing system tables such as `mysql`, `INFORMATION_SCHEMA`, or `performance_schema`.
- Queries accessing partitioned tables.
- Queries reading no tables.
- Queries using user variables, local stored-program variables, or loadable/stored functions.
- Queries using state- or time-dependent functions such as `NOW()`, `RAND()`, `UUID()`, `CONNECTION_ID()`, or `CURRENT_USER()`.
- Locking reads such as `FOR UPDATE` or `LOCK IN SHARE MODE`.
- Queries using `SELECT ... INTO OUTFILE` or `INTO DUMPFILE`.
- Queries generating warnings or involving restricted column-level privileges.

These are representative examples, not a substitute for version-specific documentation. When evaluating a specific query, check the Query Cache section of the Reference Manual for your exact MySQL 5.7 version.

Another note: the Query Cache could operate with InnoDB tables and within certain transaction contexts, yet it still had to obey cache eligibility rules and transaction consistency requirements. Do not infer that every InnoDB SELECT was cached.

## 5. Cache Invalidation and Concurrency Contention

A major limitation of the Query Cache was its table-level invalidation mechanism.

Suppose three SELECT statements all read the `products` table:

~~~sql
SELECT id, name FROM products WHERE active = 1;
SELECT COUNT(*) FROM products WHERE active = 1;
SELECT category, COUNT(*) FROM products GROUP BY category;
~~~

If all three queries were cached, any modification to `products` such as INSERT, UPDATE, DELETE, TRUNCATE, ALTER, or DROP could invalidate every entry depending on that table.

This could happen even if the write modified only a single row. The Query Cache did not maintain a dependency map granular enough to partially update individual SELECT results.

### Why Do Write Workloads Degrade Cache Effectiveness?

Consider a retail system with:

- 10,000 repeated SELECTs per second.
- 2,000 distinct SELECTs by text or parameters.
- Continuous INSERT and UPDATE operations on product, inventory, and order tables.

Even with high SELECT volume, continuous writes could flush many entries before they could be reused. The server had to recompute and re-store results while still paying the overhead of checking and maintaining the cache.

### Global Mutex and Lock Contention

The legacy Query Cache used a global synchronization lock to manage cache structures. Sessions needing to look up, store results, or invalidate entries could end up waiting on that lock.

In environments with many CPUs and many concurrent connections, this global lock could become a bottleneck. In such cases, time spent waiting on the cache exceeded time saved by cache hits.

In MySQL 5.7's Process List, the `Waiting for query cache lock` state was a sign to investigate. Other states such as `checking query cache for query`, `invalidating query cache entries`, or `sending cached result to client` also helped identify related activity.

MySQL disabled the Query Cache by default starting in MySQL 5.6 because of scalability bottlenecks in high-throughput workloads. If there was no intention to use the cache, setting both `query_cache_size=0` and `query_cache_type=0` at startup prevented the server from acquiring the Query Cache mutex.

## 6. Query Cache Parameters in MySQL 5.7

This section applies only to MySQL 5.7 servers that still support the Query Cache. Do not run these commands on MySQL 8.0 or later.

| Parameter | Meaning |
|---|---|
| `query_cache_size` | Memory allocated for the Query Cache; set to 0 to disable |
| `query_cache_type` | Mode to disable, enable, or cache only explicitly marked queries |
| `query_cache_limit` | Maximum size of an individual result eligible for caching |
| `query_cache_min_res_unit` | Minimum block size used when allocating memory for results |
| `query_cache_wlock_invalidate` | Controls whether cached results are invalidated when a write lock occurs |

### query_cache_type

Three primary values:

| Value | Behavior |
|---|---|
| `OFF` or `0` | Do not store or read results from the Query Cache |
| `ON` or `1` | Cache eligible queries except statements starting with `SELECT SQL_NO_CACHE` |
| `DEMAND` or `2` | Cache eligible queries only when the `SQL_CACHE` modifier is present |

In MySQL 5.7, the Query Cache was disabled by default via `query_cache_type=OFF`. The default `query_cache_size` was 1 MB, which did not mean the cache was active.

### Experimental Configuration in MySQL 5.7

Example caching only explicitly marked queries:

~~~ini
[mysqld]
query_cache_type=DEMAND
query_cache_size=64M
query_cache_limit=1M
query_cache_min_res_unit=4096
~~~

After restarting the server, verify:

~~~sql
SHOW VARIABLES LIKE 'query_cache%';
SHOW VARIABLES LIKE 'have_query_cache';
~~~

With `DEMAND`, a SELECT statement needed the `SQL_CACHE` modifier to be stored if eligible:

~~~sql
SELECT SQL_CACHE id, name
FROM products
WHERE active = 1;
~~~

To bypass the Query Cache for a single statement in MySQL 5.7:

~~~sql
SELECT SQL_NO_CACHE id, name
FROM products
WHERE active = 1;
~~~

Do not use these configuration examples as templates for modern MySQL. Query Cache parameters were removed in MySQL 8.0.

## 7. Monitoring Query Cache Effectiveness in MySQL 5.7

Do not simply enable the Query Cache and assume performance improved. Measure hit ratio, evictions, and lock wait time over the same workload window.

Key counters:

| Counter | Meaning |
|---|---|
| `Qcache_hits` | Number of queries served from the cache |
| `Qcache_inserts` | Number of results added to the cache |
| `Qcache_not_cached` | Number of queries not cached |
| `Qcache_lowmem_prunes` | Number of entries removed to free memory |
| `Qcache_queries_in_cache` | Number of queries currently in the cache |
| `Qcache_free_memory` | Remaining free cache memory |
| `Qcache_free_blocks` | Number of free blocks; can help detect fragmentation |

Reading the counters:

~~~sql
SHOW GLOBAL STATUS LIKE 'Qcache%';
SHOW GLOBAL STATUS LIKE 'Com_select';
~~~

Record values before and after a measurement interval, then compute deltas. Do not look solely at cumulative totals since server startup.

You can use an approximate hit ratio:

```
Hit ratio ≈ ΔQcache_hits / (ΔQcache_hits + ΔCom_select)
```

This is a reference indicator for comparison within the same measurement window; also inspect query errors, workload mix, and other counters to draw accurate conclusions.

A few interpretations:

- `Qcache_hits` rising rapidly while `Qcache_inserts` rises moderately: many repeated queries are likely being served from the cache.
- `Qcache_lowmem_prunes` rising rapidly: the cache is evicting entries to make room for new results; examine capacity and reuse patterns.
- `Qcache_not_cached` rising sharply: many queries are ineligible or not configured to be cached.
- High `Qcache_free_blocks` may indicate memory fragmentation.
- Many sessions in `Waiting for query cache lock`: the cache may be causing lock contention.

Legacy maintenance commands:

~~~sql
-- Defragment blocks; does not clear all results
FLUSH QUERY CACHE;

-- Remove all cached results
RESET QUERY CACHE;
~~~

`FLUSH QUERY CACHE` and `RESET QUERY CACHE` no longer exist in MySQL 8.0 and later.

## 8. Why Did MySQL Remove the Query Cache?

The Query Cache could provide clear benefits in read-heavy workloads with minimal writes and extremely high repetition of identical SELECTs. Yet it also had structural limitations hard to solve at the server level:

1. **Dependence on exact SQL text:** differences in whitespace, letter case, comments, or context created distinct cache keys.
2. **Table-level invalidation:** one small write could wipe out many cached results touching the same table.
3. **Poor scalability under high concurrency:** many sessions accessing the shared cache structure contended on mutexes.
4. **Benefits applied only on cache hits:** non-repeating, ineligible, or constantly invalidated queries still had to execute normally.
5. **Did not improve all workloads:** write-heavy systems or dynamic SQL workloads incurred cache management overhead instead.
6. **Did not replace query tuning:** an unindexed SQL query remained very slow whenever a cache miss or invalidation occurred.

Oracle decided to remove the Query Cache in MySQL 8.0 to focus on performance improvements benefiting broader workloads. The recommended path when upgrading is to move caching closer to the client, such as application-level caching or using a proxy capable of caching results.

## 9. Changes to Handle When Upgrading MySQL 5.7 to 8.0 or Later

When upgrading a system that uses the Query Cache, audit both server configuration and application code.

### Audit Configuration Files

Search for legacy parameters in `my.cnf`, `my.ini`, included files, and deployment configurations:

~~~ini
query_cache_type=ON
query_cache_size=64M
query_cache_limit=1M
query_cache_min_res_unit=4096
query_cache_wlock_invalidate=OFF
~~~

Remove these parameters from the target configuration. MySQL 8.0 does not recognize removed Query Cache variables; leaving them in configuration files can cause the server to report an unknown variable error and fail to start.

### Audit SQL Code and Libraries

Look for signs such as:

- `SQL_CACHE` or `SQL_NO_CACHE` in SELECT statements.
- `FLUSH QUERY CACHE` or `RESET QUERY CACHE`.
- Statements reading `query_cache_*` variables.
- Reports or dashboards depending on `Qcache_*` counters.
- Automated deployment scripts configuring the Query Cache.
- Application logic assuming repeated SELECTs are served from a server-side cache.

Remove or replace these dependencies. Do not only change server configuration while forgetting monitoring scripts or administrative SQL run during deployment.

### Verify Behavior and Performance After Upgrading

After removing legacy settings:

1. Start the target MySQL instance and inspect the error log.
2. Exercise the application's critical read/write flows.
3. Measure SELECT latency and CPU/I/O load without the Query Cache.
4. Identify time-consuming queries via the slow query log or Performance Schema.
5. Use EXPLAIN to inspect execution plans; on MySQL 8.0.18 and later, use EXPLAIN ANALYZE to compare estimates against actual timings and row counts.
6. Add external caching only where there is evidence of repeated queries and well-defined data freshness requirements.

Do not compare a warm-cache run on MySQL 5.7 against a cold-cache run on MySQL 8.0. Test across multiple iterations with the same dataset, concurrency, and read/write ratio.

## 10. Alternatives to the Query Cache

There is no single parameter in MySQL 8.0 that directly replaces the legacy Query Cache. Choose an approach suited to your system layer and consistency requirements.

### Application-Level Caching

The cache-aside pattern is commonly used:

1. The application checks the cache under a deterministic key.
2. If valid data exists, return it from the cache.
3. Otherwise, query MySQL and store the result in the cache.
4. When updating data, commit the transaction successfully and then update or invalidate related cache keys.

Pseudocode example:

~~~text
function getProductCatalog():
    value = cache.get("catalog:active:v1")

    if value exists:
        return value

    value = database.query(
        "SELECT id, name FROM products WHERE active = 1"
    )

    cache.set("catalog:active:v1", value, ttl = 60 seconds)
    return value
~~~

TTLs bound how long an entry can live. However, TTLs do not guarantee fresh data immediately after a transaction commits. If business logic requires immediate read-after-write consistency, implement controlled invalidation/updates or query the database directly on that code path.

Cache keys must include every factor that changes the output, such as query parameters, tenant, language, user permissions, and data version. Never share cache keys across users if outputs can differ by privileges or private data.

### Proxy-Level Caching

A proxy such as ProxySQL can cache SELECT results between the application and MySQL. Cache rules can target query groups and set TTLs.

The advantage is introducing caching in an intermediate tier without modifying every application code path. However, you must understand the proxy's invalidation policy. For example, ProxySQL's Query Cache relies on TTL; writes in MySQL do not automatically purge every matching entry. Stale results may continue to be served until the TTL expires or the cache is cleared.

Therefore, cache through a proxy only for queries that tolerate staleness. Flows requiring immediate read-after-write consistency should bypass the cache or use coordinated invalidation.

### Query and Data Optimization

Before adding caching, check whether queries can be improved inside MySQL itself:

- Create indexes matching filter predicates, joins, and sorting.
- Select only needed columns instead of `SELECT *`.
- Inspect rows examined versus rows returned.
- Use EXPLAIN or EXPLAIN ANALYZE to spot unnecessary full table scans, inefficient joins, and bad cardinality estimates.
- Optimize pagination and avoid redundant repeated queries.
- For heavy reports over slowly changing data, consider summary tables updated on a schedule or by events.

### Distinguishing Commonly Confused Mechanisms

| Mechanism | Does it cache SELECT results? | Role after Query Cache removal |
|---|---|---|
| InnoDB Buffer Pool | No | Continues caching data/index pages in RAM, reducing I/O |
| Prepared Statement | No | Reuses statement structure, reducing preparation overhead |
| Performance Schema | No | Collects query metrics, timings, and digests for analysis |
| Slow Query Log | No | Logs slow queries to pinpoint optimization targets |
| Application Cache | Yes | Replaces result caching according to business logic |
| ProxySQL Query Cache | Yes | Caches at the proxy tier by rules and TTL |
| Query Rewrite Plugin | No | Rewrites SQL statements by rules; does not store query results |

## 11. Practice Exercise: Observing the Query Cache in MySQL 5.7

This exercise applies only to MySQL 5.7 instances that still have the Query Cache. Do not run it on MySQL 8.0 or later.

### Prepare the Test Database

Use an administrative account on a dedicated lab instance:

~~~sql
CREATE DATABASE IF NOT EXISTS query_cache_lab;
USE query_cache_lab;

CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    active TINYINT NOT NULL
) ENGINE=InnoDB;

INSERT INTO products (id, name, category, active) VALUES
    (1, 'Keyboard', 'Accessories', 1),
    (2, 'Mouse', 'Accessories', 1),
    (3, 'Monitor', 'Display', 1),
    (4, 'Old Cable', 'Accessories', 0);
~~~

### Enable DEMAND Mode

Execute on MySQL 5.7:

~~~sql
SET GLOBAL query_cache_size = 1048576;
SET GLOBAL query_cache_type = DEMAND;
SET SESSION query_cache_type = DEMAND;

SHOW VARIABLES LIKE 'query_cache%';
~~~

After changing a GLOBAL value, other already-open sessions do not automatically pick up the new SESSION value. In this exercise, explicitly set SESSION on the exact connection running the SELECT.

### Run a Repeated Query

Run the following query twice, keeping the statement text identical:

~~~sql
SELECT SQL_CACHE category, COUNT(*) AS total
FROM products
WHERE active = 1
GROUP BY category;
~~~

Before and after the two runs, inspect the counters:

~~~sql
SHOW GLOBAL STATUS LIKE 'Qcache_hits';
SHOW GLOBAL STATUS LIKE 'Qcache_inserts';
~~~

The first run is typically a cache miss and may create an entry; the next run can be a cache hit if the query is eligible and the entry has not been invalidated or evicted.

Try changing letter case or whitespace in the SELECT statement and observe. The Query Cache can create a separate entry because the text is no longer identical.

### Observe Invalidation

Modify the data:

~~~sql
UPDATE products
SET active = 0
WHERE id = 3;
~~~

Re-run the exact cached SELECT statement. Because the `products` table changed, the old entry is invalidated; the query must execute again and may create a new entry. Run it once more to observe cache hits.

Try a query bypassing the cache:

~~~sql
SELECT SQL_NO_CACHE category, COUNT(*) AS total
FROM products
WHERE active = 1
GROUP BY category;
~~~

### Cleanup

When finished:

~~~sql
DROP DATABASE query_cache_lab;
~~~

If you need to restore the lab instance's initial configuration, turn the Query Cache off:

~~~sql
SET GLOBAL query_cache_type = OFF;
SET GLOBAL query_cache_size = 0;
~~~

These variables exist only in versions that support the Query Cache. Do not include them in shared scripts targeting MySQL 8.0 or later.

## 12. Checklist When Maintaining or Upgrading Legacy Systems

- [ ] Identified the exact source and target MySQL versions.
- [ ] Verified whether the Query Cache is actually enabled in the source version.
- [ ] Recorded hits, inserts, prunes, not-cached counts, and lock wait states under representative workloads.
- [ ] Located all `query_cache_*` parameters in configuration files and deployment scripts.
- [ ] Located `SQL_CACHE`, `SQL_NO_CACHE`, `FLUSH QUERY CACHE`, and `RESET QUERY CACHE` in application code.
- [ ] Updated dashboards and alerts that read `Qcache_*` counters.
- [ ] Ran integration tests on the target MySQL version after removing legacy settings.
- [ ] Measured performance under realistic concurrency and read/write ratios.
- [ ] Chose an alternative solution where repeated queries still require caching.
- [ ] Defined TTL, invalidation, and consistency requirements for the new cache.
- [ ] Verified that read-after-write flows, access privileges, and per-tenant/per-user data are never misserved.

The Query Cache is part of MySQL optimization history and remains worth understanding when working with legacy 5.7 systems. When moving to MySQL 8.0 or later, shift your approach: measure the workload, optimize queries, and choose caching at the layer appropriate to your data requirements.

## Official References

Historical behaviors in this article are cross-referenced against the MySQL 5.7 Reference Manual; removal boundaries are cross-referenced against MySQL 8.0 documentation and MySQL team announcements. Version status is recorded as of **19-11-2026**.

1. [MySQL 5.7 Reference Manual — The MySQL Query Cache](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache.html): role, general behavior, and deprecation/removal milestones.
2. [How the Query Cache Operates](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-operation.html): text matching, cache eligibility, privilege checks, and invalidation.
3. [Query Cache Configuration](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-configuration.html): configuration variables, ON/OFF/DEMAND modes, limits, and lock contention.
4. [Query Cache Status and Maintenance](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/query-cache-status-and-maintenance.html): Qcache counters, FLUSH, and RESET.
5. [MySQL 5.7 Release Notes — Changes in MySQL 5.7.20](https://dev.mysql.com/doc/relnotes/mysql/5.7/en/news-5-7-20.html): deprecation of the Query Cache.
6. [MySQL 8.0 Reference Manual — What Is New in MySQL 8.0](https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html): removed Query Cache components.
7. [MySQL 8.0: Retiring Support for the Query Cache](https://dev.mysql.com/blog-archive/mysql-8-0-retiring-support-for-the-query-cache/): rationale for removal and client/proxy caching alternatives.
8. [InnoDB Buffer Pool](https://dev.mysql.com/doc/refman/8.0/en/innodb-buffer-pool.html): distinguishing data/index page caching from query result caching.
9. [ProxySQL — Query Cache](https://proxysql.com/documentation/query-cache/): proxy-tier result caching, TTL configuration, and invalidation limits.
10. [MySQL 8.0 — EXPLAIN Statement](https://dev.mysql.com/doc/refman/8.0/en/explain.html): reading execution plans and using EXPLAIN ANALYZE.
11. [MySQL 8.0 — The Slow Query Log](https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html): locating slow queries to optimize after removing the Query Cache.
