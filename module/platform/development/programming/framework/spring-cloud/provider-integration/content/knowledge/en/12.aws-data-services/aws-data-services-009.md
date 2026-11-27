# Integrating AWS Services Without a Starter via the SDK in a Dedicated Adapter

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications practice integrating managed services on AWS, Azure, and Google Cloud using the corresponding Spring Cloud libraries or SDKs. Spring Cloud AWS (AWSpring) supplies starters and abstractions for several popular AWS services. However, the AWS ecosystem spans hundreds of services, and not every service has a Spring Cloud starter compatible with your project's version.

When integrating a service that lacks a suitable starter, an application can still use **AWS SDK for Java 2.x** directly. Encapsulate the SDK inside a **dedicated adapter**: the business layer invokes an application-defined interface, and the adapter translates that call into an SDK request, configures Region/credentials/retries, and maps responses or errors back into the internal contract. As a result, business code remains decoupled from AWS SDK packages and AWS-specific details.

This lesson uses **Amazon EventBridge** as its running example: when a reservation is confirmed, the application publishes a ReservationConfirmed event to an event bus for downstream systems to process. EventBridge is called via SDK v2 EventBridgeClient. The same pattern applies to other services via their respective SDK client modules—such as SES v2, AWS KMS, Amazon Bedrock Runtime, or any AWS API lacking a suitable starter.

After this lesson, you will be able to:

1. Decide when to use an AWSpring starter versus calling the AWS SDK directly.
2. Manage the AWS SDK BOM, service modules, client lifecycles, Region, and credential providers in Spring Boot.
3. Decouple business ports from AWS adapters to prevent SDK models from leaking into domain/application layers.
4. Implement an EventBridge publisher using PutEvents, handle partial failures, and map errors deliberately.
5. Grant least-privilege IAM permissions, configure local endpoints, and separate local/staging/production configs.
6. Design idempotency, outbox patterns, and retries to avoid lost or duplicated events.
7. Test the adapter with mocks/fakes, LocalStack, and AWS staging; monitor metrics and operate safely.

> **Scope:** This lesson demonstrates integrating AWS services via AWS SDK for Java 2.x, using EventBridge as the primary example. There is no universal starter covering every AWS service. Before writing a custom adapter, check which services and versions your active AWSpring release supports; when a matching starter exists and meets your requirements, prefer that abstraction.

## 2. Starter vs. Direct SDK: How to Choose?

### 2.1. Not Every Service Needs a Hand-Rolled Adapter

Several common integrations provide starters/abstractions in AWSpring depending on the version: S3, SQS, SNS, Secrets Manager, Parameter Store, and others. The exact catalog evolves per release train. For services without a starter, or when you need SDK APIs not exposed by the abstraction, calling SDK v2 is AWS's official integration path.

| Scenario | Approach | Reason |
| --- | --- | --- |
| AWSpring starter supports the exact service and APIs needed | Use the corresponding starter/abstraction | Less boilerplate configuration, smooth Spring Boot integration |
| A starter exists, but lacks a needed API or option | Use the SDK client directly in a small adapter | Retains full API access while keeping clean app boundaries |
| No suitable starter exists | Use the AWS SDK v2 service module inside an adapter | The SDK provides the official client API |
| Calling one AWS API in a single place | Thin adapter with an injected client | Avoids unnecessary generic abstractions |
| Multi-provider or potential provider swap | Stable business port, provider-specific adapters | Isolates differences in credentials, payloads, retries, and semantics |

Avoid building a custom "AWS generic client" framework wrapping every service just to hide direct SDK usage. Every AWS service has distinct APIs, error modes, quotas, and semantics. Design adapters around **application use cases**, not mechanical 1-to-1 wrappers over SDK methods.

### 2.2. Port-and-Adapter Architecture

~~~mermaid
flowchart LR
    A["Reservation application service"] --> B["ReservationEventPublisher<br/>application port"]
    B --> C["EventBridge adapter"]
    C --> D["AWS SDK v2<br/>EventBridgeClient"]
    D --> E["Amazon EventBridge"]
    F["AWS SDK configuration"] --> D
    G["IAM role / credential provider"] --> D
    H["Region / endpoint / retry"] --> D
~~~

Separation of responsibilities:

- **Domain/application:** defines events or commands and required interfaces, e.g., ReservationEventPublisher.
- **AWS adapter:** maps internal events to PutEventsRequestEntry, invokes the SDK, and interprets responses.
- **Configuration:** builds the SDK client, Region, credential provider, endpoint override, and retry strategy.
- **Infrastructure/IAM:** grants permissions to the workload role and provisions event buses/rules/targets via IaC.
- **Observability:** records logs/metrics at the adapter boundary without logging credentials or sensitive data.

