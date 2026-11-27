# PGA, SGA, ASMM/AMM, and Memory Trade-offs with the Operating System

Oracle Database uses memory to share data and metadata across sessions while providing private working space for each server process and background process. The two most important areas are the **SGA (System Global Area)** and **PGA (Program Global Area)**. The SGA is shared memory for an instance; the PGA is private memory bound to a process. How these two areas are allocated directly affects cache hits, parsing, sorts/hashes, TEMP I/O, concurrent session capacity, and remaining RAM for the operating system.

Oracle offers three common memory management methods. Manual memory management requires the DBA to size each area explicitly. ASMM (Automatic Shared Memory Management) automatically tunes SGA components within `SGA_TARGET`, while PGA is managed separately. AMM (Automatic Memory Management) dynamically manages combined SGA and instance PGA via `MEMORY_TARGET`. Each approach carries distinct trade-offs, especially when hosts use Linux HugePages, shared memory, containers, or run multiple instances.

A good configuration is not simply assigning as much RAM as possible to Oracle. Both SGA and PGA compete for physical RAM against the kernel, filesystem cache, agents, backups, ASM, other databases, and host applications. If Oracle starves the operating system of RAM, swapping or memory reclamation can slow down the entire system even though the database appears generously provisioned.

After this lesson, you will be able to:

- Distinguish SGA, PGA, UGA, and Oracle process memory.
- Identify the main SGA components and their purposes.
- Understand PGA work areas for sorts, hash joins, and SQL operations.
- Explain optimal, one-pass, and multi-pass work area execution.
- Compare manual memory management, ASMM, and AMM.
- Understand `SGA_TARGET`, `SGA_MAX_SIZE`, `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT`, `MEMORY_TARGET`, and `MEMORY_MAX_TARGET`.
- Size memory according to workload, concurrency, and actual host RAM.
- Understand trade-offs between SGA/PGA and the OS, swap, HugePages, and `/dev/shm`.
- Monitor memory using dynamic performance views and advisors.
- Diagnose TEMP spills, `ORA-04031`, `ORA-04036`, `ORA-00845`, and memory pressure.
- Plan memory parameter changes with measurements and rollback procedures.

> Mechanisms and parameters may vary by Oracle release, platform, RAC, CDB/PDB, and OS configuration. Examples use a simplified instance for illustration; check the Database Reference/Administrator's Guide for your exact version before making production changes.

## 1. Overview of Oracle Memory

### 1.1. The Two Core Areas

An Oracle instance uses two main memory regions:

| Region | Scope | Primary Purpose |
| --- | --- | --- |
| SGA | Shared among processes of an instance | Caches database blocks, SQL/PLSQL, metadata, redo, and shared structures |
| PGA | Private to each Oracle process | Stack, session/process-private data, and SQL work areas |

When a session runs SQL, its server process uses the SGA to access shared data/caches and uses the PGA for execution-private data. A large sort or hash join can require substantial PGA. Multiple sessions running such operations concurrently cause total PGA to scale with concurrency.

### 1.2. Oracle Instance and Database

A database is the collection of datafiles, control files, online redo logs, and related files. An instance consists of memory structures (notably the SGA) and background processes. Many sessions can connect to one instance; in RAC, each instance has its own SGA and instances coordinate access to the shared database via cluster mechanisms.

The SGA is not a single shared memory area across all databases on a host. Each instance has its own SGA. PGA is likewise allocated to processes belonging to their respective instance.

### 1.3. Simplified Memory Flow

```text
APPLICATION / SESSION
        |
        v
ORACLE SERVER PROCESS
        |
        +------ Process-private PGA
        |         - stack and process state
        |         - private/session work
        |         - sort/hash work area
        |
        v
Instance-shared SGA
        |
        +-- Database Buffer Cache
        +-- Shared Pool
        +-- Redo Log Buffer
        +-- Large Pool / Java Pool / Streams Pool
        |
        v
DATAFILES / REDO LOGS / TEMPFILES
```

### 1.4. Why DBAs Must Manage Both SGA and PGA

Increasing SGA can reduce physical reads or hard parses if the workload benefits from caching, but reduces RAM left for PGA and the OS. Increasing PGA can reduce sort/hash spills to TEMP, but can starve the host of memory when many processes run concurrently.

Looking solely at database metrics, a DBA might raise a parameter and see one query speed up while the OS starts swapping or another workload degrades. Memory tuning must always span from the instance to the entire host.

## 2. SGA — System Global Area

### 2.1. Characteristics

The SGA is shared memory accessed by Oracle processes of the same instance. The SGA is normally allocated at instance startup, and certain components can be resized online depending on configuration and release.

The SGA holds shared structures to cut I/O, reduce parsing, and coordinate instance activity. SGA size is governed by parameters such as `SGA_TARGET`, `SGA_MAX_SIZE`, or `MEMORY_TARGET` depending on the management mode.

### 2.2. Database Buffer Cache

The buffer cache holds copies of database blocks read from datafiles. When a session needs a block, Oracle can locate it in the cache rather than reading from storage again.

The buffer cache helps:

- Reduce physical I/O for frequently re-accessed blocks.
- Hold modified blocks in memory before DBWn writes them to datafiles.
- Serve consistent reads via undo/versioning mechanisms.
- Cache both index blocks and table blocks.

The buffer cache is not permanent storage. Datafiles remain persistent storage; checkpoints and DBWR write dirty buffers per Oracle mechanisms.

Do not judge the buffer cache solely by cache hit ratio. Some physical reads are normal, direct path reads bypass the buffer cache, and raising the cache hit ratio may not reduce response time if the workload is bound by CPU, latches/mutexes, or other I/O.

### 2.3. Shared Pool

The shared pool holds shared structures, prominently:

- Library cache: cached SQL cursors, PL/SQL program units, and executable objects.
- Data dictionary cache: metadata about objects, users, privileges, columns, and database structure.
- Other control/metadata structures supporting parsing and execution.

The shared pool plays a major role in hard parsing, cursor sharing, PL/SQL, and dictionary lookups. An undersized shared pool or fragmentation/allocation pressure can contribute to `ORA-04031`. However, raising `shared_pool_size` alone cannot fix continuous SQL parsing, literal SQL without bind variables, or application cursor leaks.

### 2.4. Redo Log Buffer

The redo log buffer holds redo entries describing changes to be logged. LGWR writes redo from the buffer to online redo logs according to internal conditions and mechanisms.

The redo buffer is not a cache for table/index data. It serves durability/recovery and coordinates with COMMITs. Do not arbitrarily raise `LOG_BUFFER` assuming it improves every workload; sizing and behavior depend on release, workload, and Oracle's automatic management of certain aspects.

### 2.5. Large Pool

The large pool provides allocation space for large or shared operations, such as:

- Shared server UGA (when appropriately configured).
- Parallel execution message buffers.
- Certain RMAN/I/O and backup operations.

The large pool prevents eligible large allocations from putting pressure on the shared pool. Not every large operation automatically uses the large pool; behavior depends on configuration and features.

### 2.6. Java Pool and Streams Pool

The Java pool serves in-database Java execution when used. The Streams pool supports Oracle Streams and certain capture/apply or integrated data-processing features depending on release.

If the corresponding features are unused, demand for these two pools may be minimal. ASMM can adjust several of these components if automatically managed and unconstrained by configured minimums.

### 2.7. Fixed SGA and Other Components

The SGA also includes the fixed SGA and other structural regions. Some components are not dynamically resized like regular pools. Total SGA is not merely the sum of familiar pools seen in a single parameter list; check `V$SGAINFO`, `V$SGASTAT`, and corresponding views for your release.

### 2.8. Inspecting SGA Sizes

```sql
SELECT name, value
FROM v$sgainfo
ORDER BY name;

SELECT component, current_size, min_size, max_size,
       user_specified_size, oper_count
FROM v$sga_dynamic_components
ORDER BY component;
```

`V$SGAINFO` gives high-level SGA overview data; `V$SGA_DYNAMIC_COMPONENTS` displays current sizes and resize history of dynamic components. Some columns/views may vary by version.

## 3. PGA — Program Global Area

### 3.1. Characteristics

The PGA is memory private to an Oracle process, not shared like the SGA. Server processes use PGA to hold private data and state while servicing sessions/requests. Background processes also have their own PGAs.

Instance-total PGA is the sum of allocations across many processes, so it can fluctuate rapidly with active session counts and running workloads.

### 3.2. Common Components

PGA can contain:

- Private SQL areas and associated execution state.
- Session/process-private data.
- Process stack space.
- SQL work areas for sorts, hash joins, bitmap merges/creations, and other operations.
- Private allocations used by Oracle features or code.

Not all PGA components can shrink or adjust automatically like work areas. Some PGA is untunable or freed only along the process/call lifecycle.

### 3.3. PGA Scales with Process Count

Under dedicated server, each session typically maps to one server process. If 300 concurrent sessions all perform heavy sorts/hashes, total PGA can be dramatically higher than when only 30 sessions run.

PGA sizing must therefore account for concurrency and simultaneous workloads, not just a single query running in isolation.

### 3.4. PGA Is Not TEMP

PGA is memory; TEMP is storage in the temporary tablespace. When a work area lacks sufficient memory, Oracle can spill intermediate data to TEMP. This allows processing datasets larger than memory, at the cost of I/O and slower query execution.

TEMP does not replace PGA, and enlarging TEMP does not speed up sorts/hashes if memory pressure is the bottleneck.

## 4. UGA and Dedicated/Shared Server

### 4.1. What Is UGA?

The UGA (User Global Area) holds session state such as session metadata, package state, cursor/session data, and user-session structures. Where the UGA resides depends on the server architecture.

### 4.2. Dedicated Server

With dedicated server, one server process serves one session at a time. The UGA typically resides inside that server process's PGA. Thus, session state increases the corresponding process's PGA.

### 4.3. Shared Server

With shared server, many sessions share a pool of shared server processes on a turn-by-turn basis. The UGA must persist independently of whichever process handles a request, so it is usually allocated in the SGA (in the large pool if configured appropriately, otherwise in the shared pool).

This changes memory accounting: you cannot multiply full UGA as private PGA per dedicated process.

### 4.4. Comparison

| Architecture | Typical UGA Location | Impact |
| --- | --- | --- |
| Dedicated server | Server process's PGA | PGA grows with session/process count |
| Shared server | SGA, preferring large pool when appropriate | Session state must be factored into shared memory |

Shared server architecture benefits high session counts, though it does not suit all workloads. Application-tier connection pooling is also a vital mechanism for reducing concurrent database sessions.

## 5. PGA Work Areas and TEMP Spills

### 5.1. What Is a Work Area?

A work area is a PGA memory region used by SQL operations that process intermediate datasets. Examples:

- Sorts for `ORDER BY`, `GROUP BY`, and `DISTINCT`.
- Hash joins.
- Hash aggregations.
- Bitmap merges/creations.

Work area sizing determines whether an operation completes in memory or must use TEMP.

### 5.2. Optimal Execution

When the work area is large enough for the operation to finish entirely in memory, it is called optimal execution. For instance, a sort holds and sorts its data inside PGA without spilling to TEMP.

Optimal does not mean the entire query performs zero disk I/O; table accesses and other operations may still read/write disk. The term specifically describes how the work area executes.

### 5.3. One-Pass Execution

If the work area cannot hold the entire dataset, but can split it into runs/partitions and finish with a single primary pass of intermediate writes/reads, the operation runs in one-pass mode. It uses TEMP, though with far fewer I/O passes than multi-pass.

### 5.4. Multi-Pass Execution

If the dataset far exceeds available memory, the sort/hash must read/write TEMP across multiple passes. This is multi-pass execution, which consumes substantially more I/O and time.

### 5.5. Why Does TEMP I/O Rise?

TEMP spills can rise when:

- `PGA_AGGREGATE_TARGET` is too low for the workload.
- Many sorts/hashes execute concurrently.
- Queries suffer cardinality misestimates causing undersized work areas.
- Large intermediate datasets, join orders, or SQL cause row explosions.
- PGA is capped by `PGA_AGGREGATE_LIMIT` or OS memory pressure.

Not all TEMP usage indicates an error. Distinguish normal TEMP usage, spills due to legitimately large workloads, and abnormal spills from poor SQL/plans/statistics.

### 5.6. Inspecting Work Area Statistics

```sql
SELECT name, value, unit
FROM v$pgastat
ORDER BY name;

SELECT
    operation_type,
    policy,
    estimated_optimal_size,
    estimated_onepass_size,
    last_memory_used,
    last_execution,
    last_tempseg_size
FROM v$sql_workarea
ORDER BY last_tempseg_size DESC NULLS LAST;
```

`V$PGASTAT` provides overall PGA statistics; `V$SQL_WORKAREA` describes work areas tied to SQL cursors. Use `V$SQL_WORKAREA_ACTIVE` to inspect work areas active at observation time.

## 6. Manual Memory Management

### 6.1. Concept

Manual memory management requires the DBA to specify individual SGA component sizes and/or PGA work area policies via explicit parameters. This offers fine-grained control, but demands understanding workloads, continuous monitoring, and manual tuning.

### 6.2. Manual SGA

Without ASMM/AMM, DBAs can set pools such as:

- `DB_CACHE_SIZE`.
- `SHARED_POOL_SIZE`.
- `LARGE_POOL_SIZE`.
- `JAVA_POOL_SIZE`.
- `STREAMS_POOL_SIZE`.

Additional components and parameters exist depending on features/releases. Total memory must fit within the configured SGA budget and `SGA_MAX_SIZE` if specified.

### 6.3. Manual Work Areas

PGA work areas can be managed using `WORKAREA_SIZE_POLICY = MANUAL` and parameters such as `SORT_AREA_SIZE`, `HASH_AREA_SIZE`, `BITMAP_MERGE_AREA_SIZE`, or `CREATE_BITMAP_AREA_SIZE` depending on operation/release.

Manual parameters apply per session/process and can cause total PGA to surge rapidly when many sessions run concurrently. Use only when specifically justified, under tightly controlled concurrency, and with full awareness of total memory impact.

### 6.4. Pros and Cons

| Pros | Cons |
| --- | --- |
| Explicit control over each component | DBA must monitor and tune manually |
| Can fit stable, specialized workloads | Easy to under- or over-allocate when workloads shift |
| Useful for legacy/special configurations | Hard to manage under fluctuating concurrency |

For most modern systems, ASMM for SGA combined with automatic PGA work area management is easier to operate than full manual sizing.

## 7. ASMM — Automatic Shared Memory Management

### 7.1. Concept

ASMM automatically resizes key SGA components within an overall budget set by `SGA_TARGET`. The DBA sets the total target and may set minimums for protected components. Oracle uses a memory advisor/broker to redistribute SGA across pools based on observed demand.

ASMM manages the SGA; it does not automatically rebalance memory between SGA and PGA like AMM does. PGA remains managed separately, typically via `PGA_AGGREGATE_TARGET` and automatic work area management.

### 7.2. Key Parameters

| Parameter | Role |
| --- | --- |
| `SGA_TARGET` | Total SGA target managed by ASMM |
| `SGA_MAX_SIZE` | Maximum SGA limit established at startup |
| `DB_CACHE_SIZE` | Minimum size/explicit value for buffer cache if specified |
| `SHARED_POOL_SIZE` | Minimum size for shared pool under ASMM |
| `LARGE_POOL_SIZE` | Minimum size for large pool under ASMM |
| `JAVA_POOL_SIZE` | Minimum size for Java pool under ASMM |
| `STREAMS_POOL_SIZE` | Minimum size for Streams pool under ASMM |
| `PGA_AGGREGATE_TARGET` | Separately managed PGA target |
| `PGA_AGGREGATE_LIMIT` | Instance-wide total PGA limit |

When `SGA_TARGET` is enabled, explicitly specified component sizes generally act as minimums that ASMM must respect, rather than letting Oracle shrink them lower.

### 7.3. How It Works

Oracle can grow or shrink dynamic SGA components within the total SGA target as demand shifts. Resizing occurs in granules and is subject to component limits, workload, release, and instance state.

ASMM does not make every component completely automatic. Some SGA areas are fixed or require separate configuration. Check `V$SGA_DYNAMIC_COMPONENTS` and `V$MEMORY_RESIZE_OPS` to see what is actually resizing.

### 7.4. Illustrative ASMM Configuration

An illustrative SPFILE configuration:

```sql
ALTER SYSTEM SET MEMORY_TARGET = 0 SCOPE = SPFILE;
ALTER SYSTEM SET SGA_TARGET = 8G SCOPE = SPFILE;
ALTER SYSTEM SET SGA_MAX_SIZE = 10G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 3G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_LIMIT = 6G SCOPE = SPFILE;
```

These are purely illustrative numbers, not sizing recommendations. `SGA_MAX_SIZE` is a startup limit; changing it typically requires a restart. Verify parameter scope and modifiability on your exact version and configuration before applying.

