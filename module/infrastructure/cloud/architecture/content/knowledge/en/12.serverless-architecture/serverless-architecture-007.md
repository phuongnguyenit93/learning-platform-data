# Managing Database Connections Under Serverless Workloads

## 1. Why Do Database Connections Become a Bottleneck in Serverless?

Serverless lets platforms automatically initialize and scale execution environments on demand instead of requiring engineering teams to maintain always-on application servers. This model works well for irregular API traffic, event-driven tasks, and spiky workloads. However, **databases generally do not scale concurrent connections as quickly or cheaply as serverless compute**.

In traditional applications, a fairly stable set of instances maintains connection pools across process lifetimes. In serverless functions, many execution environments can spin up almost simultaneously during a traffic spike. Each environment may create its own pool; scale-out events, cold starts, retries, and parallel executions cause connection counts to surge abruptly. When functions scale in or time out, returning connections to pools or closing sockets can also behave differently than expected.

Common consequences include:

- The database exhausts its connection limit even while CPU and RAM remain unsaturated.
- Connections are opened too early, held too long, or never closed properly.
- Functions stall waiting for connections, raising latency and causing cascading timeouts.
- Retries after database errors spawn additional invocations and open even more connections.
- Transactions stay open while functions call external APIs or wait on slow steps.
- Proxies/poolers become saturated, turning into a new bottleneck in place of the database.

In the **CLOUD_ARCHITECTURE** module, this is a critical design decision balancing compute, data, reliability, performance, security, cost, and operations. This lesson focuses on managing connection lifecycles as serverless concurrency fluctuates rapidly, calculating safe limits, using pools or database proxies, and validating behavior under realistic load.

After this lesson, you will be able to:

- Explain the relationship between invocation concurrency, execution environments, connection pools, and connection limits.
- Estimate connection counts during scale-out and choose safe concurrency caps.
- Distinguish in-process pools, proxies/poolers, direct connections, and database APIs.
- Design short transactions, backoff retries, idempotency, and aligned timeouts.
- Manage credentials, TLS, access permissions, and rotation for functions.
- Build load tests, observability metrics, and mitigation plans when databases or proxies saturate.

## 2. Connection Models in Serverless Applications

~~~mermaid
flowchart LR
    Client["Client / Event source"] --> GW["API Gateway / Trigger"]
    GW --> Fn["Function invocation"]
    subgraph Runtime["Execution environments can scale up/down"]
        Fn --> E1["Environment A"]
        Fn --> E2["Environment B"]
        E1 --> P1["Local connection pool"]
        E2 --> P2["Local connection pool"]
    end
    P1 --> Proxy["DB Proxy / Pooler (optional)"]
    P2 --> Proxy
    Proxy --> DB[("Database")]
~~~

Not every platform follows this exact topology. A function may handle one invocation per environment or higher concurrency depending on the runtime; environments may be reused. API-based database services may not open traditional database sockets from the function at all. Always **study the runtime's concurrency model and the chosen database service's connection semantics**.

| Concept | Meaning | Relation to connections |
| --- | --- | --- |
| **Invocation** | A single function execution handling an event/request | May require 0, 1, or multiple DB operations |
| **Execution environment** | Runtime environment provisioned and potentially reused by the platform | May retain clients/pools across invocations |
| **Concurrency** | Simultaneously executing invocations as defined by the platform | Determines environment count and DB pressure |
| **Connection** | Socket/session opened by a client to a DB or proxy | Consumes limits, memory, and DB/proxy resources |
| **Connection pool** | Managed set of reusable connections | Per-environment pools multiply on scale-out |
| **Proxy / pooler** | Layer accepting client connections and managing/multiplexing backend DB connections | Can reduce backend connections, but adds a hop and limits |
| **Transaction** | Unit of data operations with commit/rollback | Occupies a connection and can hold locks while open |

**Concurrency does not equal connection count.** One invocation can open 0, 1, or many connections; one environment can hold a pool of connections; a proxy can multiplex many client sessions onto fewer backend connections depending on pooling mode and engine.

### 2.1. Why Traditional Server Patterns Fail

An application running on 4 VMs, each with a max pool of 10 connections, has a theoretical ceiling of 40 backend connections (excluding jobs, admin tasks, and other systems). If serverless scales out to 200 environments, each holding a pool of up to 10, potential connections jump to 2,000. The database may allow only a small fraction of that number.

Setting a high pool size inside each function rarely speeds up requests. When an invocation executes a single query, a large pool per environment merely increases maximum open sessions without delivering proportional throughput.

## 3. Estimating Connections Before Deployment

### 3.1. Upper Bound

Under a simple model, if:

- E: number of concurrently active execution environments,
- P: maximum connections in each environment's pool,
- D: extra out-of-pool connections each environment may open,

then approximate maximum client connections are:

$$
C_{client,max} = E \times (P + D)
$$

If each environment processes multiple concurrent invocations and each invocation opens its own connection, calculate using actual invocation concurrency rather than E alone. The formula above is an estimation model; real limits depend on runtime, driver, pool lifecycle, multiplexing, proxies, and how sessions are held.

### 3.2. Leaving Budget for Other Clients

Never allocate the entire `max_connections` to functions. A baseline budget:

$$
C_{function} \leq C_{DB,safe} - C_{other} - C_{reserve}
$$

Where:

- `C_DB,safe` is the database connection budget sustainable under configuration and load testing.
- `C_other` covers other applications, workers, migrations, monitoring, admin, and operational tooling.
- `C_reserve` is headroom for bursts, failovers, rollouts, maintenance, and emergency operations.

A database's configured connection limit is not necessarily the number of connections at which it maintains healthy performance. Every connection consumes memory, processes/threads, and internal resources. Validate via load tests and engine guidance.

### 3.3. Budget Calculation Example

Suppose a database is configured for 500 max connections. Initial load testing establishes a safe operational budget of 350 connections. Existing clients and operational tools are projected to use up to 180; the team reserves 50 for headroom. Remaining budget for serverless:

$$
C_{function} = 350 - 180 - 50 = 120
$$

With up to 60 concurrent execution environments, the rough maximum average pool size per environment is:

$$
P \leq 120 / 60 = 2
$$

This suggests each environment should hold at most around 2 backend connections in a direct-connection model. This is **not a universal recommendation for pool size = 2**; if concurrency reaches 150 environments, the budget is still breached. Combine concurrency caps, pool sizing, proxies, timeouts, and scaling behavior.

### 3.4. Load Scenario Table

| Hypothetical scenario | Concurrent environments | Max pool per environment | Potential connections |
| --- | ---: | ---: | ---: |
| Normal traffic | 20 | 2 | 40 |
| Peak traffic | 60 | 2 | 120 |
| Unbounded burst | 150 | 2 | 300 |
| Burst with large pool | 150 | 5 | 750 |

This table reflects only environment × pool and omits other connection sources. Enforce a concurrency cap aligned with database capacity rather than letting functions scale unboundedly and hoping the DB keeps up.

## 4. Managing Connection Lifecycles Inside Functions

### 4.1. Initialize Clients Outside the Handler When Reusable

Many platforms reuse execution environments across invocations. You can initialize the DB client or pool at module/global scope for reuse instead of opening and closing pools on every request. This cuts DNS, TCP/TLS handshake, and authentication overhead on warm invocations.

Node.js example:

~~~javascript
// db.js - small pool per execution environment.
import pg from "pg";

const { Pool } = pg;
const pool = new Pool({
  host: process.env.DB_HOST,
  port: Number(process.env.DB_PORT ?? 5432),
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  max: 1,
  connectionTimeoutMillis: 2000,
  idleTimeoutMillis: 10000,
  statement_timeout: 5000,
  ssl: { rejectUnauthorized: true }
});

export async function query(text, values) {
  return pool.query(text, values);
}
~~~

The handler imports `query` and uses the environment-scoped pool. `max: 1` is illustrative for workloads executing few concurrent queries per environment; adjust according to runtime, driver, and transaction patterns.

**Never assume execution environments live forever or are always reused.** Platforms can freeze, terminate, or replace environments. Never rely on local RAM for business state, and never rely on unguaranteed shutdown hooks to commit transactions or flush critical data.

### 4.2. Avoid Creating a New Pool per Invocation

~~~javascript
export async function handler(event) {
  // Anti-pattern: creating a new pool on every invocation.
  const pool = new Pool({
    connectionString: process.env.DB_URL,
    max: 10
  });
  const result = await pool.query("SELECT now()");
  await pool.end();
  return result.rows[0];
}
~~~

Creating a new pool on every request forfeits reuse benefits, adds handshake overhead, and can trigger connection bursts. Calling `pool.end()` at the end of every invocation is also counterproductive when the runtime keeps the environment warm for subsequent requests.

This is an anti-pattern for runtimes that support pool reuse. If the runtime never reuses environments, uses a pool-less database API client, or platform guidance recommends short-lived connections, another strategy may apply. Follow official runtime/driver guidance and benchmark before choosing.

### 4.3. Always Release Borrowed Pool Connections