The application service does not need to know the event bus name, which Region the SDK client uses, where credentials originate, or what the AWS response class is named. Those details belong strictly in the adapter/configuration layers.

## 3. Preparing AWS SDK for Java 2.x

### 3.1. Managing Versions with the BOM

Do not assign differing versions to individual SDK modules. Use the AWS SDK BOM so every service module aligns to a single release:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Select an `aws.sdk.version` compatible with your Java runtime and project dependency policy; the BOM version property in this example is managed by the project, not a fixed literal to copy blindly.

### 3.2. Add Only the Service Modules You Need

Example EventBridge integration:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>eventbridge</artifactId>
    </dependency>
</dependencies>
~~~

Common SDK modules:

| AWS service/API | SDK v2 artifact |
| --- | --- |
| Amazon EventBridge | eventbridge |
| Amazon SES v2 | sesv2 |
| AWS Key Management Service | kms |
| Amazon Bedrock Runtime | bedrockruntime |
| Amazon S3 | s3 |
| AWS Secrets Manager | secretsmanager |
| Amazon SQS | sqs |

Listing an artifact above identifies its SDK module, not that it lacks a starter. Check your active AWSpring release before deciding to manage an integration manually. Never pull every SDK module into every service "just in case you need it later".

### 3.3. SDK Clients Are Shared Resources

EventBridgeClient is thread-safe and intended to be shared across requests within an application. Never instantiate a new client per controller call or per published event. The client holds an HTTP connection pool, retry configuration, and internal resources; close it when the Spring context shuts down.

In Spring Boot, declare the client as a bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.eventbridge.EventBridgeClient;

@Configuration
public class EventBridgeSdkConfiguration {

    @Bean(destroyMethod = "close")
    DefaultCredentialsProvider awsCredentialsProvider() {
        return DefaultCredentialsProvider.create();
    }

    @Bean
    EventBridgeClient eventBridgeClient(
            DefaultCredentialsProvider credentialsProvider,
            @Value("${app.aws.region}") String region) {
        return EventBridgeClient.builder()
                .region(Region.of(region))
                .credentialsProvider(credentialsProvider)
                .build();
    }
}
~~~

Spring closes EventBridgeClient when the context stops; the credential provider bean is also closed via `destroyMethod`. Never close the client after individual calls. If using an async client, manage its lifecycle similarly and ensure executors/HTTP clients shut down cleanly.

### 3.4. Region and Credential Provider Chain

DefaultCredentialsProvider resolves credentials along the AWS SDK provider chain—checking environment variables, Java system properties, web identity, profiles, container credentials, or instance profiles depending on environment and SDK version. In production workloads, prefer IAM roles:

- ECS: task role.
- EKS: EKS Pod Identity or IRSA.
- EC2: instance profile.
- Local development: organization-approved AWS IAM Identity Center/profile.

Never write access keys or secret keys into source code, Git-committed YAML, Dockerfiles, or logs. Never build a static-credentials provider in production when a workload role can issue temporary credentials. The credential provider chain refreshes temporary credentials automatically; applications should not cache AWS session credentials manually.

Region is an explicit application configuration. Never infer Region from endpoints, hostnames, or end-user locations. EventBridge buses are Regional resources; a wrong Region can route calls to the wrong bus or raise ResourceNotFoundException.

## 4. Environment-Specific Configuration

### 4.1. application.yml

Externalize the event bus name and source in application configuration:

~~~yaml
app:
  aws:
    region: ap-southeast-1
    eventbridge:
      event-bus-name: rental-app-events
      source: com.rentalapp.reservations
~~~

Source is an application-defined name identifying the emitting system, not an AWS credential. Detail type identifies the event kind, such as ReservationConfirmed. Avoid embedding tenant IDs, emails, tokens, or personal data inside source or detail type; required business fields belong in detail under a managed schema.

### 4.2. Local Endpoints and Dummy Credentials

When testing with LocalStack or a compatible emulator, use a dedicated profile:

~~~yaml
# application-local.yml
app:
  aws:
    region: ap-southeast-1
    eventbridge:
      event-bus-name: rental-app-events
      source: com.rentalapp.reservations

aws:
  endpoint: http://localhost:4566
~~~

Construct a local client with `endpointOverride` and dummy credentials:

~~~java
import java.net.URI;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;

EventBridgeClient localClient = EventBridgeClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
        .build();
~~~

This is strictly for local test configuration. Never let `endpointOverride` or dummy credentials leak into production profiles. Never use static test credentials as a substitute for IAM roles on AWS.

### 4.3. Typed Configuration Binding

In larger projects, use `@ConfigurationProperties` rather than scattering `@Value` across adapters:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.aws")
public record AwsIntegrationProperties(
        String region,
        EventBridge eventbridge) {

    public record EventBridge(
            String eventBusName,
            String source) {
    }
}
~~~

