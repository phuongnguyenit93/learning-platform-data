# Distinguishing query time and pool wait time in Spring Boot

> **Chapter:** Database observability  
> **Lesson:** Distinguishing query time and pool wait time  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. Why separate query time and pool wait time?

When a repository call takes 800 ms, the cause is not necessarily a slow SQL query. The application might spend 700 ms just waiting to borrow a connection from the pool, and then execute the query in 100 ms. If you only watch one combined timer, developers might try optimizing SQL when the real cause is pool saturation.

**Pool wait time** is how long a request waits to be granted a database connection from the connection pool. **Query time** is the duration of a database operation within a defined measurement boundary, usually starting when the statement executes and ending when the driver receives the corresponding result. Clarify whether query time includes reading the full result set.

These metrics answer different questions:

- Pool wait time: does the application have enough free connections to serve current concurrency?
- Query time: once a connection is acquired, how long does the database operation take?
- Repository duration: how long does the entire repository call take, including auxiliary method work?
- Transaction duration: how long does the transaction hold resources, including gaps between statements?

~~~mermaid
flowchart LR
  A["Repository call begins"] --> B["Acquire connection"]
  B --> C["Connection granted"]
  C --> D["Prepare / execute query"]
  D --> E["Read result"]
  E --> F["Release connection"]
  A -. "Pool wait time" .-> C
  C -. "Query / DB operation time" .-> E
  A -. "Repository duration" .-> F
~~~

Measuring and dashboarding each stage separately pinpoints the real bottleneck instead of concluding vaguely that the database is slow.

## 2. How does a connection pool work?

Opening a new TCP connection to the database per query is expensive and can overload the database. A connection pool keeps a pre-created set of connections that requests borrow and return.

With HikariCP, Spring Boot typically auto-configures the pool when a compatible JDBC DataSource is present. A connection is borrowed via `getConnection()`, used for a transaction/statement, and returned to the pool when finished.

~~~mermaid
flowchart TD
  A["Concurrent application requests"] --> B["HikariCP connection pool"]
  B --> C{"Idle connection available?"}
  C -->|"Yes"| D["Borrow connection"]
  C -->|"No, capacity left"| E["Create connection"]
  C -->|"Pool at maximum"| F["Wait in acquisition queue"]
  D --> G["Execute SQL"]
  E --> G
  G --> H["Return connection"]
  H --> B
  F -->|"Timeout"| I["Connection acquisition failure"]
  F -->|"Connection released"| D
~~~

The pool caps concurrent connections from an application instance to the database. When all connections are borrowed, new requests must wait or fail once the acquisition timeout expires.

Rising pool wait can be caused by:
- Traffic/concurrency exceeding current capacity.
- Queries or transactions holding connections too long.
- Connection leaks or code failing to close resources.
- Slow database keeping connections from being returned quickly.
- Pool size too small for the workload.
- Multiple replicas sharing the database's connection limit.

Do not assume a larger pool is always better. Increasing pool size raises the concurrent sessions the database must serve, which can drive up DB CPU, lock contention, and memory pressure.

## 3. Defining exact time intervals

A single repository call can span multiple stages. To avoid summing or comparing mismatched numbers, standardize the boundaries:

| Interval | Starts | Ends | Includes |
| --- | --- | --- | --- |
| Pool acquisition | Calling to get connection | Connection granted or timeout | Pool wait, possibly connection creation depending on metric |
| Connection creation | Beginning to open physical connection | Connection ready | DNS/TCP/TLS/authentication depending on driver |
| Statement execution | Sending/executing statement | Driver reports execution/result ready per API | Network and DB processing per driver semantics |
| Result consumption | Starting to read rows | Rows fully consumed | Data transfer, decoding/mapping depending on measurement |
| Repository duration | Entering method | Method return/error | Queries and application code inside |
| Transaction duration | Begin | Commit/rollback | Multiple statements and gaps between them |

Drivers differ in semantics. JDBC `executeQuery()` can return a `ResultSet` before all rows are read; with streaming or fetch sizes, result consumption time can extend past the execute call. R2DBC publishers may only execute when subscription and completion occur.

**Query time is not a single unambiguous concept until its boundary is defined.** Name metrics and spans accurately for what they actually measure.