### 7.5. Advantages of ASMM

- Automatically adjusts SGA pools as workloads shift.
- Reduces reliance on guessing fixed sizes for every pool.
- Pairs cleanly with `PGA_AGGREGATE_TARGET` for separate work area management.
- Compatible with Linux HugePages setups where ASMM is chosen over AMM.
- Lets DBAs enforce minimum floors on critical components.

### 7.6. Limitations of ASMM

- Does not automatically rebalance total SGA and PGA.
- Does not replace sizing PGA for concurrency.
- Setting component minimums too high shrinks the pool budget Oracle can shift elsewhere.
- OS RAM exhaustion can still occur if SGA + PGA + process overhead is too large.
- Statistics/Advisors cannot perfectly predict future workloads.

## 8. Automatic PGA Management

### 8.1. PGA_AGGREGATE_TARGET

`PGA_AGGREGATE_TARGET` is the instance-wide PGA target used by automatic PGA memory management to regulate work areas. It is neither a hard per-session quota nor an absolute cap on all PGA allocations.

If total work area demand is high, Oracle allocates less memory per work area and some operations spill to TEMP. Size `PGA_AGGREGATE_TARGET` based on workload and host RAM.

### 8.2. WORKAREA_SIZE_POLICY

`WORKAREA_SIZE_POLICY` sets the work area management policy:

- `AUTO`: Oracle dynamically sizes work areas based on PGA target and workload.
- `MANUAL`: DBA uses manual work area parameters like `SORT_AREA_SIZE` and `HASH_AREA_SIZE`.

For modern systems, `AUTO` is usually the appropriate default. Do not switch to `MANUAL` to fix a single spilling query before diagnosing the root cause.

### 8.3. PGA_AGGREGATE_LIMIT

`PGA_AGGREGATE_LIMIT` sets an upper limit on total PGA the instance may consume per Oracle's enforcement mechanism. When exceeded, Oracle may abort calls/sessions consuming the most untunable PGA according to version rules to bring total usage back within bounds.

If the limit is too low, legitimate workloads such as parallel queries, large sorts, or batch jobs may abort with `ORA-04036`. If too high relative to host RAM, the OS may suffer severe memory pressure before the database reaches the limit.

### 8.4. Target and Limit Are Different

| Parameter | Meaning |
| --- | --- |
| `PGA_AGGREGATE_TARGET` | Regulation target for PGA/work areas |
| `PGA_AGGREGATE_LIMIT` | Protective ceiling on total PGA |

Do not routinely set `PGA_AGGREGATE_LIMIT` equal to `PGA_AGGREGATE_TARGET`. Leave adequate headroom for untunable PGA, concurrency, parallel execution, and OS margin.

### 8.5. Automatic Work Area Allocation

Under `AUTO`, Oracle throttles memory for sorts/hashes according to demand and active work area count. When many operations run concurrently, each receives less memory. A query that runs optimal in isolation may degrade to one-pass or multi-pass when run alongside many concurrent queries.

This is why benchmarking a single query alone is insufficient for sizing `PGA_AGGREGATE_TARGET` in production.

### 8.6. Monitoring PGA

```sql
SELECT name, value, unit
FROM v$pgastat
ORDER BY name;

SELECT
    pga_target_for_estimate,
    pga_target_factor,
    advice_status,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

`V$PGA_TARGET_ADVICE` estimates outcomes for different target sizes when advisor data is available. Check `advice_status` and collection timeframe; never treat advisor projections as performance guarantees.

## 9. AMM — Automatic Memory Management

### 9.1. Concept

AMM uses `MEMORY_TARGET` to let Oracle dynamically balance allocations between SGA and instance PGA within a single total memory target. `MEMORY_MAX_TARGET` defines the maximum `MEMORY_TARGET` that can be set without raising the startup ceiling.

Unlike ASMM, AMM manages both SGA and PGA inside one unified budget. Oracle can shift memory between SGA and PGA as demand fluctuates, respecting limits and configured minimums.

### 9.2. Key Parameters

| Parameter | Role |
| --- | --- |
| `MEMORY_TARGET` | Total memory target Oracle dynamically balances between SGA and PGA |
| `MEMORY_MAX_TARGET` | Maximum `MEMORY_TARGET` ceiling set at startup |
| `SGA_TARGET` | Minimum SGA target when AMM is enabled, if configured |
| `PGA_AGGREGATE_TARGET` | Minimum PGA target when AMM is enabled, if configured |
| `SGA_MAX_SIZE` | Startup SGA limit; evaluate alongside AMM/platform rules |

When AMM is enabled, `SGA_TARGET` and `PGA_AGGREGATE_TARGET` act as minimums for their respective areas, rather than two independent budgets added rigidly as in ASMM. Never set the sum of minimums higher than `MEMORY_TARGET`.

### 9.3. Illustrative AMM Configuration

Example SPFILE parameters:

```sql
ALTER SYSTEM SET MEMORY_MAX_TARGET = 12G SCOPE = SPFILE;
ALTER SYSTEM SET MEMORY_TARGET = 10G SCOPE = SPFILE;
ALTER SYSTEM SET SGA_TARGET = 6G SCOPE = SPFILE;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 2G SCOPE = SPFILE;
```

In this example, the combined SGA/PGA minimums total 8 GB while `MEMORY_TARGET` is 10 GB, leaving Oracle room to shift memory dynamically. This illustrates syntax only; size according to host RAM and application needs. `MEMORY_MAX_TARGET` typically must be set before startup; changing static parameters requires a restart.

### 9.4. Memory Broker

Oracle uses a memory management mechanism to adjust components and balance between SGA and PGA toward the target. Adjustments react to recent workload activity rather than predicting every future spike.

AMM cannot manufacture physical RAM. If the host is already short on memory, raising `MEMORY_TARGET` can force OS swapping or OOM kills; the database cannot tune past hardware limits.

### 9.5. Advantages

- A single total target simplifies SGA/PGA management.
- Oracle can shift budget between shared memory and process memory on demand.
- Reduces manual balancing effort between two targets.
- Useful in simple environments without HugePages or special shared-memory constraints.

### 9.6. Limitations

- Requires careful control of host RAM and headroom.
- Imposes platform/OS requirements, notably `/dev/shm` on Linux.
- AMM is incompatible with Linux HugePages in standard Oracle configurations; when HugePages is needed for large SGAs, ASMM or manual SGA is typically chosen.
- May be unsuitable for production environments requiring pinned SGA/huge pages or multiple instances competing for RAM.
- A single total target does not remove the need to understand workloads, PGA spills, and SGA component pressure.

## 10. Comparing Manual, ASMM, and AMM

### 10.1. Comparison Table

| Criterion | Manual | ASMM | AMM |
| --- | --- | --- | --- |
| SGA components | DBA sets manually | Oracle tunes within `SGA_TARGET` | Oracle tunes within `MEMORY_TARGET` |
| PGA work areas | Can be manual | Usually automatic via `PGA_AGGREGATE_TARGET` | Managed within total target, with targets/minimums |
| Core parameters | Component `*_SIZE`, workarea policy | `SGA_TARGET` + `PGA_AGGREGATE_TARGET` | `MEMORY_TARGET` + `MEMORY_MAX_TARGET` |
| Flexibility | DBA-dependent | Flexible within SGA | Flexible between SGA and PGA |
| Operational complexity | High | Moderate | Simpler in supported setups |
| HugePages on Linux | Supported | Often the preferred choice | AMM is incompatible with HugePages |
| Best fit | Specialized/legacy workloads needing tight control | Production needing HugePages and independent PGA | Environments meeting AMM prerequisites favoring one target |

### 10.2. Common Choice

For production databases on Linux with large SGAs requiring HugePages, ASMM for SGA paired with automatic PGA management is a common choice:

- `SGA_TARGET`/`SGA_MAX_SIZE` govern the SGA.
- `PGA_AGGREGATE_TARGET` regulates work areas.
- `PGA_AGGREGATE_LIMIT` protects the instance from runaway PGA.
- HugePages backs the SGA when OS and Oracle are configured properly.

In simpler setups not using HugePages, AMM can reduce manual sizing effort. Verify `/dev/shm`, platform rules, and total RAM.

Full manual sizing should only be used when clearly justified technically and operators have sufficient data to maintain it.

### 10.3. Do Not Mix Modes Arbitrarily

Some parameters are mutually exclusive or change meaning depending on the active mode. Before switching from AMM to ASMM or vice versa:

1. Inspect all current memory parameters.
2. Identify static vs. dynamic parameters and their scopes.
3. Recalculate total SGA, PGA, and OS headroom.
4. Check HugePages and `/dev/shm`.
5. Plan SPFILE updates, restarts, and rollback.
6. Monitor memory resizes, PGA, TEMP, and OS after the change.

Never simply set `MEMORY_TARGET` to 0 and assume the instance automatically switches to a properly sized ASMM setup.

## 11. Memory Parameters You Must Understand

### 11.1. SGA_TARGET

`SGA_TARGET` sets the total SGA target for ASMM. Oracle automatically tunes managed components within the target and configured minimums. It can be modified online within supported bounds, but cannot exceed the startup `SGA_MAX_SIZE`.

### 11.2. SGA_MAX_SIZE

`SGA_MAX_SIZE` is the maximum SGA limit configured at instance startup. `SGA_TARGET` may sit below it to reserve room for online SGA expansion up to the maximum. Changing `SGA_MAX_SIZE` normally requires a restart; check `ISSES_MODIFIABLE`/`ISSYS_MODIFIABLE` and release documentation before planning.

### 11.3. PGA_AGGREGATE_TARGET

`PGA_AGGREGATE_TARGET` sets the target for automatic PGA/work area management. It is a tuning target, not a fixed reservation or hard cap. Raising it gives work areas a chance at more memory; lowering it can increase TEMP spills.

### 11.4. PGA_AGGREGATE_LIMIT

`PGA_AGGREGATE_LIMIT` protects the instance against total PGA allocations exceeding a threshold. Set it high enough for legitimate workloads while staying within the host memory budget. If set too low, calls consuming large untunable PGA may be terminated.

### 11.5. MEMORY_TARGET

`MEMORY_TARGET` enables AMM and sets the combined memory target Oracle dynamically manages across SGA and PGA. It can be adjusted online within `MEMORY_MAX_TARGET` and runtime constraints.

### 11.6. MEMORY_MAX_TARGET

`MEMORY_MAX_TARGET` is the upper ceiling for `MEMORY_TARGET`. It is set at startup and changing it usually requires a restart. On Linux, ensure `/dev/shm` shared memory capacity supports AMM when enabled.

### 11.7. WORKAREA_SIZE_POLICY

`WORKAREA_SIZE_POLICY = AUTO` lets Oracle manage work areas automatically toward the PGA target. `MANUAL` uses manual work area parameters. On modern systems, `AUTO` is usually preferable because it adapts across concurrent workloads.

### 11.8. Component Sizes Under ASMM

When `SGA_TARGET` is enabled, parameters such as `DB_CACHE_SIZE` and `SHARED_POOL_SIZE` act as minimum floors for their respective components. Setting minimums too high limits Oracle's ability to shift memory to other components.

### 11.9. Viewing Parameter Values and Modifiability

```sql
SELECT
    name,
    value,
    issys_modifiable,
    isses_modifiable,
    isdefault
