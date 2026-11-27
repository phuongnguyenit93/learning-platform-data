# Assigning Retry Responsibilities Across SDK, Spring Libraries, and Business Code

When Spring Boot calls Azure Blob Storage, Service Bus, or a database, a transient network error can cause a request to fail even though the operation would likely succeed if retried. Retries improve resilience, but if the **Azure SDK**, the **Spring resilience library**, and **business code** all retry independently, the number of calls can multiply, increasing load, extending latency, and creating duplicate side effects.

A reliable design must clearly assign **which layer is responsible for retrying which category of error**. The SDK understands protocol and transport errors; the application's resilience layer manages dependency-level behavior; business code decides whether to retry a business step or transition to another path. Not every error should be retried, and not every retry belongs in the same layer.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish retries in the **SDK**, **Spring/resilience library**, and **business code**.
2. Recognize automatic retries in HTTP transports, Azure SDKs, JDBC drivers, messaging clients, and brokers.
3. Classify retryable errors, configuration/permission errors, and business errors that should not be retried.
4. Avoid multiplying call counts when multiple retry layers are nested.
5. Combine retries with deadlines, backoff, jitter, circuit breakers, bulkheads, and rate limits.
6. Design idempotent operations, deduplication, outbox/inbox, and handling of unknown outcomes after timeouts.
7. Test retries by counting requests, simulating errors, verifying side effects, and observing the retry budget.
8. Choose the right place for retries across Blob Storage, Service Bus, databases, and multi-cloud services.

## 2. Three Retry Layers Have Different Responsibilities

| Layer | Primary Knowledge | Appropriate Scope | Examples |
| --- | --- | --- | --- |
| **Service SDK/client** | Protocol, error codes, retry headers, connection resets, throttling, and API semantics | Transient technical failures of a single request/protocol exchange | Azure Storage SDK retries HTTP 429/503 per policy; Service Bus SDK retries AMQP connection errors |
| **Spring/application resilience library** | Dependency context, SLOs, circuit breaker, bulkhead, concurrency, and timeouts | Protecting a dependency call or an integration boundary | Resilience4j Retry/CircuitBreaker around BlobGateway |
| **Business code** | Business state, idempotency, workflow, compensation, and retry conditions | Deciding whether to retry a business step or continue a workflow | Retrying order processing after checking state; handling redelivered messages |

**SDK retry** typically handles errors that the client can evaluate based on protocol or service rules. **Spring resilience** manages how the application interacts with the dependency as a whole. **Business retry** decides whether a business action is still valid and safe to execute again.

All three layers can coexist, but you must avoid retrying the exact same error across layers without a shared budget.

### Responsibility Diagram

~~~mermaid
flowchart TD
    A[Business workflow] --> B{Business error or dependency error?}
    B -->|Recoverable business condition| C[Business policy / workflow retry]
    B -->|Dependency call error| D[Spring resilience boundary]
    D --> E{Can SDK handle protocol error itself?}
    E -->|Yes| F[SDK retry within one application attempt]
    E -->|No| G[Classify error / circuit breaker / return error]
    F --> H[Azure / AWS / Google managed service]
    G --> I[Fallback or controlled error response]
    C --> J[Check state and idempotency]
    J --> A
~~~

The diagram illustrates responsibility boundaries, not a mandatory order for every library. In practice, Spring Retry may wrap an SDK client that already has retries enabled; you must account for the total attempts across both layers.

## 3. What Is Retry and When Is It Helpful?

Retrying means re-executing an operation after a prior attempt failed or produced an unknown result. Retries are appropriate when the error is likely transient and a repeat attempt has a reasonable chance of succeeding without causing wrong side effects.

Situations where retry may be considered:

- Connection resets or transient network errors.
- Timeouts when it is unclear whether the service processed the request, provided the operation is idempotent or state can be verified.
- HTTP 408, 429, or certain 5xx errors per service semantics.
- Throttling accompanied by a wait hint such as **Retry-After**.
- Broker/service temporarily unavailable or transient transport errors.
- Database deadlock/serialization conflicts if the transaction can be safely re-run.

Situations that generally **should not be blindly retried**:

- Invalid input data, validation failures.
- 401/403 due to invalid credentials, missing roles, or insufficient permissions.
- Wrong endpoint, tenant, resource name, or configuration.
- 404 when the resource does not exist and the business logic has no specific eventual consistency rule.
- Business conflicts such as an already-canceled order or a state that forbids transition.
- Deterministic schema/code errors, mapping errors, or serialization failures that cannot self-heal.
- Requests that are too large or exceed fixed service limits.