## 4. Numerical example: slow repository yet fast query

Suppose a request shows these measurements:

~~~text
Repository duration       = 820 ms
Pool acquisition wait     = 690 ms
Query execution           = 95 ms
Result mapping            = 25 ms
Other application work   = 10 ms
~~~

The illustrative parts sum to 820 ms. Pool wait accounts for most of the time; adding an index would at best shave 95 ms of query execution without fixing the primary cause.

Another request:

~~~text
Repository duration       = 850 ms
Pool acquisition wait     = 5 ms
Query execution           = 810 ms
Result mapping            = 35 ms
~~~

Here the pool is not the bottleneck. Investigate query plans, lock waits, DB load, network, and row counts.

Not every instrumentation yields components that sum cleanly to repository duration. The example above is an analytical model; verify whether your actual timers overlap or omit any stages.

## 5. HikariCP metrics in Spring Boot

When Actuator and Micrometer are properly configured, HikariCP can provide pool metrics. Common meters describe:

| Metric group | Meaning |
| --- | --- |
| Active connections | Connections currently borrowed |
| Idle connections | Connections currently idle |
| Maximum connections | Pool upper limit |
| Minimum connections | Configured minimum idle target |
| Pending threads | Threads waiting for a connection |
| Connection acquisition | Time waiting for a connection, depending on binder/version |
| Connection usage | Time a connection is in use, depending on binder/version |

Exact meter/tag names depend on Spring Boot, Micrometer, and pool versions. Check the Actuator metrics endpoint or registry rather than guessing names.

Example Actuator exposure configuration in a dev environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Expose only needed endpoints and protect them with security/network policies. Do not open metrics endpoints publicly just to debug the pool.

## 6. Reading pool saturation from metrics

A pool shows signs of saturation when active connections stay near maximum and pending threads increase. However, a single snapshot is insufficient; observe trends over time alongside workload.

Indicators:

- Active stays near maximum for an extended period.
- Idle is 0 or near 0.
- Pending threads increase.
- Acquisition latency p95/p99 increases.
- Connection timeout count increases.
- Usage duration rises abnormally.

Example:

~~~text
maximum = 20
active  = 20
idle    = 0
pending = 35
~~~

This signals many requests are contending for connections. Underlying causes may be slow queries, long transactions, lock waits, or an undersized pool; pending alone does not prove maximum needs to be increased.

### 6.1. Distinguishing saturation from connection leaks

Saturation can stem from legitimate high load, whereas a leak means connections are not returned properly. Both can keep active high and drive up pending.

Suspected leak signs:
- Active connections climb steadily and do not drop after traffic subsides.
- Some connections are held abnormally long.
- Hikari leak detection warns connections have been borrowed beyond threshold.
- Thread dumps reveal code paths failing to close resources or hung transactions.

The leak detection threshold is a diagnostic tool, not an automatic leak-fixing mechanism. Setting it too low triggers false alarms on legitimate long transactions.

## 7. Where is query time measured?

Query time can be observed at several layers:

1. Database-native statement statistics/slow query logs.
2. JDBC driver or DataSource instrumentation.
3. OpenTelemetry JDBC instrumentation/Java agent.
4. Micrometer Observation/Tracing integration.
5. Custom timers around repository/service methods.

Each layer has different boundaries and overhead. For instance, a custom `Timer` around a repository method usually includes pool wait and mapping, whereas a driver span may focus on statement execution.

~~~java
@Repository
public class OrderRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Order findById(long id) {
        return jdbcTemplate.queryForObject(
                "select id, status from orders where id = ?",
                (rs, rowNum) -> new Order(
                        rs.getLong("id"),
                        rs.getString("status")),
                id);
    }
}
~~~

To measure true query time, prefer JDBC/driver/DataSource instrumentation with documented semantics. Do not wrap a repository method with a timer and name it database execution time if it includes acquisition and application processing.

## 8. JDBC and R2DBC: differences in pool wait and query timing

### 8.1. JDBC

JDBC typically uses blocking calls. Acquiring a connection usually happens during `DataSource.getConnection()`. Statement execution and `ResultSet` consumption have relatively distinct API milestones, though still subject to driver/fetch behavior.

