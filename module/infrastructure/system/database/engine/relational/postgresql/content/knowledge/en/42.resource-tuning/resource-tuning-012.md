# Benchmarking with pgbench, Realistic Scenarios, and Bias Control

`pgbench` is the benchmarking tool bundled with PostgreSQL. It simulates multiple database clients repeatedly running one or more transaction scripts, then reports throughput (transactions per second — TPS), latency, failed transactions, and related statistics. The tool includes a built-in TPC-B-like workload for quick baselines while letting you write custom scripts to model application behavior.

A high TPS number does not automatically prove a database is better. Results are only meaningful when the workload represents the real system, the dataset is appropriately sized, concurrency is chosen intentionally, cache and vacuum states are controlled, the load generator does not become the bottleneck, and runs are fairly comparable.

```text
  Application / real workload
              |
              v
  +--------------------------+
  | pgbench clients          |
  | scripts, rate, concurrency|
  +------------+-------------+
               |
               v
  +--------------------------+
  | PostgreSQL server        |
  | CPU / memory / locks     |
  | buffers / WAL / storage  |
  +------------+-------------+
               |
       +-------+--------+
       |                |
       v                v
  pgbench results   server/OS metrics
       |                |
       +-------+--------+
               |
               v
  Compare repeated runs and explain variance
```

This lesson belongs to the **Resource Tuning** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on designing an explainable and reproducible benchmark experiment: starting from a baseline, crafting workloads close to business logic, ramping load in steps, measuring latency alongside throughput, controlling cache/data drift, and correlating server-side metrics.

After this lesson, you will be able to:

1. Distinguish a `pgbench` baseline from a benchmark modeling a real application.
2. Initialize datasets and choose an appropriate scale factor.
3. Write custom transaction scripts with realistic access distributions.
4. Choose client counts, threads, duration, protocol, and target rate.
5. Read TPS, latency, standard deviation, failures, retries, and schedule lag.
6. Collect transaction logs, per-command metrics, and server-side telemetry.
7. Control cache state, autovacuum, dead tuples, checkpoints, and data growth.
8. Repeat experiments, record variance, and avoid cherry-picking the best run.
9. Detect when the `pgbench` client or network becomes the bottleneck.
10. Compare two configurations using identical workloads and test conditions.

> **Safety scope:** Run write benchmarks only on an authorized lab or staging database. `pgbench -i` drops and recreates tables named `pgbench_*`; never run it on a database holding real data with those table names. High-load workloads can elevate CPU, I/O, WAL, replication lag, and latency for shared services.

---

## 1. Benchmarking Is a Controlled Experiment

### 1.1. What Does a Benchmark Measure?

A benchmark generates intentional load to measure how the system responds. For PostgreSQL, we typically look at:

- **Throughput:** transactions completed per second.
- **Latency:** time a client waits for a transaction to finish.
- **Concurrency:** number of simultaneous sessions/clients.
- **Failure rate:** fraction of transactions failing, deadlocking, or hitting serialization errors.
- **Resource usage:** CPU, memory, storage I/O, network, WAL, and locks.
- **Scalability:** how throughput and latency change as client count or data volume grows.

No single metric describes all of performance. High TPS with huge p99 latency may fail interactive applications; low latency with one client does not prove the system handles hundreds of sessions.

### 1.2. Define the Question First

Before running `pgbench`, write down the exact benchmark question:

- Does the new server increase TPS compared to the old server?
- Does the new index reduce read query latency?
- Does the new `work_mem` reduce temporary I/O in reporting workloads?
- Does the new storage improve throughput when data exceeds RAM?
- Does connection pooling cut overhead under frequent new connections?
- Does the configuration keep p95/p99 within target at 100 clients?

Each experiment should vary one primary factor. Changing CPU, storage, PostgreSQL version, schema, indexes, and scripts all at once leaves you unable to attribute the result.

### 1.3. Workload Determines the Result

A database can perform great on `SELECT` point lookups yet stall on concurrent `UPDATE`s hitting the same locks. It can also fly when data fits in RAM yet crawl once the working set exceeds memory.

Therefore, the workload must capture:

- Read/write ratio.
- Transaction size and SQL statements per transaction.
- Key access distribution: uniform vs. skewed toward hot records.
- Data size and working set.
- Concurrency level.
- Rate of new connections vs. reused connections.
- Consistency/locking requirements.
- Background activity such as vacuum, checkpoints, and replication.

### 1.4. Benchmarking Is Not Production Traffic Replay

`pgbench` is a script-driven load generator. It does not automatically reproduce full application behavior such as connection pools, app-tier caches, ORMs, network hops, payload serialization, retry policies, or user think time.

To simulate closer to production, build transaction scripts from critical business flows and pair with application-layer load testing when measuring end-to-end behavior.

### 1.5. Match the Workload to the Goal

| Goal | Suitable Workload |
|---|---|
| OLTP throughput | Short transactions mixing SELECT/INSERT/UPDATE |
| Read-heavy | Point lookups, range scans, list/search, joins |
| Write-heavy | INSERT/UPDATE following realistic key distributions |
| Hot-row contention | Many clients updating a shared set of keys |
| Reporting | Aggregations, sorts, joins, and large data scans |
| Connection overhead | New connection per transaction or running through a pool |
| I/O capacity | Dataset/working set larger than cache with representative access |

---

## 2. Understanding the Default pgbench Workload

### 2.1. Built-In TPC-B-Like Script

By default, `pgbench` runs a TPC-B-like transaction consisting of:

1. Updating an account balance.
2. Reading back the account balance.
3. Updating the teller balance.
4. Updating the branch balance.
5. Inserting a row into history.

This is a mixed read/write transactional workload with contention on specific tables. It is described as **TPC-B-like**, not an official TPC-B benchmark and not a certified TPC result.

### 2.2. Tables Created by pgbench

`pgbench -i` creates four tables:

| Table | Role |
|---|---|
| `pgbench_accounts` | Account rows; largest table |
| `pgbench_branches` | Branch balances |
| `pgbench_tellers` | Teller balances |
| `pgbench_history` | Transaction history; grows continuously during runs |

At scale factor 1, `pgbench_accounts` has 100,000 rows, `pgbench_branches` has 1 row, and `pgbench_tellers` has 10 rows. Scale factor scales row counts proportionally.

### 2.3. Initializing Data

First create a dedicated benchmark database. Then run:

```bash
createdb benchdb
pgbench -i -s 10 -h db-host -p 5432 -U bench_user benchdb
```

`-i` invokes initialization mode; `-s 10` builds a scale-10 dataset. Pick scale factor based on RAM, storage, and planned client count. Initialization drops existing `pgbench_*` tables of the same name before recreating them.

### 2.4. Destructive Warning for -i

Never run `pgbench -i` inside an application database if it contains tables named `pgbench_accounts`, `pgbench_branches`, `pgbench_history`, or `pgbench_tellers` that you need to keep. Creating a separate benchmark database is safer and easier to reproduce.

### 2.5. Scale Factor and Hot Branch Contention

In the default workload, every transaction updates one branch row and one teller row. The number of branch rows equals the scale factor. If `-c` greatly exceeds `-s`, many clients contend on the same rows, turning the benchmark primarily into a lock-contention test.

For the built-in TPC-B-like workload, PostgreSQL docs recommend a scale factor at least equal to the maximum number of clients you plan to test. This prevents artificial contention from an undersized dataset, rather than serving as a universal rule for custom workloads.

### 2.6. Built-In Scripts

`pgbench` provides:

- `tpcb-like`: default workload with SELECT/UPDATE/INSERT.
- `simple-update`: skips the two teller/branch updates, reducing contention on those tables.
- `select-only`: runs only account `SELECT`s.

Examples:

```bash
pgbench -b tpcb-like -c 16 -j 4 -T 180 benchdb
pgbench -b simple-update -c 16 -j 4 -T 180 benchdb
pgbench -b select-only -c 16 -j 4 -T 180 benchdb
```

`-N` is equivalent to `simple-update`; `-S` is equivalent to `select-only`.

### 2.7. Why Built-Ins Are Not Enough for Every System

The default workload lacks your business schema, join patterns, JSON processing, search, tenant skew, transaction boundaries, and business operation ratios. It is useful for:

- Baseline PostgreSQL and infrastructure sanity checks.
- Quick apples-to-apples server comparisons under identical settings.
- Observing concurrency and storage effects.
- Finding broad server limits.

