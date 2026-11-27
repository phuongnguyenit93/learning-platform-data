# Consistency levels and timeouts in Cassandra message flows

## 1. Why can a Cassandra write time out even after persisting data?

Suppose a payment service receives an `OrderPaid` event over JMS, converts it into a Spring `Message<OrderEvent>`, and sends it to a **Cassandra outbound channel adapter**. During one execution, a timeout occurs. The application does not know whether to retry or acknowledge the JMS message: retrying could duplicate writes, while skipping could lose a reconciliation record.

The issue is not simply "is Cassandra up?", but two separate questions:

1. **Consistency level (CL):** how many replicas must acknowledge before the Cassandra coordinator considers a read or write satisfied?
2. **Timeout:** how long is a layer willing to wait for that response, and which layer is enforcing the deadline?

A coordinator may have already forwarded the mutation to multiple replicas while the response back to the client was delayed or dropped. **A timeout is a lack of timely confirmation, not negative proof that the database remained unchanged.** Even when the driver throws an error, one or more replicas may have persisted the write; any retry still requires a stable business key and safe semantics.

In the **SPRING_INTEGRATION_ADAPTERS** module, learners integrate external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing flows across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. **Consistency levels and timeouts**, part of the **Adapter Cassandra** chapter, focuses on Cassandra read/write semantics when operations are triggered from Spring Integration message flows.

### Objectives

After this lesson, you will be able to:

1. Explain **replication factor**, coordinator, replicas, and CLs such as `ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`, `EACH_QUORUM`, and `ANY`.
2. Compute required acknowledgments for `RF=3`/`RF=5` and apply the `R + W > RF` overlap rule within the proper datacenter scope.
3. Understand when `SERIAL`/`LOCAL_SERIAL` applies in **lightweight transactions (LWT)** and avoid confusing it with regular read/write CLs.
4. Distinguish **driver request timeout**, **server-side read/write timeout**, **Spring Integration channel/gateway timeout**, and HTTP/JMS/Kafka deadlines.
5. Configure CL/timeouts via Java Driver 4.x, Spring Data `WriteOptions`/`QueryOptions`, and Spring Integration Cassandra DSL.
6. Classify `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, and `DriverTimeoutException`; decide when retries are safe.
7. Design idempotency, acknowledgments, backpressure, monitoring, and integration tests matching consistency/SLA requirements.

## 2. Architecture: where is data written and who waits on whom?

~~~mermaid
flowchart LR
    A["JMS/Kafka/HTTP inbound"] --> B["Spring Integration MessageChannel"]
    B --> C["CassandraMessageHandler"]
    C --> D["ReactiveCassandraOperations"]
    D --> E["Java Driver 4.x / CqlSession"]
    E --> F["Cassandra Coordinator"]
    F --> R1[("Replica 1")]
    F --> R2[("Replica 2")]
    F --> R3[("Replica 3")]
    R1 -. "ACK" .-> F
    R2 -. "ACK" .-> F
    R3 -. "ACK" .-> F
    F -. "Response or timeout" .-> E
~~~

| Concept | Responsibility | What must not be inferred |
|---|---|---|
| `MessageChannel` | Hands off a Spring Message to an endpoint | `send(true)` always means Cassandra saved the row |
| `CassandraMessageHandler` | Selects INSERT/UPDATE/DELETE/STATEMENT, invokes reactive operations; async or sync | Creates a distributed transaction across JMS/Kafka |
| `ReactiveCassandraOperations` | Entity mapping and executing Cassandra operations | Automatically selects optimal business CL |
| Driver `CqlSession` | Dispatches requests, retries, execution profiles, timeouts, and routing | Timeout means the server did nothing |
| Cassandra coordinator | Sends requests to replicas and awaits responses per CL | Must receive ACKs from every replica under `CL=ONE` |
| Replicas | Hold copies of a partition per replication strategy | A replica is equivalent to a Kafka partition/JMS queue |

**The coordinator does not have to be a replica for the target partition.** The driver normally tries to pick a token-aware coordinator, yet depending on network and routing config a request may be coordinated by another node.

### 2.1. Sequence of a `LOCAL_QUORUM` write

~~~mermaid
sequenceDiagram
    participant Flow as Spring Integration
    participant Driver as Java Driver
    participant Coord as Cassandra coordinator
    participant R1 as Replica A
    participant R2 as Replica B
    participant R3 as Replica C

    Flow->>Driver: INSERT eventId=evt-6001, CL=LOCAL_QUORUM
    Driver->>Coord: Execute CQL
    Coord->>R1: Mutation
    Coord->>R2: Mutation
    Coord->>R3: Mutation
    R1-->>Coord: ACK 1
    R2-->>Coord: ACK 2
    Coord-->>Driver: Success: 2/3 local replicas satisfied
    Driver-->>Flow: Completion
    R3-->>Coord: Late ACK
~~~

This diagram assumes **RF=3 in one local datacenter**. Cassandra may dispatch the write to **all replicas**, while CL dictates **how many responses the coordinator must wait for**. `CL=LOCAL_QUORUM` does not wait for the third replica before returning success to the client, but that does not mean the third replica never receives the mutation.

## 3. Replication factor and quorum: fundamental math

### 3.1. RF is the replica count in the replication strategy

**Replication factor (RF)** defines how many copies of each partition Cassandra aims to keep in a datacenter or per the keyspace strategy. For a multi-node test, a keyspace using `NetworkTopologyStrategy`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

This is an **example only when the cluster actually has datacenter `dc1` and enough nodes**. Never run RF=3 on a single-node test Cassandra instance expecting three independent replicas. On single-node Docker for learning CQL, RF=1 works, yet it **cannot reproduce 2/3 replica quorum or single-node fault tolerance**.

### 3.2. Quorum is a strict majority

For replication factor `RF`, quorum within that replica set is:

\[
Q = \left\lfloor\frac{RF}{2}\right\rfloor + 1
\]

| RF | ONE | QUORUM | ALL |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 2 | 1 | 2 | 2 |
| 3 | 1 | 2 | 3 |
| 4 | 1 | 3 | 4 |
| 5 | 1 | 3 | 5 |

For `LOCAL_QUORUM`, use the **local datacenter's RF** when calculating quorum, not the total RF across a multi-DC cluster. `QUORUM` normally considers the **entire keyspace's** replication factor (across datacenters per the replication strategy).

### 3.3. Intersection between read and write replica sets

In the classic quorum model, if **write** requires `W` responses and **read** requires `R` responses, the condition:

\[
R + W > RF
\]

ensures the two considered replica sets share **at least one common replica** when accessing **the same partition and replica set**. For RF=3:

| Write CL | W | Read CL | R | `R+W>3`? |
|---|---:|---|---:|---|
| ONE | 1 | ONE | 1 | **No** |
| ONE | 1 | QUORUM | 2 | **No**, equals 3 |
| QUORUM | 2 | QUORUM | 2 | **Yes**, equals 4 |
| ALL | 3 | ONE | 1 | **Yes**, equals 4 |
| ONE | 1 | ALL | 3 | **Yes**, equals 4 |

This inequality is a **tool for reasoning about quorum overlap**, not a universal promise that every query is linearizable. Cassandra uses timestamp-based conflict resolution and can experience concurrent writes, clock skew, tombstones, topology changes, and separate LWT read paths. When compare-and-set/serializable semantics within Cassandra's supported scope are required, evaluate **LWT** rather than just changing CL.

### 3.4. An important counterexample

~~~text
RF=3: replicas A, B, C

Write CL=ONE:
    A ACKs success; B and C have not applied yet.

Read CL=ONE:
    Coordinator reads B before B sees the new write.

Result:
    Read may return stale value even though the prior write succeeded.
~~~

With `QUORUM` reads and writes over the same three replicas, any two-replica subsets must overlap. However, if you **read from a different datacenter** than where a `LOCAL_QUORUM` write just returned success, the two local replica sets **do not have to overlap**; remote replication may not have arrived yet.

## 4. Consistency levels in Cassandra

| CL | Confirmation condition | Used for | Trade-off/warning |
|---|---|---|---|
| `ONE` | One replica responds | Reads/writes prioritizing latency and availability | Another replica read may miss recent writes |
| `LOCAL_ONE` | One replica in local DC responds | Workloads preferring the local DC | Does not guarantee latest read before convergence |
| `TWO` | Two replicas respond | Specific requirements | Depends on RF and topology |
| `THREE` | Three replicas respond | Specific requirements | Unsuitable if RF is insufficient |
| `QUORUM` | Majority of all replicas | Reads/writes needing keyspace-wide quorum overlap | Multi-DC incurs cross-WAN latency |
| `LOCAL_QUORUM` | Majority of replicas in local DC | Reads/writes homed in a single DC | No instant visibility guarantee in remote DCs |
| `EACH_QUORUM` | Quorum in **every** involved DC | **Writes** requiring local quorum in multiple DCs | Availability drops if any DC is unreachable |
| `ALL` | Every replica responds | Cases requiring ACKs from all replicas | Very sensitive to slow/failed replicas |
| `ANY` | One replica confirms or coordinator stores a hint | **Write-only** for extreme availability | Hints may not yet be readable at `CL=ONE` |

**`ANY` is valid only for writes.** When all replicas for a partition are unreachable, the coordinator can accept the mutation via **hinted handoff**. Success at `CL=ANY` **does not prove** any replica has stored the row or that a `ONE` read will immediately see it; never choose `ANY` when read-after-write is required.

**`EACH_QUORUM` is primarily for writes** in multi-DC replication strategies, not a common read CL. Do not equate it with cluster-wide `QUORUM`: e.g., with RF=3 in dc1 and RF=3 in dc2, `EACH_QUORUM` requires **2 ACKs in each DC**, whereas `QUORUM` across total RF=6 requires **4 responses cluster-wide** without requiring exactly two per DC.

### 4.1. SERIAL and LOCAL_SERIAL do not replace ONE/QUORUM

`SERIAL` and `LOCAL_SERIAL` provide **serial consistency** for Cassandra **lightweight transactions**, typically with `IF NOT EXISTS` or `IF version = ?`. They coordinate the consensus/compare-and-set phase within supported scope.

- `SERIAL` evaluates serial consensus across the applicable replica scope; may span multiple DCs.
- `LOCAL_SERIAL` restricts LWT consensus to the local datacenter.
- LWT still uses a **regular consistency level** for reading/writing the result, such as `LOCAL_QUORUM`.
- **Never set `SERIAL` as the regular CL of a plain INSERT** hoping it creates a transaction automatically.

When `[applied]` must be inspected, use a replying gateway/driver; a **one-way** Cassandra outbound adapter does not return the LWT result to the caller.

## 5. Choosing consistency by topology and business requirements

There is no single "strongest CL is always best". An app reading payment state needs strong guarantees, whereas metrics ingestion may tolerate eventual convergence. Evaluate **read-after-write**, **availability on node/DC loss**, **p99 latency**, **repair strategy**, and business transaction boundaries.

### 5.1. Single DC, RF=3

With `NetworkTopologyStrategy` and `dc1:3`:

- `ONE` requires at least one replica response.
- `LOCAL_QUORUM` or `QUORUM` requires two responses in a single-DC setup.
- `ALL` requires all three.
- If one replica is unavailable, quorum can still succeed; `ALL` can fail.
- If two replicas are unavailable, `LOCAL_QUORUM` fails even though one node remains healthy.

**Do not interpret "quorum tolerates one node failure" as "the system never times out when one node dies".** If remaining nodes are overloaded, network packets drop, or the coordinator struggles, requests can still fail.

### 5.2. Two DCs, each with RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_multidc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Suppose the application is in `dc1` and uses `LOCAL_QUORUM` for reads and writes:

~~~mermaid
flowchart TB
    APP["Application near dc1"] --> COORD["Coordinator in dc1"]
    COORD --> A1[("dc1 replica A")]
    COORD --> A2[("dc1 replica B")]
    COORD --> A3[("dc1 replica C")]
    COORD --> B1[("dc2 replica D")]
    COORD --> B2[("dc2 replica E")]
    COORD --> B3[("dc2 replica F")]
    A1 -. "ACK local 1" .-> COORD
    A2 -. "ACK local 2" .-> COORD
    COORD --> RESULT["Local quorum met; return success"]
~~~

In this scenario, `LOCAL_QUORUM` requires **two ACKs from dc1** and waits for no ACKs from dc2 before responding. Replication to dc2 may still be in progress or delayed. After a successful write in dc1, a `LOCAL_QUORUM` read **in dc2** is not guaranteed to see the write immediately before replication converges.

If the domain requires confirmation across multiple DCs **before** returning success, evaluate `EACH_QUORUM` for writes or a different model—accepting higher latency and reduced availability if one DC goes down. A `QUORUM` read over total RF=6 requires four responses, increasing cross-region dependency compared to `LOCAL_QUORUM`.

### 5.3. Questions before selecting CL

| Question | Design impact |
|---|---|
| Single DC or multi-DC? | Local vs global quorum, WAN latency |
| What is the actual RF per DC? | Required ACK count, node-failure tolerance |
| Is the app pinned to one DC? | Read-your-writes under `LOCAL_QUORUM` |
| Must reads immediately reflect writes? | Choose overlapping R/W and evaluate LWT |
| If one replica lags, may requests still succeed? | `ONE`/`LOCAL_QUORUM`/`ALL` |
| How long is the HTTP/JMS callback deadline? | Driver timeouts, ack boundaries, p99 |
| Are writes idempotent? | Driver retry policy and redeliveries |
| Needed compare-and-set or unique claim? | LWT with regular + serial CL |
| Will another DC read immediately? | Replication lag and read consistency |

### 5.4. Consistency does not resolve version conflicts

Cassandra uses timestamps/last-write-wins to reconcile concurrent mutations. If `OrderCancelled(v3)` and `OrderPaid(v2)` arrive via different paths, picking read/write `ALL` does **not** preserve business ordering. You need `aggregateVersion`, conditional updates (LWT), or an application-level protocol.

**Section takeaway:** CL governs **how many replica responses are required to finish a request**, not ordering, uniqueness, or distributed transactions between Cassandra and upstream sources.

## 6. Distinguishing four timeout groups

A single flow can have **multiple independent countdown clocks**. They do not automatically add, subtract, or inherit from one another:

~~~mermaid
flowchart TD
    HTTP["HTTP client/API deadline"] --> SI["Spring Integration: send/reply timeout"]
    SI --> Driver["Java driver request timeout"]
    Driver --> Coord["Cassandra coordinator"]
    Coord --> Server["Server-side read/write timeout"]
    Server --> Replicas[("Replica I/O")]
    Broker["JMS/Kafka ack/redelivery lifecycle"] -. "Separate boundary" .-> SI
~~~

| Timeout/deadline | Example config | Starts/ends where? | Observation |
|---|---|---|---|
| **Java Driver request timeout** | `basic.request.timeout` or `Statement.setTimeout(Duration)` | Total duration of one **driver request** on the client, including retries/speculative executions | `DriverTimeoutException` when client expires |
| **Cassandra server read/write timeout** | `read_request_timeout`, `write_request_timeout` in Cassandra config per version | Coordinator/server awaiting replica responses | `ReadTimeoutException` or `WriteTimeoutException` (server-side) |
| **Spring Integration channel send timeout** | `send(message, timeout)` on blocking-capable `MessageChannel` | Time spent waiting to hand off to the channel | `send` returns `false` or throws per channel; not a DB deadline |
| **Spring Integration gateway reply timeout** | `replyTimeout` on supporting gateways | Waiting for a Spring reply message | Request-reply timeout, distinct from CQL write confirmation |
| **HTTP/gRPC caller deadline** | API gateway, client/service timeout | Caller waiting for response | Caller may abandon before backend finishes |
| **JMS acknowledgment/transaction** | Listener container, broker policy | Commit/rollback and redelivery | Does not share the same deadline as CQL by default |
| **Kafka poll/processing lifecycle** | Consumer configs, offset commits, and poll loop | Consumer group membership/offset handling | Not equivalent to a Cassandra timeout |
| **Reactive publisher deadline** | Reactor `timeout(Duration)` | Subscriber waiting for signal | Timeout cancels subscription, never rolls back accepted remote mutations |

**A driver timeout is not Spring Integration `sendTimeout`.** Raising `sendTimeout` to 30 seconds will not save a Cassandra CQL request expiring after 2 seconds. Similarly, raising driver timeout does not extend an HTTP client deadline or guarantee a JMS session stays open.

### 6.1. Driver request timeout is the overall request deadline

In Java Driver 4.x, `basic.request.timeout` bounds the maximum time a request is kept alive on the driver side, **including retries and speculative executions** for that request (not a fresh full timeout per attempt). Upon expiration, callers receive `DriverTimeoutException`.

Example:

~~~text
Client driver request timeout: 2 seconds
 t=0ms       send CQL
 t=350ms     one attempt fails; driver tries another coordinator if policy allows
 t=1100ms    request not yet completed
 t=2000ms    client deadline expires, DriverTimeoutException

On Cassandra server:
 - Mutation from attempt 1 or 2 may still have been processed.
 - Result at t=2500ms never reaches the waiting caller.
~~~

**Never treat one version's default request timeout as every cluster's SLA.** Java Driver 4.x docs commonly list defaults like `2 seconds` and `LOCAL_ONE` in `reference.conf`, yet Spring Boot, execution profiles, or application config may override them; inspect the actual effective configuration.

### 6.2. Server-side read/write timeouts

Server `ReadTimeoutException` means the coordinator dispatched the request but **did not receive enough responses for the CL before the server-side threshold**. `WriteTimeoutException` is analogous for writes. Both may report received vs required response counts.

Example with CL=LOCAL_QUORUM, RF=3:

~~~text
Coordinator waits for 2 local responses.
Replica A: ACK.
Replica B: slow.
Replica C: slow.
Coordinator write timeout expires -> WriteTimeoutException.
~~~

You cannot conclude that A did not write. B/C may still apply later; the coordinator may signal an error after some replicas persisted. **Blindly retrying** a counter increment, non-idempotent side effect, or write with mutating timestamps can corrupt business state.

### 6.3. Why can a driver timeout occur without a server timeout?

The client can time out when:

- The network is slow or drops packets, losing the response.
- Requests queue inside the driver/throttler before reaching a coordinator.
- Connection pools or coordinators are saturated.
- The request is retrying or waiting on speculative executions.
- The server responds after the driver deadline passed.

Hence **`DriverTimeoutException` does not establish whether the server coordinator ever received the request**. Correlate logs, traces, and metrics across both the driver and the Cassandra cluster.

### 6.4. Reactor or HTTP timeouts do not undo a remote write

In a reactive flow:

~~~java
return reactiveCassandraOperations.insert(event)
        .timeout(java.time.Duration.ofSeconds(2));
~~~

This is a **service fragment** with `reactiveCassandraOperations` and `event`. If Reactor times out and cancels the subscription after 2 seconds, **no automatic transaction rollback occurs** for a mutation already received by the Cassandra coordinator. Idempotency or read/reconciliation is needed to resolve uncertain outcomes.

## 7. Configuring consistency and timeouts with Java Driver 4.x

Java Driver 4.x manages defaults via `application.conf`/`reference.conf` or programmatic `DriverConfigLoader`. Inspect the **effective driver config** to know runtime behavior, because Spring Boot and application code can override defaults.

### 7.1. HOCON default configuration

**Application** `application.conf` (not a lesson metadata YAML file):

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
}
~~~

With RF=3 in a matching local datacenter, this requires two quorum responses and waits up to 3 seconds in the driver. **3 seconds is a lab example, not a universal production SLA recommendation**. If a cluster has RF=1, `LOCAL_QUORUM` only needs one replica; that test does not represent an RF=3 environment.

### 7.2. Execution profiles for distinct workloads

An application both writing high-consistency events and reading analytics tables that tolerate eventual convergence:

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
  profiles {
    order-events {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
    }
    dashboard-read {
      basic.request.consistency = LOCAL_ONE
      basic.request.timeout = 1500 milliseconds
    }
  }
}
~~~

In practice, choosing a profile also involves auth, routing, p99, read/write consistency interplay, and data semantics. Setting `dashboard-read=LOCAL_ONE` **accepts reading stale data before writes converge**; never use that profile for screens requiring read-your-writes without additional guarantees.

A driver statement can select a profile:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement stmt = SimpleStatement.builder(
        "SELECT event_type FROM order_event WHERE event_id = ?")
        .addPositionalValue("evt-6001")
        .setExecutionProfileName("dashboard-read")
        .build();

// session is a Spring-injected CqlSession.
session.execute(stmt);
~~~

Here `"dashboard-read"` must exist in the driver configuration; `SimpleStatement` binds values via the API rather than concatenating event IDs into the CQL string.

### 7.3. Per-request overrides via the Statement API

When an exception to the default is needed for one operation type:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement stmt = SimpleStatement.builder(
        "SELECT event_type FROM order_event WHERE event_id = ?")
        .addPositionalValue("evt-6001")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true)
        .build();

session.execute(stmt);
~~~

`Statement.setTimeout(Duration)` overrides only the **driver request timeout** for that statement. It does **not** alter `read_request_timeout` on the Cassandra server or an HTTP caller's deadline. `setIdempotent(true)` permits the driver to consider retries/speculative executions per policy; usually fine for read-only SELECTs, yet writes with side effects must be evaluated individually.

### 7.4. PreparedStatement and BoundStatement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
        "INSERT INTO order_event "
        + "(event_id, event_type, payload_json) VALUES (?, ?, ?)");

BoundStatement write = prepared.boundStatementBuilder()
        .setString(0, "evt-6001")
        .setString(1, "OrderPaid")
        .setString(2, "{\"eventId\":\"evt-6001\"}")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true)
        .build();

session.execute(write);
~~~

The snippet assumes a service with an injected `session` bean and an existing `order_event` table. Marking an `INSERT` with `setIdempotent(true)` assumes a **stable `eventId`, identical immutable payload, and no external side effects**; if retries mint new values, mutate timestamps affecting outcomes, or change event IDs, marking it idempotent is inappropriate.

**`BoundStatement` is immutable in Driver 4.x.** Calling `bound.setTimeout(...)` or `bound.setConsistencyLevel(...)` requires capturing the **returned instance**; otherwise the original statement is unchanged. Prefer `boundStatementBuilder()` chaining as above to avoid this mistake.

### 7.5. Programmatic config instead of HOCON

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;

DriverConfigLoader loader = DriverConfigLoader
        .programmaticBuilder()
        .withDuration(DefaultDriverOption.REQUEST_TIMEOUT, Duration.ofSeconds(3))
        .withString(DefaultDriverOption.REQUEST_CONSISTENCY, "LOCAL_QUORUM")
        .build();

// Pass loader to CqlSession.builder().withConfigLoader(loader) when building the session.
~~~

This is an alternative to **HOCON config** when the application builds the driver session manually. With Spring Boot auto-config, constructing an extra un-wired `CqlSession` or loader **will not change endpoint behavior**. Verify which beans/configs are actually active rather than assuming a config file took effect merely because it exists.

### 7.6. Inspecting effective config

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

DriverExecutionProfile profile = session.getContext()
        .getConfig()
        .getDefaultProfile();

System.out.println(
        "request timeout = "
        + profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
System.out.println(
        "consistency = "
        + profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY));
~~~

This is a lab debugging snippet—**never print secrets or sensitive config**. When using named execution profiles, inspect that specific profile rather than only the default profile. Alongside request settings, retry policies and speculative execution policies also affect total elapsed time and attempt counts.

## 8. Spring Data Cassandra: `WriteOptions`, `QueryOptions`, and templates

Spring Data lets you specify per-operation CL/timeouts through:

- `WriteOptions` for entity writes (`INSERT`/`UPDATE`/`DELETE`).
- `QueryOptions` for compatible CQL/query operations.
- Execution profiles or driver statements when specialized settings are required.
- `CqlTemplate`/`ReactiveCqlTemplate` and `CassandraTemplate`/`ReactiveCassandraTemplate` at different abstraction levels.

**Do not confuse `ttl` with `timeout`:** `WriteOptions.ttl(...)` governs **how long data lives**, whereas `WriteOptions.timeout(...)` governs **how long the client waits for the operation**. Both take a Java `Duration` yet have completely different meanings.

### 8.1. Creating WriteOptions with CL and timeout

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.WriteOptions;

WriteOptions durableOrderEventWrite = WriteOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(3))
        .idempotent(true)
        .build();
~~~

Per Spring Data Cassandra Javadoc, `WriteOptions` extends `QueryOptions` and exposes builders `consistencyLevel(...)`, `timeout(...)`, `serialConsistencyLevel(...)`, `executionProfile(...)`, and `idempotent(...)`. Only options that are **explicitly set** apply to the query; unset fields fall back to driver defaults.

`idempotent(true)` here is suitable only for an event-store operation already **reviewed as idempotent**. It **does not add a unique constraint** in Cassandra or deduplicate JMS/Kafka events.

### 8.2. Using WriteOptions in the Cassandra outbound channel adapter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow orderEventWriteFlow(
        ReactiveCassandraOperations operations,
        WriteOptions durableOrderEventWrite) {

    return IntegrationFlow.from("orderEventWriteRequests")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(durableOrderEventWrite),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

This flow receives a Spring Message carrying a **`@Table`-mapped entity payload**. `CassandraMessageHandler` calls `ReactiveCassandraOperations`, applies `WriteOptions` for `INSERT` mode, and awaits completion when `async(false)`. In Spring Integration Cassandra, **the handler defaults to asynchronous**, so without sync mode, write completion can occur **after upstream `send()` returns**.

**`.writeOptions(...)` in the Cassandra DSL is meant for `INSERT`, `UPDATE`, and `DELETE`; never assume it overrides the timeout/CL of a custom driver `Statement<?>` built via `statementFunction(...)`.** In `STATEMENT` mode, configure options directly on the statement or via a driver execution profile.

### 8.3. Complete bean configuration for the WriteOptions example

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Configuration
class CassandraWriteOptionsConfig {
    @Bean
    public WriteOptions durableOrderEventWrite() {
        return WriteOptions.builder()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .timeout(Duration.ofSeconds(3))
                .idempotent(true)
                .build();
    }
}
~~~

Define this bean **before the handler starts processing**. Never mutate a shared singleton `WriteOptions` or handler config from an untrusted client header like `consistency="ANY"`, which would let an external source weaken business write consistency.

### 8.4. Using `QueryOptions` for appropriate read queries

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.QueryOptions;

QueryOptions readOptions = QueryOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(2))
        .pageSize(100)
        .build();
~~~

`QueryOptions` captures settings for query/read operations. **How it attaches to `CassandraTemplate`/repository queries depends on the API overloads and Spring Data version**; do not pass it into `CassandraMessageHandlerSpec.writeOptions(...)` in `STATEMENT` mode expecting it to take effect. For a Spring Integration Cassandra SELECT gateway using a query string, choose a default **driver execution profile**, or construct a `Statement<?>` with CL/timeout configured and pass it via `statementFunction(...)`.

### 8.5. When to use `CqlTemplate` instead of CassandraMessageHandler?

If an application intentionally uses imperative `CqlTemplate` inside a Spring `@ServiceActivator`, it runs **blocking CQL** and can use driver statements, callbacks, or template settings. Conversely, the built-in Cassandra outbound adapter/gateway requires `ReactiveCassandraOperations`; never pass `CqlTemplate` into the `CassandraMessageHandler` constructor.

With reactive `Mono`/`Flux`, remember publishers are **lazy**: creating a `Mono` does not start I/O. Ensure proper subscription and error handling so timeouts and exceptions are never dropped. **Never call `block()` on a WebFlux event loop** simply to force synchronous behavior.

## 9. Cassandra outbound adapter and gateway: where do timeouts go?

The **outbound channel adapter** and **outbound gateway** both wrap `CassandraMessageHandler`, yet enforce different response contracts:

| Endpoint | Spring Message response | What to watch |
|---|---|---|
| `Cassandra.outboundChannelAdapter(...)` | One-way, no business reply | Write completion and error paths |
| `Cassandra.outboundGateway(...)` | Replies per operation | Query/`WriteResult`, correlation, and reply channel |
| Handler `async=true` (default) | Reactive/asynchronous execution | Caller can finish before I/O |
| Handler `async=false` | Awaits reactive operation result | Exceptions can propagate along synchronous channels |

### 9.1. SELECT gateway with CL/timeout on the statement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findEventWithTimeout(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("findEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .statementFunction(message -> {
                        String eventId = (String) message.getPayload();
                        return SimpleStatement.builder(
                                "SELECT event_id, event_type FROM order_event "
                                + "WHERE event_id = ?")
                                .addPositionalValue(eventId)
                                .setConsistencyLevel(
                                        DefaultConsistencyLevel.LOCAL_QUORUM)
                                .setTimeout(Duration.ofSeconds(2))
                                .setIdempotent(true)
                                .build();
                    }),
                    endpoint -> endpoint.async(false))
            .channel("findEventResults")
            .get();
}
~~~

`findEventRequests` is a Spring input channel carrying a validated `String eventId` payload. `statementFunction(...)` returns a driver `Statement<?>` with bound value, CL, and driver request timeout. `findEventResults` must have an appropriate **consumer**; for multi-row queries, handle the exact reply type produced by your Cassandra gateway/driver version.

**This is an alternative flow** to the `INSERT` outbound adapter in section 8; do not bind both endpoints to the same input channel when only one operation is desired. `async(false)` surfaces errors on synchronous call paths, yet blocks the calling thread—never deploy it on a non-blocking event loop.

### 9.2. What happens with a `DirectChannel`?

~~~mermaid
sequenceDiagram
    participant P as Upstream Service
    participant Ch as DirectChannel
    participant H as CassandraMessageHandler async=false
    participant DB as Cassandra

    P->>Ch: send(message)
    Ch->>H: handle(message)
    H->>DB: INSERT / SELECT
    alt Operation completed
        DB-->>H: Completion / result
        H-->>Ch: Handler returns
        Ch-->>P: send returns
    else Exception propagated
        DB-->>H: timeout/unavailable/error
        H-->>Ch: Exception
        Ch-->>P: Exception
    end
~~~

On a `DirectChannel` with a sync handler, the caller can observe exceptions before the source JMS listener exits its callback. Still, **regardless of CL**, the Cassandra write and JMS commit **are not atomic**.

### 9.3. What changes with an async channel or handler?

~~~text
JMS inbound listener
  -> ExecutorChannel / QueueChannel (in-memory) / async Cassandra handler
  -> listener can return/commit
  -> Cassandra write is in flight
  -> Cassandra timeout occurs after source commit
~~~

In that case a Cassandra failure **cannot automatically roll back the already-committed JMS message**. To stay durable, design for:

- Acknowledging/committing the source only after target completion where supported.
- Durable handoff/inbox/outbox so incomplete work can be replayed.
- Recovery workers with idempotency and a retry budget.
- A DLQ/quarantine process for errors unrecoverable by retries.

**Never treat `errorChannel` as a broker DLQ.** It is a Spring `MessageChannel` for `ErrorMessage`; explicitly wire how errors reach upstream acknowledgment, monitoring, or durable storage.

### 9.4. Spring gateway reply timeout vs Cassandra request timeout

When invoking a request/reply gateway to query Cassandra:

~~~text
Spring gateway replyTimeout = 1500 ms
Driver request timeout       = 3000 ms
Cassandra server read timeout = value from server config
~~~

The gateway may stop waiting for a Spring reply after 1.5 seconds while the Cassandra request keeps running. **No automatic rollback happens** for a remote write once the coordinator receives it. When layering timeouts, consider keeping the driver deadline **shorter than the caller deadline** (leaving room for transforms, network, and error handling), while verifying behavior because async boundaries do not always cancel downstream operations.

## 10. Classifying consistency and timeout errors

### 10.1. Key exceptions

| Driver exception | Error origin | What it means |
|---|---|---|
| `UnavailableException` | Cassandra coordinator | Coordinator knows too few replicas are **currently alive** to satisfy the chosen CL |
| `ReadTimeoutException` | Cassandra coordinator | Read did not receive enough responses on time for the read CL |
| `WriteTimeoutException` | Cassandra coordinator | Write did not receive enough ACKs on time for the write CL |
| `ReadFailureException` | Cassandra coordinator | Replica/coordinator reported a non-timeout read failure |
| `WriteFailureException` | Cassandra coordinator | Replica/coordinator reported a non-timeout write failure |
| `DriverTimeoutException` | Java Driver client | Overall driver-side request deadline expired |
| `AllNodesFailedException` / `NoNodeAvailableException` | Java Driver client | No coordinator/attempt succeeded in the query plan |
| `OverloadedException` | Cassandra coordinator | Node is overloaded; may need concurrency throttling |
| `UnauthorizedException` / `InvalidQueryException` | Cassandra server | Invalid permissions or query/schema; blind retry is usually futile |

**Spring Data Cassandra translates exceptions** into `DataAccessException` or appropriate runtime exceptions. Thus the Spring service layer may not see the raw driver class at the top level; inspect the cause chain and metadata when classifying errors **without leaking secrets**. Never build retry logic solely by matching `"timeout"` in exception messages.

### 10.2. How does `Unavailable` differ from a timeout?

For RF=3, `CL=QUORUM` requiring 2 responses:

- **Unavailable:** the coordinator already knows only 1 replica is live/reachable, so **CL cannot be met immediately**.
- **WriteTimeout:** the coordinator attempted the write but **did not collect enough ACKs before the deadline**.
- **DriverTimeout:** the client saw no final result within the request deadline; the server may never have received it, may still be waiting, or may have already written it.

`Unavailable` does not mean "the cluster is dead"; one replica might still serve `ONE`, yet that does not justify silently downgrading CL just to "keep things running".

### 10.3. Numbers inside server-side timeouts

In `ReadTimeoutException` and `WriteTimeoutException`, the driver/server can report `received` and `blockFor` (responses received vs required by CL), plus `writeType` for writes or `dataPresent` for reads per API.

~~~text
WriteTimeout:
    CL = LOCAL_QUORUM
    required/blockFor = 2
    received = 1

Correct interpretation:
    Not enough ACKs for write CL.
    One replica may have persisted; global outcome is uncertain.

Wrong interpretation:
    No replica wrote; safe to retry a counter blindly.
~~~

Use these counts for observability and diagnostics only; **never infer with certainty whether remaining replicas wrote or not**.

### 10.4. Which retries are helpful?

| Scenario | Recommended action | Avoid |
|---|---|---|
| Temporary unavailable or overload | Circuit breaker/backoff; bounded retry if idempotent | Continuous high-concurrency retries |
| Write timeout, uncertain outcome | Keep same `eventId`; idempotent retry/reconcile | Minting a new `eventId` and inserting again |
| Read timeout | Bounded retry or workload tuning where appropriate | Silently downgrading critical read CL |
| Invalid CQL, missing table | Fail fast; fix schema/migration/config | Retrying the same bad CQL 100 times |
| Unauthorized/bad credentials | Alert; fix ACLs/secrets | Infinite retries without fixing access |
| Codec/type mismatch | Fix transformer/contract | Treating it as a transient cluster glitch |
| LWT `applied=false` | Read/inspect state; handle business conflict | Treating it as a transport error to retry blindly |

### 10.5. Never silently downgrade consistency on failure

Suppose a domain specifies `LOCAL_QUORUM` for read-after-write guarantees within the local DC. If a driver policy silently downgrades writes to `ONE`, those consistency assumptions **no longer hold**. Java Driver documentation warns against `ConsistencyDowngradingRetryPolicy`. Never enable it on payment or audit flows merely to make error charts look greener.

### 10.6. Speculative execution

Java Driver supports **speculative execution**: sending an extra attempt to another coordinator when a request is slow to trim tail latency. It is **disabled by default** in Driver 4.x and applies only to requests marked **idempotent**.

Trade-offs:

- Increases request traffic while the cluster is already slow.
- Speculative attempts can execute concurrently; "canceling" in the driver typically just ignores the response, **never recalling an already-sent mutation**.
- Each speculative attempt can trigger its own retries.
- Can worsen an outage when the cluster is overloaded.

For immutable event-log upserts with a fixed key and payload, speculative execution/retries may be acceptable; for counter increments, emails, or external side effects, **never mark them idempotent just to turn on speculative execution**.

## 11. Designing timeout budgets from upstream SLAs

An API that must respond within 5 seconds cannot allocate the entire 5 seconds to Cassandra. Time is also spent receiving the request, authenticating, validating, serializing, passing through channels, traversing the network, and handling errors.

### 11.1. An example time allocation

Suppose **HTTP caller deadline = 5 seconds** and normal Cassandra p99 is under 1 second. An illustrative budget:

~~~text
HTTP / API gateway hard deadline               5000 ms
  authentication + validation + routing          300 ms budgeted
  Cassandra driver request timeout              2500 ms
  Spring reply wait budget                      3500 ms
  response transform / network buffer            500 ms
  headroom for jitter / scheduling               remaining
~~~

These numbers are **illustrative**, not a naive additive formula. Some intervals **overlap** in asynchronous execution; measure total budgets using distributed traces in the real pipeline. A 3500 ms Spring channel reply timeout is meaningful only if the flow actually uses a **reply-awaiting** gateway.

Implementation rules:

1. Measure real p95/p99 per step under healthy load.
2. Budget around the end-to-end business deadline, not just a single network socket timeout.
3. Keep the driver timeout lower than the caller deadline by enough margin to propagate exceptions/responses.
4. Fit the **retry budget** inside the remaining deadline; never start a retry certain to miss the caller deadline.
5. On HTTP timeout, return **failure**, **accepted + status URL**, or **uncertain/pending reconciliation** per contract; never falsely report "write definitely failed" when uncertain.
6. For JMS/Kafka, ack/offset boundaries differ from HTTP; apply completion/transaction rules accordingly.

### 11.2. Never just raise timeouts to fix an overloaded cluster

If write p99 jumps from 200 ms to 8 s due to a hot partition, compaction, or network congestion, raising the driver timeout from 2 s to 30 s simply **piles up waiting requests**, adding memory pressure and in-flight backlogs while masking the bottleneck.

If the app receives 1,000 messages/s while Cassandra sustains 500 writes/s, the backlog grows by roughly **500 messages every second** without backpressure or source throttling. Longer timeouts do not create extra throughput.

### 11.3. Canceling on the client does not cancel inside Cassandra

A client deadline/cancellation only tells the application to stop waiting. The Cassandra coordinator may have already forwarded mutations; for an `INSERT` applied on replicas, **cancellation is never a database rollback**. Use a stable business `eventId` and reconciliation to resolve uncertain outcomes.

## 12. Idempotency and correctness across timeouts

### 12.1. Writing events with a fixed business key

Lab schema:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

Payload:

~~~json
{
  "eventId": "evt-6001",
  "orderId": "ORD-6001",
  "eventType": "OrderPaid",
  "payloadJson": "{\"currency\":\"VND\",\"amountMinor\":150000}"
}
~~~

When resending an event after a timeout:

- Preserve the **exact `eventId`** across JMS redeliveries, Kafka replays, and HTTP retries.
- Use the exact same partition and full primary key.
- Keep the event payload immutable; a matching `eventId` with different content must be flagged as a **conflicting event**.
- Never generate a new `UUID.randomUUID()` on the consumer per delivery attempt.
- If writes use TTL or per-retry mutation timestamps, verify the operation remains **genuinely business-idempotent**; upserts do not always guarantee an immutable outcome across every schema.

### 12.2. A concrete failure timeline

~~~mermaid
sequenceDiagram
    participant Source as JMS broker
    participant App as Spring Integration
    participant C as Cassandra
    Source->>App: OrderPaid evt-6001
    App->>C: INSERT evt-6001, CL=LOCAL_QUORUM
    C-->>App: Response lost / driver timeout
    Note over C: One or more replicas may have written
    App-->>Source: Rollback / nack per policy
    Source->>App: Redeliver evt-6001
    App->>C: Re-INSERT same key and values
    C-->>App: Success
    App-->>Source: Commit / ack
~~~

This flow is **only relatively safe** when designed to be idempotent. Standard Cassandra `INSERT` does not reject duplicate keys like an RDBMS unique insert; it uses **upsert semantics**. If a retry sends the same ID with a different `payloadJson`, the row can change depending on timestamps/last-write-wins.

### 12.3. Risk of early source commits

With the default async Cassandra handler or a Spring `ExecutorChannel`, a JMS listener can acknowledge **before the reactive Cassandra operation finishes**. If the write times out afterward, the JMS broker will not automatically redeliver the committed message.

Options:

1. Await Cassandra completion within the source-handling boundary when infrastructure and throughput allow.
2. Persist messages to a **durable handoff/inbox** before acknowledging the source, then let a dedicated worker write to Cassandra.
3. Run a recovery/reconciliation job with event-state tracking to replay incomplete operations.

**Do not call option (1) a distributed transaction.** Cassandra may write successfully while the JMS commit fails → the broker still redelivers, so **idempotency remains mandatory**.

### 12.4. Avoiding non-idempotent side effects

| Operation | Retry on uncertain outcome? | Conditions to evaluate |
|---|---|---|
| Immutable event `INSERT` by `eventId` | Usually yes | Stable key/values, TTL/timestamp semantics |
| `SELECT` by `eventId` | Usually yes | Data may change between two reads |
| `UPDATE SET state = ?` | Conditionally | Version guard/ordering, timestamps |
| `UPDATE counter = counter + 1` | Unsafe for blind retry | A retry can increment twice |
| Sending email/HTTP after Cassandra write | Not idempotent automatically | Requires external idempotency key |
| LWT `INSERT IF NOT EXISTS` | Conditionally | Must inspect `[applied]` and reconcile timeouts |

## 13. LWT: regular consistency and serial consistency are two settings

Another common case: `order_current_state` stores the versioned state of an order. Events arrive out of order; the app must accept an update only when the stored version matches.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_current_state (
    order_id text PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);

-- Update when the previous version matches.
UPDATE shop_integration.order_current_state
SET version = ?, state = ?, last_event_id = ?
WHERE order_id = ?
IF version = ?;
~~~

This is a Cassandra **lightweight transaction**, not a multi-table SQL transaction. LWT enables compare-and-set within Cassandra's supported partition/condition scope at the **cost of multiple consensus round-trips** compared to a normal write.

### 13.1. Configuring an LWT statement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement lwt = SimpleStatement.builder(
        "UPDATE order_current_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE order_id = ? IF version = ?")
        .addPositionalValue(3L)
        .addPositionalValue("CANCELLED")
        .addPositionalValue("evt-6003")
        .addPositionalValue("ORD-6001")
        .addPositionalValue(2L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
        .setTimeout(Duration.ofSeconds(5))
        .build();

// Must inspect result.wasApplied() or equivalent in gateway/driver.
var result = session.execute(lwt);
boolean applied = result.wasApplied();
~~~

This is a **lab snippet** for a cluster supporting `LOCAL_SERIAL`/`LOCAL_QUORUM` with compatible replication topology. `LOCAL_SERIAL` is scoped to the local DC and requires careful analysis of multi-DC failovers and business invariants. The 5-second timeout is illustrative because LWT is slower than normal writes; do not blindly raise all production timeouts to 5 seconds.

### 13.2. `applied=false` is not a connection error

If the stored version is not `2`, Cassandra returns `[applied]=false`. This is a **business condition mismatch**, not an `UnavailableException`. The handler should classify it:

- Stored version is already `3` with the same `last_event_id`: likely a valid retry.
- Stored version is higher or `last_event_id` differs: conflict or out-of-order event requiring domain handling.
- Timeout or `Unavailable`: **uncertain state**; retry/reconcile using the business key.

Never use a **one-way outbound adapter** and treat `send(true)` as `[applied]=true`. Use a gateway/driver API that reads LWT outcomes, or a reconciliation process.

### 13.3. LWT does not merge JMS and Cassandra into one atomic commit

Even though LWT enforces compare-and-set inside Cassandra, a JMS commit can still fail after Cassandra applies the update. The event will be redelivered; version/idempotency checks must still hold. Never design around **"LWT + transacted JMS = end-to-end exactly-once"**.

## 14. Backpressure, concurrency, and consistency under heavy load

**CL and timeouts do not operate in a vacuum**: they interact with partition keys, replica load, coordinator routing, request queues, compaction, network health, retry policies, and upstream message sources.

### 14.1. Strong RF/CL cannot fix a hot partition

Suppose a workload writes 20,000 events/second to a single Cassandra partition key. All three replicas for that partition run hot, and `LOCAL_QUORUM` needs ACKs from two of them. Doubling the consumer count can **increase the timeout rate** as the application drives even more requests into the same replicas.

Investigation checklist:

1. Check **query shape** and partition keys; is a single tenant/key running hot?
2. Measure write/read p95/p99 latency by table, node, and coordinator.
3. Count in-flight requests and pending tasks; is the cluster near overload?
4. Check compactions, tombstones, GC pauses, packet loss, and repairs.
5. Check broker backlog/consumer lag and retry rates.
6. Cap concurrency, shrink batches, or fix the data model/bucketing before raising request timeouts.

### 14.2. Reactive Cassandra does not allow unlimited concurrency

`ReactiveCassandraOperations` returns publishers, yet if the application subscribes to every incoming message **without limits**, active operations can overwhelm the driver and cluster.

Example of a reactive pipeline with bounded in-flight operations:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// Fragment: source is a validated Flux<OrderEvent>.
Flux<OrderEvent> successfullyWritten = source.concatMap(event ->
        reactiveCassandraOperations.insert(event)
                .map(writeResult -> event)
);
~~~

`concatMap` keeps one active publisher at a time in this stream, illustrating **source-order preservation** at the cost of lower throughput. For independent events, use `flatMap(..., maxConcurrency)` bounded and monitored; **do not** assume `flatMap` outputs finish in the original event order.

**Note:** this snippet is not a complete Spring `IntegrationFlow`; with Kafka/JMS sources, subscription and acknowledgment boundaries must be engineered explicitly. It simply illustrates bounding concurrency for reactive Cassandra operations.

### 14.3. End-to-end retry budgets

Suppose:

~~~text
Driver retry             at most 1 per policy
Service-layer retry      at most 2
JMS redelivery           at most 5
DLQ replay               possibly more after remediation
~~~

Do not treat individual limits as "small" and ignore how layers multiply. Even in a simple case where each service attempt allows two driver executions and each JMS delivery allows three service attempts (initial + two retries), total attempts can reach **30** before hitting the DLQ. Speculative execution can amplify cluster traffic even further.

When write outcomes are uncertain, overlapping retries can also cause **concurrent writes on the same key**. Bounded retries, jittered backoff, circuit breakers, and durable queuing/handoff usually matter far more than continually raising timeouts.

## 15. Metrics and timeout diagnostic workflow

Cassandra exposes metrics at the **table**, **keyspace**, **client request**, and thread-pool levels. Each node reports its own metrics, so observability must aggregate and compare across cluster topology.

| Metric / signal | Location | Meaning |
|---|---|---|
| Read/Write latency p50/p95/p99 | Cassandra table/coordinator, Java driver | Separates normal latency from tail spikes |
| ClientRequest Read/Write `Timeouts` | Cassandra coordinator | Server-side timeout counts |
| ClientRequest `Unavailables` / `Failures` | Cassandra coordinator | Unmet CL or server errors |
| Driver `DriverTimeoutException` count | Application/driver | Client-side request deadlines expired |
| Driver retries/speculative executions | Driver metrics | Tracks attempt counts and request amplification |
| In-flight requests/connection saturation | Java driver | Signals overload and missing backpressure |
| Pending compactions/flushes, dropped messages | Cassandra cluster | Backend saturation |
| Hot partitions / partition sizes | Table diagnostics | Workload skew, poor key distribution |
| Source JMS queue depth / Kafka consumer lag | Broker | Downstream slowness building backlog |
| Handler completion/error rate | Spring Integration | Confirms whether endpoints actually complete operations |
| Duplicate/conflicting event IDs | Business metrics | Retry/redelivery quality and idempotency |
| LWT applied / condition-not-met | Application/Cassandra CAS metrics | Business conflicts vs transport errors |

### 15.1. Tracing a timeout with five questions

1. **What is the exception class?** `UnavailableException`, `WriteTimeoutException`, `DriverTimeoutException`, or gateway reply timeout?
2. **What was the effective CL?** Inspect the active execution profile/statement options; do RF and DC topology match?
3. **Did the request reach a coordinator?** Correlate client traces with Cassandra metrics/logs in the same time window.
4. **Was a mutation applied?** Using the fixed `eventId`, read back by key when needed; never assume a timeout equals rollback.
5. **Has the source message been acked/committed?** Check message ID, `eventId`, JMS delivery count, or Kafka topic/partition/offset to pick the recovery path.

### 15.2. Runbook when timeouts spike

~~~mermaid
flowchart TD
    A["Cassandra timeout rate rises"] --> B{"Client or server timeout?"}
    B -->|"DriverTimeout"| C["Check request deadline, in-flight, network, retries"]
    B -->|"Read/WriteTimeout"| D["Check CL, RF, ACK counts, slow replicas"]
    B -->|"Unavailable"| E["Check replica health, topology, local DC"]
    C --> F{"Cluster overloaded?"}
    D --> F
    E --> F
    F -->|"Yes"| G["Throttle concurrency, stop retry storm, fix node/hot partition"]
    F -->|"Unclear"| H["Collect traces and driver/server metrics"]
    G --> I["Reconcile events with uncertain outcome"]
    H --> I
    I --> J["Controlled replay by eventId"]
~~~

Only lower CL after an **explicit business decision**, evaluating stale-read risk, durability, and availability. Swapping `LOCAL_QUORUM` for `ONE` to make error graphs look cleaner can silently break read-after-write contracts users depend on.

### 15.3. Logs and cardinality

Log `eventId`, request/trace ID, logical operation, CL, timeout config/profile, elapsed time, exception type, and keyspace/table. Never log raw tokens, passwords, payment details, or full JSON payloads. `eventId` belongs in **logs/traces**, not as a **per-event metric label** where cardinality will explode.

## 16. Quick troubleshooting guide

| Symptom | Common cause | Check/fix |
|---|---|---|
| `LOCAL_QUORUM` behaves unexpectedly on single-node test | Keyspace RF=1 or wrong topology config | Use RF>=3 with at least 3 replica nodes to test quorum |
| Writes throw `Unavailable` when one node is down | `CL=ALL` or insufficient live replicas for quorum | Check RF/CL, topology, and replica health |
| `LOCAL_ONE` read misses recent event | Write has not converged to the queried replica | Pick R/W CL matching read-after-write contract |
| Cross-DC read misses new write | Write used `LOCAL_QUORUM` in another DC | Account for replication lag and local/global quorum strategy |
| `DriverTimeoutException` while server timeout metric stays flat | Client deadline expired early or network/client queue delay | Check driver in-flight count, tracing, client timeout |
| `WriteTimeoutException` yet row exists later | Mutation applied on some replicas | Reconcile by stable key; do not assume rollback |
| Gateway `replyTimeout` fires before Cassandra finishes | Spring reply budget shorter than DB request | Align deadlines with SLA and design cancellation/recovery |
| `send()` returns true yet row is absent | Cassandra handler is async by default | Track completion/errors; consider `async(false)` where suitable |
| `WriteOptions` ignored on custom statement | `writeOptions` targets entity operation modes | Set options on `Statement<?>` or execution profile |
| Changing CL via client header does nothing | Endpoint ignores header or violates contract | Enforce CL server-side and allowlist use cases |
| Source retries cause write amplification | Driver + service + broker retrying concurrently | Cap retry budget, enforce idempotency, add circuit breaker |
| Speculative execution increases load | Policy enabled on idempotent operations | Tune max-executions/delay or disable during overload |
| LWT returns `applied=false` | Version condition mismatch | Handle duplicate/conflicting event; do not treat as timeout |
| Reads slow even at `CL=ONE` | Hot partition, full scan, poor table model | Fix query/partition key, paging, cluster health |
| Large driver timeout yet HTTP returns 504 | HTTP reverse proxy deadline is shorter | Budget deadlines end-to-end from caller to DB |
| JMS never redelivers after write failure | Source acked before async completion | Fix ack boundary or add durable handoff |
| Cassandra wrote yet JMS redelivers | DB and broker commits are not atomic | Keep stable `eventId` and idempotent replay |
| Bad schema/auth query retries endlessly | Permanent error | Fail fast; fix migration, ACLs, or DTO |
| One node has much higher p99 | Compaction, GC, or hot replica | Check node diagnostics, data model, load balancing |

## 17. Pre-production design checklist

1. **Replication:** keyspace replication strategy, RF per DC, and actual node count are documented.
2. **Write CL:** chosen from required confirmation strength for events/audit/state, not speed alone.
3. **Read CL:** chosen from read-after-write and DC scope, checking overlap math.
4. **LWT:** serial consistency reserved for conditional operations with clear invariants.
5. **Timeout budget:** end-to-end p99 measured from caller to Cassandra, leaving headroom to fail or retry.
6. **Driver config:** effective profiles and per-statement overrides verified rather than assuming defaults.
7. **Spring flow:** clear separation of no-reply adapters vs replying gateways; async handler default accounted for.
8. **JMS/Kafka boundary:** explicitly decided whether source ack/offset happens before or after Cassandra completion.
9. **Idempotency:** stable business `eventId`/full key and immutable payload across retries/replays.
10. **Retries:** driver, app, broker, and DLQ policies combined into one budget with backoff/jitter.
11. **Backpressure:** bounded in-flight requests, reactive concurrency, upstream buffers, and hot-partition protection.
12. **Error taxonomy:** distinguishes `Unavailable`, server timeouts, driver timeouts, LWT `applied=false`, and permanent contract errors.
13. **Monitoring:** tracks CL, p99 latency, client/server timeouts, retries, and message backlogs.
14. **Security:** only trusted services choose CL and execution profiles; no credentials/sensitive payloads in logs.
15. **Recovery:** reconciliation handles uncertain timeout outcomes and replays produce no wrong side effects.

## 18. Hands-on lab: consistency and timeouts in Spring Integration

**Environment:** Java 17+, Spring Integration Cassandra 6+, compatible Spring Data Cassandra reactive, an Apache Cassandra test cluster, and `cqlsh`. Quorum/node-failure exercises require **at least three real Cassandra replica nodes** in one DC (RF=3); a single-node test container only covers basic API, CQL, and timeout exercises and **cannot prove quorum failover**.

### Exercise A — Creating the schema and checking RF

On a cluster with three nodes in DC `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

