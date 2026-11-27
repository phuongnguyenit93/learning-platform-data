# Resource Limits and Environment-Specific Configuration Separation

## 1. Scenario: A Java Driver Configuration That Works in Dev but Overloads Production

A team writes a Java service using **Apache Cassandra** to store sensor events. In the development environment, the application has only a few threads, small data, and a single Cassandra node. To "speed things up", the author tries the following changes:

- Creates a separate `CqlSession` for every HTTP request and then closes it.
- Increases the page size to 10,000 to avoid fetching multiple pages.
- Increases the connection count and asynchronous requests without any limit.
- Sets the timeout from 2 seconds to 30 seconds to reduce error messages.
- Uses the exact same `application.conf` file, credentials, and Cassandra addresses for dev, staging, and production.

Everything may "work" on a development machine. But when production receives 8,000 requests/second, the system exhibits **ballooning in-flight requests**, rising heap/GC, overloaded coordinators, and p99 latency climbing to several seconds. There are timeouts where the client has already given up while replicas are still processing, and then the service retries and generates even more load.

**The problem is not just tweaking a few numbers.** With Cassandra, Java Driver 4.x is a **distributed client with connection pooling, routing, request multiplexing, retries, paging, and timeouts**. Every parameter alters both application efficiency and the amount of work sent to coordinators/replicas. Configuration must reflect the **topology, consistency level, security, and capacity** of each environment.

This lesson belongs to the **Java driver basics** chapter in the Cassandra module, connecting Java Driver knowledge with partition keys, CQL, replication, reads/writes, errors, compaction, and operational diagnostics.

**Expected outcomes:**

1. Explain the `CqlSession` lifecycle and why you must not create a session per request.
2. Distinguish between **connection count, in-flight requests, request throttling, page size, timeout, retry, and total bytes read**.
3. Estimate concurrency using workload and latency budgets instead of blindly increasing the connection pool.
4. Configure Java Driver 4.x using **HOCON, execution profiles**, and separate dev/staging/prod configurations without embedding secrets.
5. Write CQL and Java using **prepared statements, `LOCAL_QUORUM`, bounded async concurrency**, error handling, and latency measurement.
6. Design dashboards, alerts, canaries, and a config change process with rollback.

> **Version scope:** the examples target the `com.datastax.oss.driver.api.*` API family of Apache Cassandra Java Driver 4.x. Option names, default values, pooling/throttling algorithms, metrics, and reload capabilities vary by **minor version or distribution**. All numbers are **experimental values**, not default production recommendations. Verify the documentation and configuration of the running version before applying.

## 2. Where Does the Driver Sit in the Distributed Read/Write Path?

~~~mermaid
flowchart TD
    A["API / Java service"] --> B["Admission control / bounded queue"]
    B --> C["CqlSession, prepared statements, request profiles"]
    C --> D["Driver routing + connection pools + timeouts/retries"]
    D --> E["Cassandra Coordinator"]
    E --> F["Replicas by partition token + RF + CL"]
    F --> G["Memtable / SSTable / commit log / disk"]
    H["Metrics and tracing"] -.-> A
    H -.-> D
    H -.-> E
    H -.-> F
    I["JVM/OS resources"] -.-> C
    I -.-> G
~~~

A `SELECT` operation by partition key passes through these layers:

1. The application receives the request, checks the deadline, and enforces the concurrency limit.
2. The Java Driver selects the execution profile, serializes/binds CQL, and uses a route/connection to an appropriate node.
3. The receiving node acts as the **coordinator**, determining the natural replicas based on token, RF, and topology.
4. The coordinator collects responses according to the consistency level. Replicas may have to scan SSTables, reconcile versions/tombstones, and read from disk.
5. The driver receives the response or error, decodes rows, and may fetch additional pages.

**The driver's connection pool is not the replication factor.** Adding two connections to a coordinator does not create two copies of the data; increasing RF also does not automatically provision more connection pools. **CL is not a timeout**: `LOCAL_QUORUM` with RF = 3 requires two responses within the DC, but each response can still be slow due to I/O, GC, or network.

### 2.1. Two Independent Groups of Limits

| Layer | Limits/controls | Goal |
| --- | --- | --- |
| **Application** | HTTP admission, request deadline, thread/queue pool, tenant quota. | Prevent traffic beyond application capacity and preserve SLOs. |
| **Java Driver** | Pool/connection, in-flight/request throttler, page size, request timeout, retry policy. | Dispatch requests to Cassandra in a controlled manner. |
| **Cassandra coordinator** | Request handling, timeouts, dropped tasks, tombstone/other guardrails. | Coordinate replicas and protect nodes. |
| **Replica/JVM/OS** | CPU, heap, off-heap, commit log, SSTable, disk IOPS, network. | Physical limits of the execution path. |
| **Infrastructure** | Network policy, TLS, container quota, secret lifecycle, DC capacity. | Environment isolation and security. |

Raising a threshold in the driver **does not increase** the resources of a Cassandra node. Good configuration requires coordinating across layers rather than replacing server guardrails with unbounded client retries.

## 3. `CqlSession`: One Long-Lived Object for Many Requests

`CqlSession` holds cluster metadata, topology/routing, connections, execution resources, and prepared statements serving many requests. Driver 4.x is designed for thread-safe session reuse across multiple threads; the standard pattern is to **create one session per logical cluster/identity/configuration**, share it for the lifetime of the service, and close it cleanly.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class SessionLifecycleExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            // Reuse the same session for many requests across the service lifecycle.
            // Do not create a new session inside each HTTP handler.
            System.out.println("Cassandra session initialized");
        }  // Close the session on service shutdown or during controlled replacement.
    }
}
~~~

**The example above is for lab use only.** Production requires TLS, authentication, contact points, local DC, and proper configuration resources. With Spring or a DI framework, `CqlSession` is typically declared as a container-managed **singleton bean**; do not close it when an individual request completes.

### 3.1. Why Is Creating a Session per Request Expensive?

Each new session may need to establish connections, perform TLS/authentication handshakes, load metadata, initialize driver resources, and prepare queries. Under growing traffic, this causes:

- Unnecessary TCP connections and TLS handshakes.
- Increased heap, threads/buffers, and Java-side garbage collection overhead.
- Extra metadata/control traffic to Cassandra.
- Connection churn, `Too many open files`, or ephemeral port pressure.
- Loss of prepared statement reuse and stable route selection.

There is **no** rule of "one `CqlSession` per node". A session can manage multiple nodes and multiple connection pools. If an application genuinely accesses **two independent clusters, two identities, or two different security configurations**, separate sessions may be required; capacity and lifecycle must be planned separately for each session.

### 3.2. Reusable Prepared Statements

~~~sql
-- CQL template; the application will bind parameters.
SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
~~~

Prepare the statement **once per query template** (or use a controlled cache), then bind values per request. Avoid building distinct CQL text for every partition key value: that both increases overhead and risks unsafe data interpolation into the statement.

## 4. Cassandra Connection Pools Differ from JDBC Relational Database Pools