~~~javascript
export async function createOrder(pool, order) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const inserted = await client.query(
      "INSERT INTO orders(id, customer_id, status) VALUES ($1, $2, $3) RETURNING id",
      [order.id, order.customerId, "PENDING"]
    );
    await client.query(
      "UPDATE inventory SET reserved = reserved + 1 WHERE sku = $1",
      [order.sku]
    );
    await client.query("COMMIT");
    return inserted.rows[0].id;
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch (rollbackError) {
      // Log safely, preserve original error.
    }
    throw error;
  } finally {
    client.release();
  }
}
~~~

Forgetting `release()` exhausts the pool even while the database remains healthy. Failing to roll back on transaction errors can leave a session stuck in an open transaction, holding locks or tainting subsequent operations. Production code should handle rollback failures and discard the session if the driver marks it unsafe for reuse.

## 5. Connection Pooling: Where Should the Pool Live?

### 5.1. Per-Execution-Environment Pools

Each environment maintains a small pool, reusing connections across subsequent invocations.

**Advantages:** simple, zero extra network hops, low latency while connections stay warm.

**Limitations:** pools multiply with environment count; instances can scale concurrently; stale environments can freeze or close; connections invalidated by network/database failovers must be detected and re-established.

Well suited when concurrency is bounded, pools are tiny, database connection budget is sufficient, and drivers handle broken connections cleanly.

### 5.2. Intermediary Proxy or Pooler

A proxy accepts many client connections from functions and manages backend connections to the database. Some proxies simply retain and reuse backend sessions; dedicated poolers support **transaction pooling** or multiplexing so many client sessions share fewer backend connections.

~~~mermaid
flowchart TB
    F1["Function environment A"] --> C1["Client connection"]
    F2["Function environment B"] --> C2["Client connection"]
    F3["Function environment C"] --> C3["Client connection"]
    C1 --> Proxy["Managed DB Proxy / Pooler"]
    C2 --> Proxy
    C3 --> Proxy
    Proxy --> B1["Backend DB session 1"]
    Proxy --> B2["Backend DB session 2"]
    B1 --> DB[("Database")]
    B2 --> DB
~~~

**Advantages:** reduces backend connections, absorbs client churn, centralizes authentication, and can smooth failover depending on the product.

**Costs:** adds a network hop, another component requiring capacity and monitoring, service fees, session/pinning restrictions, and new failure modes. Proxies also have max client, CPU, memory, and throughput limits.

### 5.3. Session Pooling vs. Transaction Pooling

| Mode | Mechanism | Compatibility |
| --- | --- | --- |
| **Session pooling** | Client binds to a backend session for the client connection's lifetime | Better compatibility with session state, but lower backend multiplexing |
| **Transaction pooling** | Backend connection is assigned when a transaction begins and returned on commit/rollback | Higher multiplexing, but restricts session state outside transactions |
| **Statement pooling** | Backend connection can switch after every statement | Heavily restricted; unsuitable for multi-statement transaction flows |

Transaction pooling can be incompatible with session-level `SET` commands, temporary tables, session advisory locks, prepared statements, or backend-bound state depending on the pooler and settings. Test real drivers, ORMs, and queries. Never switch pooling modes in production without verifying compatibility.

### 5.4. Proxies Do Not Share Identical Semantics

Being called a proxy does not guarantee every product supports transaction multiplexing. Managed database proxies may manage connection lifecycles, pin backend sessions to clients, or impose pinning limits. Dedicated poolers like PgBouncer publish explicit pooling modes. Verify:

- Does the proxy open backend connections on clients' behalf, and what is the cap?
- Does it support transaction pooling or only session pooling?
- Which operations cause a session to become pinned to a backend?
- How does it behave during database failover, credential rotation, or connection timeouts?
- Is TLS enforced from client to proxy and from proxy to database?
- What are the quotas, throughput, connection limits, idle timeouts, and costs?

## 6. Choosing a Data Access Model for Serverless

Not every serverless application needs a proxy. The choice depends on database engine, driver, concurrency, query duration, transaction needs, and platform capabilities.

| Model | Best when | Trade-offs |
| --- | --- | --- |
| Direct connection + small pool | Bounded concurrency, DB tolerates client sessions | Simple with fewer hops, but connections scale with environments |
| Managed DB proxy | Need to curb connection churn and centralize client connections | Adds cost/hop; requires understanding pinning, quotas, and failover |
| Dedicated pooler | Can operate a pooler and need transaction pooling/multiplexing | Self-managed HA, sizing, monitoring, and compatibility |
| HTTP/Data API | Database exposes an HTTP API; workload suits HTTP requests | Eliminates client sockets, but changes semantics, latency, transactions, and API quotas |
| Queue + batch/worker | Tasks can run asynchronously and be batched | Adds latency, eventual consistency, and retry/dedup mechanisms |