Register the record via `@EnableConfigurationProperties(AwsIntegrationProperties.class)` or your project's configuration scan. You can add validation annotations to catch missing Region, bus name, or source at startup. Never store credentials in this record; credentials are managed by the AWS SDK provider chain.

## 5. Defining Contracts at the Application Layer

### 5.1. AWS-Agnostic Business Events

Example event emitted when a booking is confirmed:

~~~java
import java.time.Instant;

public record ReservationConfirmed(
        String eventId,
        String tenantId,
        String reservationId,
        String propertyId,
        Instant occurredAt) {
}
~~~

Event IDs should be deterministic per business occurrence. If a publisher retries or an outbox replays the same event, consumers receive the same ID to enforce idempotency.

### 5.2. Application Port

~~~java
public interface ReservationEventPublisher {
    void publish(ReservationConfirmed event);
}
~~~

The application service depends solely on the port:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationApplicationService {
    private final ReservationRepository reservations;
    private final ReservationEventPublisher eventPublisher;

    public ReservationApplicationService(
            ReservationRepository reservations,
            ReservationEventPublisher eventPublisher) {
        this.reservations = reservations;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void confirm(String reservationId) {
        Reservation reservation = reservations.confirm(reservationId);

        eventPublisher.publish(new ReservationConfirmed(
                reservation.eventId(),
                reservation.tenantId(),
                reservation.id(),
                reservation.propertyId(),
                reservation.confirmedAt()));
    }
}
~~~

This snippet illustrates dependency direction only. **Do not blindly publish to EventBridge directly inside a database transaction** like this in production. If the DB commits and publish fails, or publish succeeds and the DB rolls back, the two systems diverge. Section 9 presents the transactional outbox pattern to avoid dual-writes, where a worker invokes this port after the DB transaction commits.

### 5.3. Why Never Return AWS SDK Models from the Port?

Never make an application port return PutEventsResponse, accept PutEventsRequestEntry, or throw EventBridgeException. Doing so couples domain/application code to the SDK and forces other providers' adapters to fabricate AWS types.

Keep the port in application domain types. The adapter is responsible for:

- Serializing the event to JSON.
- Setting EventBridge `source`, `detailType`, `eventBusName`, and `time`.
- Calling the SDK.
- Inspecting `eventId`, `errorCode`, `errorMessage`, and `failedEntryCount`.
- Translating failures into internal exceptions/results meaningful to the use case.

## 6. Implementing the EventBridge Adapter with SDK v2

### 6.1. Serializing Detail and Building the Request

EventBridge PutEvents accepts a list of entries. Each entry specifies the event bus name, source, detail type, timestamp, and JSON-serialized `detail`.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import software.amazon.awssdk.services.eventbridge.EventBridgeClient;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequest;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequestEntry;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResponse;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResultEntry;
import software.amazon.awssdk.services.eventbridge.model.EventBridgeException;
import software.amazon.awssdk.core.exception.SdkClientException;

@Component
public class EventBridgeReservationEventPublisher
        implements ReservationEventPublisher {

    private final EventBridgeClient client;
    private final ObjectMapper objectMapper;
    private final String eventBusName;
    private final String source;

    public EventBridgeReservationEventPublisher(
            EventBridgeClient client,
            ObjectMapper objectMapper,
            @Value("${app.aws.eventbridge.event-bus-name}") String eventBusName,
            @Value("${app.aws.eventbridge.source}") String source) {
        this.client = client;
        this.objectMapper = objectMapper;
        this.eventBusName = eventBusName;
        this.source = source;
    }

    @Override
    public void publish(ReservationConfirmed event) {
        final String detail;
        try {
            detail = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize ReservationConfirmed event", ex);
        }

        PutEventsRequestEntry entry = PutEventsRequestEntry.builder()
                .eventBusName(eventBusName)
                .source(source)
                .detailType("ReservationConfirmed")
                .time(event.occurredAt())
                .detail(detail)
                .build();

        final PutEventsResponse response;
        try {
            response = client.putEvents(
                    PutEventsRequest.builder()
                            .entries(entry)
                            .build());
        } catch (EventBridgeException ex) {
            String code = ex.awsErrorDetails() == null
                    ? "EVENTBRIDGE_SERVICE_ERROR"
                    : ex.awsErrorDetails().errorCode();
            throw new EventPublicationException(event.eventId(), code, ex);
        } catch (SdkClientException ex) {
            throw new EventPublicationException(
                    event.eventId(), "AWS_SDK_CLIENT_ERROR", ex);
        }

        if (response.failedEntryCount() != null
                && response.failedEntryCount() > 0) {
            PutEventsResultEntry result = response.entries().get(0);
            throw new EventPublicationException(
                    event.eventId(),
                    result.errorCode());
        }
    }
}
~~~

For a single-entry request, if `failedEntryCount` exceeds 0, the corresponding result entry holds the error details. The internal exception captures the event ID and error code for retry workers or failure tracking. Never embed the full JSON detail or tokens in exceptions or logs.

### 6.2. Internal Exception

~~~java
public class EventPublicationException extends RuntimeException {
    private final String eventId;
    private final String errorCode;

    public EventPublicationException(String eventId, String errorCode) {
        super("Event publication failed: " + errorCode + " for " + eventId);
        this.eventId = eventId;
        this.errorCode = errorCode;
    }

    public EventPublicationException(
            String eventId, String errorCode, Throwable cause) {
        super("Event publication failed: " + errorCode + " for " + eventId, cause);
        this.eventId = eventId;
        this.errorCode = errorCode;
    }

    public String eventId() {
        return eventId;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Here, raw AWS error messages are not forwarded straight to client HTTP responses. When diagnostic context is needed, log redacted details in the adapter tied by correlation ID. AWS message text can change across service updates; business logic must never parse human-readable messages to control flow.

### 6.3. Do Not Mistake HTTP 200 for Full Batch Success

A PutEvents call can return HTTP 200 even when individual entries fail. Always inspect `FailedEntryCount` and every `PutEventsResultEntry`:

- `EventId` populated: EventBridge accepted that entry.
- `ErrorCode`/`ErrorMessage` populated: that entry failed.
- With multiple entries, response entries align positionally with request entries.
- The SDK retry strategy handles request-level HTTP/retryable failures; partial failures inside a 200 response require dedicated application handling.

When sending multiple entries in one batch, **retry only the failed entries with retryable error codes**—never resend the entire batch including already-accepted entries. When a timeout or dropped response leaves the outcome uncertain, consumers still need idempotency because retries may produce duplicate events.

### 6.4. Request and Event Size Limits

EventBridge PutEvents accepts at most **10 entries per request**. Each event is capped at **256 KB**, calculated across event fields per service rules—not `detail` alone. Control payloads before sending:

- Include only fields consumers genuinely need.
- Never embed large files, images, or documents; store objects in S3 and publish object keys/metadata.
- Never emit secrets, access tokens, or sensitive payment data.
- Version event schemas and preserve backward compatibility for consumers.
- In batches, check total request limits and process each entry result individually.

## 7. Retries, Idempotency, and Distributed Failures

### 7.1. Error Classification

| Error category | Examples | Handling strategy |
| --- | --- | --- |
| Configuration/permission error | AccessDeniedException, wrong bus/Region | Do not retry endlessly; fix IAM, resource policy, or config |
| Payload error | Invalid JSON, oversized event, invalid source/detail type | Fix schema/payload; retrying verbatim will not help |
| Throttling | ThrottlingException | Backoff + jitter, cap attempts, and rate-limit |
| Internal service error | InternalFailure | Bounded retries per policy |
| Network/timeout error | SdkClientException, socket timeout | Outcome ambiguous; controlled retries relying on idempotent event IDs |
| Partial failure | HTTP 200 with entry ErrorCode | Retry only failed retryable entries |

Avoid lumping every error into "AWS unavailable". Permission and validation errors require config/code fixes; throttling and transient errors can be retried. When the SDK client already runs a retry strategy, avoid adding unbounded service-layer retry loops that amplify traffic.

### 7.2. Jittered Backoff and Time Bounds

For retryable errors, apply exponential backoff with jitter, for example:

\[
delay_k \sim U(0,\min(delay_{max},baseDelay \times 2^k))
\]

Bound retry attempts and total deadlines according to your SLO. Once an HTTP deadline approaches, do not block the request thread waiting on retries; hand off to an asynchronous worker/queue/outbox. Configure SDK retry strategies at the client level; add application-level retries only for clear reasons, notably handling partial failures inside HTTP 200 responses.

### 7.3. Consumer Idempotency

EventBridge does not provide end-to-end exactly-once delivery. Consumers must tolerate duplicate deliveries and be idempotent:

1. Every event carries a deterministic `eventId` generated by business logic/outbox.
2. Consumers record processed event IDs in an inbox/deduplication table with a unique constraint.
3. Within the same transaction as business state updates, consumers mark the event ID as processed.
4. When a duplicate event ID arrives, skip already-completed side effects and return cleanly.
5. For side effects on external systems, pass an idempotency key if supported by the target API or use sagas/compensation.

Never treat the `EventId` returned by EventBridge as your unique business event ID if duplicate prevention must span retries across publishes. EventBridge's `EventId` identifies a specific EventBridge ingestion; retrying after a timeout generates a new EventBridge `EventId`.

### 7.4. Bus Existence and Successful Responses

Misconfigured event buses should be caught during deployment. In some scenarios targeting a nonexistent bus, PutEvents may still succeed at the API call level without delivering events as expected. Therefore:

- Provision event buses, rules, and targets via IaC before deploying applications.
- Verify bus name, account, and Region in pipelines or smoke tests.
- Optionally run `DescribeEventBus` during startup/deployment validation if the role has permission.
- Verify ingestion metrics and target invocations after publishing test events.

Never treat HTTP 200 or `FailedEntryCount=0` alone as proof that end-to-end routing is configured properly.

## 8. Transactional Outbox: Avoiding Dual-Writes

### 8.1. Why Is Calling EventBridge Inside a DB Transaction Risky?

Suppose reservations live in RDS and events go to EventBridge:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant DB as RDS
    participant EB as EventBridge
    App->>DB: UPDATE reservation = CONFIRMED
    App->>EB: PutEvents ReservationConfirmed
    EB-->>App: Accepted
    DB-->>App: COMMIT fails
    Note over DB,EB: Event published even though reservation rolled back
~~~

The reverse failure also occurs: DB commits, then the app crashes before calling EventBridge—leaving the reservation confirmed with no event emitted. No default ACID transaction spans RDS and EventBridge.

### 8.2. Writing the Outbox in the Same Transaction

Create an outbox table in the same database as `reservation`:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(100) PRIMARY KEY,
    aggregate_id    VARCHAR(100) NOT NULL,
    event_type      VARCHAR(150) NOT NULL,
    payload         JSONB NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    published_at    TIMESTAMPTZ NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      VARCHAR(500) NULL
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (occurred_at)
    WHERE published_at IS NULL;
~~~

Inside the same `@Transactional` method:

~~~java
@Transactional
public void confirm(String reservationId) {
    Reservation reservation = reservations.confirm(reservationId);

    ReservationConfirmed event = new ReservationConfirmed(
            reservation.eventId(),
            reservation.tenantId(),
            reservation.id(),
            reservation.propertyId(),
            reservation.confirmedAt());

    final String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    } catch (JsonProcessingException ex) {
        throw new IllegalArgumentException("Cannot serialize outbox event", ex);
    }

    outboxRepository.insert(
            event.eventId(),
            reservation.id(),
            "ReservationConfirmed",
            payload,
            event.occurredAt());
}
~~~

If the transaction commits, both the reservation update and outbox record persist together. If it rolls back, both roll back. In this PostgreSQL example, bind the payload into the JSONB column using `PGobject` or `CAST(? AS jsonb)` rather than plain VARCHAR. An independent worker reads pending outbox rows and publishes them via ReservationEventPublisher.

### 8.3. Outbox Relay Worker

Basic flow:

~~~text
SELECT pending outbox rows
  -> publish to EventBridge
  -> if entry accepted: mark published_at
  -> if retryable: increment attempts, record last_error, schedule retry
  -> if permanent failure: transition to dead-letter/review queue
~~~

When running multiple workers concurrently, claim rows with appropriate locking—such as `SELECT ... FOR UPDATE SKIP LOCKED` in a short transaction, or `claimed_by`/`lease_until` columns. Never hold a DB transaction or row lock open across slow AWS network calls; claim records, commit, publish, and update status separately with leases and crash recovery.

There remains a crash window after EventBridge accepts an event and before the outbox row is marked published, causing the worker to resend. Thus, the outbox guarantees **no committed event intent is lost**, while delivery remains at-least-once—making consumer deduplication by event ID essential.

### 8.4. Never Mark Published on Partial Failure

When a batch holds multiple entries, map every result entry back to its corresponding event ID:

- Entry with `EventId` and no error: mark accepted/published.
- Entry with retryable error: keep pending and schedule retry.
- Entry with permanent error: move to dead-letter/review, alert, and retain payload for inspection.
- Timeout with unknown result: retry with the same event ID; consumers deduplicate.

Never mark an entire batch published solely because PutEvents returned HTTP 200.

## 9. Least-Privilege IAM and EventBridge Resources

### 9.1. Event Publishing Permissions

The producer's role typically needs `events:PutEvents` scoped to the exact event bus ARN:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutEvents"
      ],
      "Resource": "arn:aws:events:ap-southeast-1:123456789012:event-bus/rental-app-events"
    }
  ]
}
~~~

