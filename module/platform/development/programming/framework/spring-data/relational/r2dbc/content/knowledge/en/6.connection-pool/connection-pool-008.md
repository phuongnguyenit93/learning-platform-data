# Calculating Connection Budgets for Multi-Replica Applications

When deploying a Spring Data R2DBC application across multiple instances, you must calculate the total number of connections all instances combined can open to the database. The `maxSize` limit on a connection pool applies only to one pool in one process. When running multiple replicas, total connection capacity equals the sum of all pool limits across every replica, including temporary replicas created during scaling or rollouts.

If you size the pool based on a single instance and later increase replicas without recalculating, the application can exceed the database's connection limit. Common consequences include inability to open new connections, requests stalling in pool wait queues, slowed or failed transactions, and unrelated services impacting one another through a shared connection budget.

## 1. Distinguishing Per-Pool Limits from System-Wide Limits

`ConnectionPool` manages connections created from a single `ConnectionFactory`. The `maxSize` property sets the maximum number of connections one pool can manage. Pools are normally configured inside each application process, so every replica holds its own pool and its own limit.

For example, a Deployment with 5 replicas where each replica has one pool with `maxSize = 20` can open up to 100 connections to the database. If a background worker also runs with a pool capped at 10 connections, the combined potential of both workloads is 110 connections.

| Scope | How the Limit Is Calculated |
|---|---|
| One pool in one process | `maxSize` of that pool |
| One process with multiple pools | Sum of `maxSize` across all pools in the process |
| One workload with identical replicas | Maximum process count multiplied by total `maxSize` per process |
| Entire system sharing a database | Sum of potential connections from every workload, job, and operational tool able to connect |

Pools usually create connections on demand or per initialization settings rather than opening the entire `maxSize` immediately. When budgeting, however, assume every pool can hit its maximum limit at the same time. This worst-case capacity calculation keeps the system within bounds under load spikes.

## 2. Determining the Database Connection Budget

First, identify the maximum connections allowed by the database and the portion that must be reserved for other components. Never allocate the entire `max_connections` or equivalent limit to a single application.

The budget available to an application can be expressed as:

\[
  B_{app} = C_{db} - C_{reserved} - C_{other}
\]

Where:

- \(C_{db}\): concurrent connection limit of the database or of the endpoint the application connects to.
- \(C_{reserved}\): capacity reserved for administration, monitoring, migrations, backups, incident response, and safety headroom.
- \(C_{other}\): maximum expected connections from other applications, services, and workloads sharing the database.
- \(B_{app}\): remaining maximum budget for the application being sized.

For example, suppose a database allows 250 connections. Operations reserves 20 connections for admin tools and maintenance tasks, other apps can use up to 70 connections, and the team keeps 30 connections as headroom. The remaining budget for this application is:

\[
  B_{app} = 250 - 20 - 70 - 30 = 130
\]

The number 130 is the total ceiling across all replicas and pools of the application, not a per-replica limit.

Take limits from actual database configurations and environments. In some databases, admin or privileged accounts may have dedicated slots; proxies or connection brokers may also enforce a different cap than the backend database. Calculate against the actual endpoint the application connects to, and separate frontend vs. backend limits if a proxy sits in between.

## 3. Counting Peak Replicas

Do not rely solely on the replica count running at the moment you check. Calculate the peak number of processes that can exist simultaneously during peak load or deployments.

Sources that increase process counts include:

- **Horizontal scaling:** HPA or autoscalers can scale replicas up to `maxReplicas`.
- **Rolling updates:** during a rollout, new replicas may start before old replicas terminate. For Kubernetes Deployments, include `maxSurge`.
- **Blue-green deployments:** old and new environments can run concurrently during traffic cutover.
- **Workers and scheduled jobs:** background pods, consumers, or batch jobs can open their own pools even if excluded from API replica counts.
- **Multiple processes per host or pod:** if one pod runs multiple application processes, each process may own its own pool.

Peak process count can be expressed as:

\[
  N_{peak} = N_{steady,max} + N_{surge} + N_{extra}
\]

Where \(N_{steady,max}\) is the maximum scaled process count, \(N_{surge}\) is extra processes allowed during rollouts or cutovers, and \(N_{extra}\) is auxiliary processes like workers or jobs if not already counted in the previous two terms.

For example, suppose a Deployment has `maxReplicas = 8`, rollout allows `maxSurge = 2`, and 2 background workers run separately. If all target the same database and each process has one pool, the process count to plan for is:

\[
  N_{peak} = 8 + 2 + 2 = 12
\]