An HTTP status code is only one signal. For example, **404** can sometimes be temporary in a workflow that just provisioned a resource, whereas when reading a Blob with a misspelled name, retrying will not help. **409** may be a business conflict, a lease conflict, or a service state that requires dedicated handling. Always inspect the error code and operation semantics.

## 4. Assigning Retries by Layer

### 4.1. Let the SDK Handle Protocol and Transient Service Errors

The SDK usually knows:

- Whether a request is retryable under the protocol/service contract.
- Whether the service returned Retry-After or backoff guidance.
- Which transport errors are recoverable.
- Which endpoint the request targeted and how to re-send it.
- Whether a specific API has special retry conditions.

Examples:

| SDK/Client | Appropriate Retry at the SDK Layer |
| --- | --- |
| Azure Blob Storage SDK | Transient HTTP/transport errors per Storage retry policy, throttling, and SDK-recognized service errors |
| Azure Service Bus SDK | Connection errors, transient AMQP errors, operation retries per messaging client policy |
| Azure Cosmos DB SDK | 429 throttling, retries per service response and request semantics |
| AWS SDK for Java v2 | Transient/throttling errors per the AWS client's retry strategy |
| Google Cloud Java client | Retries per RPC/API retry settings and library-defined error codes |
| JDBC driver | Certain connection or protocol errors, driver-dependent; does not retry whole business transactions by default |

Do not write an extra Spring loop merely to retry individual network errors that the SDK already handles well. If the SDK already retries within a single API call, treat that entire sequence as **one attempt at the application boundary**.

### 4.2. Let Spring Resilience Protect the Dependency Boundary

The Spring/resilience layer is suited for:

- Placing a **circuit breaker** when a dependency experiences prolonged failures.
- Limiting concurrency with a **bulkhead**.
- Rate limiting or capping request rates per client.
- Retrying certain transient failures after the SDK finishes its call and returns an error.
- Recording consistent metrics/traces per dependency.
- Choosing a meaningful application-level fallback, such as returning cached data or failing fast.

Retries at this layer should be used when there is a **clear reason beyond transport retries**. If the SDK already performs multiple internal retries, adding more attempts in Spring Retry can multiply request counts and breach the deadline.

### 4.3. Let Business Code Decide Workflow Retries

Business code needs to retry when the decision depends on business state or multiple distributed steps, for example:

- A workflow waiting for a newly provisioned resource that must poll status before continuing.
- A consumer receiving a message while a business service is temporarily unready.
- A step that needs re-execution after verifying the previous operation did not finish.
- A saga that must retry a command or run compensation based on persisted state.

A business retry must not be a loop repeating the same HTTP request without knowing what happened. It must inspect **state**, **idempotency key**, **attempt count**, **next retry time**, **deadline**, and stop conditions.

## 5. Nested Retries Can Multiply Call Counts

Suppose:

- The SDK makes up to 4 attempts per client call.
- Spring Retry calls the method up to 3 times.
- The business workflow reruns the entire step up to 2 times.

The number of requests reaching the service can reach:

~~~text
4 × 3 × 2 = 24 attempts at the SDK/transport layer
~~~

The exact figure depends on how each library defines **max attempts/max retries** and at which stage failures happen. Some configurations include the initial attempt; some APIs specify only the number of retries after the initial attempt. Verify the semantics before calculating.

### Impact Table of Nested Retries

| SDK Attempts | Spring Attempts | Business Attempts | Maximum Total Requests (Multiplicative Model) |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 1 |
| 3 | 1 | 1 | 3 |
| 3 | 2 | 1 | 6 |
| 3 | 3 | 1 | 9 |
| 4 | 3 | 2 | 24 |
| 5 | 4 | 3 | 60 |

This is a conservative model to spot **retry amplification**, assuming every outer-layer call triggers the full inner-layer attempt count. Some errors may stop early or bypass parts of the transport, but you should not rely on that when designing load limits.

### Practical Rules

- Choose one primary **retry owner** for each error category.
- Keep SDK retries for transient transport/service errors that the SDK understands.
- Use Spring Retry only when retrying at the dependency boundary is needed and internal SDK attempts have been accounted for.
- Use business retries for workflows with state, retry schedules, and idempotency.
- Expose attempt counts and total duration in metrics.
- Do not let each layer set its own max attempts without an overall budget.

## 6. Classify Errors Before Retrying

An adapter should translate SDK/provider-specific errors into meaningful internal error categories, for example:

| Internal Error Category | Source Examples | Default Retry? | Handling Approach |
| --- | --- | --- | --- |
| **Transient transport** | Connection reset, temporary DNS/network failure | Possible | Let the SDK or one chosen layer retry within bounds |
| **Throttled** | HTTP 429, service throttling | Possible | Respect Retry-After/backoff, reduce concurrency |
| **Transient service** | Certain 5xx/service unavailable | Possible | Retry within budget and with idempotency |
| **Authentication** | 401, invalid/expired token depending on case | Usually not at Spring layer | Refresh credentials via SDK if supported; if still failing, fix identity |
| **Authorization** | 403, RBAC/access policy | No | Fix principal, role, scope, or network policy |
| **Not found/configuration** | 404 wrong resource, wrong endpoint | Not by default | Verify resource name, deployment order, and eventual consistency |
| **Conflict** | 409, ETag/lease/state conflict | Operation-dependent | Read error code and resolve conflict |
| **Validation/business rejection** | Invalid data, disallowed state | No | Return business error |
| **Unknown outcome** | Timeout after the request may have been processed | Only when safe | Query state or use idempotency/deduplication |

**Do not retry every RuntimeException.** An unknown exception could be a programming bug, configuration mistake, or bad data. Retrying broad exceptions masks real bugs and prolongs processing time.

### Blob Storage Classification Example

| Scenario | Classification | Action |
| --- | --- | --- |
| Temporary connection drop before sending request | Transient transport | SDK can retry |
| Blob service returns 503 | Transient service | Use bounded SDK retry policy |
| Storage throttling 429 | Throttled | Back off, respect service signals |
| Managed identity lacks write role | Authorization | Do not retry; grant proper role via IAM process |
| Wrong container name | Configuration/not found | Fix configuration or provision container |
| Blob already exists with overwrite=false | Conflict | Handle in business logic or use appropriate naming/idempotency |
| Timeout during upload commit | Unknown outcome | Check blob state before repeating if needed |

## 7. Retries in Azure SDK and Spring Cloud Azure

Spring Cloud Azure starters can auto-configure Azure SDK clients in the Spring context. The actual retry policy depends on the **service SDK**, **Azure Core**, **starter version**, and the properties supported in that version.

### 7.1. Azure SDK Understands Service-Level Retries

For example, the Blob Storage SDK has its own retry options; Service Bus has AMQP client retry options; Cosmos DB has retry behavior for throttling and requests. Do not assume a single generic Spring property controls retries for all services.

For Blob Storage, retries can be configured via the builder/service SDK when supported by the version. Check:

- Whether max retries/attempts includes the initial attempt.
- Default and maximum retry delays.
- Exponential backoff vs. fixed delay.
- Which status codes/errors trigger retries.
- Per-attempt timeout and overall operation timeout.
- Whether secondary endpoints/failover are used.
- Whether retries apply to multi-block uploads, download streams, and specific operations.

**Do not hardcode one shared set of retry values for all environments.** Dev, integration test, and production environments have different latencies, throughput, and SLOs.

### 7.2. Do Not Blindly Wrap an Entire SDK in Spring Retries

Suppose an upload method uses the Blob SDK with internal retries. If you wrap that method with Spring Retry without classifying exceptions, each time the SDK finally fails it can trigger another full round of SDK retries. This can cause a single business request to generate many more upload requests than intended.

Some upload operations can be idempotent if they use deterministic blob names and appropriate write semantics, but you should not assume every upload is idempotent by default. Consider overwrite behavior, conditional headers/ETags, block commits, and unknown outcomes after timeouts.

### 7.3. Spring Cloud Azure Is Not One Unified Retry Policy Across All Services

Starters help wire clients into Spring. Retries may still reside inside the Azure SDK service client, or be added at the application resilience layer. Before putting retry properties in application.yml, verify that the property belongs to the right starter/service and is supported by the current version.

## 8. Retries in Spring Libraries: Spring Retry and Resilience4j

There are two common options in Spring applications:

- **Spring Retry:** provides declarative/programmatic retries, typically using annotations like **@Retryable** and corresponding recovery mechanisms.
- **Resilience4j:** provides Retry, CircuitBreaker, Bulkhead, RateLimiter, and TimeLimiter; includes Spring Boot/annotation integration.

There is no need to include both libraries just because you have many dependencies. Pick one primary mechanism aligned with your architecture, Spring Boot version, and operational needs.

### 8.1. Spring Retry Example with Classified Internal Errors

An adapter can translate SDK errors into an internal **TransientDependencyException** after confirming it is a transient failure. Spring Retry catches only this exception group:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class PartnerDocumentService {

    private final DocumentGateway gateway;

    public PartnerDocumentService(DocumentGateway gateway) {
        this.gateway = gateway;
    }

    @Retryable(
        retryFor = TransientDependencyException.class,
        maxAttempts = 3,
        backoff = @Backoff(
            delay = 200,
            multiplier = 2.0,
            maxDelay = 1000
        )
    )
    public DocumentReference upload(DocumentCommand command) {
        return gateway.upload(command);
    }
}
~~~