Before running, **verify the actual datacenter name is `dc1`**, all nodes are healthy, and RF=3 is achievable. If using a single-node cluster, change to RF=1 **for the single-node lab only** and skip 1-of-3-node fault-tolerance comparisons.

Verify with `cqlsh`:

~~~sql
DESCRIBE KEYSPACE shop_integration;
CONSISTENCY LOCAL_QUORUM;

INSERT INTO shop_integration.order_event
    (event_id, order_id, event_type, payload_json)
VALUES
    ('evt-6001', 'ORD-6001', 'OrderPaid', '{"source":"lab"}');

SELECT event_id, event_type
FROM shop_integration.order_event
WHERE event_id = 'evt-6001';
~~~

**PASS:** confirms active CL, reads/writes by primary key, and verifies RF/topology in the schema. `CONSISTENCY` is a **`cqlsh` shell command**, not a CQL statement for `CqlTemplate.execute(...)`.

### Exercise B — RF=3, ONE vs LOCAL_QUORUM vs ALL

1. Write 100 events at `CL=ONE` and measure p50/p95/p99 latency on a healthy cluster.
2. Write an equivalent batch at `LOCAL_QUORUM` and measure again.
3. Write at `ALL` on the **test cluster** and measure the latency impact.
4. Stop **one Cassandra node** using managed test orchestration, verifying two replicas stay healthy.
5. Test `LOCAL_QUORUM` and `ALL`; explain why quorum still succeeds while `ALL` can fail.
6. Stop a second node (in the controlled lab only) and try `LOCAL_QUORUM`; distinguish `UnavailableException` from timeouts.
7. Restore the cluster, wait for normal health, and check node/replica state.