**Do not convert every database operation into an HTTP API solely to avoid connections.** Compare transactions, query patterns, payloads, request limits, latency, and correctness guarantees.

## 7. Concurrency Limits and Backpressure

Small pools reduce connections per environment, but do not cap total environments. Concurrency must be governed at the function and event-source layers.

### 7.1. Setting Concurrency Caps from the DB Budget

If each environment opens at most `P` backend connections and the function budget is `C_function`, a baseline environment cap is:

$$
E_{max} \leq \left\lfloor \frac{C_{function}}{P} \right\rfloor
$$

When using a proxy, distinguish **client connections to the proxy** from **backend connections to the database**. Total client connections may exceed the backend pool, yet the proxy still has max client, CPU, memory, and throughput limits. Size both ends.

### 7.2. Multi-Layer Throttling

- **Function concurrency limit:** set maximum concurrency to match the database budget.
- **Event source concurrency:** tune parallel message processing; batch sizes and polling also drive load.
- **Queue buffering:** offload deferrable work to queues to absorb bursts.
- **Rate limiting:** throttle per client/tenant and protect expensive operations.
- **Database admission control:** cap workload concurrency, query timeouts, transaction durations, and pool sizes.
- **Backpressure:** when the DB or proxy nears limits, slow down ingestion instead of spawning more invocations.

With queues, scaling consumers too aggressively turns a backlog into a connection burst. Tune consumer concurrency to DB capacity and ramp gently under backlog rather than scaling workers unboundedly with queue depth.

### 7.3. Example Burst-Handling Strategy

An order-intake API quickly acknowledges receipt and enqueues order processing. Serverless workers pull small batches at capped concurrency, using a pool/proxy to write to the DB. When DB latency climbs or backend connections approach limits, consumer concurrency throttles back and allows the queue backlog to grow within acceptable business bounds.

This works only if business rules allow an "accepted" response before transaction completion. If users need immediate inventory and payment confirmation, design a dedicated synchronous path or explicit status flow.

## 8. Designing Short, Recoverable Transactions

Transactions hold backend connections and potentially locks while open. In serverless, function execution can stretch due to cold starts, retries, external calls, or queue waits. Therefore, **transaction durations must be short and bounded**.

### 8.1. Never Hold a Transaction Across External System Calls

Risky pattern:

~~~text
BEGIN
  Read inventory and lock rows
  Call payment gateway over the Internet (may take several seconds)
  Wait for callback or retry
  Write order status
COMMIT
~~~

While waiting on payment, the connection and locks stay held. If the payment gateway slows down, many invocations pile up holding connections and locks, stalling other requests and raising deadlock and timeout risks.

Split the flow into stateful steps:

1. Short transaction creates the order in `PENDING` state and atomically records/reserves inventory.
2. Commit the transaction and release the connection back to the pool.
3. Call the payment gateway outside any DB transaction, passing an idempotency key.
4. A subsequent short transaction updates order state based on the verified payment result.
5. If the outcome is indeterminate due to timeout, retain `PENDING`/`UNKNOWN` per policy and reconcile—never assume failure.

~~~mermaid
sequenceDiagram
    participant F as Serverless function
    participant DB as Database
    participant Pay as Payment gateway
    F->>DB: BEGIN, create PENDING order
    F->>DB: Reserve inventory, COMMIT
    DB-->>F: Commit OK
    F->>Pay: Charge with idempotency key
    alt Payment accepted
        Pay-->>F: Payment reference
        F->>DB: BEGIN, set PAID, COMMIT
    else Timeout / unknown result
        Pay--xF: No conclusive response
        F->>DB: Record PENDING/UNKNOWN, schedule reconciliation
    end
~~~

This is now a multi-step business process rather than one overarching ACID transaction. Design state machines, reservation expiration, compensation/refunds, reconciliation, and notifications as required. Never solve this by extending transaction timeouts.

### 8.2. Timeout Hierarchy

Configure timeouts in proper order:

| Timeout | Purpose | Notes |
| --- | --- | --- |
| Connection acquisition timeout | Cap wait time for a connection from pool/proxy | Too long ties up function concurrency without doing work |
| Connect timeout | Cap time to open socket/TLS to DB or proxy | Must account for DNS, network, and handshake |
| Statement/query timeout | Prevent runaway queries | Must fit query SLAs and engine behavior |
| Transaction timeout/idle-in-transaction | Catch long-running or abandoned transactions | Must align across application and DB settings |
| Function deadline | Cap overall invocation runtime | Leave margin for controlled cleanup/rollback before hard stop if runtime supports it |