JDBC pools typically assign one connection to a transaction/request in a "borrow–return" model. The Cassandra native protocol supports **multiple concurrent requests on the same connection** (multiplexing) according to protocol/driver capabilities. Therefore:

| Question | Accurate understanding for Java Driver |
| --- | --- |
| "Does each request need its own connection?" | **No.** A single connection can handle multiple in-flight requests. |
| "Will increasing connections 100x increase throughput 100x?" | **No.** Coordinator/replica, network, queues, CPU, and disk determine the limit. |
| "Does a `CqlSession` connect only to the first contact point?" | **No.** Contact points are for initial discovery; the driver tracks topology and opens pools per config/policy. |
| "Do remote DCs need pools like the local DC?" | **Not by default.** Routing and connections to remote DCs must account for latency/cost, local DC, and failover policy. |
| "Can a pool fix a hot partition?" | **No.** A partition key still routes to the replica set for that token. |

### 4.1. What Must Be Measured Before Increasing the Pool

- Number of `CqlSession` instances in the process, **open connections per node**, in-flight requests per connection/session.
- Request queue/throttler backlog, request acquire/wait time, and timeouts.
- **Client-side** p50/p95/p99, throughput, retry attempts, and coordinator distribution.
- Application CPU/GC, direct memory/heap, file descriptors, and network.
- CPU/GC, `nodetool tpstats`, SSTable/disk latency, and dropped messages on **replicas**.

Genuine pool starvation alongside spare node capacity can justify tuning. However, if `tpstats` or disk is saturated, enlarging the pool usually just **pushes more traffic into the bottleneck**.

## 5. In-Flight, Queue, and Deadline: Three Distinct Quantities

A request can pass through these states:

~~~mermaid
flowchart LR
    A["API request arrived"] --> B{"Admission has room?"}
    B -->|No| X["Reject/429/503 per API contract"]
    B -->|Yes| C["Wait for permit/concurrency budget"]
    C --> D["Driver dispatch / in-flight"]
    D --> E["Coordinator + replicas"]
    E --> F["Response or timeout"]
    F --> G["Release permit + metrics"]
~~~

| Term | Meaning |
| --- | --- |
| **In-flight** | Number of requests already accepted/in progress but not yet completed within the measurement boundary. |
| **Queue** | Requests still waiting to be dispatched or waiting for a permit; queues also consume RAM and time. |
| **Concurrency limit** | Ceiling on requests processed concurrently within a scope; can be per process, query class, or tenant. |
| **Request timeout** | Duration the driver allows an applicable request/attempt to complete according to version semantics. |
| **API deadline** | The point by which **all work** for a business request must finish, including queue wait, multiple CQL statements/pages, and application processing. |
| **Retry budget** | Number of attempts, time, or percentage of traffic allocated to retries; not synonymous with timeout. |

**A common mistake:** capping driver in-flight at 100 while leaving an **unbounded queue** in front of HTTP or a message consumer. When Cassandra slows down, application memory can still grow because **tens of thousands of requests are waiting for a permit**. You must bound **both in-flight and queue depth**, and enforce an overload rejection policy at ingress.

### 5.1. Estimating Concurrency with Little's Law

In steady state:

~~~text
L ≈ λ × W

L = average requests present in the system
λ = completion throughput per second
W = average time from entering to leaving the system, in seconds

Example λ = 600 requests/s:
  W = 0.05 s => L ≈ 30 requests
  W = 0.50 s => L ≈ 300 requests
  W = 2.00 s => L ≈ 1,200 requests
~~~

This is an illustrative calculation and **not the number of connections to open**. It shows that when latency increases 10x, the same throughput holds 10x as many unfinished requests. Under overload, completion throughput may drop while queues keep growing and the system is no longer stable; do not treat the formula as a capacity guarantee.

### 5.2. Consequences of Increasing Timeouts

Suppose the gateway has only a 1-second deadline while the driver timeout is set to 20 seconds. When queries slow down:

1. The gateway returns a timeout to the user after 1 second.
2. If the application does not manage cancellation/budget, the driver request may **still continue** per current semantics.
3. Old work continues occupying in-flight slots while new requests keep arriving.
4. If clients or the gateway retry blindly, traffic amplifies; other users' p99 can degrade.

**Increasing timeouts does not make replicas read SSTables faster, restore a down node, or resolve tombstone guardrails.** It only allows waiting longer when other layers still have remaining time and capacity.

## 6. Page Size and Byte Limits: Counting Rows Is Not Enough

In Cassandra, `LIMIT 100` caps the **logical rows returned** by the matching statement. `page size = 50` is how the driver splits the result set into **pages**. Neither means every read touches only 50 cells on disk.

| Parameter | Controls | Risk if set too large |
| --- | --- | --- |
| `LIMIT` in CQL | Number of result rows for a statement. | If selecting very large payload columns, 100 rows can still be hundreds of MB. |
| Driver page size | Target number of rows in a page under paging. | Buffers/network/decode/GC grow; each page can become slow. |
| `SELECT` column projection | Bytes/row and decode work. | `SELECT *` on tables with large payloads wastes RAM/network. |
| Clustering range | Amount of data examined within a partition. | Wide ranges may scan many SSTables/tombstones. |
| Bucket/partition count | Fan-out of an API query. | Each bucket creates requests/merges; many buckets at once easily overload nodes. |

### 6.1. Calculating a Byte Budget

~~~text
Example:
  1 returned row averages ~8 KiB
  500 rows/page
  payload per page ≈ 4,000 KiB ≈ 3.9 MiB

With 200 concurrent pages/requests:
  the volume of data in flight can be very large,
  depending on received pages, buffering, decoding, and actual memory.
~~~

Page size counts **rows**, not an exact byte ceiling. Exceptionally large rows, large collections, or UDTs can cause a page to exceed estimates. Measure **bytes/read**, row size distributions, and enforce payload limits in the data model or ingestion layer if needed.

### 6.2. `ResultSet` and Paging in Java

In driver 4.x, iterating synchronously over a `ResultSet` can **trigger fetching the next page**. If timing starts before `session.execute()` and stops right after receiving the first page, it **excludes** the time spent fetching and iterating subsequent pages. Be explicit:

- **Time to first page** differs from **time to consume all rows**.
- A single driver request timeout is not necessarily the **total deadline across all pages and statements**.
- Multi-bucket reads must bound bucket count, row count, and total duration—not just `setPageSize`.
- If an API must respond under 300 ms, a single request should not fetch hundreds of pages on the hot path.

## 7. Timeouts, Retries, and Speculative Execution Need a Shared Budget

### 7.1. Time Layers

| Layer | Example | Impact |
| --- | --- | --- |
| Gateway/API | 800 ms deadline | Users do not wait any longer. |
| Java service | 600 ms remaining budget for queries and processing | May need headroom for HTTP serialization. |
| Java Driver | `basic.request.timeout` | Driver-side request limit per version; does not alter server timeouts. |
| Cassandra coordinator | Read/write/range timeouts | Waits for replica responses by request type. |
| Replica/OS | GC, queues, compaction, disk, network | Potential causes of slow execution. |