Never use a single built-in result to directly predict how many requests/second your real application can serve.

---

## 3. Preparing the Benchmark Environment

### 3.1. Separate the Benchmark Database

Use a dedicated lab/staging database to:

- Avoid overwriting application tables.
- Cleanly create and reset datasets.
- Allow running initialization/vacuum freely.
- Easily record data state between runs.
- Reduce risk of impacting real users.

### 3.2. Check pgbench and Server Versions

On the client machine:

```bash
pgbench --version
psql --version
```

Connected to the server:

```sql
SELECT version();
SHOW server_version;
SHOW block_size;
```

Record client utility and server versions separately. Do not assume matching major version is enough; newer `pgbench` flags may not exist in an older client binary.

### 3.3. Verify Connectivity

```bash
pgbench -h db-host -p 5432 -U bench_user -d benchdb --client=1 --time=10
```

Run a brief smoke test to confirm DNS, port, authentication, privileges, and network path. This is a connectivity check, not performance data.

### 3.4. Safe Privileges and Schemas

The benchmark role needs privileges on the test dataset's tables and sequences. Use a dedicated role scoped to the lab database/schema.

`pgbench` uses unqualified table names in built-in scripts and does not alter `search_path`. Do not run `pgbench` in a database with unsafe schema usage for untrusted users. In custom scripts, schema-qualify table names to minimize `search_path` ambiguity.

### 3.5. Where to Run pgbench

Running `pgbench` directly on the database server makes client processes compete with PostgreSQL for CPU, memory, and network. At high client counts, `pgbench` can become the bottleneck and under-report server capacity.

For measuring server throughput:

- Run `pgbench` on a separate host in the same network/VPC or low-latency LAN.
- Monitor CPU and network on the client host.
- Ensure the client host has enough CPUs/threads to drive the load.
- If needed, use multiple load generator hosts and aggregate results.

If your goal is end-to-end measurement from a laptop or remote location, keep that path fixed and record RTT; results then include network latency.

### 3.6. Record Configuration Before Running

Capture:

- CPU model, core/vCPU count, and memory.
- Storage type, IOPS/throughput/latency, and filesystem.
- OS/kernel and container/cgroup limits.
- PostgreSQL version/build and extensions.
- Memory, WAL, checkpoint, autovacuum, and parallelism parameters.
- Dataset size, row counts, indexes, and statistics.
- `pgbench` version, exact command line, script files, and random seeds.
- Client host placement and network path.

Never compare two results if one ran on different storage/networking without noting it.

---

## 4. Key pgbench Options

### 4.1. Clients and Threads

| Option | Meaning |
|---|---|
| `-c N` | Number of concurrent client sessions |
| `-j N` | Number of `pgbench` worker threads |

For example, `-c 64 -j 8` creates 64 client sessions managed across 8 `pgbench` threads. `-j` is not PostgreSQL's parallel worker count; it controls threads inside the benchmark tool.

### 4.2. Duration or Transaction Count

| Option | Meaning |
|---|---|
| `-T 180` | Run for 180 seconds |
| `-t 1000` | Each client runs 1000 transactions |

`-T` and `-t` are mutually exclusive. For steady-state comparison benchmarks, `-T` ensures each configuration runs for the same duration.

### 4.3. Progress

`-P 10` prints progress every 10 seconds, showing TPS and average/stddev latency for the latest interval. Progress output reveals how throughput/latency shift over time, such as once caches warm up or when autovacuum kicks in.

### 4.4. Protocol Mode

```bash
pgbench -M simple -c 16 -T 120 benchdb
pgbench -M extended -c 16 -T 120 benchdb
pgbench -M prepared -c 16 -T 120 benchdb
```

Modes:

- `simple`: simple query protocol.
- `extended`: extended query protocol.
- `prepared`: extended protocol with prepared statements.

Prepared mode can be faster by reusing parse analysis results after the first execution. Pick the mode matching your real driver/application. Never compare two configurations where one used `simple` and the other `prepared` unless intentionally measuring protocol overhead.

### 4.5. New Connection per Transaction

`-C` opens a fresh connection for every transaction instead of holding one connection per client session:

```bash
pgbench -C -c 32 -j 4 -T 120 benchdb
```

Useful for measuring connection/authentication overhead. If your application uses a connection pool to reuse connections, do not use `-C` as your sole workload.

### 4.6. Rate Control

`-R rate` tells `pgbench` to launch transactions at a target transactions/second rate:

```bash
pgbench -R 500 -c 64 -j 8 -T 180 benchdb
```

Without `-R`, clients start the next transaction immediately when the prior one finishes; this is closed-loop load. With `-R`, `pgbench` schedules transaction starts as a Poisson process to control offered load.

### 4.7. Latency Limit

`-L milliseconds` marks transactions exceeding the latency threshold as late. Combined with `-R`, transactions already past the limit before dispatch are skipped and never sent to the server.

Never use `-L` to prettify metrics. Always report late/skipped counts alongside TPS and latency so readers know how much work was actually processed.

### 4.8. Logging

- `-l`: logs individual transaction details.
- `--aggregate-interval=seconds`: logs aggregated interval statistics when using `-l`.
- `--sampling-rate=0.05`: logs only a sampled fraction of transactions.
- `-r`: reports average latency per command/statement after the benchmark.

Logging adds overhead and disk I/O. Measure one run with logging and one without to gauge impact; use sampling when full transaction logs grow too large.

### 4.9. Retries and Failures

By default `--max-tries=1`, meaning serialization/deadlock errors are not retried. You can configure retries, but you must report retried transactions, retry counts, and failures. Latency of a retried transaction includes prior attempts.

Never raise retries merely to make failure counts look smaller; reflect your real application's retry policy.

---

## 5. Reading pgbench Output

### 5.1. Basic Output

A run typically reports:

- Transaction type/script.
- Scale factor.
- Query protocol mode.
- Number of clients and threads.
- Target and actual transactions processed.
- Failed transactions.
- Latency average and standard deviation.
- Initial connection time.
- TPS.

Save the complete output alongside the exact command line; never record just the final TPS number.

### 5.2. Transactions per Second

TPS is the throughput observed by `pgbench` during the run. In mixed workloads, one transaction may execute multiple SQL statements; TPS does not equal SQL statements/second or HTTP requests/second.

When comparing two results, verify transaction scripts and boundaries match. If one script runs 2 statements and another runs 12, TPS cannot be compared directly as identical units of work.

### 5.3. Latency Average

Average latency is the mean transaction duration from the client's perspective. It includes network round trips and waiting per benchmark configuration. With rate limiting, latency is measured from scheduled start time and thus includes schedule lag.

### 5.4. Standard Deviation

Standard deviation shows latency variability. Low mean with high standard deviation can reflect instability, outliers, lock contention, background I/O, or cache effects.

### 5.5. p95 and p99

Standard `pgbench` summary output reports average and standard deviation; never extrapolate p95/p99 from those two numbers.

To analyze tail latency:

- Enable transaction logs with `-l`.
- Pick a suitable sampling rate if logs are huge.
- Parse transaction durations from the logs using external tools.
- Or use `--aggregate-interval` to track latency shifts over intervals, noting that aggregated logs lose per-transaction distributions.

When reporting p95/p99, state the calculation method, sample count, and how failed/skipped transactions were handled.

### 5.6. Initial Connection Time

Initial connection time is the time spent opening client connections at startup. When clients hold connections for the entire test, this setup time is separated from final TPS. To measure connection churn, use `-C` and analyze separately.

### 5.7. Failures and Retries

Always inspect:

- Actual transactions processed.
- Failed transactions and failure percentage.
- Serialization failures.
- Deadlocks.
- Retried transactions and retry counts.
- Skipped transactions when using rate/latency limits.

High TPS with many failed transactions is not a successful benchmark.

### 5.8. Per-Command Latency

`-r` reports average latency per statement/command. It helps pinpoint which `UPDATE` or `SELECT` takes most of the time in a script.

Per-command timing introduces overhead. Measure the impact of `-r` by comparing runs with and without it; never treat per-command results as zero-overhead instrumentation.

### 5.9. Interpreting Rate-Controlled Results

When using `-R`, also check:

- Average/max schedule lag.
- Late transactions.
- Skipped transactions.
- Actual transactions completed.
- Latency from scheduled start.

Continuously climbing schedule lag indicates the system cannot sustain the target rate with the current client/thread count. Lower target rate or increase capacity; never mistake reported latency for pure server execution time.