**PASS:** explains `Q=2` for RF=3, single-replica fault tolerance, and why **`ALL`** reduces availability. Do not claim every node-down failure throws the exact same exception; it depends on failure detection timing vs timeouts.

### Exercise C — Driver config and per-statement overrides

1. Configure `application.conf` with `LOCAL_QUORUM` and `3 seconds`.
2. Read the effective driver profile via `session.getContext().getConfig()`.
3. Send a prepared `INSERT` using `BoundStatement` with `setTimeout(Duration.ofSeconds(2))`.
4. Run `SELECT` using execution profiles `dashboard-read` (`LOCAL_ONE`) and `order-events` (`LOCAL_QUORUM`).
5. Verify CL and deadlines applied to the **actual statement/operation**, not just bean names or config files.
6. Read values back from Cassandra and compare `session.execute(...)` timings.

**PASS:** distinguishes global config, execution profiles, and per-statement overrides; never concatenates user values into CQL strings.

### Exercise D — Spring Data WriteOptions and Spring Integration adapter

1. Create the Java entity:

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

2. Define a `WriteOptions` bean with `consistencyLevel(LOCAL_QUORUM)` and `timeout(Duration.ofSeconds(3))`.
3. Wire `Cassandra.outboundChannelAdapter(operations, Type.INSERT).writeOptions(options)`.
4. Send `Message<OrderEvent>` to the channel; query Cassandra by `event_id`.
5. Switch from `async(false)` to `async(true)` to compare when `send()` returns vs when the write completes.
6. Stop one replica on the RF=3 cluster; observe handler errors/latency and upstream handling.