Never set all timeouts to identical values. Connection acquisition must be shorter than total deadline; query timeouts must allow valid queries while halting hung ones; function deadlines must leave room for error handling and cleanup.

### 8.3. Stale Connections and Failovers

A long-lived pool can hold connections broken by DB restarts, proxy failovers, network blips, or idle timeouts. Drivers must detect broken connections and pools must discard dead sessions instead of reusing them repeatedly. Consider:

- Validation/health checks on connection borrow where driver and performance allow.
- Maximum lifetime/idle timeouts aligned with proxy/database policies.
- Retrying new connections on transient errors, while never blindly retrying write commands when commit status is unknown.
- Using idempotency keys or transaction markers to determine outcomes when responses drop after commit.
- Tracking reconnect rates, connection resets, auth failures, and recovery times.

## 9. Retries, Idempotency, and Avoiding Load Amplification

Retries recover from transient glitches, yet in serverless they can spike concurrency right when the database is weakest. If invocations time out and the platform auto-retries, functions can rerun repeatedly while older connections or queries are still executing.

### 9.1. Classify Errors Before Retrying

| Error class | Examples | Recommended behavior |
| --- | --- | --- |
| Configuration / permanent | Bad password, missing database, missing privileges | Do not retry repeatedly; alert and fix configuration |
| Transient connection error | Resets, failovers, DNS/network interruptions | Bounded retries with backoff and jitter |
| Overload | Too many connections, pool exhausted, throttling | Lower concurrency/apply backpressure; do not retry immediately |
| Statement error | Constraint violations, SQL syntax, schema mismatches | Handle per business semantics or fix code; usually do not retry as-is |
| Indeterminate outcome | Client disconnects after sending `COMMIT` | Query by idempotency key/operation ID before deciding to repeat |

### 9.2. Exponential Backoff and Jitter

A typical retry schedule increases delay exponentially with a cap and adds jitter so invocations do not retry in lockstep:

~~~javascript
function retryDelayMs(attempt, baseMs = 100, capMs = 3000) {
  const ceiling = Math.min(capMs, baseMs * (2 ** attempt));
  return Math.floor(Math.random() * ceiling);
}
~~~

This helper is illustrative only; real policies need max attempts, overall deadlines, error classification, and concurrency caps. Do not sleep-retry inside a function if waiting holds the invocation longer than a queue or scheduler could manage more efficiently.

### 9.3. Idempotency for Write Operations

Suppose a client submits an order-creation request with an idempotency key. The database can store the unique key alongside the operation outcome:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id       text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash    text NOT NULL,
    response_body   jsonb,
    status          text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Design rules for the use case:

- Same key and same request hash: return the saved result or in-progress status.
- Same key with a different payload: reject due to key misuse.
- Initial request still running: duplicate request waits, reads status, or receives a processing code per API contract.
- Key expiration: retention must exceed retry windows of clients, event sources, and payment providers.

Idempotency records must be persisted in the same transaction as critical side effects. Writing the key in one transaction and the order in another without coordination risks leaving a "processed" marker with no order, or vice versa.

## 10. Securing Database Connections

Serverless DB access demands least privilege and controlled credential lifecycles. Automatic function scaling is no excuse to grant a superuser DB account to every invocation.

### 10.1. Secrets and Identity Management

- Prefer integrated workload identity/IAM authentication or short-lived tokens when supported by engine, driver, and proxy.
- When using usernames/passwords, store them in a secret manager with per-function/role read permissions and a rotation schedule.
- Never log connection strings, passwords, tokens, or raw SQL containing personal data.
- Never embed secrets in source code, container images, packages, or unprotected config variables.
- Isolate identities by environment and workload; avoid sharing DB accounts across dev, staging, and production.
- Scope `SELECT`/`INSERT`/`UPDATE` privileges per table or schema; never grant DDL/owner privileges by default.

### 10.2. TLS and Network Access

Connections from functions to proxies/databases must be encrypted per policy. Verify server certificates, CA chains, hostname validation, and rotation. If TLS terminates at a proxy, evaluate the proxy→database leg too; never assume a private network is automatically encrypted.

Databases should not expose public endpoints to all addresses merely for function convenience. Place functions in a VPC/VNet or appropriate private networking topology, restricting security groups/firewalls to required sources and ports. Also account for NAT gateways, subnet routing, DNS, and egress IP addresses when databases or proxies require allowlists.

### 10.3. Privilege Separation and Data Scoping

| Control | Design |
| --- | --- |
| Function identity | Dedicated role per function or risk-aligned workload group |
| DB principal | Account granted access only to required schemas/tables |
| Secret access | Only runtime role reads needed secrets; access is audited |
| Networking | Allow connections only from required subnets/security identities; never expose DB publicly |
| TLS | Verify certificates and encrypt every sensitive hop |
| Logging | Mask passwords, tokens, sensitive parameters, and personal data |
| Rotation | Rotate secrets/tokens without taking down functions; test pool reconnection |

