# Avoiding Restart Loops on Transient Broker Failures

In a Spring Kafka system, brokers can become temporarily unreachable due to rolling restarts, leader elections, network interruptions, DNS issues, TLS handshakes, overload, or a single-node failure. If the application stops listener containers on every error, throws to exit the process, and lets Kubernetes restart the pod immediately, a brief blip can turn into a prolonged **restart loop**.

Restart loops make multiple bad things happen simultaneously: consumer groups repeatedly leave and rejoin, partitions rebalance multiple times, producers flood brokers with new connections, requests retry in bursts, and logs and alerts spike—all while recovering brokers face extra load. Once brokers come back, clients can reconnect all at once and create a traffic spike.

The principle of **Avoiding restart loops on transient broker failures** is to distinguish self-recoverable connectivity errors from configuration or lifecycle errors that truly require intervention. Kafka clients already have reconnect/retry mechanisms for many transient failures. Spring Kafka containers and applications must give those mechanisms a chance to work, apply bounded backoff when restarts are genuinely required, and build readiness/liveness to reflect real business state.

This lesson belongs to the **Health and readiness** chapter of Spring Kafka Reliability Operations. It covers Kafka client retries, listener container lifecycles, producer/consumer behavior, Kubernetes probes, and how to observe and test transient broker disconnects.

## 1. How does a restart loop form?

Suppose a broker performs a 30-second rolling restart. Each consumer pod sees connection errors. The application has a health check that treats an unreachable broker as a liveness failure, so Kubernetes restarts the pod.

    Broker performing rolling restart
             |
             v
    Consumer receives disconnect / request timeout
             |
             v
    Liveness probe returns DOWN
             |
             v
    Kubernetes kills and restarts pod
             |
             v
    Consumer group member leaves group
             |
             v
    Remaining members rebalance
             |
             v
    New pod initializes producer/consumer
             |
             v
    Broker is still not ready
             |
             +------> repeats from the start

When all replicas are affected together, they can restart nearly simultaneously. As soon as brokers return, they are hit with new connections, metadata requests, group joins, producer initializations, and authentication all at once. This is a form of **thundering herd**.

A single disconnect does not necessarily mean the consumer is dead. The Kafka client can keep reconnecting and resume operation without restarting the JVM or container.

## 2. Distinguishing transient broker errors from application faults

Not every Kafka error should be handled with the same policy.

| Situation | Example | Initial Action |
|---|---|---|
| Broker temporarily unreachable | Node restart, leader election, network flap | Let Kafka client reconnect/retry |
| Request transiently fails | Timeout, coordinator leadership change | Retry per client policy and deadline |
| Authentication/authorization failure | Wrong secret, missing ACL | Fix credentials/ACLs; use controlled retry interval if appropriate |
| Producer fenced | Duplicate transactional identity, zombie producer still alive | Fix identity/lifecycle; simple restart is insufficient |
| Invalid offset | Retention deleted needed offset, reset policy is `none` | Decide recovery based on data semantics |
| Listener business processing error | Validation, database exception | Use error handler/retry/DLT for the record |
| JVM or process hung | Deadlock, OOM, thread starvation | Investigate liveness and process resources |
| Misconfigured cluster | Wrong bootstrap address, unreachable `advertised.listeners` | Fix configuration/network |

The key is identifying **whether the fault lies in the broker/network, Kafka client, listener container, business handler, or JVM**. A single HTTP health check failing to reach a broker is not enough to conclude the entire process needs a restart.

## 3. Kafka clients already have reconnect and retry

The Kafka Java client manages broker connections and has built-in mechanisms to reconnect when brokers temporarily lose contact. For many transient network/leader/coordinator errors, the client refreshes metadata, reconnects, and retries requests per policy.

Related configurations include:

- `reconnect.backoff.ms`: base backoff time between reconnect attempts.
- `reconnect.backoff.max.ms`: upper bound on reconnect backoff.
- `retry.backoff.ms`: wait interval between retries of certain failed requests.
- `request.timeout.ms`: time to wait for a request response.
- `delivery.timeout.ms`: total time budget the producer tries to complete a send.
- `metadata.max.age.ms`: periodic metadata refresh interval when no earlier refresh is triggered.

Kafka clients may apply increasing backoff and jitter depending on implementation and version. Do not assume all requests retry identically: retryability depends on request type, exception, producer/consumer API, and group/transaction state.

**Reconnect is not the same as restarting a process.** Reconnecting recreates broker connections inside the existing client; restarting a process recreates the entire Spring context, consumers, producers, thread pools, and many other resources.

## 4. Choosing bootstrap servers with sufficient redundancy

`bootstrap.servers` configuration should list multiple reachable broker endpoints in the cluster rather than a single node:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-0.kafka.svc:9092
      - kafka-1.kafka.svc:9092
      - kafka-2.kafka.svc:9092
~~~

The client uses bootstrap endpoints to fetch metadata and then connects to the appropriate broker for each partition/request. A multi-broker bootstrap list gives the client multiple starting points if one endpoint is temporarily unavailable.

However, a bootstrap list cannot fix:

- Broken DNS/service discovery for the whole cluster.
- `advertised.listeners` returning addresses the client cannot reach.
- Network policies blocking all brokers.
- Invalid TLS/SASL credentials.
- A cluster that is genuinely down.

After bootstrapping, the client must reach the broker addresses advertised in metadata. If the bootstrap address is reachable yet advertised addresses are unreachable, the client will keep failing.

Do not add fake hostnames just to make the list longer. Every endpoint must belong to the real cluster and match the network/security context.

## 5. Configuring reconnect backoff

Example consumer and producer configuration in Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-0:9092,kafka-1:9092,kafka-2:9092
    consumer:
      group-id: order-workers
      enable-auto-commit: false
      properties:
        reconnect.backoff.ms: 500
        reconnect.backoff.max.ms: 10000
        retry.backoff.ms: 500
        request.timeout.ms: 30000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
    producer:
      properties:
        reconnect.backoff.ms: 500
        reconnect.backoff.max.ms: 10000
        retry.backoff.ms: 500
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        acks: all
        enable.idempotence: true
