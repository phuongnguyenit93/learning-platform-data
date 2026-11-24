# Relationship Between Thread Pools, Connection Pools, and Concurrency Capacity

## 1. Learning objectives

A Spring Boot application can receive many concurrent HTTP requests yet respond slowly even when CPU is mostly idle. The cause often lies in limits on shared resources: **worker threads**, **database connections**, **queues**, resource hold times, and backend service capacity.

After this lesson, you should be able to explain:

- What a thread pool manages, what a connection pool manages, and why the two pools **do not share the same unit of measurement**.
- How a synchronous HTTP request in Spring MVC/Tomcat can hold a thread while waiting for a JDBC connection, and what happens when either pool is exhausted.
- Why increasing thread count or connection count does not automatically raise throughput and can even slow the system down.
- How to estimate concurrency needs using processing time and Little's Law, spot bottlenecks from metrics, run load tests, and tune with verification.
- Differences between servlet blocking, async processing, virtual threads, and WebFlux from a resource perspective.

The primary scope is **Spring Boot Web MVC with embedded Tomcat and HikariCP/JDBC**. Principles regarding queues and finite resources also apply to connection pools for HTTP services or Redis, though each pool type operates differently.

## 2. Three concepts to keep separate

| Component | Managed resource | Role | When limit is reached |
| --- | --- | --- | --- |
| Tomcat **HTTP worker thread pool** | Threads executing HTTP request work | Runs controllers, services, blocking calls | Requests may wait in accept/queue mechanisms or be rejected when upstream limits fill |
| **JDBC connection pool** (commonly HikariCP) | Open reusable connections to the database | Leases connections for queries/transactions | `getConnection()` may **wait** up to `connectionTimeout`, then throw `SQLException` if none is available |
| **HTTP client connection pool** | Network connections from app to external services | Reuses outbound connections with library-specific limits | May wait for a slot, open a new connection, or fail depending on library and config |

**A thread is not a connection.** A thread can handle HTTP without querying a database. A single request may borrow and return multiple connections sequentially. A JDBC connection can be reused by different requests **over time**, yet at any instant a leased connection is unavailable to other requests.

“Thread pool” here refers to a **thread pool/executor**. Java has `java.lang.ThreadGroup`, which is **not** the resource coordinator discussed in HTTP thread-pool tuning.

Distinguish three meanings of “connection”:

1. **Inbound HTTP connection**: socket between client/proxy and Tomcat; HTTP keep-alive can keep the socket open when no request is running.
2. **JDBC connection**: connection from the application to the database, leased by the pool.
3. **Outbound HTTP connection**: socket from the application to another API, managed by the HTTP client.

An idle HTTP keep-alive socket **does not mean** a Tomcat worker thread is held continuously. With HTTP/2, the relationship between connections and requests also involves multiplexing. Never equate `max-connections` with `threads.max` or `hikari.maximum-pool-size`.

## 3. How does a synchronous request traverse resources?

Consider a Spring MVC endpoint calling JDBC synchronously:

~~~text
Client
  |
  | HTTP connection
  v
Reverse proxy / Tomcat connector
  |
  | Pick worker thread for request
  v
Spring MVC: Controller -> Service
  |
  | dataSource.getConnection()
  +--> Does HikariCP have a free connection?
       | Yes
       |   v
       | Database query / transaction
       |   |
       |   v
       | close() -> RETURN connection to pool
       |
       ' No
           |
           | Worker thread keeps waiting in getConnection()
           | (bounded by connectionTimeout)
           v
       Connection acquired -> continue
       Timed out -> SQLException
  |
  v
Write response -> release worker thread
~~~

Key takeaway: inside a **blocking** controller, when `getConnection()` waits because the pool is exhausted, **the servlet thread usually remains occupied** throughout that wait. Thus a bottleneck in the JDBC pool can cascade into the HTTP thread pool. Clients observe slow responses, yet raising `threads.max` may simply leave **more threads waiting** if the database cannot process more work.

Example for a single request:

- HTTP parsing/handling before query: 20 ms, holding a worker thread, no JDBC connection yet.
- Waiting for a connection: 150 ms, **holding a worker thread**, still no connection.
- Querying and holding the connection: 80 ms, **holding both a worker thread and a JDBC connection**.
- Building and writing the response: 10 ms, still holding a worker thread; connection already returned if closed promptly.

