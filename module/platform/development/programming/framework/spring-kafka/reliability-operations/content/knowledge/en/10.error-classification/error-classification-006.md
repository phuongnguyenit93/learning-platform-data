# Network timeout

In a Spring Kafka system, a network timeout is a category of errors occurring when a component fails to receive a response or complete a network operation within the configured duration. A producer may send a record without receiving an ACK in time; a consumer may fail to receive data from a broker; an offset commit request may fail due to a dropped connection; or the application may fail to connect to a broker when DNS, TLS, or the network path encounters issues.

In the **Error classification** chapter, accurately identifying network timeouts is essential because many exceptions share similar names yet originate from different layers. A timeout can occur while establishing a connection, waiting for a broker response, waiting for producer buffers or metadata, invoking a synchronous API, processing downstream HTTP calls, or waiting for a listener to finish. Recovery depends on where the error occurred and whether the operation's effect may already have taken place.

**A network timeout does not mean a record was definitely not written.** The broker may have appended the record while the ACK was lost or delayed. The consumer may have completed business processing while the offset commit failed. Therefore, timeout handling must account for ambiguous outcomes, bounded retries, idempotency, and data reconciliation capability.

## 1. Network timeouts in a Spring Kafka flow

A Kafka flow crosses multiple network boundaries and multiple operations with distinct timeouts:

~~~mermaid
flowchart LR
    A["Spring application"] --> B["Kafka client"]
    B --> C["DNS / route / TCP"]
    C --> D["TLS / SASL authentication"]
    D --> E["Kafka broker"]
    E --> F["Metadata / coordinator"]
    E --> G["Partition leader / replicas"]
    B --> H["Producer send / Consumer fetch"]
    H --> I["ACK / records / commit response"]
~~~

A failure at any boundary can prevent an operation from completing:

- DNS fails to resolve the broker hostname.
- TCP connection cannot be established or is reset.
- TLS handshake hangs or fails.
- SASL authentication does not complete or the broker does not respond.
- The client sends ProduceRequest, FetchRequest, or OffsetCommitRequest without receiving a timely response.
- An overloaded broker processes requests slowly.
- A network route, firewall, proxy, or load balancer drops the connection.
- The client connects to a broker address returned in metadata that is unreachable from the application's network.

A timeout is an operation time limit. On its own, it does not reveal whether the root cause is network, broker, DNS, TLS, system load, or downstream. You must inspect the root exception, pending requests, target broker, and concurrent metrics.

### 1.1 Timeout vs. connection failure

Two states are often conflated:

- **Connection failure**: the client cannot establish or maintain a connection, such as connection refused, connection reset, or unknown host.
- **Timeout**: the operation does not finish before its deadline, such as failing to connect within the allowed time or a request not receiving a response on time.

Connection failures usually cause the client to reconnect. Timeouts can happen even when the TCP connection remains open, such as when a broker receives a request but processes it too slowly or the response is lost in transit.

One exception can be the final symptom of a chain of failures. For example, a client retries reconnecting several times after connection resets, eventually hits the API deadline, and throws TimeoutException. Looking only at the final exception can miss the initial connection failure.

### 1.2 Timeout vs. authentication errors

TLS handshake timeouts and SASL authentication failures must be distinguished:

- A TLS handshake timeout may result from slow networks, overloaded brokers, certificate negotiation, or proxies.
- Invalid certificates, hostname mismatches, or truststores missing a CA are usually configuration/certificate errors, not timeouts solvable by infinite retries.
- SASL authentication failures usually require checking username, password, mechanism, token, or ACLs.
- If the broker stops responding during authentication, the client may report a timeout or disconnect.

Do not raise timeouts just to mask certificate, credential, or ACL errors. Classify using the root exception and broker logs.

## 2. Common timeout locations

### 2.1 DNS and broker addresses

Producers and consumers typically use bootstrap servers to discover cluster metadata. Bootstrap servers are only an entry point. After receiving metadata, clients connect to the broker/leader's advertised addresses.

A common scenario in Kubernetes or cloud environments:

1. The application connects to the bootstrap endpoint.
2. The broker returns metadata containing advertised listener addresses.
3. The client attempts to connect to those addresses.
4. Those addresses are only reachable inside a different internal network, not from the application pod.
5. The client repeatedly reconnects or hits request timeouts.

Therefore, a successful bootstrap connection does not prove every broker address is reachable. Inspect advertised.listeners, DNS, routing, security groups, firewalls, service meshes, and network policies from the application's actual runtime environment.

Symptoms:

- Logs show UnknownHostException or hostname resolution errors.
- Some brokers connect while others continuously time out.
- Producers fail only when records route to partitions whose leader is on a specific broker.
- Consumers fetch from some partitions while other partitions make no progress.

### 2.2 TCP connect and reconnect

The client must establish a TCP connection to the broker. Connections can fail if the broker is not listening, the port is blocked, routing is wrong, the backlog is full, or a firewall rejects traffic.

The Kafka client includes reconnect backoff. Commonly involved properties:

- reconnect.backoff.ms: base wait time before attempting to reconnect.
- reconnect.backoff.max.ms: upper bound for reconnect backoff.
- socket.connection.setup.timeout.ms: maximum time to establish a connection.
- socket.connection.setup.timeout.max.ms: upper bound for connection setup time across attempts.

Property names and defaults depend on the Kafka client version. Consult documentation for the exact version in use. Backoff helps avoid reconnect storms; it cannot fix wrong DNS, routing, or broker listeners.

### 2.3 Request-response between client and broker

Once connected, the Kafka client sends requests and waits for broker responses. Relevant requests include:

- ProduceRequest: sending records to a partition leader.
- FetchRequest: consumer fetching records from a broker.
- MetadataRequest: retrieving cluster/topic metadata.
- OffsetCommitRequest: committing offsets for a consumer group.
- FindCoordinator and requests to the group coordinator.
- Transaction coordinator requests for transactional producers.
- Admin API requests such as describe topic or alter configuration.

If a broker is slow, request queues congest, or packets drop on the network, the client may miss response deadlines.

### 2.4 Consumer fetch and poll

Consumer poll is the loop fetching data and executing listeners per container model. Poll may return empty when no new records exist; that is not necessarily a timeout or error.

Configurations to distinguish:

- fetch.max.wait.ms: maximum time the broker waits for a fetch response to satisfy fetch.min.bytes.
- fetch.min.bytes: minimum data threshold the broker tries to accumulate before responding.
- request.timeout.ms: wait limit for a single client request's response.
- pollTimeout in Spring Kafka: how long the container waits in a single poll per container configuration.
- max.poll.interval.ms: maximum interval between consumer group member poll calls.

pollTimeout is not request.timeout.ms. max.poll.interval.ms is not a network timeout either; it guards poll progress. If a listener processes too long and fails to call poll again on time, the consumer can be evicted from the group even when the network is healthy.

### 2.5 Offset commit

After processing records, the consumer can send an offset commit request. If the coordinator is unreachable or the response does not arrive before the deadline, the commit can fail.

When a commit fails, determine:

- Has the listener completed its business effects?
- Was the offset commit applied by the broker with the response lost?
- Will the container retry the commit, or will the record be redelivered?
- Which ack mode is in use?
- Does the application have idempotent side effects?

Never conclude that a commit timeout always means the offset was not saved. This is also an ambiguous outcome. If the record was processed and the commit response was lost, redelivery can cause duplicate side effects.

## 3. Distinguishing Kafka timeout configurations

No single property controls all network timeouts. Producers, consumers, connection setup, and APIs have separate deadlines.

| Property | Scope | Primary meaning |
|---|---|---|
| request.timeout.ms | Producer and consumer requests | How long the client waits for a response to one request |
| delivery.timeout.ms | Producer | Maximum total time to report send outcome, including batching, requests, and retries |
| max.block.ms | Producer API | How long send can block waiting for metadata or buffer space |
| default.api.timeout.ms | Consumer API | Default deadline for certain synchronous consumer APIs |
| socket.connection.setup.timeout.ms | Network connection | Maximum time to establish a connection |
| socket.connection.setup.timeout.max.ms | Network connection | Upper bound on connection setup time |
| reconnect.backoff.ms | Network connection | Backoff between reconnect attempts |
| reconnect.backoff.max.ms | Network connection | Maximum reconnect backoff |
| retry.backoff.ms | Client request retry | Wait time between request retries |
| fetch.max.wait.ms | Broker fetch | How long the broker waits to accumulate data for fetch |
| session.timeout.ms | Consumer group | Heartbeat/member timeout under the group protocol |
| heartbeat.interval.ms | Consumer group | Interval between heartbeats in the classic group protocol |
| max.poll.interval.ms | Consumer group | Maximum time between poll calls |
| transaction.timeout.ms | Producer transaction | Maximum time a transaction may stay open |

Properties can vary across Kafka versions. Some APIs have dedicated timeouts or use default.api.timeout.ms. Read documentation for the running client version and verify effective configuration at runtime.

### 3.1 request.timeout.ms

request.timeout.ms defines how long the client waits for a response to a single request. If a request does not finish within this window, the client can mark an error, close or transition the request state, and retry depending on request type and policy.

For producers, request timeout applies to record send requests to brokers. If a broker appends the record but the response is lost, the client can time out even though the record was written. Idempotent producers handle protocol-level retries, but applications still need to understand delivery outcomes and business idempotency.

For consumers, request timeout can affect fetch, metadata, or other requests. Consumers can reconnect and resume fetching once the broker/network recovers.

Do not set request.timeout.ms too low relative to actual network and broker latency. Overly low values cause false timeouts, unnecessary retries, and extra load. Overly high values delay outage detection.

### 3.2 delivery.timeout.ms

delivery.timeout.ms is the overall deadline for a producer sending a record. It covers time spent waiting in batches, requests, and retries. When time expires without completion, the callback/future completes with an error.

In modern Kafka producers, delivery.timeout.ms must be greater than or equal to request.timeout.ms plus linger.ms per client requirements. Verify documentation for your specific version.