**PASS:** Spring Data mapping and `WriteOptions` apply to the entity operation; understands that the one-way adapter produces no reply.

### Exercise E — Three failure modes and uncertain outcomes

1. Set a short driver timeout **in tests only** and introduce controlled latency.
2. Catch `DriverTimeoutException` when the driver deadline expires before completion.
3. Induce a scenario where the coordinator accepts the request yet replica responses miss the server deadline to observe `ReadTimeoutException`/`WriteTimeoutException` where supported.
4. Reduce available replicas below CL to observe `UnavailableException` or the corresponding error when the coordinator knows enough nodes are down.
5. On a write timeout, **read back by `eventId`** after the cluster stabilizes to prove a client error **does not prove** the row is absent.
6. Implement retries with the same event ID and immutable payload. Never generate a fresh event ID per attempt.

**PASS:** reports exception class, CL, RF, elapsed time, received/required counts when available, and post-reconciliation row state. Never try to force every failure type on a single-node cluster.

### Exercise F — Spring Integration gateway and independent timeouts

1. Create `findEventWithTimeout` from section 9 with a consumer for `findEventResults`.
2. Execute a successful request with `CL=LOCAL_QUORUM`.
3. Set the Spring gateway reply timeout shorter than the driver timeout in a **properly configured gateway test flow**, verifying the caller can time out before Cassandra finishes.
4. Compare with a driver timeout shorter than the reply timeout; record the **exception and elapsed time**.
5. Send invalid input (missing event ID, failed authorization) and confirm validation errors are not retried like transient database timeouts.
6. Verify the error channel and request/reply contract without treating a gateway timeout as proof Cassandra never processed the query.