---

## 6. Designing Realistic Custom Scripts

### 6.1. When Do You Need Custom Scripts?

Use custom scripts when the built-in workload fails to reflect:

- Real schemas and indexes.
- `SELECT`/`INSERT`/`UPDATE`/`DELETE` ratios.
- Multi-step transactions.
- Joins and aggregations.
- Tenant/customer distributions.
- Hot keys.
- Varied query parameters and payload sizes.

Custom scripts should stem from high-frequency or high-impact business flows.

### 6.2. Script Structure

A `pgbench` script is a text file containing semicolon-terminated SQL statements and optional backslash-prefixed meta-commands. Each execution of a script file counts as one transaction in `pgbench`; scripts must leave transaction blocks cleanly closed.

Variables are assigned via `\set` or `-D` and referenced in SQL as `:variable_name`.

### 6.3. Account Read Workload Example

File `read_account.sql`:

```sql
\set account_id random(1, 1000000)
SELECT account_id, balance, updated_at
FROM bench.accounts
WHERE account_id = :account_id;
```

Simulates a uniform point lookup. The table requires a primary key or index on `account_id`.

### 6.4. Account Write Workload Example

File `update_account.sql`:

```sql
\set account_id random_zipfian(1, 1000000, 1.07)
\set delta random(1, 100)
UPDATE bench.accounts
SET balance = balance + :delta,
    updated_at = clock_timestamp()
WHERE account_id = :account_id;
```

Uses a Zipfian distribution to make some accounts hotter than others, mirroring workloads where certain customers or accounts are disproportionately active.

### 6.5. Order Listing Workload Example

File `list_orders.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount, created_at
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

An appropriate index would be `(customer_id, created_at DESC)`. Keep the same schema/index policy across compared configurations.

### 6.6. Order Creation Example

File `create_order.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
\set total_amount random(100, 100000)
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
VALUES
    (:customer_id, 'created', :total_amount, clock_timestamp());
```

This transaction inserts new data. Every benchmark grows the table, so reset/restore the dataset or control data growth between runs.

### 6.7. Running Multiple Weighted Scripts

You can mix scripts with weights:

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -f update_account.sql@1 -c 32 -j 8 -T 300 benchdb
```

Weights 7:2:1 yield selection probabilities of roughly 70% list reads, 20% order inserts, and 10% account updates. These are selection probabilities, not guaranteed exact ratios over short windows.

### 6.8. Multi-Statement Transactions

When business logic needs multiple atomic steps, place them in one script transaction. Example:

```sql
\set account_id random(1, 1000000)
\set amount random(1, 500)
WITH changed AS (
    UPDATE bench.accounts
    SET balance = balance - :amount
    WHERE account_id = :account_id
      AND balance >= :amount
    RETURNING account_id
)
INSERT INTO bench.account_events(account_id, amount, created_at)
SELECT account_id, :amount, clock_timestamp()
FROM changed;
```

The CTE ensures an event is inserted only if the `UPDATE` modified a row. This is one atomic SQL statement preserving the example's business invariant. Never oversimplify logic and claim the result represents full application workloads.

### 6.9. SQL and Meta-Commands

Useful meta-commands:

- `\set`: assigns a variable using a `pgbench` expression.
- `\if` / `\elif` / `\else` / `\endif`: conditional logic in scripts.
- `\gset`: stores query result columns into variables.
- `\sleep`: simulates think time between steps.
- `\startpipeline` / `\endpipeline`: sends statements via extended protocol pipelining.

Avoid shell meta-commands that cause external side effects inside retried transactions; external side effects do not roll back like SQL.

### 6.10. Test Scripts Before Benchmarking

Run one client briefly and verify:

- SQL syntax and schema-qualified names.
- Row counts and resulting data after transactions.
- Constraints and foreign keys.
- Query success rate.
- Transaction boundaries.
- No unexpected data growth.

Only scale concurrency after single-client execution works cleanly.

---

## 7. Data Distributions and Access Patterns

### 7.1. Uniform Distribution

`random(min, max)` picks values uniformly across the range. Suitable when every record has roughly equal access probability.

Example:

```sql
\set account_id random(1, 1000000)
SELECT balance
FROM bench.accounts
WHERE account_id = :account_id;
```

### 7.2. Zipfian Distribution

In real systems, certain products, accounts, or tenants are accessed far more often than others. Zipfian distribution models that skew:

```sql
\set customer_id random_zipfian(1, 1000000, 1.10)
SELECT customer_id, profile
FROM bench.customers
WHERE customer_id = :customer_id;
```

Higher skew parameters concentrate selections even more tightly near the start of the range. Base parameters on real telemetry where available instead of inventing extreme hotspots arbitrarily.

### 7.3. Gaussian and Exponential Distributions

`pgbench` also provides `random_gaussian` and `random_exponential`. These help model:

- Access clustered around popular values.
- Rapid decay from hot keys to rare keys.
- Non-uniform access ranges.

### 7.4. Correlation Between Keys and Physical Row Order

With non-uniform distributions, frequently picked keys may correlate with sequential IDs or physical heap ordering, artificially improving or hurting locality.

Use `permute` or a shuffle step to scatter hot keys if you want to remove unintended correlation. `pgbench`'s `permute` function creates a bijective permutation across the range without duplicates or gaps.

### 7.5. Working Set

The working set is the subset of data frequently touched by the workload. A dataset may be huge overall, yet if only a small slice of rows is queried, the working set fits in RAM.

Dataset design must distinguish:

- Total database size.
- Table/index sizes.
- Frequently accessed working set.
- `shared_buffers`.
- OS page cache.
- RAM available to PostgreSQL vs. other processes.

### 7.6. Dataset Smaller Than RAM

If dataset and indexes fit in memory, post-warmup benchmarks mainly measure CPU, locking, executor, network, and memory speed. Numbers can look far rosier than production workloads whose working sets exceed RAM.

### 7.7. Dataset Larger Than RAM

To measure storage/I/O behavior, build a dataset and working set exceeding available cache. Do not just create a giant table while hitting the same handful of keys; ensure the access pattern actually touches wide page ranges.

### 7.8. Data Skew and Tenant Skew

For SaaS/multi-tenant workloads, model:

- Many small tenants and a few huge tenants.
- One tenant driving most writes.
- Larger tenants carrying more secondary indexes/rows.
- Fan-out queries across tenants.

A uniform tenant distribution can hide production hotspots and lock contention.

### 7.9. Transaction Size

A 1-statement transaction behaves very differently from a 10-statement transaction updating multiple indexes. Measure:

- Small, frequent transactions.
- Medium read/write transactions.
- Multi-row batch transactions.
- Long-running reports.

If the application commits in batches, benchmark scripts should preserve similar transaction boundaries.

### 7.10. Data Growth and Churn

`UPDATE`/`DELETE` workloads generate dead tuples and index churn. Continuous `INSERT` workloads expand tables and shift page layouts. If each benchmark run starts from a different dataset size, comparisons lose fairness.

Decide explicitly:

- Test steady-state on a fixed-size dataset, or
- Test growth/ingestion over a defined window.
- Whether datasets reset between runs.
- Whether vacuum/autovacuum runs as in production or is controlled out.

---

## 8. Stepping Up Concurrency

### 8.1. Do Not Start at Maximum Clients

Start at low concurrency to establish a baseline, then ramp up. Illustrative progression:

| Run | Clients |
|---|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 4 |
| 4 | 8 |
| 5 | 16 |
| 6 | 32 |
| 7 | 64 |
| 8 | 96 |

This sequence is not mandatory; adapt to core counts, connection limits, and production load. Use finer steps around the throughput saturation knee.

### 8.2. Throughput Curve

At low concurrency, adding clients raises TPS as CPU/storage utilize spare capacity. At saturation, TPS slows or plateaus; adding further clients drives latency up and can trigger failures or lock waits.

```text
TPS
 ^
 |                         ________
 |                    ____/
 |               ____/
 |          ____/
 |     ____/
 |____/
 +---------------------------------> Clients
       rising      saturation
```

Real curves often dip past saturation if contention, context switching, or resource pressure spikes.

### 8.3. Latency Curve

Latency climbs once concurrency exceeds processing capacity. Track both average and tail latency; averages can look calm while a fraction of requests stalls badly.

### 8.4. Finding the Saturation Point

Saturation appears when:

- TPS barely rises despite more clients.
- Latency starts climbing steeply.
- CPU nears capacity or I/O wait surges.
- Lock waits, queueing, or connection waits grow.
- Schedule lag rises in rate-controlled tests.

Never pick a client count just because it is the highest `pgbench` can sustain. Pick operating levels matching peak concurrency and desired headroom.

### 8.5. Distinguishing Clients and Threads

`-c` sets client sessions; `-j` sets `pgbench` worker threads. Raise threads when the load generator has multiple CPU cores and client scheduling becomes a bottleneck. Never change both clients and threads together if isolating one factor.

### 8.6. Connection Limits

Client counts should not wildly exceed realistic server/pool limits. Benchmarking 500 direct sessions when production runs a 40-connection pool tests a different workload.

Check:

```sql
SHOW max_connections;

SELECT count(*) AS current_connections
FROM pg_stat_activity;
```

With PgBouncer or managed pools, benchmark through the same endpoint applications use when testing end-to-end connection paths.

### 8.7. Queueing and Saturation

Once service rate maxes out, incoming requests queue. Adding concurrency spikes latency with zero TPS gain. Measure this saturation curve to learn capacity limits—not as an excuse to blindly raise `max_connections`.

---

## 9. Closed-Loop vs. Rate-Controlled Workloads

### 9.1. Default Closed-Loop

Without `-R`, each `pgbench` client starts its next transaction right after the previous one finishes. When latency rises, client submission rate drops automatically.

This is a closed-loop model. It measures peak throughput at a fixed client count, yet masks queueing that occurs under independent arrival rates.

### 9.2. Rate-Controlled Workloads

`-R` sets a target transactions/second rate. `pgbench` schedules starts via a Poisson process, closely modeling independent arrival rates.

Example:

```bash
pgbench -R 300 -c 48 -j 8 -T 300 -P 10 benchdb
```

If 300 TPS exceeds system capacity, schedule lag rises and latency measured from scheduled start includes queue wait time.

### 9.3. Schedule Lag

Schedule lag is the gap between when a transaction was scheduled to start and when a client actually started it. This is a critical signal showing whether the server or load generator is falling behind the offered rate.

When schedule lag is high:

- The server may be saturated.
- Client count `-c` may be too small to sustain the target rate.
- `pgbench` worker threads or the client host may be bottlenecked.
- Transaction duration may exceed inter-arrival spacing.

### 9.4. Choosing Rate to Test SLOs

If an application targets 250 TPS with p95 latency under 100 ms, run rate-controlled tests around that load and measure tail latency. Then step up the target rate to locate where latency or failures breach thresholds.

Do not pick a tiny rate and claim massive headroom, nor crank rates far past reality without stating the stress-test objective.

### 9.5. Late and Skipped Transactions

Combining `-L` with `-R` marks transactions late and skips transactions already overdue before dispatch. Report skipped counts; they never hit the database and must not be counted as completed work.

### 9.6. Arrival Rate Is Not Concurrency

Target TPS is transaction start rate; client count is maximum simultaneous sessions. The same target rate requires different client counts depending on latency. Never equate 300 TPS with 300 clients.

### 9.7. When to Use Each Model

| Goal | Model |
|---|---|
| Find peak throughput for N clients | Closed-loop |
| Verify SLO at a defined offered load | Rate-controlled |
| Model burst/arrival behavior | Rate-controlled with fitting scripts |
| Measure connection creation cost | Combine with `-C` |
| Find concurrency/lock limits | Closed-loop client sweep |

---

## 10. Warm-Up, Cache State, and Cold-Start Bias

### 10.1. Shared Buffers and OS Page Cache

PostgreSQL reads pages through `shared_buffers`, while the OS maintains its page cache. Initial reads may hit storage; subsequent runs hit `shared_buffers` or OS cache.

Consequently, the first run and later runs can perform dramatically differently even with identical SQL and data.

### 10.2. Warm-Up Phase

For steady-state benchmarks:

1. Initialize/restore the dataset.
2. Run a warm-up workload.
3. Discard warm-up metrics.
4. Run a sufficiently long measured interval.
5. Track cache hits, I/O, and latency over time.

Warm-up should mirror the measured workload so the right working set loads into cache.

### 10.3. Do Not Assume First Run Means Cold Cache

Restarting PostgreSQL empties `shared_buffers`, yet leaves the OS page cache intact. Thus a server restart does not guarantee a comparable cold-storage benchmark.

True cold-cache testing requires dedicated environments and cache control across PostgreSQL, OS, and storage. Never drop OS caches in production; it disrupts other processes and causes outages/regressions.

### 10.4. Datasets Exceeding RAM

To measure storage-bound workloads, use a dataset larger than cache capacity and query across a broad working set. A huge table where queries repeatedly touch a tiny hot slice still stays cached.

### 10.5. Warm Cache vs. Cold Cache Answer Different Questions

| Test Type | Question |
|---|---|
| Warm cache | How does the system behave once the working set is cached? |
| Cold/first-touch | How does the system respond when data is not yet in cache? |
| Mixed cache | How does the system behave at production-like hit/miss ratios? |

Never average these three together when they represent distinct operational regimes.

### 10.6. Cache State Across A/B Runs

When comparing configs A and B, running A warmed up and B right after a restart skews results. Apply identical warm-up protocols and cache-state targets to both.

### 10.7. Measuring Cache Hits and Read I/O

Inspect `pg_stat_database`:

```sql
SELECT
    datname,
    blks_hit,
    blks_read,
    round(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS cache_hit_pct,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
```

These are cumulative counters. Take snapshots before and after the benchmark to compute deltas; never compare raw cumulative counts across runs without subtracting baselines or resetting.

---

## 11. Vacuum, Dead Tuples, and Data State

### 11.1. Updates Create Dead Tuples

PostgreSQL uses MVCC. `UPDATE`/`DELETE` creates new row versions or marks old versions invisible to newer transactions. Dead tuples and dead index entries accumulate until vacuumed.

Hence, running the same benchmark on a fresh table vs. one after millions of updates produces different results.

### 11.2. Autovacuum Affects Results

Autovacuum may trigger during a measured window, competing for CPU/I/O. This is not necessarily noise to delete: in production, autovacuum is part of the system. Decide your goal:

- **Production-like:** leave autovacuum configured like production and record when it runs.
- **Isolated microbenchmark:** control vacuum state to isolate one variable, while not claiming it represents production.

### 11.3. Recording Vacuum Timing

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Compare before and after benchmarks to see which tables gained dead tuples or were vacuumed during the window.

### 11.4. Do Not Use VACUUM FULL as Warm-Up

`VACUUM FULL` rewrites tables, takes strong locks, and alters physical layout. It is not a standard pre-benchmark cleanup step. Use `VACUUM`/`ANALYZE` purposefully and keep procedures identical across runs.

### 11.5. Analyze and Planner Statistics

If data changed substantially, run `ANALYZE` before benchmarking so the planner has accurate statistics:

```sql
ANALYZE bench.accounts;
ANALYZE bench.orders;
```

Never test one configuration with fresh statistics and the other with stale statistics. For skewed/correlated workloads, include extended statistics if production uses them.

### 11.6. Index Bloat and Table Bloat

Prolonged update-heavy workloads build bloat. Comparing one run on compact indexes against another after heavy churn skews results. Use snapshots/restores or standardized dataset resets between runs.

### 11.7. History Tables Grow Continuously

In built-in `pgbench`, `pgbench_history` grows with transaction count. Without consistent resets/re-initialization, table/index sizes and cache footprints drift across runs.

### 11.8. Autovacuum Is Not Always Noise to Disable

Disabling autovacuum makes short runs look faster while hiding long-term operational trouble. For production capacity testing, keep autovacuum enabled and observe its impact.

---

## 12. Repetition and Bias Control

### 12.1. Do Not Trust a Single Short Run

Runs lasting a few seconds are hypersensitive to scheduler jitter, cache warm-up, checkpoints, background tasks, and connection setup. PostgreSQL docs recommend running at least several minutes and repeating; some systems need longer for stability.

### 12.2. Exclude Warm-Up from Measured Runs

Separate:

- Initialization/setup.
- Warm-up.
- Measurement.
- Cool-down/restore.

Log exact durations for every phase. Never quietly include warm-up in primary throughput numbers.

### 12.3. Repeat Multiple Times

Run each configuration multiple times under identical conditions. Report median, range, or interquartile range alongside run count. If variance is wide, investigate the cause rather than picking the fastest run.