For example: request.timeout.ms is 30 seconds, linger.ms is 5 milliseconds, delivery.timeout.ms is 120 seconds. The producer has an overall window exceeding a single request timeout to retry requests within the delivery deadline.

Increasing delivery timeout helps survive brief broker failovers, but also makes the application wait longer before learning a send failed. Choose based on SLA and the application's ability to buffer pending events.

### 3.3 max.block.ms

KafkaProducer.send() normally returns asynchronously, yet a send() call can still block before returning if the producer needs metadata or must wait for buffer space. max.block.ms caps wait time for certain of those cases.

Examples:

- The producer lacks topic/partition metadata and must wait for metadata.
- A record needs buffer space while the producer buffer is full due to a slow broker.
- A network outage keeps records in the buffer longer, preventing space from being freed.

Consequently, the application may see send() hang before a callback/future is even returned. This differs from a future being returned and then failing due to delivery timeout.

### 3.4 default.api.timeout.ms

Some synchronous KafkaConsumer APIs use default.api.timeout.ms as the default deadline if the caller does not pass an explicit timeout. It does not replace request.timeout.ms; an API deadline may span multiple requests or internal waits.

If the application calls synchronous APIs like commitSync or consumer management operations, distinguish the overall API timeout from individual broker request timeouts.

### 3.5 session.timeout.ms and heartbeat.interval.ms

session.timeout.ms relates to how long the broker waits for heartbeats from a consumer group member before considering the member disconnected. heartbeat.interval.ms controls heartbeat cadence in the classic group protocol.

This is not a timeout for a ProduceRequest or FetchRequest. A consumer can be evicted from the group because heartbeats miss their deadline due to network outages, process pauses, or thread scheduling. Conversely, fetch requests can time out while the consumer keeps membership if heartbeats continue succeeding.

In newer group protocols, some heartbeat parameters are governed differently. Use settings aligned with your group protocol and Kafka client version.

### 3.6 max.poll.interval.ms

max.poll.interval.ms limits the time between two poll calls. If a listener processes too long or the consumer thread blocks, the consumer can exceed this limit and be considered stalled.

This is typically a processing time or thread starvation issue, not necessarily a network timeout. Raising max.poll.interval.ms may fit when valid batches take longer than expected, but it will not cure an infinitely hanging HTTP call or an exhausted database pool.

### 3.7 transaction.timeout.ms

transaction.timeout.ms limits how long a Kafka transaction may stay open. Long-running transactions can be aborted by the coordinator. This is a transaction timeout, not a request timeout.

A producer can experience a network timeout while committing a transaction; a transaction can also time out by exceeding its allowed duration; both errors can happen together and must be classified separately.

## 4. Network timeouts on the producer

A producer can time out before sending, during sending, or after the broker has received the record.

### 4.1 Potential timeout points

- Fetching topic or partition metadata.
- Establishing a connection to the leader broker.
- Waiting for producer buffer space.
- Waiting for the broker to process ProduceRequest.
- Retrying requests after connection reset or broker failover.
- Waiting for the overall delivery deadline.
- Calling transaction commit/abort or coordinator APIs.

A producer sending to multiple topics/partitions may time out on only one broker or a subset of partitions. Therefore, logging topic, partition, broker node, client id, and root exception is vital.

### 4.2 Common exceptions

Exception names depend on the failing layer and Kafka client version. Common types:

| Exception / symptom | Typical interpretation | What to check |
|---|---|---|
| TimeoutException | An operation did not finish within its deadline | Check API, request, delivery, and max block timeouts |
| NetworkException | Error at the client network layer | Connection, route, broker, and socket |
| DisconnectException | Broker connection dropped while handling a request | Broker restart, idle connection, proxy, or network reset |
| SocketTimeoutException | Socket failed to receive data on time at some layer | Network path, broker response, and timeout |
| UnknownHostException | DNS could not resolve broker hostname | DNS, advertised.listeners, and network namespace |
| NotLeaderOrFollowerException | Request sent to a broker no longer holding the right role | Metadata refresh, leader election, and broker state |
| RecordTooLargeException | Record exceeds size limit | Producer, broker, and topic size limits |
| KafkaException wrapping send error | Composite client/Spring exception | Inspect root cause and failed record metadata |

Not every TimeoutException is caused by packet loss. Broker overload, thread starvation, metadata delays, or overly low timeout settings can produce the same symptom.

### 4.3 Ambiguous send outcomes

An important case:

1. The producer sends a record to the leader.
2. The leader appends the record successfully.
3. The broker sends an ACK.
4. The network drops the response before the ACK reaches the producer.
5. The producer hits request/delivery timeout.
6. The application receives an error even though the record may already exist in Kafka.

If the application immediately creates a new event and resends it, the record can be duplicated. Distinguish retrying the same producer request from initiating a new business send.

An idempotent producer eliminates duplicates caused by protocol retries within the same producer session. However, if the application restarts or resends the same event as a new operation, rely on a stable event id/business key and consumer/downstream idempotency.