`ReadTimeout`, `WriteTimeout`, `Unavailable`, driver request timeout, and `Unauthorized` are **different situations**. Changing one timeout setting does not fix all of them.

### 7.2. Retries Are Not Free

~~~mermaid
flowchart TD
    A["Slow request"] --> B["Timeout or retry trigger"]
    B --> C["Client sends another attempt"]
    C --> D["Coordinator/replicas do extra work"]
    D --> E["Queue + disk/CPU/GC pressure rises"]
    E --> A
~~~

**Reads** can be retried in certain cases, but every retry increases traffic; a **write timeout** can occur **after one or more replicas have already written**. If the application retries an `INSERT` with a new `event_id`, it can create logical duplicates. With counters, LWT, or read-modify-write, retry semantics are more complex.

Configure **retry policies and speculative execution** according to your version's guidelines, with a **retry budget, backoff/jitter, idempotency, and metrics**. Do not enable speculative execution on all writes or every slow query; a speculative attempt may involve a **second coordinator** and amplify load. The driver needs to know which statements are **idempotent**; mislabeling them is dangerous.

### 7.3. Backpressure Beats Unbounded Queues

A resilient processing pipeline needs:

1. **Admission control** at HTTP/message consumers with a pending request cap and controlled `429/503` or deferral policies.
2. **Bounded in-flight** per process, and optionally per tenant/query type to keep one workload from starving all slots.
3. **Request timeouts smaller than the business deadline** where appropriate, accounting for queue wait time.
4. **A finite retry budget** applied only to safely retryable errors.
5. **Metrics** covering permit wait time, in-flight, queue depth, rejections, driver requests, and server latency.

Do not spawn unlimited threads to "solve" blocked requests. If the bottleneck is disk I/O or a hot partition, higher concurrency only worsens contention.

## 8. Distinguishing Driver Limits from Cassandra Guardrails

| Symptom | Primary responsible layer | Do not solve by |
| --- | --- | --- |
| App holds 100,000 `CompletableFuture`s waiting on Cassandra | App-side admission/bounded queue/concurrency | Only increasing pool size. |
| Driver request throttler is queuing/rejecting | Driver/app budget | Making queues unbounded. |
| Replicas scan too many tombstones | CQL data model, TTL/deletes, SSTables/compaction, and server guardrails | Only increasing timeout or page size. |
| `Unavailable` on `LOCAL_QUORUM` | RF, node/DC availability, topology | Only increasing request timeout. |
| Reads on a hot partition key | Partition/token distribution, workload/rate | Adding Java Driver connections. |
| Node disk full from SSTables/compaction | Storage capacity and maintenance | Increasing driver concurrency. |
| Driver fails to authenticate | Auth/TLS/credentials and roles | Retrying every error indefinitely. |

For example, `SELECT ... LIMIT 20` can still scan thousands of tombstones just to find enough live rows. If the server logs warnings or aborts due to tombstone thresholds, **no driver page-size setting makes tombstones disappear**. You must fix the partition/range/TTL design and data maintenance.

## 9. Separating Config Across Dev, Staging, and Production

Split configuration into two categories:

1. **Shared versioned policy:** query/profile names, serialization, timeout classes, logging/metrics contracts, TLS and retry principles. Store in source control when free of secrets.
2. **Environment-specific values:** contact points/DNS, local datacenter, RF/CL per topology, connection/throttling budgets, credentials/certificates, feature flags, and limits. Supply via deployment/secret store with auditing.

### 9.1. Environment Matrix

| Attribute | Dev/laptop | Staging | Production |
| --- | --- | --- | --- |
| **Topology** | May be a single lab node or container; synthetic data. | Close to production in DC/RF/CL count, hardware, and workload shape for capacity tests. | Real topology, approved DCs/racks, RF per SLA. |
| **Contact points** | Lab DNS/loopback. | Staging-specific DNS. | Internal production DNS, never inherited from dev defaults. |
| **Local DC** | Exact name reported by lab snitch. | Staging DC name. | Exact DC where the app runs; avoid DC mismatch during failover. |
| **Role/secret** | Low-privilege lab account, non-sensitive data. | Independent staging identity. | Per-service least-privilege identity; rotated via secret manager. |
| **TLS** | Should test intended policy; lab CA. | Full testing of trust/hostname/cert rotation. | TLS/peer validation, network policy, and standard auditing. |
| **Timeout** | Supports debugging/testing without masking errors. | Matches production or uses test profiles. | SLO-driven, separated for interactive vs. batch. |
| **Page/concurrency** | Small so lab is not overloaded. | Controlled load tests with production-like config. | Based on per-DC benchmarks/capacity and tail latency. |
| **Retry/logging** | Verbose logging acceptable on synthetic data. | Test failure injection and retry budgets. | Redacted logging, sampling, alerting, controlled overhead. |

**Do not treat staging as production just because they share the same Docker image.** Environments must differ in **identity, addresses/clusters, secrets, data, permissions, networking, and telemetry labels**. A pipeline that accidentally deploys production endpoints from dev can mutate live data.

### 9.2. Splitting Files per Environment and Controlling the "Source of Truth"

**Conceptual** application layout example:

~~~text
src/main/resources/
  cassandra-dev.conf
  cassandra-staging.conf
  cassandra-prod.conf

Deployment:
  APP_ENV=dev|staging|prod
  CASSANDRA_CONTACT_POINT=...
  CASSANDRA_LOCAL_DC=...
  secret reference: Cassandra service credential / TLS trust
~~~

On larger systems, environment files may be **rendered at deploy time** from ConfigMaps/IaC/secret management rather than bundled inside the JAR. Key principles:

- Files tracked in Git **must not contain passwords, access tokens, private keys, or user data**.
- Enforce **schema validation/allowlist** for `APP_ENV`; never silently fall back from `prod` to `dev` or vice versa.
- Each critical setting has one clear authoritative source: avoid undocumented multi-layer overrides.
- When rotating secrets/certs, avoid requiring a new application code release if your secret manager supports proper dynamic delivery.
- Startup logs should print only **environment, config version/hash, cluster identity/local DC, profiles, and non-sensitive limits**; never echo the full config.

## 10. Java Driver 4.x HOCON: Shared Configuration Foundation

Java Driver 4.x uses a configuration model typically under the `datastax-java-driver` namespace. Below is **a reference set of values for staging/lab**, not a prescription for production thresholds:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }

  advanced.connection.pool {
    local.size = 1
  }

  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Key explanations:**

- `basic.request.timeout` is the **client** wait time; it does not modify `read_request_timeout_in_ms` on Cassandra servers.
- `page-size` sets the default page size; it does not replace `LIMIT` in CQL.
- `advanced.connection.pool.local.size` controls the number of connections per **local** node within version/driver rules; it is not the service's total request cap.
- `advanced.request-throttler` uses the driver's throttling mechanism where supported by the version. `max-concurrent-requests` and `max-queue-size` are **client budgets**, not extra replica capacity.
- The throttler class name, keys, defaults, and enforcement point must be **verified against your driver version**. If a driver/distribution ignores an option, do not silently ignore that and claim the system is rate-limited.
- The numbers `200/400` are illustrative only. If the service runs 20 pods, total concurrency **can be 20 times the per-pod budget**; calculate fleet-wide limits.