Total response time is nearly 260 ms, yet JDBC connection occupancy is only 80 ms. The two pools have **different occupancy durations**, so you cannot size them by setting them equal.

Actual timing depends on transaction boundaries and when connections are acquired/released. With pooled JDBC connections, `Connection.close()` normally **returns the connection to the pool** rather than closing the underlying TCP socket immediately. If code leaks connections or holds transactions open unnecessarily, slots stay occupied and queues grow.

## 4. Concurrency limits apply stage by stage

Suppose a Spring Boot instance is configured with:

- Tomcat max **12** standard worker threads.
- HikariCP max **3** JDBC connections in the pool.
- The database can handle three concurrent queries in the experiment, ignoring other resources for now.

If **12 synchronous requests** arrive nearly simultaneously and all require a JDBC connection:

| Illustrative moment | Workers serving requests | JDBC connections leased | Requests waiting for JDBC |
| --- | ---: | ---: | ---: |
| Right after requests reach JDBC (assuming workers are created) | 12 | 3 | 9 |
| After first three requests return connections | Up to 12 | Up to 3 | Decreasing |
| Once all finish | 0 | 0 leased | 0 |

This is an **illustrative scenario**, not a guarantee of scheduling, socket counts, or exact timing. Tomcat may ramp up workers gradually; requests may arrive unevenly, time out, or take branches that skip the database.

When the connection pool has only three slots, at most three requests in **that instance** can hold connections simultaneously. That is not a limit of “only three HTTP requests running”: remaining requests can run non-DB logic, wait for connections, or sit in another queue. Conversely, raising the pool to 30 does not guarantee 30 useful parallel queries if the database only has enough CPU, I/O, or locks to serve a few fast queries at a time.

Stage-by-stage view:

~~~text
HTTP arrival
  -> [Tomcat worker: processing time + wait time]
  -> [DB pool: wait for slot -> hold connection -> return slot]
  -> [Database: CPU / I-O / locks / network]
  -> [Response]
~~~

**Throughput** is measured in completed requests/second; **concurrency** is the amount of work in progress at the same instant; **latency** is how long each request waits until completion. These are three distinct numbers.

An instance also faces external bounds: the database's max allowed connections, load from other instances, downstream API connection limits, CPU cores, memory, locks, and network. Bottlenecks shift as load rises.

## 5. Little's Law: estimate demand, do not pick “pretty numbers”

In a relatively stable system, Little's Law states:

\[
L = \lambda W
\]

Where `L` is the average number of items **inside the measured scope**, `λ` is average throughput (items/second), and `W` is the average time an item stays within that scope (seconds).

Be consistent about **scope**:

- Measuring all requests inside the application: `L_request ≈ RPS × response_time`, including wait times.
- Measuring only **currently leased** JDBC connections: `L_db_lease ≈ connection_leases_per_second × avg_hold_time`. Do not add wait time **before** acquisition into connection hold time.
- If a single request borrows a connection multiple times, leases/second **differs** from requests/second.

**Back-of-the-envelope example:** a system steadily completes 60 requests/second; each request uses JDBC once for 100 ms (= 0.1 s) on average. Average **leased connection demand** is roughly:

\[
60\ \text{request/s} \times 0{,}1\ \text{s/request} = 6\ \text{connections}
\]

A three-connection pool cannot sustain that **same** 60 leases/second rate if each lease truly holds a connection for 0.1 s on average with nothing else changing the math. Yet sizing the pool solely to the average of six can still fall short during traffic bursts, query-time variance, or database locking. At the same time, pool growth must stay bounded by database capacity and total instances.

Suppose average response time is 300 ms under synchronous servlet processing: average requests inside the system are near `60 × 0.3 = 18`. That number 18 is **not equivalent** to “exactly 18 worker threads are required” across all architectures: queues, async handling, keep-alive, and I/O models all affect how many threads are actually busy.

Do not treat the formula as a promise about p95/p99 or an optimal slot count. Little's Law describes **steady-state averages**; sustained overload causes queues to grow, wait times to climb, and short-window measurements to mislead.

## 6. Spring Boot 3.x / Java 17+ lab: two pools with different sizes

Create a Maven project via Spring Initializr with **Java 17 or newer**, **Spring Boot 3.x**, and dependencies:

- **Spring Web** (`spring-boot-starter-web`): Spring MVC and embedded Tomcat.
- **JDBC API** (`spring-boot-starter-jdbc`): JDBC and default HikariCP in typical setups.
- **H2 Database** (`com.h2database:h2`): in-memory database for the lab.