If an adapter or health check requires `DescribeEventBus`, grant that action narrowly where supported and genuinely needed. Applications do not need `events:PutRule`, `events:PutTargets`, `events:CreateEventBus`, or EventBridge admin permissions when buses, rules, and targets are provisioned via IaC.

### 9.2. Cross-Account Event Buses

When publishing events to another AWS account:

- The producer role needs `events:PutEvents` targeting the destination bus in its IAM policy.
- The destination event bus needs a resource-based policy permitting the source principal/account to send events.
- Verify Region, account, bus ARN, and any Organization policies/SCPs.
- Never grant account-wide `events:*` to work around cross-account permission errors.

Separate runtime producer roles from infrastructure deployment roles. Runtime applications only emit events; CI/IaC pipelines manage buses, rules, targets, archives, replays, and DLQs.

### 9.3. Target Permissions Differ from Producer Permissions

The producer sends events to the bus; EventBridge rules match events and invoke targets like Lambda, SQS, or Step Functions. Roles/resource policies allowing EventBridge to invoke targets are configured separately. `events:PutEvents` succeeding only proves EventBridge accepted the entry at the API boundary—not that rules matched or targets processed it cleanly.

## 10. SDK Retries, Timeouts, and Client Configuration

### 10.1. Start with Default Retries Before Customizing