Credential rotation can invalidate existing connections or break new pool logins. Test proxy, database, and driver behavior; roll out in phases and watch authentication errors.

## 11. Observing Connections and Database Saturation

Watching database CPU alone is insufficient. A database can show low CPU while out of connections, clogged with `idle-in-transaction` sessions, or blocked on locks; a proxy can exhaust client capacity while the backend DB remains idle.

### 11.1. Metrics to Monitor

| Layer | Metrics / signals | Meaning |
| --- | --- | --- |
| Function | Concurrent executions, throttles, duration, timeouts, cold starts | Estimates potential client count and generated load |
| Driver / pool | Total, idle, active, waiting, acquisition latency, connection errors | Detects pool exhaustion, leaks, or reconnect storms |
| Proxy | Client connections, backend connections, queue depth, pinning, CPU/memory | Detects proxy saturation and poor multiplexing |
| Database | Current/max connections, active/idle sessions, lock waits, deadlocks | Shows DB limits and contention |
| Query | p50/p95/p99 latency, slow queries, rows scanned, timeouts | Identifies slow queries as root cause rather than connection counts |
| Transaction | Duration, idle-in-transaction, rollbacks, commit failures | Surfaces connections/locks held too long |
| Queue/event source | Backlog age, batch sizes, retry counts, consumer concurrency | Reveals bursts hitting the database |

Configure alerts by thresholds and trends—for instance, when backend connections reach a high percentage of the safe budget, acquisition latency spikes, or pool waits grow. Derive concrete thresholds from load tests and engine capacity.

### 11.2. Correlation IDs and Tracing

Propagate operation/request IDs across API gateways, functions, queues, proxy logs, and database query logs where tooling permits. This pinpoints which request holds long transactions or fires duplicate queries. Never place credentials or sensitive payloads in trace attributes; bound telemetry cardinality and retention.

### 11.3. Distinguishing Pool Exhaustion from DB Exhaustion

**Client-side pool exhaustion:** the pool has no idle connections left, so invocations block on acquisition. The database may still be well below `max_connections`; likely causes include connection leaks, long transactions, or an undersized pool.

**DB connection exhaustion:** the database has hit its session cap; new clients or proxy backends cannot log in. Audit other connection consumers, idle sessions, and workload budgets.

**Proxy saturation:** the proxy runs out of client slots, backend pools, CPU/memory, or queue capacity. The database may still be healthy; raising `max` pool size in every function can overload the proxy further.

Investigate layer by layer and compare concurrent metrics before raising limits.

## 12. Load Testing and Realistic Sizing

A meaningful load test must reproduce serverless dynamics rather than hammering a single pre-warmed function.

### 12.1. Scenarios to Measure

1. **Warm steady-state:** steady traffic with reused execution environments; establish baseline pools, query latency, and connections.
2. **Cold burst:** ramp rapidly from near zero to peak; observe new environment creation, connection handshakes, and proxy/backend growth.
3. **Sustained peak:** hold concurrency long enough to surface leaks and idle sessions.
4. **Spike and recovery:** surge then drop traffic; measure connection closures, idle timeouts, and resource release times.
5. **Database failover/restart:** observe stale connections, reconnect storms, ambiguous transactions, and recovery time.
6. **Proxy unavailable or overloaded:** verify function timeouts/backoff engage without triggering retry storms.
7. **Credential rotation:** verify old/new pools, authentication, and continuity.
8. **Queue backlog:** step up consumer concurrency to locate the database saturation point.

### 12.2. Test Matrix

| Variable | Suggested test values | Observations |
| --- | --- | --- |
| Function concurrency cap | 10, 25, 50, 100 (per lab quota) | Connection peaks, throttles, latency |
| Pool max per environment | 1, 2, 4 | Backend sessions, acquisition wait |
| Proxy | No proxy / session proxy / transaction pool if supported | Client/backend ratio, pinning, latency |
| Query duration | Short, medium, simulated slow queries | Transaction duration, locks, waits |
| Retry policy | No retry, fixed retry, backoff+jitter | Total requests, connection storms, recovery time |
| Event batch/concurrency | Small/large batches, low/high consumer caps | DB pressure, backlog age, throughput |

Never run destructive tests against production databases. Use staging environments with sanitized data and cost guardrails. Change small groups of variables per run to isolate root causes.

### 12.3. Acceptance Criteria

A configuration is acceptable when:

- Peak connections stay below the approved budget, including during bursts and failovers.
- Acquisition/query latencies and error rates stay within SLO.
- Functions do not time out waiting on pools; pool wait queues do not grow unboundedly.
- Proxies and databases maintain healthy headroom with no lingering `idle-in-transaction` sessions.
- Retries do not amplify load when the database is under stress.
- Write operations stay idempotent across timeouts or lost responses.
- Credential rotation and endpoint failovers complete within recovery targets.
- Combined costs of functions, proxies, databases, NAT, and telemetry stay within budget.

## 13. Architecture Example: Serverless Order Placement API

Suppose an API accepts order creation requests. API Gateway invokes a function, which writes the order and reservation to PostgreSQL and then emits an event for payment processing. Baseline traffic is low, but promotional campaigns cause sharp concurrency spikes.

### 13.1. Proposed Architecture

~~~mermaid
flowchart TB
    Client["Web / Mobile"] --> GW["API Gateway"]
    GW --> Fn["CreateOrder function"]
    Fn --> Proxy["Managed DB proxy / pooler"]
    Proxy --> DB[("PostgreSQL")]
    Fn --> Q["Queue: OrderAccepted"]
    Q --> Worker["Payment / order worker functions"]
    Worker --> Proxy
    Proxy --> DB
    DB --> Obs["DB metrics / logs"]
    Proxy --> Obs
    Fn --> Telemetry["Function logs / traces"]
    Worker --> Telemetry
~~~

In this design, the API function uses a small pool or short-lived client per proxy guidance; worker concurrency is capped to the DB budget. Never default every function to a pool of 10 connections. Connection budgets account jointly for APIs, workers, batch jobs, admin tasks, and migrations.

### 13.2. Order Creation Flow

1. API Gateway authenticates requests appropriately; the function verifies tenant/actor and idempotency key.
2. Function opens a short transaction to write the `PENDING` order, reservation, and idempotency record per contract.
3. Upon commit, the connection returns immediately.
4. System writes an outbox event in the same transaction or uses an explicit lossless event-emission pattern.
5. Worker consumes the message and processes payment outside any DB transaction, passing an idempotency key to the payment gateway.
6. Worker updates order status in a separate short transaction.
7. If payment times out, `UNKNOWN` state is reconciled—never recharge merely because a message was redelivered.

### 13.3. Sizing Decisions

| Item | Sample design rule |
| --- | --- |
| Function local pool | Small, tuned to parallel queries inside each environment |
| Function concurrency | Cap total environments to match backend connection budget and proxy capacity |
| DB proxy | Deploy HA and monitor client/backend sessions, pinning, and queue depth |
| Database | Reserve connections for admin, migrations, monitoring, and other workloads |
| Queue workers | Cap consumer concurrency; apply backpressure when DB latency/connections climb |
| Transactions | Include only DB operations requiring atomicity; never hold across payment API calls |
| Retries | Apply backoff+jitter, max attempts, and idempotency |
| Monitoring | Monitor functions, pools, proxies, DB, and queues together |

These are design principles, not fixed configurations. Exact pool sizes, concurrency caps, and proxy sizing must be validated under load against your specific services.

## 14. Choosing the Right Database and Data Model

Connection management cannot be separated from database selection. A serverless workload may use a relational database, key-value/document store, data API, or HTTP-backed managed service.

| Backend type | Access model | Questions to consider |
| --- | --- | --- |
| Relational DB over TCP | Driver and connection pool/proxy | Transactions, concurrent sessions, connection caps, locks, and query patterns |
| Managed key-value/document | SDK/API, often HTTP-based | Partition keys, throughput, hot partitions, transaction semantics, throttling |
| Database Data API | HTTPS requests to a service API | Request quotas, payload limits, transaction duration, latency, feature parity |
| Serverless database engine | Auto-scaling compute/storage or connection management | Capacity model, minimum spend, cold behavior, connection semantics, failover |

Choosing NoSQL does not automatically eliminate connection or capacity issues if SDKs still maintain clients/sessions or the service enforces request and throughput quotas. Likewise, choosing a relational DB does not mandate a proxy if concurrency is low and connection budgets are ample.