### 12.4. Randomize A/B Order

Always running A before B can give B warmer caches or different background load. Alternate A/B and B/A or randomize order across rounds to cancel time-order bias.

### 12.5. Paired Runs

If you can restore the same dataset snapshot, run A and B from identical data state. Compare time-adjacent pairs rather than comparing A from morning against B from evening.

### 12.6. Change One Primary Variable

Example evaluating an index:

1. Hold hardware, PostgreSQL config, dataset, and scripts constant.
2. Run baseline without the new index.
3. Create the index.
4. Run `ANALYZE` identically.
5. Run identical warm-up.
6. Run the measured workload.
7. Repeat and compare latency, TPS, buffers, write cost, and storage size.

Never change `work_mem`, `shared_buffers`, indexes, and client count simultaneously.

### 12.7. Keep Transaction Mix Constant

If A runs 80% SELECT / 20% UPDATE and B runs 95% SELECT / 5% UPDATE, TPS differs simply because work differs. Use identical script weights and parameter distributions.

### 12.8. Random Seed

`--random-seed` makes random sequences reproducible under controlled conditions. Fixed seeds help debug specific cases or run paired comparisons.

However, repeating the exact same seed hides workload variance and favors caching the same pages. Use varied seeds (recording each) for variability analysis, and fixed seeds for paired diagnostics when needed.

### 12.9. Avoid Unintended System Changes

During every measured interval, log:

- Backups, replication, autovacuum, checkpoints.
- Other deployments/application traffic.
- Cloud noisy neighbors or CPU throttling.
- Storage burst credits/throttling.
- Network congestion.
- Autoscaling or VM live migrations.

If a major event occurs, mark that run non-comparable or re-run per protocol.

### 12.10. Small Differences May Just Be Noise

If A beats B by 2% while run-to-run variance is 8%, there is insufficient evidence that A is better. Increase repetitions, extend duration, or eliminate noise sources.

---

## 13. Collecting PostgreSQL-Side Metrics

### 13.1. pg_stat_database

Take before/after snapshots:

```sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

Cumulative counters verify how much actual work ran. Compute deltas between snapshots for the measured interval.

### 13.2. pg_stat_activity and Wait Events

During the benchmark:

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS backends
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY backends DESC;
```

Many backends waiting on `Lock` indicate contention. Waiting on `IO` points to storage; `active` with no wait indicates CPU or executor work.

### 13.3. pg_stat_statements

If enabled, snapshot query stats before/after to find query groups with high:

- Total execution time.
- Call counts.
- Shared blocks read.
- Temporary blocks.
- WAL bytes.
- Planning time if tracked.

Combine `queryid` and query text to identify SQL; never assume `queryid` stays stable across major versions.

### 13.4. pg_stat_io

PostgreSQL 16+ provides `pg_stat_io` to inspect I/O activity by backend type, object, and context:

```sql
SELECT
    backend_type,
    object,
    context,
    reads,
    read_time,
    writes,
    write_time,
    fsyncs,
    fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Verify the view schema for your major version before building cross-version dashboards. `pg_stat_io` is server-level and does not attribute I/O directly to one query.

### 13.5. WAL and Checkpoints

Monitor:

- WAL bytes/records generated.
- Archive backlog and replication lag.
- Checkpoint frequency and write pressure.
- WAL buffers/checkpoint writes.
- `pg_wal` disk free space.

A write-heavy benchmark can be limited by WAL flush or checkpoints even when query plans look trivial.

### 13.6. Lock Statistics

```sql
SELECT
    locktype,
    mode,
    granted,
    count(*) AS lock_count
