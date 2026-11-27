# RESULT_CACHE, Suitability Criteria, and Data Dependencies in PL/SQL

Oracle PL/SQL can store a function's return value in the **server result cache** via the `RESULT_CACHE` clause. When the function is invoked again with the same parameters and none of the data it depends on has changed, Oracle can return the cached result without re-executing the function body. This mechanism is useful for relatively expensive lookups that are called repeatedly and depend on infrequently changing data.

Result caching is not a way to make every function faster. A function is suitable only when results can be safely reused across calls and sessions. If a function depends on package variables, current time, sequences, current user, or NLS/session context without passing those values explicitly as inputs, the cache can return contextually wrong results. If dependent tables change constantly, cache entries are invalidated frequently and management overhead can exceed benefits.

This lesson belongs to the **Advanced PL/SQL** topic of *Database Engine Relational Oracle*. It focuses on:

- How to declare and how the PL/SQL function result cache works.
- Suitability conditions, purity, and data dependencies.
- Cache keys, function parameters, and session-specific context.
- Table dependency tracking and automatic invalidation upon commit.
- Behavior within transactions, across multiple sessions, and in Oracle RAC.
- Differences between PL/SQL function result cache and SQL query result cache.
- Monitoring with DBMS_RESULT_CACHE and V$ views.
- Hands-on lab creating a function and observing cache hits and invalidation.

## 1. What Is the Result Cache?

The result cache is a shared memory area in the SGA for storing reusable results. With the PL/SQL function result cache, a function is marked `RESULT_CACHE` so Oracle manages results keyed by parameter values and data dependencies read by the function.

High-level execution flow:

~~~text
Caller invokes function(parameters)
              |
              v
       Build/find cache key
              |
       +------+------+
       |             |
    Cache hit     Cache miss
       |             |
       v             v
 Return cached    Execute function
 result           body and query data
       |             |
       |             v
       |          Store result
       |          if cacheable
       |             |
       +------+------+
              |
              v
         Return value
~~~

On a cache hit, Oracle returns the stored result. On a cache miss, the function runs normally; if the result and context qualify, Oracle stores the result for future calls to reuse.

### Cache Scope

- The cache resides in the database instance's SGA, not in a session's private PGA.
- Multiple sessions on the same instance can share cached results.
- Cache entries may be evicted/freed due to memory pressure, administration, or invalidation.
- Cached results are not durable data; never treat the cache as a persistent storage table.
- In Oracle RAC, the result cache is per-instance; each instance maintains its own cache region, and Oracle coordinates invalidations across instances when dependent data changes.

The result cache is a performance optimization. The function must still return accurate results per program semantics whenever the cache lacks an entry, is flushed, or is invalidated.

## 2. Declaring a Function with RESULT_CACHE

The `RESULT_CACHE` clause is placed in the function declaration, after the return type:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_rate;
END get_tax_rate;
/
~~~

This function looks up a tax rate by region code. When multiple sessions call `get_tax_rate('APAC')` and the underlying configuration data has not changed, Oracle can share the cached result.

### Calling the Function

~~~sql
SELECT get_tax_rate('APAC')
FROM dual;
~~~

Or from PL/SQL:

~~~sql
DECLARE
    l_rate NUMBER;
BEGIN
    l_rate := get_tax_rate('APAC');
    DBMS_OUTPUT.PUT_LINE(l_rate);
END;
/
~~~

The first call typically executes the function to populate a cache entry. Subsequent calls with the same parameters and valid dependencies can result in a cache hit. Do not rely on body execution counts in business logic; the result cache can be bypassed or entries can be evicted at any time.

### Functions in a Package

A public function can declare `RESULT_CACHE` in the package specification:

~~~sql
CREATE OR REPLACE PACKAGE tax_api AS
    FUNCTION tax_rate(
        p_region_code IN VARCHAR2
    ) RETURN NUMBER RESULT_CACHE;
END tax_api;
/
~~~

Implementation:

~~~sql
CREATE OR REPLACE PACKAGE BODY tax_api AS
    FUNCTION tax_rate(
        p_region_code IN VARCHAR2
    ) RETURN NUMBER RESULT_CACHE
    IS
        l_rate NUMBER;
    BEGIN
        SELECT tax_rate
        INTO l_rate
        FROM tax_configuration
        WHERE region_code = p_region_code;

        RETURN l_rate;
    END tax_rate;
END tax_api;
/
~~~

If the function is published in the specification, the implementation signature and attributes must match consistently. Private functions in the package body can also be declared result-cached when appropriate.

### RESULT_CACHE Is Not DETERMINISTIC

`DETERMINISTIC` is the author's assertion that a function returns the same result for identical inputs under its deterministic contract; Oracle does not automatically track every table queried by a function merely because that keyword is present. `RESULT_CACHE` is a mechanism for storing results and managing data dependencies for reuse. The two attributes serve different purposes; do not add both out of habit or treat them as synonyms.