FROM v$parameter
WHERE name IN (
    'memory_target',
    'memory_max_target',
    'sga_target',
    'sga_max_size',
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'workarea_size_policy',
    'use_large_pages'
)
ORDER BY name;
```

`V$PARAMETER` reflects current session/instance values per view context. For SPFILE settings and pending/restart values, inspect `V$SPPARAMETER` and `V$PARAMETER2` as appropriate.

## 12. Oracle Memory and OS RAM

### 12.1. Not All Host RAM Belongs to Oracle

The host also needs memory for:

- Kernel, drivers, and system services.
- Filesystem caches and system daemons.
- ASM, listeners, agents, monitoring, and backups.
- Other Oracle instances.
- Application servers, middleware, and job schedulers if co-located.
- Administrative processes and operational tools.

Allocating nearly all RAM to SGA/PGA leaves the OS no headroom for bursts, new processes, filesystem caching, or background tasks.

### 12.2. SGA and PGA Seen from the OS

SGA is shared memory mapped into the address space of many Oracle processes. PGA is private process memory. Because SGA appears in the RSS of multiple processes, summing RSS across every Oracle process double-counts the same shared memory region many times.

On Linux, PSS (Proportional Set Size) divides shared memory proportionally across mapping processes; however, understand how the tool measures it and always cross-check with Oracle's SGA/PGA views.

### 12.3. Available RAM Matters More Than Free RAM

Linux uses idle RAM for page cache/buffers. Low `MemFree` does not automatically indicate memory exhaustion. Inspect `MemAvailable`, swap activity, reclamation, and memory pressure together:

```text
free -h
vmstat 1
cat /proc/meminfo
```

In `vmstat`, the `si`/`so` columns show periodic swap-ins/swap-outs. Sustained swap activity paired with rising latency signals a problem to investigate; do not rely on a single snapshot.

### 12.4. Swap and Oracle

Swap lets the OS move memory pages to disk when RAM is scarce. If SGA/PGA gets swapped out or the host swaps heavily, latency can spike dramatically. The database may report normal memory targets while response times collapse due to OS paging.

Never treat swap as extra performance RAM. Some OS setups maintain swap for safety or system requirements, but the operational goal is avoiding sustained swapping for database memory workloads.

### 12.5. OOM Killer and Process Termination

When a host or container runs out of memory, Linux may invoke the OOM killer and terminate processes. An Oracle instance can crash abruptly, with the alert log recording dead processes or instance recovery. `PGA_AGGREGATE_LIMIT` does not replace OS headroom; it only enforces PGA limits per Oracle rules.

### 12.6. Memory Pressure Causes Multiple Symptoms

- Slow queries due to swapping/page reclamation.
- Process spawn failures due to memory exhaustion.
- Oracle processes killed by the OS.
- SGA resize failures or stalled resizes.
- Restricted PGA allocations causing rising TEMP spills.
- Memory starvation in backup, monitoring, or ASM processes.

During an incident, align timestamps across the alert log, database views, OS metrics, and kernel logs.

## 13. HugePages and Shared Memory on Linux

### 13.1. What Is HugePages?

HugePages lets the OS manage memory using much larger pages than standard pages. For large SGAs, HugePages reduces page table entries, cuts page management overhead, and eases TLB pressure. HugePages also allocates SGA from reserved memory, avoiding certain shared-memory paging risks.

HugePages applies primarily to the SGA; process PGA cannot be pooled into a shared HugePages region like the SGA.

### 13.2. ASMM and HugePages

On Linux, ASMM or manual SGA is typically used when leveraging HugePages. Size the SGA to match reserved HugePages while leaving enough standard memory for OS and PGA.

If the SGA requests more HugePages than the OS reserved, the instance may fail to start or fall back away from HugePages depending on the `USE_LARGE_PAGES` setting.

### 13.3. AMM and HugePages

AMM on Linux relies on shared memory backed by `/dev/shm` and is incompatible with standard Oracle HugePages setups. When HugePages is required for the SGA, choose ASMM or manual SGA instead of AMM.

This is a key trade-off: AMM simplifies SGA/PGA balancing, whereas ASMM with HugePages is often better suited for large databases needing strict OS memory control.

### 13.4. USE_LARGE_PAGES

`USE_LARGE_PAGES` controls Oracle's use of HugePages on Linux in supported releases. Modes such as `TRUE` and `ONLY` carry different semantics: `ONLY` requires sufficient HugePages to start, while fallback modes may allow standard pages if HugePages is insufficient.

Do not change this parameter before verifying `HugePages_Total`, `HugePages_Free`, `Hugepagesize`, and the SGA size to be allocated.

### 13.5. Memlock

The OS user running Oracle needs adequate `memlock` limits to lock/reserve memory regions as required. If `memlock` is too low, HugePages may not be used as intended. Configuring `ulimit`/security limits depends on the Linux distribution and Oracle installation method.

### 13.6. Checking HugePages

```text
grep -i Huge /proc/meminfo
ulimit -l
```

Key fields to inspect:

- `HugePages_Total`: total large pages reserved.
- `HugePages_Free`: large pages still free.
- `HugePages_Rsvd`: pages reserved for mappings.
- `Hugepagesize`: size of each large page.

Do not look solely at `HugePages_Free` right after startup; cross-check actual SGA allocations and process mappings.

### 13.7. HugePages and Headroom

Reserved HugePages reduce the RAM available to the regular OS page allocator. Over-reserving starves the OS and PGA; under-reserving prevents the SGA from fitting fully in huge pages. Calculate across the sum of all HugePages-backed SGAs on the host while preserving OS headroom.

## 14. AMM and /dev/shm on Linux

### 14.1. What Is /dev/shm?

`/dev/shm` is typically a `tmpfs` mount used for POSIX shared memory. When AMM is enabled on Linux, Oracle uses this shared memory area to manage the memory target. The mount size must accommodate the AMM configuration.

### 14.2. Checking Capacity

```text
df -h /dev/shm
mount | grep /dev/shm
```

Compare mount capacity against `MEMORY_TARGET`/`MEMORY_MAX_TARGET` and release requirements. Also account for other applications/processes using `tmpfs`.

### 14.3. ORA-00845

`ORA-00845: MEMORY_TARGET not supported on this system` typically occurs when Linux shared-memory prerequisites for AMM are unmet—such as `/dev/shm` missing, undersized mount, or misconfigured system settings.

Remediation steps:

1. Check the alert log and OS mounts.
2. Run `df -h /dev/shm`.
3. Verify `MEMORY_TARGET` and `MEMORY_MAX_TARGET`.
4. Increase `tmpfs` capacity per OS/DBA guidance if the host has sufficient RAM.
5. If using HugePages, consider switching to ASMM/manual SGA instead of AMM.

Never enlarge `/dev/shm` beyond available RAM without accounting for total host memory.

### 14.4. /dev/shm Consumes Host Resources Too

`tmpfs` is not free storage. `tmpfs` pages are backed by memory and subject to OS swapping. Increasing mount size does not add physical RAM; it merely sets the maximum ceiling allowed.

### 14.5. Containers and /dev/shm

In Docker/Kubernetes, a container's `/dev/shm` and memory limit may be far smaller than the host's. Oracle inside a container must be configured for the container's limits, not the entire node's RAM. Verify mount size, cgroup limits, and Oracle platform certification for that environment.

## 15. Sizing Memory by Host

### 15.1. Start from the RAM Budget

A budgeting framework:

```text
Available physical RAM
  - Kernel and OS reserve
  - Agents, backups, monitoring, ASM
  - Co-located applications and middleware
  - Other Oracle instances
  - Safety headroom for bursts
  = Expected budget for the target instance