In this example, **maxAttempts=3** includes the initial call per Spring Retry semantics. Confirm the annotation API matches the Spring Retry version managed by your project; older releases use different attribute names.

**Do not wrap every Azure SDK exception in TransientDependencyException.** The adapter should only translate genuinely retryable errors; 401/403, validation, wrong endpoints, or business conflicts must retain their own error types.

### 8.2. Spring Retry Proxy/AOP Caveat

Retry annotations usually rely on Spring AOP/proxies. If a method within the same class directly calls another method annotated with retry, the self-invocation may bypass the proxy and the annotation will not take effect as expected.

Place the retry boundary on a separate bean invoked through a Spring proxy, and test the actual execution count. Do not assume seeing an annotation in code guarantees runtime retries.

### 8.3. Resilience4j Example

Resilience4j can configure attempt counts and backoff:

~~~yaml
resilience4j:
  retry:
    instances:
      partnerRead:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        retry-exceptions:
          - com.example.TransientDependencyException
        ignore-exceptions:
          - com.example.AuthorizationFailure
          - com.example.InvalidRequest
~~~

A service can apply the annotation:

~~~java
import io.github.resilience4j.retry.annotation.Retry;
import org.springframework.stereotype.Service;

@Service
public class PartnerReadService {

    private final PartnerGateway gateway;

    public PartnerReadService(PartnerGateway gateway) {
        this.gateway = gateway;
    }

    @Retry(name = "partnerRead")
    public PartnerResult read(String id) {
        return gateway.read(id);
    }
}
~~~

To run, the project needs the Resilience4j Spring Boot integration dependency and corresponding AOP configuration. This illustrative configuration must be verified against your starter version; property names, exception predicates, and annotation integration can vary by release.

**Spring retries do not replace SDK retries.** If PartnerGateway invokes an Azure SDK client that retries internally, count total attempts and only retry classified exceptions after the SDK exhausts its handling.

## 9. Assigning Roles Across Retry, Circuit Breaker, and Bulkhead

Retry is not the only tool for dealing with failing dependencies.

| Mechanism | Purpose | When Appropriate | Does Not Solve |
| --- | --- | --- | --- |
| **Retry** | Re-attempt transient errors | Transient failures, operations safe to repeat | Configuration/permission errors, prolonged outages |
| **Circuit breaker** | Temporarily stop calling a failing dependency | High failure rates or sustained latency spikes | Does not fix the dependency or guarantee request success |
| **Bulkhead** | Limit resources/concurrency dedicated to a dependency | Prevents one dependency from exhausting all threads/connections | Does not automatically retry or recover data |
| **Rate limiter** | Limit call rate | Protects quotas/throttling | Does not make rejected requests succeed on its own |
| **Time limiter/deadline** | Bound wait duration | Protects SLOs and request budgets | Does not always cancel remote side effects |
| **Fallback** | Provide an alternative result or degrade gracefully | Cached/stale data, non-core features | Should not mask failures on mandatory data |

### Common Ordering

A common structure is:

~~~text
Business service
    → Circuit breaker / bulkhead boundary
        → Retry boundary (if chosen)
            → SDK client with bounded protocol retries
                → Managed service
~~~

The actual decorator order affects behavior:

- If **CircuitBreaker wraps Retry**, the breaker may record one final business outcome after retries finish.
- If **Retry wraps CircuitBreaker**, each attempt can be recorded separately by the breaker; the breaker may open mid-retry loop.
- If Bulkhead is outside Retry, the entire retry loop holds one slot; if inside, each attempt acquires its own slot.

There is no single best order for all cases. Choose based on how you want to measure errors, limit concurrency, and protect dependencies. Check events/metrics to verify decorator order.

## 10. Retries Must Obey Deadlines and Retry Budgets

Retries add latency. If a request has a 2.5-second deadline but the retry policy waits a total of 3 seconds, the system only prolongs futile work and may finish after the caller has given up.

A retry plan must evaluate:

- Time already consumed.
- Remaining time for the operation.
- Maximum timeout for the next attempt.
- Backoff before the attempt.
- Reserve buffer for returning a response/cleanup.
- Token acquisition and connection-pool wait times if included in the call.
- Overall retry budget of the service.

### Check Formula

~~~text
T_remaining >= T_backoff + T_next_attempt + T_cleanup_reserve
~~~