### 10.1. Execution Profiles by Query Class

An application handling both interactive APIs and backfills should not share the same timeouts and page sizes across both. You can define workload-based **execution profiles** inside the driver namespace, for example:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }

  profiles {
    interactive {
      basic.request {
        timeout = 500 milliseconds
        page-size = 50
      }
    }
    batch-read {
      basic.request {
        timeout = 5 seconds
        page-size = 200
      }
    }
  }
}
~~~

This is a **structural example** of profiles in 4.x HOCON; verify against your exact version. Profiles select timeout/CL/page size **per statement**, but they **do not isolate replica resources**. A batch read with a 5-second timeout still needs rate/concurrency limits at the application/driver layer or a dedicated batch cluster.

### 10.2. Avoid Mixing Profiles with Environments

**Environment** answers: "Which cluster, DC, IAM, and capacity is the app running against?"; **execution profile** answers: "Which workload class does this statement belong to?". Production may use `interactive` and `batch-read`, and staging uses those same two profiles with **suitably benchmarked values**. Never create a profile named `prod` just to avoid distinguishing query classes.

## 11. Preparing Lab CQL: Partition Key for Predictable Request Cost

Assume a lab cluster with DC `dc1`, three full replicas, and permission to create schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_driver
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_driver.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Here, `(device_id, event_day)` is a **composite partition key** to bound the number of events accumulated in a partition. `event_time` and `event_id` are **clustering columns**; events sharing the same timestamp remain distinguishable by a stable ID.

### 11.1. Writing Sample Data

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_driver.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'temperature:21.5');

INSERT INTO telemetry_driver.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature:21.6');
~~~

### 11.2. Valid Query Without `ALLOW FILTERING`

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

Do not query this table with only `WHERE event_time >= ... ALLOW FILTERING`: omitting the partition key can scan massive amounts of data. **Tuning pools/timeouts/page size cannot fix a bad query shape.** For queries spanning multiple days, the application must read the relevant buckets and merge/sort while bounding the bucket count.

## 12. Java: Selecting the Right Environment Config File and Failing Closed

The Java Driver 4.x example below selects the **config file via an allowlist**. Contact point, local DC, and credentials come from deployment environment variables so production addresses are never hardcoded in source.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import java.net.InetSocketAddress;
import java.util.Map;
import java.util.Objects;

public final class EnvironmentAwareCassandraSession {
    public static CqlSession open() {
        String environment = Objects.requireNonNull(
            System.getenv("APP_ENV"), "APP_ENV is required");

        Map<String, String> configFiles = Map.of(
            "dev", "cassandra-dev.conf",
            "staging", "cassandra-staging.conf",
            "prod", "cassandra-prod.conf");

        String config = configFiles.get(environment);
        if (config == null) {
            throw new IllegalArgumentException(
                "Unsupported APP_ENV: " + environment);
        }

        String host = Objects.requireNonNull(
            System.getenv("CASSANDRA_CONTACT_POINT"),
            "contact point is required");
        String dc = Objects.requireNonNull(
            System.getenv("CASSANDRA_LOCAL_DC"),
            "local DC is required");
        String username = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_USER"),
            "CQL user is required");
        String password = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_PASSWORD"),
            "CQL password is required");

        DriverConfigLoader loader = DriverConfigLoader.fromClasspath(config);
        return CqlSession.builder()
            .withConfigLoader(loader)
            .addContactPoint(new InetSocketAddress(host, 9042))
            .withLocalDatacenter(dc)
            .withAuthCredentials(username, password)
            .build();
    }
}
~~~

**Code notes:**

1. `Map.of` requires Java 9+. If targeting an older JDK, switch to a compatible structure.
2. This is a **bootstrap skeleton** without full TLS configuration. Production must enable **TLS with appropriate truststore/CA/hostname validation**, via driver SSL settings or a verified `withSslContext(...)`, before sending credentials.
3. Passwords in environment variables only demonstrate avoiding hardcoding; env vars can still be inspected by privileged runtime/admins. Production should prefer a **secret manager**, workload identity, or an appropriate deployment mechanism.
4. Never silently fall back `APP_ENV` or contact points to production; missing variables must **fail-fast**.
5. `CqlSession` is created **once at service startup**, then shared; close it on shutdown.
6. `host` represents a discovery endpoint: real systems may use multiple contact points, custom DNS/ports, proxies/tunnels, or policy-driven service discovery.
7. Validate effective role/cluster name/DC after connecting rather than trusting `APP_ENV=staging` alone. Avoid printing usernames/passwords or entire configs in logs.

### 12.1. Avoiding Duplicate Config Sources

If both HOCON and the builder specify `local-datacenter`, contact points, or credentials with differing values, operators can easily misread which setting took effect. Establish **one single owner per setting**, run startup assertions, and log a **non-sensitive fingerprint**.

Example:

~~~text
APP_ENV                = staging
CONFIG_ID              = cassandra-staging-v17
CONTACT_POINT_SET_ID   = staging-dc1-cql
LOCAL_DC               = dc1
REQUEST_PROFILE        = interactive
DRIVER_MAJOR           = 4.x
TLS_EXPECTED           = true
SECRET_REFERENCE       = vault/path/version-only

Do not log: passwords, private keys, access tokens, sensitive full CQL literals.
~~~

## 13. Java: Bounded Reads Measuring Full Result Consumption Time