Instance budget
  -> SGA
  -> PGA based on concurrency/workload
  -> process overhead and variance margin
```

This is a planning model, not a rigid formula. `SGA_TARGET` and `PGA_AGGREGATE_TARGET` are targets; actual PGA and process overhead fluctuate.

### 15.2. Do Not Simply Assign All Remaining RAM Minus SGA

The remainder cannot automatically all go to PGA. The host still needs process memory, kernel space, page cache, background processes, agents, and other workloads. Nor does `PGA_AGGREGATE_LIMIT` represent the maximum total memory footprint of Oracle on the host.

### 15.3. Estimating PGA by Concurrency

Ask:

- How many sessions run concurrently?
- How many concurrent queries run heavy sorts/hashes?
- Do batch/reporting jobs overlap with OLTP?
- Do parallel queries use high DOP?
- Can one session open multiple concurrent cursors/work areas?
- Do ETL/backup processes consume heavy PGA?

PGA demand does not equal session count times a constant. Work areas allocate dynamically and many sessions sit idle. Use `V$PGASTAT`, `V$SQL_WORKAREA_ACTIVE`, and peak workload observations to estimate.

### 15.4. Parallel Execution

Parallel queries can spawn many PX server processes. Each process has its own PGA and potentially its own work areas; total PGA for a single parallel statement can vastly exceed serial execution.

When raising DOP, account for:

- Concurrent PX server processes.
- Work areas per process.
- Simultaneously running parallel statements.
- PGA for coordinator and background processes.
- Impact on TEMP and I/O.

Resource Manager, parallel statement queuing, and DOP caps help protect the host when many parallel queries arrive together.

### 15.5. Multiple Instances on the Same Host

On a RAC node or host running multiple database instances, sum every instance's SGA and the concurrent PGA across all instances. Never size each instance independently as if it owned all host RAM.

HugePages is also a shared host resource. Reserve enough for the combined HugePages-backed SGAs of all instances while leaving standard RAM for OS and PGA.

### 15.6. Illustrative Memory Budget Example

Suppose a host has 64 GB of RAM. An initial plan might reserve 12 GB for OS/kernel/headroom, 4 GB for agents/ASM/backups, and 4 GB for variance. The remaining ~44 GB forms the expected budget for the Oracle instance and related process overhead.

Within that budget, a DBA might test 24 GB SGA, 10 GB PGA target, and 14 GB PGA limit, leaving the rest for process overhead/fluctuations. These figures illustrate the thought process only; validate against actual peak memory, workloads, and OS metrics. Never copy this example blindly to any real host.

## 16. SGA Trade-offs with OS and PGA

### 16.1. Increasing SGA

Potential benefits:

- Buffer cache retains more hot blocks.
- Shared pool retains more cursors/metadata.
- Reduces certain physical reads or parse overhead.

Costs/risks:

- Shrinks RAM available to PGA and OS.
- Can increase PGA spills to TEMP when total host memory is fixed.
- Increases shared memory footprint and HugePages requirements.
- If cache hits are not the bottleneck, raising SGA may not improve response time.

### 16.2. Increasing PGA

Potential benefits:

- Larger sort/hash work areas.
- Fewer one-pass/multi-pass spills.
- Reduced TEMP I/O and faster elapsed time for certain queries.

Costs/risks:

- PGA is process-private memory and grows rapidly with concurrency.
- Can trigger memory pressure, swapping, or OOM.
- Parallel queries multiply processes/work areas.
- `PGA_AGGREGATE_LIMIT` can abort calls if exceeded.

### 16.3. Increasing Both

You cannot raise both SGA and PGA endlessly. Without adding host RAM, memory must come from OS headroom or other workloads. Speeding up one report query can degrade OLTP latency due to host-wide memory starvation.

### 16.4. Reducing SGA Too Far

An undersized SGA can spike physical reads, hard parses, or allocation pressure. The database can then slow down even while the OS has plenty of free RAM. Identify which component is genuinely starved rather than blindly raising the entire SGA.

### 16.5. Reducing PGA Too Far

An undersized PGA causes work areas to spill to TEMP, increasing I/O, query duration, and TEMP tablespace contention. If TEMP usage grows even when PGA target fits the host well, the cause may be SQL generating oversized intermediate sets or poor plans.

### 16.6. Optimize the System, Not One Query

Evaluate memory against the workload mix: OLTP, reporting, batch, ETL, backups, and parallel queries. Never let a single report query consume nearly all PGA and starve hundreds of OLTP sessions. Resource Manager and workload scheduling are integral to memory management.

## 17. Monitoring SGA and Dynamic Resizing

### 17.1. V$SGAINFO

`V$SGAINFO` reports general information such as SGA size, granule size, and SGA regions:

```sql
SELECT name, bytes
FROM v$sgainfo
ORDER BY name;
```

### 17.2. V$SGASTAT

`V$SGASTAT` breaks down memory allocations by pool/name:

```sql
SELECT
    pool,
    name,
    bytes
FROM v$sgastat
ORDER BY pool, bytes DESC;
```

This is a granular allocation view; not every row corresponds to an independently resizable component. Use it to pinpoint pools/areas consuming memory and compare over time.

### 17.3. V$SGA_DYNAMIC_COMPONENTS

Track current/min/max sizes and resize activity:

```sql
SELECT
    component,
    current_size,
    min_size,
    max_size,
    user_specified_size,
    oper_count,
    last_oper_type,
    last_oper_time
FROM v$sga_dynamic_components
ORDER BY current_size DESC;
```

Components may show `current_size` of 0 or be absent depending on configuration/features. Inspect alongside parameters and workload; do not assume memory shortage simply because a component is small.

### 17.4. V$MEMORY_RESIZE_OPS

This view logs recent memory resize operations:

```sql
SELECT
    component,
    oper_type,
    oper_mode,
    initial_size,
    target_size,
    final_size,
    status,
    start_time,
    end_time