If there is not enough budget, do not start a new attempt. Stop retrying and return an error or offload work to a queue as designed.

### Example

700 ms remain on the deadline. The SDK consumed 500 ms and returned 503. Spring Retry intends to wait 400 ms before the next attempt. Once you add the attempt timeout and response time, it will clearly exceed the deadline; do not retry.

A **retry budget** can be bounded by attempt count, time, or ratio of retries to total requests. In multi-replica systems, per-instance budgets must be evaluated because fleet-wide retries can be much higher.

## 11. Backoff, Jitter, and Retry-After

Immediate retries can cause many clients to slam a recovering service simultaneously. **Exponential backoff** progressively increases the wait between attempts; **jitter** adds randomness to break synchronization.

A reference formula:

~~~text
delay(k) = min(maxDelay, initialDelay × multiplier^(k - 1))
actualDelay = delay(k) + randomJitter
~~~

For example, initial delay 100 ms, multiplier 2, max delay 1,000 ms:

| Wait | Base Backoff |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 onward | Up to 1,000 ms |

Values are illustrative only. Do not add jitter beyond deadline bounds or service policies.

### Retry-After

Some services return **Retry-After** or equivalent information to suggest a wait duration. When the SDK already honors that header, do not add a Spring Retry layer with a shorter backoff that causes the application to call earlier than the service instructed.

If the application layer owns retries, read and honor the service signal via the actual API/exception. If the wait value exceeds the deadline, return an error or schedule later processing; do not force an immediate retry.

## 12. Idempotency Determines Whether Retries Are Safe

An **idempotent** operation produces the same observable result when executed multiple times with the same input/identifier under the business contract. Retries are only safe when side effects are controlled.

| Operation | Risk on Retry | Risk Mitigation |
| --- | --- | --- |
| Read Blob | Usually no data side effects, but can incur cost | Bounded retries within deadline |
| Upload Blob with a random name each time | Can create multiple objects | Use deterministic names/idempotency keys and cleanup |
| Upload same Blob name with overwrite=true | Can overwrite newer content | ETag/conditional write, versioning, or state check |
| Send Service Bus message | Broker may have received the message while ACK was lost | Stable message ID, duplicate detection where appropriate, consumer idempotency |
| Create order in database | Can create two orders | Unique business key/idempotency record |
| Charge money or call payment provider | Can double-charge | Provider-contract idempotency key and state reconciliation |
| Send email/notification | Can send duplicates | Outbox, deduplication, or business tolerance for duplicates |

### Timeouts Create Unknown Outcomes

When a client receives a timeout, it cannot always tell whether the server never processed the request or processed it and lost the response. For write operations:

1. Query state by resource ID or idempotency key if available.
2. If the operation already completed, return the prior result.
3. If it did not occur and can be retried, re-run with the same key.
4. If state is unknown, route to a reconciliation workflow instead of blindly retrying.

## 13. Business Retries: Stateful Workflows and Retry Schedules

Some situations cannot be solved by immediate SDK retries. For instance, an order must wait for a downstream resource to be provisioned, or a partner system only permits retrying after several minutes.

Business retries should persist:

- **Operation ID / idempotency key**.
- Current workflow state.
- Attempt count and latest error.
- **Next retry time**.
- Deadline or business expiration timestamp.
- Stop policy, DLQ routing, or manual intervention requirement.
- Outputs of completed steps so they are not wrongly re-executed.

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Running: start processing
    Running --> Succeeded: step completed
    Running --> RetryScheduled: transient error
    RetryScheduled --> Running: next retry time reached
    Running --> Failed: non-retryable error
    RetryScheduled --> Expired: deadline / retry budget exhausted
    Failed --> [*]
    Succeeded --> [*]
    Expired --> [*]
~~~

Do not use a while/sleep loop inside an HTTP request to wait for minutes. Persist state and hand the work off to a scheduler/queue for asynchronous processing. Return **202 Accepted** or an operation reference to the client if appropriate for the business flow.

### When Should a Retry Become Compensation?

If a workflow has completed several steps and a later step fails permanently, **compensation** may be required instead of retrying everything:

- Blob uploaded but business record creation failed: delete the object or mark it orphaned per policy.
- Database write succeeded but message publish failed: outbox worker continues publishing.
- Inventory reserved but payment declined: release the reservation.

Business retries must understand state and step ordering; the SDK lacks sufficient context to decide compensation.

## 14. Transactional Outbox and Retries in Messaging

A common failure mode:

~~~text
1. Commit order to database
2. Send OrderCreated to Service Bus
3. Service Bus temporarily fails
4. API retries sending the message or returns an error
~~~