## 3. Suitability Criteria: Results Must Be Safely Reusable

A function suited for result caching typically exhibits these traits:

- The same parameter set and same dependent data state must produce the same result.
- No side effects such as INSERT/UPDATE/DELETE, file writes, message sends, or external state changes.
- Does not rely on hidden session state unless represented in parameters/cache key.
- High enough computation or query cost to justify reuse.
- Called repeatedly while underlying dependent data changes relatively infrequently.
- Result sizes and key counts do not excessively consume cache memory.

### Good Fit Example

Functions looking up region codes, tax rates, product configuration, currency info, or slowly changing reference tables often benefit:

~~~sql
CREATE OR REPLACE FUNCTION get_country_name (
    p_country_code IN VARCHAR2
)
RETURN VARCHAR2
RESULT_CACHE
IS
    l_country_name countries.country_name%TYPE;
BEGIN
    SELECT country_name
    INTO l_country_name
    FROM countries
    WHERE country_code = p_country_code;

    RETURN l_country_name;
END get_country_name;
/
~~~

The function has an explicit input, reads a reference table, and returns a single value. If the countries table changes rarely and is queried frequently, result caching can reduce SELECT executions.

### Poor Fit Example: Time-Dependent Output

~~~sql
CREATE OR REPLACE FUNCTION current_time_text
RETURN VARCHAR2
RESULT_CACHE
IS
BEGIN
    RETURN TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF');
END current_time_text;
/
~~~

The output changes with invocation time despite having no parameters. The cache cannot treat a prior call's result as valid for a later call. Never mark functions like this `RESULT_CACHE`; call `SYSTIMESTAMP` directly or pass the timestamp as a parameter if caching a computation derived from that timestamp.

### Poor Fit Example: Side Effects

Functions meant to increment counters, write audit records, or update state should not use result caching:

~~~sql
CREATE OR REPLACE PROCEDURE increment_business_counter (
    p_new_value OUT NUMBER
)
IS
BEGIN
    UPDATE business_counter
    SET counter_value = counter_value + 1
    RETURNING counter_value INTO p_new_value;
END increment_business_counter;
/
~~~

This is a procedure because the operation has a side effect. A function with side effects is not a pure computation whose execution can be skipped on a cache hit. Use a procedure, sequence, or appropriate number-generation mechanism instead of result caching.

## 4. Parameters and Cache Keys

Oracle uses input parameter values to identify which cache entry a call can use. Therefore, any information that alters the output must appear in parameters or be governed by a dependency Oracle tracks.

### Parameters Must Represent All Logical Inputs

Example calculating tax-inclusive price by region:

~~~sql
CREATE OR REPLACE FUNCTION price_with_tax (
    p_net_amount IN NUMBER,
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_tax_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_tax_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN p_net_amount * (1 + l_tax_rate);
END price_with_tax;
/
~~~

The result depends on both net amount and region code, so both must be parameters. If you only passed the amount and read region from a package variable or session context, two sessions could match the same key while needing different results.

### IN Parameters Only, No OUT/IN OUT

Result-cached functions use input parameters to determine output. Do not design result-cached functions with OUT or IN OUT parameters; functions should return results via the RETURN value. If multiple values must be returned, use a supported record/collection or another API design, confirming datatype compatibility with your Oracle version.

### NULL Is Also an Input

If a parameter is nullable, define NULL semantics explicitly:

~~~sql
CREATE OR REPLACE FUNCTION get_discount_rate (
    p_customer_tier IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_rate
    FROM discount_tiers
    WHERE tier_code = p_customer_tier;

    RETURN l_rate;
END get_discount_rate;
/
~~~

If `p_customer_tier` is NULL, `tier_code = NULL` matches no rows because comparing with NULL yields UNKNOWN. Decide explicitly whether NULL means "no tier," "default tier," or invalid data, and handle it cleanly. The cache key reflects actual inputs; do not rely on implicit conversions or NLS to normalize parameters.

### Normalizing Inputs

If business rules treat region codes as case-insensitive, normalize before calling or inside the function with a clear rule:

~~~sql
FUNCTION get_region_rate(p_region_code IN VARCHAR2)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
    l_code VARCHAR2(30) := UPPER(TRIM(p_region_code));
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = l_code;

    RETURN l_rate;
END;
~~~

Variations like `'APAC'`, `'apac'`, and leading/trailing spaces create distinct cache keys even if the function normalizes them to the same code. Having callers normalize consistently beforehand avoids creating duplicate cache entries for equivalent keys. Never let normalization depend on NLS/session settings when sessions must share cached results.

## 5. Data Dependencies: What Does Oracle Track?

Function result caching is especially useful when functions query tables. Oracle tracks the data objects a function depends on and manages cached result validity against committed data changes.

Tax lookup function example:

~~~sql
CREATE OR REPLACE FUNCTION lookup_tax (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_tax_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_tax_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_tax_rate;
END lookup_tax;
/
~~~

When the function executes, Oracle detects that `TAX_CONFIGURATION` was queried. If a transaction modifies data in this table and COMMITs, cache entries depending on the modified data are invalidated so subsequent calls do not return stale values.

### Dependencies Are Tracked Automatically

For static SQL inside a function, Oracle identifies accessed tables/views and records dependencies. Dependency tracking lets the result cache know when source data has changed.

In new code, do not rely on `RELIES_ON` to manually declare every table as a default practice. Dependency tracking for function result caches is handled automatically by Oracle; `RELIES_ON` is legacy syntax from earlier Oracle releases and is deprecated in newer releases. When maintaining legacy systems, check the documentation for the exact version before modifying or removing that clause.

### Uncommitted Changes

Transaction A updates `TAX_CONFIGURATION` without committing. Transaction B still sees committed data per Oracle isolation and can continue using cache entries reflecting the committed state. Once A COMMITs, Oracle invalidates dependent results; subsequent calls recompute against the new data.

Within the same session modifying the dependent table, Oracle can bypass the result cache for functions depending on that table during the transaction so the session does not receive stale cached values instead of its own uncommitted changes. After COMMIT/ROLLBACK, caching resumes against the valid data state.

### Indirect Dependencies

A function may query a view or call other functions; dependencies can arise across an object chain. Understand dependencies at the level of underlying data accessed, not just table names appearing directly in the outermost function's source.

If a function uses dynamic SQL, synonyms, views, or calls other packages/functions, carefully verify actual dependency tracking for your Oracle version. Do not assume all dynamic or external data sources are tracked identically to a simple static SELECT.

### Things Not Automatically Treated as Table Dependencies

The result cache cannot infer hidden state in PL/SQL. For example:

- Package variables or other global state.
- Sequence NEXTVAL/CURRVAL.
- SYSDATE, SYSTIMESTAMP, or random values.
- SYS_CONTEXT, application context, or user identity.
- NLS settings, time zone, current schema, and session settings.
- Files, HTTP services, message queues, or external data sources.

If output depends on such a value, pass it as an explicit parameter when appropriate or do not use result caching. Never expect table invalidation to refresh state that is not a tracked data dependency.

## 6. Session-Specific Context and Shared Results

The PL/SQL function result cache can share results across sessions on the same instance. Consequently, functions must not implicitly depend on session identity or session-specific settings.

### Dangerous Example: Current User

~~~sql
CREATE OR REPLACE FUNCTION current_user_discount
RETURN NUMBER
RESULT_CACHE
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM user_discounts
    WHERE username = SYS_CONTEXT('USERENV', 'SESSION_USER');

    RETURN l_discount;
END current_user_discount;
/
~~~

Output depends on `SESSION_USER`, yet the function takes no parameters. If shared caching treats the output as keyed only by an empty parameter list, another user may require a different result. Never design such a function as a parameterless result-cached function.

### Make Context an Explicit Parameter

~~~sql
CREATE OR REPLACE FUNCTION user_discount (
    p_username IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM user_discounts
    WHERE username = p_username;

    RETURN l_discount;
END user_discount;
/
~~~

Now `username` is part of the input. However, passing a username does not solve authorization by itself: the caller must still be authenticated and authorized to request that data. Never use the result cache as a substitute for access checks.

### NLS, Timezone, and Formatting

A function returning strings formatted according to `NLS_DATE_LANGUAGE` or `NLS_NUMERIC_CHARACTERS` can yield different results across sessions despite identical parameters. Safer practices are:

- Return native DATE/NUMBER values and let the caller format at the presentation layer.
- Or pass required locale/timezone/format as explicit parameters.
- Avoid reading hidden session settings inside result-cached functions.

### Tenants and Application Context

In multi-tenant applications, functions reading a tenant ID from `SYS_CONTEXT` risk cross-tenant cache leakage if context is not captured properly in the key or isolated by the caching mechanism. Pass tenant ID as an explicit parameter and verify caller authorization; never treat application context as an automatic table dependency.

### Session Context Can Change Within the Same Session

Connection pools reuse sessions across requests. If package variables or application contexts change per request, a result-cached function reading them risks returning wrong results if those values are not reflected in parameters/cache identity. Prefer explicit parameters and clean up session state.

## 7. Transactions, Commit, and Invalidation

The result cache must reflect committed data visible to the current transaction. Oracle coordinates the cache with transactions so stale values are not served after dependent data changes.

### Modifying Dependent Data

Suppose function `LOOKUP_TAX` reads `TAX_CONFIGURATION`:

~~~sql
SELECT lookup_tax('APAC') FROM dual;
~~~

After the first call, the result may be cached. When a transaction updates:

~~~sql
UPDATE tax_configuration
SET tax_rate = 0.09
WHERE region_code = 'APAC';
~~~

Before COMMIT, that transaction sees its own changes per read consistency; other sessions still see previously committed data. When the transaction COMMITs, cache entries depending on the committed changes are invalidated. The next call must recompute from the new data.

### ROLLBACK

If the transaction rolls back, the changes never become committed data. Oracle does not need the cache to reflect an uncommitted value. Cache entries valid for the pre-transaction data state can continue to be used after rollback.

### Session Performing DML on Dependencies

When a session modifies a table that a result-cached function depends on, the result cache can be bypassed for calls to that function during the transaction to avoid returning cached values that ignore the session's uncommitted changes. After COMMIT, old cache entries are invalidated; after ROLLBACK, the old data remains the committed state.

Never use the cache as a way to read another session's uncommitted data. The result cache respects Oracle transaction consistency, not a channel for sharing uncommitted changes.

### Invalidation Can Affect Multiple Entries

A single modified table may be a dependency for many distinct results, such as multiple region codes in the same configuration table. Oracle invalidates cached results depending on the modified object according to its dependency management; the exact scope can be broader than a single key depending on object/dependency granularity. Hence, frequently updated tables can sharply reduce hit ratios.

### DDL and Structural Changes

Metadata changes on dependent objects can invalidate objects or related result cache entries. After DDL deployments, recompilations, or schema changes, monitor object validity and the result cache; do not assume older cache entries remain valid.

## 8. Oracle RAC and Multiple Instances

In RAC, each instance has its own SGA and result cache. A cache entry created on instance 1 is not a memory region directly read by instance 2. Each instance builds its own cache from calls executed on that instance.

When a transaction on one instance commits changes to data that result caches on other instances depend on, Oracle coordinates invalidations to prevent serving stale results. This coordination carries communication and synchronization overhead; workloads constantly updating dependencies can reduce cache effectiveness on RAC.

### Operational Implications

- Do not assume a cache hit on instance A implies a cache hit on instance B.
- The same function may be recomputed independently on each instance.
- Committing DML on one instance can invalidate dependent cache entries on other instances.
- Monitor per-instance statistics and memory when analyzing RAC.
- Account for service routing/load balancing because requests may land on different instances.

### Do Not Use the Result Cache as a Shared Data Store

The result cache is a performance optimization and can be flushed, invalidated, or aged out. Data requiring durability or cross-instance synchronization belongs in tables or an appropriate persistent store.

## 9. When Is the Result Cache Bypassed or Ineffective?

Declaring `RESULT_CACHE` does not guarantee every call is a cache hit. Oracle may skip caching or not store results in situations such as:

- The function depends on session state or values not fully represented in parameters.
- The function has side effects or uses operations incompatible with result caching.
- The current session has uncommitted modifications to data the function depends on.
- The result cache is disabled/bypassed at the instance or session level.
- The cache entry was invalidated due to dependency changes.
- The cache entry was evicted due to memory pressure or cache management policies.
- Parameter/return datatypes or implementation constructs are unsupported by result caching in the current version.
- The function raises an exception rather than returning a normal reusable value.

### Never Rely on How Many Times the Function Body Runs

Never write business logic assuming "the function executes only once." Cache entries can miss, be evicted, bypassed, or invalidated at any moment. The function must always produce correct results upon re-execution.

### Result Cache Does Not Replace Materialized Views

If you need to store and manage a large derived dataset refreshed on a schedule or on commit, a materialized view may be more appropriate. Function result caching suits function outputs keyed by parameters and dependencies; it is not an aggregated table with its own schema and query plan.

### Result Cache Does Not Replace Indexes

If a function is slow because its internal query lacks a proper index, caching may help repeated calls, yet cache misses remain slow. Optimize SQL, indexes, statistics, and access paths before evaluating caching.

## 10. Size, Change Frequency, and Cache Effectiveness

The result cache consumes SGA memory. Large results, many rarely reused keys, or frequently changing dependencies can consume memory while yielding few hits.

Factors to evaluate:

- **Reuse:** how frequently is the same key invoked?
- **Computation cost:** how much CPU/I/O does executing the function and internal SQL take?
- **Invalidation frequency:** how often do dependent tables change?
- **Result size:** how much memory does each cached result occupy?
- **Key cardinality:** how many distinct parameter combinations can occur?
- **Concurrency:** do multiple sessions invoke the same key concurrently?
- **Cache pressure:** are result cache entries continuously evicted?

Examples:

| Function Type | Typical Suitability | Reason |
| --- | --- | --- |
| Country name lookup by code | High | Rarely changes, many repeated calls, small result. |
| Tax rate lookup by region | Potentially high | Depends on infrequently modified config table. |
| Current account balance calculation | Low | Data changes frequently; freshness is critical. |
| Getting current timestamp | Unsuitable | Result depends on invocation time. |
| Generating next sequence number | Unsuitable | Side effects / sequence semantics. |
| Very cheap arithmetic expression | Usually low | Cache lookup may cost more than the computation. |
| Large report over millions of unique parameters | Usually low | High key cardinality and result size, low reuse. |

### Measure Before and After

Do not measure only the elapsed time of a single call. Compare:

- Total function invocations.
- Actual function body executions.
- Cache hit/miss counts or result cache statistics.
- Logical reads/physical reads and CPU.
- Invalidation rate after DML.
- Memory used by the result cache.
- Latency on warm cache versus cold cache.

Test with data volumes, concurrency, and update rates close to production. A single-session, single-key microbenchmark with no DML can exaggerate benefits.

## 11. PL/SQL Function Result Cache vs. SQL Query Result Cache

Oracle has two result cache mechanisms that are easily confused:

| Criterion | PL/SQL Function Result Cache | SQL Query Result Cache |
| --- | --- | --- |
| Marker | `RESULT_CACHE` clause on function | `/*+ RESULT_CACHE */` hint or query result cache config |
| Cached item | Function RETURN value per parameters | Result set of a SQL query |
| Primary cache key | Function identity and parameter values | Query/result semantics and related factors |
| Dependencies | Data accessed by function and related dependencies | Data objects read by query |
| Scope | Instance SGA result cache | Instance SGA result cache |
| Use when | Multiple callers invoke the same function with repeated inputs | Repeated runs of the same query have reusable results |

### SQL Query Result Cache

You can instruct Oracle to cache a query result:

~~~sql
SELECT /*+ RESULT_CACHE */
       region_code,
       tax_rate
FROM tax_configuration
WHERE region_code = 'APAC';
~~~

Or control query result cache behavior via `RESULT_CACHE_MODE` (MANUAL/FORCE), depending on system configuration. This caches SQL query results; it does not mark a PL/SQL function as result-cached.

### Function Result Cache Is Declared on the Function

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate(p_region_code VARCHAR2)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_configuration
    WHERE region_code = p_region_code;
    RETURN l_rate;
END;
/
~~~

Callers can invoke the function from PL/SQL or SQL. The cache manages the function's RETURN value by parameters and dependencies.

### Do Not Misuse RESULT_CACHE_MODE

Setting `RESULT_CACHE_MODE=FORCE` is not a substitute for the `RESULT_CACHE` clause on a function. If you want a function managed as PL/SQL result-cached, declare that attribute directly on the function. Conversely, SQL query result caching is controlled by its corresponding hint and parameter.

### Can Both Mechanisms Be Combined?

A query can invoke a result-cached PL/SQL function, and the query itself might also be considered for SQL query result caching. However, stacking multiple cache layers complicates diagnosing invalidations, hit ratios, and memory. Pick caching at the right layer, measure, and combine only when there is a clear benefit.

## 12. Monitoring with DBMS_RESULT_CACHE

The `DBMS_RESULT_CACHE` package provides administrative and diagnostic APIs for the result cache. Execution privileges and certain administrative operations depend on user grants and Oracle version.

### Check Cache Status

~~~sql
SELECT DBMS_RESULT_CACHE.STATUS
FROM dual;
~~~

`STATUS` returns the result cache state per version and configuration. Another common observation method is querying the dynamic performance views covered next.

### Memory Report

~~~sql
BEGIN
    DBMS_RESULT_CACHE.MEMORY_REPORT;
END;
/
~~~

`MEMORY_REPORT` prints result cache memory usage via the package output. Enable `DBMS_OUTPUT` to view it in SQL Developer or SQL*Plus.

### Bypassing the Cache

You can request bypassing the result cache at the session or system level using the appropriate API:

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => TRUE,
        session => TRUE
    );
END;
/
~~~

To re-enable for the session:

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => FALSE,
        session => TRUE
    );
END;
/
~~~

`BYPASS` is a diagnostic or administrative tool, not a fix for broken dependency tracking. When bypassed, the function still runs and may be slower; record state before and after testing.

### Flushing the Cache

~~~sql
BEGIN
    DBMS_RESULT_CACHE.FLUSH;
END;
/
~~~

`FLUSH` frees result cache entries per API scope and user privileges. This affects the entire workload using the cache on the instance; never run it casually in production just to "refresh" one function. When invalidating a specific object is needed, inspect the `INVALIDATE` API and check dependencies first.

### Invalidating an Object

`DBMS_RESULT_CACHE` provides an `INVALIDATE` API to invalidate cache entries associated with an object by owner/name. Syntax and privileges can vary by release; inspect the target database's package specification before running in operational environments.

## 13. Monitoring via V$ Views

Dynamic performance views reveal what entries exist in the cache, their dependencies, and operational statistics. Typically `SELECT_CATALOG_ROLE` or explicit view grants are required.

### V$RESULT_CACHE_OBJECTS

~~~sql
SELECT cache_id,
       type,
       status,
       name,
       creation_timestamp,
       block_count,
       scan_count,
       pin_count
FROM v$result_cache_objects
ORDER BY creation_timestamp DESC;
~~~

This view can display result objects and dependency objects. `TYPE`/`STATUS` help distinguish published results, dependencies, or entries in other states. Exact columns may vary by version; check `DESC V$RESULT_CACHE_OBJECTS` on your actual database.

### Finding Objects Related to a Function

~~~sql
SELECT cache_id,
       type,
       status,
       name,
       creation_timestamp
FROM v$result_cache_objects
WHERE UPPER(name) LIKE '%GET_TAX_RATE%'
ORDER BY creation_timestamp DESC;
~~~

Displayed names may include schema, package, or other identifying details. Do not rely solely on `LIKE` to conclude no cache entry exists; inspect full objects and dependencies when needed.

### V$RESULT_CACHE_STATISTICS

~~~sql
SELECT name, value
FROM v$result_cache_statistics
ORDER BY name;
~~~

The statistics view reports metrics related to memory, entry creation/invalidation counts, and cache activity depending on version. Consult version-specific documentation for metric names and meanings; do not assume one fixed threshold across all systems.

### V$RESULT_CACHE_MEMORY

~~~sql
SELECT *
FROM v$result_cache_memory;
~~~

This view shows memory blocks/regions used by the result cache. Use `DESC` to view columns available on the running release.

### V$RESULT_CACHE_DEPENDENCY

~~~sql
SELECT *
FROM v$result_cache_dependency;
~~~

The dependency view lets you trace links between result objects and the data objects they depend on. Column structure may vary by version; inspect `DESC` before writing fixed operational reports.

### Comparing Before and After DML

A useful experiment is:

1. Call the function twice with identical parameters.
2. Observe result/dependency objects and statistics.
3. UPDATE the dependent table and COMMIT.
4. Call the function again.
5. Observe the old entry invalidated and a new entry created as the function re-executes.

Do not look at a single hit/miss column alone. Combine execution time, body execution count, invalidation count, memory usage, and DML volume on dependent tables.

## 14. Design Rules and Unsuitable Conditions

Before adding `RESULT_CACHE`, confirm the following conditions:

| Question | If the Answer Is "No" |
| --- | --- |
| Do the same parameters and dependent data always yield the same result? | Do not use result caching for that function. |
| Are all inputs affecting the output either parameters or tracked dependencies? | Add parameters or remove hidden state. |
| Is the function free of side effects? | Use a procedure or a different API design. |
| Is the function free of hidden session state/NLS/user context dependencies? | Pass context explicitly or do not cache. |
| Does source data change infrequently enough for entries to be reused? | Result caching may be ineffective. |
| Are the same keys invoked frequently enough? | Cache lookup/memory cost may not pay off. |
| Are result sizes and key counts bounded? | Reduce cardinality/result size or choose another cache. |
| Is the function still correct on a cache miss or cache flush? | Fix the function; caching must never be required for correctness. |

### Purity Rules

A result-cached function must be designed as a side-effect-free computation. Avoid:

- DML or transaction control.
- Mutating package variables or global state.
- Writing files, sending messages, or calling external APIs.
- Reading sequences or time-varying values.
- Relying implicitly on current user, application context, locale, or timezone.
- Depending on prior invocation order or state left by another request.

Oracle may enforce compile-time/runtime restrictions in certain cases, but the designer remains responsible for safe semantics. Never assume a function is suitable simply because the compiler raises no error.

### Datatypes and Function Signatures

Function result caching has restrictions on parameter/return datatypes and function forms depending on version. Safely prefer scalar SQL types and PL/SQL types documented as supported in your version; avoid LOB, LONG, REF CURSOR, or complex types unless support is confirmed. Functions should not use OUT/IN OUT parameters. If multiple values must be returned, consider supported records/collections or a different API, and test caching on the target release.

### Functions Raising Exceptions

If a function raises an exception instead of returning normally, the caller receives the exception per PL/SQL semantics. Never design logic assuming exceptions are cached like normal return values. Handle `NO_DATA_FOUND`, `TOO_MANY_ROWS`, and data errors per business rules; caching optimizes only valid, reusable return values.

### Dynamic SQL and Indirect Data Sources

When a function uses `EXECUTE IMMEDIATE`, mutable synonyms, database links, or external data sources, verify dependency tracking in your Oracle release and specific execution path. Do not assume dynamic SQL dependencies are tracked identically to static SELECT statements. If you cannot guarantee Oracle invalidates entries when source data changes, do not use result caching or redesign so dependencies are explicit.

### Functions with DEFINER/INVOKER Rights

A function may be compiled with `AUTHID DEFINER` or `AUTHID CURRENT_USER`. If results depend on privileges, current schema, or caller identity, carefully evaluate cache sharing across sessions. Never cache sensitive data under a key that omits proper security context; prefer explicit inputs and independent authorization checks.

## 15. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Function gets no cache hits | Parameters constantly vary, cache bypassed, entries invalidated, or aged out | Check key reuse, bypass status, dependent DML, and statistics. |
| Stale results after table changes | Dependency not tracked as expected or external source used | Inspect dependency view, dynamic SQL, and commit status; avoid hidden state. |
| Function returns different values across users/sessions | Function reads session context, NLS, or package variables | Pass context as parameters or remove RESULT_CACHE. |
| Cache invalidated constantly | Dependent table receives frequent DML | Target slowly changing reference data or disable caching. |
| Cache memory grows with low-reuse entries | High key cardinality or large result sizes | Reduce cardinality, cache small values, measure reuse, tune SGA. |
| Function re-runs after FLUSH | Cache was cleared | Expected behavior; function must work properly on cache miss. |
| First call is slow | Cache miss must run SQL and populate entry | Measure both cold and warm paths; tune underlying query. |
| Function result caching fails with datatype | Unsupported datatype or invalid signature | Check compile errors and version docs; use supported types. |
| Wrong results with package state | Package variables are not tracked like table dependencies | Remove hidden state or pass values as parameters. |
| Cache hit on one instance, miss on another | RAC maintains per-instance caches | Measure per instance and account for cache warm-up/invalidation. |
| DML session misses new data via function | Function result cache misused mid-transaction or uncommitted dependency | Check session DML, commit/rollback, and cache bypass/invalidation. |
| ORA-04068 or package invalidation confused with cache miss | Package state and result cache are separate mechanisms | Diagnose package validity separately from result cache objects. |

### Recommended Diagnostic Workflow

1. Confirm the function actually declares `RESULT_CACHE` and compiles `VALID`.
2. Call the same function with identical parameters in the same session.
3. Inspect cache status, objects, and statistics.
4. Check whether dependent tables undergo frequent DML/COMMITs.
5. Check whether the function reads package state, `SYS_CONTEXT`, NLS, time, or external sources.
6. Test `BYPASS` in a test session to compare outputs and latency.
7. Compare cold/warm caches and multiple sessions/instances.
8. Retain `RESULT_CACHE` only if results are correct and the workload genuinely improves.

## 16. Comprehensive Lab Exercise

Perform this lab in a learning schema with `CREATE TABLE` and `CREATE FUNCTION` privileges. DDL statements issue implicit commits in Oracle; do not run on real production/business configuration tables.

### Step 1: Create the Tax Configuration Table

~~~sql
CREATE TABLE lab_tax_configuration (
    region_code VARCHAR2(20)
        CONSTRAINT pk_lab_tax_configuration PRIMARY KEY,
    tax_rate NUMBER(8,5) NOT NULL
);

INSERT INTO lab_tax_configuration VALUES ('APAC', 0.08000);
INSERT INTO lab_tax_configuration VALUES ('EMEA', 0.20000);
COMMIT;
~~~

### Step 2: Create the Result-Cached Function

~~~sql
CREATE OR REPLACE FUNCTION lab_tax_rate (
    p_region_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate lab_tax_configuration.tax_rate%TYPE;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM lab_tax_configuration
    WHERE region_code = p_region_code;

    RETURN l_rate;
END lab_tax_rate;
/
~~~

Verify compilation:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_TAX_RATE';

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'LAB_TAX_RATE'
ORDER BY sequence;
~~~

### Step 3: Call Multiple Times with the Same Parameters

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('EMEA'));
    DBMS_OUTPUT.PUT_LINE(lab_tax_rate('APAC'));
END;
/
~~~

The `'APAC'` calls share the same parameter and dependency data, providing cache hit opportunities after the initial execution. `'EMEA'` is a separate key. Returned values must be identical regardless of hit or miss.

### Step 4: Observe Cache Objects and Statistics

~~~sql
SELECT cache_id, type, status, name, creation_timestamp
FROM v$result_cache_objects
ORDER BY creation_timestamp DESC;

SELECT name, value
FROM v$result_cache_statistics
ORDER BY name;
~~~

If you lack privileges on `V$` views, ask a DBA for appropriate grants or use authorized administrative tools. Entry names/details depend on Oracle version and object display formatting; do not expect one fixed cache name.

### Step 5: Modify Dependency and COMMIT

~~~sql
UPDATE lab_tax_configuration
SET tax_rate = 0.09000
WHERE region_code = 'APAC';

COMMIT;

SELECT lab_tax_rate('APAC')
FROM dual;
~~~

After COMMIT, cached results depending on the old APAC data are invalidated. The next call recomputes and returns 0.09. Inspect `V$RESULT_CACHE_OBJECTS` and statistics again.

### Step 6: Test ROLLBACK

~~~sql
UPDATE lab_tax_configuration
SET tax_rate = 0.10000
WHERE region_code = 'APAC';

SELECT lab_tax_rate('APAC')
FROM dual;

ROLLBACK;

SELECT lab_tax_rate('APAC')
FROM dual;
~~~

The session modifying the dependency may bypass the cache within its transaction so it sees its own changes. After ROLLBACK, committed data remains 0.09. Observe actual behavior rather than assuming the cache is always used inside a DML transaction.

### Step 7: Test Two Sessions

**Session A:**

~~~sql
SELECT lab_tax_rate('APAC') FROM dual;
~~~

**Session B:**

~~~sql
SELECT lab_tax_rate('APAC') FROM dual;
~~~

Two sessions on the same instance can share valid result cache entries. Next, Session A updates the tax rate and COMMITs; Session B calls the function again to observe invalidation and recomputation against the new data.

### Step 8: Compare with a Session-Dependent Function

Do not implement a function depending on `SESSION_USER` as a parameterless result-cached function. Design a function with explicit username/tenant parameters, then enforce authorization independently. Discuss why cache keys must distinguish inputs that alter output.

### Step 9: Bypass in a Test Session

~~~sql
BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => TRUE,
        session => TRUE
    );
END;
/

SELECT lab_tax_rate('APAC') FROM dual;

BEGIN
    DBMS_RESULT_CACHE.BYPASS(
        bypass_mode => FALSE,
        session => TRUE
    );
END;
/
~~~

The bypass test affects only the current session per the `session` parameter. Record timing and outputs before/after; never use bypass to mask dependency bugs.

### Step 10: Clean Up

~~~sql
DROP FUNCTION lab_tax_rate;
DROP TABLE lab_tax_configuration PURGE;
~~~

Run only after finishing the lab when objects are no longer needed. DROP is DDL and issues an implicit commit.

## 17. Self-Check Questions

1. **What does RESULT_CACHE on a PL/SQL function do?** Allows Oracle to store and reuse the RETURN value keyed by parameters and data dependencies.
2. **Where does the cache live?** In the database instance's SGA result cache.
3. **Do multiple sessions on the same instance share the cache?** Yes, when entries are valid and the function qualifies.
4. **Are identical parameters always enough to return the same result?** Only when all data/context affecting output are also identical and dependencies are properly managed.
5. **Why shouldn't a function read hidden package variables?** Package state is not a tracked cache-key input like parameters; other sessions may hold different values.
6. **Should a result-cached function have side effects?** No; cache hits can skip body execution.
7. **Are OUT/IN OUT parameters suitable?** No; use IN parameters and the RETURN value.
8. **When does Oracle track changes to dependent tables?** Committed DML on dependent objects can invalidate related cache entries.
9. **Does ROLLBACK make uncommitted values the new dependency state?** No; rolled-back changes never become committed data.
10. **How should RELIES_ON be used in new code?** Do not use it by default; it is a legacy/deprecated clause in newer releases, and dependencies are tracked automatically for eligible SQL.
11. **Should functions reading SYSDATE or sequences be cached?** No, because output depends on state changing outside parameters.
12. **What must be watched when a function reads SESSION_USER or tenant context?** Pass context as an explicit parameter or omit result caching; authorization must still be checked separately.
13. **Does RAC share a single cache across all instances?** No; each instance has its own cache and Oracle coordinates invalidation.
14. **How does the PL/SQL function result cache differ from the SQL query result cache?** One caches a function's RETURN value; the other caches a SQL query's result set.
15. **Does RESULT_CACHE_MODE replace the function's RESULT_CACHE clause?** No; that parameter controls SQL query result caching, whereas functions must declare their own attribute.
16. **Are cache hits guaranteed?** No; entries can miss, be bypassed, invalidated, or aged out.
17. **Why do frequently updated dependency tables make caching ineffective?** Related entries are repeatedly invalidated before being reused.
18. **Which view shows cache objects?** V$RESULT_CACHE_OBJECTS.
19. **Which view shows cache statistics?** V$RESULT_CACHE_STATISTICS.
20. **Why measure both cold and warm paths?** The first call must compute the result; later calls may hit. Both occur in real workloads.

PL/SQL `RESULT_CACHE` suits side-effect-free functions with explicit inputs, stable data dependencies, and repeated invocations. Oracle automatically tracks eligible data dependencies and invalidates results after committed changes. Functions must not depend on hidden package state, time, sequences, NLS, user, or application context. Distinguish the function result cache from the SQL query result cache, measure hits/misses and invalidations on real workloads, and ensure the function remains correct whenever the cache misses or is flushed.