FROM v$memory_resize_ops
ORDER BY start_time DESC;
```

Resize failures or frequent oscillations can indicate unsuitable targets or floor constraints. Check the alert log and min/max parameters to understand why.

### 17.5. Buffer Cache and Shared Pool

Look beyond size alone:

- Buffer cache: examine physical reads, logical reads, workload reuse, and direct path behavior.
- Shared pool: examine parse counts, hard parses, cursor reuse, allocation failures, and `ORA-04031`.
- Large pool: examine shared server, parallel execution, RMAN, and related allocations.

Cache hit ratio alone is never enough to justify growing a pool. Evaluate wait events, SQL plans, actual I/O, and response times.

## 18. Monitoring PGA and Work Areas

### 18.1. V$PGASTAT

Key metrics include:

- `aggregate PGA target parameter`.
- `total PGA allocated`.
- `total PGA inuse`.
- `maximum PGA allocated`.
- `over allocation count`.
- `cache hit percentage`.
- `extra bytes read/written`.
- `global memory bound`.

Query:

```sql
SELECT name, value, unit
FROM v$pgastat
WHERE name IN (
    'aggregate PGA target parameter',
    'total PGA allocated',
    'total PGA inuse',
    'maximum PGA allocated',
    'over allocation count',
    'cache hit percentage',
    'extra bytes read/written',
    'global memory bound'
)
ORDER BY name;
```

`cache hit percentage` is an aggregate work-area metric; it is not the buffer cache hit ratio and should not be used alone to raise targets.

### 18.2. V$PROCESS

Inspect PGA per process:

```sql
SELECT
    pid,
    spid,
    program,
    pga_used_mem,
    pga_alloc_mem,
    pga_freeable_mem,
    pga_max_mem
FROM v$process
ORDER BY pga_alloc_mem DESC;
```

This is a point-in-time snapshot of per-process allocations. Join with `V$SESSION` on `PADDR/ADDR` when locating sessions consuming heavy PGA; background processes can also consume notable memory.

### 18.3. V$PROCESS_MEMORY

Break down memory by process/category:

```sql
SELECT
    pid,
    category,
    allocated,
    used,
    max_allocated
FROM v$process_memory
ORDER BY allocated DESC;
```

Categories may include SQL, PL/SQL, OLAP, Java, Freeable, and Other depending on release. Use this to see allocation types rather than assuming all PGA is SQL work areas.

### 18.4. V$SQL_WORKAREA_ACTIVE

Inspect currently active work areas:

```sql
SELECT
    sid,
    sql_id,
    operation_type,
    policy,
    expected_size,
    actual_mem_used,
    max_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY actual_mem_used DESC;
```

`NUMBER_PASSES` and `TEMPSEG_SIZE` reveal whether an operation is spilling to TEMP. This is a snapshot; a work area can finish before the DBA queries the view.

### 18.5. V$TEMPSEG_USAGE

Inspect sessions using temporary segments:

```sql
SELECT
    username,
    session_addr,
    session_num,
    sql_id,
    tablespace,
    segtype,
    blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
```

Join with `V$SESSION` to find `SQL_ID`, module, action, and execution duration. TEMP usage can also come from global temporary tables, index builds, bitmap operations, or other operations—not just sort/hash spills.

## 19. Memory Advisors

### 19.1. SGA_TARGET_ADVICE

`V$SGA_TARGET_ADVICE` estimates the impact of varying SGA target sizes based on observed workload:

```sql
SELECT
    sga_size,
    sga_size_factor,
    estd_db_time,
    estd_db_time_factor,
    estd_physical_reads
FROM v$sga_target_advice
ORDER BY sga_size;
```

Advisors are only helpful after collecting a representative workload. Daytime-only activity cannot fully represent overnight batch workloads.

### 19.2. PGA_TARGET_ADVICE

```sql
SELECT
    pga_target_for_estimate,
    pga_target_factor,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

If estimated cache hit rises negligibly when increasing PGA, the benefit may be low. If overalloc count is non-zero, understand the workload/target before concluding. Advisors cannot perfectly model every concurrency peak.

### 19.3. MEMORY_TARGET_ADVICE

When AMM is enabled and advisor data is populated:

```sql
SELECT
    memory_size,
    memory_size_factor,
    estd_db_time,
    estd_db_time_factor,
    estd_physical_reads
FROM v$memory_target_advice
ORDER BY memory_size;
```

This view may lack useful data if AMM is off or workload history is insufficient. Never use advisor projections to justify exceeding the host RAM budget.

### 19.4. Advisors Are Estimates

Advisors:

- Rely on observed workloads/intervals.
- May underrepresent peak concurrency.
- Do not account for OS, agents, or other instances' memory.
- Cannot foresee future workload shifts.
- Do not guarantee linear response-time improvements with added memory.

Combine advisors with AWR/ASH (where licensed), SQL Monitor, wait events, and OS metrics.

## 20. Monitoring Memory from the Operating System

### 20.1. Linux

Common commands:

```text
free -h
vmstat 1
top
ps -eo pid,ppid,rss,vsz,comm --sort=-rss | head
grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree|HugePages|Hugepagesize' /proc/meminfo
```

Meaning:

- `free -h`: RAM and swap summary.
- `vmstat`: run queue, paging, swap, and CPU over intervals.
- `top`/`ps`: processes consuming memory/CPU.
- `/proc/meminfo`: available memory, huge pages, and kernel states.

Per-process RSS for Oracle processes often includes shared SGA mappings; do not mechanically sum RSS to derive total PGA.

### 20.2. PSS and Shared Mappings

On Linux, `smem` or `/proc/PID/smaps_rollup` can report PSS if supported by the OS. PSS splits shared memory proportionally across processes mapping it. This offers a helpful supplement, not a replacement for Oracle memory views.

### 20.3. Windows

On Windows, use Task Manager, Resource Monitor, Performance Monitor, and counters for committed memory, available memory, paging, and process working set/private bytes. Distinguish shared memory/working set from private bytes; measurement semantics differ from Linux, so never apply Linux commands or formulas directly.

### 20.4. Containers/cgroups

When Oracle runs inside a container, inspect actual cgroup memory limits, `memory.current`, `memory.max`, and `memory.events` (cgroup v2) or equivalent cgroup v1 files. Large host RAM does not mean a container can access all host RAM.

Oracle version, platform certification, and how the runtime enforces cgroup limits determine how much memory Oracle sees. Never rely solely on `free` run on the host.

### 20.5. OS Metrics Must Match Timestamps

When queries slow down, collect database views and OS metrics over the exact same timeframe. Comparing a `V$PGASTAT` snapshot from 10:00 with `vmstat` output from 14:00 cannot explain an incident at 11:00.

## 21. Diagnosing Memory Incidents

### 21.1. ORA-04031 — Unable to Allocate Shared Memory

`ORA-04031` typically indicates Oracle failed to allocate a required chunk of shared memory in the SGA. It may involve the shared pool, large pool, or a specific pool/heap.

Investigation steps:

1. Read the full error text to identify the pool/heap and requested allocation size.
2. Inspect the alert log and trace files.
3. Check `V$SGASTAT` by pool/name and `V$SGA_DYNAMIC_COMPONENTS`.
4. Check shared pool pressure, hard parsing, cursor churn, and allocation patterns.
5. Check whether component minimums are overly high or SGA target is too low.
6. Check whether the application continuously generates SQL text with varying literals.

Never blindly increase `SHARED_POOL_SIZE` by default. `ORA-04031` can occur in other pools or stem from allocation/fragmentation patterns, cursor management, and workload behavior.

### 21.2. ORA-04036 — PGA_AGGREGATE_LIMIT Exceeded

`ORA-04036` occurs when total PGA exceeds `PGA_AGGREGATE_LIMIT` per Oracle's rules. Offending calls/sessions may be terminated.

Investigation steps:

- Check `V$PGASTAT`, especially total/maximum PGA allocated.
- Check `V$PROCESS` and `V$PROCESS_MEMORY` to identify top consumers.
- Check `V$SQL_WORKAREA_ACTIVE` and `V$TEMPSEG_USAGE`.
- Identify parallel queries, batches, or sessions running heavy sorts/hashes.
- Check `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT`, and host headroom.
- Check whether the application opens excessive sessions or runs unbounded queries.

Do not just raise `PGA_AGGREGATE_LIMIT` to silence the error. If the host lacks RAM, raising the limit pushes the problem into swapping or OOM.

### 21.3. ORA-04030 — Out of Process Memory

`ORA-04030` indicates a process cannot allocate private memory. Causes include excessive PGA/process memory, OS process limits, address space limits, OS memory pressure, or abnormal allocations.

Check:

- Trace/alert log for the exact process and requested allocation.
- PGA per process and category.
- Session/process counts and parallel workers.
- OS memory, swap, `ulimit`, and cgroup limits.
- Whether application/PLSQL code holds huge collections/LOBs or leaks memory.

`ORA-04030` differs from `ORA-04036`: one reflects process-level allocation failure; the other enforces the instance-wide PGA aggregate limit.

### 21.4. ORA-00845 — MEMORY_TARGET Not Supported on This System

On Linux, check `/dev/shm` mount and capacity along with `MEMORY_TARGET`/`MEMORY_MAX_TARGET`. If HugePages is required, recognize AMM is unsuitable and plan a transition to ASMM.

