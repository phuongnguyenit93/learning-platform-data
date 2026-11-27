# Retrying unavailable and timeout errors in Cassandra message flows

## 1. Real-world problem: one event, three kinds of failures

An application receives `OrderPaid` over JMS, transforms it into a Spring Integration `Message<OrderPaidEvent>`, and writes it to Apache Cassandra. During peak traffic, the system observes:

- `UnavailableException` when too few replicas are available for `LOCAL_QUORUM`.
- `WriteTimeoutException` when the coordinator dispatched the mutation yet did not collect enough responses.
- `DriverTimeoutException` when the Java Driver hit its request deadline while Cassandra's mutation state remained unknown.

If a team simply wraps every error in `retry(10)`, thousands of JMS messages can multiply into tens of thousands of Cassandra requests. Conversely, acknowledging the JMS message as succeeded after seeing a timeout risks dropping events whose writes never finished.

**The core question is not "how many retries", but:** which layer failed, what might Cassandra have done already, is the operation safe to repeat, how much deadline remains, and when will the source system acknowledge?

This lesson, **Retrying unavailable and timeout errors**, belongs to the **Adapter Cassandra** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems into Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing exchanges with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. This lesson focuses on Cassandra retries as messages flow from upstream sources to adapters or gateways.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, `DriverTimeoutException`, and transport/abort errors.
2. Explain consistency levels, replication factors, coordinators, and fields like `required`, `alive`, `received`, and `blockFor`.
3. Understand **when** Java Driver 4.x's `DefaultRetryPolicy` retries and **when it does not**.
4. Evaluate idempotency for `INSERT`, `UPDATE`, LWT, batches, and counters before enabling retries.
5. Configure driver request timeouts, consistency, execution profiles, and per-statement options.
6. Place retries **deliberately** at the driver, Reactor/Spring service, or JMS/Kafka broker layer without causing retry storms.
7. Design Spring Integration Cassandra flows with clear error propagation and acknowledgment boundaries.
8. Build test matrices covering node failures, server/client timeouts, lost responses, and redeliveries.

## 2. Cassandra writes cross multiple boundaries

~~~mermaid
flowchart LR
    S["HTTP/JMS/Kafka source"] --> I["Spring Integration inbound endpoint"]
    I --> M["MessageChannel + validator/transformer"]
    M --> H["CassandraMessageHandler"]
    H --> O["ReactiveCassandraOperations"]
    O --> D["Java Driver CqlSession"]
    D --> C["Cassandra coordinator"]
    C --> R1[("Replica A")]
    C --> R2[("Replica B")]
    C --> R3[("Replica C")]
    R1 -. "ACK" .-> C
    R2 -. "ACK" .-> C
    R3 -. "ACK" .-> C
    C -. "Success/error/timeout" .-> D
~~~

Suppose the keyspace uses replication factor `RF=3` in one datacenter with write consistency `LOCAL_QUORUM`. The coordinator needs responses from **two of the three local replicas** to report write success at the requested consistency. When only one replica responds before the deadline, the coordinator may throw `WRITE_TIMEOUT`; that **does not negate** that the responding replica already applied the mutation.

### 2.1. Five outcomes often lumped together as "DB error"

| Client-side outcome | What Cassandra may have done | Safe conclusion |
|---|---|---|
| Write success | Collected enough ACKs for CL | Operation met CL at response time; not atomic with broker |
| `UNAVAILABLE` | Coordinator knew too few replicas were alive for CL | CL unmet; no justification to silently lower CL |
| `WRITE_TIMEOUT` | Mutation may have reached one or more replicas | Uncertain outcome; never assume rollback |
| `DRIVER_TIMEOUT` | Request may still be queued, running, or finished | Client did not receive a result within its deadline |
| Network closed / aborted | Coordinator may have received the mutation before drop | Never assume the write did not occur |

For **reads**, a timeout likewise never proves a row is absent. The API layer must not convert every Cassandra read timeout into HTTP `404 Not Found` or `Mono.empty()`, because "not found" differs fundamentally from "unable to confirm read outcome".

### 2.2. No automatic distributed transaction

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant SI as Integration flow
    participant DB as Cassandra
    Broker->>SI: Deliver evt-9001
    SI->>DB: INSERT evt-9001
    DB-->>SI: Mutation completed yet response was lost
    Note over SI,DB: Client sees timeout; state is uncertain
    SI-->>Broker: Rollback / nack per policy
    Broker->>SI: Redeliver evt-9001
    SI->>DB: Retry with same primary key/payload
    DB-->>SI: Success
    SI-->>Broker: Commit/ack
~~~

Success in Cassandra **does not commit the JMS session**. Likewise, Kafka offset commits share no transaction with Cassandra writes. When an upstream source redelivers after Cassandra succeeded, the application needs a **stable event ID and idempotent mutation** to avoid duplicate side effects.

## 3. Replication factor, consistency, and "unavailable"

### 3.1. Replication factor (RF) is not consumer count