### 4.4 Handling KafkaTemplate futures

Spring Kafka's KafkaTemplate.send() returns CompletableFuture in modern Spring Kafka versions. Applications should observe asynchronous results rather than ignoring failures.

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send(
            "orders",
            event.orderId(),
            event
        )
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Kafka send failed: eventId={}",
                    event.eventId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Kafka send succeeded: eventId={}, topic={}, partition={}, offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

A completed future means the producer received an outcome per ACK policy. It does not prove a downstream consumer has processed the record.

Also remember that send() itself can block before returning a future while waiting for metadata or buffer space per max.block.ms. If the calling thread blocks inside send(), the callback cannot free that thread. Monitor both send call latency and future completion latency.

### 4.5 Do not retry infinitely in callbacks

A callback should not immediately call send again in an unbounded loop. During a broker outage, all producer instances can create a retry storm, filling buffers and increasing pressure on recovering brokers.

Retries must:

- Have a finite attempt limit or overall deadline.
- Use backoff, with jitter when multiple instances retry concurrently.
- Classify retriable vs. non-retriable errors.
- Preserve the event id to prevent duplicates.
- Have durable storage/outbox if events must not be lost.
- Expose metrics for pending sends, retries, timeouts, and send failures.

The Kafka producer already performs internal retries. Application-layer retries must be budgeted alongside client retries to avoid unexpectedly multiplying attempts.

## 5. Network timeouts on the consumer

Consumers receive data via FetchRequest and send requests for group coordination, offset commits, and metadata. Network timeouts can pause fetching, drop coordinator connections, or break offset commits.

### 5.1 Fetch timeouts and consumers receiving no records

An empty consumer poll does not automatically mean a network timeout. The topic may have no new records, partitions may not be assigned yet, the consumer may be at the end of the log, or records may not yet be visible due to isolation level.

When suspecting a network timeout, check:

- Fetch request latency and errors.
- Broker connection state.
- Consumer assigned partitions.
- Poll rate and record rate.
- Partition leader broker.
- Consumer lag and offset position.
- DNS and advertised broker addresses.

If a consumer stops receiving records from one partition while still receiving from others, that partition may have a specific leader/network issue.

### 5.2 Offset commit timeouts

Offset commits can time out when the coordinator is unreachable or responses are lost. When using manual acknowledgment or container-managed commits, inspect container logs and commit failure metrics.

If business effects succeeded while commit outcome is uncertain, the record may be redelivered. Therefore:

- Business operations should be idempotent.
- Log/trace the event id and source offset.
- Do not commit offsets before business effects complete if aiming for at-least-once.
- Do not treat a commit timeout as proof that the commit failed.

### 5.3 Heartbeats and session timeouts

During network interruptions, consumers may fail to send heartbeats. If the broker receives no heartbeat within session timeout, the member is removed from the group and partitions are reassigned.

This triggers a rebalance and records are delivered to another consumer. The old consumer might still be running listener code briefly; if side effects are not idempotent, two instances can modify business state concurrently.

When network connectivity recovers, the consumer can rejoin the group. Monitor rebalances, assignments, and offsets to confirm the group has stabilized.

### 5.4 Network timeout or slow listener processing?

Synchronous listeners running on the consumer thread can hold the thread too long. The consumer fails to call poll again on time, breaching max.poll.interval.ms. This is a processing timeout or poll interval violation, even though logs may later show consumer membership errors.

Example of a listener calling an external API:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void handle(OrderCreated event) {
    paymentClient.charge(event);
}
~~~

If paymentClient.charge() waits 5 minutes for an HTTP response, the consumer thread cannot poll during that window. If max.poll.interval.ms is shorter, the consumer can be kicked out of the group.

The solution is to set finite timeouts on HTTP calls, bound record/batch processing time, design appropriate retries, and align poll intervals with valid processing duration. Do not raise Kafka's request.timeout.ms to cure an HTTP timeout in the payment service.

## 6. Downstream network timeouts are not Kafka broker timeouts

A listener may call a database, REST API, gRPC service, or object storage. Timeouts at these dependencies are typically wrapped in exceptions thrown by the dependency's client.

Examples:

- HTTP connect timeout: unable to establish a connection to the API.
- HTTP read/response timeout: connection established, but no timely response received.
- JDBC socket timeout: database query or network response did not complete.
- gRPC deadline exceeded: RPC did not finish before deadline.

These are dependency network errors, not necessarily Kafka connectivity failures. However, they can cause listener processing to fail, leading to retries, rollbacks, or uncommitted offsets.

Log the dependency name, operation, endpoint/service, timeout setting, and correlation id. Avoid lumping all failures into a single kafka_network_timeout metric, which misleads diagnosis.

### 6.1 Downstream timeouts can increase Kafka lag

Impact chain:

1. Consumer polls record.
2. Listener calls downstream.
3. Downstream is slow or disconnected.
4. Listener holds consumer thread or retries.
5. Consumer processes fewer records.
6. Consumer lag increases.
7. If poll interval breaches limit, group rebalances.
8. Uncommitted records may be redelivered.