~~~

These values are only **illustrative starting points**, not optimal settings for every cluster. They must match network RTT, broker capacity, SLAs, application timeouts, and Kafka client version.

Notes:

- `reconnect.backoff.ms` controls reconnect attempts, not the wait time for an entire business operation.
- `retry.backoff.ms` does not replace `delivery.timeout.ms`.
- A producer can fail a send with a timeout once the delivery deadline expires even while the client stays alive and reconnects.
- `session.timeout.ms` and `heartbeat.interval.ms` govern group membership, not producer retries.
- `enable.idempotence` helps guard against duplicates from certain producer retries within the Kafka protocol scope; it does not deduplicate new business commands.

Do not set backoff too tiny across all replicas. When brokers recover, hundreds of consumers could storm connections and requests at high frequency.

## 6. Exponential backoff and jitter

When the application genuinely needs to retry an operation outside the Kafka client mechanism, exponential backoff increases wait intervals across failures.

A simple formula:

    delay(n) = min(maxDelay, baseDelay * 2^n)

Example with `baseDelay = 1 second`, `maxDelay = 30 seconds`:

| Attempt | Delay before next attempt |
|---:|---:|
| 0 | 1 second |
| 1 | 2 seconds |
| 2 | 4 seconds |
| 3 | 8 seconds |
| 4 | 16 seconds |
| 5 onward | Max 30 seconds |

If every pod uses the exact same fixed schedule, they can still retry in lockstep. **Jitter** adds randomness to spread out attempts.

One form of full jitter:

    delay = random(0, min(maxDelay, baseDelay * 2^attempt))

Jitter prevents multiple instances from reconnecting or restarting at the exact same instant. Retries must have an appropriate deadline or cap; backoff should never make a business request wait indefinitely.

The Kafka client already has its own reconnect backoff. Do not wrap an outer retry loop around every poll/request without understanding how the two layers multiply.

## 7. Do not restart containers on a single disconnect

A consumer may log a disconnect or request timeout while remaining alive and actively retrying connections. Calling `stop()` then `start()` repeatedly can disrupt the client's own recovery process.

A sensible policy:

1. Record the error and timestamp.
2. Check whether the container is still running.
3. Observe client reconnects and request failures over a time window.
4. Track consumer group assignment, lag, and progress.
5. Intervene on lifecycle only if the container has stopped or a confirmed terminal error occurred.
6. If a restart is needed, use backoff/cooldown and cap restart attempts.

Never treat a single `Connection to node ... could not be established` line as a pod restart trigger. Verify that the fault is sustained, impairs progress, and lacks an appropriate self-recovery path.

## 8. Broker outages do not necessarily stop listener containers

When brokers temporarily disconnect, the Kafka consumer can remain inside its poll loop and keep reconnecting. The Spring Kafka container can continue reporting running while record processing pauses temporarily.

This means:

- `container.isRunning() == true` does not prove brokers are reachable.
- A poll returning no records does not prove the group lost assignments.
- A broker disconnect does not necessarily emit `ConsumerStoppedEvent`.
- The container can recover without any new start/stop events.
- Consumer lag can grow while brokers or leaders are unavailable.

Monitoring must observe lifecycle, broker connectivity, group assignment, poll progress, and lag together. Do not decide restarts from a single metric.

## 9. When can a Spring Kafka container stop?

Certain consumer/lifecycle-level errors cause the container to stop rather than merely reconnect. Examples can include authentication/authorization exceptions per policy, unrecoverable offset errors, producer fencing in transactional listeners, or other terminal errors depending on version and configuration.

When a container actually stops, inspect:

- `ConsumerStoppedEvent` and its reason if emitted.
- `ContainerStoppedEvent`/lifecycle state.
- Root exception preceding the stop.
- Whether the listener container has an auto-start/restart policy.
- Whether an auth retry interval is configured.
- Whether brokers/network have recovered.
- Whether restarting solves the cause or merely repeats the same error.

Do not treat every error in Kafka client logs as a container-stopping error. Separate request errors retried inside the client from exceptions terminating container lifecycle.

## 10. AuthenticationException and authExceptionRetryInterval

A special case occurs when brokers temporarily reject authentication or authorization. If a Spring Kafka container stops on authentication/authorization exceptions, the application can configure a wait interval before retrying using `authExceptionRetryInterval` in supported versions.

Example Java configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setAuthExceptionRetryInterval(Duration.ofSeconds(10));

    return factory;
}
~~~

This example uses Spring Kafka APIs supporting that setter; verify Javadoc for your project's version. If unset, some versions/containers may stop when authentication/authorization exceptions appear instead of retrying on an interval.

Distinguish:

- Broker temporarily unready to answer authentication requests.
- Wrong or expired credentials.
- Missing ACL permissions.
- Misconfigured certificate/CA/TLS settings.

Retry intervals only wait before retrying. They cannot fix wrong passwords or permanently denied ACLs. For configuration faults, alert and repair secrets/permissions rather than retrying rapidly forever.

## 11. Listener error handlers are not broker reconnect policies