If the database committed but the message was not sent, system state can become inconsistent. If the message was sent but the response was lost, retrying can produce duplicate messages.

The **transactional outbox** solves data persistence and event creation in one database transaction:

~~~mermaid
flowchart TD
    A[Order API] --> B[Database transaction]
    B --> C[Orders table]
    B --> D[Outbox table]
    D --> E[Outbox publisher]
    E --> F[Service Bus / SQS / Pub/Sub]
    F --> G[Consumer]
    G --> H[Idempotent business handler]
~~~

1. Within a single transaction, write the order and an outbox record.
2. The publisher reads unsent outbox records.
3. The publisher sends the message using a **stable message ID**.
4. Upon receiving an appropriate acknowledgment, mark the outbox record as sent.
5. If the publisher times out/gets an unknown outcome, it can re-send; the consumer must be idempotent or the broker configured for deduplication.
6. The consumer stores an inbox/processed message ID alongside the business change to prevent duplicate processing.

Outbox alone does not guarantee end-to-end exactly-once processing. It ensures events are not lost between the database transaction and the publish step; duplicates can still happen and must be handled.

## 15. Broker Redelivery Differs from SDK and Spring Retries

For messaging, at least three mechanisms may operate concurrently:

| Mechanism | Timing | Responsibility |
| --- | --- | --- |
| **SDK retry** | During send/receive/settlement | Recovers transient transport or service errors per client policy |
| **Application retry** | When the message handler fails | Decides whether to reprocess, abandon/nack, or persist retry state |
| **Broker redelivery** | Message not completed/acked or lock/visibility expired | Redelivers message per delivery semantics |

Do not simultaneously retry inside the handler, immediately abandon the message, and send a copy to a retry queue without clear rules. That can result in multiple copies of the message being processed concurrently.

### Azure Service Bus

- The SDK can retry certain communication errors with the namespace.
- When a handler receives a message and fails, the application can **abandon**, dead-letter, or settle according to its settlement mode.
- If the lock expires, the broker can redeliver the message.
- Control **MaxDeliveryCount**, dead-letter queues, lock renewal, and consumer idempotency.
- Do not confuse SDK connection retries with broker redelivery.

### AWS SQS

- The SDK retries SQS requests per its retry strategy.
- Visibility timeout determines how long a message remains hidden after being received.
- If not deleted before visibility expires, the message can be redelivered.
- DLQ/redrive policies handle messages exceeding the configured receive count.
- Consumers should be idempotent because duplicate delivery can occur.

### Google Cloud Pub/Sub

- The client retries RPCs.
- Subscription ack deadline and lease extension govern how long a message is held by a subscriber.
- Nacking or failing to ack can lead to redelivery per subscription configuration.
- Dead-letter topics and delivery attempts must be considered alongside the application handler.
- Do not equate ack deadline with the timeout of a publish/subscribe RPC.

## 16. End-to-End Example: Blob Upload and Service Bus Publish

**Context:** The Documents API receives a file, uploads a Blob, and publishes a DocumentUploaded event.

An uncontrolled design:

~~~text
Controller
  → @Retryable uploadAndPublish()
      → Blob SDK retries internally
      → Service Bus SDK retries internally
      → if any step fails, re-run the entire method
~~~

If the Blob upload succeeds but the Service Bus publish fails, Spring Retry re-invokes the entire method and uploads the Blob again. If Blob names are random, duplicate objects may be created; if overwriting, data may be overwritten.

### A Better Assignment of Responsibilities

1. **Blob SDK:** handles transport/throttling retries per upload request according to the verified policy.
2. **Blob adapter:** maps errors to transient/permanent/unknown outcome; uses deterministic blob names and appropriate write conditions.
3. **Application service:** does not automatically retry the whole workflow if the Blob step already succeeded; persists state/outbox or verifies results.
4. **Service Bus SDK:** handles transport retries when publishing per the client policy.
5. **Outbox publisher:** manages business-level retry scheduling for unpublished messages using a stable message ID.
6. **Consumer:** idempotent on message ID and business state.

~~~mermaid
sequenceDiagram
    participant A as Documents API
    participant B as Blob SDK
    participant DB as Database / Outbox
    participant P as Outbox publisher
    participant S as Service Bus
    A->>B: Upload blob with stable key
    B-->>A: Blob reference
    A->>DB: Commit document + outbox event
    DB-->>A: Commit succeeded
    A-->>A: Return business result
    P->>DB: Read pending outbox
    P->>S: Publish event, stable message ID
    S-->>P: ACK or unknown outcome
    P->>DB: Mark sent upon appropriate confirmation