Rising lag is a symptom at the Kafka consumer, while the root cause may lie downstream. Increasing concurrency when a database/API is already overloaded can worsen the outage.

### 6.2 Setting timeouts per dependency

Do not use one generic timeout for all operations. For example:

- Connect timeout for TCP setup.
- Response/read timeout for waiting on data.
- Overall deadline for the entire request.
- Database query timeout and connection acquisition timeout.
- Kafka request timeout and delivery timeout.

Total duration of one processing attempt must align with the retry budget and max.poll.interval.ms. If one record calls multiple dependencies sequentially, total latency can exceed any individual call timeout.

## 7. Distinguishing timeouts from other Kafka errors

Timeouts are often confused with other failure modes. The table below aids classification:

| Error | Nature | What to check |
|---|---|---|
| Network timeout | Network operation did not finish on time | Request, connection, DNS, route, broker latency |
| Connection refused | TCP endpoint rejects connection | Broker listener, port, firewall, service |
| AuthenticationException | Client failed authentication | SASL, credentials, token, TLS identity |
| AuthorizationException | Client lacks permission | ACL, principal, topic/group permissions |
| SerializationException | Cannot serialize/deserialize data | Serializer, schema, payload |
| NotLeaderOrFollowerException | Metadata/leader changed or wrong broker targeted | Leader election, metadata refresh |
| NotEnoughReplicasException | ISR below min ISR for writes | ISR, broker replicas, min.insync.replicas |
| RecordTooLargeException | Record size exceeds limit | Producer/broker/topic limits |
| CommitFailedException | Commit failed, often tied to group state | Rebalance, membership, commit timing |
| RebalanceInProgressException | Group is rebalancing | Member changes, poll, heartbeat |
| ListenerExecutionFailedException | Listener processing threw an exception | Root cause in business code |
| Max poll interval exceeded | Consumer failed to poll again in time | Listener duration, thread blocking, batch size |

A Spring wrapper exception can hide an inner Kafka or dependency exception. Always inspect the root cause and full stack trace while recording the active operation.

## 8. Configuring timeouts in Spring Boot

Illustrative configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        max.block.ms: 60000
        reconnect.backoff.ms: 250
        reconnect.backoff.max.ms: 5000
    consumer:
      enable-auto-commit: false
      properties:
        request.timeout.ms: 30000
        default.api.timeout.ms: 60000
        reconnect.backoff.ms: 250
        reconnect.backoff.max.ms: 5000
        retry.backoff.ms: 500
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
        max.poll.interval.ms: 300000
    listener:
      poll-timeout: 1500
~~~

These numbers are strictly illustrative to show timeout relationships. Do not copy them to production without measuring network latency, broker processing time, listener duration, SLAs, and group protocols.

Keep in mind:

- Producer request timeout bounds a single request; delivery timeout bounds overall send time.
- max.block.ms affects how long send() waits for metadata/buffer.
- Consumer request timeout and default API timeout have different scopes.
- session.timeout.ms relates to heartbeat/member liveness.
- max.poll.interval.ms relates to intervals between polls.
- poll-timeout is a listener container setting, not a network request timeout.

If using Spring Kafka with a custom ProducerFactory/ConsumerFactory, verify properties are passed to the factory. Properties in application.yml may not automatically apply to manually created factories.

## 9. Choosing timeouts by latency and SLA

Do not pick timeouts by guesswork or set them all huge. Define deadlines per layer.

One approach:

1. Measure normal latency and p95/p99 for network/brokers.
2. Determine the brief interruption window the system should self-recover from.
3. Define SLAs for producer sends and consumer processing.
4. Choose a request timeout large enough to avoid false timeouts under normal load.
5. Choose a delivery timeout covering expected retries/backoff.
6. Ensure listener processing budget fits within max.poll.interval.ms.
7. Set downstream dependency timeouts separately.
8. Check shutdown timeouts and transaction timeouts if listeners use transactions.

For example, if p99 ProduceRequest latency is 800 ms at peak, a 100 ms request timeout triggers false timeouts. Yet setting a 10-minute request timeout delays outage detection too much. Use real measurements and recovery targets.

### 9.1 Nested deadlines

A business request can cross multiple layers:

~~~text
HTTP caller deadline
  -> application processing deadline
      -> Kafka producer delivery timeout
          -> individual request timeout
              -> TCP/network
~~~

Outer deadlines must be large enough for inner layers, without summing timeouts unboundedly. If the application deadline is shorter than delivery timeout, the caller may give up while the producer keeps trying to send. If the application retries immediately, duplicates can appear.

Determine who owns retries and deadlines. One layer should coordinate overall retries, while lower layers have bounded retries that stay within budget.

### 9.2 Retry budget

Suppose an operation has a 90-second deadline. The application might allocate:

- 10 seconds for connect/metadata.
- Up to 3 requests with a 20-second timeout each.
- Backoff of 1 and 2 seconds between attempts.
- The remainder for callbacks and result handling.