Base the decision on queries and business needs: consistency, relationships, transactions, access patterns, latency, volume, retention, backups, portability, and operational skills.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a new pool per invocation | Connection churn, extra handshakes, and backend sessions | Reuse clients/pools when supported by runtime or use an appropriate connection model |
| Large pools inside every environment | Connections multiply rapidly on scale-out | Small pools, concurrency caps, and global connection budgeting |
| Allowing unbounded function scaling | Database saturates long before compute | Admission control, concurrency limits, and queue backpressure |
| Holding transactions across external API calls | Locks/connections stay held, raising deadlocks and timeouts | Split flows into short transactions with explicit states |
| Infinite retries or retrying config errors | Connection storms and rising costs | Classify errors, apply backoff+jitter, deadlines, and attempt caps |
| Retrying non-idempotent writes | Duplicate orders or double charges | Idempotency keys, operation IDs, and reconciliation |
| Assuming proxies multiplex every session | Session pinning keeps backend connections high | Read pooler semantics and test real queries/session state |
| Failing to release clients after transactions | Pool drains even while DB is healthy | `finally`/release, rollback on errors, and leak checks |
| Watching DB CPU as the sole metric | Misses connection exhaustion, locks, and proxy queues | Monitor pools, proxies, databases, and transactions jointly |
| Untested password rotation | New pools fail auth; old pools get dropped | Phased secret rotation, reconnect testing, and rollback |
| Exposing DB publicly for easier function access | Expands attack surface and IP coupling | Private networking, TLS, IAM, and minimal firewall rules |
| Making every task asynchronous | Unnecessary eventual consistency and retry complexity | Use async only where business semantics allow |

## 16. Hands-On Exercise: Keeping the Database Stable During a Campaign

An e-commerce platform runs checkout via serverless functions. On normal days around 15 environments stay active, but campaigns rapidly scale up to 180. Each environment currently creates a PostgreSQL pool of up to 5 connections. The database has a configured limit of 600 connections; reporting and admin systems can consume up to 160. After a test campaign, the database reports `too many connections` and function timeouts spike.

**Assignment requirements:**

1. Calculate potential client connections during normal days and campaigns assuming pools are fully populated.
2. Propose a connection budget for checkout after reserving operational usage and headroom; document any unverified assumptions.
3. Compare three options: shrinking pool size + concurrency caps; adding a managed proxy/pooler; offloading part of processing to a queue/worker.
4. Redesign the order-creation transaction so connections are never held while calling the payment gateway; describe states when payment times out.
5. Specify idempotency keys, result storage, and handling when clients retry after dropped responses.
6. Propose timeouts, retry/backoff, and worker concurrency policies as queue backlog grows.
7. List metrics and dashboards needed to distinguish pool exhaustion, proxy saturation, and database exhaustion.
8. Write a load test plan covering warm traffic, cold bursts, sustained peak, failover, and credential rotation.
9. Write an ADR documenting the architectural choice, costs, risks, and review triggers.

### Evaluation Hints

Assuming every environment fills its pool:

$$
C_{normal} = 15 \times 5 = 75
$$

$$
C_{campaign} = 180 \times 5 = 900
$$

900 already exceeds the 600 configured limit even before counting the 160 reporting/admin connections. A passing design cannot just shrink the pool; it must **cap total concurrency, reserve budgets, shorten transactions, and control retries**. If adding a proxy, budget client connections and backend connections separately while verifying pinning and quotas.

## 17. Pre-Production Checklist for Functions Accessing Databases

- [ ] Runtime concurrency and maximum execution environments are modeled.
- [ ] Maximum connections each environment/invocation can open are identified.
- [ ] Connection budget accounts for other apps, workers, migrations, admin tasks, and headroom.
- [ ] Pools are reused per lifecycle or follow provider-recommended connection strategies.
- [ ] Connections are always released; transactions always commit/rollback within short bounds.
- [ ] Transactions are never held open while waiting on external APIs, queues, or unrelated work.
- [ ] Pools/proxies/DBs define clear timeouts, idle policies, connection lifetimes, and stale-session handling.
- [ ] Function concurrency, event source concurrency, and queue consumers are capped.
- [ ] Retries classify errors, use backoff+jitter, and are bounded; writes enforce idempotency.
- [ ] Payment or external operations support indeterminate states and reconciliation.
- [ ] Database credentials are managed via secret manager/IAM with tested rotation.
- [ ] TLS, hostname verification, private networking, firewalls, and least privilege are configured.
- [ ] Metrics cover pool waiting, proxy client/backend connections, DB connections, transaction duration, and query latency.
- [ ] Load tests exercise cold bursts, sustained peaks, failovers, proxy pressure, and credential rotation.
- [ ] Alerts, runbooks, cost limits, and load-shedding plans exist for DB overload.

**Takeaway:** Serverless scales compute rapidly, yet databases remain constrained by sessions, memory, locks, and throughput. Resilient designs start with a **headroom-backed connection budget**, tiny per-environment pools, concurrency caps, and short transactions. Proxies/poolers, queues, or Data APIs each solve only part of the problem; verify semantics, security, and failure behavior under real load to keep reliability, performance, cost, and operations within acceptable bounds.