AWS SDK v2 ships with mode-based retry strategies. Default client settings are usually a good starting point; observe actual errors and throttling before tuning. When customization is needed, configure it on the client:

~~~java
EventBridgeClient client = EventBridgeClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(java.time.Duration.ofSeconds(2))
                .apiCallTimeout(java.time.Duration.ofSeconds(5)))
        .build();
~~~

This illustrates SDK-level timeouts; tune values to your real latencies and SLOs. `apiCallAttemptTimeout` bounds a single attempt, while `apiCallTimeout` bounds the entire API call including retries. If the overall call times out, server-side outcome remains uncertain; downstream idempotency is still mandatory.

Never stack retry policies across HTTP clients, SDK, and application code without computing total attempts. For instance, 3 SDK attempts inside 3 service-layer retries can emit up to 9 requests. Partial failures inside HTTP 200 responses still need custom handling because the SDK cannot know which entries the app wishes to retry.

### 10.2. When to Use AsyncClient?

EventBridgeAsyncClient returns `CompletableFuture`, fitting non-blocking pipelines with explicit backpressure. Do not switch to async just to "go faster" if controllers or repositories still block. When using async:

- Manage executors/HTTP clients and clean shutdown.
- Handle exceptions inside completion stages.
- Cap concurrent in-flight futures.
- Propagate correlation and tracing contexts explicitly.
- Ensure outbox workers mark rows accepted only after the future completes and result entries show no errors.