**PASS:** the two timeout scopes operate independently and appear clearly in traces.

### Exercise G — JMS/Kafka acknowledgment across two channel types

1. Use a transacted JMS listener or test Kafka source feeding `OrderPaid(evt-6001)` into `DirectChannel` with an `async(false)` Cassandra handler.
2. Induce a Cassandra write error and **propagate the exception**, observing rollback/redelivery (JMS) or offset policy (Kafka) per configuration.
3. Switch to `ExecutorChannel` or an async Cassandra handler; verify the source **can finish its callback before database completion**.
4. Simulate a crash: Cassandra finishes writing, then the JVM crashes before JMS/offset commit; the broker redelivers the same `eventId`.
5. Confirm key/payload immutability prevents duplicate business side effects.
6. Route malformed events to quarantine/DLQ per policy without infinite retries.

**PASS:** accurately defines ACK/commit boundaries and durable replay design. Never claims transacted JMS forms an atomic transaction with Cassandra.

### Exercise H — LWT and serial consistency

1. Create `order_current_state` from section 13.
2. Insert the initial row via `INSERT ... IF NOT EXISTS`; read `[applied]`.
3. Run `UPDATE ... IF version = ?` with regular `LOCAL_QUORUM` and serial `LOCAL_SERIAL`, updating version 2 → 3.
4. Resend the same update when version is already 3; verify `[applied]=false`.
5. Induce a timeout and distinguish "not applied" from "uncertain due to timeout".
6. Measure LWT latency vs regular `INSERT` on the test cluster to decide whether LWT is truly justified for every event.

