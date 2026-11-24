# Load Testing with Representative Data, Concurrency, and Runtime Duration in Spring Boot

## 1. Goal: Load Results Must Reflect How the System Actually Runs in Production

A Spring Boot application can return HTTP 200 in 5 ms when one developer tests with `curl`. That result **proves nothing** about whether the app meets SLOs with hundreds of active sessions, growing tables, PostgreSQL holding millions of rows, uneven cache behavior, and load sustained long enough for connection pools, GC, memory, or downstreams to hit their limits.

Meaningful load testing must accurately model **three axes** simultaneously:

1. **Representative data:** record counts, data size, payload width, data distribution, hot vs cold keys, cache hit/miss ratios, per-tenant skew, read/write operation mix, and data growth rate.
2. **Representative load and concurrency:** active users, request/transaction arrival rate (RPS/TPS), think time, in-flight request count, bursts/peaks, and parallelism hitting DBs or external services.
3. **Representative duration:** warm-up, steady state, peak, spike, long soak, testing alongside batch/backup/autoscaling jobs, and spanning enough cycles to reveal GC, cache, and connection leaks.

**Core message:** huge VU counts alone do not prove resilience; 1,000 fake rows do not represent 10 million real rows; a 30-second test does not represent an hour of operation. Measure **p95/p99 latency, completed throughput, error rate, dropped iterations, resource utilization, and response correctness** under explicitly documented load and configuration.

This lesson focuses on the Spring Boot web runtime (Spring MVC/Tomcat, JDBC/HikariCP/PostgreSQL, Actuator/Micrometer) using k6 as the load generator. It includes a runnable project with **Spring Boot 3.5.16, Java 17+, Maven, and PostgreSQL via Docker Compose**, seeded with **200,000 products**, an 80% product-detail / 15% search / 5% event-write mix, plus both open-model and closed-model k6 scripts. Configs and load figures here are **learning samples**, not real measurements or universal enterprise SLOs.

### Learning Outcomes

After this lesson, you will be able to:

- Design workloads from production-observed traffic and data distributions.
- Distinguish user, virtual user, session, RPS, throughput, in-flight requests, and DB connections.
- Pick **closed workloads** or **open arrival rates** for the right purpose, avoiding coordinated omission.
- Choose ramp-up, steady-state, peak, stress, and soak durations long enough to uncover failures.
- Use k6 to verify functional correctness and per-endpoint thresholds rather than global averages.
- Read Spring Boot/Tomcat/Hikari/JVM/PostgreSQL metrics to pinpoint bottlenecks.
- Report reproducible results while clearly stating what cannot be extrapolated from a lab.

## 2. Define the Goal and Question Before Picking a Tool

Start with a concrete **validation question**, for example:

> Given 2 Spring MVC instances (2 vCPU / 2 GiB RAM each), a production-like PostgreSQL instance, 500,000 products, and observed mixed traffic, can the system sustain **200 HTTP requests/second for 30 minutes** with p95 under 300 ms, p99 under 800 ms, and system errors under 0.5%?

This statement fixes topology, data volume, traffic mix, arrival rate, duration, and acceptance thresholds. Numbers above are **illustrative hypotheses only**; real SLOs come from product requirements, telemetry, and capacity budgets.

### Different Test Types

| Test Type | Question Answered | Meaningful Profile |
| --- | --- | --- |
| **Smoke** | Do scripts, auth, data, and endpoints work? | A few VUs/RPS for 1–3 minutes with response assertions |
| **Baseline** | What latency does the current system show at low load? | Fixed environment, steady low load, multiple repeats |
| **Load / capacity** | Do p95/p99/errors pass at normal/peak load? | Realistic data + traffic mix, steady state |
| **Stress** | Where do SLOs or limits break? | Step up RPS/VUs gradually to locate the capacity knee |
| **Spike** | What happens when arrival rate jumps suddenly? | Sudden rate surges, monitoring queues and recovery |
| **Soak / endurance** | Are there leaks or pool/heap/DB degradation over time? | 1–4 hours or longer across real maintenance cycles |
| **Scale test** | Does autoscaling scale out/in fast enough? | Ramps matching HPA, startup, and cooldown |
| **Recovery test** | Does the system recover after upstream timeouts or DB failover? | Controlled fault injection and rollback checks |

Never test just to "score the highest number on a benchmark". The goal is proving **ability to serve a defined workload** or identifying exact limits and root causes with evidence.

## 3. Representative Data: Row Count Is Only the Starting Point

### 3.1. Minimum Data Dimensions to Model

| Dimension | Examples to Measure | Why It Changes Outcomes |
| --- | --- | --- |
| **Cardinality** | 200k, 2M, 20M products | Index size, working set, DB/cache efficiency |
| **Row width** | 30-char name vs 10 KiB description | Disk I/O, network, serialization, heap allocations |
| **Key distribution** | 70% of requests hit 10% hot products | Cache hit rates and row contention differ from uniform |
| **Category/tenant skew** | Books 50%, electronics 30%, home 20% | Selectivity/partition skew and tenant fairness |
| **Read/write mix** | 80% detail, 15% search, 5% events | DB writes/WAL, locks, query mix |
| **Query patterns** | PK point lookup, filters, sorts, deep offsets | Query plans and index utilization |
| **Existence ratio** | Mostly valid IDs plus realistic 404s | Realistic error distribution and error-path load |
| **Cache state** | Cold, warm, hot-key hit rate | Warm caches can mask disk/DB bottlenecks |
| **Data growth** | Events growing 5% per minute | Table/index bloat, autovacuum, disk usage |
| **Multi-tenant shape** | One large tenant with heavy data and traffic | Noisy neighbors and fairness |
| **Payload sizes** | P50/P95 request/response bytes | Bandwidth, compression, GC |
| **Downstream latency** | DB, Redis, payment latencies/errors | Tail latency and system-wide contention |

**Distribution** matters just as much as total row count. A 1-million-row database queried exclusively via `GET /products/1` responds artificially fast from caches and fails to represent real traffic.

### 3.2. Avoid Two Data-Generation Traps

**Trap 1: seeding 100 rows and querying them repeatedly.** Indexes and the entire working set fit effortlessly in RAM. Query plans, cache hits, and disk pressure look nothing like production.

**Trap 2: uniform random across all IDs.** Real traffic usually exhibits heavy-tail hot items where a tiny fraction of SKUs or categories draws most views. Uniform randomness can **underestimate cache hits** while **underestimating hot-key lock contention**. Model skew from aggregated logs or Zipf/weighted buckets.

### 3.3. Building Reproducible Datasets

Practices:

- Generate **synthetic or anonymized** datasets—never copy production PII, access tokens, or payment details.
- Fix the seed/algorithm, row counts, category weights, schema/indexes, and generator version.
- Document dataset specs in the test report.
- Maintain tiered datasets: `small` for smoke tests, `representative` matching today's volume, `growth` matching 6–12 months ahead.
- Inspect query plans after `ANALYZE`, verifying statistics and index usage.
- Verify row counts, min/max IDs, category distributions, row/page sizes, and DB disk size before running.
- Reset datasets or record accumulated state before repeats; never A/B-compare a run with 10M events against one with 100k.

The demo dataset in Section 9 uses **200,000 products** split 50%/30%/20% across categories, with 70% of views hitting the first 10% of IDs and 30% spread across all IDs. This distribution is illustrative for learning—**not production data from any specific company**.

### 3.4. Watch Cache State and Correctness

Test both cold and warm caches when relevant, without blending them into one p95:

- **Cold cache:** DB page cache, Redis, or app caches are empty; reflects rollouts/restarts rather than normal traffic.
- **Warm cache:** after warm-up, hot keys are loaded; reflects steady-state traffic.
- **Cache invalidation:** do writes stale cached reads? Returning stale prices faster is still broken.
- **Query plan stability:** does the optimizer keep using the same index after tables grow and statistics update?

An API returning 200 twice as fast with stale prices or dropped events **fails correctness**. Load testing must never trade data integrity for speed.