Keep dependency versions managed by Spring Initializr. This example is standalone; no Spring Data JPA or external database server is needed. File structure:

~~~text
src/main/java/com/example/poollab/
  PoolLabApplication.java
  PoolLabController.java
src/main/resources/
  application.properties
load-test/
  LoadClient.java
~~~

### 6.1. Configuring two distinct limits

**`src/main/resources/application.properties`**

~~~properties
server.port=8080

# Experiment: maximum 12 Tomcat worker threads
server.tomcat.threads.max=12
server.tomcat.threads.min-spare=4

# JDBC pool: maximum 3 connections
spring.datasource.url=jdbc:h2:mem:poollab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=3
spring.datasource.hikari.connection-timeout=2000
~~~

`server.tomcat.threads.max` applies to standard Tomcat worker threads; it is **not** the Hikari pool size. `spring.datasource.hikari.maximum-pool-size` caps total **idle + active** JDBC connections in the pool. `connection-timeout=2000` sets the maximum wait to borrow a connection to 2,000 ms; upon expiration Hikari throws `SQLException`. Do not confuse this property with SQL execution timeout or HTTP timeout.

Small numbers are used **to make contention easy to observe in the lab**, not as recommended production settings. This Tomcat setting also behaves differently when virtual threads are enabled.

### 6.2. Application entry point

**`src/main/java/com/example/poollab/PoolLabApplication.java`**

~~~java
package com.example.poollab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PoolLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolLabApplication.class, args);
    }
}
~~~

### 6.3. Two endpoints with identical sleep durations but different resource usage

**`src/main/java/com/example/poollab/PoolLabController.java`**

~~~java
package com.example.poollab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/lab")
public class PoolLabController {
    private final HikariDataSource dataSource;

    public PoolLabController(HikariDataSource dataSource) {
        this.dataSource = dataSource;
    }

    // Hold a servlet worker for ~400 ms,
    // WITHOUT acquiring a JDBC connection.
    @GetMapping("/no-db")
    public String noDb() throws InterruptedException {
        Thread.sleep(400);
        return "no-db";
    }

    // Acquire a connection, run SQL, then INTENTIONALLY HOLD
    // the connection for 400 ms more to simulate a slow DB step.
    @GetMapping("/db")
    public String withDb() throws SQLException, InterruptedException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
             ResultSet result = statement.executeQuery()) {
            result.next();
            int value = result.getInt(1);
            Thread.sleep(400);
            return "db=" + value;
        }
    }

    // Read pool status; call /lab/db at least once
    // before reading so Hikari initializes the pool.
    @GetMapping("/pool")
    public PoolState pool() {
        HikariPoolMXBean bean = dataSource.getHikariPoolMXBean();
        if (bean == null) {
            return new PoolState(0, 0, 0, 0);
        }
        return new PoolState(
                bean.getActiveConnections(),
                bean.getIdleConnections(),
                bean.getTotalConnections(),
                bean.getThreadsAwaitingConnection()
        );
    }

    public record PoolState(
            int active, int idle, int total, int waiting
    ) {}
}
~~~

Both endpoints use `Thread.sleep(400)` and therefore **hold the worker thread** while sleeping. The difference is:

- `GET /lab/no-db`: does not borrow a JDBC connection; the bottleneck in this lab is primarily worker threads and other overhead.
- `GET /lab/db`: borrows a connection before sleeping, so at most three requests can hold connections concurrently; other requests reaching `getConnection()` wait.
- `GET /lab/pool`: inspects `active` (currently leased), `idle` (free), `total`, and `waiting` (threads waiting to borrow). These numbers are an **instantaneous snapshot** that can change right after the response; once load stops, `active` normally returns to 0.

**Important lab warning:** deliberately sleeping while holding a connection is **for simulation only**. In real applications, keep connections and transactions as brief as reasonable, avoiding network API calls, sleeps, or heavy CPU work while a transaction holds a connection. `try-with-resources` guarantees returning the resource to the pool at block exit, even on exceptions.

Run from the Maven project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Verify a single request (in another terminal):

~~~bash
curl -s http://localhost:8080/lab/db
curl -s http://localhost:8080/lab/no-db
curl -s http://localhost:8080/lab/pool
~~~

The first two responses have exact bodies:

~~~text
db=1
no-db
~~~