~~~

If the outbox publisher loses the ACK, it can republish; the consumer must prevent duplicate processing. This decouples publish retries from the user's upload request and avoids re-running the entire workflow.

## 17. Observing Retries and Detecting Retry Amplification

Measure retries at each layer rather than only counting overall succeeded/failed requests.

| Metric | What to Know |
| --- | --- |
| **sdk_attempts_total** | Attempts at the SDK/transport layer per service |
| **application_retry_attempts_total** | Times Spring resilience re-invoked the adapter |
| **business_retry_scheduled_total** | Workflows scheduled for retry |
| **broker_delivery_attempt** | Broker message delivery count, if provided by the service |
| **retry_delay_seconds** | Actual backoff durations |
| **retry_exhausted_total** | Operations that exhausted their retry budget |
| **deadline_exceeded_total** | Operations lacking enough remaining time to retry |
| **circuit_breaker_state** | Closed/open/half-open state |
| **duplicate_detected_total** | Duplicate messages/resources detected |
| **operation_duration** | Total duration including retries |

Tag metrics by dependency, operation, and error category. Do not use user ID, blob name, or request ID as high-cardinality labels. Request/correlation IDs can be recorded in traces/logs per policy.

### Signs of a Retry Storm

- Request throughput rises while success rate does not.
- p95/p99 latency spikes rapidly after each wave of errors.
- Average attempts per request climb.
- Dependencies throttle more heavily after clients retry.
- Thread pools/connection pools are held longer during backoffs.
- Broker delivery counts and DLQ volume increase.
- Multiple instances retry in lockstep on the same schedule.

When these signs appear, consider reducing retries, adding jitter, opening the circuit breaker, lowering concurrency, applying rate limits, or shifting work to a queue instead of continuing synchronous retries.

## 18. Purposeful Testing of Retries

### 18.1. Unit Tests for the Classifier

Write tests for the adapter/error classifier:

- 429/503 per service policy are marked transient.
- 401/403 are marked permanent authorization/configuration.
- 404 and 409 are classified per operation/error code.
- Unknown exceptions do not automatically become retryable.
- Retry-After is translated into an appropriate delay when the application layer owns retries.

### 18.2. Verifying Actual Call Counts

Use a mock/fake gateway or HTTP test server to verify:

| Scenario | Expected Verification |
| --- | --- |
| First call 503, next succeeds | Attempt count matches policy |
| 403 on first call | No futile retries |
| 429 with Retry-After | Delay follows chosen policy |
| SDK exhausts retries then Spring retries | Total outbound requests stay within expected cap |
| Deadline expires before next attempt | No new request sent |
| Timeout after side effect | State is checked or idempotency prevents duplication |
| Circuit breaker open | Request rejected early without calling dependency |
| Message redelivery | Consumer creates no duplicate business side effects |

### 18.3. Integration Tests with Azure Dev/Test

- Use dedicated test Blob Storage/Service Bus resources and identities.
- Inject controlled errors using a test proxy, test configuration, or supported service fault injection.
- Read SDK diagnostics and application metrics to count attempts.
- Verify RBAC permissions separately; 403 must not be retried as transient.
- Inspect uploads and published messages after timeouts to determine actual state.
- Clean up test resources and data.

Azurite can help test parts of the Storage API, but it does not fully simulate Azure throttling, Entra, RBAC, or Service Bus. For messaging, test against a real broker or supported equivalent environment.

### 18.4. Testing Annotations/Proxies

With Spring Retry/Resilience4j:

- Invoke the bean through a Spring proxy.
- Do not test only internal methods within the same class.
- Verify attempt counts and backoff.
- Test exception predicates/ignore lists.
- Check the decorator order of Retry, CircuitBreaker, and Bulkhead.
- Confirm validation, authentication, and authorization errors are not retried.

## 19. Comparing Retries Across AWS, Azure, and Google Cloud

| Layer | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| SDK/client | Retry options per Storage, Service Bus, Cosmos, and each SDK | AWS SDK client/service retry strategy | Client/RPC/API retry settings |
| Spring resilience | Spring Retry, Resilience4j, Spring Cloud CircuitBreaker | Similar | Similar |
| Business workflow | State machine, scheduler, outbox, message retry | State machine, EventBridge/SQS workflow, outbox | Workflow/task queue, Pub/Sub retry, outbox |
| Messaging redelivery | Service Bus lock/abandon/DLQ, Event Hubs checkpoint | SQS visibility/DLQ, Kinesis checkpoint | Pub/Sub ack deadline/dead-letter, subscriber retry |
| Retry signal | HTTP Retry-After and service-specific behavior | Service response/retry headers and SDK behavior | RPC status, retry policy, and service guidance |