Using the same lab table, build a read query with a **full partition key, clustering range, and `LIMIT`**. Use `System.nanoTime()` to measure elapsed duration (not wall-clock UTC timestamps).

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class BoundedReadExample {
    public static void read(CqlSession session) {
        PreparedStatement select = session.prepare(
            "SELECT event_time, event_id, payload " +
            "FROM telemetry_driver.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");

        BoundStatement statement = select.bind(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"))
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        long started = System.nanoTime();
        int rowCount = 0;
        try {
            ResultSet result = session.execute(statement);
            for (Row row : result) {
                rowCount++;
                // Process only needed columns; do not accumulate payloads into a large list.
                row.getInstant("event_time");
                row.getString("payload");
            }
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
            System.out.println("query=read_recent_events"
                + " rows=" + rowCount
                + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

`rowCount` is only the number of rows **iterated by the application**, not the number of tombstones scanned on the server. In production, emit latency into metrics with `query_name`, `status`, `dc`, and `profile`, avoiding `device_id` labels (high cardinality and sensitive data).

**Further reading:** if an API invokes multiple CQL statements or uses paging, total API duration must be measured separately with an overall deadline; `LIMIT 100` does not guarantee replicas read only 100 physical cells.

## 14. Java: Asynchronous Writes with Bounded In-Flight Concurrency

`executeAsync()` lets the application avoid blocking a thread just to wait for each Cassandra response. However, **async does not mean infinite resources**. Firing 100,000 `CompletableFuture` instances at once can exhaust memory and queues in both the app and coordinators.

The example below issues **50 sample mutations** with deterministic event IDs per run while permitting **at most 8 pending requests** at any instant. This code is for a **lab**, running on a regular producer thread; never run blocking `Semaphore.acquire()` inside an event-loop or driver I/O callback.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedAsyncWrites {
    private static final int MAX_IN_FLIGHT = 8;
    private static final int LAB_EVENTS = 50;

    public static void run(CqlSession session)
            throws InterruptedException {

        PreparedStatement insert = session.prepare(
            "INSERT INTO telemetry_driver.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?)");

        Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
        List<CompletableFuture<Void>> futures = new ArrayList<>();
        AtomicInteger acknowledged = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        for (int i = 0; i < LAB_EVENTS; i++) {
            // Only blocks the dedicated producer, NEVER block driver I/O threads.
            permits.acquire();

            Instant when = Instant.parse("2026-11-21T09:00:00Z")
                                  .plusSeconds(i);
            UUID eventId = UUID.nameUUIDFromBytes(
                ("device-7-lab-" + i).getBytes(StandardCharsets.UTF_8));

            BoundStatement write = insert.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    when,
                    eventId,
                    "temperature:" + i)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            CompletableFuture<Void> done = new CompletableFuture<>();
            futures.add(done);

            try {
                session.executeAsync(write).whenComplete((result, error) -> {
                    try {
                        if (error == null) {
                            acknowledged.incrementAndGet();
                            done.complete(null);
                        } else {
                            failures.incrementAndGet();
                            done.completeExceptionally(error);
                        }
                    } finally {
                        // Callback only updates state; does not block I/O.
                        permits.release();
                    }
                });
            } catch (RuntimeException dispatchFailure) {
                failures.incrementAndGet();
                permits.release();
                done.completeExceptionally(dispatchFailure);
            }
        }

        try {
            CompletableFuture.allOf(
                futures.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException ex) {
            // Production: record error_type and route to DLQ/reconciliation,
            // do not blindly retry every WriteTimeout with a new event ID.
            System.err.println("Some lab writes did not ACK: "
                + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("writes_acknowledged=" + acknowledged.get()
            + " writes_failed_or_unknown=" + failures.get());
    }
}
~~~

### 14.1. Why This Bounds Requests Without Being a Full Ingestion Pipeline

- `Semaphore` caps concurrency at **8 async writes** only **within this invocation/process**. With 20 pods running, the fleet could issue up to 160 similar writes simultaneously, excluding other threads.
- `permits.acquire()` **blocks the producer** when slots are full. That is intentional lab backpressure; production needs **bounded input queues, cancellation/deadlines**, and an overload rejection policy toward upstream callers.
- The callback calls `complete(...)` and `release()` quickly; never perform file I/O, blocking API calls, or `join()` inside a driver callback.
- IDs are generated deterministically for the lab run; reusing the same `event_id` prevents **row duplication** when replaying the exact key. However, if TTL, timestamp, or payload changes, retries are **not automatically idempotent in all respects**.
- `acknowledged` counts writes acknowledged at `LOCAL_QUORUM`; it does not prove every replica holds the data yet. `failures` includes failed/unconfirmed requests, which **does not mean the mutation was never written**.
- `executeAsync` returns a `CompletionStage`; for multi-page `SELECT` queries, you must fetch/consume pages via the `AsyncResultSet` API rather than treating the first page as the entire result.
- The example lacks a durable retry log/DLQ, service-level deadlines, tracing, or standard metrics. **Do not use as-is for non-lossy business data.**

### 14.2. If a Driver Request Throttler Exists, Do You Still Need a Semaphore?

**Possibly yes.** They guard different boundaries:

| Mechanism | Scope | Effect |
| --- | --- | --- |
| **API admission** | User/tenant/entire service | Rejects traffic that should not be accepted before creating work. |
| **Semaphore/concurrency gate** | A query class/producer/process | Bounds how many requests a producer allows concurrently. |
| **Driver request throttler** | Requests passing through a session/driver per configured semantics | Bounds request dispatch and queuing at the driver layer. |
| **Server guardrail** | CQL/schema/processing inside Cassandra | Blocks queries or data patterns deemed dangerous. |
| **Cassandra queue/OS capacity** | Node/replica, disk/CPU/network | Physical limit where data is actually processed. |

Configuring only a driver throttler does not stop an application from accepting unlimited HTTP requests and buffering them in RAM before reaching the driver. Conversely, a per-handler semaphore **has no visibility** into request counts on other pods or other workloads.

## 15. Execution Profiles in Java and Separating Read/Write Paths

The snippet below assumes HOCON defines `interactive` and `batch-read` profiles as in section 10.1:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;

// "session" is a long-lived CqlSession managed by DI.
PreparedStatement query = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM telemetry_driver.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT 100");

BoundStatement interactive = query.bind(
        "device-7",
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T09:00:00Z"),
        Instant.parse("2026-11-21T10:00:00Z"))
    .setExecutionProfileName("interactive")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

// Run session.execute(interactive) in the appropriate service layer.
// For batch jobs, select the "batch-read" profile
// while still enforcing bounded concurrency/rate and an overall deadline.
~~~

This is an **in-method excerpt** illustrating a call site, not a full `class`. You do not need another session just to select a different timeout or page size. However, if batch jobs risk impacting primary APIs, profiles **do not provide physical isolation**: you still need rate limits, admission control, scheduling, or appropriate cluster/tenant resource policies.

**Do not create profiles per `device_id` or `request_uuid`**. Profiles should represent a **small set of stable workload classes** that are easy to measure and govern, avoiding unbounded configuration cardinality.

## 16. Budgeting When Scaling Across Multiple Java Instances

A `MAX_IN_FLIGHT=50` limit inside **one** instance is not a cap of 50 for the **entire service**:

~~~text
Example:
  30 Java service instances
  each instance allows up to 50 concurrent Cassandra requests
  => theoretical ceiling: 30 × 50 = 1,500 concurrent requests

If each logical API request reads 3 buckets in parallel:
  account for fan-out and the chance of hitting the same replicas/nodes.
~~~

**Do not treat that product as the TCP connection count**: requests multiplex over connections. And 1,500 is the **cap on granted concurrent slots**, not a throughput of 1,500 requests/s.

### 16.1. Capacity Sizing Formula

~~~text
Assume:
  20 pods
  target throughput per pod = 150 logical API requests/s
  each API call typically sends 2 CQL statements

Estimated total CQL request rate:
  20 × 150 × 2 = 6,000 statements/s

If statement p99 = 0.25 s:
  DO NOT compute normal in-flight directly as 6000 × p99.
  Little's Law uses mean W, not p99.

If estimated mean W = 0.06 s under steady load:
  L ≈ 6,000 × 0.06 = 360 average fleet-wide in-flight requests.

Peak in-flight budgets must account for bursts, tail latency, retries,
partition/DC fan-out, and coordinator/replica capacity.
~~~

**This is a preliminary sizing exercise.** Real thresholds must be measured via load tests matching production data shapes. If the retry rate is 10% and each retry adds a request, total traffic to Cassandra exceeds 6,000 statements/s; if shadow/canary reads, backfills, or speculative executions run concurrently, add those load sources too.

### 16.2. Avoiding Hotspots and DC Misrouting

Setting `localDatacenter` properly routes traffic according to the intended topology, especially with `LOCAL_QUORUM`. Still, **the driver cannot fix data modeling**. If 90% of requests target the same `device_id` on the same day, that single partition token can overheat one replica set even in a cluster with hundreds of nodes.

| Change | What it can improve | What it does not automatically fix |
| --- | --- | --- |
| Add Java instances | Application capacity, if the backend has headroom. | Hot partitions and Cassandra IOPS. |
| Increase connections/local pool | Can relieve genuine client-side bottlenecks. | Disk-saturated replicas. |
| Use `LOCAL_QUORUM` in the right DC | Reduces cross-DC dependency for local reads/writes. | A local replica suffering heavy GC/compaction. |
| Time-bucketed partitions | Bounds history and spreads partitions across days. | Historical reads may need multi-bucket fan-out. |
| Shard hot buckets | Spreads write hotspots across multiple tokens. | Reads requiring merge increase with shard count. |
| Trim payload/page size | Reduces network/memory/decode per request. | Unfixed `ALLOW FILTERING` or tombstone scans. |

## 17. Security Config Must Separate Environments, Not Just Hostnames

A `cassandra-prod.conf` with tuned timeouts and pools is still non-compliant if the application sends credentials over unencrypted connections or connects with a superuser account.

### 17.1. What Must Differ Across Environments

- **Auth identity:** `telemetry_api_dev`, `telemetry_api_staging`, `telemetry_api_prod`, or an equivalent naming convention; never share secrets.
- **CQL privileges:** grant only `SELECT`/`MODIFY` on required tables. Application roles do not need `CREATE ROLE`, `ALTER KEYSPACE`, or JMX privileges.
- **TLS trust anchors:** cluster-specific CA/certificates and hostname/SAN validation; never enable `trust-all` to bypass staging errors.
- **Network:** production clusters must block unapproved direct access from developer laptops; staging must not share seeds or gossip identity with production.
- **Backup/logging:** never log passwords, access tokens, or sensitive payloads/partition keys; restrict access to telemetry.
- **Data lifecycle:** staging uses synthetic or properly masked data; never copy production SSTables containing PII into environments with weaker controls.

### 17.2. Fail-Closed Startup Practices

Verify **before the service accepts traffic**:

~~~text
[ ] APP_ENV belongs to the dev/staging/prod allowlist, with no ambiguous default.
[ ] Contact points and local DC match the expected cluster.
[ ] Driver major/minor version and config ID are logged clearly.
[ ] TLS and peer certificate validation are genuinely enabled per policy.
[ ] Secrets come from an approved source, with no hardcoded fallback passwords.
[ ] App role can access required tables without schema/admin privileges.
[ ] Prepared statements prepare successfully; keyspace/schema match expectations.
[ ] Driver timeout and throttling configs are loaded, not silently ignored.
[ ] Metrics/health endpoints reflect connection state and in-flight counts.
[ ] Shutdown closes the session and stops accepting new requests cleanly.
~~~

A startup heartbeat `SELECT` catches obvious issues but **does not prove every partition or replica is healthy**. Health checks need appropriate deadlines and frequency; do not hammer a hot query multiple times per second solely as a connectivity probe.

## 18. Monitoring: Measure End-to-End from Application to Replica

Looking solely at HTTP `p99` cannot tell whether a slow request comes from Java, the driver queue, coordinator, tombstones, disk, or network.

### 18.1. Minimum Dashboard

| Layer | Useful metrics | Question answered |
| --- | --- | --- |
| **API/gateway** | Request rate, p50/p95/p99, errors/timeouts, queue and rejections. | How severely are users affected? |
| **Java application** | In-flight by query class, pending queue, permit wait, heap/RSS, GC pause, thread usage. | Is the app bottlenecked before calling Cassandra? |
| **Driver** | Request latency/errors/timeouts, per-node in-flight, open connections, throttler delays/queue/rejections, retry attempts (where metrics support it). | Is there a client bottleneck or wrong-node routing? |
| **Coordinator** | Read/write latency, timeouts/unavailable, dropped messages, `tpstats`. | Is the cluster receiving too many requests? |
| **Replica/SSTable** | Read latency, tombstones scanned, SSTable count, compaction backlog, disk await/IOPS. | Is server-side query cost too high? |
| **Network/DC** | Connection failures, retransmits, cross-DC traffic, node membership. | Is the driver picking the wrong DC or is the network degraded? |
| **Security/config** | TLS/auth failures, credential rotation, config versions, drift. | Did a rollout accidentally change cluster or permissions? |

### 18.2. Reference `nodetool` Commands

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool netstats
nodetool proxyhistograms
nodetool tablestats telemetry_driver.events_by_device_day
nodetool tablehistograms telemetry_driver events_by_device_day
~~~

Exact subcommands, arguments, and metrics depend on the Cassandra version; check `nodetool help`. Some counters accumulate since node startup, while histograms cover specific scopes. Never average per-node p99s to compute a cluster-wide p99. Plot client metrics and server metrics on the **same UTC timeline** alongside request rate and deploys to correlate root causes accurately.

### 18.3. Selective Tracing

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, payload
FROM telemetry_driver.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

`TRACING` and `CONSISTENCY` are **cqlsh** commands, not sent verbatim via the Java Driver. Tracing an individual query helps identify the coordinator/replicas and expensive steps; **never enable tracing on 100% of production traffic**, as tracing itself adds load and metadata writes.

### 18.4. Metrics Cardinality and Log Redaction

Stable metric labels should be `query_name`, `environment`, `local_dc`, `status`, `profile`, and node identity where permitted. Never attach `event_id`, `device_id`, `request_uuid`, or full CQL literals to high-volume metrics: that causes cardinality explosions and PII exposure. In error logs, record **exception class, timestamp, request correlation ID, redacted query template**, and retry attempt count—never credentials or payloads.

## 19. Case Study: Raising Timeouts Made Errors Drop While p99 Worsened

Consider a service with 24 Java pods; each opens one session against the same event table. Each pod receives an average of 200 API requests/s, each issuing one SELECT. During disk/compaction contention, mean latency rises from 40 ms to 300 ms.

| Metric | Baseline | During incident | Consequence |
| --- | ---: | ---: | --- |
| Total request rate | 4,800/s | 4,800/s | Ingress load has not dropped. |
| Mean DB latency | 40 ms | 300 ms | Requests hold resources much longer. |
| Theoretical mean in-flight (Little's Law) | ~192 | ~1,440 | ~7.5x increase despite flat throughput. |
| Driver request timeout | 2 s | If raised to 20 s | Does not reduce mean DB latency by itself. |
| JVM heap/GC | Stable | Heap and pauses rise | Likely caused by queued work and buffered responses. |
| Server compaction/disk | Normal | Disk await and pending compaction rise | Capacity and maintenance must be investigated. |

**Wrong response:** increase pool size 10x, raise timeout to 20 seconds, increase page size 10x, and enable unbounded retries. This may make client error rates look lower for a few minutes, but it swells queues and piles more work onto saturated disks.

**Evidence-based response:**

1. Measure client p99, driver queue/in-flight, and retries; align timestamps with replica disk await, `compactionstats`, and `tpstats`.
2. Keep admission/queues bounded; if the backend is overloaded, shed batch/backfill traffic or return controlled overload errors.
3. Verify queries include full partition keys, clustering ranges, `LIMIT`, suitable page sizes, and no abnormal tombstone scans.
4. Adjust timeouts/profiles **only for workloads with longer SLAs** when benchmarks confirm benefit without hurting interactive APIs.
5. Canary on a subset of pods, watching throughput, p99, GC, queues, and disk; roll back immediately if regressions appear.

**Note:** 1,440 is an **estimated average in-flight count**, not a direct measurement or driver connection count. Once a system enters overload, steady-state formulas no longer capture runaway queue growth.

## 20. Environment Config Drift Leading to Hard-to-Diagnose Failures

### 20.1. Staging Uses RF = 1 While Java Uses `LOCAL_QUORUM`

With RF = 1 in a single DC, `LOCAL_QUORUM` requires **one** replica; queries succeed, yet **production RF = 3 quorum behavior goes untested**. Do not assume from single-node staging that the service tolerates a slow replica or down node in a multi-replica cluster.

If staging has **one node** while the keyspace declares RF = 3 and the client uses `LOCAL_QUORUM`, replica availability cannot be met; failures surface as `Unavailable` rather than driver timeouts. Test topology intentionally instead of arbitrarily lowering consistency levels "just to make it pass".

### 20.2. Wrong Local DC Configured

A Java service running in `dc1` configured with `localDatacenter("dc2")` may cause the driver to misroute relative to intended placement or fail to establish valid connections depending on topology/contact points/config. WAN latency and auth/network policies can masquerade as timeouts. Check the **DC name reported by the snitch**, driver metadata, and pod placement—do not inspect contact-point IPs alone.

### 20.3. Staging Credentials Used in Production

A misconfiguration can cause:

- Connections failing with `AuthenticationException` or `Unauthorized` due to differing roles.
- Worse, if credentials are shared, an application accidentally reads or modifies production data with overly broad privileges.
- Monitoring loses actor/environment attribution, and incident response must rotate secrets across multiple services at once.

**Enforce separate identities, separate secret references, endpoint/network controls, and fail-fast checks on environment mismatch.** Never fix auth errors by switching to a superuser or disabling TLS.

## 21. Controlled Driver Config Change Process

~~~mermaid
flowchart TD
    A["Need to change driver limits / environment config"] --> B["Confirm SLO, RF/CL, workload, version, and topology"]
    B --> C["Capture baseline client/driver/server metrics"]
    C --> D["Pick minimal change, write hypothesis"]
    D --> E["Test in staging with realistic traffic, data shape, and TLS/RBAC"]
    E --> F{"Meet p99, errors, throughput, resource budgets?"}
    F -->|No| G["Keep old config, fix root cause/re-evaluate"]
    F -->|Yes| H["Canary a small pod group, never full fleet at once"]
    H --> I["Measure in-flight, queue, GC, disk, coordinator, retries"]
    I --> J{"All workloads healthy?"}
    J -->|No| K["Rollback config / throttle rate in a controlled way"]
    J -->|Yes| L["Expand rollout, record change ID, and review"]
~~~

### 21.1. Experiment Log Template

~~~text
Experiment ID:
Driver exact version:
Cassandra version, JDK:
Environment / cluster / DC / RF / CL:
Config before/after (redacted):
Query types, data shape, request rate, burst:
Load test duration, sample count:
Client p50/p95/p99, timeouts, retries:
Driver connections, in-flight, throttler queue/rejects:
Server tpstats, GC, disk latency, compaction:
Application JVM heap/RSS, threads/CPU:
Decision GO/NO-GO:
Rollback trigger:
Owner and UTC change time:
~~~

**A 100-request test** cannot measure p99 meaningfully; gather sufficient samples under representative load, including peaks/bursts, TTL/tombstone data, and compaction/repair activity coinciding with peak hours.

### 21.2. What to Track When Scaling Out Instances

- Track the **total fleet-wide request budget**, not only per-pod limits.
- Check keyspace/tenant quotas, connections per node, and coordinator distribution.
- Scaling from 10 to 50 pods while keeping 100 in-flight per pod expands the theoretical budget from 1,000 to 5,000. Backend capacity does not scale automatically to match.
- Consider **global rate limiting** or telemetry-driven controllers to pace ingress.
- Ensure shutdown/draining does not drop queued writes; write timeout outcomes still need idempotency/reconciliation handling.

## 22. Common Misconceptions

| Statement | Verdict | Reason |
| --- | --- | --- |
| "Creating a new `CqlSession` per request is safer." | **False** | Sessions hold connections/metadata/resources and should be reused. |
| "A Cassandra connection pool gives one exclusive connection per request like JDBC." | **False** | The native protocol supports multiplexing. |
| "Enlarging the pool or adding pods fixes a hot partition." | **False** | Partition token/replica placement does not change. |
| "`executeAsync` consumes no memory or threads." | **False** | Futures, queues, buffers, callbacks, and server work still consume resources. |
| "A semaphore of 100 in one pod means the whole service sends at most 100 requests." | **False** | Multiple pods and query classes add up. |
| "Page size 10,000 is always faster than page size 100." | **False** | Bytes/page, GC/network, and timeouts can degrade. |
| "`LIMIT 20` means Cassandra reads at most 20 physical cells." | **False** | Tombstones and SSTable versions can force much larger scans. |
| "A 20-second driver timeout fixes `Unavailable`." | **False** | It does not add replicas to satisfy quorum. |
| "`LOCAL_QUORUM` with RF = 3 requires all three replicas." | **False** | Two responses within the DC are required. |
| "A `batch-read` profile isolates batch resources from the main API." | **False** | Profiles only choose statement parameters; backend resources may still be shared. |
| "Splitting dev/prod files while sharing passwords is good environment separation." | **False** | Identities and secrets must be distinct to limit blast radius. |
| "CQL RBAC and TLS automatically replace bounded concurrency." | **False** | Security controls do not prevent overload. |
| "Averaging each node's p99 gives the cluster p99." | **False** | Percentiles cannot be aggregated by averaging. |
| "Tracing every request improves throughput during errors." | **False** | Tracing introduces overhead. |
| "Config changes should be benchmarked and canaried per workload and version." | **True** | Prevents local optimizations from causing system-wide regressions. |

## 23. Self-Check Exercises with Answers

**Exercise 1.** A Java service currently creates a `CqlSession` inside every HTTP handler at 3,000 requests/s. What are the risks and the single most important fix?

**Answer:** Session churn, TCP/TLS/auth handshakes, heavy metadata load, and spiking JVM resources. Create a **shared long-lived session** (for example, a DI-managed singleton) and close it on service shutdown.

**Exercise 2.** A Cassandra connection serves only one request at a time, just like a JDBC connection inside a transaction. Is this statement true?

**Answer:** **False.** The Cassandra native protocol and Java Driver multiplex multiple requests over a single connection; measure in-flight concurrency and throughput before raising connection counts.

**Exercise 3.** A service runs 12 pods, each capped at 80 in-flight Cassandra statements. What is the fleet-wide theoretical ceiling if all pods hit their limit?

**Answer:** `12 × 80 = 960` concurrent statements. This is neither the TCP connection count nor throughput/s, and it excludes other code paths.

**Exercise 4.** An app has a steady request rate of 400/s and mean DB latency of 50 ms. What is the estimated average in-flight count? What if the mean rises to 500 ms?

**Answer:** `400 × 0.05 = 20` and `400 × 0.5 = 200` average in-flight requests. Do not substitute p99 for the mean in Little's Law.

**Exercise 5.** A query has `LIMIT 100` and driver page size 20. Logically, how many pages might occur if all 100 rows are returned?

**Answer:** Roughly **5 pages** by target row count; actual page requests can depend on paging behavior, row sizes, server limits, and results. `LIMIT` does not cap tombstone scans at 100.

**Exercise 6.** Driver timeout is 30 seconds while the API gateway deadline is 800 ms. Will raising only the driver timeout let the API return a read that takes 4 seconds?

**Answer:** **No.** The gateway hits its deadline first. Reduce query/queue cost or revise the API contract and overall time budget.

**Exercise 7.** Single-node staging with RF = 1 runs `LOCAL_QUORUM` cleanly. Does that prove the service handles one down replica in RF = 3 production?

**Answer:** **No.** A single-node setup does not exercise RF = 3 routing/quorum, speculative execution, or replica failure handling. Use realistic staging topology and load when testing resilience.

**Exercise 8.** All 20 pods use `MAX_IN_FLIGHT=100`; rising traffic drives up Cassandra `tpstats` pending tasks and disk latency. Should you double the pool/limit?

**Answer:** **Do not increase automatically.** The backend shows signs of saturation; raising limits can push even more load. Investigate query shapes, compaction/disk, hot partitions, retry rates, and ingress throttling.

**Exercise 9.** Why is splitting `cassandra-dev.conf` and `cassandra-prod.conf` insufficient if both environments use the same superuser account?

**Answer:** Credential leaks or endpoint mix-ups create a blast radius across both environments, and complicate rotation and auditing. Every service/environment needs its own least-privilege identity and TLS.

**Exercise 10.** Given `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, an app queries last week using only `device_id` and `event_time`. Does raising page size turn it into a cheap partition lookup?

**Answer:** **No.** It is missing `event_day` from the partition key. Identify the relevant date buckets, read each partition with bounds, and merge; or build a suitable projection.

**Exercise 11.** An async write times out after one replica already applied the mutation. What is the risk of retrying with a new `event_id`?

**Answer:** Logical duplicates because the original write may have partially succeeded. Use stable IDs, a retry budget, awareness of CL/idempotency, and proper reconciliation.

**Exercise 12.** A team configures the driver request throttler while leaving the HTTP queue unbounded. When Cassandra slows down, the app still OOMs. Why?

**Answer:** Requests waiting at the **application layer** before entering the driver still consume RAM. Enforce bounded admission/queuing and backpressure right at ingress.

## 24. Production Readiness Checklist and Decision Flow

~~~text
CQL / DATA MODEL
[ ] Hot-path queries specify full partition keys and clustering ranges.
[ ] Time-series bucket sizes and read fan-out are benchmarked.
[ ] Prepared statements are reused; no sensitive values concatenated into CQL.
[ ] LIMIT, page size, bytes/row, and tombstone scans are measured.

JAVA DRIVER LIFECYCLE
[ ] One long-lived CqlSession per needed logical cluster/identity/config.
[ ] Session is managed by DI and closed cleanly on shutdown.
[ ] No session creation per request or guesswork pool sizing.
[ ] Driver version, HOCON option names, and effective config are verified.

RESOURCE BUDGET
[ ] Bounded admission/queues and concurrency per workload.
[ ] Total budget calculated across all instances/pods.
[ ] Request/page/API deadlines and retry budgets are explicit.
[ ] Async callbacks never block driver I/O threads.
[ ] Batch/backfill paths have rate limits and durable retry/reconciliation.
[ ] No speculative execution or unbounded retries everywhere.

ENVIRONMENT / SECURITY
[ ] Dev, staging, and production have distinct clusters/contact points/DCs.
[ ] APP_ENV is allowlisted with no ambiguous fallbacks.
[ ] TLS peer validation and truststore/secret manager match each environment.
[ ] Identities and CQL privileges are scoped per service, never superuser.
[ ] Config files contain no passwords/private keys; auditing/versioning is clear.
[ ] Staging validates RF/CL, node failures, and production-like data where needed.

OBSERVABILITY / ROLLOUT
[ ] p50/p95/p99, throughput, errors/retries, queue/permit waits are monitored.
[ ] Connections/in-flight/driver throttler, JVM GC, server tpstats/disk are measured.
[ ] Metric labels exclude device/event IDs and raw payloads.
[ ] Load tests use sufficient samples covering peaks, compaction, and tombstones.
[ ] Canaries limit pods/traffic with clear stop criteria and rollback.
~~~

~~~mermaid
flowchart TD
    A["Java Cassandra app needs resource tuning"] --> B["Inspect query shape, partition key, CL/RF/DC"]
    B --> C["Measure p99, retries, in-flight, queue, GC, disk, and nodetool"]
    C --> D{"Primary bottleneck at client or replica?"}
    D -->|Client/pool| E["Adjust pool/throttler/admission in a controlled way"]
    D -->|Replica/query| F["Fix CQL/data model, rate, compaction/capacity"]
    E --> G["Compute fleet-wide budget and timeouts from API SLO"]
    F --> G
    G --> H["Separate HOCON, TLS, credentials, local DC per environment"]
    H --> I["Staging load test + chaos/failure cases"]
    I --> J{"SLO, data correctness, security, and resource budgets pass?"}
    J -->|No| K["Keep previous config, investigate root cause"]
    J -->|Yes| L["Production canary + observation + rollback plan"]
~~~

**Summary:** The Java Driver lets Java applications communicate with Cassandra efficiently through **a reused `CqlSession`, topology-aware routing, prepared statements, paging, and async requests**. Yet efficiency does not come from loosening every limit: **connection pools, in-flight concurrency, queues, page size, timeouts, and retries** must be governed by resource budgets across the **application, driver, coordinator, and replicas**. At the same time, **dev/staging/production** must be strictly separated across clusters, DCs, profiles, RF/CL, TLS, credentials, and permissions without shared secrets or ambiguous fallbacks. The best approach is to **measure real workloads, cap fleet-wide concurrency, fix query shapes where needed, test in staging, and roll out canaries with rollback**, rather than masking an overloaded Cassandra cluster behind inflated timeouts or connection counts.