For blocking Spring MVC/JDBC applications, synchronous EventBridgeClient is usually simpler and easier to reason about. Keep a consistent concurrency model across your stack.

## 11. Testing the Adapter and AWS Integration

### 11.1. Unit Tests with a Mocked SDK Client

Mock EventBridgeClient to verify event mapping and partial-failure handling:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import software.amazon.awssdk.services.eventbridge.EventBridgeClient;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequest;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResponse;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResultEntry;

class EventBridgeReservationEventPublisherTest {

    @Test
    void publishesReservationConfirmed() {
        EventBridgeClient client = org.mockito.Mockito.mock(
                EventBridgeClient.class);
        when(client.putEvents(any(PutEventsRequest.class)))
                .thenReturn(PutEventsResponse.builder()
                        .failedEntryCount(0)
                        .entries(PutEventsResultEntry.builder()
                                .eventId("aws-event-1")
                                .build())
                        .build());

        var publisher = new EventBridgeReservationEventPublisher(
                client, new ObjectMapper(),
                "rental-app-events", "com.rentalapp.reservations");

        publisher.publish(new ReservationConfirmed(
                "evt-1", "tenant-a", "res-1", "house-1",
                java.time.Instant.parse("2026-11-24T10:00:00Z")));

        ArgumentCaptor<PutEventsRequest> captor =
                ArgumentCaptor.forClass(PutEventsRequest.class);
        verify(client).putEvents(captor.capture());

        var entry = captor.getValue().entries().get(0);
        org.junit.jupiter.api.Assertions.assertEquals(
                "rental-app-events", entry.eventBusName());
        org.junit.jupiter.api.Assertions.assertEquals(
                "ReservationConfirmed", entry.detailType());
        org.junit.jupiter.api.Assertions.assertTrue(
                entry.detail().contains("res-1"));
    }

    @Test
    void failsWhenEntryHasPartialFailure() {
        EventBridgeClient client = org.mockito.Mockito.mock(
                EventBridgeClient.class);
        when(client.putEvents(any(PutEventsRequest.class)))
                .thenReturn(PutEventsResponse.builder()
                        .failedEntryCount(1)
                        .entries(PutEventsResultEntry.builder()
                                .errorCode("ThrottlingException")
                                .errorMessage("Rate exceeded")
                                .build())
                        .build());

        var publisher = new EventBridgeReservationEventPublisher(
                client, new ObjectMapper(),
                "rental-app-events", "com.rentalapp.reservations");

        assertThrows(EventPublicationException.class, () ->
                publisher.publish(new ReservationConfirmed(
                        "evt-2", "tenant-a", "res-2", "house-1",
                        java.time.Instant.now())));
    }
}
~~~