A synchronous repository call may hold a connection for the entire transaction or method. If a thread waits for a connection, it is also occupied during pool wait.

### 8.2. R2DBC

R2DBC uses reactive publishers. Connection acquisition and query execution usually occur upon subscription. Measuring publisher creation time measures neither pool wait nor database execution.

~~~java
Mono<Order> order = connectionFactory.create()
        .flatMap(connection ->
                executeQuery(connection, orderId)
                    .doFinally(signal -> connection.close()));
~~~

This conceptual snippet must be implemented per the specific API/driver; closing a connection in R2DBC is typically a publisher operation that must be composed properly. Use Spring `DatabaseClient` or an appropriate transaction manager instead of manual connection management lacking lifecycle guarantees.

In both JDBC and R2DBC, measure acquisition and database operations separately to isolate bottlenecks.

## 9. Transactions holding connections longer than queries

A transaction can run fast queries while holding a connection as application code performs extra work.

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    inventoryRepository.reserve(command.items());
    validateBusinessRules(command);
    pricingService.calculate(command);
    orderRepository.save(command);
}
~~~

If `validateBusinessRules` or `pricingService` does slow work inside the transaction, the connection remains held. Under high concurrency, pool wait rises even though individual SQL statements are fast.

Guidelines:
- Keep transactions as short as possible while preserving atomicity.
- Avoid calling HTTP dependencies inside a DB transaction unless necessary.
- Do not sleep or process large files while holding a connection.
- Check transaction propagation and nested calls.
- Measure transaction duration separately from statement duration.

Do not move logic outside a transaction if doing so breaks consistency. Define business boundaries clearly and evaluate outbox/saga or appropriate consistency patterns when transactions span multiple systems.

## 10. Lock waits increase query time and occupy the pool

A query waiting on a lock still holds its connection in many cases. Database lock contention can therefore cause both high query latency and pool saturation.

~~~mermaid
flowchart TD
  A["Transaction A holds row lock"] --> B["Transaction B executes UPDATE"]
  B --> C["B waits for lock"]
  C --> D["Connection B remains occupied"]
  D --> E["Pool has fewer free connections"]
  E --> F["Other requests wait for pool"]
  C --> G["Query / transaction latency rises"]
  F --> H["Pool acquisition latency rises"]
~~~

When both query time and pool wait time increase, do not jump to pool size as the root cause. The database may be holding connections due to lock waits or slow queries. Inspect database wait events, blocking sessions, transaction ages, and query plans.

## 11. Pool size and system-wide connection budgets

Pool size must be calculated across all replicas, not a single process.

Example:
- 6 replicas of `order-service`, each with pool max 20: up to 120 connections.
- 4 replicas of `inventory-service`, each with pool max 15: up to 60 connections.
- Other services also consume the connection budget.

~~~text
Potential application connections
  = sum(replicas(service) * pool_max(service))
~~~

This total must fit within the database connection budget, leaving room for migrations, monitoring, admin sessions, autoscaling spikes, and other applications.

Do not raise pool size just to drive pending to 0. The database may saturate at fewer connections than the summed pool max. Benchmark concurrency and monitor DB CPU, I/O, lock waits, throughput, and latency together.

## 12. Query time, pool wait, and trace waterfalls

A good trace shows where database operations sit within a request. However, pool acquisition appears separately only if instrumentation supports measuring it. Otherwise, a DB span may include pool wait or cover only execution depending on integration.

~~~text
orders.create [INTERNAL]                    900 ms
  acquire connection                        650 ms  (if instrumented separately)
  SELECT order_items [CLIENT / DB]            80 ms
  INSERT orders [CLIENT / DB]                 40 ms
  result mapping / application work          130 ms
~~~

When reading traces:
- Check span start/end semantics.
- Check whether a dedicated span exists for pool acquisition.
- Compare DB spans against Hikari metrics.
- Do not mechanically sum nested span durations.
- Inspect transaction/repository spans if present.

If the DB span takes only 80 ms while the repository takes 800 ms, the gap may be pool wait, mapping, or application work. Pool metrics help distinguish them.

## 13. Metrics and percentiles for pool wait/query time