This is only an example. What matters is that total retry time fits within the operation's deadline and does not hold threads or buffers indefinitely.

## 10. Retrying and recovering from network timeouts

Retrying makes sense when an error is likely temporary and the operation can safely repeat. Not every timeout should be retried.

### 10.1 Classifying errors before retrying

**Bounded retry may apply:**

- Broker temporarily unreachable.
- Connection reset.
- Brief leader election.
- Request timeout due to temporary broker/network slowness.
- Downstream returns a transient error or rate limit with a recovery window.

**Must fix configuration or data first:**

- Unknown topic or wrong bootstrap server.
- Non-existent DNS hostname.
- Invalid TLS certificate or hostname mismatch.
- Wrong SASL credentials.
- Insufficient ACL permissions.
- Record serialization failure.
- Record exceeds size limit.
- Misconfigured endpoint.

Some errors initially surface as timeouts before the root cause becomes clear. Use root exceptions, logs, and network probes to classify.

### 10.2 Exponential backoff and jitter

Continuous immediate retries can overload brokers or downstream systems. Exponential backoff progressively increases wait time:

~~~text
attempt 1: wait 250 ms
attempt 2: wait 500 ms
attempt 3: wait 1 s
attempt 4: wait 2 s
attempt 5: wait 4 s
~~~

Jitter can be added so instances do not retry at the exact same instant. Backoff needs a maximum cap and an overall retry deadline.

The Kafka client already has its own reconnect and retry backoff. Application-level retries must coordinate with client retries rather than multiplying attempts indefinitely.

### 10.3 Circuit breaker and bulkhead

If a downstream system repeatedly times out, a circuit breaker can temporarily halt calls to let it recover. A bulkhead limits concurrent calls so a slow dependency does not exhaust all threads or connections.

With Kafka listeners, decide what happens when the circuit opens:

- Listener throws an exception so the record is retried later.
- Temporarily pause the container/partition per policy.
- Route the record to a retry topic if semantics allow.
- Persist the event into a pre-designed durable queue/outbox.

Never swallow an exception and commit the offset if business effects have not finished. Nor should you retry rapidly on the same record while the dependency remains down.

### 10.4 Retry topics and blocking retries

Blocking retries keep the record in the current processing flow and can block the partition. Retry topics move the record to another topic for later processing, reducing consumer thread blocking at the cost of potentially altering order.

Choose according to ordering requirements and SLAs. Broker/network timeouts at the Kafka producer layer may need client retry handling before listener-level retries. Downstream timeouts from business listeners may fit error handlers or retry topics better.

## 11. Spring Kafka error handling on timeouts

Spring Kafka listener containers invoke the error handler when a listener throws an exception. Retrying depends on exception type, error handler configuration, and transaction mode.

Illustrative example configuring DefaultErrorHandler with bounded retries:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler() {
    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            new FixedBackOff(1_000L, 3L)
        );

    handler.addRetryableExceptions(
        RetryableBusinessException.class
    );

    return handler;
}
~~~

This is an illustrative example. In real applications:

- This error handler processes exceptions originating inside the listener. Internal Kafka consumer network requests/reconnects are managed by the Kafka client; do not assume fetch/connection failures are routed into the listener error handler.
- HTTP/database timeouts may be wrapped in dependency client exceptions. Translate temporary errors into a business exception such as RetryableBusinessException only after confirming the operation can be safely retried.
- Do not add all exceptions to retryable.
- Certain authentication/authorization/configuration errors cannot be fixed by retrying.
- Retry counts must be finite and backoffs must fit SLAs.
- For unrecoverable records, consider a DLT.
- If using transactional listeners, transaction rollback/retry/recovery must be configured appropriately.

### 11.1 Timeouts inside listeners and retries

If a listener calls a downstream service and gets a SocketTimeoutException, the error handler can retry the record. However, retrying only helps if the downstream service can recover within the retry window.

If the listener performed partial side effects before timing out, retrying the record may repeat those side effects. An idempotency key or proper transaction/outbox/inbox is required.

### 11.2 Do not use retries to mask prolonged broker outages

If the entire Kafka cluster is unreachable, listener record retries cannot repair the network path. DLT producers may also fail to send. In that scenario, restore broker connectivity or use a pre-designed durable fallback.

## 12. Ambiguous outcomes and idempotency

Timeouts are one of the most common sources of ambiguous outcomes. The client cannot know for sure whether the operation executed.

### 12.1 Producer send timeout

The broker may append the record and then lose the ACK. The application gets an error even though the record may already exist. Retrying with a new event id creates a brand-new business event in data terms.

Solutions:

- Enable idempotent producer when appropriate.
- Keep event id stable across resend attempts.
- Persist intent to emit events in a transactional outbox if the event is mandatory.
- Consumer deduplicates by event id or business key.
- Reconcile topic/partition/offset during investigation.

### 12.2 Consumer commit timeout

A listener may finish a database update while the offset commit times out. The consumer group may redeliver the record after a rebalance or restart.

Solutions:

- Log event id and source offset.
- Maintain a unique constraint/inbox table in the database if required by the business.
- Business handlers must be idempotent.
- Commit offsets per policy only after business effects finish.
- Do not arbitrarily reset offsets when commit outcomes are uncertain.

### 12.3 HTTP timeout after downstream processed the request

An API may complete an operation while the response is lost. Retrying the request can trigger the side effect a second time.

Use an idempotency key supported by the downstream service. If downstream does not support it, reconciliation or a domain model capable of detecting duplicates is required.

## 13. Observing network timeouts

Observe across three layers: Kafka client, broker/network, and business processing.

### 13.1 Producer metrics

Track:

- request-latency-avg and request-latency-max.
- record-error-rate and record-retry-rate.
- record-send-rate.
- request-rate and response-rate.
- buffer-available-bytes.
- record-queue-time-avg.
- batch-size-avg.
- connection creation/close and node connection state if exposed by your exporter.

Some metric names vary by client version or exporter. Verify actual metrics before building dashboards.

### 13.2 Consumer metrics

Track:

- fetch-latency-avg/max.
- fetch-rate and records-consumed-rate.
- commit-latency-avg/max.
- heartbeat rate and responses.
- assigned partitions.
- rebalance rate.
- consumer lag by group/topic/partition.
- poll interval and listener processing duration.
- connection state and request errors.

Rising lag paired with high fetch latency suggests broker/network or fetch load issues. Rising lag paired with high listener duration suggests a processing/downstream bottleneck.

### 13.3 Broker and network metrics

Track:

- Produce/Fetch request handler latency.
- Request queue time and handler saturation.
- Network processor idle percent.
- Bytes in/out, connection count, and connection creation rate.
- CPU, disk I/O, page cache, and filesystem.
- Broker availability and leader distribution.
- Under-replicated partitions, ISR shrink/expand.
- TCP retransmissions, packet loss, and connection resets if provided by infrastructure.
- DNS resolution errors and TLS handshake failures.

If multiple services simultaneously time out to one broker, suspect that broker or a shared network segment. If only one pod fails, inspect that pod's node, DNS cache, routes, security policies, and local resources.

### 13.4 Required logs

Each error should record:

- Service name, environment, and instance/pod.
- Kafka client id and group id if consumer.
- Operation: metadata, produce, fetch, commit, transaction, or downstream call.
- Topic, partition, and offset if available.
- Target broker node/host/port.
- Exception class and root cause.
- Relevant timeout setting/deadline.
- Event id/correlation id.
- Retry count and elapsed wait time.

Do not log credentials, SASL secrets, tokens, or sensitive payloads.

## 14. Isolation procedure during a network timeout

When alerts or logs show timeouts, follow this order:

1. **Identify the operation**: producer send, metadata, consumer fetch, offset commit, transaction, or downstream HTTP/database call.
2. **Identify the scope**: one pod, one broker, one partition, one service, one AZ, or the entire cluster.
3. **Read the root cause**: TimeoutException, NetworkException, DisconnectException, UnknownHostException, SocketTimeoutException, or dependency exception.
4. **Verify target addresses**: bootstrap servers, advertised broker addresses, DNS, ports, and routes from the failing pod itself.
5. **Verify connectivity**: TCP connect/reset, TLS handshake, SASL, and firewalls/network policies.
6. **Correlate broker metrics**: request latency, queue time, CPU, disk, network processor, and broker restarts.
7. **Check timeout hierarchy**: request timeout, delivery timeout, max block, API timeout, session timeout, max poll interval, and downstream deadlines.
8. **Assess operation outcome**: could the record have been appended? Could business effects have finished? Could the offset commit have been applied?
9. **Controlled recovery**: fix network/config, allow clients to reconnect, use bounded retries, and avoid unnecessary simultaneous restarts.
10. **Verify after recovery**: normal send/fetch/commit latency, stable consumer group, decreasing lag, and no lost or duplicated business events.

Do not start by increasing every timeout. First identify the operation and root cause; if the network route is broken or the broker address is unreachable, raising timeouts only prolongs waiting.

## 15. Common scenarios and resolutions

| Symptom | Possible cause | Resolution |
|---|---|---|
| Producer send timeout to one broker | Overloaded broker, unreachable leader broker, or broken network path | Identify partition leader and broker; check request latency, routes, and reconnects |
| Bootstrap connects but produce fails | advertised.listeners returns addresses unreachable from the app | Check metadata and advertised listeners from the pod's network |
| Consumer fetch timeout | Slow broker, network packet loss, or broker connection reset | Inspect fetch latency, broker health, and connection state |
| Offset commit timeout | Unreachable group coordinator or lost response | Check coordinator, rebalances, and committed offsets; ensure idempotency |
| Multiple pods time out together | Shared broker, DNS, firewall, or network segment | Correlate errors by broker and zone; inspect shared infrastructure |
| Only one pod times out | Node/pod DNS, route, CPU pause, or local resources | Compare healthy and failing pods over the same timeframe |
| Timeouts rise with traffic | Broker/request handler/buffer or downstream saturation | Inspect queues, CPU, disk, pools, and throughput |
| Listener times out while Kafka client is healthy | Slow HTTP/database downstream | Inspect dependency latency and configure dedicated timeouts |
| Consumer rebalances after slow call | Listener blocks beyond max.poll.interval.ms | Bound processing time, tune poll budget and retries |
| Timeouts after leader election | Client refreshing metadata/reconnecting | Monitor leader and retry; confirm record outcome |
| Transaction commit timeout | Coordinator/network issue or uncertain transaction state | Inspect transaction lifecycle, producer fencing, and idempotency |