The first test verifies request mapping; the second proves HTTP-level success is not mistaken for entry-level success. In real projects, add assertions on exception `eventId`/`errorCode`, JSON schema, and required fields. This snippet is a template requiring real project dependencies and test setup; no test execution results are claimed here.

### 11.2. LocalStack for Local Development Loops

LocalStack supports many AWS APIs, including EventBridge. Use Testcontainers/Compose to launch LocalStack, create the event bus, and point the SDK at it via `endpointOverride`. Example bus creation via AWS CLI:

~~~bash
aws --endpoint-url http://localhost:4566 events create-event-bus \
  --name rental-app-events \
  --region ap-southeast-1
~~~

LocalStack validates bean wiring, serialization, and API requests locally. Do not assume it faithfully simulates all AWS IAM authorization, throttling, cross-account policies, archive/replay, target retries, or metrics.

### 11.3. AWS Staging to Verify Real Semantics

Staging should verify:

1. The workload role holds `events:PutEvents` on the exact event bus ARN.
2. The event bus exists in the configured account and Region.
3. PutEvents returns an accepted event ID and events reach matching rules/targets.
4. Event patterns match the exact `source`, `detail-type`, and version.
5. Target permissions, retry policies, and DLQs work as intended.
6. Throttling/partial failures are handled within configured bounds.
7. Cross-account resource policies work when targeting buses in another account.
8. Consumers deduplicate when the same event ID is re-sent.

Never test throttling with unbounded load. Enforce request/cost budgets, concurrency limits, and a clear kill switch.

## 12. Observability and Troubleshooting

### 12.1. Structured Logging

Logs should include enough context for investigation:

- Business `eventId`, correlation ID, and reservation ID (where permitted).
- Event bus name, `source`, `detailType`, and AWS Region.
- SDK operation, latency, retry attempts, and error codes.
- EventBridge's returned `EventId` once an entry is accepted.
- Outbox outcome: pending, published, retry scheduled, or dead-lettered.

Never log tokens, AWS credentials, full payloads containing personal data, payment details, or secrets. Trace across producer and consumer using event IDs instead of dumping entire payloads.

### 12.2. CloudWatch Metrics

Monitor EventBridge metrics under namespace `AWS/Events`, for example:

| Metric | Meaning |
| --- | --- |
| PutEventsApproximateCallCount | Approximate PutEvents call volume |
| PutEventsApproximateFailedCount | Approximate failed entries |
| PutEventsApproximateThrottledCount | Approximate throttled entries/requests |
| MatchedEvents | Events matching rules |
| Invocations | Times EventBridge invoked targets |
| FailedInvocations | Failed target invocations |

Exact metric names and available dimensions vary by bus type and features; verify in the CloudWatch console for your resources. Also monitor outbox backlog/oldest age, retry counts, DLQ depth, and consumer processing latency. If PutEvents succeeds while `MatchedEvents` stays flat, inspect event patterns, bus, source, and detail type. If `Invocations` rises alongside `FailedInvocations`, inspect target permissions, target health, and retry/DLQ settings.

### 12.3. Diagnostic Table

| Symptom | Possible causes | What to check |
| --- | --- | --- |
| AccessDeniedException | Missing IAM policy or bus resource policy permission | Principal, action, ARN, SCPs, and cross-account policies |
| ResourceNotFoundException | Wrong bus, Region, or account | Compare config against IaC; verify bus exists |
| PutEvents returns 200 but events vanish | Wrong/missing bus, non-matching rule, or delayed metrics/targets | Event bus, source, detail type, event pattern, and ingestion metrics |
| FailedEntryCount > 0 | Partial failure inside batch | Inspect each result entry; retry only retryable failures |
| ThrottlingException | Publish rate exceeds limits | Backoff + jitter, lower concurrency, and inspect quotas |
| Event accepted, target fails | Target permission, timeout, or target unavailable | Check `FailedInvocations`, retry policy, DLQ, and target logs |
| Consumer processes duplicates | At-least-once delivery or producer retry after timeout | Deduplicate via business event ID / inbox table |
| Outbox backlog grows | Publisher failing, under-provisioned workers, or bus unavailable | Check oldest item age, error breakdown, worker concurrency, and DLQ |

## 13. Extending the Adapter Pattern to Other AWS Services

Every service SDK has its own models, retries, and semantics, yet the same structure holds:

| Use case | Adapter/SDK | Suggested business port |
| --- | --- | --- |
| Transactional email delivery | SES v2 (sesv2) | TransactionalEmailSender |
| Envelope key encryption/decryption | KMS (kms) | DataKeyProvider |
| Invoking foundation models | Bedrock Runtime (bedrockruntime) | TextGenerationGateway |
| Object upload/download | S3 (s3) | DocumentStorage |
| Domain event publishing | EventBridge (eventbridge) | DomainEventPublisher |

Avoid generic interfaces like `AwsService.call(Map<String,Object>)`. Ports should express business intent—such as `sendReservationConfirmation`, `encryptDataKey`, or `storeDocument`—without exposing provider API shapes.

When switching providers, Azure/Google adapters implement the same port while differing in retry behavior, consistency, authentication, quotas, message ordering, delivery guarantees, and payload limits. Define the application's required contract explicitly and verify whether each provider meets it or requires extra workflow steps.

## 14. Production Checklist

1. **Service support:** verified whether AWSpring offers a compatible starter for the service/API/version; using direct SDK only with clear justification.
2. **Dependencies:** AWS SDK BOM aligns versions; only required service modules are included.
3. **Client lifecycle:** clients are singleton Spring beans, thread-safe, and closed on context shutdown.
4. **Identity:** production relies on workload IAM roles/credential providers; zero hardcoded access keys.
5. **Region/endpoints:** Regions and resources are configured per environment; endpoint overrides exist only in local/test.
6. **Adapter boundary:** domain/application layers never import AWS SDK requests, responses, or exceptions.
7. **Payloads:** schemas are versioned, event IDs are deterministic, no unnecessary secrets/PII are emitted, and sizes fit within limits.
8. **Failure handling:** partial failures are checked, retries use jitter/deadlines, and permission/validation errors never retry infinitely.
9. **Delivery:** outbox pattern is used when DB commits and event emissions must stay consistent; consumers are idempotent.
10. **IAM:** runtime permissions allow only required actions/resources; buses/rules/targets are provisioned via IaC.
11. **Testing:** unit tests for adapters, local emulators for fast feedback, staging for real IAM/network/target semantics.
12. **Operations:** CloudWatch dashboards, safe logging, backlog/age/DLQ alerts, and replay/recovery runbooks.

## 15. Self-Practice Exercises

1. Check whether an AWS service you need has a matching AWSpring starter. If not, pick the SDK module and explain why a dedicated adapter is needed.
2. Define a `DomainEventPublisher` port and an `EventBridgeDomainEventPublisher` adapter; ensure the domain package imports zero AWS SDK classes.
3. Configure the AWS SDK BOM and `EventBridgeClient` using a configured Region, workload role credentials, and Spring-managed lifecycle.
4. Create a `ReservationConfirmed` event with a deterministic event ID, serialize it to JSON, and publish it with `PutEvents`.
5. Simulate an HTTP 200 response with `FailedEntryCount=1`; pinpoint the failed entry and design bounded retries.
6. Write an IAM policy granting only `events:PutEvents` on one event bus; test the error when publishing to a different bus or Region.
7. Use LocalStack to create an event bus, publish an event, and verify rule/target delivery locally.
8. Design an outbox worker that avoids losing events after DB commits and handles crashes occurring after EventBridge accepts an event but before the row is marked published.
9. Design a consumer inbox/deduplication mechanism so duplicate deliveries of the same event ID never trigger duplicate side effects.
10. Compare the EventBridge adapter against an SES v2 or KMS adapter; identify shared client configuration versus service-specific port/error/payload semantics.

**Completion criteria:** learners can integrate an AWS service lacking a suitable starter using SDK v2 inside a dedicated adapter, manage clients/Regions/credentials safely, handle partial-failure responses and retries, preserve consistency with outbox/idempotency patterns, and test adapters both locally and on AWS staging.

## References

- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): module list, starters, and version-specific configuration.
- [AWS SDK for Java 2.x — Developer guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html): service clients, credentials, Regions, and retries.
- [AWS SDK for Java 2.x — Set the AWS Region](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html): Region configuration.
- [AWS SDK for Java 2.x — Credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html): default provider chain and IAM roles.
- [AWS SDK for Java 2.x — Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html): retry modes and attempts.
- [Amazon EventBridge — PutEvents API](https://docs.aws.amazon.com/eventbridge/latest/APIReference/API_PutEvents.html): requests/responses, entry errors, and limits.
- [Amazon EventBridge — Permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus-perms.html): event bus resource policies and cross-account access.
- [Amazon EventBridge — Monitoring](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html): CloudWatch metrics.
- [Amazon EventBridge — Quotas](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-quota.html): quotas, event sizes, and PutEvents limits.
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): dual-writes, outboxes, and duplicate delivery.