**PASS:** understands both consistency settings and handles `applied=false` as a business result rather than a transport exception.

### Minimum verification matrix

| Case | PASS outcome |
|---|---|
| RF=3, local quorum | Two local responses suffice when replicas are healthy |
| `ONE` vs `LOCAL_ONE` | Understands local scope and stale-read risk |
| `QUORUM` overlap | Explains `R+W>RF` within its exact scope |
| `ALL` | Recognizes reduced availability on replica loss |
| `ANY` | Not used for reads; never assumes read-after-write |
| Multi-DC | Distinguishes `LOCAL_QUORUM` from `EACH_QUORUM`/`QUORUM` |
| Driver timeout | Identifies `DriverTimeoutException` and total request deadline |
| Server timeout | Identifies coordinator-side read/write timeouts |
| `WriteOptions` | Applies to entity `INSERT`/`UPDATE`/`DELETE` in the right mode |
| Statement options | Configures CL/timeout on `Statement<?>` where appropriate |
| Sync/async | Knows when sources may ack before write completion |
| Timeout uncertainty | Keeps same `eventId` and reconciles rather than minting new IDs |
| LWT | Reads `wasApplied()`; separates result from transport error |
| Load control | Enforces concurrency caps and retry budgets |
| Observability | Measures error types, CL, RF, p99, and source backlogs |