### 21.5. TEMP Tablespace Full

A full TEMP tablespace does not mean PGA is out of memory. A query can spill massive data to TEMP due to small work areas or huge intermediate result sets. Inspect `V$TEMPSEG_USAGE`, `SQL_ID`, operation, and TEMP capacity. Expanding TEMP solves temporary capacity, not necessarily performance.

### 21.6. OS Swapping or OOM

If the OS swaps continuously or the kernel OOM-kills an Oracle process:

1. Collect `free`, `vmstat`, `/proc/meminfo`, or equivalent tools.
2. Inspect SGA, PGA, and other host processes.
3. Check cgroup/container memory limits.
4. Check HugePages and `/dev/shm`.
5. Reduce concurrency/parallelism or memory targets in a planned manner if the host is overloaded.
6. Avoid repeatedly restarting the instance before resolving the underlying RAM deficit.

### 21.7. Symptoms and Evidence Sources

| Symptom | Database Evidence | OS Evidence |
| --- | --- | --- |
| Shared memory allocation failure | `ORA-04031`, `V$SGASTAT`, resize ops | Available RAM, shared memory limits |
| PGA aggregate limit exceeded | `ORA-04036`, `V$PGASTAT`, `V$PROCESS` | RAM, swap, cgroup |
| Process allocation failure | `ORA-04030`, `V$PROCESS_MEMORY` | `ulimit`, process RSS/PSS, kernel logs |
| Slow sorts/hashes | `V$SQL_WORKAREA`, `V$TEMPSEG_USAGE` | I/O latency, TEMP storage |
| AMM startup failure | `ORA-00845`, memory parameters | `/dev/shm` size/mount |
| Instance killed by OS | alert/trace logs, process exit | kernel OOM logs, `memory.events` |

## 22. Controlled Memory Tuning Workflow

### 22.1. Step 1 — Establish a Baseline

Collect metrics during both normal and peak hours:

- SGA component sizes and resize history.
- PGA target, limit, total/max PGA, and over-allocations.
- Work area optimal/one-pass/multi-pass counts and TEMP usage.
- Session/process counts and parallel degree.
- OS `MemAvailable`, swap in/out, CPU, I/O, and cgroup limits.
- Response times and throughput of key workloads.

### 22.2. Step 2 — Identify the Bottleneck

Ask where the issue lies:

- Shared pool allocation/parsing?
- Buffer cache physical reads?
- PGA work area spills?
- Parallel query concurrency?
- OS swapping/OOM?
- `/dev/shm` or HugePages?
- Application/agent process memory?

Never raise SGA/PGA if the bottleneck is CPU, storage latency, SQL plans, or application concurrency.

### 22.3. Step 3 — Formulate a Measurable Hypothesis

Examples:

- Raising PGA target moderately will reduce multi-pass sorts and TEMP I/O during the batch window.
- Lowering DOP will reduce peak PGA while potentially lengthening single-statement elapsed time.
- Raising the shared pool minimum will ease allocation pressure during peak parsing hours.
- Moving from AMM to ASMM will allow Linux HugePages, requiring OS reservation changes and a restart.

Every hypothesis must specify which metrics will move and the success criteria.

### 22.4. Step 4 — Verify Headroom

Before raising memory targets, confirm physical/VM/container RAM, other instances' memory, OS reserves, HugePages reservations, `/dev/shm`, peak PGA, and process overhead. Never budget from raw total RAM alone.

### 22.5. Step 5 — Make Small Changes with Rollback Plans

Change only one related parameter group within an approved change window. Record old values, back up SPFILE/PFILE, verify scope, restart needs, and rollback steps. Never alter hidden parameters arbitrarily.

### 22.6. Step 6 — Observe Post-Change

Compare under matching workloads and durations:

- Response time/throughput.
- SGA resizes and component pressure.
- PGA total/max, cache hit, overalloc.
- TEMP I/O and work area passes.
- OS `MemAvailable`, swap, page reclamation, and OOM events.

A successful change improves the target workload without starving host headroom or causing unacceptable degradation to other workloads.

### 22.7. Step 7 — Keep or Roll Back

If metrics fail to improve or OS pressure rises, roll back to previous settings. If improved, monitor across multiple workload cycles to confirm the gain is not merely short-term.

## 23. Parameter Changes and Scope

### 23.1. SCOPE

`ALTER SYSTEM` writes values to memory, the SPFILE, or both:

| Scope | Meaning |
| --- | --- |
| `MEMORY` | Active in the current instance only; does not update SPFILE |
| `SPFILE` | Writes setting for the next startup; not necessarily active immediately |
| `BOTH` | Updates SPFILE and applies at runtime if supported |

Applicability depends on the parameter and instance state. If the instance boots from a PFILE, `SCOPE=SPFILE`/`BOTH` is not valid.

### 23.2. Dynamic and Static Parameters

`SGA_TARGET`, `PGA_AGGREGATE_TARGET`, and `MEMORY_TARGET` can typically be adjusted online within supported limits. `SGA_MAX_SIZE` and `MEMORY_MAX_TARGET` normally require a restart to change. Confirm via `V$PARAMETER.ISSYS_MODIFIABLE` and release documentation.

### 23.3. Illustrative ASMM Adjustment

Example runtime adjustment where permitted:

```sql
ALTER SYSTEM SET SGA_TARGET = 8G SCOPE = BOTH;
ALTER SYSTEM SET PGA_AGGREGATE_TARGET = 3G SCOPE = BOTH;
```

Apply only after verifying host budget, `SGA_MAX_SIZE`, component minimums, and peak PGA. Values shown here illustrate syntax only.

### 23.4. Static Parameter Change

Example setting a startup parameter:

```sql
ALTER SYSTEM SET SGA_MAX_SIZE = 10G SCOPE = SPFILE;
```

This change normally requires a restart to take effect. Never run in production without change approval, a startup plan, and a rollback plan.

### 23.5. Switching from AMM to ASMM

Switching modes may require updating `MEMORY_TARGET`/`MEMORY_MAX_TARGET`, `SGA_TARGET`/`SGA_MAX_SIZE`, `PGA_AGGREGATE_TARGET`, HugePages, and OS memory settings. Follow a runbook tailored to your Oracle release/platform; verify SPFILE values beforehand, plan the restart, validate startup, and re-verify memory allocations.

Never execute ad-hoc `ALTER SYSTEM` sequences on production based purely on documentation snippets. Parameter ordering, limits, and restart rules must be checked against the live configuration.

### 23.6. Record Before/After State

Save outputs of `V$PARAMETER`/`V$SPPARAMETER`, `V$SGAINFO`, `V$PGASTAT`, OS memory, and change timestamps. Record affected SQL_IDs/workloads for objective comparison.

## 24. Practice Lab: Observing SGA/PGA and Advisors

The commands below are primarily read-only. Run them in a lab schema/instance with appropriate `SELECT` privileges; never alter memory parameters in production.

### 24.1. Check Current Memory Mode

```sql
SHOW PARAMETER memory_target
SHOW PARAMETER memory_max_target
SHOW PARAMETER sga_target
SHOW PARAMETER sga_max_size
SHOW PARAMETER pga_aggregate_target
SHOW PARAMETER pga_aggregate_limit
SHOW PARAMETER workarea_size_policy
SHOW PARAMETER use_large_pages
```

### 24.2. Inspect SGA Components

```sql
SELECT component,
       current_size / 1024 / 1024 AS current_mb,
       min_size / 1024 / 1024 AS min_mb,
       max_size / 1024 / 1024 AS max_mb
FROM v$sga_dynamic_components
ORDER BY current_size DESC;
```

### 24.3. Inspect Overall PGA

```sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
```

### 24.4. Inspect Top PGA Processes

```sql
SELECT pid,
       spid,
       program,
       ROUND(pga_alloc_mem / 1024 / 1024, 1) AS pga_alloc_mb,
       ROUND(pga_used_mem / 1024 / 1024, 1) AS pga_used_mb,
       ROUND(pga_max_mem / 1024 / 1024, 1) AS pga_max_mb
FROM v$process
ORDER BY pga_alloc_mem DESC;
```

### 24.5. Inspect PGA Advisor

```sql
SELECT
    ROUND(pga_target_for_estimate / 1024 / 1024) AS target_mb,
    pga_target_factor,
    estd_pga_cache_hit_percentage,
    estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;
```

### 24.6. Inspect Spilling Work Areas

```sql
SELECT
    sql_id,
    operation_type,
    actual_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
```