Spring Kafka provides `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, and retry/recovery mechanisms to handle **record listener failures**.

Example:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

This configuration illustrates finite retries for record processing failures. It is not how you configure reconnects when brokers stop accepting connections.

Distinguish:

| Error | Appropriate Mechanism |
|---|---|
| JSON/schema/business validation of a record | Error handler, bounded retries, DLT |
| Database timeout inside listener | Controlled retries, idempotency, suitable circuit breaker |
| Broker disconnect / leader unavailable | Kafka client reconnect/retry |
| Consumer group rebalance | Kafka group protocol and rebalance handling |
| Authentication/authorization | Credential/ACL repair and auth retry interval if suitable |
| Process deadlock/OOM | Liveness/process recovery and root-cause fix |

Using an error handler to throw errors outward just to restart the pod whenever a broker blips turns an infrastructure blip into a restart loop.

## 12. Producer send retries and delivery timeouts

Producers can retry certain transient failures. Key properties:

- `retries`: retry count in versions/configs still using this limit; modern clients typically manage retries alongside delivery timeout.
- `request.timeout.ms`: time waiting for a single request response.
- `delivery.timeout.ms`: maximum total time the producer tries to complete sending a record.
- `retry.backoff.ms`: wait between request retries.
- `acks`: broker acknowledgement level.
- `enable.idempotence`: helps prevent duplicates from producer-protocol retries.

In modern Kafka clients, producer retries and delivery timeout work together; consult documentation for your exact version. A send can end with an exception when the delivery deadline expires, yet that does not mean the producer or JVM needs restarting.

With Spring Kafka, `KafkaTemplate.send()` returns a future. The application must observe future completion and handle failures per API contract. Never fire-and-forget `send()`, ignore the future, and log success as if the broker received the record.

## 13. KafkaTemplate and send errors during broker outages

Example:

~~~java
public void publish(OrderCreated event) {

    CompletableFuture<SendResult<String, OrderCreated>> future =
            kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
            );

    future.whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Kafka publish failed: eventId={}",
                event.eventId(),
                error
            );
        }
        else {
            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Kafka publish acknowledged: eventId={}, topic={}, partition={}, offset={}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        }
    });
}
~~~

This Spring Kafka 3.x example uses `CompletableFuture`; return types differ in older versions. Callbacks may run on another thread, requiring context propagation if logging relies on MDC/tracing.

During extended broker outages, the future may complete only after producer retries or `delivery.timeout.ms` expire. If the application handles HTTP requests, clearly decide whether the API waits for the outcome, returns a pending status via an outbox, or returns a retryable error.

Never hold request threads waiting indefinitely. Enforce an overall request deadline and a durable mechanism if business work must continue after the HTTP connection closes.

## 14. Transactional producers during broker errors

Kafka transactions require the transaction coordinator and participating brokers. When brokers/coordinators are temporarily unavailable, transactions can time out or abort.

Principles:

- Do not create a new producer on every timeout exception.
- Do not dynamically change `transactional.id` to dodge coordinator errors.
- Do not repeatedly restart containers while the client can reconnect.
- Keep event IDs stable to handle uncertain outcomes.
- Monitor transaction commits, aborts, and fencing separately.
- Distinguish transient timeouts from `ProducerFencedException`.

Fencing normally relates to transactional identity/producer epochs, not a normal disconnect. Repeatedly restarting with a conflicting transactional identity can repeat fencing.

If a Kafka transaction aborts, transactional output is not visible to `read_committed` consumers. If the application already performed external database/API side effects outside Kafka, those side effects do not roll back automatically; idempotency/reconciliation is required.

## 15. Consumer behavior when brokers are temporarily unreachable

Consumers normally need brokers to fetch, commit offsets, and participate in group coordination. When connectivity drops:

- Fetch requests may fail or wait for retries.
- Metadata may be refreshed.
- Heartbeat/coordinator requests may be affected.
- The group may rebalance if membership cannot be maintained.
- Consumer lag rises while producers keep writing and consumers cannot read.
- Once connectivity returns, consumers can resume from their position/committed offset depending on state.

Never reset offsets to "wake up" a consumer. If an offset commit failed, already-processed records may be redelivered. That is one reason side effects must be idempotent.

In a consumer group, a broker outage lasting longer than membership timeouts can shift assignments. That does not require restarting every member; once the cluster stabilizes, the group protocol can complete rebalancing.

## 16. session.timeout.ms and max.poll.interval.ms are two different issues

These two timeouts are often confused:

- `session.timeout.ms`: how long the broker waits for valid heartbeats before considering a member lost under the group protocol.
- `max.poll.interval.ms`: maximum time between polls under consumer group rules, especially when applications take long to process records.

A slow-processing listener can exceed `max.poll.interval.ms` even while brokers are reachable. A network outage can prevent heartbeats from reaching brokers and trigger session timeout.

Do not set both values huge just to avoid restarts/rebalances. Doing so delays detection of genuinely dead consumers.

Measure listener processing time, poll cadence, heartbeat errors, and broker availability to choose timeouts with sensible headroom.

## 17. max.poll.records and processing time per poll

If each poll returns too many records, the listener can take too long to finish the batch and return to `poll()`. During broker/network trouble, this adds onto processing time and can cause membership instability.

Estimate:

    PollWorkTime
      ~= RecordsPerPoll * AverageProcessingTime
         + RetryTime
         + SynchronousCommitWait

Example:

    max.poll.records = 200
    processing p95 = 100 ms/record

    Approximate work time = 20 seconds
      (excluding retries, commits, and scheduling)

Size `max.poll.records` based on actual processing time and `max.poll.interval.ms`. Shrinking batch sizes lets consumers return to `poll()` sooner, though it increases overhead.

Broker outages are not the only reason to tune poll sizes; evaluate normal and worst-case workloads.

## 18. Do Spring Kafka containers need restarting after reconnect?

In many cases, no. If the Kafka client remains alive, the container remains running, and the client reconnects on its own, the listener will resume receiving records once brokers/leaders/coordinators are ready.

Consider restarting a container only when there is evidence lifecycle has stopped or the client/container entered an unrecoverable state under the contract of your version.

Before restarting, confirm:

1. Does `KafkaListenerEndpointRegistry` have the container for that exact ID?
2. What state does `isRunning()` report?
3. Was `ConsumerStoppedEvent` emitted, and what was the reason?
4. Is there a terminal exception or only a network disconnect?
5. Have brokers actually recovered?
6. Are there credential/ACL/transactional ID issues?
7. Will restarting affect other child consumers in a concurrent container?
8. Are restart cooldowns and attempt caps in place?

Do not restart a healthy running container merely because broker request failure metrics briefly spiked. Observe over time and check progress.

## 19. Readiness and liveness should not have identical dependencies

Kubernetes commonly has two probes:

**Liveness** answers whether the process must be restarted because it can no longer progress at the application level.

**Readiness** answers whether the pod should receive more traffic from the service.

Temporarily unavailable brokers are usually not sufficient reason to fail liveness. Restarting the JVM does not bring brokers back up; it only drops connections the client is retrying and triggers rebalances.

Readiness can reflect broker dependencies if the service's business logic genuinely needs Kafka to accept traffic safely. However, policy must match the contract:

- APIs able to write to a durable outbox when Kafka is down: can stay ready while the database and outbox have capacity.
- APIs that finish requests only on successful Kafka publish: can return controlled errors or fail readiness per SLO.
- Consumer-only workers: readiness can degrade when the group cannot process workloads beyond thresholds, with grace periods and no restart loops.
- Services with multiple consumer groups: an auxiliary group failing does not necessarily make the whole API service NotReady.

There is no single policy for all applications.

## 20. Example liveness probe independent of brokers

A liveness endpoint should reflect the process and critical internal components, avoiding synchronous Kafka broker calls on every probe.

Illustrative Kubernetes configuration:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

In Spring Boot, configure health groups:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

When using Spring Boot Actuator probe groups, liveness/readiness endpoints reflect health indicators wired into each group per configuration. Do not add a Kafka indicator to liveness by default.

When brokers experience temporary faults, liveness can stay `UP` so the process keeps its Kafka clients alive and reconnects. Readiness is decided by serving capability and SLOs.

## 21. When should readiness go DOWN because of Kafka?

Marking readiness `DOWN` makes sense if a pod accepting new requests cannot fulfill its committed contract and has no durable fallback.

Example:

- An API receives commands and must publish to Kafka before returning success.
- There is no outbox/database queue to hold commands while Kafka is down.
- Returning success in that state would lose business intent.

In another scenario:

- The API writes commands to a database/outbox first.
- A background publisher emits events once Kafka returns.
- Requests can be acknowledged under an "accepted/pending" contract.

Here the service can stay ready as long as outbox capacity, database, and SLAs hold. The Kafka outage is surfaced via backlog/alerts rather than pulling pods from Service endpoints.

For consumer workers, readiness should evaluate group-level processing. A pod legitimately holding no partitions due to excess consumers should not automatically go `DOWN`.

## 22. Do not call brokers synchronously on every readiness probe

A custom `HealthIndicator` might call `AdminClient` or `KafkaTemplate` to check brokers. If every probe makes a network request with a long timeout, broker trouble can slow down the health endpoint and cause probe failures.

Risks:

- Probes timing out waiting on Kafka requests.
- Each pod continuously adding requests to an overloaded broker.
- Readiness oscillating on a single brief fault.
- Health endpoints saturating thread pools during outages.
- Probes and recovery creating a thundering herd together.

A safer design:

1. Run a periodic monitor with short, bounded timeouts.
2. Store a snapshot of broker/connectivity status and last check time.
3. Have the health endpoint read only the in-memory snapshot.
4. Evaluate state using thresholds and hysteresis.
5. If the snapshot is too old, return `UNKNOWN`/`DEGRADED` per policy.
6. Never create a new Kafka `AdminClient` on every probe.

Probes must be fast, deterministic, and never become an extra load generator for struggling brokers.

## 23. Grace periods and hysteresis for readiness

A single failed broker check can be transient. If readiness flips `UP`/`DOWN` on every request, the endpoint will flap.

Use two thresholds:

    Continuous broker check successes
      -> mark recovered after stability condition

    Continuous broker check failures over duration T
      -> mark unavailable

Example:

| Signal | Illustrative Policy |
|---|---|
| Single request timeout | Record metric, keep previous state |
| 3 consecutive failures within 15 seconds | Mark degraded |
| 2 minutes without recovery | High-severity alert |
| 5 consecutive successful checks | Mark recovered |
| Container not running | Separate lifecycle-based health |

This is an example policy; pick thresholds for your SLOs, traffic, and timeouts. Hysteresis prevents flapping without hiding prolonged outages.

If health state is group-level, distinguish single-member faults from whole-group faults. You can source group metrics from an external monitor rather than having every pod infer global state independently.

## 24. Startup when brokers are not ready yet

An application may need to start its HTTP server and health endpoints before the Kafka cluster is ready. If the startup path forces a broker call and fails fast, the app cannot come up even though Kafka clients could have reconnected shortly after.

Check:

- Does any custom `@PostConstruct` call `AdminClient` or `KafkaTemplate`?
- Does any startup runner wait indefinitely for topic metadata?
- Is topic provisioning running synchronously?
- Is `KafkaAdmin` configured to fail fatally when brokers are unavailable?
- Do listener containers auto-start right on context refresh?
- Does startup readiness have a grace period?

If business logic permits, decouple process startup from broker readiness. Containers can start and clients can reconnect on their own; readiness reflects true serving capability.

If topics/ACLs/schemas must strictly be verified before taking traffic, use a startup/readiness gate with explicit timeouts and clear failure reasons. Never loop-restart the process just to retry a startup check without backoff.

## 25. Listener container autoStartup and lifecycle

Spring Kafka listener containers are managed by the Spring lifecycle and typically auto-start per configuration. You can set `autoStartup=false` so the application starts explicitly after an internal condition is met, though you should not use it to build a tight broker-polling loop.

Example:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-workers",
    autoStartup = "false"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Containers can then be controlled via `KafkaListenerEndpointRegistry`:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

This is a lifecycle control example, not a complete supervisor. Ensure `start()` is not called concurrently from multiple threads, apply backoff, and track clear state. If the broker only briefly disconnected while the container is already running, there is no need to call `start()`.

With concurrent containers, `start()`/`stop()` on the parent can affect all child consumers. If only one child has an issue, understand the API and ownership before acting.

## 26. Restart supervisors with backoff

If a container genuinely stopped due to a recoverable error, a supervisor can attempt to start it again after a wait. Manage:

- Restart count within a time window.
- Exponential backoff and jitter.
- Cooldown after a successful start.
- In-progress restart state to avoid concurrent triggers.
- Classification of terminal vs. non-terminal errors.
- No restarts while the pod is shutting down.
- No continuous restarts while credentials/ACLs/transactional identities remain unfixed.

Model:

    ContainerStoppedEvent / lifecycle state
                |
                v
        Recovery supervisor
                |
                v
       Classify root cause
          /             \
      transient       configuration
         |                  |
         v                  v
    backoff + retry     alert + wait for fix
         |
         v
     container.start()
         |
         v
    observe started + assignment + progress

Never restart merely for `ConsumerStoppedEvent.NORMAL` during rolling deployments or application shutdown. Never treat every `ERROR` as retryable.

## 27. Example state machine for restart policies

A supervisor should have explicit states:

| State | Meaning | Transitions |
|---|---|---|
| `RUNNING` | Container is operating | Stop/error → `STOPPED` |
| `STOPPED` | Container stopped | If transient and not shutting down → `BACKOFF` |
| `BACKOFF` | Waiting for next attempt | Delay elapsed → `STARTING` |
| `STARTING` | Start requested | Started → `RUNNING`; failure → `BACKOFF` |
| `CIRCUIT_OPEN` | Restart limit exceeded | Wait for cooldown/operator |
| `SHUTTING_DOWN` | Application closing | No restarts |

Rules:

- Only one restart attempt runs at a time per listener.
- Duplicate events do not spawn extra restarts.
- Restart attempts are capped.
- Backoff includes jitter.
- Once the container runs steadily long enough, reset failure counters.
- If errors like `AUTH`/`FENCED`/`NO_OFFSET` are config/data issues, do not fast-restart infinitely.
- On process shutdown, cancel pending restart tasks.

This state machine can be implemented with a scheduler, lock/atomic state, or a suitable supervisor service. Avoid building complex custom restart machinery if Kubernetes or the framework already manages lifecycle adequately.

## 28. Producer outages and the transactional outbox

If an API receives business commands and must publish events while Kafka may be temporarily unavailable, a **transactional outbox** avoids forcing requests to depend on broker availability.

Flow:

    HTTP command
        |
        v
    Database transaction
      +-- update business state
      +-- insert outbox row
        |
        v
    Commit database
        |
        v
    API returns accepted
        |
        v
    Outbox publisher
        |
        +--> Kafka available: publish, mark sent
        |
        +--> Kafka unavailable: keep row, retry later

The outbox persists publish intent durably while Kafka is temporarily down. The publisher can retry once brokers return without restarting API pods.

Trade-offs:

- Event delivery is typically at-least-once; downstream needs idempotency by `eventId`.
- Outbox backlog grows during outages.
- Metrics are needed for oldest outbox age and pending count.
- Bounded retry/backoff and poison-event handling are required.
- Database capacity must cover expected outage durations.

An outbox is not mandatory for every producer. If the request contract demands synchronous Kafka ACKs, the API must return outcomes reflecting publishing; even then, never restart the JVM when a send future fails due to a transient broker blip.

## 29. Consumer offsets when brokers recover

During broker unavailability, consumers may fail to commit offsets. Once connectivity returns:

- Consumers can continue polling from their current position if assignments remain valid.
- If group membership changed, rebalancing determines new assignments.
- Uncommitted records may be redelivered.
- Side effects completed before the outage without committed offsets may execute again.

Example:

    Committed offset = 500
    Consumer processes records 500, 501
    Broker disconnects before offset commit
    Consumer reconnects or group rebalances
    New consumer reads from offset 500

This is why you need:

- Stable event IDs.
- Database unique constraints / inbox tables.
- Idempotent side effects.
- No offset commits before durable processing.
- Duplicate-detection monitoring after outages.

Never seek to `latest` just to skip backlog when brokers recover. Doing so turns a temporary outage into permanent data loss.

## 30. Kafka transactions during broker outages

For transactional listeners or producer-initiated Kafka transactions, broker outages can cause sends/commits to time out or abort.

Distinguish:

- Producer reconnect in progress.
- Transaction timeout.
- Transaction coordinator unavailable.
- Producer fenced.
- Commit outcome uncertain due to lost response.

An aborted transaction never exposes output to `read_committed` consumers. Input offsets inside an aborted transaction are also not committed as successful.

Never generate a new `transactional.id` on every retry to dodge timeouts. Doing so breaks producer identity and fencing semantics. On `ProducerFencedException`, investigate identity conflicts; on transient timeouts, inspect retries/transaction outcomes while keeping `eventId` stable.

If a transaction commit times out with an uncertain outcome, do not assume the transaction definitely failed to commit. Use reconciliation/idempotency instead of re-emitting commands with a new event ID.

## 31. Graceful shutdown avoids extra rebalances

During intentional deployments or scale-downs, giving listener containers time to stop cleanly lets consumers leave the group gracefully and reduces partial processing.

Key points:

- Spring context shutdown must budget enough time for listener containers.
- Kubernetes `terminationGracePeriodSeconds` must exceed expected stop duration.
- Any `preStop` hook must align with deployment lifecycle.
- Listeners must not block indefinitely on DB/API calls.
- Never commit offsets for unfinished records.
- Use idempotency because hard crashes can still happen.
- Producers/transactions must close cleanly per lifecycle.

Kubernetes example:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

60 seconds is an example. Set it according to worst-case shutdown, listener processing deadlines, transaction timeouts, and deployment needs. Graceful shutdown does not cure broker outages, yet it prevents turning outages into waves of members dropping out from repeated restarts.

## 32. What role do circuit breakers play?

Circuit breakers can help for **business dependencies** called by listeners, such as HTTP APIs or databases, when downstream repeatedly times out. They should not replace Kafka client reconnects.

Example:

    Consumer poll keeps running
          |
          v
    Listener calls Payment API
          |
          v
    Circuit breaker OPEN
          |
          +--> pause container/partition per policy
          |
          +--> or retry record with finite backoff
          |
          v
    Independent health probe checks Payment API
          |
          v
    HALF_OPEN -> CLOSED upon recovery

When brokers are unavailable, a circuit breaker around a broker health check can throttle probe attempts, but must not trigger a container restart every time the breaker opens.

Ensure recovery probes do not depend on a paused listener. When resuming, keep rate limits/backoff to avoid unleashing the backlog as one massive burst.

## 33. Do not multiply retries at every layer

A system can accidentally stack retries:

    HTTP client retries: 3x
      x service retries: 3x
      x Kafka producer retries: many times within delivery timeout
      x listener retries: 4x
      x Kubernetes restarts: unbounded

As a result, a single business action can be attempted dozens of times while layers share no deadline or idempotency key.

Define clearly:

- Which layer owns transport retries?
- Which layer owns record retries?
- Which layer restarts containers/processes?
- What is the total deadline?
- Where do backoff and jitter live?
- Which retries count as the same event/command?
- Once retries exhaust, how do recovery/DLT/outbox handle it?

Kafka clients retry transport within configured bounds. `DefaultErrorHandler` handles record failures. Kubernetes restarts processes when containers/processes fail liveness. These three responsibilities should never be collapsed into one.

## 34. Distinguishing broker outages from DNS and advertised.listeners

When logs say brokers are unreachable, the cause might not be a dead broker process.

Check:

- Does DNS resolve the hostname properly?
- Does service discovery return the right endpoints?
- Are network policies/security groups blocking ports?
- Do broker `advertised.listeners` use hostnames/IPs reachable from pods?
- Do TLS certificates include matching SANs for the hostname?
- Are SASL mechanisms/credentials accurate?
- Is the client targeting the right bootstrap cluster/environment?

A common scenario:

    Client connects to bootstrap broker successfully
          |
          v
    Receives metadata
          |
          v
    Metadata advertises broker.internal.local
          |
          v
    Pod cannot resolve that hostname
          |
          v
    Requests to leader/coordinator fail

Adding retries or restarts cannot fix wrong advertised listeners. Fix the cluster/network configuration.

## 35. Readiness while the consumer group is still rebalancing

After a broker outage or network interruption, a consumer group can take time to return to `Stable`. Meanwhile, some members may have no assignments or shifting assignments.

Readiness should not fail on the very first snapshot.

Use:

- Startup grace period.
- Minimum time the group must stay `Stable` before evaluating.
- Group-wide assignment count.
- Healthy member count.
- Lag / oldest record age.
- Time since last commit/processing progress.
- Pause state and listener lifecycle.

A pod with no partitions may be a valid standby member. If the entire group has no partitions while the topic has data and work must be processed, that is the real severe sign.

Never call `consumer.assignment()` from a health thread. Use snapshots updated on rebalance callbacks or bounded `AdminClient` monitors.

## 36. Monitoring needed during broker outages

Dashboards should combine four layers.

**Broker and network**

- Broker availability/health.
- Client connection/disconnect counts.
- Request latency/error rates.
- Metadata refresh errors.
- Authentication/authorization errors.
- DNS/network/TLS failures.

**Consumer group**

- Group member count.
- Assigned partitions.
- Rebalance count/duration.
- Heartbeat failures.
- Consumer lag and oldest record age.
- Commit rate, latency, and failures.

**Producer**

- Send rate/error rate.
- Record retry rate.
- Delivery timeout count.
- Buffer availability/wait time.
- Transaction commits/aborts/fencing.
- Outbox pending count/oldest age if applicable.

**Application and Kubernetes**

- Container running/stopped events.
- `ConsumerStarted`/`Stopped` events.
- Pod restart count.
- Liveness/readiness states.
- JVM GC pauses, CPU throttling, memory.
- Restart supervisor attempts/backoff state.

Do not monitor log error counts alone. During an outage, log volume can explode; metrics show trends and blast radius much more clearly.

## 37. Alerting without triggering another restart storm

Alerts should separate brief blips from prolonged outages:

| Condition | Action |
|---|---|
| Brief single broker disconnect | Log/metric, no paging |
| Multiple reconnects while consumer still recovers | Warning if prolonged |
| Group lag continuously growing past SLO | Alert on freshness/lag |
| Entire group has no assignments | Critical if topic/workload must operate |
| Container stops abnormally without auto-starting | Lifecycle alert |
| Repeated `AUTH`/`FENCED`/`NO_OFFSET` | Alert on specific root cause |
| Rising pod restart count | Restart-loop alert |
| Broker recovers yet reconnect rate spikes | Thundering-herd warning |

Use duration, rate, and multiple signals to set severity. Never page every time a Kafka client attempts a reconnect.

Alerts should not auto-trigger restarts for every disconnect. If auto-remediation exists, cap attempts and enforce a circuit breaker.

## 38. A non-blocking health snapshot

A custom monitor can update the latest connectivity status in the background while the health endpoint simply reads the snapshot.

Simple model example:

~~~java
public record BrokerStatus(
        boolean reachable,
        Instant checkedAt,
        String lastError) {
}

@Component
public class BrokerStatusSnapshot {

    private final AtomicReference<BrokerStatus> current =
            new AtomicReference<>(
                new BrokerStatus(false, Instant.EPOCH, "Not checked")
            );

    public void update(BrokerStatus status) {
        current.set(status);
    }

    public BrokerStatus current() {
        return current.get();
    }
}
~~~

A separate monitor executes probes with timeouts and rate caps to update the snapshot. `HealthIndicator` never calls brokers directly:

~~~java
@Component
public class KafkaReadinessIndicator implements HealthIndicator {

    private final BrokerStatusSnapshot snapshot;

    public KafkaReadinessIndicator(BrokerStatusSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @Override
    public Health health() {
        BrokerStatus status = snapshot.current();

        if (!status.reachable()) {
            return Health.outOfService()
                    .withDetail("brokerReachable", false)
                    .withDetail("checkedAt", status.checkedAt())
                    .build();
        }

        return Health.up()
                .withDetail("brokerReachable", true)
                .withDetail("checkedAt", status.checkedAt())
                .build();
    }
}
~~~

This is a structural example lacking grace period/hysteresis and group-level readiness distinction. `reachable` must be updated by a monitor with explicit deadlines; never create a new `KafkaAdminClient` inside `health()`.

In production, overly old states must be handled explicitly. A snapshot claiming reachable from 10 minutes ago does not prove the broker is healthy now.

## 39. Why health probes should not call KafkaTemplate.send

One way people test brokers is sending a test record on every readiness request. This causes side effects and extra traffic.

Risks:

- Probes can publish test records into real topics.
- Business consumers might process test records.
- Transactional producers create unnecessary transactions.
- Every pod and probe interval generates new requests.
- Probe failures get confused with business send failures.
- Topics/ACLs may differ from actual consumer permissions.

If you need to test the producer path, use a dedicated low-frequency synthetic canary with its own key/topic/consumer and retention. Never emit test records on every Kubernetes probe.

Readiness should read measured health snapshots or dependency states rather than executing new business publishes.

## 40. Broker recovery: avoiding bursts when consumers resume

Once brokers return, consumers may face a large backlog. If every consumer resumes and processes at full throttle immediately, downstream databases/APIs can overload.

Consider:

- Keeping rate limiters/concurrency limits active.
- Scaling consumers according to partition counts and dependency capacity.
- Resuming in groups or staggered with jitter if the application paused intentionally.
- Monitoring oldest record age and drain rate.
- Never raising concurrency beyond partition count.
- Never setting infinite producer retries.
- Controlling retry-topic/DLT re-drives.
- Ensuring database connection pools and HTTP quotas have capacity.

Approximate backlog drain time:

    DrainRate = ConsumerCapacity - IncomingRate

    DrainTime = CurrentLag / DrainRate

Example:

    Lag = 360,000 records
    Capacity = 800 records/s
    Incoming = 500 records/s
    DrainRate = 300 records/s

    DrainTime ~= 1,200 seconds = 20 minutes

If capacity is below incoming rate, backlog cannot shrink. In that case, throttle input or increase dependency/consumer capacity appropriately.

## 41. Do not autoscale on lag while ignoring dependencies

Autoscaling on consumer lag helps, yet right after brokers recover or while downstream is slow, adding pods immediately increases connections, consumer group churn, and downstream load.

Before scaling, check:

- Partition count and maximum parallelism.
- Consumer CPU/memory.
- Listener processing duration.
- Database/API capacity.
- Rate limiter state.
- Rebalance overhead.
- Lag trend and input rate.
- Existing consumer member count.

If the bottleneck is a database connection pool, adding consumer pods overloads the database further. If the bottleneck is partition count, scaling pods past partition count adds zero throughput.

## 42. Handling credential rotation when brokers temporarily reject

A secret rotation can leave old consumers holding expired credentials before new secrets are mounted or refreshed properly.

Procedure:

1. Distinguish `AUTH` errors from network disconnects.
2. Check secret rotation timing and credential version.
3. Confirm pods are running with the new secret.
4. Check ACLs for the new principal.
5. If a container stopped on an authentication exception, use an appropriate auth retry interval or a controlled restart after credentials update.
6. Avoid restarting all pods repeatedly while the secret is still wrong.
7. Verify group join, assignment, and offset progress after recovery.

A retry interval will not fix wrong ACLs. An unbounded retry loop only floods logs and auth load without fixing configuration.

## 43. Transaction fencing is not a normal reconnect error

If logs show `ProducerFencedException`, `InvalidProducerEpochException`, or transactional identity errors, do not treat them as simple broker disconnects.

Check:

- Are two producers using the exact same `transactional.id`?
- Is the transaction ID prefix unique per instance?
- Is an old zombie pod/process still running without shutting down?
- Does the producer factory cache/suffix lifecycle work properly?
- Did a rolling deployment cause an identity conflict?

The Kafka client can reconnect successfully yet the old producer stays fenced because its identity was superseded. A restart loop with the same `transactional.id` conflict will keep repeating the error.

Fix the identity/lifecycle and ensure transaction outcomes. Never swap transactional IDs arbitrarily on every error, as that breaks transaction recovery and producer identity semantics.

## 44. Testing broker outages and recovery

A meaningful integration test should simulate unreachable brokers followed by recovery.

You can use Testcontainers with a network proxy capable of dropping/restoring traffic, or a test environment that stops/restarts brokers. Scenario:

1. Start broker, topic, and consumer group.
2. Send a few records and confirm the listener processes them.
3. Cut connectivity between application and broker for a bounded period.
4. Verify the container/process does not restart repeatedly on disconnect alone.
5. Verify reconnect/request-failure metrics increase.
6. During the outage, send producer records per chosen contract and observe future/outbox behavior.
7. Restore broker connectivity.
8. Verify client reconnects and consumer group stabilizes.
9. Verify uncommitted records are safely reprocessed.
10. Verify lag decreases and producer sends resume.
11. Verify pod restart count does not rise unexpectedly.
12. Verify readiness transitions per grace period/hysteresis.

Do not hard-assert that containers always retain identical assignments during long outages; the group protocol may rebalance depending on timeouts and coordinator state. Verify final outcomes and delivery guarantees.

## 45. Testing readiness/liveness when brokers are down

Separate two goals:

**Liveness test**

1. Run the application with healthy brokers.
2. Disconnect the broker.
3. Confirm liveness remains `UP` while JVM/process is operating.
4. Confirm no restart occurs solely from a transient broker error.
5. Induce a controlled internal deadlock in a separate test.
6. Confirm liveness detects real process faults per policy.

**Readiness test**

1. Identify the service contract: outbox or synchronous Kafka requirement?
2. Disconnect the broker.
3. Confirm readiness matches the contract without oscillating per request.
4. Restore the broker.
5. Wait for enough successful probes to satisfy hysteresis.
6. Confirm readiness returns `UP`.
7. Verify readiness does not make blocking broker calls on every request.

Do not use a single combined test to prove both liveness and readiness; they serve different purposes.

## 46. Testing restart supervisors and backoff

If the application has a listener container restart mechanism:

1. Trigger an error that actually stops the container under your version's contract.
2. Verify the supervisor receives the right event/state.
3. Verify a single restart attempt is scheduled.
4. Verify backoff increases with jitter within bounds.
5. Emit multiple duplicate events; confirm no concurrent restarts spawn.
6. Let the broker recover; confirm the container starts and group assignment stabilizes.
7. Repeat errors past the threshold; verify circuit opens/alerts instead of infinite restarts.
8. Trigger application shutdown; confirm the supervisor schedules no new starts.
9. Confirm sustained success resets failure counters per policy.

Never test restart loops by endlessly restarting processes in CI. Use a fake clock/scheduler or cap attempts so test suites finish deterministically.

## 47. Runbook during transient broker failures

When seeing widespread Kafka disconnects/request timeouts:

1. **Identify scope:** single broker, single client, single pod, or whole cluster?
2. **Check broker health:** node restarts, controller/leader elections, coordinators.
3. **Check network:** DNS, routing, firewalls, network policies, TLS, and `advertised.listeners`.
4. **Check Kafka clients:** reconnect attempts, request latency, retries, and timeouts.
5. **Check lifecycle:** are listener containers still running or stopped?
6. **Check groups:** member count, assignments, rebalances, and heartbeats.
7. **Check producers:** future failures, delivery timeouts, buffer pressure.
8. **Check transactions:** commits/aborts, fencing, and unknown outcomes.
9. **Check Kubernetes:** liveness/readiness transitions, restart counts, and termination events.
10. **Check retry layers:** client retries, record retries, supervisor restarts, and orchestrator.
11. **Protect offsets:** never reset/seek to skip backlog.
12. **Keep side effects idempotent:** expect redelivery after outages.
13. **Restore broker/network/config:** fix root cause before forcing restarts.
14. **Monitor reconnects:** avoid thundering herds and broker overload.
15. **Monitor drain:** lag, oldest record age, producer/consumer rates.
16. **Record postmortem:** outage duration, restart counts, duplicates, and SLO impact.

Never reset consumer groups or delete topics to handle transient connectivity errors. Those actions do not restore networking and can lose data progress.

## 48. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Liveness calls broker directly | Broker outage restarts every pod | Tie liveness to process health |
| Restarting pod on every disconnect | Restart loops and rebalance storms | Let Kafka clients reconnect |
| Restarting containers already reconnecting | Disrupts ongoing recovery | Check lifecycle/terminal errors |
| Retrying without backoff | Thundering herd | Exponential backoff and jitter |
| Each layer retries independently with no deadline | Retry multiplication | Clarify roles and deadlines |
| Readiness calls blocking `AdminClient` per probe | Health endpoint hangs when broker is down | Background snapshots with timeouts |
| Treating container running as broker healthy | Misses request failures | Combine client metrics/progress |
| Treating broker disconnects as listener exceptions | Misusing `DefaultErrorHandler` | Separate transport and record errors |
| Using auth retry for wrong ACLs | Retries forever without recovery | Fix credentials/permissions |
| Changing `transactional.id` after every timeout | Breaks identity/recovery semantics | Distinguish timeouts from fencing |
| Committing offsets or seeking to skip backlog | Data loss | Preserve committed progress |
| Restarting all pods at once | Connection storm | Stagger, jitter, controlled rollouts |
| Scaling consumers on lag while ignoring DB | Overloads downstream further | Scale by bottleneck and partitions |
| Resuming full backlog unboundedly | Burst hits dependencies | Rate limiting/concurrency control |
| Monitoring only error logs | Misses progress/SLOs | Group, lag, restart, and health metrics |

## 49. Production deployment checklist

- Do `bootstrap.servers` list multiple valid endpoints?
- Are `advertised.listeners`, DNS, network, and TLS right for where consumers run?
- Are Kafka client reconnect/retry backoffs tuned sensibly?
- Do producer delivery and request timeouts align with SLAs?
- Are consumer session timeout, heartbeat, and `max.poll.interval.ms` properly understood?
- Can listener containers self-reconnect during transient outages?
- Are retryable request errors distinguished from terminal container-stopping errors?
- Is `authExceptionRetryInterval` configured where appropriate?
- Does `DefaultErrorHandler` handle only record failures rather than acting as a broker reconnect policy?
- Is liveness independent of transient broker outages?
- Does readiness reflect the service contract with grace/hysteresis?
- Do health endpoints avoid blocking network calls on every probe?
- Do restart supervisors have backoff, jitter, cooldowns, and attempt limits?
- Are restarts suppressed while the application is shutting down?
- Are retries prevented from multiplying across layers?
- Do event IDs/idempotency protect against redelivery?
- Are transactional IDs kept stable and unique across instances?
- Is an outbox considered if APIs must accept commands while Kafka is down?
- Do metrics cover reconnects, request failures, group assignments, lag, delivery timeouts, and pod restarts?
- Do tests cover broker outages/recovery, readiness/liveness, and restart supervisors?
- Do runbooks forbid resetting offsets to fix connectivity errors?

## 50. Conclusion

**Avoiding restart loops on transient broker failures** starts with recognizing that Kafka clients can reconnect and retry many transport errors without restarting the JVM. Spring Kafka listener containers can stay running while brokers are unavailable, and repeated restarts trigger group rebalances, add broker load, and prolong outages.

Let Kafka clients handle reconnects with their backoff; use error handlers for record failures; use auth retries or recovery policies for retryable lifecycle faults; and restart containers/processes only when there is proof they stopped or cannot self-recover. Liveness should protect the process, readiness should reflect the serving contract, and supervisors must enforce backoff, jitter, and attempt caps.

When brokers return, offsets and side effects must handle redelivery safely, backlogs must drain within downstream capacity, and monitoring must show both connectivity and progress. **A client that preserves self-recovery during brief outages is far more stable than a system that restarts on every network error.**