## 4. Concurrency: VUs, In-Flight Requests, and RPS Are Three Different Variables

### 4.1. Definitions

- **User/session:** a human or client session executing actions separated by pauses; one user generates multiple requests.
- **k6 Virtual User (VU):** an execution loop running JavaScript iterations; VUs **do not equal** concurrent browser users.
- **Arrival rate:** rate at which new iterations/transactions start over time, e.g., 50 iterations/s.
- **Request rate (RPS):** HTTP requests sent or completed per second; one iteration may fire 1 or multiple requests.
- **Concurrency / in-flight:** requests currently active/waiting inside the system at a point in time.
- **Throughput:** requests or business transactions completed successfully per second; define explicitly.
- **Thread count:** Java/Servlet worker threads, not equal to in-flight requests or connections.
- **DB pool active:** database connections currently leased, not equal to active HTTP requests.

### 4.2. Little's Law Is a Sanity Check, Not a Formula for VUs

In a stable system with arrival rate `λ` (requests/sec), mean response time `W` (seconds), and mean concurrent in-flight requests `L`:

```text
L ≈ λ × W
```

**Mathematical illustration:** 50 requests/s averaging 0.2 s in the system gives ~10 concurrent requests. If latency rises to 1 s while arrival rate holds at 50/s, concurrency rises to ~50. Once queueing, drops, or errors start, stability assumptions break—never treat the formula as proof of capacity.

**Never substitute p95 for `W`** in Little's Law. It relates **means** across the same measurement boundary, not percentiles. If one transaction issues multiple HTTP calls, keep transaction concurrency distinct from HTTP request concurrency.

### 4.3. Closed Workload: Fixed VU Count

k6 executors `constant-vus` or `ramping-vus` simulate fixed concurrent actors:

```text
VU -> send HTTP -> wait for response -> sleep 1–3s -> repeat
```

When the server slows down, each VU waits longer, so requests/s **drop automatically**. This fits certain session models, yet when real-world arrival rates keep coming regardless of backend speed, closed models mask overload (**coordinated omission**).

Use closed models to test bounded session journeys with think time. Never equate "100 VUs = 100 RPS".

### 4.4. Open Workload: Response-Independent Arrival Rate

k6 `constant-arrival-rate` and `ramping-arrival-rate` **launch iterations on a fixed schedule** whenever VUs are available, matching incoming Internet traffic, queues, or event streams.

```text
Every 20 ms: start a new iteration (~50/s)
      |
      +----> HTTP request A (might wait 100 ms)
      +----> HTTP request B (might wait 500 ms)
      +----> HTTP request C ...
```

In an open model, **VUs are merely the worker pool executing scheduled iterations**. If VUs run out due to low pre-allocation or a sluggish SUT, k6 logs `dropped_iterations`. Then **achieved rate falls below target**—never report "the system handled 100 RPS" just because `rate: 100` was configured.

When each iteration sends **one HTTP request**, target iterations/s matches target HTTP RPS if drops are zero. When an iteration runs login + catalog + checkout (3 requests), 50 iterations/s produces ~150 HTTP requests/s. Report both levels clearly.

### 4.5. Sizing VUs for an Arrival Rate

Start with `arrival rate × average iteration duration`, then add headroom for tail latency. For example, 50 iterations/s × 0.2 s ≈ 10 VUs, though tail p99 spikes, payload parsing, auth, think time, or multi-call iterations demand more.

- `preAllocatedVUs`: VUs allocated before the test starts.
- `maxVUs`: cap for dynamic VU allocation; allocating mid-test also adds harness overhead.
- `dropped_iterations`: scheduled iterations skipped due to no free VU or limits.

**Do not fix every `dropped_iterations` warning by raising VUs infinitely.** If SUT latency spiked, investigate DB, thread pools, or CPU; if the generator ran out of CPU or pre-allocated VUs, fix the generator. Separate the two using metrics from both sides.

## 5. Representative Runtime Duration: Warm-Up, Steady State, Peak, and Soak

### 5.1. Why 10–30 Seconds Is Not Enough

Short tests are skewed by:

- JVM class loading, JIT warm-up, and dynamic recompilation.
- Cold PostgreSQL buffer caches (or leftover warm caches from the prior run).
- Hikari connection pools still warming up.
- Incomplete GC cycles.
- Autoscalers not having enough time to spin up pods and pass readiness.
- Missing DB checkpoints, autovacuum, WAL pressure, background jobs, or cache expirations.
- Slow connection or memory leaks failing to surface.
- Too few samples for reliable p99 measurements.

Therefore **duration is an integral part of workload design**, not an optional shortcut.

### 5.2. Example Phase Profile

| Phase | Illustrative Load | Illustrative Duration | What to Observe |
| --- | --- | --- | --- |
| Smoke | 1–5 RPS | 1–3 min | Scripts, schema, functional correctness |
| Warm-up | 10–20 RPS | 3–5 min | JIT, pools, caches, DB buffers |
| Baseline | 50 RPS | 10–15 min | p95/p99, errors, CPU, connections |
| Expected peak | 100 RPS | 15–30 min | SLOs, autoscaling, queues |
| Stress | 100 → 150 → 200 RPS | 5–10 min per step | Capacity knee and degradation mode |
| Spike | 20 → 200 → 20 RPS | A few minutes per step | Bursts, queueing, recovery |
| Soak | 60–80 RPS | 1–4 hours or longer | Heap, GC, WAL, bloat, pools |
| Recovery | Scenario-specific | Duration of failover | Error budgets and recovery time |

**No single duration fits every system.** If production peaks last 45 minutes, a 3-minute peak test falls short. If batch jobs fire every 30 minutes, a 20-minute soak misses them. If a memory leak takes 6 hours to surface, a 1-hour run won't catch it.

### 5.3. Separate Metrics by Phase

Never report a single p95 blending warm-up, steady state, and ramp-down. Tag/slice metrics by test stage or time window; specifically **exclude warm-up from steady-state SLO decisions**, while keeping warm-up as its own release-readiness check.

Run baselines at least 3 times with identical dataset/hardware and report variance—one "lucky" run proves nothing. High p95 variance points to noisy host neighbors, cache state changes, background tasks, or autoscaling timing.

## 6. Metrics to Observe Together

### 6.1. Four Result Groups from k6

| Metric | How to Read | Notes |
| --- | --- | --- |
| `http_reqs` | Sent HTTP requests; total rate | Includes failed requests |
| `http_req_duration` | Sending + waiting + receiving | Excludes full DNS/connection setup |
| `http_req_waiting` | Time to first byte (TTFB) | Helps isolate upstream processing |
| `http_req_failed` | Failure rate per k6 expected-response policy | Does not replace business correctness checks |
| `checks` | Assertion pass rate (status/body) | Must verify payloads, not just HTTP 200 |
| `iterations` | Completed k6 iterations | May differ from HTTP request count |
| `iteration_duration` | Full iteration duration | Includes script logic, multiple calls, think time |
| `vus`/`vus_max` | Active / allocated VUs | Not equal to HTTP concurrency |
| `dropped_iterations` | Iterations missed on schedule | **Target load was not achieved** |
| `data_received`/`data_sent` | Network volume | Check against payload sizes and headers |

Per k6 documentation, `http_req_duration` sums `sending + waiting + receiving`. To inspect TLS, DNS, or connection reuse, check `http_req_blocked`, `http_req_connecting`, and `http_req_tls_handshaking`. Browser-perceived latency also includes rendering, JS, and user interaction, differing from k6 HTTP timing.

### 6.2. Percentiles and Errors

With 10,000 requests and p95 = 300 ms, at least ~95% completed within 300 ms. p99 captures the ~99% tail threshold, requiring ample samples.

**Never judge by average alone:** 99 requests at 10 ms plus one at 5,000 ms yields a deceptive average that hides the user hitting a 5-second timeout.

A proper report includes:

- p50/p90/p95/p99 **per endpoint or operation class**;
- latency of successful requests separately from error responses so fast errors don't make p95 look artificially fast;
- HTTP error rate plus business check failure rate;
- achieved RPS, expected RPS, and dropped iterations;
- per-minute time series to spot drift rather than only final summaries.