FROM pg_locks
GROUP BY locktype, mode, granted
ORDER BY lock_count DESC;
```

To identify blockers, pair `pg_blocking_pids()` with `pg_stat_activity`. Look at wait duration and contended objects, not lock counts alone.

### 13.7. Autovacuum and Dead Tuples

Check `pg_stat_user_tables`, logs, and activity to confirm whether vacuum/analyze ran during the measured interval. For production-like tests, keep production autovacuum behavior.

### 13.8. Controlled Counter Resets

Do not reset cluster-wide statistics merely for pretty numbers. Prefer before/after snapshots. If a reset is mandatory in a lab, record the reset timestamp, which views/functions were reset, and any impact on other monitoring.

---

## 14. Collecting OS and Load Generator Metrics

### 14.1. CPU

Monitor:

- Overall and per-core CPU utilization.
- User/system/iowait/steal time.
- Run queue/load average.
- Context switches.
- Container/cgroup CPU throttling.

70% machine-wide CPU does not mean every core has headroom; one hot thread can bottleneck throughput even at moderate average utilization.

### 14.2. Memory

Record:

- Available/free RAM.
- Swap activity.
- Page faults.
- PostgreSQL RSS/shared memory.
- `pgbench` client memory.
- Cgroup memory limit/pressure.

If the system swaps during the measured interval, results do not represent healthy steady state.

### 14.3. Storage

Monitor:

- Read/write IOPS and throughput.
- Read/write latency.
- Queue depth.
- Utilization and throttling.
- Filesystem free space.
- WAL/data/temp volumes.

If storage has burst credits or throughput caps, record credit levels before and after tests.

### 14.4. Network

Record RTT between `pgbench` and database hosts, throughput, retransmits, packet drops, and NIC utilization. For cloud databases, place clients in the same region/VPC when testing server capacity; remote runs include WAN latency.

### 14.5. Load Generator

On the `pgbench` host, monitor CPU, memory, network, and threads. If the client host saturates before the database, measured TPS reflects load-generator limits.

### 14.6. Time Synchronization

Sync clocks across client, database, and monitoring hosts to align logs, snapshots, and metrics by timestamp. Record timezones and exact run start/end times.

### 14.7. Correlate on a Timeline

Plot/record on the same timeline:

- TPS and latency per interval.
- CPU and I/O utilization.
- Active sessions/wait events.
- Checkpoints/autovacuum.
- WAL rate and replication lag.

A latency spike coinciding with a checkpoint or storage throttling explains why run averages shifted.

---

## 15. Preparing a Reproducible Custom Dataset

### 15.1. Create Benchmark Schema

Example schema for accounts and orders workloads:

```sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.accounts (
    account_id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE bench.account_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE bench.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    total_amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
```

This is a minimal lab schema. If production uses foreign keys, triggers, partitioning, RLS, or additional indexes, include them in custom benchmarks to reflect true costs.

### 15.2. Populate Accounts

```sql
INSERT INTO bench.accounts(account_id, balance, updated_at)
SELECT
    g,
    100000,
    clock_timestamp()
FROM generate_series(1, 1000000) AS g;
```

### 15.3. Populate Orders

```sql
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
SELECT
    (g % 100000) + 1,
    CASE WHEN g % 5 = 0 THEN 'paid' ELSE 'created' END,
    100 + (g % 100000),
    clock_timestamp() - (g % 365) * interval '1 day'
FROM generate_series(1, 2000000) AS g;
```

### 15.4. Create Indexes and Statistics

```sql
CREATE INDEX orders_customer_created_idx
ON bench.orders (customer_id, created_at DESC);

ANALYZE bench.accounts;
ANALYZE bench.orders;
ANALYZE bench.account_events;
```

To compare two index strategies, build each state from the exact same base snapshot. Never let one run carry extra indexes unrelated to the experiment.

### 15.5. Verify Sizes and Row Counts

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
WHERE schemaname = 'bench'
ORDER BY relname;
```

Record table/index sizes and row counts for verification across runs.

### 15.6. Restoring Initial State

Options:

- Restore the same database snapshot/backup.
- Recreate schema and regenerate data with deterministic scripts.
- Clone storage/database snapshots if supported by your platform.
- Design read-only workloads that do not mutate data distributions.

Never reuse a heavily mutated database across all runs without accounting for data drift.

### 15.7. Keep Setup Out of Measurement

`CREATE INDEX`, bulk `INSERT`, `ANALYZE`, and initial vacuum belong to setup. Finish them, log setup duration, verify data state, and only then begin warm-up and measured phases.

---

## 16. Realistic Workload Scenarios

### 16.1. Read-Heavy Application

Characteristics:

- Many point lookups and list/search queries.
- Few writes.
- Working set concentrated on hot customers/products.
- Strong sensitivity to indexes and cache hit rates.

Use `list_orders.sql` and `read_account.sql` with high weights on `SELECT`. Test both warm cache and datasets exceeding cache if production involves disk I/O.

### 16.2. Mixed OLTP

Example mix:

| Transaction | Weight | Expected Share |
|---|---:|---:|
| List orders | 7 | 70% |
| Create order | 2 | 20% |
| Update account | 1 | 10% |

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -f update_account.sql@1 -c 48 -j 8 -T 300 -P 10 benchdb
```

Ratios are illustrative only. Derive mixes from application telemetry or access logs where available.

### 16.3. Write-Heavy Ingestion

Characteristics:

- Heavy `INSERT` volume.
- High WAL rate.
- Index maintenance and checkpoints dominate.
- Table growth and autovacuum impact over time.

Write batch/row insert scripts matching application transaction boundaries. Measure WAL bytes, commit latency, storage throughput, and replication lag if standbys exist.

### 16.4. Hot-Row Contention

To simulate many clients updating the same account:

```sql
\set account_id 1
\set delta random(1, 10)
UPDATE bench.accounts
SET balance = balance + :delta,
    updated_at = clock_timestamp()
WHERE account_id = :account_id;
```

This deliberately creates a hotspot. Use it to measure lock contention or test counter/hot-key designs, never to represent uniform access.

### 16.5. Skewed Customer Workload

Use Zipfian distribution so popular customers are queried more frequently:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

Compare against uniform distribution to see the effect of cache locality, hot indexes, and contention.

### 16.6. Reporting Workload

Example:

```sql
SELECT
    customer_id,
    status,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM bench.orders
WHERE created_at >= current_date - interval '30 days'
GROUP BY customer_id, status
ORDER BY total_amount DESC
LIMIT 100;
```

Heavy aggregate/sort workload. Measure temp blocks, memory spills, actual rows, I/O, and plans. Do not mix heavy report queries into pure OLTP benchmarks if measuring OLTP in isolation.

### 16.7. Connection Churn

Compare persistent connections vs. new connections per transaction:

```bash
pgbench -c 32 -j 8 -T 180 benchdb
pgbench -C -c 32 -j 8 -T 180 benchdb
```

The difference estimates connection setup/authentication cost. If production uses PgBouncer, also benchmark through the pooler using production pool mode, pool size, and client concurrency.

### 16.8. Mixed Workload with Think Time

If users pause between actions, use `\sleep` to model think time. Note that think time lowers per-client TPS and changes active concurrency; document sleep duration and rationale.

### 16.9. Read-After-Write

A flow may insert an order and immediately read it back. This tests transaction boundaries, index visibility, and application consistency assumptions. Pass the generated ID to the next query using `RETURNING`/`\gset` or equivalent.

### 16.10. Pick a Representative Workload Suite

You do not need every application query in one giant script. Select key critical flows and report per-script results. When weighting, document how ratios and total mix were determined.

---

## 17. Fair A/B Configuration Comparisons

### 17.1. Define Baseline

The baseline is the reference configuration and workload prior to changes. Record:

- PostgreSQL version/build.
- Hardware/storage/network.
- Server parameters.
- Dataset snapshot/size/indexes.
- `pgbench` client version.
- Scripts and weights.
- Clients/threads/protocol/rate/duration.
- Warm-up and measured intervals.
- Cache/vacuum state.

### 17.2. Change One Primary Variable

Example comparing two `work_mem` values:

1. Hold dataset, indexes, scripts, and client settings constant.
2. Run baseline with current `work_mem`.
3. Change only `work_mem`.
4. Run identical warm-up and measured phases.
5. Repeat multiple times.
6. Compare TPS, latency, temp blocks, memory, and CPU.

Changing `work_mem`, indexes, and client count together makes attribution impossible.

### 17.3. Comparing Index Strategies

Indexes speed up `SELECT`s while slowing `INSERT`/`UPDATE`s due to index maintenance and extra storage. Evaluate the full workload mix:

- Read latency.
- Write TPS/latency.
- WAL bytes.
- Index size.
- Vacuum overhead.

Never benchmark `SELECT` alone and declare an index beneficial for an entire OLTP workload.

### 17.4. Comparing PostgreSQL Settings

When changing `shared_buffers`, `work_mem`, `effective_cache_size`, checkpoint settings, or parallelism:

- Check whether a restart or reload is required.
- Let the server stabilize after restarts.
- Apply identical cache/warm-up policies.
- Confirm active values with `SHOW`.
- Measure both target workloads and secondary workloads that could regress.

### 17.5. Comparing Storage

Keep PostgreSQL build/config, dataset, scripts, client placement, and concurrency identical. Track IOPS, throughput, latency, and queue depth across both storage systems. Document any differences in volume size or burst credits.

### 17.6. Comparing Network/Client Placement

Moving the load generator changes the network path. Measure RTT and throughput separately. Keep clients in the same network zone to test server capacity, or match user paths to test end-user experience.

### 17.7. A/B Results Table

| Metric | Baseline A | Variant B | Delta |
|---|---:|---:|---:|
| TPS |  |  |  |
| Mean latency |  |  |  |
| p95 latency |  |  |  |
| p99 latency |  |  |  |
| Failed transactions |  |  |  |
| Schedule lag |  |  |  |
| CPU utilization |  |  |  |
| Read/write IOPS |  |  |  |
| WAL bytes/s |  |  |  |
| Temp bytes |  |  |  |

Populate from multiple runs using medians and dispersion. If p95/p99 were not measured directly, leave blank rather than estimating from averages.

### 17.8. Conditional Conclusions

A configuration might raise throughput while worsening tail latency. Tie conclusions to goals:

- If prioritizing peak throughput, inspect TPS at saturation.
- If prioritizing interactive SLAs, inspect p95/p99 at target offered load.
- If prioritizing write durability, never drop `fsync`/commit semantics for higher TPS.
- If prioritizing cost efficiency, compare throughput/latency at equal resource budgets.

---

## 18. Interpreting Results and Finding Bottlenecks

### 18.1. TPS Rises, Latency Stable

Usually a healthy sign when scaling concurrency or tuning configuration. Confirm failure rates stay flat and resource headroom remains adequate.

### 18.2. TPS Plateaus, Latency Rises

The system has likely reached saturation. Check CPU, I/O, locks, connection queues, WAL flushes, and the load generator. Adding clients does not guarantee extra throughput.

### 18.3. High CPU, Low I/O

Workload may be CPU-bound or limited by executor, expressions, joins, aggregations, serialization, or context switching. Inspect `EXPLAIN ANALYZE`, `pg_stat_statements`, and per-core CPU.

### 18.4. High I/O Wait

Cross-check storage latency/IOPS/queue depth, `shared_blks_read`, and I/O timings. Inspect working set, index access patterns, sequential scans, checkpoints, and storage throttling.

### 18.5. High Lock Waits

Inspect `pg_stat_activity.wait_event_type`, `pg_blocking_pids()`, `pg_locks`, and transaction age. Hot rows or updates to shared parent rows often trigger contention.

### 18.6. High Temporary Blocks

Inspect sort/hash nodes in `EXPLAIN`, actual rows, `work_mem`, and concurrency. Evaluate query rewrites/indexes/statistics before raising global memory.

### 18.7. High WAL Rate

Check write workloads, index maintenance, full-page images, checkpoints, and replication/archive throughput. Rising WAL generation can cause downstream replication lag or archive backlogs.

### 18.8. High Client CPU, Idle Server

The load generator cannot push enough requests. Raise `pgbench` worker threads, move to a stronger client host, or use multiple client hosts. Do not conclude PostgreSQL maxes out at that TPS.

### 18.9. High Latency, Low Server Metrics

Check network RTT, DNS, TLS/authentication, connection pool queues, client scheduling, and application serialization. `pgbench` latency is end-to-end from the client, not purely server execution time.

### 18.10. Throughput Drops Over Time

Possible causes:

- Autovacuum or checkpoints started.
- Dataset/history table grew.
- Cached working set shifted.
- Dead tuples/index bloat accumulated.
- Storage burst credits ran out.
- Client/server thermal or CPU throttling.
- Network congestion.

Use progress logs and server telemetry timelines to pinpoint when behavior changed.

---

## 19. Common Sources of Bias

### 19.1. Too-Short Runs

A 5–10 second run mostly captures startup/cache effects. Run for several minutes, repeat, and separate warm-up.

### 19.2. Unrepresentative Datasets

Tiny datasets yield artificially high cache hit rates; oversized datasets or mismatched access distributions also distort results.

### 19.3. Too-Small Scale Factor

In built-in TPC-B-like runs, a scale below client count induces hot-branch contention, measuring setup contention rather than overall server capacity.

### 19.4. Client and Server on the Same Host

`pgbench` steals CPU/network from PostgreSQL. Client saturation artificially caps measured TPS.

### 19.5. Inconsistent Autovacuum

One run encountering vacuum during measurement while another does not makes comparisons unfair. Either standardize vacuum state or keep it production-like and log vacuum events.

### 19.6. Differing Cache States

Comparing a cold-ish first run against a warmed-up later run skews results. Enforce identical warm-up protocols or measure each cache scenario separately.

### 19.7. Differing Transaction Mixes

Different scripts, weights, parameters, payload sizes, or transaction boundaries render TPS numbers incomparable.

### 19.8. Differing Protocol Modes

`simple`, `extended`, and `prepared` protocols carry different overhead and planning behavior. Keep them identical unless protocol overhead is the variable tested.

### 19.9. Enabling Logging on Only One Run

`-l`, `-r`, and sampling/logging add client/server overhead. Never compare a logged run against an unlogged run without accounting for it.

### 19.10. Cherry-Picking the Best Run

Reporting only the fastest run introduces bias. Report median and dispersion; if variance is high, run more iterations or tighten environment controls.

### 19.11. Repeating the Exact Same Random Seed Forever

One fixed seed repeats identical access patterns and cache footprints. Use fixed seeds for debugging/paired runs, and varied seeds to measure variability.

### 19.12. Background Traffic

Backups, batch jobs, replication, ETL, monitoring queries, and other user traffic consume resources. Pause them in labs or keep them steady and documented.

### 19.13. Changing Multiple Parameters at Once

Impossible to tell which change helped or hurt. Design each experiment around one clear hypothesis.

### 19.14. Comparing Non-Equivalent Machines

CPU, memory, storage, kernel, filesystem, virtualization, cgroups, networking, and firmware all affect performance. Normalize or explicitly state differences before concluding.

---

## 20. Troubleshooting Benchmarks

### 20.1. pgbench Cannot Connect

Check:

- Hostname, port, and routing.
- Firewalls/security groups.
- PostgreSQL listening status.
- `pg_hba.conf` and authentication.
- Existence and privileges of database/user.
- SSL mode/certificates if using TLS.
- Connection limits and pools.

Test `psql` with the same host/user/database to isolate connectivity errors from benchmark issues.

### 20.2. Relation Does Not Exist

For custom scripts, verify schemas/tables exist and names are schema-qualified. For built-in scripts, verify initialization ran in the exact target database.

### 20.3. Duplicate Key or Constraint Violations

Workloads may generate duplicate IDs, start from mismatched data, or retry non-idempotent logic. Check transaction logic and retry policies; never drop constraints just to make benchmarks pass.

### 20.4. Deadlocks / Serialization Failures

Inspect lock ordering, hot rows, transaction duration, and isolation levels. Record failures/retries and inspect `pg_stat_activity`/`pg_locks`. Only retry when the real application also uses matching retry semantics.

### 20.5. Lower TPS Than Expected

Check:

- Is the `pgbench` client CPU-bound?
- Is network RTT high?
- Are there lock waits or connection queues?
- Does the working set exceed cache?
- Is storage throttling?
- Is autovacuum/checkpoint running?
- Are there too many clients for capacity?
- Does the script run heavier queries than intended?

### 20.6. Continuously Climbing Latency

Check schedule lag, active sessions, wait events, CPU run queues, I/O latency, and checkpoint/vacuum timelines. With `-R`, lower target rate to find sustainable load.

### 20.7. Runs with Many Skipped Transactions

Under rate control and latency limits, skipped transactions never hit the server. Check target rate, client count, latency limit, and schedule lag. Report skipped counts; never count them as completed transactions.

### 20.8. Oversized Logs

Lower sampling rate, use `--aggregate-interval` where appropriate, or shorten the measured window. Document sampling rates and adjust calculations when analyzing TPS from sampled logs.

### 20.9. Per-Command Latency Lowers TPS

`-r` collects per-statement timing and adds overhead. Compare runs without `-r` and with `-r` to quantify the impact.

### 20.10. Non-Reproducible Results

Record exact commands, script hashes, random seeds, data snapshots, PostgreSQL settings, cache state, host placement, and metric timelines. Reproduce with a fixed seed to debug, then use varied seeds to measure variance.

---

## 21. End-to-End Lab Benchmark Workflow

### 21.1. Step 1 — Define the Question

Example: verify whether index `(customer_id, created_at DESC)` improves the list-orders workload without excessively slowing writes.

### 21.2. Step 2 — Prepare the Database

Create a dedicated lab database, connect with a benchmark role, and verify PostgreSQL/`pgbench` versions. Never use production databases.

### 21.3. Step 3 — Generate the Dataset

Run DDL and data generation from Section 15. Record row counts, table/index sizes, and server settings. Take a snapshot to restore identical state across A/B tests.

### 21.4. Step 4 — Prepare Scripts

File `list_orders.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
SELECT order_id, status, total_amount, created_at
FROM bench.orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 20;
```

File `create_order.sql`:

```sql
\set customer_id random_zipfian(1, 100000, 1.10)
\set total_amount random(100, 100000)
INSERT INTO bench.orders
    (customer_id, status, total_amount, created_at)
VALUES
    (:customer_id, 'created', :total_amount, clock_timestamp());
```

### 21.5. Step 5 — Smoke Test

```bash
pgbench -f list_orders.sql -c 1 -j 1 -T 10 -P 2 benchdb
```

Confirm the script runs cleanly without SQL errors and returns sensible rows.

### 21.6. Step 6 — Warm-Up

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -c 16 -j 4 -T 60 benchdb
```

This is warm-up; exclude results from baseline measurements. If write workloads grow tables significantly, restore snapshots before measured runs or define a steady-state growth policy.

### 21.7. Step 7 — Measured Run

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -c 16 -j 4 -T 300 -P 10 -l --log-prefix=run_a benchdb
```

Save output and transaction logs. Collect CPU, storage, network, and PostgreSQL metrics with aligned timestamps.

### 21.8. Step 8 — Concurrency Sweep

Run identical workloads and durations at 1, 2, 4, 8, 16, and 32 clients without changing other factors. Build a TPS/latency/failure table by concurrency to locate saturation.

### 21.9. Step 9 — Rate-Controlled Run

```bash
pgbench -f list_orders.sql@7 -f create_order.sql@2 -R 250 -c 32 -j 8 -T 300 -P 10 -L 100 benchdb
```

Check schedule lag, late/skipped transactions, and latency. Use `-L` only when testing a specific SLO latency target; otherwise omit it and report full latency.

### 21.10. Step 10 — A/B Index Comparison

Baseline A: without the new index, run warm-up and measured tests. Restore dataset. Variant B: build index, run `ANALYZE`, warm up, and run the exact same commands. Compare read latency, write TPS, WAL, storage size, and temp/I/O metrics.

### 21.11. Step 11 — Repeat

Repeat each configuration multiple times; alternate A/B order across rounds if possible. Report median and spread, never cherry-picking the fastest run.

### 21.12. Step 12 — Save the Report

The report should include:

- Goal and hypothesis.
- Server/client/hardware/network description.
- Dataset snapshot, row counts, sizes, and indexes.
- Script contents/hashes, weights, and random seeds.
- Exact command lines.
- Warm-up/duration/repetitions.
- TPS, average/stddev, measured p95/p99, failures/retries/skipped.
- CPU, memory, storage, network, WAL, waits, and vacuum/checkpoint events.
- Bottleneck analysis, conclusions, and limitations.

### 21.13. Step 13 — Clean Up the Lab

After saving the report, stop load generators, verify no stray sessions remain, and drop lab schemas/databases per procedure. Never leave benchmark jobs running or test data consuming storage unnecessarily.

---

## 22. Practice Exercises and Answers

### Exercise 1 — TPC-B-Like

**Question:** Is `pgbench`'s default workload an official TPC-B benchmark?

**Answer:** No. It is a TPC-B-like workload inspired by TPC-B, not an official TPC-B benchmark or certification.

### Exercise 2 — Initialization

**Question:** Why use a separate database when running `pgbench -i`?

**Answer:** Initialization drops and recreates fixed-name `pgbench_*` tables and would destroy real data sharing those names.

### Exercise 3 — Scale Factor

**Question:** Why should the scale factor for built-in TPC-B-like tests be at least equal to the maximum client count?

**Answer:** Because the branch table has only `scale` rows and every transaction updates a branch row; too small a scale causes hot-row contention.

### Exercise 4 — Clients and Threads

**Question:** What does `-c 64 -j 8` mean?

**Answer:** 64 client sessions driven by 8 `pgbench` worker threads.

### Exercise 5 — Duration

**Question:** How do `-T` and `-t` differ?

**Answer:** `-T` limits total run duration; `-t` sets transaction count per client. The two options cannot be used together.

### Exercise 6 — Protocol

**Question:** What are the three values for `-M`?

**Answer:** `simple`, `extended`, and `prepared`.

### Exercise 7 — Connection Churn

**Question:** What is `-C` used to measure?

**Answer:** Opening a new connection for every transaction to measure connection overhead.

### Exercise 8 — Rate Control

**Question:** What does `-R 300` mean?

**Answer:** Tells `pgbench` to target 300 transactions/second using rate-controlled start scheduling.

### Exercise 9 — Schedule Lag

**Question:** What does continuously growing schedule lag suggest?

**Answer:** Either the server or the load generator cannot sustain the target arrival rate with the current clients/threads.

### Exercise 10 — Latency Limit

**Question:** Are skipped transactions in a rate-controlled test sent to PostgreSQL?

**Answer:** No. They exceeded the latency limit before being dispatched.

### Exercise 11 — TPC-B-Like and SELECT-Only

**Question:** Which workload does `-S` run?

**Answer:** Built-in `select-only`.

### Exercise 12 — Script Weights

**Question:** What are the selection probabilities for two scripts with weights 7 and 3?

**Answer:** Roughly 70% and 30% selection probabilities.

### Exercise 13 — Uniform

**Question:** Which distribution does `random(1, 100)` model?

**Answer:** Uniform distribution from 1 to 100.

### Exercise 14 — Zipfian

**Question:** When should you use `random_zipfian`?

**Answer:** When certain hot keys/customers are accessed much more frequently than the rest.

### Exercise 15 — Working Set

**Question:** Does a dataset larger than RAM guarantee the benchmark measures storage?

**Answer:** No. The access pattern must span a working set large enough to trigger cache misses; merely inflating total table size is not enough.

### Exercise 16 — Warm-Up

**Question:** Why run a warm-up before the measured run?

**Answer:** To separate startup and cache-loading effects from steady-state performance.

### Exercise 17 — Cold Cache

**Question:** Does restarting PostgreSQL guarantee the OS page cache is empty?

**Answer:** No. Restarting empties `shared_buffers`, yet the OS page cache can still retain data pages.

### Exercise 18 — Vacuum

**Question:** Why can autovacuum cause runs to differ?

**Answer:** It competes for CPU/I/O and changes dead tuples, bloat, and cache footprints during the measured interval.

### Exercise 19 — Repetition

**Question:** Why should you never pick the run with the highest TPS?

**Answer:** It may be an outlier; report the median and dispersion across multiple runs.

### Exercise 20 — Random Seed

**Question:** Should you always use the exact same random seed for every run?

**Answer:** No. Fixed seeds help with debugging/paired tests, while varied seeds are needed to measure variability.

### Exercise 21 — Load Generator

**Question:** Server CPU is low yet TPS stops rising as clients increase. What should you check?

**Answer:** CPU/network/thread saturation on the `pgbench` client host, network RTT, connection limits, and wait events.

### Exercise 22 — Latency

**Question:** Is `pgbench` latency purely server execution time?

**Answer:** No. It is client-observed latency, including network time, scheduling lag, and other overheads.

### Exercise 23 — p95/p99

**Question:** Can p95/p99 be derived from average and standard deviation?

**Answer:** No. You need transaction-level logs or appropriate tail-latency instrumentation.

### Exercise 24 — Server Metrics

**Question:** Which view shows active sessions and wait events?

**Answer:** `pg_stat_activity`.

### Exercise 25 — A/B

**Question:** When comparing index A vs. B, what must remain constant?

**Answer:** Dataset, workload scripts/weights, clients/threads, protocol, duration, cache/warm-up, server/client placement, and all settings outside the tested index.

---

## 23. Reliable Benchmark Checklist

### Before Running

1. Define the question and success metrics.
2. Choose a realistic business workload.
3. Create a dedicated benchmark database.
4. Check `pgbench` and PostgreSQL versions.
5. Record hardware, OS, storage, network, and server settings.
6. Choose representative dataset size and working set.
7. Match schema, indexes, constraints, and data distributions.
8. Verify transaction scripts and business invariants.
9. Choose clients, threads, protocol, rate, and duration.
10. Decide warm-cache vs. cold/first-touch test.

### During Runs

11. Run a single-client smoke test.
12. Separate setup, warm-up, and measured intervals.
13. Run the measured phase for at least several minutes.
14. Repeat each configuration multiple times.
15. Track TPS, latency, failures, retries, and schedule lag.
16. Monitor CPU, memory, I/O, network, and load generator.
17. Monitor waits, locks, WAL, checkpoints, and autovacuum.
18. Record any background events during the measured window.
19. Never change multiple variables simultaneously.
20. Never cherry-pick the best run as representative.

### After Running

21. Save command lines, scripts, and random seeds.
22. Save logs and timestamped server metrics.
23. Compute median and range/spread across runs.
24. Report p95/p99 only when measured from sufficient samples.
25. Reconcile `pg_stat_statements` and `pg_stat_database` deltas.
26. Identify bottlenecks using server and OS evidence.
27. Compare strictly under equal workload/cache/data states.
28. Document limitations and uncontrolled variables.
29. Restore/reset datasets before the next round if workloads drift data.
30. Stop load generators and clean up the lab when finished.

---

## 24. Summary

`pgbench` is a practical tool for measuring PostgreSQL throughput, latency, and concurrency behavior. Built-in TPC-B-like workloads give quick baselines, yet benchmarks carry the most value when transaction scripts, data sizes, key distributions, read/write mixes, and connection patterns reflect the target system.

Key takeaways:

- Default `pgbench` runs a TPC-B-like workload, not official TPC-B.
- `pgbench -i` creates and drops fixed-name `pgbench_*` tables; always use a dedicated benchmark database.
- The built-in TPC-B-like scale factor must be large enough to avoid hot-branch contention.
- `-c` sets client sessions; `-j` sets `pgbench` worker threads.
- `-T` controls duration; `-t` sets transactions per client.
- `-M` selects `simple`/`extended`/`prepared` protocol; `-C` opens a new connection per transaction.
- `-R` sets offered rate and reported latency includes schedule lag; `-L` can create late/skipped transactions.
- `-l` and `-r` add overhead; document logging and sampling choices.
- Custom scripts should mirror real transaction boundaries, business rules, data skew, and read/write mixes.
- Warm-up, cache state, autovacuum, dead tuples, checkpoints, and data growth all influence results.
- Run for several minutes, repeat multiple times, randomize A/B order, and report median/variability.
- Monitor PostgreSQL, OS, storage, network, and the load generator together.
- High TPS alone is not enough; read latency, failures, retries, schedule lag, and resource headroom.
- Use `pg_stat_activity`, `pg_stat_statements`, `pg_stat_io`, and logs to explain bottlenecks.
- A/B comparisons are meaningful only when workloads and test conditions match.

**Self-check question:** A new configuration raises TPS by 12% in a single 30-second run measured right after warm-up, while the baseline ran from a cold cache. Can you conclude the new configuration is better? Not yet. You must repeat over longer runs, enforce identical cache protocols, keep workload/dataset/client settings identical, collect latency/failure/resource metrics, and compare medians alongside variance.

### Official PostgreSQL Documentation

- [pgbench — PostgreSQL 18](https://www.postgresql.org/docs/18/pgbench.html).
- [pgbench — PostgreSQL 17](https://www.postgresql.org/docs/17/pgbench.html).
- [pgbench — PostgreSQL 16](https://www.postgresql.org/docs/16/pgbench.html).
- [pgbench — PostgreSQL 15](https://www.postgresql.org/docs/15/pgbench.html).
- [pgbench — PostgreSQL 14](https://www.postgresql.org/docs/14/pgbench.html).
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Runtime Statistics Configuration](https://www.postgresql.org/docs/current/runtime-config-statistics.html).
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