Use histograms/timers to observe distributions rather than averages alone. Illustrative custom metric names:

~~~text
app.db.pool.acquire
app.db.statement.duration
app.db.repository.duration
app.db.transaction.duration
~~~

These metrics should be placed at exact instrumentation boundaries without duplicating existing automatic meters. Use percentiles/histograms for p50/p95/p99 and counts for throughput.

Never use high-cardinality labels such as SQL text, bind values, connection IDs, thread names, or request IDs. Useful dimensions are typically DataSource name, `db.system`, operation group, and outcome.

Example dashboard table:

| Panel | Metric | Question |
| --- | --- | --- |
| Pool acquisition p95 | Pool wait timer | How long do requests wait for connections? |
| Statement p95 | DB statement timer | Is query execution slow? |
| Active/idle/pending | Pool gauges | Is the pool saturated? |
| Connection usage p95 | Usage timer | Are connections held too long? |
| Transaction duration | Transaction timer | Are transactions too long? |
| DB lock waits | Database-native telemetry | What resource are queries waiting on? |

## 14. Timeouts and failures in pool acquisition

If a connection cannot be acquired within the acquisition timeout, a repository call can fail before any SQL is sent. This is not a query timeout even though the exception surfaces inside repository code.

HikariCP can throw an acquisition timeout error after waiting past `connectionTimeout`. Exception names/messages and wrapping depend on versions. Distinguish:
- Pool acquisition timeout: failed to borrow a connection.
- Driver connect timeout: opening a new physical connection timed out.
- Statement/query timeout: query started executing but exceeded deadline.
- Transaction timeout: transaction exceeded deadline.
- Application request timeout: caller exhausted overall budget.

Order timeouts sensibly so inner-layer failures surface before outer deadlines, without forcing one fixed set of numbers on every workload.

## 15. Inspecting in Spring Boot Actuator

The Actuator metrics endpoint lets you inspect meters and tag values in secured environments.

Example endpoint queries:

~~~http
GET /actuator/metrics
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
~~~

The meter names above are common examples with the HikariCP binder; verify against your application's actual meter list and version. Some pool metrics may not appear if the DataSource/pool binder is not registered.

Check:
- active, idle, max, min.
- pending/waiting.
- acquisition/usage metrics if available.
- query timers or DB spans.
- tags per DataSource/pool name.

Never expose metrics endpoints to the public internet. Use authentication, network restrictions, or a dedicated management port.

## 16. Troubleshooting by combined patterns

| Pool wait | Query time | Likely cause | Investigation direction |
| --- | --- | --- | --- |
| High | Low | Pool saturation, transaction holding connection, leak | Pending/active, usage duration, transaction age |
| Low | High | Query plan, locks, DB load, network | Slow queries, EXPLAIN, wait events |
| High | High | DB overload, lock contention, undersized pool, or multiple factors | DB health, pool, concurrency, transactions |
| Low | Low yet high repository | Mapping/application logic or many queries | CPU profile, query count, traces |
| Spikes suddenly after deploy | Pool config or transaction regression | Compare versions/config/traffic |
| Acquisition timeout, no DB span | Failed to get connection so statement never ran | Pool metrics and connection budget |

### Investigation workflow

1. Select the service, DataSource, and time window.
2. Inspect pool active/idle/pending/max.
3. Check acquisition latency p95/p99.
4. Compare query/statement latency with repository duration.
5. Inspect transaction duration, lock waits, and connection usage.
6. Determine request concurrency and total replicas.
7. Check for connection leaks and resource cleanup.
8. Change one variable, run a load test under identical conditions, and compare.

## 17. Real-world scenario: pool wait rises after traffic doubles

**Scenario:** `order-service` runs 5 replicas. After traffic doubles, p95 repository duration rises from 90 ms to 720 ms. DB statement p95 remains around 35 ms. Hikari active stays near maximum and pending climbs.

### Step 1 — separate the timings

Traces/repository timers show a large gap before statements run. Pool metrics confirm rising acquisition waits. Query execution shows no clear regression.

### Step 2 — inspect connection usage

Connection usage duration rises from 50 ms to 600 ms. A transaction calls a pricing service over HTTP while holding the DB transaction open. Connections remain held during network waits.