The `/lab/pool` response is JSON with `active`, `idle`, `total`, and `waiting`. Exact numbers vary by timing; do not copy one snapshot as a fixed expected output.

### 6.4. Sending nine concurrent requests with Java 17

Place the following **standalone** program at `load-test/LoadClient.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class LoadClient {
    public static void main(String[] args) {
        String endpoint = args.length == 0 ? "db" : args[0];
        if (!endpoint.equals("db") && !endpoint.equals("no-db")) {
            System.err.println("Choose endpoint: db or no-db");
            return;
        }

        HttpClient client = HttpClient.newHttpClient();
        URI uri = URI.create("http://localhost:8080/lab/" + endpoint);
        List<CompletableFuture<String>> pending = new ArrayList<>();

        long batchStart = System.nanoTime();
        for (int index = 1; index <= 9; index++) {
            final int requestNumber = index;
            long start = System.nanoTime();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();

            pending.add(client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString()
            ).handle((response, error) -> {
                long ms = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - start
                );
                if (error != null) {
                    return requestNumber + ": ERROR "
                            + error.getClass().getSimpleName()
                            + " (" + ms + " ms)";
                }
                return requestNumber + ": HTTP "
                        + response.statusCode()
                        + " " + response.body()
                        + " (" + ms + " ms)";
            }));
        }

        CompletableFuture.allOf(
                pending.toArray(new CompletableFuture[0])
        ).join();

        for (CompletableFuture<String> result : pending) {
            System.out.println(result.join());
        }
        long totalMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - batchStart
        );
        System.out.println("Total: " + totalMs + " ms");
    }
}
~~~

This is a standard Java program **with no Spring dependencies**. It launches nine asynchronous HTTP requests, captures each status and elapsed time, and waits for all nine. Run inside `load-test`:

~~~bash
javac LoadClient.java
java LoadClient no-db
java LoadClient db
~~~

For cleaner comparisons, hit both endpoints once before measuring to reduce lazy-initialization effects; run multiple iterations and inspect medians/p95 for serious measurements.

**Mechanism-based predicted outcome**, not fixed timed stdout:

- For `no-db`, all nine requests can sleep concurrently on available workers and finish in roughly one 400 ms wave plus HTTP/thread-startup overhead.
- For `db`, only three requests hold a JDBC connection at once. If all nine arrive fast enough and each holds a connection for 400 ms, they tend to complete in **three waves**, totaling roughly `3 × 400 ms = 1,200 ms` plus overhead.
- If you increase request count, hold duration, or add external load, requests can wait past `connectionTimeout`. Code then receives `SQLException`; the HTTP status depends on exception handling (defaulting to 500), **not automatically 429 or 503**.

Observed timings alone do not prove “Spring has a bug” or “DB is broken” without queue and resource metrics. OS scheduling, H2, sockets, connection initialization, JIT, GC, and host capacity all shift timings.

## 7. Queues and cascading congestion

There can be **multiple waiting points**:

1. Before a request obtains a worker thread or begins application handling, depending on connector, socket limits, backlog, proxies, and load balancers.
2. Inside the application when a synchronous worker waits on `getConnection()`.
3. At the database when many queries contend for CPU, I/O, locks, or other resources.
4. When calling downstream HTTP services or reading/writing network data.

When arrival rate exceeds completion rate for an extended period, queues grow. p95/p99 latency usually degrades before most requests fail. Client-side timeouts may fire **before** `connectionTimeout` or server completion, triggering retries that add even more load.

Amplification loop example:

~~~text
Slow DB -> holds connections longer
       -> Hikari active hits limit, pending rises
       -> servlet workers wait on getConnection()
       -> new requests stall at HTTP layer
       -> client timeouts / retries
       -> more requests -> worse congestion
~~~

With mixed workloads, one slow-DB endpoint can slow down other endpoints by exhausting **shared HTTP workers**, even when those other endpoints never touch the database. That is why load limits, timeouts, and sometimes resource/workload isolation are necessary.

Never use **total open connections** as a direct proxy for throughput: idle connections count toward `total`, and slow queries can keep `active` high while completed queries stay low.

## 8. Reading metrics to identify the true bottleneck

In real projects, enable **Spring Boot Actuator** and a suitable metrics/tracing stack; inspect the exact meter names and tags available for your version and environment. Useful signals include:

| Signal | What you want to know | Caution in interpretation |
| --- | --- | --- |
| Tomcat busy/current threads | How many workers are busy vs. available/max | Sustained high busy count plus high latency suggests contention or blocking inside workers |
| Hikari active connections | How many JDBC connections are leased | Active near max continuously is only a clue; inspect pending count and hold time |
| Hikari idle connections | Whether free connection slots exist | `idle=0` does not prove a problem if `pending=0` and throughput is healthy |
| Hikari pending / awaiting connections | How many threads are waiting to borrow | Rising pending plus high acquisition time is strong evidence of pool contention |
| Connection acquisition time / timeouts | How long borrowing a connection takes | Do not confuse acquisition wait with SQL execution duration |
| SQL/transaction duration, DB CPU/I-O/locks | Is the DB keeping up or locking? | Enlarging the pool when the DB is already saturated usually makes things worse |
| HTTP RPS, status, p50/p95/p99 | What response times and errors users see | Break down by endpoint and request type; avoid relying only on averages |

Depending on Micrometer/Actuator configuration, you may see names like `hikaricp.connections.active`, `hikaricp.connections.pending`, `tomcat.threads.busy`, and `http.server.requests`; Tomcat metrics also depend on instrumentation/MBean registration. **Never assume** every meter exists without checking your runtime environment.

In the lab, `/lab/pool` gives a snapshot illustrating the relationship between `active` and `waiting`. In production, collect periodic time-series metrics via monitoring rather than trying to catch a single instant manually.

## 9. Diagnostic scenarios and remediation

| Observed symptom | Hypothesis to verify | Action |
| --- | --- | --- |
| Hikari `active≈maximumPoolSize`, `pending>0`, acquisition time rising | Connection pool is the immediate wait point | Optimize queries/transactions, release connections sooner, check DB limits, then consider sizing pool |
| Tomcat workers nearly maxed, Hikari still has idle | Time spent in code/CPU, network, other locks, or non-JDBC blocking | Profile stacks/traces, separate CPU vs. blocking, inspect outbound pools and timeouts |
| Hikari active high, DB CPU/locks also high | DB cannot finish queries fast enough | Optimize indexes/queries, locks, transactions; cap concurrency, scale DB with verification |
| Many timeouts yet app CPU is low | Waiting on I/O, pools, or downstream | Measure per-stage waits and latency; do not conclude “we need more CPU” |
| Raising pool size fails to boost throughput and worsens p99 | Shifted bottleneck to DB or increased contention | Revert to better config, measure query/DB saturation, add backpressure thresholds |
| Overload only after scaling app instances | Combined JDBC connections across instances exceed DB budget | Sum pool sizes across replicas, reserve admin/maintenance slots, bound per instance |

**Controlled tuning workflow:**

1. Define targets: RPS, p95/p99, error rate, expected concurrency, and spike duration.
2. Measure per-stage baselines: JDBC acquisition wait, connection hold time, SQL duration, busy threads, DB utilization, and timeout errors.
3. Find the **actual** bottleneck. Fix slow queries, connection leaks, long transactions, or downstream calls inside transactions first.
4. Adjust **one relevant limit** in small, reasoned increments; measure under identical workload and replica count. Stop if throughput stops rising, p99 degrades, DB saturates, or errors increase.
5. Align timeouts and load shedding: HTTP/client deadlines, JDBC acquire timeout, query timeout, DB concurrency limits; avoid unbacked-off retry storms.
6. Verify total connection budget: with four replicas each having `maximumPoolSize=20`, the app **can** open up to 80 JDBC connections, excluding other services. The database must have connection headroom and processing capacity to match.

**Do not** infer a golden rule like `Tomcat maxThreads = Hikari maximumPoolSize`. An app serving mostly cached or non-DB requests may need more workers than DB connections; an app with tiny transactions cycles connections rapidly. Conversely, a huge connection pool on top of a slow database remains a poor configuration.

## 10. Do async, virtual threads, and WebFlux solve this?

**Synchronous (blocking) Spring MVC:** in standard controller execution, each active request holds a servlet worker. A JDBC call blocks that thread until results return or it times out. The lab above uses this model.

**Spring MVC async:** with `Callable`/`DeferredResult` and Servlet async, the initial servlet worker can be released while waiting for the result; `Callable` runs on another executor. Moving blocking work to another executor **does not make JDBC non-blocking**. You must still bound the executor, DB connections, and queued work. Moving where threads wait sometimes merely shifts the bottleneck to another pool.

**Virtual threads (Java 21+):** well suited to many blocking I/O tasks; they reduce the cost of holding a **platform thread** per request compared to traditional threading. Yet they do not create extra DB connections or speed up queries. With virtual threads, traditional worker-pool properties like `server.tomcat.threads.max` may no longer apply; you still need query/connection bounds, pinning observation, and real performance testing.

**Spring WebFlux:** uses event loops and non-blocking I/O when the entire pipeline is truly non-blocking. Reactor Netty uses event-loop threads and may maintain separate HTTP connection pools. Calling **blocking JDBC** directly on the event loop stalls handling of many connections; offloading blocking code to an appropriate scheduler protects the event loop yet **does not bypass** JDBC pool limits. With R2DBC, connection management and semantics differ from JDBC; never use Hikari properties to configure an R2DBC pool.

Thus choosing async, virtual threads, or reactive is an **execution-model decision**, not a substitute for database and downstream concurrency control.

## 11. Common misconceptions when reasoning about concurrency

1. **“200 threads means 200 parallel queries.”** False: not every request queries the DB; JDBC connections are bounded independently and the DB may handle fewer.
2. **“Hikari max 10 means only 10 users can be online.”** False: users/sessions, active requests, and leased JDBC connections are distinct concepts.
3. **“Increasing maxThreads to 1,000 makes things faster.”** Not necessarily: it can add waiting threads, context switching, memory overhead, and contention.
4. **“Increasing the connection pool always increases RPS.”** False when the DB is limited by CPU/I/O/locks or when multiple app replicas share one DB.
5. **“Calling `close()` tears down the physical connection so it's slow.”** On Hikari-leased connections, `close()` normally returns the connection to the pool for reuse and must be called promptly.
6. **“Every keep-alive socket holds a Tomcat request worker forever.”** False for standard non-blocking connectors; idle sockets and active requests are different.
7. **“Async/WebFlux/virtual threads eliminate all queues.”** False: downstream limits, timeouts, database capacity, and backpressure still apply.
8. **“Checking app CPU alone reveals the root cause.”** False: an app can sit idle on CPU while hundreds of threads block on DB/network/locks.
9. **“One load test with nice millisecond numbers is enough.”** False: warm-up, controlled workloads, multiple percentiles, and error tracking are needed to avoid optimizing on noise.

## 12. Self-check exercises

**Question 1.** Tomcat has 20 worker threads; the Hikari pool has 5 connections. Twenty synchronous requests all call `getConnection()`, and five have leased connections. What resources are the remaining fifteen requests holding?

**Question 2.** Why can `Hikari active=5` and `pending=12` alongside rising p99 also slow down endpoints that do not use the database?

**Question 3.** A service steadily completes 100 requests/s; each request leases a connection once and holds it for 40 ms on average. By Little's Law, how many connections are leased on average? Why is that number alone insufficient to finalize `maximumPoolSize`?

**Question 4.** An application runs three replicas, each configured with `maximumPoolSize=30`. Roughly how many concurrent JDBC connections can those replicas alone use at peak? When the DB starts overloading after scaling, what should you measure?

**Question 5.** Why does switching a controller that uses blocking JDBC to `Callable` or virtual threads still not allow a ten-connection pool to execute 100 queries simultaneously?

**Suggested answers:**

1. The fifteen requests do not hold connections; during a typical blocking wait, they still hold worker threads while waiting for Hikari to grant a slot or time out.
2. Many workers get blocked waiting on the DB, competing with other endpoints for workers; verify via busy threads, pool wait time, and traces.
3. `100 × 0.04 = 4` connections **on average**. Account for bursts, variance in hold times, DB capacity, other pools/replicas, and p99 targets.
4. `3 × 30 = 90` connections from configured budgets, excluding other services; measure active/pending, DB connection count, CPU/I/O, locks, SQL latency, and actual RPS.
5. Those models can lower worker/platform-thread overhead or move execution elsewhere, yet the pool still grants at most ten JDBC connections at a time.

## 13. References

- Spring Boot 3.3 — Common Application Properties (Tomcat, Hikari, R2DBC): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot — Data Access / SQL (connection pools and JDBC): https://docs.spring.io/spring-boot/docs/3.2.1/reference/htmlsingle/index.html
- HikariCP — configuring `maximumPoolSize`, `connectionTimeout`: https://github.com/brettwooldridge/HikariCP
- Spring Framework — Asynchronous Requests (Spring MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Java 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