With small samples, p99 has high uncertainty. Never claim "p99 passes SLO" from 50 samples on a rare endpoint—ensure enough samples per interval, repeat runs, and realistic mixes.

### 6.3. Spring Boot / Tomcat Server Metrics

With Actuator/Micrometer enabled and configured:

- `http.server.requests`: server request count/latency by method/status/route (per instrumentation).
- `jvm.memory.used`, `jvm.gc.pause`: heap and GC pressure.
- `process.cpu.usage`, `system.cpu.usage`: process and host CPU.
- `tomcat.threads.busy` and `tomcat.threads.current` when Tomcat MBean metrics are enabled.
- `jdbc.connections.active`, `jdbc.connections.idle`, `jdbc.connections.max`: pool utilization.
- `hikaricp.connections.pending`, `hikaricp.connections.timeout`, and related Hikari meters when present.
- `process.files.open`, thread counts, and network sockets where supported.

Exact names/tags depend on Spring Boot, registry, and instrumentation. **Never assume every metric appears automatically** or that Actuator JSON suits Prometheus scraping directly—add `micrometer-registry-prometheus` for `/actuator/prometheus`.

### 6.4. PostgreSQL Database Metrics

Serious load tests monitor PostgreSQL simultaneously:

- `pg_stat_activity`: active connections, `wait_event`, long transactions.
- `pg_stat_database`: commits/rollbacks, block hits vs reads, temp files, deadlocks.
- `pg_stat_statements` (if enabled/authorized): per-query-template total time and latency.
- `EXPLAIN (ANALYZE, BUFFERS)` on representative queries (note `ANALYZE` executes the query and adds overhead).
- Index scans vs sequential scans, disk sorts/spills, lock waits, WAL bytes, and checkpoints.
- Autovacuum activity, table/index bloat, disk usage, and IOPS.

**Many busy threads do not prove CPU is the bottleneck.** Threads may be stuck waiting on Hikari connections, DB locks, upstream HTTP calls, or disk I/O. Inspect wait states and traces.

## 7. Design Workloads from Telemetry Rather Than Guesses

### 7.1. Sources for Estimating Profiles

Gather in **aggregated, PII-scrubbed** form:

1. HTTP logs/metrics by route template, method, and status class.
2. Normal RPS, 1-minute/5-minute/hourly peaks, and ramp/burst rates.
3. p50/p95/p99 latencies and request/response sizes per operation.
4. Active sessions, requests per session, think times, and common user journeys.
5. **Anonymized** product ID, category, and tenant skew (hot vs cold keys).
6. Cache hit/miss rates, DB query plans, pool usage, and retry rates.
7. Expected client 4xx rates (distinct from server failures).
8. Data creation/mutation rates over time plus retention/cleanup jobs.
9. Background tasks, events, batch jobs, and autoscaling behavior.
10. Current dataset size plus projected growth.

Never feed raw access logs containing IPs, cookies, `Authorization` headers, user IDs, or PII into external load tools. Aggregate route weights, percentiles, and synthetic parameter distributions safely.

### 7.2. Illustrative Traffic Mix

| Operation | Probability per HTTP Request | Data Shape | Impact |
| --- | --- | --- | --- |
| `GET /api/products/{id}` | 80% | 70% hot IDs, 30% full range | Point lookup / cache |
| `GET /api/products/search` | 15% | Categories weighted 50/30/20; varied offsets | Index scan and pagination |
| `POST /api/events` | 5% | Valid product ID + synthetic session key | INSERT, WAL, and table growth |

Sum = 100%. In the k6 script in Section 10, each iteration **sends exactly one HTTP request**, so target iterations/s equals target HTTP RPS when dropped iterations are zero. When real transactions make multiple calls, document the multiplier clearly.

### 7.3. "Realistic" Data Means More Than a List of IDs

A search endpoint over 1,000 uniform items picks different query plans than a 10-million-row table with skewed categories and deep offsets. Verify:

- Row counts, category selectivity, and indexes.
- Whether the working set exceeds available RAM.
- Whether write/update patterns trigger lock contention, churn, or WAL pressure.
- Realistic parameter distributions: offsets, sorts, and filter combinations.
- Payload sizes, chunking, gzip, connection reuse, and TLS.
- Auth overhead, token refreshes, and session stores if used in production.
- Downstream failure and latency distributions where dependencies exist.

You do not need to copy production data. A synthetic dataset built from **real statistical distributions** tests accurately without leaking sensitive data.

## 8. Preparing a Reproducible Benchmark Environment

### 8.1. Mandatory Fields in Any Benchmark Report

| Category | Details to Freeze |
| --- | --- |
| Source/build | Git revision, artifact checksum, JDK/Boot version |
| SUT topology | Pods/instances, vCPU/RAM, JVM args, web threads |
| DB | PostgreSQL version, connection caps, pool sizes, indexes |
| Network | Load generator location, TLS, LB/CDN/proxy, RTT latency |
| Dataset | Seed/version, row counts, sizes, skew, pre-existing events |
| Traffic | Mix/weights, RPS/VUs, read/write ratio, think time |
| Time | Warm-up, steady, peak, soak windows, timezone, run date |
| Cache | Cold/warm state, TTLs, CDN/Redis config |
| SLO | p95/p99/error/drop thresholds and sampling rules |
| Infrastructure | Autoscaling policy, sidecars, monitoring, background jobs |

Measuring on a laptop and declaring "production handles 1,000 RPS" is invalid. This lab teaches methodology; production capacity planning demands production-like isolated environments and formal sign-off.

### 8.2. Never Run Unauthorized Load Tests

Send load strictly to **localhost or owner-authorized environments** with approved RPS, source IPs, schedules, and data reset procedures. Never aim high-rate scripts at public APIs or live partner systems without agreeing on quotas, blast radius, and rollback. Avoid triggering real payments, emails, or external orders during load tests.

### 8.3. Separate the Load Generator from the SUT for Serious Runs

Running k6 and PostgreSQL on the same laptop creates **resource contention**. k6 can saturate CPU or sockets before Spring Boot nears its limit. For serious capacity tests, run k6 on dedicated generator hosts, monitor generator CPU/memory/network, distribute generators if needed, and compare target vs achieved rate.

### 8.4. Repeatability and Variance

- Repeat each scenario multiple times and compare medians, p95s, and time series.
- Change one variable per experiment (e.g., pool 10 → 20 connections) while holding dataset and load fixed.
- Keep SUT warm-up state consistent, or label cold-start tests explicitly.
- Never compare a 2-minute run on 5,000 rows against a 30-minute run on 2 million rows as if only one property changed.
- Account for DB background processes, OS page caches, and autoscaling lag.
- Report errors and `dropped_iterations` right beside speed metrics.

## 9. Complete Spring Boot Project with PostgreSQL and Non-Trivial Data

### 9.1. Lab Scenario

We build a **product and event API**:

- 200,000 products in PostgreSQL.
- `GET /api/products/{id}` fetches by primary key.
- `GET /api/products/search?category=books&limit=20&offset=100` queries an indexed category.
- `POST /api/events` records `VIEW`/`CART` events. **Each POST creates one event**, with no auto-retry to avoid duplicates.
- Actuator `health,metrics` listens on loopback port 9091 for observation.
- k6 drives an 80/15/5 mix with hot-key skew at user-chosen RPS and duration.

Running PostgreSQL via Docker Compose models JDBC pooling, SQL plans, indexes, and WAL far better than in-memory H2. Still, **one Postgres container on your laptop is not a production PostgreSQL cluster**—never extrapolate real capacity numbers from local lab runs.

### 9.2. Directory Structure

```text
realistic-load-demo/
├── pom.xml
├── compose.yaml
├── db/
│   └── init.sql
├── load/
│   ├── open-model.js
│   └── closed-model.js
└── src/
    └── main/
        ├── java/com/example/loadstudy/
        │   ├── LoadStudyApplication.java
        │   ├── Product.java
        │   ├── ProductRepository.java
        │   ├── ProductsController.java
        │   └── EventsController.java
        └── resources/
            └── application.properties
```