Example test cluster with three Cassandra nodes in datacenter `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

RF=3 means Cassandra keeps replicas of each partition across **three nodes per replication strategy**, not three JMS consumers or three Kafka partitions. In a single-node Testcontainers setup with RF=1, you cannot use that lab to demonstrate losing one of three replicas.

With `LOCAL_QUORUM` and RF=3:

\[
Q = \left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

| Consistency level | Required responses (RF=3, single DC) | Primary risk |
|---|---:|---|
| `LOCAL_ONE` | 1 local replica | Reads may miss recent writes |
| `ONE` | 1 replica | Cross-DC reach depending on topology/routing |
| `LOCAL_QUORUM` | 2 local replicas | Fails if two replicas are unresponsive |
| `QUORUM` | 2 replicas keyspace-wide in single-DC example | Differs from `LOCAL_QUORUM` in multi-DC |
| `ALL` | 3 replicas | Slow/failed replicas hurt availability |

In multi-DC deployments, `LOCAL_QUORUM` computes quorum from the **local datacenter's RF**, not the sum of all cluster replicas. A `LOCAL_QUORUM` write in dc1 does not mean a `LOCAL_QUORUM` read in dc2 sees the data immediately; cross-DC replication may lag.

### 3.2. Why does the coordinator throw UnavailableException?

`UNAVAILABLE` normally occurs when the coordinator **knows upfront** from cluster state that fewer live/reachable replicas exist than **required by the CL**.

~~~text
RF=3, CL=LOCAL_QUORUM
required = 2
alive    = 1

Coordinator: cannot satisfy LOCAL_QUORUM immediately
             -> UNAVAILABLE
~~~

`UnavailableException` carries metadata for `consistencyLevel`, `required`, and `alive` (accessor names depend on driver version). These values help diagnose **why CL could not be met**, without proving what data does or does not reside on individual replicas.

### 3.3. Why not silently switch LOCAL_QUORUM to ONE?

If a domain guarantees **read-after-write** based on R/W quorum overlap, dropping write CL to `ONE` breaks that guarantee. For example:

~~~text
RF=3, write ONE: A ACKs.
Read QUORUM: B and C return stale data before convergence.

The write may have been reported "successful" to the app,
yet an immediate read misses it.
~~~

`ConsistencyDowngradingRetryPolicy` may try weaker CLs in some cases, yet driver documentation warns it can **break invariants and violate datacenter locality**. For payment/audit events, keep intentional CLs and handle availability via retries, backoff, and reconciliation instead of silent downgrades.

## 4. Distinguishing Unavailable, server timeouts, and driver timeouts

| Exception / signal | Origin | When? | What to inspect |
|---|---|---|---|
| `UnavailableException` | Cassandra coordinator | Not enough live replicas for CL at dispatch | `required`, `alive`, DC/RF, coordinator view |
| `ReadTimeoutException` | Cassandra coordinator | Not enough read responses/data on time | `received`, `blockFor`, `dataPresent` |
| `WriteTimeoutException` | Cassandra coordinator | Not enough write ACKs on time | `received`, `blockFor`, `WriteType` |
| `ReadFailureException` | Cassandra server | Non-timeout read processing error | Replica failures, logs, retry safety |
| `WriteFailureException` | Cassandra server | Non-timeout write processing error | Outcome uncertainty, write type |
| `DriverTimeoutException` | Java Driver client | **Total request deadline** expired | Driver queue, network, retries, server response |
| `ClosedConnectionException` / heartbeat error | Driver transport | Connection dropped before response | Request may already have reached server |
| `OverloadedException` | Cassandra server | Node overloaded | Reduce concurrency; avoid retry storms |
| `RequestThrottlingException` | Java Driver throttler | Not allowed to execute/enqueue | App is overloading driver; consider failing fast |
| `InvalidQueryException` / `UnauthorizedException` | Cassandra server | Invalid CQL/schema/permissions | Permanent until config/schema is fixed |

### 4.1. ReadTimeout: enough responses, missing actual data

Cassandra reads may ask one replica for **data** and others for **digests**. If enough replicas respond yet none supplied the actual data response, the coordinator can still return `ReadTimeoutException`.

~~~text
Read CL=QUORUM, RF=3, blockFor=2
received=2, dataPresent=false

Two responses do not automatically mean the required data arrived.
~~~

Consequently, the driver's `DefaultRetryPolicy` can **retry the same coordinator once** specifically when `received >= blockFor && !dataPresent`, while most other read timeouts are rethrown to the caller.

### 4.2. WriteTimeout: `writeType` governs retry behavior

Server-side write timeouts include `WriteType` metadata. Values can include `SIMPLE`, `BATCH`, `UNLOGGED_BATCH`, `BATCH_LOG`, `COUNTER`, and `CAS` depending on Cassandra/driver version.

**Easy-to-miss trap:** Java Driver 4.x's `DefaultRetryPolicy` does not automatically retry every `WriteTimeoutException` for an `INSERT`. By default it only considers **one retry on the same coordinator for `BATCH_LOG`** when the query is idempotent, due to batchlog mechanics. For `SIMPLE` write timeouts, the driver normally **rethrows** so the application handles the uncertain outcome.

### 4.3. DriverTimeout does not mean coordinator WriteTimeout

`basic.request.timeout` in Java Driver 4.x is the **deadline for the entire client-side request**, including retries and speculative executions. With a driver throttling queue, a request can even time out **before ever reaching a Cassandra node**.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant D as Driver
    participant C as Coordinator
    App->>D: Execute INSERT (deadline 2s)
    D->>C: Request
    C-->>D: May respond late
    Note over D: Client-side deadline expires
    D-->>App: DriverTimeoutException
    Note over C: Mutation may already have applied or still be processing
~~~

**Never deduce from `DriverTimeoutException` that the coordinator emitted `WRITE_TIMEOUT`.** Driver timeouts and server timeouts live at different layers and occur under different conditions.

### 4.4. Timeouts outside Cassandra

Spring `sendTimeout`, Spring gateway `replyTimeout`, HTTP caller deadlines, Reactor `timeout(Duration)`, JMS transaction boundaries, and Kafka poll/offset lifecycles are all **distinct** from driver timeouts.

If a Spring gateway expires after 1.5 seconds while the Cassandra request runs up to 3 seconds, the caller sees a timeout **even if the database finishes afterward**. Canceling a subscription or client wait never rolls back a mutation that reached Cassandra.

## 5. How does Java Driver 4.x `DefaultRetryPolicy` work?

The Java Driver has a **request-level retry policy**, configured via `advanced.retry-policy`. `DefaultRetryPolicy` is the default and retries **select high-probability cases** rather than every error. The driver also has internal rules such as trying the next node when a request **could not even write bytes to the network**; those do not always route through retry-policy callbacks.

### 5.1. Policy decisions

| Error signal | Typical `DefaultRetryPolicy` 4.19 behavior | Why? |
|---|---|---|
| `UNAVAILABLE` | Up to one retry on the **next node** in the query plan | First coordinator may have a stale view due to network isolation |
| `READ_TIMEOUT`, enough responses, no data | Up to one retry on the **same coordinator** | Can re-select a replica to supply full data |
| `READ_TIMEOUT`, insufficient responses | Rethrow | No sign retrying at the same CL will succeed |
| `WRITE_TIMEOUT` of type `BATCH_LOG` | Up to one retry on the **same coordinator**, if idempotent | May overcome slow batchlog endpoints |
| `WRITE_TIMEOUT` of type `SIMPLE`/`COUNTER` | Rethrow | Mutation may already have applied; retrying risks duplicate effects |
| Connection closed / heartbeat request aborted | Try **next node** if idempotent | Unknown whether prior request applied |
| `OverloadedException`, `ServerError`, `TruncateException` | May try next node if policy allows | Another coordinator might succeed |
| `ReadFailureException`/`WriteFailureException` | Usually rethrow | Often unsafe to retry blindly |
| Invalid query/authorization/codec mismatch | Fail/rethrow | Cannot be fixed by retrying identical input |

**Important scope:** these rules describe Driver 4.19. `DefaultRetryPolicy` generally requires requests to be marked **idempotent** before allowing retries where the operation might already have reached the server. Some hard-coded driver paths before network writes do not require that flag. **Do not treat this table as an exact guarantee for every exception across every version.**

### 5.2. `RetryVerdict` API: avoid old callbacks

Driver 4.10+ introduced callbacks returning `RetryVerdict` on `RetryPolicy`:

~~~java
// API signatures (illustrative, not a complete implementation class):
onUnavailableVerdict(
    Request request, ConsistencyLevel cl,
    int required, int alive, int retryCount);

onReadTimeoutVerdict(
    Request request, ConsistencyLevel cl,
    int blockFor, int received,
    boolean dataPresent, int retryCount);

onWriteTimeoutVerdict(
    Request request, ConsistencyLevel cl,
    WriteType writeType,
    int blockFor, int received, int retryCount);

onRequestAbortedVerdict(
    Request request, Throwable error, int retryCount);

onErrorResponseVerdict(
    Request request, CoordinatorException error, int retryCount);
~~~

The older `onUnavailable(...)`, `onReadTimeout(...)`, and `onWriteTimeout(...)` methods returning `RetryDecision` were **deprecated** in 4.10. If you must write a custom policy, use the current API, bound attempts, and document every verdict. **Most applications need no custom retry policy**; the default is usually safer than a policy retrying every exception.

### 5.3. Why never enable `ConsistencyDowngradingRetryPolicy`?

This policy can report "success" for a write with just one replica ACK even though CL asked for quorum, or read at a weaker CL. Quorum-based business invariants **break**, and local datacenter locality can be violated.

**Never enable `ConsistencyDowngradingRetryPolicy` on payments, audits, access control, or any flow requiring specific CL guarantees** merely to reduce exception rates. If a use case truly allows eventual stale reads, select the appropriate CL in the business contract and monitor its behavior.

## 6. Idempotency is a precondition for retries, not an outcome of retries

In Cassandra, an **idempotent operation** leaves the database in an equivalent state if executed repeatedly as when executed once (accounting for semantics and concurrent writes). The driver **does not automatically know** the business contract of your CQL statements.

### 6.1. Two layers of idempotency

| Layer | Example | Cannot achieve alone |
|---|---|---|
| **CQL statement idempotency** | `INSERT` with same primary key and values | Ensuring external emails/HTTP side effects run only once |
| **Business event idempotency** | Immutable `eventId` across JMS redelivery/Kafka replay | Making two Cassandra tables commit atomically together |

A statement can be idempotent in Cassandra while the overall workflow is non-idempotent—for instance, inserting the same row and then firing another email on every replay.

### 6.2. Idempotency evaluation matrix

| CQL/business operation | Safe for automatic retry? | Required conditions |
|---|---|---|
| `SELECT` by primary key | Usually yes | Later reads may observe newer concurrent writes |
| Immutable `INSERT` with fixed `event_id` and values | Conditionally | Payload, primary key, and timestamp/TTL semantics fixed |
| `UPDATE SET state = 'PAID'` | Conditionally | Protected against stale overwrites from concurrent versions |
| `UPDATE list = ['x'] + list` | **No** | Repeating prepends the item twice |
| Cassandra counter `+1` | **No** | Retries can increment twice |
| `INSERT ... IF NOT EXISTS` | Only with LWT result handling | `applied=false` must separate duplicates from conflicts |
| Multi-partition batch | Depends on mutations | **All** constituent mutations must be safe to repeat |
| Sending HTTP/payment/email after Cassandra write | Not automatically idempotent | Needs downstream idempotency keys / durable outbox |

### 6.3. `setIdempotent(true)` is only metadata for the driver

Example storing `OrderPaid` as an immutable row:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement insert = SimpleStatement.newInstance(
        "INSERT INTO shop_integration.order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "evt-9001", "ORD-9001", "OrderPaid",
        "{\"eventId\":\"evt-9001\",\"amountMinor\":150000}"
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setTimeout(Duration.ofSeconds(3))
 .setIdempotent(true);

session.execute(insert);
~~~

Built-in statement setters in Java Driver 4.x are **immutable**, returning a new statement; chaining preserves changes. `setIdempotent(true)` tells the driver the application considers this operation **safe to retry**—it **creates neither a unique constraint nor a deduplication inbox**.

### 6.4. Never mark every statement idempotent in global config

Driver option:

~~~hocon
datastax-java-driver {
  basic.request.default-idempotence = false
}
~~~

Java Driver 4.x defaults to `false`. Mark **individual statements** or specific execution profiles once semantics are verified. Setting `basic.request.default-idempotence = true` globally in a system containing counters, list appends, external side effects, or replay-varying values causes unsafe retries.

### 6.5. Why sharing a primary key still does not guarantee end-to-end idempotency

Suppose a retry uses the same `event_id`, yet the consumer:

- Recomputes `occurredAt = Instant.now()`, shifting event data/timeline.
- Builds a different `payloadJson` (with retry timestamps, random tokens, or volatile fields).
- Writes a fresh `USING TTL 86400`, extending expiration relative to the first write.
- Writes a second projection table and crashes between the two writes.
- Fires a payment/email call on every success.

In those cases, **Cassandra upserts are no longer enough** to ensure once-only business effects. You need durable event identity, immutable payloads, explicit TTL/timestamp policies, and recovery/reconciliation for downstream steps.

## 7. Retry budgets belong to the entire workflow

A single message can pass through multiple retry layers:

~~~mermaid
flowchart TD
    A["JMS/Kafka source"] --> B["Spring Integration handler"]
    B --> C["Service retry / Reactor retryWhen"]
    C --> D["Java Driver RetryPolicy"]
    D --> E["Cassandra coordinator / replicas"]
    E -. "Timeout/error" .-> D
    D -. "Failed request" .-> C
    C -. "Exhausted" .-> B
    B -. "Throw/rollback" .-> A
    A -. "Redelivery/replay" .-> B
~~~

### 7.1. Retry multiplication

Suppose a JMS message allows up to **5 deliveries**, the service runs up to **3 attempts per delivery** (initial + two retries), and the driver performs up to **2 executions** per eligible request. The theoretical upper bound in that scenario reaches:

\[
5 \times 3 \times 2 = 30 \text{ Cassandra executions}
\]

This is **illustrative**; not every exception triggers driver retries, while speculative execution can add further attempts if enabled. At 1,000 messages/s during cluster overload, retry multiplication drives Cassandra into a **feedback loop** that worsens the outage.

### 7.2. Pick one layer to own long-term retries

For inbound JMS/Kafka flows, a manageable division of labor is typically:

1. **Driver `DefaultRetryPolicy`** handles the few safe network/coordinator failures within the single-request budget.
2. **Application service retries** apply only to a small subset of transient failures, with backoff/jitter and capped attempts.
3. **Broker redelivery / retry topics** handle durable retries across outages or crashes, with max-retry limits and DLQs.
4. **Reconciliation** resolves uncertain timeout outcomes by checking primary-key state rather than blindly retrying.

When the broker already provides durable delayed retries, stacking multiple `retryWhen` loops in the service is often unnecessary. When no broker retry exists, build durable recovery rather than sleeping indefinitely inside a message listener.

### 7.3. When never to retry?

Never retry the same input on `InvalidQueryException`, missing keyspaces/tables, missing Cassandra permissions, invalid JSON schemas, converter/codec mismatches, or missing `eventId`. These are fixed only by **changing contracts, migrations, config, or code**.

Even for infrastructure `UNAVAILABLE` errors, retries help only if the cluster can recover within the workflow's remaining deadline/budget. If two replicas needed for quorum are down for minutes, retrying 100 times in one second wastes resources.

## 8. Configuring Java Driver: timeouts, CL, retry policy, and execution profiles

### 8.1. `application.conf`

Java Driver 4.x uses HOCON configuration under `datastax-java-driver`:

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
    default-idempotence = false
  }

  advanced.retry-policy.class = DefaultRetryPolicy
  advanced.speculative-execution-policy.class = NoSpeculativeExecutionPolicy
}
~~~

**Values are illustrative** for a cluster with matching replication/topology. `LOCAL_QUORUM` cannot invent extra replicas when a test cluster has only one node. A 3-second timeout does not change Cassandra's `read_request_timeout`/`write_request_timeout` or an HTTP client's deadline.

The driver already defaults to `DefaultRetryPolicy` and disabled speculative execution; the last two lines can often **be omitted**. They are shown explicitly here so retry choices are visible rather than implicit.

### 8.2. Execution profiles separating reads and writes

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
  profiles {
    event-write {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
    }
    analytical-read {
      basic.request.consistency = LOCAL_ONE
      basic.request.timeout = 1500 milliseconds
    }
  }
}
~~~

`analytical-read` fits only when the business **tolerates stale reads**; never use it on endpoints requiring read-after-write under quorum invariants. Profiles must be chosen **by server-verified use cases**—never let an untrusted HTTP header drop CL to `ONE`.

### 8.3. Per-statement timeout and idempotency

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement select = SimpleStatement.newInstance(
        "SELECT event_id, event_type "
        + "FROM shop_integration.order_event WHERE event_id = ?",
        "evt-9001");

select = select
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true);

var result = session.execute(select);
~~~

`SimpleStatement`/`BoundStatement` in Driver 4.x are **immutable**. Setters return a **new statement**; discarding the return value leaves old settings intact. Use builders or reassign as shown. Key-based `SELECT`s are generally safe to retry, though subsequent reads can reflect concurrent writes.

### 8.4. PreparedStatement and immutable BoundStatement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
        "INSERT INTO shop_integration.order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)");

BoundStatement statement = prepared.bind(
        event.eventId(),
        event.orderId(),
        event.eventType(),
        event.payloadJson());

statement = statement
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true);

session.execute(statement);
~~~

This is a fragment inside a DAO with `session` and a validated `event` DTO. Setting `idempotent=true` is valid only if **`eventId`, primary key, payload, and TTL/write-timestamp policies** remain stable. `PreparedStatement` can be reused across requests, while each event gets its own `BoundStatement`; never share a mutable builder across concurrent consumers.

### 8.5. Inspecting effective config

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

DriverExecutionProfile profile = session.getContext()
        .getConfig()
        .getDefaultProfile();

System.out.println("requestTimeout="
        + profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
System.out.println("consistency="
        + profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY));
System.out.println("defaultIdempotence="
        + profile.getBoolean(DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE));
~~~

For named execution profiles, inspect `session.getContext().getConfig().getProfile("event-write")` instead of checking only the default profile. Spring Boot or custom `CqlSession` builders can override `application.conf`; **a file's mere presence does not prove its options took effect**.

### 8.6. Driver timeout spans more than wire time

~~~text
request deadline starts
   |
   +-- driver throttling queue / borrow connection
   +-- first coordinator attempt
   +-- optional retry on another/same coordinator
   +-- optional speculative execution (if enabled)
   +-- response handling
   |
   +-- deadline expires -> DriverTimeoutException
~~~

In Driver 4.x, `basic.request.timeout` covers the **entire request**, never resetting to 3 seconds per retry. A request can even expire before leaving the local queue. That is why raising retry counts rarely helps when queues or clusters are already saturated.

## 9. Spring Data Cassandra: configuring write timeouts on the right operation

Spring Data Cassandra provides `ReactiveCassandraOperations`, `CqlTemplate`, and options for CQL/entity operations. `WriteOptions` extends query options, covering consistency, timeouts, and idempotency per your Spring Data version's API.

### 9.1. Entity with an immutable business ID

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEventRow(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {}
~~~

This example uses explicit column names to avoid `NamingStrategy` surprises. If the schema adds `tenantId`, timestamps, or a composite partition key, update fields, annotations, and mappers accordingly rather than assuming `eventId` alone serves every query.

### 9.2. WriteOptions with CL and deadline

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Configuration
class CassandraWritePolicyConfiguration {

    @Bean
    WriteOptions immutableEventWriteOptions() {
        return WriteOptions.builder()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .timeout(Duration.ofSeconds(3))
                .idempotent(true)
                .build();
    }
}
~~~

Set `idempotent(true)` only when the DAO/flow genuinely writes an **immutable event** matching the contract in section 6. For counter increments, list appends, and non-idempotent mutations, choose different options and disable automatic retries.

### 9.3. Cassandra outbound channel adapter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow persistImmutableOrderEvents(
        ReactiveCassandraOperations operations,
        WriteOptions immutableEventWriteOptions) {

    return IntegrationFlow.from("validatedOrderEventRows")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(immutableEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`validatedOrderEventRows` accepts Spring Messages carrying an **`OrderEventRow` with `@Table`**, not arbitrary JSON Strings. `WriteOptions` applies to entity `INSERT`/`UPDATE`/`DELETE` modes; when the handler receives a driver `Statement<?>` via `statementFunction(...)`, set CL/timeout/idempotency directly on that statement or its execution profile.

**Spring Integration's `CassandraMessageHandler` defaults to async.** `endpoint.async(false)` waits for completion on synchronous paths (e.g., `DirectChannel`) so Cassandra errors can propagate to upstream listeners. It does **not** merge Cassandra and JMS into an atomic transaction.

### 9.4. Why not mutate WriteOptions on a singleton per message?

CL and timeouts are **application policies**. If an HTTP source sends `"consistency": "ANY"`, never let that header mutate shared singleton template/handler options; it would break read-after-write guarantees across concurrent tenants. Use separate server-configured execution profiles or flows per use case.

### 9.5. When an app uses imperative or reactive services directly

If an app uses a `@ServiceActivator` calling a custom DAO, it may:

- Use `CqlSession.execute(Statement<?>)` and catch driver exceptions.
- Use `ReactiveCassandraOperations.insert(entity)` returning reactive publishers.
- Use `CqlTemplate`/`ReactiveCqlTemplate` which translate errors into `DataAccessException`.

**Never assume the top-level exception is always a raw driver exception class.** Spring Data performs exception translation; inspect the cause chain to classify failures accurately.

## 10. Bounded service-layer retries with Reactor

Service-layer retries help when the source is an HTTP request or workflow needing a couple of quick attempts before falling back to broker delayed retries. Enable them **only after proving idempotency** and aligning retry budgets with the driver and broker.

### 10.1. Classifying transient failures along the cause chain

~~~java
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

public final class CassandraRetryClassifier {
    private CassandraRetryClassifier() {}

    // ONLY use for operations proven idempotent.
    public static boolean forImmutableEventWrite(Throwable error) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 12;
                depth++, current = current.getCause()) {
            if (current instanceof UnavailableException
                    || current instanceof WriteTimeoutException
                    || current instanceof DriverTimeoutException
                    || current instanceof OverloadedException) {
                return true;
            }
        }
        return false;
    }
}
~~~

This function is an **example policy** for immutable event `INSERT`s. `WriteTimeoutException`/`DriverTimeoutException` have **unknown outcomes**; retrying is permissible solely because the business key and payload are proven immutable, not because timeouts are safe for all writes. For counters/appends, the classifier must return `false` on unknown-outcome paths; for `SELECT` reads, define a separate classifier.

Never apply `forImmutableEventWrite` to LWTs, counters, HTTP calls, or batches containing non-idempotent mutations. Nor does it distinguish every infrastructure state (e.g., session closed during shutdown); production needs budgets, cancellation, liveness checks, and domain rules.

### 10.2. `Retry.backoff` in a reactive service

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ImmutableOrderEventWriter {

    private final ReactiveCassandraOperations operations;

    public ImmutableOrderEventWriter(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> save(OrderEventRow row) {
        if (row == null || row.eventId() == null
                || row.eventId().isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "eventId is required"));
        }

        return Mono.defer(() -> operations.insert(row).then())
                .retryWhen(Retry.backoff(
                            2, Duration.ofMillis(250))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.4)
                        .filter(CassandraRetryClassifier::forImmutableEventWrite));
    }
}
~~~

`Retry.backoff(2, ...)` means up to **two retries after the initial attempt**, not two total attempts. `Mono.defer(...)` builds a fresh publisher on every subscription/attempt; `row` data must remain **immutable** across attempts.

**You may not even need this retry inside a JMS listener that already has broker redelivery/retry topics.** This pattern fits flows needing short in-service retries and must be budgeted alongside driver attempts and source redeliveries to avoid storms.

### 10.3. Never block a Reactor/WebFlux event loop

~~~java
// DO NOT DO THIS on a reactive event loop:
writer.save(row).block();
~~~

In WebFlux or reactive integration, return the `Mono` to the framework and wire acknowledgment/completion to reactive signals. For synchronous JMS listeners that must wait for DB completion, use a sync endpoint/path or an explicit boundary rather than calling `block()` randomly without knowing the threading model.

### 10.4. Reactor timeouts do not roll back Cassandra

~~~java
Mono<Void> withinBusinessDeadline =
        writer.save(row).timeout(Duration.ofSeconds(4));
~~~

If Reactor emits `TimeoutException` after 4 seconds, downstream work may have already reached the coordinator. Subscription cancellation and DB rollback are completely separate concepts. Any replay must keep the same `eventId` and reconcile uncertain outcomes.

## 11. Spring Integration: where to place retries in a message flow?

A Spring Integration flow can chain transformers, filters, routers, `DirectChannel`, `ExecutorChannel`, gateways, and the Cassandra outbound adapter. **No single Cassandra retry policy covers all of them**. Decide explicitly whether retries replay the **whole message**, only the **Cassandra call**, or also **downstream side effects**.

### 11.1. Synchronous flow to propagate errors

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraEventIntegrationConfig {

    @Bean
    public IntegrationFlow persistOrderEvents(
            ReactiveCassandraOperations operations,
            WriteOptions immutableEventWriteOptions) {

        return IntegrationFlow.from("orderEventsReadyForDb")
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT)
                        .writeOptions(immutableEventWriteOptions),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Input `orderEventsReadyForDb` expects a Spring Message containing an **`OrderEventRow`** with Cassandra `@Table`/`@PrimaryKey`, not a raw JSON String. With a `DirectChannel` and `async(false)` handler, Cassandra exceptions propagate back to the sending thread.

**Note:** this is a one-way write flow, returning no `CassandraWriteResult` upstream like an outbound gateway; therefore do not rely on `replyChannel` to determine write success. Observe success/failure via endpoint completion/exceptions and source policies.

### 11.2. Transforming JSON or business events before writing

~~~java
@Bean
public IntegrationFlow mappedOrderEvents(
        ReactiveCassandraOperations operations,
        WriteOptions immutableEventWriteOptions,
        OrderEventMapper mapper) {

    return IntegrationFlow.from("validatedDomainOrderEvents")
            .transform(OrderPaidEvent.class, mapper::toRow)
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(immutableEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

This is an **alternative** to section 11.1 (taking a DTO instead of an entity); do not attach both flows to the same channel expecting single writes. `OrderEventMapper` and `OrderPaidEvent` are application-defined domain types. The mapper must:

- Validate `eventId`/`tenantId`/`orderId`/version.
- Preserve `eventId` and immutable data across retries.
- Normalize timestamps per contract (UTC, CQL millisecond precision when using `timestamp`).
- Avoid minting random IDs or substituting current time into primary-key components on replay.
- Avoid serializing secrets or extraneous headers into the row.

### 11.3. How does `DirectChannel` differ from `ExecutorChannel`?

~~~text
Path A — synchronous:
  JMS listener
   -> DirectChannel
   -> Transformer
   -> Cassandra handler async(false)
   -> Cassandra completion/exception
   -> listener handles commit/rollback

Path B — asynchronous:
  JMS listener
   -> ExecutorChannel / in-memory QueueChannel
   -> listener returns/commits per config
   -> Cassandra handler runs later
   -> Cassandra may fail after JMS already committed
~~~

On Path B, `errorChannel` may receive an error message, yet **it cannot turn back time to roll back an already-completed JMS commit**. For resilient async processing, use a durable broker, inbox, or handoff with its own replay mechanism.

### 11.4. `errorChannel` is not "automatic retry"

In Spring Integration, `ErrorMessage` can be routed to `errorChannel` when errors arise in messaging infrastructure. Still:

1. Subscribing to `errorChannel` does not automatically retry Cassandra.
2. If an error handler **swallows the exception**, a transacted listener may treat the callback as successful.
3. If an error handler triggers a retry that eventually succeeds, the event may write multiple times; idempotency is mandatory.
4. An in-memory error channel **is not a durable DLQ** across process crashes.

Never catch all exceptions in a transformer and `return null`, because that blurs a permanent mapping error with a transient Cassandra timeout.

### 11.5. Do not apply retry advice blindly

Spring Integration supports endpoint retry advice, yet **not every endpoint shares the same semantics**. If a retry advice wraps a handler, know precisely what it retries:

- Only the database call, or also the mapper/validator?
- Does it re-trigger an upstream HTTP/email call?
- Can it receive synchronous exceptions from the Cassandra handler, or did the handler hand off asynchronously?
- Is Spring Retry's `RetryContext` and `RecoveryCallback` coordinated with broker redelivery?

With the default async Cassandra handler, synchronous advice that does not await publisher completion will **miss errors** emitted after the handler returns. Pick a sync boundary or a reactive pipeline with explicit error-signal/ack wiring.

## 12. JMS redelivery: when retries cause the source to deliver twice

### 12.1. A listener with a transacted session

Architectural example:

~~~mermaid
sequenceDiagram
    participant JMS as JMS Broker
    participant L as Message-driven listener
    participant SI as DirectChannel / Cassandra handler sync
    participant DB as Cassandra
    JMS->>L: Deliver OrderPaid evt-9001
    L->>SI: Send Message<OrderEventRow>
    SI->>DB: INSERT evt-9001 (LOCAL_QUORUM)
    alt Cassandra success
        DB-->>SI: Success
        SI-->>L: Handler returns
        L-->>JMS: Session commit
    else Cassandra unavailable/timeout
        DB-->>SI: Exception
        SI-->>L: Exception propagated
        L-->>JMS: Session rollback
        JMS->>L: Redelivery after delay per broker policy
    end
~~~

This is the **architectural target** when the listener uses a transacted session, a synchronous flow, and exceptions truly reach the container. Spring Integration does not force JMS rollback automatically for every error or configuration.

### 12.2. First failure window: DB wrote, JMS not yet committed

~~~text
t0   Broker delivers evt-9001
t1   Cassandra INSERT evt-9001 succeeds
t2   JVM crashes before JMS session commit
t3   Broker redelivers evt-9001
t4   Cassandra re-INSERTs same event_id and payload
~~~

If `event_id` is the Cassandra primary key and the mutation is an immutable upsert, retrying does not create a second row. If the consumer changes the event ID, bucket, or amount, data corrupts or duplicates. If an email is also sent after insert, that email needs its own idempotency.

### 12.3. Second failure window: JMS commits before DB completion

~~~text
t0   Broker delivers evt-9001
t1   Listener sends message to ExecutorChannel
t2   Listener returns, JMS commits
t3   Worker executes Cassandra INSERT
t4   Cassandra WriteTimeoutException
t5   Broker is no longer responsible for redelivering the committed message
~~~

To run asynchronously without losing work, implement a **durable handoff**: persist a record to a durable queue/inbox before committing, then let a worker retry Cassandra; or run an independent recovery job from the broker/source-of-truth.

### 12.4. Prefer delayed retries over hot retries inside the listener

If Cassandra loses quorum for several minutes, spinning in a tight retry loop inside the JMS listener pins threads and hammers the cluster. Instead:

- Let exceptions propagate so broker redelivery applies configured **delays/backoff**.
- Use tiered retry queues/destinations with max delivery caps.
- Route permanent failures to a DLQ/quarantine.
- Alert on queue depth, oldest message age, and delivery attempts.

Not all brokers share identical redelivery behavior; `JMSXDeliveryCount` and DLQ semantics are **provider/container-specific**. Test against your actual broker instead of assuming behavior.

### 12.5. JMS transactions do not encompass Cassandra

`sessionTransacted=true` (on a supporting listener container) governs only the JMS session transaction. It does not pull Cassandra writes into a two-phase transaction. Cassandra does not participate in standard RDBMS/JMS XA commits in normal flows. Thus **idempotent replay remains mandatory** even with synchronous error propagation.

## 13. Kafka retries, offset commits, and consumer liveness

Kafka record keys, partitions, and offsets identify log positions; they never automatically form Cassandra primary keys or transactions.

### 13.1. Committing offsets after database success

~~~text
Kafka poll record offset=120, eventId=evt-9001
    -> validate + Cassandra write
    -> write completion observed
    -> commit/ack offset per consumer/container policy
~~~

This is a common policy to reduce data loss when downstream fails. If the JVM crashes **after Cassandra succeeds yet before the offset commits**, Kafka replays offset 120; `eventId` and primary keys must remain deterministic.

### 13.2. Running async while committing offsets too early

~~~text
poll offset=120
    -> send to ExecutorChannel
    -> Kafka offset commit
    -> Cassandra write runs on executor
    -> driver timeout
    -> offset 120 already committed; automatic replay is no longer guaranteed
~~~

Never claim Kafka transactions or exactly-once producer semantics cover a Cassandra mutation. Kafka transactions only govern supported Kafka resources/protocols; Cassandra does not join a Kafka transaction.

### 13.3. Retry topics vs retrying inside the poll loop

Kafka frameworks offer error handlers, seek/replay, retry topics, and dead-letter topics. Choose based on **ordering and liveness** requirements:

- Retrying directly inside the consumer callback blocks the partition, risking poll timeouts and consumer-group rebalances.
- Retry topics enable durable delays yet can alter ordering among events for the same aggregate unless carefully designed.
- DLQs isolate poisoned records; post-fix replays must preserve `eventId`.
- For business state needing ordering, enforce `aggregateVersion`/conditional writes or key-serialized processing rather than relying purely on retry counts.

### 13.4. Kafka keys differ from Cassandra partition keys

A Kafka key `tenant42:ORD-9001` keeps an order's events in one Kafka partition, yet Cassandra token/replica placement depends on the **CQL partition key**. Any consumer-side hashing/sharding must stay deterministic across retries, deployments, and backfills. Never embed Kafka offsets or consumer partition assignments into Cassandra row keys if they change during replay.

## 14. LWT, CAS, and `applied=false` outcomes

Some events must **update current state by version** rather than simply appending history. When two Kafka/JMS events arrive out of order, a regular `UPDATE` with `LOCAL_QUORUM` will not stop an older event from overwriting newer state.

### 14.1. Current-state table example

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_state (
    order_id text PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);
~~~

A compare-and-set update:

~~~sql
UPDATE shop_integration.order_state
SET version = ?, state = ?, last_event_id = ?
WHERE order_id = ?
IF version = ?;
~~~

Cassandra LWT uses **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) alongside regular consistency for its respective phases. It costs more than normal writes and should be reserved for invariants genuinely needing compare-and-set.

### 14.2. Reading the applied result

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement conditional = SimpleStatement.newInstance(
        "UPDATE shop_integration.order_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE order_id = ? IF version = ?",
        3L, "SHIPPED", "evt-9003", "ORD-9001", 2L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

var result = session.execute(conditional);
boolean applied = result.wasApplied();
~~~

If `applied=false`, the server returned a **valid business result**: the stored version did not equal 2. Never blindly retry it as a transport error.

### 14.3. Three interpretations

| Result | Interpretation | Handling |
|---|---|---|
| `applied=true` | Conditional mutation applied | Confirm operation per policy |
| `applied=false`, stored version=3 and same event ID | Likely a replay already applied earlier | Reconcile and treat as valid duplicate if payload/version match |
| `applied=false`, higher stored version or different event ID | Conflicting/out-of-order state update | Classify as domain conflict; never hot-retry |
| Timeout during LWT | Unknown whether Paxos/condition completed | Read back/reconcile by key + version; bounded retry |

**Never** use a one-way `Cassandra.outboundChannelAdapter(...)` and equate `send(true)` with `wasApplied()==true`. When LWT outcomes are needed, use the driver API or an outbound gateway/service with a reply contract.

### 14.4. LWT does not solve broker atomicity

If an LWT applied right before a JVM crash prior to JMS commit, the same event redelivers. On replay, `IF version=2` returns `false` because stored version is already `3`. The application must recognize **that event ID already succeeded** rather than treating `false` as "definitely failed" and retrying endlessly.

## 15. Batches and counters: particularly risky retries

### 15.1. Logged batches are not SQL transactions

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9004', 'ORD-9001', 'OrderPaid', '{}');

    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9005', 'ORD-9002', 'OrderPaid', '{}');
APPLY BATCH;
~~~

For multi-partition **`LOGGED`** batches, Cassandra uses the batchlog to drive mutations to completion after coordinator failures. Still, partitions can **become visible at different times**, with no cross-partition snapshot isolation. On caller timeout, one or more mutations may already have applied, or Cassandra may be replaying the batchlog.

`WriteTimeoutException` with `WriteType.BATCH_LOG` is the special case where `DefaultRetryPolicy` considers one retry if the request is idempotent. **Do not blindly enable retries on every multi-partition batch** because of that: evaluate every mutation, batch size, and timeout budget.

### 15.2. UNLOGGED batches can partially apply

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9006', 'ORD-9006', 'OrderPaid', '{}');

    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9007', 'ORD-9007', 'OrderPaid', '{}');
APPLY BATCH;
~~~

Across multiple partitions, an `UNLOGGED` batch has no batchlog to ensure full completion if the coordinator crashes. When mutations are independent, **bounded individual async writes** usually outperform a large batch built solely for throughput.

### 15.3. Counter updates are unsafe on replay

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_counters (
    order_id text PRIMARY KEY,
    event_count counter
);

UPDATE shop_integration.order_counters
SET event_count = event_count + 1
WHERE order_id = 'ORD-9001';
~~~

If the first `+1` **was applied by Cassandra** yet the response dropped, a retry increments to `+2`. Hence counter increments are normally **non-idempotent**. Never set `setIdempotent(true)` or apply the classifier from section 10 to counters.

When exact, recoverable event counts are required:

1. Persist an event log with stable event IDs.
2. Deduplicate by event ID in a designed projection/inbox.
3. Update counters/state under a verified protocol.
4. Maintain the ability to recompute/reconcile from the event log.

### 15.4. TTL, timestamps, and partial updates

Even a regular `INSERT` on the same key can be non-equivalent across retries if:

- It recomputes TTL, extending row expiration.
- It supplies a new timestamp, altering conflict resolution under concurrent writes.
- It binds `NULL` instead of `UNSET` in a partial update, creating tombstones/deleting existing values.
- It reads volatile event metadata on each attempt.

**Never equate** "same primary key" with "invariant business outcome under all conditions". Review idempotency across the **full mutation, external side effects, and concurrent writes**.

## 16. Reconciliation: resolving uncertain outcomes with evidence

Retries help with transient errors, whereas **reading back/tracing state** is needed when the caller cannot tell whether Cassandra applied a mutation.

### 16.1. A reconciliation data shape

~~~json
{
  "eventId": "evt-9001",
  "orderId": "ORD-9001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "payloadHash": "sha256-of-canonical-payload",
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

`payloadHash` above is an **illustrative placeholder field**; production must compute an actual hash of the canonical payload with a stable algorithm/encoding and domain safeguards if used as integrity evidence.

For `order_event(event_id PRIMARY KEY, ...)`, the service can read back by `event_id` after a timeout once the cluster stabilizes:

~~~sql
SELECT event_id, order_id, event_type, payload_json
FROM shop_integration.order_event
WHERE event_id = 'evt-9001';
~~~

### 16.2. Reconciliation outcomes

| Read-back outcome | Safe conclusion? | Suggested action |
|---|---|---|
| Row exists, same event ID + canonical payload | Write succeeded or valid duplicate | Mark processed per business invariant |
| Row exists, same ID, different payload | **Conflict**; not a safe duplicate | Quarantine, alert, and investigate producer |
| Row missing, cluster stale or weak read CL | Cannot yet prove write did not happen | Wait/retry read at proper CL; check topology |
| Row missing on healthy cluster past reconciliation window | Likely needs replay | Retry with same event ID/payload if idempotent |
| Read also times out / unavailable | State remains unknown | Never falsely acknowledge; backoff/defer reconciliation |

**Important note:** Cassandra eventual consistency and CL affect read-back results. A `LOCAL_ONE` read immediately after a `LOCAL_QUORUM` write may miss the update on the chosen replica; pick matching read/write CLs, and never rely on a hasty read from another DC to prove absence.

### 16.3. Inbox and outbox: picking one source of truth

If one business event must write to Cassandra and also send an email or update another system, those steps span **separate resources**. Architectural patterns:

- **Durable event inbox** storing event IDs and processing state so incomplete steps can resume.
- **Outbox** inside a transactional source of truth when available, reliably publishing to brokers.
- **Idempotent downstream handlers** keyed by event ID, version, or request token.
- **Reconciliation workers** comparing source and destination for controlled replay.

Never write a "dedup record" in Cassandra table A and then write table B assuming an SQL-like atomic commit. Crashing between A and B still requires recovery/reconciliation to finish B.

### 16.4. Late retries and event ordering

A Kafka `OrderPaid(v2)` can arrive **after** `OrderCancelled(v3)`. If a handler retries `UPDATE current_state='PAID'` without a version guard, it regresses state. Immutable event logs can store both records by ID; current-state projections must enforce `aggregateVersion`/LWT or an explicit ordering protocol.

## 17. Deadlines and retry budgets from business SLAs

A transient error is only worth retrying when **reasonable time** remains to finish without worsening cluster health. If an HTTP client waits at most 4 seconds, never set a 5-second Cassandra driver timeout followed by three service retries.

### 17.1. Example time budget allocation

~~~text
HTTP gateway deadline              5.0s
  - deserialize/authorize          0.3s (budgeted)
  - app/handler logic              0.3s
  - Cassandra request timeout      2.0s
  - optional backoff/retry         within remaining budget
  - response/network buffer        0.5s
  - headroom                       per measurements
~~~

These are **illustrative figures**, not framework defaults. Stages can overlap in asynchronous pipelines. Measure p95/p99 traces to set deadlines, retry counts, and backoff for your workload.

### 17.2. Aligning responses with uncertain states

On write timeout, an API should not blindly return "transaction cancelled" if Cassandra may have saved the event. When the domain supports asynchronous reconciliation, return **accepted/pending** with the event ID and a status lookup endpoint *once a durable handoff is secured*.

**Never return 202 Accepted merely because a message entered an in-memory queue** that could vanish on JVM crash. Accepted status must correspond to durably handed-off work per contract.

### 17.3. Be careful when "raising timeouts"

Longer timeouts add zero capacity to Cassandra. If 1,000 messages/s arrive while Cassandra sustains 600 writes/s, the backlog grows by roughly **400 messages/s**. Letting more requests wait saturates memory and in-flight streams while driving p99 higher.

Set explicit bounds:

- Max in-flight Cassandra operations.
- Max retry attempts and backoff.
- Max broker redelivery/DLQ age.
- Max JVM queue depth, batch size, and Kafka consumer lag.
- Circuit breakers during prolonged downstream outages.
- Business-specific deadlines and maximum staleness.

## 18. Backpressure, throttling, and speculative execution

### 18.1. Bounding concurrency in Reactor

Given a validated `Flux<OrderEventRow>`, capping at **at most eight concurrent writes**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<OrderEventRow> completed = source.flatMap(
        row -> operations.insert(row).thenReturn(row),
        8);
~~~

This fragment belongs in a reactive service with `source` and `ReactiveCassandraOperations operations`. It does **not** automatically wire Spring Integration broker acknowledgments; connect completion/error signals to your source policy. `flatMap` can complete **out of input order**, so use `concatMap` or version guards when aggregate state ordering is required, weighing throughput vs invariants.

### 18.2. Driver throttling vs broker backpressure

Java Driver 4.x includes request throttling, such as `ConcurrencyLimitingRequestThrottler`. Request timeouts keep ticking **while a request sits in the throttler queue**. If the queue fills, the driver throws `RequestThrottlingException`; the right interpretation is that the app is exceeding allowed pressure—never "retry ten more times immediately".

On the driver, monitor `pool.in-flight`, `pool.available-streams`, queued requests, and failed/timeout counts. On the broker, monitor queue depth, consumer lag, and oldest message age. **Throttle upstream or consumer concurrency**, rather than just raising timeouts.

### 18.3. Speculative execution is parallel retrying with a cost

Java Driver 4.x **disables speculative execution by default**. When enabled for idempotent statements, the driver can fire an extra query to another coordinator if the first attempt lags.

~~~text
Request SELECT id=evt-9001
 t=0ms   Execute on coordinator A
 t=100ms No response yet -> may send speculative attempt to B
 t=120ms B responds first -> driver returns response to client
 t=200ms A responds late -> response is discarded
~~~

In Cassandra, "canceling attempt A" on the driver **only discards its response**; the server does not necessarily abort in-progress work. Therefore:

- Enable only for idempotent operations.
- Cap speculative attempts and delays.
- Watch orphaned streams and `available-streams`.
- Never use it to cure cluster-wide overload or hot partitions.
- Remember each speculative execution may interact with retry policies, amplifying traffic.

### 18.4. Triage sequence when the cluster is overloaded

~~~mermaid
flowchart TD
    A["Timeouts rise + broker backlog"] --> B["Classify exception"]
    B --> C{"Unavailable due to missing replicas?"}
    C -->|"Yes"| D["Fix node/topology; keep CL per contract"]
    C -->|"No"| E{"Driver/Server timeout?"}
    E -->|"Yes"| F["Measure in-flight, p99, hot partitions, compactions"]
    F --> G["Throttle concurrency / producer"]
    G --> H["Controlled backoff and recovery"]
    D --> H
    E -->|"No"| I["Check contract/codec/authorization"]
    I --> J["Fail fast / quarantine if permanent"]
~~~

**Never auto-downgrade consistency** as an escape hatch from a retry storm; doing so trades visible failures for silent stale or conflicting data.

## 19. Observing retries: separating real errors from traffic amplification

| Metric/signal | Source | Question to answer |
|---|---|---|
| `UnavailableException` count by CL | Driver/app | Are live replicas missing for CL? |
| `ReadTimeoutException` / `WriteTimeoutException` | Driver/server | Coordinator timeout or just client deadline? |
| `DriverTimeoutException` count | App/driver | When did client deadlines expire? |
| `RetryPolicy` retry counts and coordinator switches | Driver metrics/logs | Are retries helping or just shifting load? |
| Request success-after-retry rate | App tracing | Are retries actually succeeding? |
| `WriteType` in `WriteTimeoutException` | Driver | `SIMPLE`, `BATCH_LOG`, or something else? |
| `pool.in-flight` / available streams | Driver | Are connections saturated? |
| Read/write p50, p95, p99 | Cassandra/driver | Tail latency spike or whole workload slow? |
| `ClientRequest` timeouts/unavailables/failures | Cassandra nodes | Server-side error rate |
| Hot partitions, compactions, pending tasks | Cassandra | Query/model/GC bottleneck? |
| JMS delivery counts / queue depth | Broker | Are redeliveries climbing? |
| Kafka consumer lag / retry-topic backlog | Kafka | Is downstream stalling consumer groups? |
| Duplicate/conflicting event IDs | Business metrics | Are replays causing data corruption? |
| Quarantine/DLQ oldest age | Recovery systems | Are permanent errors piling up? |

### 19.1. Tracing a request with complete context

Example log **excluding sensitive payloads**:

~~~text
traceId=tr-9138
eventId=evt-9001
operation=order_event_insert
consistency=LOCAL_QUORUM
driverTimeoutMs=3000
attempt=2
elapsedMs=2805
exception=WriteTimeoutException
writeType=SIMPLE
requiredResponses=2
receivedResponses=1
source=jms
sourceAck=NOT_COMMITTED
~~~

`attempt` must have a clear scope (driver, service, or broker attempt) rather than an ambiguous number. If an exception lacks `required`/`received` or occurred strictly in the driver client, **never fabricate placeholder numbers**.

Never use `eventId` as a Prometheus metric label per event (cardinality explodes). `eventId` and `traceId` belong in logs and traces, while metrics aggregate by operation, `errorType`, service, and cluster/DC.

### 19.2. Six-question investigation workflow

1. **Which layer failed?** Coordinator, driver, Spring gateway, broker, or mapper?
2. **What are RF, CL, and DC topology?** Are enough replicas alive for CL?
3. **Did the request reach a coordinator?** Correlate client/server traces, queue time, and packet drops.
4. **Is the operation idempotent?** Check primary key, payload, TTL, timestamp, and side effects.
5. **Did the broker commit?** If not, expect redelivery; if so, check what recovery relies on.
6. **Retry or reconcile?** On uncertain timeouts, never assume negative proof.

### 19.3. Worthwhile alerts

Valuable alerts include:

- Timeout/unavailable rates exceeding baseline.
- Driver retry/request ratio spiking while success-after-retry stays flat.
- JMS queue depth or Kafka consumer lag climbing steadily.
- In-flight requests or available streams crossing safety thresholds.
- Single nodes or partitions showing anomalous p99 latency.
- Rising duplicate/conflicting events or aging DLQ items.

Never alert solely on cluster-average CPU; one hot partition or node can wreck p99 while cluster CPU looks fine.

## 20. Common troubleshooting table

| Symptom | Possible cause | Fix |
|---|---|---|
| `UnavailableException` with `LOCAL_QUORUM` | Insufficient live local replicas for RF/CL | Check RF, datacenter, and replica health; never silently downgrade CL |
| `UnavailableException` while Cassandra nodes stay up | Alive nodes lack enough replicas for that partition | Check token placement/replica sets and RF/CL |
| `ReadTimeoutException` with `received>=blockFor` and `dataPresent=false` | Only digests arrived without actual data | `DefaultRetryPolicy` may retry the same coordinator once |
| `WriteTimeoutException` with `SIMPLE` | Mutation may have reached replicas | Reconcile, retry only if idempotent, never mint new `eventId` |
| `WriteTimeoutException` with `BATCH_LOG` | Slowness writing batchlog | Inspect coordinator/batchlog; note default policy permits conditional retry |
| `DriverTimeoutException` without server timeouts | Client deadline expired before coordinator reply or in queue | Check driver throttle queue, network, request timeout, in-flight count |
| `RequestThrottlingException` | Driver hit concurrency/queue cap | Throttle producer/consumer concurrency; avoid hot retries |
| `OverloadedException` rises with backlog | Coordinator/replicas saturated | Throttle, apply backoff/circuit breaker, fix hot partitions |
| Infinite retries on `InvalidQueryException` | Bad schema/CQL or missing table | Fail fast; fix migration or config |
| Infinite retries on `UnauthorizedException` | Cassandra role lacks access | Fix permissions/secrets; do not retry unchanged |
| Retrying counter doubles values | Non-idempotent mutation | Remove `idempotent` flag; use event log/dedup protocol |
| Immutable `INSERT` alters values after retry | Payload, TTL, or timestamp mutated | Freeze canonical event; check concurrent writes |
| LWT `applied=false` reported as DB down | Confused business condition with transport failure | Read existing row; compare event/version |
| Cassandra write succeeds yet JMS redelivers | Crash before JMS commit | Stable primary key and idempotent replay |
| JMS fails to redeliver after DB timeout | Listener acked/committed before async error | Use sync completion or durable handoff/replay |
| Kafka lag spikes during in-poll retries | Long blocking retries stall consumer | Use retry topics/delayed processing; monitor poll liveness |
| `errorChannel` logs error yet source never retries | Handler error processed after source commit | Review ack boundaries and async flows |
| Raising timeouts increases memory usage | Pending/in-flight requests pile up | Lower concurrency and fix the bottleneck |
| App sees `Mono.empty()` on Cassandra failure | Error swallowed and turned into not-found | Separate empty results from timeouts/`DataAccessException` |
| Gateway `replyTimeout` fires before Cassandra finishes | Gateway deadline shorter than DB request | Align deadlines and uncertainty semantics |
| `setIdempotent(true)` has no effect | Ignored return value of immutable setter | Reassign statement or use builder |
| Custom retry policy downgrades `LOCAL_QUORUM` | Using consistency-downgrading policy | Revert to safe policy; review business invariants |
| Speculative execution inflates write rate | Enabled on idempotent writes with too low delay | Review max-executions/delay, throughput, and orphaned streams |
| Driver never retries `SIMPLE` write timeouts | `DefaultRetryPolicy` intentionally rethrows `SIMPLE` | Handle at service/broker layer if business-idempotent |
| Testing RF=3 on single node fails | Insufficient replica nodes | Single-node lab uses RF=1; multi-node required for quorum tests |

### 20.1. Retry decision checklist

Before every retry decision, answer:

1. **Exception class:** `Unavailable`, `WriteTimeout`, `DriverTimeout`, `InvalidQuery`, or app error?
2. **Operation:** `SELECT`, immutable `INSERT`, partial `UPDATE`, LWT, batch, or counter?
3. **Idempotency:** same full PK, values, timestamp/TTL, version, and side effects?
4. **Current CL:** do business invariants require quorum? Never silently downgrade.
5. **Budget:** remaining deadline, attempts, backoff, and in-flight capacity?
6. **Source:** has JMS/Kafka/HTTP already acknowledged, or is durable replay active?
7. **Unknown outcome:** is read-back/reconciliation needed?
8. **Permanent error:** must it quarantine/alert instead of retrying?

### 20.2. Condensed decision flow

~~~mermaid
flowchart TD
    A["Cassandra operation fails"] --> B{"Contract/authorization/CQL error?"}
    B -->|"Yes"| P["Fail fast / quarantine"]
    B -->|"No"| C{"Transient unavailable/timeout?"}
    C -->|"No"| X["Investigate other error"]
    C -->|"Yes"| D{"Operation idempotent?"}
    D -->|"No"| R["Reconcile / domain-specific recovery"]
    D -->|"Yes"| E{"Retry budget left and cluster has capacity?"}
    E -->|"Yes"| T["Jittered backoff, bounded retry"]
    E -->|"No"| Q["Durable retry queue / reconcile / DLQ"]
    T --> F{"Succeeded?"}
    F -->|"Yes"| K["Ack source per policy"]
    F -->|"Not yet"| Q
~~~

**This diagram is a decision framework, not an automatic library.** For uncertain timeout outcomes, even idempotent mutations need monitoring/tracing and potentially reconciliation to verify business completion.

## 21. Hands-on lab: verifying unavailable and timeout retries

**Environment:** Java 17+, Spring Integration Cassandra compatible with Spring Data Cassandra reactive, Java Driver 4.x, a Cassandra test cluster, plus a test JMS broker/Kafka cluster when testing real sources. Exercises involving `RF=3`, quorum, and node failures require **at least three real Cassandra replica nodes**—a single container is insufficient.

### Exercise A — Distinguishing RF/CL and Unavailable

1. Start a three-node test cluster in one DC `dc1`.
2. Create keyspace `shop_integration` with `NetworkTopologyStrategy 'dc1':3`.
3. Run an `INSERT` with `LOCAL_QUORUM`, confirming two local responses succeed when healthy.
4. Intentionally stop **one replica node** in tests; retry `LOCAL_QUORUM` and observe it can still succeed.
5. Stop a second replica node (only in safe test orchestration), retry, and observe `UnavailableException` or the corresponding failure-detection error.
6. Capture `required`/`alive` metadata and effective CL from driver/server.
7. Restore the cluster and verify ring/replication health before the next exercise.

**PASS:** explains why `required=2, alive=1` yields `UNAVAILABLE`, and why you must not silently lower CL to bypass it.

### Exercise B — Server ReadTimeout and WriteTimeout

1. On a healthy RF=3 cluster, set `CL=LOCAL_QUORUM`.
2. Inject network latency/faults **in the test environment** to slow down some replicas.
3. Run reads/writes with suitable server timeouts/test deadlines and capture exceptions.
4. On `ReadTimeoutException`, record `received`, `blockFor`, and `dataPresent`.
5. On `WriteTimeoutException`, record `received`, `blockFor`, and `writeType`.
6. Query again by the same primary key after cluster recovery.
7. Do not try to force identical exceptions on every attempt: if a node is marked down early, `UNAVAILABLE` may fire instead of `WRITE_TIMEOUT`.

**PASS:** distinguishes coordinator-side timeouts from upfront missing-replica `UNAVAILABLE`; never treats a write timeout as a DB rollback.

### Exercise C — DriverTimeout vs server timeout

1. Set `basic.request.timeout = 2 seconds` in the test driver config.
2. Induce a delayed request or hold it in the driver throttling queue.
3. Observe `DriverTimeoutException` when the client deadline expires.
4. Compare with server-side timeout metrics/logs: the server may show no matching `WRITE_TIMEOUT`.
5. Test per-statement `setTimeout(Duration.ofSeconds(1))` and inspect effective config.
6. Verify requests can still reach the server even after the client times out.

**PASS:** explains that request deadlines span driver queues/retries; distinguishes client timeouts from coordinator timeouts.

### Exercise D — `DefaultRetryPolicy` does not retry every error

1. Use `DefaultRetryPolicy` with an immutable `SELECT` having `setIdempotent(true)`.
2. Trigger `UNAVAILABLE` on the first coordinator and observe the policy trying the next node in the query plan.
3. Trigger `READ_TIMEOUT` with `received>=blockFor && !dataPresent` and verify the same-coordinator retry rule if the test setup supports it.
4. Trigger a `SIMPLE` `WRITE_TIMEOUT` in tests: verify the driver rethrows instead of retrying endlessly.
5. Add a conditional test for `BATCH_LOG` timeouts if multi-node fault injection and batchlog inspection are available.
6. Verify that errors occurring **before network writes** follow rules distinct from `RetryPolicy` callbacks.

**PASS:** describes default decisions per exception/`writeType` without claiming a blanket "maxRetry=1" rule for all errors.

### Exercise E — Idempotency and retrying the same event ID

1. Create `order_event(event_id PRIMARY KEY, ...)`.
2. Send `evt-9001` initially with an immutable payload.
3. Simulate response loss/timeout, then resend the **same event ID and values**.
4. Query back and confirm only one row exists under that PK.
5. Resend the same ID with a different `payload_json` and classify it as a conflicting duplicate.
6. Create a test counter table and increment `+1` twice to observe non-idempotent side effects.
7. Test overwriting TTLs or changing timestamps to explain why "same key" alone is not always sufficient.

**PASS:** distinguishes CQL idempotence from business idempotence and never sets `setIdempotent(true)` on counters.

### Exercise F — Reactor `retryWhen`, backoff, and circuit breakers

1. Create `OrderEventRow` and `ImmutableOrderEventWriter.save(...)` from section 10.
2. Use test doubles **for unit policy tests only** to emit two `UnavailableException`s followed by success; verify attempt counts and backoff.
3. With `InvalidQueryException`/mapping errors, verify the classifier does not retry.
4. Never reuse `forImmutableEventWrite` on non-idempotent operations.
5. Use Reactor `StepVerifier.withVirtualTime` to test retry delays where supported.
6. Bound max concurrency so unbounded `Mono`s cannot launch simultaneously.
7. Run the full workflow against real Cassandra to verify exception translation and cause chains.

**PASS:** retries are bounded and restricted to eligible failures; error signals are preserved and malformed JSON is never retried.

### Exercise G — Spring Integration and JMS commit boundaries

1. Use a transacted JMS inbound endpoint + `DirectChannel` + `async(false)` Cassandra handler.
2. Send `evt-9001` with a deterministic primary key.
3. Simulate a Cassandra timeout and verify exceptions propagate to the listener for rollback/redelivery per broker policy.
4. Let Cassandra write succeed, simulate a JVM crash before JMS commit, and observe broker redelivery of the same event.
5. Switch to `ExecutorChannel` or an async handler to see the listener return/commit before Cassandra completes.
6. Design a durable handoff/retry queue for the async case.
7. Route poisoned JSON/schema events to DLQ/quarantine instead of hot-retrying.

**PASS:** pinpoints exactly when source ack occurs and why Cassandra+JMS lack atomic commits.

### Exercise H — Kafka replay and ordering

1. Have a producer send three events for the same business order with a stable Kafka key.
2. Persist them via a consumer/flow into the Cassandra event log by event ID.
3. Let Cassandra write succeed, crash before offset commit, and verify replay creates no business duplicates.
4. Use a delayed retry topic test to see an older event finish after a newer event.
5. Protect the current-state projection using `aggregateVersion`/LWT.
6. Route permanent schema errors to a dead-letter topic and verify alerts, retention, and replay.

**PASS:** never uses Kafka offsets as Cassandra event IDs; handles redeliveries and out-of-order arrivals properly.

### Exercise I — LWT, batchlog, and reconciliation

1. Create `order_state` with `version`.
2. Run `UPDATE ... IF version = ?` and read `wasApplied()`.
3. Resend the same event and separate `applied=false` benign duplicates from conflicts.
4. Run a multi-partition logged batch test and observe batchlog/failure metrics when a coordinator lags.
5. Induce a client timeout and query each event ID back after cluster recovery.
6. Classify outcomes as `known success`, `known conflict`, `unknown outcome`, and `eventually reconciled`.

**PASS:** never confuses LWT `applied=false` with a driver timeout or treats the batchlog as a cross-JMS/Kafka transaction.

### Exercise J — Benchmarking under Cassandra overload

1. Measure baseline p50/p95/p99 latency at a low request rate.
2. Gradually raise concurrent events while holding payload and schema constant.
3. Enable `DefaultRetryPolicy` and count retries vs success-after-retry.
4. Add optional bounded service retries and measure traffic amplification.
5. Compare against reducing concurrency/applying backpressure.
6. Measure driver in-flight/`available-streams`, Cassandra timeouts, Kafka/JMS backlogs, and hot partitions.
7. In tests only, try speculative execution on idempotent `SELECT`s to observe extra request traffic.

**PASS:** bases concurrency and retry budgets on measurements rather than raising timeouts/retries just to mask short-term error rates.

### Final verification matrix

| Area | PASS outcome |
|---|---|
| CL/RF | Knows `LOCAL_QUORUM` needs two local replicas when RF=3 |
| Unavailable | Accurately interprets `required`/`alive` metadata |
| ReadTimeout | Inspects `received`/`blockFor`/`dataPresent` |
| WriteTimeout | Separates `SIMPLE` vs `BATCH_LOG` retry rules |
| DriverTimeout | Client deadline never confused with server rollback |
| Driver policy | `DefaultRetryPolicy` retries selectively without downgrading CL |
| Idempotency | Same event ID, full PK, and values across replays |
| Reactor | `Retry.backoff` has max attempts, filter, and jitter |
| Spring Integration | Error propagation respects sync/async boundaries |
| JMS | Commit/rollback and redelivery verified on a real broker |
| Kafka | Offsets/replays produce no duplicate side effects |
| LWT | `applied=false` distinguished from transport errors |
| Batch/counters | Non-idempotent mutations never blindly retried |
| Reconciliation | Unknown outcomes have a verification/read-back plan |
| Observability | Measures p99, retries, backlogs, and in-flight counts |
| Recovery | Appropriate DLQ/quarantine/durable handoff in place |

**Testing limitation:** unit mocks only verify classifier/flow invocations; they prove neither replica placement, quorum, coordinator timeouts, batchlog replay, nor lost network responses. Real multi-node Cassandra test clusters and matching brokers are required to validate those behaviors.

## 22. Self-assessment questions

1. Why can retrying a `WriteTimeoutException` cause a mutation to execute more than once?
2. How does `UnavailableException` differ from `WriteTimeoutException` in when the coordinator detects the failure?
3. What does `required=2, alive=1` with `LOCAL_QUORUM` indicate?
4. With Cassandra RF=3 and `CL=LOCAL_QUORUM`, how many replica responses are required in one DC?
5. Does `LOCAL_QUORUM` in dc1 guarantee a `LOCAL_QUORUM` read in dc2 sees the new write immediately?
6. What does `ReadTimeoutException` with `received>=blockFor` and `dataPresent=false` mean?
7. Why might `DefaultRetryPolicy` retry a `READ_TIMEOUT` when enough digest responses arrived without data?
8. How does `WriteType.BATCH_LOG` differ from `WriteType.SIMPLE` under default retries?
9. Does `DefaultRetryPolicy` automatically retry every `WRITE_TIMEOUT`?
10. Are driver retry policies invoked for errors happening before bytes hit the network?
11. Does `DriverTimeoutException` originate in the driver or the coordinator?
12. Does a 3-second driver request timeout grant another 3 seconds per retry?
13. Can a request sitting in the driver throttler queue throw `DriverTimeoutException`?
14. Does `RequestThrottlingException` suggest increasing retry counts or reducing pressure?
15. How can `ConsistencyDowngradingRetryPolicy` break read-after-write invariants?
16. Why shouldn't you lower `LOCAL_QUORUM` to `ONE` when only one replica remains?
17. Which Cassandra operations use `SERIAL`/`LOCAL_SERIAL`?
18. Is LWT `applied=false` an exception?
19. Does an LWT timeout prove the condition was not applied?
20. What problems arise from a Cassandra `INSERT` with the same primary key yet a different payload?
21. Does `setIdempotent(true)` create a database unique constraint or deduplication inbox?
22. Why is `list = ['x'] + list` non-idempotent?
23. Why is counter increment `+1` unsafe for blind retries?
24. Can a batch mixing an immutable `INSERT` and a counter be marked idempotent as a whole?
25. Can recomputing TTL on every retry alter the business outcome?
26. Why use a fixed `eventId` and canonical payload to reconcile timeouts?
27. Does `Retry.backoff(2, ...)` in Reactor mean two total attempts or two retries?
28. Why is `Mono.defer(...)` helpful when each retry must rebuild the publisher?
29. How can underlying driver exceptions get wrapped in `DataAccessException` in Spring Data?
30. Why should a retry classifier walk the cause chain instead of searching for `"timeout"`?
31. Why must an immutable-`INSERT` classifier never be reused verbatim for LWTs or counters?
32. Are `WriteOptions.timeout(...)` and `WriteOptions.ttl(...)` the same thing?
33. Does Java Driver `Statement.setTimeout(...)` alter Cassandra server `write_request_timeout`?
34. Why does `CassandraMessageHandler`'s async default affect JMS commits?
35. Do `DirectChannel` + `async(false)` handler create a shared transaction across Cassandra and JMS?
36. Why doesn't `errorChannel` replace a broker DLQ?
37. When Cassandra writes yet the JMS commit fails, what happens?
38. When JMS commits before an async Cassandra failure, does the source automatically redeliver?
39. Is a Kafka offset commit atomic with a Cassandra `INSERT`?
40. How can a Kafka retry topic affect per-order ordering?
41. Is an in-memory `ExecutorChannel` a durable queue across JVM crashes?
42. Why does raising driver timeouts increase in-flight requests without adding capacity?
43. Does speculative execution actually cancel an already-sent remote Cassandra mutation?
44. Which metrics should you watch during a retry storm?
45. If a read-back after a timeout finds no row at `LOCAL_ONE`, can you conclude with certainty that the write never occurred?
46. How does reconciliation distinguish a valid duplicate from a conflicting event ID?
47. What is the difference between a transient database failure and a permanent JSON/codec error?
48. Why avoid using `eventId` as a per-event metric label?
49. What Cassandra environment is needed to test `LOCAL_QUORUM` with RF=3 when losing one replica?
50. Outline an end-to-end retry strategy across driver policy, service attempts, JMS/Kafka redelivery, DLQ, and reconciliation.

## 23. Official references

- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): `DefaultRetryPolicy`, `ConsistencyDowngradingRetryPolicy`, `UNAVAILABLE`/`READ_TIMEOUT`/`WRITE_TIMEOUT` cases, aborted requests, and retry verdicts.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): `basic.request.default-idempotence`, `setIdempotent`, and conditions for safe retries/speculative execution.
- [Apache Cassandra Java Driver 4.19 — Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): `basic.request.timeout`, `basic.request.consistency`, execution profiles, and effective config.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): extra attempts, idempotency, stream ID pressure, and cancellation limits.
- [Apache Cassandra Java Driver 4.19 — Request Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/): concurrent request/queue limits, `RequestThrottlingException`, and request deadlines.
- [Apache Cassandra Java Driver 4.19 — Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): overall request timeouts in Driver 4.x and the `RetryVerdict` API since 4.10.
- [Apache Cassandra Java Driver API — RetryPolicy](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html): `onUnavailableVerdict`/`onReadTimeoutVerdict`/`onWriteTimeoutVerdict` callbacks and `required`/`received`/`blockFor`/`writeType` parameters.
- [Apache Cassandra Java Driver API — DriverTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/DriverTimeoutException.html): client-side deadline.
- [Apache Cassandra Java Driver API — UnavailableException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/UnavailableException.html): coordinator-side unavailable.
- [Apache Cassandra Java Driver API — WriteTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html): coordinator-side write timeout and `WriteType`.
- [Apache Cassandra — Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): RF, read/write CL, coordinators, and quorum reasoning.
- [Apache Cassandra — Monitoring and Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): `ClientRequest` timeouts/unavailables/failures and read/write latency.
- [Spring Data Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, publisher lifecycles, and reactive database access.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): per-operation consistency, timeouts, idempotence, and write TTL.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): Cassandra outbound channel adapter/gateway, `CassandraMessageHandler`, and `setAsync(false)`.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and synchronous/asynchronous error propagation.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound endpoints, transactions, and redelivery considerations.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound/outbound integration and Kafka consumer considerations.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, backoff, and error handling.

**Key takeaway:** `UNAVAILABLE`, `READ/WRITE_TIMEOUT`, and `DRIVER_TIMEOUT` are not one single error. Java Driver 4.x's **`DefaultRetryPolicy`** retries selectively and **never automatically retries all `WRITE_TIMEOUT`s**; the **`idempotent`** flag must accurately reflect domain semantics. **Timeouts never prove Cassandra did not write.** In Spring Integration, clarify sync/async handlers, when JMS/Kafka sources acknowledge, and which layer owns retries. For immutable events, rely on stable `eventId`, bounded retries, backoff, backpressure, and reconciliation; for LWTs, batches, and counters, respect their distinct semantics. Never silently downgrade consistency or trigger retry storms to mask Cassandra outages.