## 16. Practical examples

### 16.1 Producer with timeouts and idempotence

Illustrative configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        max.block.ms: 60000
~~~

In this example, the producer awaits ACKs per acks=all, retries per client policy within delivery timeout, and waits for metadata/buffer up to max.block.ms. Values must be set based on measured latency and SLAs.

### 16.2 Consumer timeouts and poll budget

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        request.timeout.ms: 30000
        default.api.timeout.ms: 60000
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
        max.poll.interval.ms: 300000
    listener:
      poll-timeout: 1500ms
~~~

This configuration illustrates that request, API, session, poll interval, and container poll timeout are distinct limits. Adjust them according to the consumer group protocol and Kafka version in use.

### 16.3 Listener calling downstream with finite timeout

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service-prod"
)
public void handle(OrderCreated event) {
    try {
        paymentClient.charge(
            event.orderId(),
            event.eventId()
        );
    } catch (SocketTimeoutException ex) {
        throw new RetryableBusinessException(
            "Payment service response timed out",
            ex
        );
    }
}
~~~

This example shows a downstream timeout translated into a retryable business error per policy. In a real application, the payment client must have its own connect/read/deadline timeouts and eventId must be used downstream as an idempotency key. Do not retry if the charge outcome is unknown and the API lacks idempotency or reconciliation.

## 17. Testing network timeouts

Test in staging or a test cluster with matching topology. Do not inject network faults in production without clear blast-radius limits and kill switches.

Scenarios to test:

- Block TCP connectivity from a test consumer to a test broker.
- Cause DNS resolution failure for a broker hostname in an isolated environment.
- Inject controlled packet delay/loss.
- Restart a broker to observe leader election and client reconnect.
- Generate high broker load to observe request latency and timeouts.
- Slow down a downstream HTTP service to distinguish listener timeouts from Kafka request timeouts.
- Drop connections during producer sends and reconcile event id/offsets.
- Drop connections during offset commits and confirm safe duplicate handling.
- Inspect producer buffers when brokers reject requests.
- Inspect consumer heartbeats and rebalances during network interruptions.

Every test needs a hypothesis, time limit, target scope, record ids, and recovery criteria. For example: after the broker returns, producer sends succeed within deadline; the consumer group rejoins; offsets advance; no unpermitted duplicate side effects occur.

## 18. Network timeout operational checklist

**Classification**

- [ ] Know whether the timeout occurs at producer, consumer, broker request, coordinator, or downstream.
- [ ] Root cause is logged rather than only the exception wrapper.
- [ ] Timeouts, connection refused, authentication, and authorization are distinguished.
- [ ] Affected broker/partition/operation is identified.

**Configuration**

- [ ] request.timeout.ms matches real latency.
- [ ] delivery.timeout.ms covers the retry budget and fits the SLA.
- [ ] max.block.ms is accounted for regarding metadata/buffer waits.
- [ ] default.api.timeout.ms is properly understood for consumer APIs.
- [ ] reconnect/retry backoffs are bounded.
- [ ] session.timeout.ms and max.poll.interval.ms are distinguished.
- [ ] Downstream connect/read/deadline timeouts are configured separately.

**Data safety**

- [ ] Producer idempotence is enabled where appropriate.
- [ ] Event id/business key remains stable across retries.
- [ ] Consumer side effects are idempotent or backed by inbox/deduplication.
- [ ] Offsets are committed per policy only after required business effects.
- [ ] Outbox or durable fallback exists for mandatory events.
- [ ] Timeouts are never treated as proof that an operation did not execute.

**Observability and recovery**

- [ ] Track producer request latency, retries, errors, and buffers.
- [ ] Track consumer fetch/commit latency, lag, and rebalances.
- [ ] Track broker queues, network, disk, and connections.
- [ ] Log operation, broker, topic/partition, event id, and timeout settings.
- [ ] Bounded retries with backoff/jitter.
- [ ] Runbooks exist to verify DNS, advertised.listeners, routes, TLS, and ACLs.
- [ ] Reconnects, leader loss, commit timeouts, and downstream timeouts have been rehearsed.

A network timeout is a signal about an operation's deadline, not definitive proof that data was neither written nor processed. In Spring Kafka, identify which layer timed out and distinguish request timeout from delivery timeout, poll interval, and downstream timeouts. By combining client/broker observability, bounded retries, idempotent producers, idempotent consumers, and offset/event id reconciliation workflows, systems can recover from network interruptions while keeping duplicates and backlogs under control.