The files below form the **complete minimal lab**, requiring no external partner API. You need **JDK 17+, Maven, Docker Compose, and k6** to run everything. `docker compose` starts only PostgreSQL; Spring Boot and k6 run directly on the host.

### 9.3. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>realistic-load-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot BOM aligns Spring JDBC, Tomcat, Jackson, HikariCP, and PostgreSQL driver versions. Do not pin individual Spring Framework artifacts to mismatched versions to "optimize benchmarks". `Spring Boot 3.5.16` is pinned for lab reproducibility; for production deployments, use an actively maintained Boot branch per organizational policy.

### 9.4. `compose.yaml`: Local PostgreSQL

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: perfdb
      POSTGRES_USER: perf
      POSTGRES_PASSWORD: dev-only-password
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - ./db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U perf -d perfdb"]
      interval: 5s
      timeout: 3s
      retries: 30
```

- Binds DB port to host **loopback only**—never expose the DB to the Internet.
- `dev-only-password` is strictly a **demo** credential; never reuse lab credentials in production.
- `db/init.sql` runs only when the PostgreSQL container initializes an empty data directory; if a persistent volume already exists, the script **does not re-run**.
- `postgres:16` pins the major version, while minor tags/digests evolve over time; for rigorous comparison benchmarks, **pin the image digest** and record PostgreSQL settings.
- If port 5432 is busy, update both the published host port and JDBC URL.

### 9.5. `db/init.sql`: 200,000 Indexed Products and an Events Table

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    category TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE visit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    session_key VARCHAR(64) NOT NULL,
    event_type VARCHAR(16) NOT NULL
        CHECK (event_type IN ('VIEW', 'CART')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed deterministic: 50% books, 30% electronics, 20% home.
INSERT INTO products (id, category, price_cents, stock, created_at)
SELECT
    n,
    CASE
        WHEN n % 10 < 5 THEN 'books'
        WHEN n % 10 < 8 THEN 'electronics'
        ELSE 'home'
    END,
    1000 + ((n * 37) % 100000),
    (n * 29) % 200,
    now() - (n % 365) * INTERVAL '1 day'
FROM generate_series(1, 200000) AS seq(n);

CREATE INDEX idx_products_category_id
    ON products(category, id);

CREATE INDEX idx_visit_events_product_time
    ON visit_events(product_id, created_at DESC);

ANALYZE products;
```

**Verifiable dataset properties:**

- Exactly **200,000** products with IDs 1..200000.
- 100,000 `books`, 60,000 `electronics`, and 40,000 `home` rows via modulo 10.
- `price_cents` spans 1,000..100,999; `stock` spans 0..199.
- `created_at` spreads across 365 days instead of stamping all rows identically.
- Index `(category, id)` supports category filtering with `ORDER BY id`.
- `visit_events` starts empty and grows on POSTs during load tests, generating WAL and table/index growth.

This remains a **simple formulaic synthetic dataset**, not reproducing every real system's correlations and hotspots. For real workloads, tune schemas, row widths, data sizes, and distributions from telemetry.

### 9.6. `LoadStudyApplication.java`

```java
package com.example.loadstudy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoadStudyApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoadStudyApplication.class, args);
    }
}
```

### 9.7. `Product.java`

```java
package com.example.loadstudy;

public record Product(
        long id,
        String category,
        int priceCents,
        int stock) {
}
```

Java 17 records give a clean DTO. Jackson serializes the field as `priceCents`, not the SQL column name `price_cents`—keep that in mind when writing k6 checks.

### 9.8. `ProductRepository.java` Using `JdbcTemplate` and Parameterized SQL

```java
package com.example.loadstudy;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {

    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Product> find(long id) {
        List<Product> results = jdbc.query(
                """
                SELECT id, category, price_cents, stock
                FROM products
                WHERE id = ?
                """,
                (rs, row) -> new Product(
                        rs.getLong("id"),
                        rs.getString("category"),
                        rs.getInt("price_cents"),
                        rs.getInt("stock")),
                id);
        return results.stream().findFirst();
    }

    public List<Product> search(
            String category, int limit, int offset) {
        return jdbc.query(
                """
                SELECT id, category, price_cents, stock
                FROM products
                WHERE category = ?
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (rs, row) -> new Product(
                        rs.getLong("id"),
                        rs.getString("category"),
                        rs.getInt("price_cents"),
                        rs.getInt("stock")),
                category, limit, offset);
    }

    public long appendEvent(
            long productId, String sessionKey,
            String eventType) {
        Long id = jdbc.queryForObject(
                """
                INSERT INTO visit_events
                    (product_id, session_key, event_type)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                Long.class, productId, sessionKey, eventType);
        if (id == null) {
            throw new IllegalStateException(
                    "INSERT did not return an event id");
        }
        return id;
    }
}
```

**Explanation:**

- SQL uses bind parameters `?` rather than string concatenation.
- `find` performs a primary-key point lookup; `search` uses the category index with offset pagination.
- `appendEvent` uses PostgreSQL's `INSERT ... RETURNING id`; the demo is intentionally PostgreSQL-specific rather than database-agnostic.
- Every HTTP GET/POST borrows a JDBC connection managed through HikariCP.
- The events table stores no PII and implements no idempotency logic. **Never retry POST blindly** after network timeouts, as it can insert duplicates.
- `OFFSET 5000` is a moderate offset; at multi-million offsets, keyset pagination is usually required to avoid scanning and discarding huge row counts.

### 9.9. `ProductsController.java`

```java
package com.example.loadstudy;

import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class ProductsController {

    private static final Set<String> CATEGORIES =
            Set.of("books", "electronics", "home");

    private final ProductRepository products;

    public ProductsController(ProductRepository products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Product> byId(
            @PathVariable long id) {
        if (id < 1 || id > 200000) {
            return ResponseEntity.notFound().build();
        }
        return products.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() ->
                        ResponseEntity.notFound().build());
    }

    @GetMapping("/search")
    public List<Product> search(
            @RequestParam String category,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(defaultValue = "20") int limit) {

        if (!CATEGORIES.contains(category)
                || offset < 0 || offset > 5000
                || limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid search parameters");
        }

        return products.search(category, limit, offset);
    }
}
```

`GET /api/products/search` uses a literal path, so Spring MVC matches it ahead of `/{id}`. Input validation bounds category, offset, and limit to keep test queries controlled. `byId` checks `1..200000` **to match the lab seed**; in production, never hardcode dataset bounds in a controller.

### 9.10. `EventsController.java`: Recording Valid Events

```java
package com.example.loadstudy;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

record EventInput(
        @Min(1) long productId,
        @NotBlank @Size(max = 64) String sessionKey,
        @NotBlank @Pattern(regexp = "VIEW|CART") String eventType) {
}

@RestController
@RequestMapping("/api/events")
public class EventsController {

    private final ProductRepository products;

    public EventsController(ProductRepository products) {
        this.products = products;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Long> append(
            @Valid @RequestBody EventInput input) {
        long id = products.appendEvent(
                input.productId(),
                input.sessionKey(),
                input.eventType());
        return Map.of("id", id);
    }
}
```

Each valid POST inserts one row into `visit_events` and returns **HTTP 201** with JSON containing a positive ID. On a brand-new database with zero events, the first ID is typically 1; **never hardcode `ID=1`** in benchmarks because repeated tests or rolled-back transactions advance the sequence.

Note: demo correctness means **persisting one event per accepted request**, not checkout/payment semantics. Real financial actions require idempotency keys, transactional invariants, auth, and stronger consistency guarantees.

### 9.11. `application.properties`