Avoid double-counting a process group. If workers are already included in `N_{steady,max}`, do not add them again. For multiple distinct Deployments or workloads, compute each group separately and sum them.

## 4. Calculating Maximum `maxSize` Per Replica

When replicas are identical and each process has one pool, the maximum per-process pool size can be calculated as:

\[
  P_{max} \leq \left\lfloor \frac{B_{app}}{N_{peak}} \right\rfloor
\]

Where \(P_{max}\) is the pool's `maxSize` per process. Rounding down with floor ensures total connections never exceed the budget.

Continuing the example above: the application budget is 130 connections and peak processes equal 12. Then:

\[
  P_{max} \leq \left\lfloor \frac{130}{12} \right\rfloor = 10
\]

Configuring `maxSize = 10` per process yields a maximum combined capacity of:

\[
  C_{app,peak} = 12 \times 10 = 120
\]

The application stays inside its 130 budget, leaving 10 spare connections inside the application's own allocation. Teams can choose an even lower `maxSize` if real load does not require 10 concurrent connections per process.

### Spring Boot Configuration Example

When using Spring Boot with R2DBC pool, you can set limits in `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-acquire-time: 2s
```

This example assumes the R2DBC pool dependency is present in the application and the active Spring Boot version supports these properties. `max-size: 10` applies per application process. Running 12 processes gives a theoretical workload ceiling of 120 connections.

`initial-size` controls how many connections the pool initially creates per configuration, not the maximum cap. `max-acquire-time` limits wait time to borrow a connection. Timeout values should reflect SLAs and database latency; setting timeouts too long lets requests hold resources too long, while setting them too short fails requests during brief load spikes.

Property names and default values can vary by Spring Boot and R2DBC Pool version. Verify configuration against your project's actual dependency versions, and set `max-size` explicitly instead of relying on defaults.

## 5. Multiple Pools Within a Single Process

A process can use multiple `ConnectionFactory` beans or multiple pools—for example, a read pool and a write pool, or connections to two separate databases. In that case, you cannot treat one pool's `maxSize` as the process budget.

If a process contains \(K\) pools, the maximum connection limit per process is the sum of its pools:

\[
  P_{process} = \sum_{j=1}^{K} P_j
\]

With multiple workload groups having different process counts and pools, the general formula is:

\[
  C_{total} = \sum_{i=1}^{M} N_i \times
              \left(\sum_{j=1}^{K_i} P_{i,j}\right)
\]

Where \(N_i\) is the peak process count of workload group \(i\), and \(P_{i,j}\) is `maxSize` of pool \(j\) in each process of that group. This total must fit inside the connection budget allocated to the application or entire system.

For example, each API replica has a read pool capped at 8 and a write pool capped at 4. If up to 10 replicas can exist, the theoretical ceiling is:

\[
  10 \times (8 + 4) = 120 \text{ connections}
\]

If a batch worker has an additional pool capped at 6 across up to 2 processes, add 12 more connections, bringing total potential capacity to 132 connections. Include read pools, write pools, auxiliary pools, and worker pools in the spreadsheet.

When independent databases have separate limits, budget each database separately. A pool targeting database A does not consume database B's connection limit, unless both databases share a proxy or intermediary layer whose own limits must also be budgeted.

## 6. Leaving Headroom and Avoiding Over-Allocation

The division result provides an arithmetic ceiling, not a requirement to configure every replica right up to that limit. Picking a smaller pool can cut idle connections, lower database resource usage, and curb contention when multiple instances scale up simultaneously.

When selecting `maxSize`, consider:

- **Actual concurrency:** concurrent requests running database operations, parallel queries per request, and connection hold durations.
- **Transaction characteristics:** transactions typically hold a connection for their entire scope. Long transactions can exhaust a pool even at modest request rates.
- **Query duration:** slow queries hold connections longer, raising required concurrent connections.
- **Load spikes:** the pool must handle expected peak load, yet never inflate pool size to disguise inefficient queries or prolonged transactions.
- **Database resources:** many concurrent connections consume database memory, workers, slots, and other resources.
- **Operational headroom:** reserve capacity for migrations, maintenance tasks, traffic shifts, and rollout overlaps. Define headroom explicitly in the budget instead of treating the entire database limit as fair game.

Reactive design does not eliminate the need for connection limits. Multiple reactive requests can still wait on or occupy connections simultaneously. An unbounded `flatMap` concurrency stream can generate far higher database demand than expected. Control concurrency at the processing layer and ensure database operations do not hold connections while waiting on unrelated work like HTTP calls to external services.