**Limitations of mocks:** mocking `ReactiveCassandraOperations` or `CqlSession` only verifies the service calls the right APIs; it **cannot prove** replica ACKs, quorum intersection, server/driver timeouts, failover, LWT consensus, or whether an event persisted after a timeout. Those behaviors require real Cassandra/multi-node test clusters, and JMS/Kafka ack checks require an actual test broker.

## 19. Self-assessment questions

1. How do consistency level and request timeout solve two different problems?
2. With replication factor RF=3, how many copies of a partition exist in the example's local DC?
3. With RF=3, how many responses does `LOCAL_QUORUM` wait for?
4. With RF=5, what is quorum? What happens if two replicas do not respond?
5. Why can Cassandra forward writes to all replicas even at `CL=ONE`?
6. What does `R + W > RF` let you reason about? Does it automatically guarantee linearizability in every case?
7. Does choosing `LOCAL_QUORUM` for reads and writes in two different datacenters guarantee immediate visibility of new writes?
8. How do `ONE` and `LOCAL_ONE` differ in multi-DC clusters?
9. How does `QUORUM` differ from `LOCAL_QUORUM` in the replica set considered?
10. Is `EACH_QUORUM` better suited for writes or reads, and what is the trade-off when one DC fails?
11. Why can `CL=ALL` increase write latency and reduce availability?
12. Can `ANY` be used for `SELECT`? Does a successful `ANY` write guarantee a `ONE` read immediately sees the row?
13. For which Cassandra operations are `SERIAL` and `LOCAL_SERIAL` used?
14. Does an LWT still need a regular consistency level alongside its serial consistency level?
15. How does `DriverTimeoutException` differ from `WriteTimeoutException` and `UnavailableException`?
16. Given `WriteTimeoutException received=1, required=2`, what do you know for certain and what remains unknown?
17. Does Driver 4.x `basic.request.timeout` include retries and speculative executions?
18. Does `Statement.setTimeout(Duration)` change Cassandra server `write_request_timeout`?
19. Does increasing `MessageChannel.sendTimeout` rescue a CQL request that already hit its driver timeout?
20. Why doesn't Reactor `timeout(...)` roll back a remote Cassandra mutation that already happened?
21. What advantage do execution profiles offer over mutating a singleton template per request?
22. Which Spring Integration Cassandra modes use `WriteOptions.consistencyLevel/timeout`?
23. When `statementFunction(...)` returns a `SimpleStatement`, where must CL/timeout be configured?
24. Is `CassandraMessageHandler` sync or async by default, and how does that affect `send()`?
25. Why doesn't a one-way Spring Integration outbound adapter return `[applied]` like a gateway?
26. If a JMS broker already committed and an async Cassandra write fails, can the source message be rolled back?
27. When Cassandra writes successfully yet the JVM crashes before JMS commit, which fields must redelivery preserve?
28. Why is minting a new `eventId` on each retry dangerous?
29. Does calling `setIdempotent(true)` automatically add a database unique constraint or idempotency inbox?
30. Why are counter increments usually unsafe for blind retries?
31. When does a `WriteTimeoutException` require reconciliation instead of reporting "write failed completely"?
32. Which business assumptions break if you lower CL from `LOCAL_QUORUM` to `ONE` just to cut error counts?
33. How can speculative execution amplify traffic, and why must it stay off for non-idempotent mutations?
34. Why does raising Cassandra request timeouts fail to cure a hot partition?
35. Name five metrics that help distinguish cluster overload, stale reads, and driver timeouts.
36. Why can't a mocked Cassandra client prove quorum behavior and failover?

## 20. Official references

- [Apache Cassandra — Dynamo Architecture: Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo): replication, CL, quorum, `R+W>RF`, and timestamp conflict resolution.
- [Apache Cassandra — Managing and Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): client request timeouts, unavailable, failures, read/write latency, table/node metrics.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): replication strategies, partition/primary keys, keyspace layout.
- [Apache Cassandra — Lightweight Transactions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): conditional operations, applied results, and Cassandra LWT semantics.
- [Apache Cassandra Java Driver 4.19 — Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): `basic.request.timeout`, `basic.request.consistency`, execution profiles, and programmatic config.
- [Apache Cassandra Java Driver 4.19 — Upgrade Notes](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): driver request timeouts including retries and speculative executions.
- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): retry policies, error-specific actions, and consistency-downgrading warnings.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): idempotency, extra attempts, timeouts, and request amplification.
- [Apache Cassandra Java Driver API — DriverTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/DriverTimeoutException.html): client-side request timeout.
- [Apache Cassandra Java Driver API — UnavailableException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/UnavailableException.html): required/alive CL and server responses.
- [Apache Cassandra Java Driver API — WriteTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html): coordinator-side write timeout and `WriteType`.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): per-operation consistency, timeout, serial consistency, TTL, and idempotency.
- [Spring Data Cassandra API — WriteOptionsBuilder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.WriteOptionsBuilder.html): `consistencyLevel`, `timeout`, `executionProfile`, and builder API.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, lazy publishers, and reactive error handling.
- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): Cassandra outbound channel adapter/gateway, `CassandraMessageHandler`, async default.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `writeOptions`, `statementFunction`, and `query`/`parameter`.

**Key takeaway:** **Consistency level** governs **how many replica responses are required**, whereas **timeout** governs **how long a layer waits for the outcome**. `LOCAL_QUORUM` at RF=3 requires two ACKs in the local DC, yet creates no atomic transaction with JMS/Kafka and does not guarantee remote DC convergence. **Timeouts never prove Cassandra did not write.** In Spring Integration, configure CL/timeouts at the right layer (driver statement, Spring Data `WriteOptions`, gateway/channel), remember `CassandraMessageHandler` defaults to async, keep business `eventId` stable, bound retries/backpressure, and test failures and acknowledgments against a real cluster before production.