```properties
spring.application.name=realistic-load-demo

# Lab listens only for HTTP traffic from the local host.
server.port=8080
server.address=127.0.0.1

# PostgreSQL published on localhost by Docker Compose.
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/perfdb
spring.datasource.username=${DB_USER:perf}
spring.datasource.password=${DB_PASSWORD:dev-only-password}

# Bounded pool size to observe saturation.
spring.datasource.hikari.maximum-pool-size=16
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.pool-name=perfPool

# Deliberately tuned for the lab, NOT production defaults.
server.tomcat.threads.max=64

# Loopback-only Actuator for health and metrics.
management.server.port=9091
management.server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
```

In the lab, both the main app and Actuator listen strictly on loopback. **Do not benchmark from a separate machine** while keeping `server.address=127.0.0.1`; in authorized multi-host setups, bind interfaces carefully and secure endpoints. Actuator `metrics` is exposed on loopback **for local observation only**—never expose it publicly in production.

`server.tomcat.threads.max=64` and Hikari max pool 16 are **deliberate values to make limits observable**, not universal recommendations. Servlet threads waiting on Hikari drive latency up even when CPU is idle.

## 10. k6: Open Workload with 80% Detail, 15% Search, 5% Write

### 10.1. Why Choose an Arrival-Rate Executor?

We want **request launch rate per second** independent of SUT latency. When the backend slows down, rising in-flight backlogs and tail latencies must become visible. Because each iteration sends one HTTP request, target iterations/s equals target HTTP RPS when dropped iterations are zero.

k6 provides `constant-arrival-rate` with `rate`, `timeUnit`, `duration`, and `preAllocatedVUs`. Omit `sleep()` at the end of the iteration because the arrival-rate executor paces launches itself.

### 10.2. `load/open-model.js` — Complete Script

```javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const PRODUCTS = Number(__ENV.PRODUCTS || '200000');
const TARGET_RPS = Number(__ENV.RPS || '20');
const VUS = Number(__ENV.VUS || '80');
const DURATION = __ENV.DURATION || '5m';

export const options = {
  scenarios: {
    mixedTraffic: {
      executor: 'constant-arrival-rate',
      rate: TARGET_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS,
      gracefulStop: '15s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{operation:detail}': [
      'p(95)<300', 'p(99)<800',
    ],
    'http_req_duration{operation:search}': [
      'p(95)<600',
    ],
    'http_req_duration{operation:event}': [
      'p(95)<800',
    ],
    dropped_iterations: ['count<1'],
  },
  summaryTrendStats: [
    'avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max',
  ],
};

// 70% reads hit the hot 10% IDs, 30% hit the entire range.
function randomProductId() {
  const hotCount = Math.max(1, Math.floor(PRODUCTS * 0.1));
  const range = Math.random() < 0.70 ? hotCount : PRODUCTS;
  return 1 + Math.floor(Math.random() * range);
}

// Category ratios matching SQL seed: 50/30/20.
function randomCategory() {
  const p = Math.random();
  if (p < 0.50) return 'books';
  if (p < 0.80) return 'electronics';
  return 'home';
}

function detail() {
  const id = randomProductId();
  const res = http.get(
    `${BASE}/api/products/${id}`,
    { tags: { name: 'GET /api/products/{id}', operation: 'detail' } },
  );
  check(res, {
    'detail HTTP 200 and correct id':
      (r) => r.status === 200 && Number(r.json('id')) === id,
  });
}

function search() {
  const category = randomCategory();
  const offsets = [0, 0, 20, 100, 1000, 5000];
  const offset = offsets[Math.floor(Math.random() * offsets.length)];
  const url = `${BASE}/api/products/search?category=${category}&limit=20&offset=${offset}`;
  const res = http.get(url, {
    tags: { name: 'GET /api/products/search', operation: 'search' },
  });
  check(res, {
    'search HTTP 200 and JSON array':
      (r) => r.status === 200 && Array.isArray(r.json()),
  });
}

function writeEvent() {
  const id = randomProductId();
  const session = `run-${__ENV.RUN_ID || 'local'}-vu-${__VU}-it-${__ITER}`;
  const payload = JSON.stringify({
    productId: id,
    sessionKey: session,
    eventType: Math.random() < 0.9 ? 'VIEW' : 'CART',
  });
  const res = http.post(`${BASE}/api/events`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'POST /api/events', operation: 'event' },
  });
  check(res, {
    'event HTTP 201 and positive id':
      (r) => r.status === 201 && Number(r.json('id')) > 0,
  });
}

export default function () {
  const p = Math.random();
  if (p < 0.80) {
    detail();
  } else if (p < 0.95) {
    search();
  } else {
    writeEvent();
  }
}
```

**How the script works:**

- `RPS`, `DURATION`, and `VUS` can be overridden via k6 `-e` flags; default is **20 iterations/s for 5 minutes**.
- `PRODUCTS=200000` must match the seeded dataset; update it if you change the seed.
- `preAllocatedVUs` equals `maxVUs` to prevent runtime VU allocation spikes; if drops occur, verify whether the SUT stalled, the generator saturated, or pre-allocation was too low.
- Each iteration picks **one** branch ⇒ one HTTP request; the 80/15/5 split holds stochastically across large samples, not exactly on tiny counts.
- `tags.name`/`operation` stay low-cardinality for per-endpoint grouping. Never embed `productId` or `sessionKey` into metric names/tags.
- Keep `RUN_ID` to a short synthetic string (under ~16 chars) so combined with VU/iteration suffixes it never exceeds `session_key VARCHAR(64)`.
- GET chooses seeded IDs; search uses valid categories/offsets; POST sends synthetic `sessionKey`s.
- `checks` verify basic **status and payload correctness**—HTTP 200 returning the wrong product ID must fail.
- Example p95/p99/error/drop thresholds are **practice thresholds**, not universal production SLOs.
- If k6 runs out of VUs to sustain the target rate, `dropped_iterations > 0` fails the threshold—never report the configured rate as the achieved rate.

**Script limitations:** this random mix is educational; it omits login, multi-step user journeys, TLS, CDN, cookies, real user pagination, retries, and multi-tenancy. Derive real production profiles from telemetry rather than assuming 80/15/5 or 70% hot keys.

### 10.3. k6 Is Not a Full Browser

k6's HTTP executor does not render DOM, run frontend JS, or fetch images/CSS like a browser. For user-perceived page-load SLAs, combine with browser-level tests or RUM. For backend API latency SLAs, HTTP-level k6 is well suited. Never equate k6 VU count directly with open browser tabs or concurrent website visitors.

### 10.4. Notes on Read/Write Counts and Test State

At 20 RPS × 5 minutes with zero drops, expect mathematically around **6,000 HTTP requests** and **~300 POST events**; actual counts vary slightly due to randomness, errors, dropped iterations, and exact timing. These are **not** pre-run measurements.

A 2-hour soak at 80 RPS with 5% POSTs **expects** ~28,800 events if full load completes cleanly; monitor table size, WAL, and autovacuum, and reset/clean up test environments afterward.

## 11. k6 Closed Model: Sessions and Think Time

When modeling concurrent users performing actions separated by pauses, use `constant-vus`. File `load/closed-model.js`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    users: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || '30'),
      duration: __ENV.DURATION || '5m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const id = 1 + Math.floor(Math.random() * 200000);
  const res = http.get(
    `${BASE}/api/products/${id}`,
    { tags: { name: 'GET /api/products/{id}', operation: 'detail' } },
  );
  check(res, { 'detail result': r => r.status === 200 });
  sleep(1 + Math.random() * 2);
}
```

This is a **different** scenario for study, not interchangeable with open-model results:

- Each VU fetches once then sleeps 1–3 seconds; when the server slows down, iterations lengthen ⇒ RPS falls.
- `VUS=30` does **not** mean 30 simultaneous HTTP requests at every instant.
- Never use closed-model results to claim the system sustains a fixed open arrival rate.
- To model full user journeys, expand iterations into login → search → detail → cart → checkout with realistic think times, then measure **business transactions/s**.

## 12. Running the Lab Step by Step and Checking Data

### 12.1. Start PostgreSQL

From `realistic-load-demo`:

```bash
docker compose up -d
docker compose ps
docker compose logs db --tail=20
```

Wait until the DB healthcheck reports healthy and `init.sql` finishes. The first run pulls the image and generates 200,000 rows, taking time depending on your machine—do not assume instant readiness.

### 12.2. Verify the SQL Seed

```bash
docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) AS product_count FROM products;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY category;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) AS event_count FROM visit_events;"
```

Expected counts **on a freshly initialized database**:

```text
product_count = 200000
books         = 100000
electronics   = 60000
home          = 40000
event_count   = 0
```

These are **expected SQL values**, not verbatim `psql` table borders. If reusing a volume from an earlier run, counts and `event_count` will differ.

### 12.3. Build and Run Spring Boot

With JDK 17+, Maven, and healthy PostgreSQL:

```bash
mvn clean package
java -jar target/realistic-load-demo-1.0.0.jar
```

If running from an IDE, confirm working directory and `application.properties`. If ports 8080, 9091, or 5432 are occupied, update settings and k6 URLs accordingly.

### 12.4. HTTP Smoke Tests

In another terminal:

```bash
curl -i http://127.0.0.1:8080/api/products/42