## 7. Proxies and Multi-Tier Connection Pooling

Some architectures place a proxy or pooler such as PgBouncer between the application and database. In that setup, distinguish:

- **Client connections:** connections from each R2DBC pool to the proxy.
- **Backend connections:** connections from the proxy to the actual database.

`maxSize` on an R2DBC pool generally caps client connections opened by one process to the proxy. The proxy may multiplex or map client connections onto a pool of backend connections depending on pooling mode. Thus, client connection counts and backend connection counts do not necessarily match.

Using a proxy does not remove the need for budgeting. Verify the proxy's client limit, backend limits per database or user, and how the proxy handles transactions, session state, and prepared statements. For instance, transaction-pooling mode carries different constraints than session-pooling mode; applications should not assume all session state persists across backend connection reuse.

Without a proxy, connections from application pools count directly toward the database's connection limit. With a proxy, maintain two budgets: one for client connections to the proxy and one for backend connections to the database.

## 8. Monitoring the Pool and Spotting Budget Shortfalls

After deployment, compare actual metrics against your calculated budget. Useful metrics include:

| Metric | Meaning When Monitored |
|---|---|
| Allocated / total connections | Connections created and managed by the pool. Compare against per-replica `maxSize`. |
| Active connections | Connections currently borrowed by operations. Prolonged high values point to heavy pool or database load. |
| Idle connections | Connections sitting free in the pool. Many idle connections across every replica can keep total connections high even under low load. |
| Pending acquire | Requests waiting for a connection. Sustained growth signals the pool cannot keep pace or connections are held too long. |
| Acquire latency / timeout | Wait duration to obtain a connection and timeout counts. Surfaces bottlenecks before mass request failures. |
| Database connections | Total connections grouped by application, user, or client on the database side. Used to reconcile against the system-wide budget. |

Specific metric names vary by R2DBC Pool, Spring Boot, and observability tooling. Tag metrics by application, pod/instance, and pool so you can aggregate across replicas. Inspecting a single pod misses the workload's total connection footprint.

Common warning signs:

- **Pool hits `maxSize` and pending acquire climbs:** the application needs more concurrent connections than the pool allows. Check query times, transactions, concurrency, and pool config.
- **Database approaches its limit while single-replica pools are not full:** multiple replicas, extra pools, jobs, or other apps are likely connecting together. Sum metrics system-wide.
- **Connections spike during rollouts:** old and new pods coexist, scaling total pool capacity by actual process count.
- **High idle counts across many replicas:** `initial-size` or minimum-idle settings may be too high relative to replica count. Consider lowering initial connections or pool limits.
- **Acquire timeouts even though the database is below its limit:** local pools may be full, connections held too long, or queries slow. Overall database limits and per-process pool limits are separate layers.

Do not react to every pool error by raising `maxSize`. If the database is already near its limit, larger pools worsen the problem. First identify whether congestion sits in the application pool, proxy, or database.

## 9. Process for Creating and Updating Budgets

You can apply this process for each deployment environment:

1. Record the actual connection limits of the database and any proxy.
2. Subtract allocations for admin, monitoring, migrations, other workloads, and operational headroom to get the application budget.
3. Inventory every Deployment, worker, consumer, scheduled job, and process able to connect to the database.
4. Calculate peak process counts, including autoscaling, rollout surges, and overlap between old and new versions.
5. List every pool per process, including read/write pools or multi-database pools.
6. Allocate `maxSize` so total potential capacity stays within budget; pick practical values based on concurrency and hold durations.
7. Inspect metrics at normal load, peak load, and during rollouts; adjust pools or concurrency from measured data.
8. Recalculate the budget whenever `maxReplicas`, `maxSurge`, worker counts, pool counts, or database limits change.

A small budget table helps operations teams verify the impact of changes prior to rollout:

| Group | Peak Processes | Pools Per Process | Max Total Connections |
|---|---:|---:|---:|
| API replicas, including rollout surge | 10 | 1 × 10 | 100 |
| Background workers | 2 | 1 × 6 | 12 |
| **Application total** | | | **112** |

With the 130-connection application budget from the earlier example, this setup leaves 18 connections of headroom. If maximum API replicas increase from 8 to 12 or rollout surge changes, recalculate peak processes and confirm the total still fits inside the budget. The table must reflect actual configured pools rather than just pod counts shown on a dashboard.

Connection budgeting is part of deployment design. Every pool configured on a replica contributes to total database load. By sizing around peak processes, summing all pools, and reserving capacity for other workloads, teams can scale applications without accidentally exhausting connection limits during traffic peaks or rollouts.