Provider SDKs differ in attempt counts, error classification, default backoff, and semantics. When switching providers, do not copy retry numbers verbatim from Azure to AWS/GCP. Re-evaluate:

- Request idempotency and duplicate behavior.
- Throttling/quotas and Retry-After or RPC retry signals.
- Broker delivery/ack/visibility/lock semantics.
- Deadlines and total retry budgets.
- Observability and how attempt counts are verified.

## 20. Lab Exercise: Assigning Retries for the Documents API

**Context:** The Spring Boot Documents API uploads files to Blob Storage, saves metadata to a database, and publishes a DocumentUploaded event to Service Bus.

### Part A — Classify Errors

Create an error table for each dependency:

1. Blob: 429, 503, 403, 404, timeout during upload commit.
2. Database: deadlock, connection reset, constraint violation, query timeout.
3. Service Bus: network failure, throttling, 401/403, timeout after publish.
4. Outbox publisher: lost ACK, worker restart, retry budget exhausted.

For each error, classify it as **retryable**, **permanent**, **unknown outcome**, or **business conflict**.

### Part B — Choose Retry Owners

- Let the SDK handle transient protocol/service errors within configured limits.
- Use Resilience4j/Spring Retry on the gateway only if dependency protection is needed and internal attempt counts are accounted for.
- Use the outbox publisher for message publish retries after database commit.
- Have the consumer use idempotency keys/message IDs to prevent duplicate processing.
- Do not retry 401/403 or validation errors.

### Part C — Compute Total Attempts and Deadline

1. Document the SDK max retries/attempts for your actual version.
2. Document Spring maxAttempts and note whether it includes the initial attempt.
3. Calculate the upper bound of requests when layers are nested.
4. Set a 2.5-second deadline for the synchronous API; do not start new attempts if budget is exhausted.
5. Offload unfinished publishes to the outbox worker instead of holding the HTTP request open too long.

### Part D — Testing

1. Make Blob return 503 once then succeed; verify SDK retries and request count.
2. Make Blob return 403; verify no retry occurs.
3. Force a Service Bus publish timeout after the broker may have received the message; verify duplicate behavior.
4. Restart the outbox worker between sends; verify stable message IDs.
5. Re-send the same event to the consumer; verify business state is updated only once.
6. Trip the circuit breaker open; verify the application fails fast.
7. Measure total latency, attempt counts, retry delays, and deadline exhaustion.

**Deliverables:** retry ownership diagram, error classifier table, SDK/Spring configuration, upper-bound attempt calculation, idempotency test results, and metrics dashboard.

### Self-Check Questions

1. Why can enabling both SDK retries and Spring Retry multiply request counts?
2. When should you let the Azure SDK retry on its own instead of adding @Retryable?
3. Why should a 403 caused by missing RBAC not be retried?
4. How do Spring Retry and Resilience4j Retry differ in role from a circuit breaker?
5. If Retry wraps a CircuitBreaker, how is each attempt counted toward the breaker?
6. Why must business retries persist state and next retry time?
7. When the Service Bus broker received a message but the client lost the ACK, what can a retry cause?
8. What gap between a database commit and message publishing does the outbox solve?
9. Why is message redelivery not the same mechanism as an SDK retry?
10. How do you verify the upper bound of attempts in an integration test?

## 21. Takeaways

- The **SDK** should handle transient transport/protocol/service errors it understands; **Spring resilience** protects dependency boundaries and SLOs; **business code** decides workflow retries based on state and business rules.
- Pick one primary retry owner per error category. If multiple layers retry, compute the nested upper bound of attempts and check max attempts/max retries semantics.
- Never blindly retry configuration, validation, authentication/authorization, or business conflict errors.
- Retries require deadlines, retry budgets, exponential backoff, jitter, and adherence to Retry-After; combine with circuit breakers, bulkheads, and rate limits where appropriate.
- Retrying write operations requires idempotency, deterministic IDs, conditional writes, or deduplication. A timeout does not prove side effects did not occur.
- Business retries should maintain state, retry schedules, deadlines, and termination/DLQ paths; use outbox/inbox when coordinating databases and messaging.
- Measure attempts across the SDK, Spring, business workflow, and broker; test success, rejection, timeout, duplicate, and retry-budget-exhausted scenarios.

## References

- [Spring Retry project](https://github.com/spring-projects/spring-retry)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage retry policy](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [AWS SDK for Java 2.x retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub retry policy](https://cloud.google.com/pubsub/docs/subscription-retry-policy)