curl -i "http://127.0.0.1:8080/api/products/search?category=books&offset=0&limit=2"

curl -i -X POST http://127.0.0.1:8080/api/events \
  -H "Content-Type: application/json" \
  --data '{"productId":42,"sessionKey":"demo-1","eventType":"VIEW"}'
```

For `GET /api/products/42`, expected status is **200** and JSON contains exact field values:

```json
{"id":42,"category":"books","priceCents":2554,"stock":18}
```

Because `42 % 10 = 2`, category is `books`; `1000 + 42×37 = 2554`; and `(42×29) % 200 = 18`. JSON key ordering is not guaranteed.

Searching `books` with `limit=2` returns a **JSON array of two products** starting with the lowest valid category IDs in ascending order. A valid POST returns **HTTP 201** with a positive event ID, e.g.:

```json
{"id":1}
```

**`id=1` only holds on a brand-new table prior to any other inserts.** Subsequent runs produce higher IDs; assertions must only require a positive ID. Never wipe tables shared with other work.

### 12.5. Metrics from Actuator

After running a few requests:

```bash
curl -i http://127.0.0.1:9091/actuator/health

curl -s http://127.0.0.1:9091/actuator/metrics

curl -s http://127.0.0.1:9091/actuator/metrics/http.server.requests

curl -s http://127.0.0.1:9091/actuator/metrics/jdbc.connections.active
```

These return **Actuator JSON metrics**, not Prometheus text format. Available meters depend on instrumentation and runtime—never guarantee a fixed list or hardcoded values. In production, secure Actuator via private network and auth rather than exposing metrics publicly.

### 12.6. Warm Up, Then Run Baseline

Once k6 is installed per official documentation:

```bash
k6 run -e RPS=10 -e VUS=40 -e DURATION=3m \
  load/open-model.js

k6 run -e RPS=50 -e VUS=100 -e DURATION=10m \
  --summary-export=baseline-50rps.json \
  load/open-model.js
```

k6 thresholds may fail on an underpowered laptop; a failure is **diagnostic signal to investigate**, not a bug to silence. Compared to production baselines, 10 minutes is a learning baseline that may miss longer GC or background cycles.

### 12.7. Measure Peak and Probe Limits

```bash
k6 run -e RPS=100 -e VUS=150 -e DURATION=15m \
  --summary-export=peak-100rps.json \
  load/open-model.js

k6 run -e RPS=150 -e VUS=250 -e DURATION=10m \
  --summary-export=stress-150rps.json \
  load/open-model.js
```

**Run only on hardware and environments authorized for load.** These figures teach profiling methodology—they are not target SLOs or safe limits for a laptop. Before stepping up load, watch errors, dropped iterations, Hikari pending, DB CPU/disk, k6 generator CPU, and event growth.

### 12.8. Measure Session-Based Closed Model

```bash
k6 run -e VUS=30 -e DURATION=5m \
  load/closed-model.js