### Step 3 — review total connection budget

Pool max 20 across 5 replicas creates up to 100 potential connections. The DB has a limited connection budget shared with other services. Do not raise pool size without assessing database capacity.

### Step 4 — shorten the transaction

Move the remote HTTP call outside the transaction if business consistency allows, keeping the transaction strictly around DB operations requiring atomicity. If coordination across systems is needed, evaluate outbox/saga or an appropriate consistency pattern.

### Step 5 — verify

Re-run load tests at the same concurrency. Compare acquisition p95, usage duration, pending, query p95, transaction duration, DB CPU, and request latency.

**Expected outcome:** pool wait drops because connections return earlier; query time remains steady; pool is not enlarged past the connection budget.

## 18. Hands-on exercises and self-check questions

### Exercise A — separate the two timers

Build a repository call with simulated pool wait and a slow query. Collect acquisition time, statement duration, and repository duration. Explain what each metric includes.

### Exercise B — induce pool saturation

Configure a small pool in a test environment, send concurrent requests, and hold connections briefly. Observe active, idle, pending, acquisition latency, and timeouts. Never run this test on a production database.

### Exercise C — simulate a slow query

Create a test query with a poor plan or controlled lock wait. Observe the query timer and pool wait. Confirm a slow query can drive up pool wait for other requests.

### Exercise D — transaction holding a connection

Place a simulated remote call inside a transaction. Measure connection usage and transaction duration. Then extract the remote call where semantics permit and compare.

### Exercise E — connection budget

Sum maximum pool sizes across replica counts for all services. Compare against database max connections, admin reserves, and migration/monitoring needs. Propose safe limits.

### Exercise F — traces and metrics

Enable JDBC instrumentation and Hikari metrics. Trigger requests with fast queries yet long pool waits. Determine whether trace spans isolate acquisition separately; cross-check with pool metrics.

### Self-check questions

1. Which stage does pool wait time measure?
2. How does query execution time differ from result consumption?
3. Why is repository duration not synonymous with statement duration?
4. What do active=max and rising pending suggest?
5. How does a connection leak differ from traffic-driven saturation?
6. Why can increasing pool size overload the database further?
7. How do JDBC and R2DBC differ in acquisition/execution lifecycles?
8. How can a long transaction increase pool wait even with fast queries?
9. How can lock contention affect both query time and pool wait?
10. When a pool acquisition timeout occurs, has the SQL statement necessarily executed?
11. How do you distinguish a pool timeout from a statement timeout?
12. Why is a connection budget needed across all replicas?
13. Does a trace DB span always isolate pool acquisition separately?
14. Which metrics should be read alongside acquisition latency?
15. How do you verify a pool/transaction change genuinely improved the system?

**Completion criteria:** accurately define pool wait/query/repository/transaction durations; read Hikari metrics; distinguish saturation, leaks, locks, and query regressions; understand JDBC/R2DBC lifecycles; calculate connection budgets; correlate traces and metrics; validate under controlled load.

## 19. Key takeaways

- Pool wait time is time spent waiting for a connection; query time is database operation duration within an instrumentation boundary.
- Repository duration can include pool wait, multiple queries, mapping, and application code.
- Hikari active near max, low idle, rising pending, and high acquisition p95 indicate pool pressure, not automatically that the pool should be enlarged.
- Slow queries/transactions hold connections longer and indirectly drive up pool waits.
- Separate acquisition, statement execution, result consumption, repository, and transaction durations.
- Blocking JDBC and reactive R2DBC have different lifecycles; measure at the right subscription/execution boundaries.
- Calculate connection budgets by summing replicas times pool maximum system-wide, reserving capacity for DB and operations.
- Never enlarge pools blindly; inspect DB capacity, lock waits, connection usage, and concurrency.
- Use Actuator/Hikari metrics together with DB spans, slow query logs, and database-native wait telemetry.
- Run controlled load tests comparing identical workloads before and after changes.

## References

- [Spring Boot Reference — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Micrometer — JVM and Datasource Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry Semantic Conventions — Database](https://opentelemetry.io/docs/specs/semconv/database/)
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