### 24.7. Inspect OS Memory from Oracle

```sql
SELECT stat_name, value
FROM v$osstat
WHERE stat_name IN (
    'PHYSICAL_MEMORY_BYTES',
    'FREE_MEMORY_BYTES',
    'NUM_CPUS'
)
ORDER BY stat_name;
```

Statistic names may vary or be unavailable across platforms/releases. Cross-check with host OS tools.

## 25. Practice Lab: Observing Sorts and TEMP

### 25.1. Prepare a Lab Table

If you have a suitably sized sample schema, use a dedicated test table. For example:

```sql
CREATE TABLE lab_memory_sort AS
SELECT level AS id,
       MOD(level, 1000) AS group_id,
       RPAD('X', 100, 'X') AS payload
FROM dual
CONNECT BY level <= 500000;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_MEMORY_SORT'
    );
END;
/
```

Scale the lab table to fit your environment's RAM/TEMP; reduce the row count on smaller machines.

### 25.2. Run a Sort with Runtime Statistics

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_memory_sort
ORDER BY payload DESC, id DESC;
```

Immediately inspect the actual plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +MEMSTATS'
    )
);
```

`MEMSTATS` displays memory/temp statistics when available in the plan. Observe the sort operation, memory used, and TEMP usage. If the query is small or PGA is large, the sort may run optimal with zero spill.

### 25.3. Observe Concurrency

Open multiple lab sessions running sort/hash queries simultaneously while monitoring `V$SQL_WORKAREA_ACTIVE`, `V$PGASTAT`, and `V$TEMPSEG_USAGE`. You will observe that higher concurrency shrinks memory per work area and increases TEMP spills.

Never intentionally set an ultra-low PGA limit in production to trigger `ORA-04036`. When testing limits, use an isolated lab instance with bounded RAM/TEMP and a recovery plan.

## 26. Practice Lab: Calculating a Memory Budget

### 26.1. Build the Host Table

Fill in actual numbers:

| Item | GB |
| --- | ---: |
| Physical RAM or container limit | |
| OS/kernel reserve | |
| Agents, backups, ASM, middleware | |
| Other Oracle instances | |
| Safety headroom for peaks | |
| Remaining budget for target instance | |

### 26.2. Break Down the Instance Budget

| Item | Planned Value |
| --- | ---: |
| SGA target | |
| PGA aggregate target | |
| PGA aggregate limit | |
| Process/feature overhead outside targets | |
| Expected total peak | |

`PGA_AGGREGATE_TARGET` is a regulation target, while `PGA_AGGREGATE_LIMIT` is an Oracle cap; do not sum the two as independent memory pools. When estimating peak, treat the limit as a PGA ceiling and combine with SGA and process/OS overhead per an appropriate model.

### 26.3. Check HugePages or /dev/shm

If using HugePages, sum the SGAs of all HugePages-backed instances and confirm the OS reserves enough pages, `memlock`, and remaining standard RAM. If using AMM on Linux, verify `/dev/shm` is large enough and the host retains sufficient available RAM.

### 26.4. Verify Peak Concurrency

Record active session counts, PX processes, sort/hash queries, and max PGA during peak windows. Sizing purely on averages can starve the host right when batch and reporting workloads overlap.

## 27. Best-Practice Principles

1. **Take a host-wide view.** Account for OS, agents, backups, ASM, other instances, and headroom before sizing SGA/PGA.
2. **Distinguish SGA and PGA.** SGA is shared; PGA is private per process.
3. **Account for UGA by architecture.** Dedicated server keeps UGA in PGA; shared server keeps UGA in SGA.
4. **Use ASMM deliberately.** `SGA_TARGET` tunes SGA components; `PGA_AGGREGATE_TARGET` manages PGA separately.
5. **Use AMM where platform-appropriate.** Check `/dev/shm` and HugePages before enabling.
6. **Avoid AMM when Linux HugePages is required.** Prefer ASMM/manual SGA per Oracle guidance.
7. **Size PGA target for concurrency.** Never size from a single isolated query.
8. **Keep PGA limit sensible.** Protect the host without aborting legitimate workloads.
9. **Monitor TEMP spills.** Separate PGA shortages from SQL generating huge intermediate sets.
10. **Never tune cache hit ratio in isolation.** Inspect waits, I/O, CPU, and response times.
11. **Treat advisors as reference data.** Cross-check against peak workloads and OS headroom.
12. **Do not sum RSS across all Oracle processes.** Shared SGA gets double-counted.
13. **Prevent sustained swapping.** Swapping/OOM cripples instance-wide performance.
14. **Leave OS headroom.** Never commit 100% of RAM to `MEMORY_TARGET`/SGA/PGA.
15. **Cap parallelism.** High DOP multiplies processes and total PGA.
16. **Change with baselines and rollback plans.** Record old values, scope, restart needs, and before/after metrics.
17. **Never tweak hidden parameters casually.** Follow official documentation and Oracle Support guidance when needed.
18. **Re-verify after upgrades or container migrations.** OS memory visibility and optimizer/runtime behavior can change.

## 28. Self-Check Questions

1. How do SGA and PGA differ in sharing scope?
2. What functions do the major SGA components serve?
3. Why can shared pool pressure cause `ORA-04031`?
4. Which operations use PGA work areas?
5. How do optimal, one-pass, and multi-pass work area executions differ?
6. Why does rising TEMP usage not automatically mean the TEMP tablespace is misconfigured?
7. Where does UGA reside under dedicated server vs. shared server?
8. How does manual memory management differ from ASMM?
9. Which components does ASMM tune, and which parameter manages PGA?
10. How does AMM differ from ASMM?
11. How do `SGA_TARGET` and `SGA_MAX_SIZE` differ?
12. Is `PGA_AGGREGATE_TARGET` a hard limit?
13. What does `PGA_AGGREGATE_LIMIT` protect against?
14. How do `MEMORY_TARGET` and `MEMORY_MAX_TARGET` differ?
15. Why is ASMM commonly chosen when Linux HugePages is needed?
16. Why does AMM on Linux require a sufficiently large `/dev/shm`?
17. What conditions typically trigger `ORA-00845`?
18. How does HugePages benefit the SGA, and does it apply directly to PGA?
19. Why should you not sum RSS across all Oracle processes to calculate total SGA?
20. How does `MemAvailable` differ from `MemFree` on Linux?
21. How does sustained swapping affect Oracle?
22. How does parallel query alter peak PGA?
23. How do `V$PGASTAT` and `V$PROCESS` provide different perspectives?
24. How does `V$SQL_WORKAREA_ACTIVE` help detect TEMP spills?
25. Why do advisors not replace OS memory monitoring?
26. How does `ORA-04030` differ from `ORA-04036`?
27. When should you inspect `V$MEMORY_RESIZE_OPS`?
28. What should be recorded before changing memory parameters?

## 29. Mental Model Summary

```text
HOST RAM
   |
   +-- OS / Kernel / Page cache / Agents / ASM
   +-- Safety headroom
   |
   v
ORACLE INSTANCE
   |
   +-- SGA (shared)
   |     +-- Buffer Cache
   |     +-- Shared Pool
   |     +-- Redo Buffer
   |     +-- Large / Java / Streams Pool
   |
   +-- PGA (private per process)
         +-- Process/session memory
         +-- Sort / Hash work areas
         +-- Untunable allocations
   |
   v
MEMORY MANAGEMENT
   |
   +-- Manual: DBA sizes components/work areas
   +-- ASMM: SGA_TARGET + PGA_AGGREGATE_TARGET
   +-- AMM: MEMORY_TARGET + MEMORY_MAX_TARGET
   |
   v
OS TRADE-OFFS
   |
   +-- HugePages: suited to SGA, usually paired with ASMM
   +-- AMM Linux: requires /dev/shm, incompatible with HugePages
   +-- PGA concurrency and parallelism
   +-- Swap / OOM / container limits
   |
   v
OBSERVABILITY
   |
   +-- V$SGAINFO / V$SGASTAT / resize views
   +-- V$PGASTAT / V$PROCESS / workarea views
   +-- Advisor + actual workload
   +-- OS metrics with matching timestamps
```

**Key takeaway:** SGA is instance-shared memory, while PGA is process-private memory. ASMM tunes the SGA while PGA is managed separately; AMM tunes combined SGA/PGA under one target. Every target must fit within the host RAM budget after reserving for the OS and other workloads. Sizing for peak concurrency, monitoring TEMP/OS pressure, and measuring before and after changes matter far more than chasing a fixed memory number.