```

Store results separately, and **never compare its RPS directly** against the open model without documenting think times and transaction modeling.

### 12.9. Check Event Growth and Reset the Lab

```bash
docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) FROM visit_events;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT pg_size_pretty(pg_total_relation_size('visit_events'));"
```

To reset the local demo database **only when certain nothing needs to be kept**:

```bash
docker compose down -v
docker compose up -d
```

**Warning:** `down -v` destroys Compose project volumes—never run it where data must be preserved. Production-like staging requires approved seed/cleanup workflows, snapshots, and synthetic datasets.

## 13. Designing Stress, Spike, and Soak Beyond Baseline

### 13.1. Stepping Arrival Rate Across Stages

To simulate varying request arrival rates, use k6 `ramping-arrival-rate`. **Configuration snippet** replacing `scenarios` inside `open-model.js`:

```javascript
scenarios: {
  ramped: {
    executor: 'ramping-arrival-rate',
    startRate: 10,
    timeUnit: '1s',
    preAllocatedVUs: 150,
    maxVUs: 150,
    stages: [
      { target: 50, duration: '3m' },
      { target: 50, duration: '10m' },
      { target: 100, duration: '3m' },
      { target: 100, duration: '15m' },
      { target: 10, duration: '3m' },
    ],
  },
},
```

This is a **fragment of the `options` object**, not a standalone JS file. Total scheduled runtime is **34 minutes**, ramping linearly across transition stages. Analyze p95 per stage/time window rather than blending all 34 minutes together.

### 13.2. Stress Testing to Find the Capacity Knee

Step load up (e.g., 20 → 50 → 80 → 100 → 120 RPS), holding each plateau long enough to stabilize. Watch for the knee where:

- p95/p99 grows faster than RPS;
- throughput flattens despite rising arrival rate;
- `dropped_iterations` climbs as slow iterations exhaust VUs;
- Hikari pending/timeouts and DB locks climb;
- Tomcat busy workers approach max;
- CPU throttling, GC pauses, or network queues grow;
- 503/timeout rates rise and recovery lags.

The SLO-breach knee prior to crashing is far **more useful** than boasting "max 500 RPS" when 40% of requests failed.

### 13.3. Spikes and Autoscaling

In an autoscaled cluster:

- Measure time-to-scale-out and startup/readiness latency.
- Check whether **per-replica** connection pools multiply total DB connections past DB max.
- Test both the burst and post-spike recovery, not just final steady state.
- Ensure the load generator sustains target rate while the SUT scales.
- Record HPA events, pod scheduling delays, image pulls, and cache warm-up.

Autoscalers are never instantaneous; short spikes can still pile up queues and timeouts before new replicas become Ready.

### 13.4. Soak Testing and Data Growth

A 1–4+ hour soak requires inspecting **time series**:

- Does post-GC heap return to baseline?
- Do Hikari active/pending/timeout counts drift upward?
- Do DB connections, locks, or long transactions accumulate?
- Does `visit_events`/WAL/bloat growth cause p95 drift?
- Do background jobs, autovacuum, or checkpoints trigger latency spikes?
- Are logs, disk, or temp directories filling up?
- Are there resource leaks in HTTP clients, JDBC connections, or thread pools?

A soak test is meaningful only when **sustaining representative load** across enough time. "Running 4 hours with 1 VU" never proves peak endurance.

## 14. Analyzing Results: Separating Real Bottlenecks from Generator Issues

### 14.1. Order of Result Analysis

1. Confirm **the test sent the intended workload**: target RPS/VUs, mix, dataset, duration.
2. Check **achieved HTTP throughput**; if below target, inspect `dropped_iterations` and generator utilization.
3. Verify **correctness** and error rates; fast 500s or wrong-ID 200s are failures.
4. Inspect p50/p95/p99 **per endpoint**, not just global aggregates.
5. Align timestamps with CPU, GC, Tomcat, Hikari, PostgreSQL, and network graphs.
6. Find which stage shifted first to identify the candidate bottleneck.
7. Change **one variable** with the same workload/dataset to verify the hypothesis.
8. Repeat runs and report variance; never trust a single "clean" run.

### 14.2. Mathematical Illustration (Not Executed Output)

Targeting 100 iterations/s over 10 minutes schedules ~**60,000** iterations. If each iteration issues one request and k6 sends only 45,000 while recording 15,000 `dropped_iterations`, **never** claim "100 RPS achieved". Average achieved rate is roughly 75 req/s across 600 s (check time-series distribution too).

If detail p95 < 300 ms while search p95 > 1 s, combined p95 may still look fine simply because detail is 80% of traffic. Always enforce **per-operation thresholds**, and track low-volume critical operations like checkout/payment separately.

### 14.3. Symptom → Hypothesis → Evidence Matrix

| Symptom | Hypothesis to Test | Evidence |
| --- | --- | --- |
| CPU 95%, low GC, flat throughput | CPU-bound | CPU profile/flamegraph, request mix |
| Low CPU, Tomcat busy at max | Blocking waits/threads | Thread dumps, Hikari pending, downstream latency |
| Hikari pending rising, `active=max` | DB connection pool saturated | `jdbc.connections.active`, Hikari metrics |
| High DB CPU, slow queries | Query/index/data volume | `EXPLAIN ANALYZE BUFFERS`, `pg_stat_statements` |
| DB lock waits | Hot-row writes or transaction contention | `pg_locks`, `pg_stat_activity` |
| p95 drifts up over time, post-GC heap climbs | Memory leak / retention | JFR/heap analysis, GC logs |
| Periodic p99 spikes every minute | Scheduled jobs / DB checkpoints | Time-aligned app and DB events |
| `dropped_iterations` even at low load | Too few pre-allocated VUs or under-sized generator | Generator CPU, VUs, iteration duration |
| Drops appear after SUT latency rises | Backpressure / capacity knee | VU usage, SUT metrics, RPS time series |
| Hot-ID GETs fast, random IDs slow | Working set / cache miss | Cache hit ratio, DB buffer hits vs reads |
| Search with large offset slow | Deep pagination scan/index cost | Query plan, `LIMIT/OFFSET` execution cost |
| Event POST slows down late in soak | Table/WAL/index growth | Table size, vacuum stats, disk I/O |
| Rising 429 errors | Rate limiter / upstream quota | Response headers, quota stats |
| 503/504 at proxy, sparse app logs | LB/proxy timeout or upstream networking | Proxy access/error logs |
| k6 host CPU 100%, SUT idle | Generator bottleneck | Generator metrics; split across generator hosts |
| HTTP 200 yet checks fail | Bad payload or business logic bug | Response checks and app logs |
| Latency drops while errors climb | Fast failures masking tail latency | Split latency of successful vs failed requests |
| HPA adds pods, DB slows down further | Aggregate pools exceed DB capacity | Sum of pool maximums, PostgreSQL active connections |

Trust a hypothesis only when corroborated by **cross-layer evidence**. Never raise Tomcat threads to 2,000 simply because latency jumped: with a 16-connection DB pool, extra threads just worsen queueing and memory.

### 14.4. Benchmark the k6 Generator Too

k6 executes JavaScript assertions and drives HTTP traffic. If the generator runs out of CPU or ephemeral sockets, `dropped_iterations` and inflated latencies reflect **the test harness**, not the server. Monitor generator OS CPU, RAM, file descriptors, NIC, and DNS, and verify from a second host when needed. Large production-like loads require distributed load generation with aggregated metrics.

## 15. Validating Correctness Alongside Side Effects

### 15.1. HTTP 200 Does Not Guarantee Business Correctness

Assert beyond status codes:

- `GET product/{id}` returns the **matching ID**, never another ID's cached response.
- Search returns arrays matching category, sort order, and pagination.
- POST persists **one event** per accepted request.
- No lost writes under load; row counts, WAL, and storage align.
- Idempotency keys protect payments/orders across retries.
- Authorization and tenant isolation hold under concurrency.
- 5xx, timeouts, and 429s conform to API error contracts.

The lab script runs lightweight checks (ID match, JSON array, positive event ID); real apps need thorough contract checks without making each VU parse massive payloads in a way that distorts generator CPU.

### 15.2. Never Generate Corrupt or Harmful Side-Effect Data

Write-heavy tests must use synthetic data respecting foreign keys, validation, and business invariants. If a test writes 500,000 event rows filling disk, plan cleanup/retention. For order/payment/email flows, enforce sandbox idempotency, disable external side effects, or point at safe downstream stubs—**never** charge real cards or email real users.

### 15.3. Static vs Mutable Test Data

Distinguish:

- Static dataset for GET/search: stays unchanged across runs.
- Mutable data inserted by POST: grows during tests and alters DB behavior.
- Cache state: record warm vs cold explicitly.
- Tenant/user sessions: may require token/cookie lifecycles.
- Background cleanup/batch jobs: can mutate row counts mid-test.

If run A reads 200,000 rows after 1,000 event inserts while run B runs after 1,000,000 inserts, those two runs **do not share the same starting state**.

## 16. Writing Benchmark Reports That Do Not Mislead

Minimum report template:

```text
Benchmark name:
Code revision / Spring Boot / JDK:
Environment: pods/CPU/RAM/DB/network/region:
Data: row counts, size, skew, preloaded events:
Workload: GET detail/search/POST events = 80/15/5:
Arrival model: constant-arrival-rate:
Target iterations/s and expected HTTP RPS:
Achieved RPS and dropped iterations:
Warm-up / steady-state / peak / soak windows:
Per-operation sample count and p50/p95/p99:
HTTP error rate and failed business checks:
CPU, JVM heap/GC, Tomcat busy:
Hikari active/pending/max/timeout:
PostgreSQL CPU/IO/locks/query plans/WAL:
SLO pass/fail with exact thresholds:
Evidence: k6 summary, time series, logs/traces:
Limitations: topology mismatch, unmodeled cache/auth:
Decision: pass / capacity limit / investigate:
```

This is a **template of fields to populate from real measurements**, not executed results. When reporting to stakeholders, always separate:

- **Configured target** vs **achieved throughput**.
- **Successful requests** vs **all attempted requests**.
- **Open-model target rate** vs **closed-model measured RPS**.
- **Per-operation percentiles** vs global aggregates.
- **Measured results** vs **mathematical estimates**.
- **Lab boundaries** vs production guarantees.

### 16.1. How to Phrase a Proper Conclusion

Conditional conclusion template (**never fill with fabricated numbers**):

> "In the documented environment, with dataset X and workload Y, the system achieved throughput Z over steady-state window T; p95/p99, error rates, and drops met (or failed) the defined thresholds. The observed bottleneck involved ..., evidenced by .... Results do not directly transfer to production where topology, data, or network conditions differ."

Never claim "Spring Boot supports 10,000 concurrent users" merely because k6 spun up 10,000 VUs in a short test without reporting RPS, response times, error rates, and duration.

## 17. Common Pitfalls to Avoid

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Testing with 1 row / 1 SKU | Caches and indexes stay artificially tiny | Use realistic cardinality, width, and skew |
| Testing GET only, skipping writes | Misses locks, WAL, and DB growth | Include realistic read/write mix |
| Uniform random IDs | Ignores hot-key skew | Model Zipf/weighted skew from telemetry |
| Using H2 to predict production PostgreSQL | Different optimizer, concurrency, and WAL | Use production-like engine and topology |
| Benchmarking only one fast endpoint | Global p95 hides slow search/checkout | Test per-route operation mix |
| Assuming "100 VUs = 100 RPS" | VUs are execution loops, not arrival rate | Report target vs achieved RPS |
| Using closed model for open arrival demand | Slow responses throttle RPS automatically | Use arrival-rate executors |
| Ignoring `dropped_iterations` | Target load was never actually sent | Enforce drop thresholds and watch generator metrics |
| Adding `sleep` inside arrival-rate iterations | Exhausts VUs and causes dropped iterations | Let the executor pace; put think time in closed/journey tests |
| Reporting only global p95, hiding p99/per-route | Rare slow endpoints stay masked | Enforce per-operation thresholds |
| Checking error status while skipping correctness | Wrong-data 200s look healthy | Assert body fields and business invariants |
| Mixing warm-up into steady-state results | JIT/cold caches skew metrics | Separate stages and time windows |
| Running 30 seconds and claiming endurance | Misses GC cycles, DB maintenance, leaks | Soak across representative cycles |
| Running k6 and SUT on one laptop unmonitored | Generator contention masks server limits | Dedicated generator host + generator metrics |
| Comparing runs across different datasets | Changing cardinality/size alters plans | Controlled seeding and resets |
| Raising Tomcat threads when VUs slow down | DB pool or CPU may be the real bottleneck | Cross-check Tomcat, Hikari, and DB metrics |
| Looking only at CPU | Thread waits and I/O do not burn CPU | Check thread dumps, Hikari pending, DB waits |
| Testing warm cache and claiming cold-start readiness | Misrepresents restarts and rollouts | Run cold and warm profiles separately |
| Ignoring 429/5xx in latency averages | Fast failures make latency look better | Split error counts and success-only latency |
| Load-testing production/partners unapproved | Causes outages or quota billing | Use approved staging |
| Putting PII into seeds or k6 outputs | Data leaks | Use synthetic/anonymized generators |
| Claiming "guaranteed" capacity from a laptop | Non-equivalent environment | State limits and revalidate in staging/prod-like |
| Failing to pin images/versions | Benchmark results drift silently | Pin Boot/JDK/PG/image digests and artifacts |
| Discarding configs or raw RPS/latency time series | Impossible to reproduce or investigate | Archive artifacts, metrics, and time series |

## 18. Hands-On Exercises

### Exercise A — Scale the Dataset Without Changing Code

Replace `generate_series(1, 200000)` with `generate_series(1, 2000000)`, update the ID check in the controller and `PRODUCTS` in k6, keeping traffic mix and RPS unchanged. Compare `EXPLAIN (ANALYZE, BUFFERS)`, search p95, DB size, heap, and Hikari. **Never** assume every query slows down 10×: indexes, caches, and query plans scale nonlinearly.

### Exercise B — Vary Hot-Key Skew

Run three profiles—10% hot, 70% hot, 95% hot—holding dataset, RPS, duration, and seeding comparable. Measure cache hits, DB CPU, and point-GET p95. Analyze why skew helps reads while raising contention if hot keys are updated concurrently.

### Exercise C — Closed vs Open Under Identical Conditions

Run 30 VUs with 1–3 s think time and record achieved RPS. Then run `constant-arrival-rate` at that exact measured RPS. Compare p95/p99 and behavior when injecting extra backend wait time. Explain why closed RPS drops when the server slows while open mode holds arrival rate.

### Exercise D — Find the Capacity Knee

Run 20, 40, 60, and 80 RPS long enough at each plateau to stabilize; record p95, p99, errors, `dropped_iterations`, Hikari pending, and CPU. Plot latency against achieved RPS to locate the steep inflection point. Stop escalating once the SUT breaches safe environmental error thresholds.

### Exercise E — Adjust DB Pool Concurrency

Hold SUT, load, and dataset constant while testing Hikari max 8, 16, and 24; measure wait times and DB CPU. Draw conditional conclusions: larger pools can cut acquire wait yet heighten DB contention—never assume the largest pool is fastest.

### Exercise F — Soak with Write Growth

Run 1–2 hours at an authorized rate, tracking `visit_events` row/index sizes, PostgreSQL WAL, autovacuum, and 5-minute p95 slices. Compare post-GC heap and Hikari pending for drift. Avoid mistaking expected table growth for a memory leak.

### Exercise G — Fast HTTP 500s Skewing Metrics

Modify a stub so 20% of requests return HTTP 500 immediately. Compare combined p95 vs success-only p95 and error rate. Explain why aggregate latency looks deceptively low while service quality collapses.

### Exercise H — Running Alongside Maintenance Batches

Run the benchmark alongside an authorized maintenance batch vs without it, holding workload fixed. Compare DB locks/IO, p99 spikes, CPU, and queues. Nighttime-only quiet benchmarks fail to represent daytime peaks.

## 19. Self-Assessment Questions

1. **Is a 10,000-row uniform random dataset representative of production?** No; cardinality, row width, skew, read/write mix, indexes, and cache behavior matter too.
2. **Do 100 VUs equal 100 concurrent HTTP requests?** No. VUs sleep, wait, or issue multiple calls per iteration.
3. **Do 100 VUs automatically generate 100 RPS?** No; RPS depends on iteration duration and think time.
4. **How does an open model differ from a closed model?** Open models schedule arrivals independently of responses; closed models wait for each VU's response before starting the next iteration.
5. **What does `dropped_iterations` mean?** Scheduled iterations k6 could not start on time due to insufficient VUs/generator capacity or a slow SUT.
6. **If a test targets 100 RPS and achieves 75 RPS, did it pass 100 RPS?** No.
7. **Can Little's Law use p95 to compute concurrency?** No; steady-state Little's Law requires the corresponding mean duration.
8. **Why do you need a warm-up phase?** JIT, connection pools, caches, and database buffers need to reach representative steady states.
9. **Why run soak tests?** To uncover memory/pool leaks, GC drift, DB table/WAL growth, checkpoints, and background job interference.
10. **Can global p95 mask a slow search endpoint?** Yes, if search is a small share of total traffic.
11. **Is low SUT CPU paired with high latency contradictory?** No; threads may be waiting on DB connections, locks, or networks.
12. **Do Spring Boot Actuator metrics replace k6?** No; server metrics do not generate scheduled arrivals or verify client-side correctness.
13. **Do k6 HTTP metrics measure browser rendering time?** No; use browser tests or RUM for full user-perceived rendering.
14. **Is comparing two runs on different dataset sizes a clean A/B test?** No.
15. **Is raising DB pool from 16 to 64 always better?** No; it can overload the DB with lock contention and CPU/IO pressure.
16. **Does HTTP 200 returning the wrong product ID pass?** No; correctness assertions must verify payloads.
17. **Can event POSTs be retried unconditionally?** No, retries risk duplicate inserts without idempotency.
18. **May you stress-test public partner systems without permission?** No.
19. **Why monitor load generator CPU?** To separate k6 bottlenecks from SUT bottlenecks.
20. **What makes a benchmark conclusion trustworthy?** Documented workload/data/duration, target vs achieved rates, errors/checks, per-operation p95/p99, server/DB metrics, repeated runs, and explicit environmental limitations.

## 20. Official References

- [Spring Boot 3.5 — Actuator Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, metrics, and tracing.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): HTTP server metrics, DataSource/HikariCP, JVM metrics.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Tomcat/thread configuration and web runtime.
- [Spring Boot 3.5 — Data SQL/JdbcTemplate](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasources, JDBC, and connection pooling.
- [Grafana k6 — Executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/): scenario executor types.
- [Grafana k6 — Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): open-model rate, `timeUnit`, and VUs.
- [Grafana k6 — Ramping Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): staging arrival rates.
- [Grafana k6 — Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): diagnosing missed target rates.
- [Grafana k6 — Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): `http_req_duration`, `http_req_failed`, `http_reqs`, and network timings.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): validating p95/p99/error/drop criteria.
- [Grafana k6 — Environment Variables](https://grafana.com/docs/k6/latest/using-k6/environment-variables/): `-e` and `__ENV`.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and runtime stats.
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plans and performance analysis.
- [PostgreSQL — Set Returning Functions](https://www.postgresql.org/docs/current/functions-srf.html): `generate_series` used to seed data.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): lifecycle/readiness effects on traffic and scaling.

**Conclusion:** Meaningful Spring Boot load testing must simultaneously represent **data**, **arrival rates and concurrency**, **runtime duration**, and **operation mix and correctness**, while capturing telemetry across k6, JVM/Tomcat/HikariCP, and PostgreSQL. Always publish **target vs achieved**, per-operation p95/p99, errors/dropped iterations, warm-up/steady/soak windows, dataset specs, and environmental limits. Never turn a high lab RPS number into a production capacity promise without matching workloads and cross-layer evidence.