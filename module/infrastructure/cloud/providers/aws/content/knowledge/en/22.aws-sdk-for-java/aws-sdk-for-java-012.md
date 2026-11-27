# Calling SQS, SNS, STS, and Secrets Manager from Java

> **Chapter:** AWS SDK for Java  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem across Region/AZ infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless. Learners build skills in selecting services and designing and deploying applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

After this lesson, learners can:

1. Set up Maven/Gradle projects using **AWS SDK for Java 2.x**, the BOM, and required service modules.
2. Create AWS service clients with the right **Region**, credentials provider, and lifecycle.
3. Send, receive, delete, change visibility, and send batch messages with **Amazon SQS**.
4. Handle delivery semantics, duplicate messages, ordering, FIFO, visibility timeouts, and dead-letter queues (DLQs).
5. Publish messages to **Amazon SNS**, configure topics/subscriptions, filter policies, and SNS → SQS fan-out.
6. Use **AWS STS** to inspect caller identity, assume roles, manage temporary credentials, and understand role chaining.
7. Retrieve **AWS Secrets Manager** secrets, handle `SecretString`/`SecretBinary`, KMS, rotation, and caching.
8. Apply IAM least privilege, resource policies, VPC endpoints, TLS, and sensitive data hygiene.
9. Handle AWS SDK errors, retries, timeouts, idempotency, and observability.
10. Write integration tests and use **read-only** AWS CLI commands to inspect related resources.

## 1. The Problem: A Java Service Needs to Send Messages, Emit Events, and Fetch Secrets

An Orders system written in **Spring Boot** runs on Amazon ECS. When a user places an order, the service must:

- Enqueue invoice-generation work onto **SQS** for asynchronous worker processing.
- Publish an **OrderCreated** event to **SNS** so multiple consumers receive notifications.
- Use **STS AssumeRole** when accessing resources in another AWS account.
- Read database credentials from **Secrets Manager** instead of storing passwords in source code or configuration files.

~~~mermaid
flowchart TB
    API["Spring Boot Orders API"] --> SDK["AWS SDK for Java 2.x"]
    SDK --> SQS["Amazon SQS"]
    SDK --> SNS["Amazon SNS"]
    SDK --> STS["AWS STS"]
    SDK --> SM["AWS Secrets Manager"]
    SQS --> BILL["Billing worker"]
    SNS --> Q1["SQS inventory subscription"]
    SNS --> Q2["SQS analytics subscription"]
    SM --> DB["RDS / Aurora credentials"]
    STS --> ROLE["Temporary role credentials"]
~~~

The SDK is a client layer invoking AWS APIs over HTTPS. IAM determines what the caller is allowed to do; service resource policies can restrict who may send or receive; VPC/network controls govern connectivity. **Constructing a client successfully does not mean IAM will authorize the request.**

### 1.1. When to Use Which Service?

| Service | Role | Example in Orders |
| --- | --- | --- |
| **SQS** | Message queue decoupling producers/consumers, buffering backlogs, and retries. | Send `CreateInvoice` to a worker. |
| **SNS** | Pub/sub fanning out one message to multiple subscriptions. | Publish `OrderCreated` for Inventory, Analytics, and Notification. |
| **STS** | Issues temporary security credentials and identity details. | Assume a role in the Billing account. |
| **Secrets Manager** | Stores, distributes, and rotates secrets. | Retrieve database username/password or API credentials. |

SQS fits when consumers pull and control processing pace. SNS fits when a producer broadcasts one message to multiple subscribers. STS is not a message broker; Secrets Manager is not a store for non-sensitive public application configuration.

## 2. AWS SDK for Java 2.x: Dependencies and BOM

AWS SDK for Java 2.x uses package `software.amazon.awssdk.*`, builder APIs, and immutable request/response models. SDK 1.x uses `com.amazonaws.*` and has a different lifecycle and API.

For new code, prefer **SDK 2.x**. Never mix SDK 1.x and 2.x classes in the same code block or assume they share credential providers.

### 2.1. Maven: Import the SDK BOM

The BOM aligns versions across modules. Example `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <aws.sdk.version>2.x.y</aws.sdk.version>
</properties>

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

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sqs</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sns</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>secretsmanager</artifactId>
    </dependency>
</dependencies>
~~~

`2.x.y` is a placeholder, not a resolvable version. Replace it with **an organization-approved 2.x release**, update the BOM periodically, and review release notes and security advisories. Never let individual service modules drift in version once using the BOM.

### 2.2. Gradle: Using Platform BOM

~~~kotlin
dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.x.y"))

    implementation("software.amazon.awssdk:sqs")
    implementation("software.amazon.awssdk:sns")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:secretsmanager")
}
~~~

In Gradle, `platform(...)` imports dependency constraints from the BOM. When using Spring Boot, verify which dependency management controls SDK versions to avoid conflicts between the BOM and other dependency constraints.

### 2.3. Secrets Manager Caching (Optional)

If the application caches secrets to reduce API calls, add the dedicated module:

~~~xml
<dependency>
    <groupId>com.amazonaws.secretsmanager</groupId>
    <artifactId>aws-secretsmanager-caching-java</artifactId>
    <version>2.2.0</version>
</dependency>
~~~

This caching library is versioned independently from the AWS SDK BOM; release 2.2.0 uses AWS SDK for Java 2.x. Review release notes before upgrading. The cache defaults to LRU and refreshes items roughly every hour; TTL is configurable. The cache does not harden memory containing secrets and does not automatically invalidate an item when the app needs an immediate refresh.

## 3. Region, Credentials Provider, and Client Lifecycle

### 3.1. Never Hardcode Access Keys

AWS SDK for Java 2.x provides a **default credentials provider chain**. The chain checks runtime-appropriate credential sources, such as:

- Java system properties / environment variables when configured.
- Web identity tokens and roles for workloads on supported platforms.
- Shared AWS config/credentials files in developer environments.
- ECS task role credentials.
- EC2 instance profile credentials.

For production workloads on ECS/EC2/Lambda/EKS, prefer **IAM roles/workload identities** and let the SDK fetch and refresh credentials automatically. Never commit access keys or secret keys to Git, Docker images, `application.yml`, or Java source files.

### 3.2. Creating an SQS Client for a Region

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

public final class AwsClients {
    private AwsClients() {}

    public static SqsClient sqsClient() {
        return SqsClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

The SDK uses the default credentials provider automatically when `credentialsProvider` is omitted. Region can be injected from application configuration or environment; the snippet above illustrates Singapore (`ap-southeast-1`).

**A client's Region does not automatically switch to a queue/topic/secret in another Region.** The ARN/resource must reside in the Region matching the endpoint called; to access resources in another Region, create a separate client for that Region according to architecture and permissions.

### 3.3. Create Clients Once and Reuse Them

Synchronous SDK clients are thread-safe and can be shared across threads. Never create and close a client per message or HTTP request.

~~~java
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;

public final class AwsClientFactory implements AutoCloseable {
    public final SqsClient sqs;
    public final SnsClient sns;
    public final StsClient sts;
    public final SecretsManagerClient secrets;

    public AwsClientFactory() {
        this.sqs = SqsClient.create();
        this.sns = SnsClient.create();
        this.sts = StsClient.create();
        this.secrets = SecretsManagerClient.create();
    }

    @Override
    public void close() {
        secrets.close();
        sts.close();
        sns.close();
        sqs.close();
    }
}
~~~

`create()` uses default configuration from the SDK environment/profile/Region chains. In real applications, manage lifecycles via dependency injection—such as Spring `@Bean` singletons and shutdown hooks—and never close clients when a request ends.

### 3.4. Configuring Timeouts

You can bound both the overall API call and each attempt:

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.regions.Region;

SqsClient client = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .overrideConfiguration(
        ClientOverrideConfiguration.builder()
            .apiCallAttemptTimeout(Duration.ofSeconds(3))
            .apiCallTimeout(Duration.ofSeconds(10))
            .build()
    )
    .build();
~~~

- **`apiCallAttemptTimeout`:** bounds a single HTTP/API attempt.
- **`apiCallTimeout`:** bounds the total call duration, including retries.
- Timeouts must align with SLOs, networking, and service operation behavior.
- For SQS long polling, the HTTP read timeout must be **longer than `WaitTimeSeconds`** plus network margin; if shorter, the client times out before SQS responds.

Never set overly tight timeouts and then compensate with unlimited retries. Retrying cannot fix misconfigured timeouts.

## 4. SQS: Sending Messages with Java SDK 2.x

### 4.1. Sending a Single Message

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

public final class InvoicePublisher {
    private final SqsClient sqs;
    private final String queueUrl;

    public InvoicePublisher(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public String publish(String orderId, String operationId) {
        String body = """
            {
              "eventType": "CreateInvoice",
              "orderId": "%s",
              "operationId": "%s"
            }
            """.formatted(orderId, operationId);

        SendMessageRequest request = SendMessageRequest.builder()
            .queueUrl(queueUrl)
            .messageBody(body)
            .build();

        SendMessageResponse response = sqs.sendMessage(request);
        return response.messageId();
    }
}
~~~

This simple example demonstrates the API. In production, **serialize JSON with Jackson** or a JSON library instead of string formatting; `orderId` could contain characters needing escaping and should never be manually interpolated into JSON.

`queueUrl` is the queue URL, not the queue ARN. Obtain the URL from deployment config or via `GetQueueUrl` if the IAM role permits lookup.

### 4.2. Resolving Queue URL by Name

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.GetQueueUrlRequest;

String queueUrl = sqs.getQueueUrl(
    GetQueueUrlRequest.builder()
        .queueName("orders-invoice-queue")
        .build()
).queueUrl();
~~~

For cross-account queues, requests may need `QueueOwnerAWSAccountId` and matching IAM/resource policies. Prefer injecting the queue URL/ARN from deployment configuration rather than guessing names or accounts.

### 4.3. Useful Metadata on SendMessageResponse

The response provides:

- **`messageId`:** SQS-assigned message ID.
- **`MD5OfMessageBody`:** checksum of the body per the API.
- **`MD5OfMessageAttributes`:** checksum of attributes when attributes are sent.
- **`sequenceNumber`:** sequence info for FIFO queues.

`messageId` is not a business idempotency key. If a producer times out after SQS accepted the message but before the response arrived, retrying creates another message. Include a **stable `operationId`/`eventId`** in the payload or message attributes so consumers can deduplicate.

## 5. SQS: Receiving, Processing, and Deleting Messages

SQS is a **pull-based queue**: consumers call `ReceiveMessage` to fetch a batch of messages, process them, and call `DeleteMessage` once work succeeds.

### 5.1. ReceiveMessage with Long Polling

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;

import java.util.List;

public final class InvoiceWorker {
    private final SqsClient sqs;
    private final String queueUrl;

    public InvoiceWorker(SqsClient sqs, String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    public List<Message> poll() {
        ReceiveMessageRequest request = ReceiveMessageRequest.builder()
            .queueUrl(queueUrl)
            .maxNumberOfMessages(10)
            .waitTimeSeconds(20)
            .visibilityTimeout(60)
            .messageAttributeNames("All")
            .messageSystemAttributeNames(MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT)
            .build();

        return sqs.receiveMessage(request).messages();
    }
}
~~~

- `maxNumberOfMessages` caps at **10** per `ReceiveMessage` call.
- `waitTimeSeconds` caps at **20 seconds** for long polling.
- `visibilityTimeout` on the request adjusts how long the message stays hidden after receipt.
- An empty list is normal: the queue may simply have no messages.
- Long polling cuts empty receives and polling request volume compared to short polling.

Different SDK versions may expose slightly different overloads/enums for message attributes; match the API of your project's 2.x version.

### 5.2. Processing and DeleteMessage

~~~java
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;

public void handle(Message message) {
    String receiptHandle = message.receiptHandle();

    try {
        processInvoice(message.body());

        sqs.deleteMessage(DeleteMessageRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(receiptHandle)
            .build());
    } catch (RuntimeException failure) {
        // Do not delete message when business operation fails.
        // Message may reappear after visibility timeout.
        throw failure;
    }
}
~~~

`DeleteMessage` requires the current receive's `receiptHandle`, not `messageId`. A receipt handle changes each time a message is received; using an old handle fails to delete the active receipt.

Delete only after the business operation commits successfully. Deleting first and then failing a database transaction loses the message with no retry.

### 5.3. Visibility Timeout and Duplicate Delivery

When SQS returns a message, it temporarily hides the message from other consumers for the **visibility timeout**. If the consumer fails to delete before it expires, the message becomes visible again.

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Worker A
    participant X as Worker B
    Q->>W: Receive message M
    Note over Q: M invisible during visibility timeout
    W->>W: Long-running processing
    Note over Q: Visibility timeout expires
    Q->>X: Message M reappears
    W->>Q: Delete with old receipt handle
    X->>X: May be processing M
~~~

To reduce duplicate processing:

- Set the visibility timeout longer than typical and p99 processing times with margin.
- For long jobs, call **`ChangeMessageVisibility`** to extend the lease.
- Make consumers idempotent by business operation ID.
- Configure a DLQ and `maxReceiveCount` for poison messages.
- Avoid crashing after side effects but before `DeleteMessage` without idempotency protection.

SQS Standard provides **at-least-once delivery**; duplicate deliveries can still occur even with well-tuned visibility timeouts.

## 6. Extending Visibility Timeout for Long Jobs

If invoice processing can take several minutes, the consumer can extend visibility while working:

~~~java
import software.amazon.awssdk.services.sqs.model.ChangeMessageVisibilityRequest;

public void extendVisibility(String receiptHandle, int seconds) {
    sqs.changeMessageVisibility(
        ChangeMessageVisibilityRequest.builder()
            .queueUrl(queueUrl)
            .receiptHandle(receiptHandle)
            .visibilityTimeout(seconds)
            .build()
    );
}
~~~

- A single `visibilityTimeout` update must fall within SQS's **0–43,200 seconds** (12 hours) API limit.
- Total visibility time from initial receipt cannot be extended indefinitely by repeated renewals.
- If jobs regularly exceed allowed durations, split into smaller tasks, use workflow orchestration, or manage application-layer leases/checkpoints.
- Extending too late—after visibility already expired—may leave you without a valid receipt handle to control the message.

Never use visibility timeouts as your sole business distributed lock. Consumers still need idempotency or conditional updates because duplicate deliveries can still happen.

## 7. SQS Batch APIs: Throughput and Partial Failures

When a producer sends many messages, batch APIs cut request counts. SQS batches support up to **10 entries per request**.

### 7.1. Sending a Batch

~~~java
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

var batch = SendMessageBatchRequest.builder()
    .queueUrl(queueUrl)
    .entries(
        SendMessageBatchRequestEntry.builder()
            .id("entry-1")
            .messageBody("{\"orderId\":\"ORDER-1001\"}")
            .build(),
        SendMessageBatchRequestEntry.builder()
            .id("entry-2")
            .messageBody("{\"orderId\":\"ORDER-1002\"}")
            .build()
    )
    .build();

SendMessageBatchResponse response = sqs.sendMessageBatch(batch);

response.successful().forEach(entry ->
    System.out.println("Accepted entry: " + entry.id())
);

response.failed().forEach(entry ->
    System.err.println("Failed entry: " + entry.id() + " - " + entry.code())
);
~~~

A batch HTTP/API call can succeed at the transport level while **individual entries fail**. Always inspect both `successful()` and `failed()`; retry only failed entries after classifying their errors. Retrying the whole batch duplicates entries that already succeeded.

### 7.2. Handling Partial Failures

- Assign unique per-batch entry IDs to map results back to business operations.
- Record failed entry IDs, error codes, and sender fault flags.
- Retry transient failures with backoff.
- Never retry validation or permission errors infinitely.
- Keep an idempotency key in the payload so consumers deduplicate if the producer cannot tell whether a request succeeded.

Batch APIs lower overhead, but are not transactions: entries are not atomic with one another.

## 8. SQS FIFO: Ordering and Deduplication

Use a **FIFO queue** when message ordering must be preserved within a business group, such as all commands for a specific order or customer.

### 8.1. Sending FIFO Messages

~~~java
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

sqs.sendMessage(SendMessageRequest.builder()
    .queueUrl(fifoQueueUrl)
    .messageBody(orderEventJson)
    .messageGroupId("ORDER#10023")
    .messageDeduplicationId("ORDER#10023#PAYMENT#TXN-91")
    .build());
~~~

- FIFO queue names must end with **`.fifo`**.
- `MessageGroupId` defines an ordered group; messages sharing a group are processed in FIFO order.
- Multiple message groups can be processed in parallel.
- `MessageDeduplicationId` deduplicates sends within a **5-minute window**; content-based deduplication can also be enabled on the queue.
- Never put all traffic into a single group ID if high parallelism is required.

### 8.2. FIFO Does Not Guarantee Business Exactly-Once Processing

SQS FIFO handles deduplication and ordering at the queue layer, yet a consumer can still execute a side effect and crash before calling `DeleteMessage`. When the message is redelivered, the side effect can repeat.

Therefore, payment, order, and inventory consumers still need **operation IDs, inbox tables, conditional writes, or provider idempotency keys**. FIFO suppresses duplicate sends within the dedup window and preserves per-group order; it does not replace business transactions.

### 8.3. Standard vs. FIFO?

| Requirement | Standard | FIFO |
| --- | --- | --- |
| Broad throughput / scale | Fits most workloads. | Subject to Region/configuration quotas and throughput modes. |
| Ordering | Best-effort, not guaranteed. | Strict per `MessageGroupId`. |
| Duplicate delivery | Possible. | Deduplicated on send within window; consumer still needs idempotency. |
| Message groups | None. | Supported, allowing parallelism across groups. |
| Use cases | Notifications, independent background jobs. | Commands requiring sequential execution per order/account/aggregate. |

## 9. SQS Dead-Letter Queues and Redrive

A **DLQ** receives messages that fail processing after the configured number of receives/retries on the source queue.

### 9.1. Redrive Policy

A source queue's redrive policy defines:

- **`deadLetterTargetArn`:** ARN of the DLQ.
- **`maxReceiveCount`:** maximum receives before moving the message to the DLQ.

DLQs isolate poison messages so workers do not endlessly burn resources on bad payloads. FIFO source queues require FIFO DLQs; Standard source queues use Standard DLQs.

### 9.2. DLQ Triage Workflow

1. Alert when `ApproximateNumberOfMessagesVisible` on the DLQ climbs.
2. Inspect message and error metadata within authorized permissions.
3. Diagnose whether the cause is schema mismatch, business validation, IAM, dependency outage, or transient failure.
4. Fix the producer, consumer, or bad data as needed.
5. Test a sample message in a safe environment.
6. Run an SQS redrive task / controlled replay or dedicated consumer to reprocess.
7. Reconcile business operation IDs and mark the incident resolved.

Never purge a DLQ merely to reset a dashboard to 0. Messages in a DLQ may represent business data requiring recovery.

### 9.3. SQS Redrive Is Not Infinite Retry

Redrive moves messages back to the source queue or a chosen destination per API/configuration; it does not fix code bugs or IAM permissions by itself. Rate-limit and monitor redrive runs to avoid overwhelming queues or re-triggering side effects.

## 10. SNS: Publishing Messages to Topics

SNS is a **push-based pub/sub** service. Producers publish messages to a topic ARN; SNS delivers them to confirmed, authorized subscriptions. For Standard topics, delivery is at-least-once with best-effort ordering; consumers need idempotency if side effects cannot repeat.

### 10.1. Publishing a Message

~~~java
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.PublishRequest;
import software.amazon.awssdk.services.sns.model.PublishResponse;

public final class OrderEventPublisher {
    private final SnsClient sns;
    private final String topicArn;

    public OrderEventPublisher(SnsClient sns, String topicArn) {
        this.sns = sns;
        this.topicArn = topicArn;
    }

    public String publish(String eventJson) {
        PublishResponse response = sns.publish(
            PublishRequest.builder()
                .topicArn(topicArn)
                .subject("OrderCreated")
                .message(eventJson)
                .build()
        );
        return response.messageId();
    }
}
~~~

A topic ARN encodes its Region and account ID; the client Region must match the topic Region. Callers need `sns:Publish` on that exact topic ARN, and the topic policy must permit it if resource-based restrictions exist.

### 10.2. Message Attributes

Attributes let subscribers filter or classify messages without parsing the entire body.

~~~java
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import java.util.Map;

sns.publish(PublishRequest.builder()
    .topicArn(topicArn)
    .message(eventJson)
    .messageAttributes(Map.of(
        "eventType", MessageAttributeValue.builder()
            .dataType("String")
            .stringValue("OrderCreated")
            .build(),
        "tenantTier", MessageAttributeValue.builder()
            .dataType("String")
            .stringValue("premium")
            .build()
    ))
    .build());
~~~

Message attributes are routing/filtering metadata. Never place credentials, payment secrets, or unnecessary PII in attributes.

### 10.3. Structured Messages

SNS supports JSON-structured messages for protocol-specific payloads. When using that mode, set `MessageStructure = json` and supply valid keys for each target protocol. Do not confuse ordinary business JSON inside `Message` with an SNS structured message envelope.

## 11. SNS Subscriptions, Fan-Out, and Filter Policies

An SNS topic can feed multiple subscriptions: SQS, Lambda, HTTP/S, email, or other service-supported protocols. Each subscription has its own delivery semantics, retries, and permissions.

~~~mermaid
flowchart LR
    APP["Orders service"] --> TOPIC["SNS topic: order-events"]
    TOPIC --> Q1["SQS inventory"]
    TOPIC --> Q2["SQS analytics"]
    TOPIC --> L["Lambda notification"]
    Q1 --> W1["Inventory worker"]
    Q2 --> W2["Analytics worker"]
~~~

### 11.1. SNS → SQS Queue Policy

For SNS to deliver messages to SQS, the queue policy must allow the SNS service principal to call `sqs:SendMessage`, scoped to the specific topic ARN.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSpecificSnsTopic",
      "Effect": "Allow",
      "Principal": {
        "Service": "sns.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-inventory",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
        }
      }
    }
  ]
}
~~~

ARNs in this example are placeholders; use your real topic and queue ARNs. The `aws:SourceArn` condition prevents other topics in the same account from sending unauthorized messages to the queue.

### 11.2. Raw Message Delivery

On SQS subscriptions, you can enable **`RawMessageDelivery`** so SQS receives the raw message body instead of the SNS JSON envelope. Choose based on consumer contract:

- Raw delivery: body is the business payload directly.
- Wrapped delivery: body contains the SNS metadata envelope wrapping the message payload.

Consumers must know the exact format to deserialize properly. Never flip raw delivery mid-flight without versioning consumer contracts.

### 11.3. Filter Policies

Subscription filter policies deliver only messages matching specific attributes or body fields.

Example filtering on message attribute `eventType`:

~~~json
{
  "eventType": ["OrderCreated", "OrderPaid"],
  "tenantTier": ["premium"]
}
~~~

Filter policies can evaluate **message attributes** or **message bodies** depending on subscription configuration. When filtering on the body, JSON structure must stay consistent; schema changes can cause subscribers to stop matching silently.

### 11.4. Subscription Confirmation and Delivery

Some protocols require confirming the subscription or endpoint ownership. For same-account SQS subscriptions, this is typically handled seamlessly when creating the subscription with the right policy; for HTTP/S or cross-account setups, handle confirmation and authorization per protocol.

A successful SNS publish only confirms SNS accepted the message; it does not prove every downstream consumer completed business processing. Monitor delivery failures, SQS backlogs, Lambda errors, and business acknowledgements.

## 12. SNS FIFO and Ordered Fan-Out

SNS supports **FIFO topics** for use cases requiring ordering and deduplication when delivering to **SQS FIFO subscriptions**.

### 12.1. Publishing to a FIFO Topic

~~~java
sns.publish(PublishRequest.builder()
    .topicArn(fifoTopicArn)
    .message(orderEventJson)
    .messageGroupId("ORDER#10023")
    .messageDeduplicationId("ORDER#10023#EVENT#PAID#V4")
    .build());
~~~

- FIFO topic names must end with **`.fifo`**.
- `MessageGroupId` defines the ordered group.
- `MessageDeduplicationId` or content-based deduplication suppresses duplicate publishes within the SNS FIFO deduplication window.
- The SNS FIFO deduplication window is **5 minutes**; this is publish-level deduplication, not an exactly-once business processing guarantee.
- FIFO topics pair with SQS FIFO subscriptions; do not assume every SNS Standard subscription protocol works with FIFO.
- Ordering is guaranteed per message group per service semantics, not globally across all groups.

### 12.2. SNS FIFO and SQS FIFO

To preserve end-to-end ordering, pair a FIFO topic with FIFO queues on each subscriber while keeping the same business grouping key. When consumers process asynchronously, maintain idempotency and error handling so failures do not violate business ordering.

SNS FIFO deduplication does not replace worker idempotency. A consumer can commit a side effect and fail before deleting the message from SQS FIFO.

### 12.3. Controlled Fan-Out

One topic can serve multiple independent subscribers. Inventory can filter `OrderCreated`, Billing receives `OrderPaid`, and Analytics receives both. Each subscriber should own a dedicated queue to:

- Decouple processing speeds and backlogs.
- Maintain a dedicated DLQ.
- Deploy consumers independently.
- Prevent a slow consumer from stalling other consumers.
- Tune retries, retention, and monitoring independently.

## 13. STS: Identifying the Caller

AWS Security Token Service (STS) provides APIs to inspect the current identity and issue temporary credentials.

### 13.1. GetCallerIdentity

~~~java
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.create()) {
    GetCallerIdentityResponse identity = sts.getCallerIdentity();
    System.out.println("Account: " + identity.account());
    System.out.println("ARN: " + identity.arn());
    System.out.println("User ID: " + identity.userId());
}
~~~

`GetCallerIdentity` returns the account, ARN, and user ID of the principal signing the request. This API **requires no IAM permissions**; even if a policy explicitly denies `sts:GetCallerIdentity`, STS still returns identity info per API behavior.

Use this API in diagnostics to confirm whether a workload is running under an ECS task role, EC2 instance profile, or assumed role. Never log full credentials or tokens.

### 13.2. Assumed Role ARN

An assumed-role identity typically has an ARN shaped like:

~~~text
arn:aws:sts::111122223333:assumed-role/OrdersRuntimeRole/orders-api-session
~~~

This differs from the IAM role ARN `iam::...:role/OrdersRuntimeRole`. The STS ARN identifies the active session making the request; the IAM role ARN identifies the role resource being assumed.

## 14. STS AssumeRole: Accessing Another Account or Role

When a service needs permissions in another AWS account, use **`AssumeRole`** to obtain a temporary access key, secret key, and session token. Never copy long-lived access keys from the target account.

### 14.1. Both Sides Must Grant Permission

The caller's **identity policy** must allow `sts:AssumeRole` on the target role ARN. The target role's **trust policy** must trust the caller's account/role and matching conditions.

Example trust policy in the Billing account:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustOrdersRuntime",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/OrdersRuntimeRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Example identity policy attached to `OrdersRuntimeRole`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/BillingReadRole"
    }
  ]
}
~~~

These ARNs are examples. Trust policies can also enforce `ExternalId`, `SourceIdentity`, session tags, and MFA conditions where appropriate.

### 14.2. AssumeRole with Java SDK v2

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;
import software.amazon.awssdk.services.sqs.SqsClient;

StsClient sts = StsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();

AssumeRoleRequest assumeRequest = AssumeRoleRequest.builder()
    .roleArn("arn:aws:iam::444455556666:role/BillingReadRole")
    .roleSessionName("orders-api-billing-read")
    .durationSeconds(3600)
    .build();

StsAssumeRoleCredentialsProvider provider =
    StsAssumeRoleCredentialsProvider.builder()
        .stsClient(sts)
        .refreshRequest(assumeRequest)
        .build();

SqsClient billingSqs = SqsClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(provider)
    .build();
~~~

The provider manages fetching and refreshing temporary credentials as needed. Keep the provider alive alongside the client; on shutdown, close the service client, provider, and STS client according to application lifecycle ownership.

Never call `AssumeRole` once manually and hold those credentials in memory until they expire on long-running workloads. Temporary credentials expire; use a dedicated refreshing provider.

### 14.3. Session Duration and Role Chaining

- `AssumeRole` typically defaults to one hour when duration is omitted.
- Maximum duration depends on the target role's **`MaxSessionDuration`** setting, within STS limits.
- When the caller is already an assumed role and calls `AssumeRole` again (role chaining), the new session is capped at **one hour maximum**.
- When the session expires, the SDK provider refreshes using valid source credentials.

Do not set session durations longer than necessary. Session names should help auditors identify which workload or operation assumed the role, without embedding customer data.

### 14.4. ExternalId and Third-Party Cross-Account Access

When a third-party service accesses a customer account, use **`ExternalId`** in both the trust policy and `AssumeRole` request to mitigate the confused deputy risk. `ExternalId` is not a password and does not replace restricting the `Principal`. Use only the value defined by the integration contract.

### 14.5. Web Identity and Workload Roles

In EKS IRSA or environments supporting web identity, the SDK can use the web identity token file and role ARN through the default credential provider chain. You do not need static keys or manual `AssumeRole` calls when workload identity already supplies the intended role.

For ECS tasks, attach a task role; for EC2, use an instance profile. Use additional `AssumeRole` hops only when crossing a security boundary into a different role is genuinely required.

## 15. Secrets Manager: Fetching Secrets from Java

Secrets Manager stores secret values, metadata, versions, and rotation settings. Applications should retrieve secrets via the SDK using an IAM role and keep them in memory only within the required scope.

### 15.1. Sample Secret JSON

A database secret might look like:

~~~json
{
  "engine": "postgres",
  "host": "orders-db.cluster-example.ap-southeast-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "orders",
  "username": "orders_app",
  "password": "REDACTED"
}
~~~

Values above illustrate structure only. Never store real secrets in lessons, source code, or logs.

### 15.2. GetSecretValue with Java SDK v2

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class SecretReader {
    private final SecretsManagerClient secrets;

    public SecretReader(SecretsManagerClient secrets) {
        this.secrets = secrets;
    }

    public String readSecretString(String secretId) {
        GetSecretValueResponse response = secrets.getSecretValue(
            GetSecretValueRequest.builder()
                .secretId(secretId)
                .versionStage("AWSCURRENT")
                .build()
        );

        if (response.secretString() == null) {
            throw new IllegalStateException("Secret does not contain SecretString");
        }
        return response.secretString();
    }
}
~~~

`secretId` can be a secret name or ARN. In production, use explicit ARNs or managed configuration to avoid reading an identically named secret in another account/Region. `AWSCURRENT` is the standard staging label for the active version.

### 15.3. SecretBinary

Secrets Manager supports `SecretString` or `SecretBinary`. For binary data, the SDK returns `SdkBytes`:

~~~java
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

GetSecretValueResponse response = secrets.getSecretValue(request);

SdkBytes binary = response.secretBinary();
if (binary != null) {
    byte[] bytes = binary.asByteArray();
    // Convert according to application-defined binary format.
}
~~~

Never assume every secret is a JSON string. Inspect response fields before parsing.

### 15.4. Parsing JSON Secrets with Jackson

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public record DatabaseSecret(
    String engine,
    String host,
    int port,
    String dbname,
    String username,
    String password
) {}

ObjectMapper mapper = new ObjectMapper();
DatabaseSecret dbSecret =
    mapper.readValue(secretJson, DatabaseSecret.class);

// Use fields to configure connection factory.
// Never print dbSecret or password to logs.
~~~

Java `record` works on Java 17+. Real implementations must handle missing fields, schema versions, rotation, and parse failures; never assume every key is always present.

## 16. Secrets Manager Caching and Rotation

### 16.1. Why Cache?

If every HTTP request calls `GetSecretValue`, the application will:

- Increase API calls and latency.
- Depend on Secrets Manager availability for every single request.
- Increase costs under high workloads.
- Risk burst throttling when many instances start simultaneously.

In-memory caching reduces repeated requests. You can use the **AWS Secrets Manager Java caching client** or an application-managed TTL cache. Verify the caching library's lifecycle/version, SDK compatibility, thread safety, refresh interval, and eviction behavior before deploying.

### 16.2. Caches Need TTLs and Refresh Strategies

- Never cache secrets indefinitely.
- Pick a refresh interval aligned with the rotation schedule and availability targets.
- Add jitter so multiple instances do not refresh at the exact same instant.
- Never log cache contents or exception messages that could expose secrets.
- When database authentication fails due to credential rotation, call `refreshNow` on the caching client v2 (if using that library) or refresh your application-managed cache, then perform a bounded retry.
- Never retry infinitely with an old password.

Example using caching client v2 to force-refresh a secret after an authentication failure:

~~~java
import com.amazonaws.secretsmanager.caching.SecretCache;

try (SecretCache cache = new SecretCache()) {
    String current = cache.getSecretString(secretArn);
    // Use current to create credentials/connections per app config.

    boolean refreshed = cache.refreshNow(secretArn);
    if (!refreshed) {
        throw new IllegalStateException("Could not refresh secret");
    }
    String rotated = cache.getSecretString(secretArn);
}
~~~

A long cache TTL reduces API calls at the cost of holding stale credentials longer after rotation. A cache implementation is not a hardened vault; minimize secret residency in memory, protect heap dumps, and never log values. Document this trade-off in security reviews.

### 16.3. Rotation Lifecycle

Secrets Manager rotation typically uses a Lambda rotation function and staging labels:

- **`AWSCURRENT`:** active version applications should use.
- **`AWSPENDING`:** version currently undergoing rotation.
- **`AWSPREVIOUS`:** prior version, if any.

A standard rotation flow creates the pending secret, updates the target database credential, tests the new credential, and promotes it to `AWSCURRENT`. Exact steps depend on the rotation template and target service.

~~~mermaid
sequenceDiagram
    participant SM as Secrets Manager
    participant L as Rotation Lambda
    participant DB as RDS / Database
    participant APP as Java application
    SM->>L: Create pending secret
    L->>DB: Set new credential
    L->>DB: Test new credential
    L->>SM: Promote AWSCURRENT
    APP->>SM: GetSecretValue AWSCURRENT
    SM-->>APP: Current secret version
    APP->>DB: Connect with refreshed credential
~~~

### 16.4. Database Connection Pools and Rotation

When a database password rotates:

- Existing connections may keep working until closed or until the server revokes sessions.
- The connection pool may keep opening new connections with old credentials if the secret cache has not refreshed yet.
- The application must coordinate secret refreshes with the HikariCP/`DataSource` lifecycle.
- With RDS Proxy and Secrets Manager, configure rotation/authentication per service documentation; the proxy can use the secret to open backend connections.
- Test rotation under live traffic, warm pools, and horizontal scaling.

Do not restart the entire service on every rotation when controlled refresh is possible, but also never retain stale credentials indefinitely.

## 17. IAM and Security Across the Four Services

### 17.1. Least Privilege by Workload

| Workload | Typical Needed Actions | Resource Scope |
| --- | --- | --- |
| SQS producer | `sqs:SendMessage`; optionally `SendMessageBatch`. | Specific queue ARN. |
| SQS consumer | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `GetQueueAttributes` if needed. | Specific queue ARN. |
| SNS publisher | `sns:Publish`. | Specific topic ARN. |
| STS caller | `sts:AssumeRole`. | Specific target role ARN. |
| Secrets reader | `secretsmanager:GetSecretValue`; `DescribeSecret` if metadata needed. | Specific secret ARN. |
| KMS-backed secret reader | `kms:Decrypt` on the matching key if encrypted with a CMK. | Specific KMS key ARN. |

Never grant `sqs:*` or `secretsmanager:*` across all resources for a single use case.

### 17.2. Identity Policies and Resource Policies

For a request to succeed, evaluate:

- The caller's IAM identity policy.
- Queue/topic/secret resource policies where used.
- Role trust policies for `AssumeRole`.
- Permissions boundaries and AWS Organizations SCPs.
- KMS key policies when encrypted with a customer-managed key.
- VPC endpoint policies when traffic crosses an interface/gateway endpoint.

**Explicit Deny overrides Allow.** An IAM `Allow` on an application role cannot bypass an explicit `Deny` in an SCP, resource policy, or KMS policy.

### 17.3. SQS Queue Policy

A queue policy is typically needed when:

- SNS delivers messages to SQS.
- Another AWS account sends or receives messages.
- An AWS service principal needs send permissions.
- Producers should be restricted by source ARN or source account.

For SNS → SQS, scope `aws:SourceArn` to the exact topic. For cross-account access, pair the identity policy in the sender account with the resource policy in the queue-owner account.

### 17.4. SNS Topic Policy

An SNS topic policy can authorize cross-account publishers or AWS services. Specify the exact `Principal` and `sns:Publish` on the target topic ARN; when integrating AWS services, add service-recommended condition keys to prevent confused deputy attacks.

### 17.5. Secrets Manager and KMS

- Secrets Manager encrypts secrets at rest by default using an AWS managed key or configured key.
- With a customer-managed KMS key, the principal needs decrypt permissions and the key policy must allow access.
- Cross-account secret access requires alignment across identity policy, secret resource policy, and CMK policy.
- Never disable or delete a KMS key while secrets still rely on it.
- Never emit secret values into CloudWatch, traces, exception telemetry, or support tickets.

### 17.6. VPC Endpoints and Private Connectivity

Workloads in private subnets can use VPC endpoints to call AWS APIs without traversing the public internet:

- SQS interface VPC endpoint.
- SNS interface VPC endpoint.
- STS interface VPC endpoint.
- Secrets Manager interface VPC endpoint.

Verify endpoint service names, private DNS, subnet/AZ coverage, endpoint security groups, routes/DNS, and endpoint policies. VPC endpoints do not bypass IAM; requests must still be authorized.

## 18. Retries, Timeouts, and Errors in AWS SDK for Java 2.x

### 18.1. Classifying Errors

| Error Group | Examples | Handling |
| --- | --- | --- |
| **Service exception** | `AccessDenied`, `ResourceNotFound`, `InvalidParameter`, throttling. | Read error code/status/request ID; fix permissions/config or retry if transient. |
| **Client/transport exception** | DNS, socket timeout, TLS, connection reset. | Check network, endpoint, proxy, DNS, and timeouts. |
| **Business failure** | Duplicate operation, invalid state, invalid message schema. | Handle at the application layer; do not retry blindly. |
| **Partial batch failure** | Certain entries in a batch failed. | Retry only failed entries after error classification. |

SDK service exceptions typically extend `AwsServiceException`; client/network failures are `SdkClientException`. Service exceptions supply status codes, error details, and request IDs invaluable for support and diagnostics.

### 18.2. Retry Strategy

AWS SDK for Java 2.x has built-in retry strategies. Use standard SDK behavior for retryable faults; tune max attempts and backoff when workloads have explicit requirements.

Never retry permanent configuration faults such as `AccessDenied` or validation errors. For throttling and transient service errors, use backoff with jitter to curb retry storms.

### 18.3. Retries and Duplicate Side Effects

Suppose SQS accepts `SendMessage` while the response is lost to a network timeout. The SDK or app may resend; the producer cannot tell if the earlier request succeeded.

Similarly, SNS `Publish` may have been accepted before the client timed out. Therefore:

- Include a stable business event ID.
- Deduplicate at the consumer.
- Never treat the SQS/SNS `messageId` as a business idempotency key.
- For payments or third-party APIs, pass the downstream system's idempotency key.
- Persist outcomes by operation ID for reconciliation.

### 18.4. API Call Timeout and Attempt Timeout

Configure attempt timeouts to bound a single request and call timeouts to cap total time across retries. For SQS long polling, read/socket timeouts must exceed the queue wait time. For Secrets Manager/STS, timeouts must account for cold starts, networking, and refresh cadences.

Do not apply one identical timeout to every service without considering semantics. A 20-second `ReceiveMessage` long poll behaves very differently from `GetCallerIdentity` or `GetSecretValue`.

## 19. Observability and Operations

### 19.1. SQS Metrics

Useful CloudWatch metrics:

- **`ApproximateNumberOfMessagesVisible`:** backlog waiting to be received.
- **`ApproximateNumberOfMessagesNotVisible`:** messages hidden/in-flight.
- **`ApproximateAgeOfOldestMessage`:** age of the oldest queued message.
- **`NumberOfMessagesSent`/`Received`/`Deleted`:** producer/consumer throughput trends.
- **`NumberOfEmptyReceives`:** receives returning no messages.
- **`ApproximateNumberOfMessagesDelayed`:** messages currently delayed.

Metric names start with `Approximate` because counts are approximate. Low queue depth does not prove consumers succeeded on business operations; pair with application success/error metrics.

### 19.2. SNS Metrics

Monitor `NumberOfMessagesPublished`, `NumberOfNotificationsDelivered`, `NumberOfNotificationsFailed`, and delivery failures per protocol/subscriber. A successful publish does not guarantee every endpoint received or processed the message.

### 19.3. STS and Secrets Manager Auditing

- CloudTrail logs AWS API calls such as `AssumeRole`, `GetSecretValue`, and control-plane actions.
- Standard audit events never contain secret values, yet audit logs still need protection.
- Monitor `AccessDenied`, unexpected role assumptions, principal/account/Region patterns, and secret access patterns.
- Alert when workloads fetch secrets abnormally frequently or from unexpected Regions/accounts.

### 19.4. Application Metrics

Record:

- SQS publish successes/failures and batch partial failures.
- Queue receive counts, processing duration, and delete outcomes.
- Duplicate operation counts and idempotency hit rates.
- SNS publish successes/failures and subscriber backlogs.
- STS `AssumeRole` refresh failures and caller identity changes.
- Secret refresh age, cache hit/miss ratios, and authentication failures.

Never log message bodies containing PII or secrets just to debug. Log correlation IDs, operation IDs, AWS request IDs, and error codes.

## 20. Read-Only AWS CLI: Inspecting Queues, Topics, Roles, and Secret Metadata

The commands below only read state or configuration; they do not send messages, publish events, assume roles, or retrieve secret values.

### 20.1. Caller Identity

~~~bash
aws sts get-caller-identity
~~~

Verifies the account, ARN, and UserId of the active AWS credentials.

### 20.2. SQS Queue Metadata

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-invoice \
  --attribute-names All \
  --region ap-southeast-1
~~~

Inspects `VisibilityTimeout`, `ReceiveMessageWaitTimeSeconds`, `RedrivePolicy`, `QueueArn`, `ApproximateNumberOfMessages`, and encryption settings when returned. Queue URL is a placeholder.

### 20.3. SNS Topic and Subscriptions

~~~bash
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1

aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1
~~~

Checks topic policies, encryption, delivery status settings, and endpoint subscriptions. Never rely on `list-subscriptions` to conclude subscribers processed messages cleanly.

### 20.4. Role Metadata

~~~bash
aws iam get-role \
  --role-name BillingReadRole
~~~

`GetRole` reads trust policies and role metadata. To inspect attached/inline policies, use the appropriate IAM list/get APIs within your permissions. You do not need to assume a role just to check caller identity.

### 20.5. Secrets Manager Metadata

~~~bash
aws secretsmanager describe-secret \
  --secret-id arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:orders/database-EXAMPLE \
  --region ap-southeast-1
~~~

`DescribeSecret` returns metadata, rotation settings, KMS key ARN, and version staging labels per permissions; it never returns the secret value. **Never run `get-secret-value` in shared terminals or public logs**, as the output prints live credentials.

## 21. Testing Java Applications

### 21.1. Unit Tests

Mock service clients or wrap them behind application interfaces to verify:

- SQS publisher sets the right queue URL, body, and message attributes.
- Consumer calls `DeleteMessage` only after business processing succeeds.
- Batch publisher handles `successful()` and `failed()` entries separately.
- SNS publisher sends to the right topic ARN with matching message attributes.
- STS provider is configured with the right role ARN and session name.
- Secrets parser handles `SecretString`/`SecretBinary` and missing fields.

Unit tests do not prove IAM or resource policies on live AWS are valid.

### 21.2. Integration Tests in a Sandbox

Use a dedicated test AWS account and Region:

1. Provision SQS Standard/FIFO queues and DLQs via IaC.
2. Provision SNS topics/subscriptions and queue policies.
3. Provision IAM roles and trust policies for STS `AssumeRole`.
4. Provision synthetic test secrets containing no production credentials.
5. Run producers and consumers with deterministic operation IDs.
6. Test visibility timeouts, duplicates, redrive, and SNS filter policies.
7. Test rotation and cache refresh in a controlled environment.
8. Tear down resources afterward and monitor costs.

LocalStack or service mocks provide fast developer feedback, yet do not replace live AWS integration tests for IAM, STS, KMS, SNS delivery, and service-specific semantics.

### 21.3. Testing Failure Paths

- SQS `AccessDenied` or wrong queue URL.
- SNS topic ARN in the wrong Region.
- Consumer crash before `DeleteMessage`.
- SQS message exceeding visibility timeout and redelivering.
- STS `AssumeRole` denied by trust policy.
- Temporary credentials expiring.
- Secret version rotating while a connection pool still holds stale credentials.
- KMS key policy denying decrypt.
- VPC endpoint policy blocking requests.

## 22. Cost and Architectural Choices

| Service | Cost Factors to Watch |
| --- | --- |
| **SQS** | Requests, payload/request units, FIFO usage, DLQ storage, and data transfer per pricing. |
| **SNS** | Publish/delivery requests, protocol charges, payloads, and delivery retries. |
| **STS** | API usage/quotas and operational overhead; never call `AssumeRole` per message when a provider can refresh/reuse. |
| **Secrets Manager** | Stored secrets count, API calls, rotation Lambdas, and KMS requests. |
| **CloudWatch** | Metrics, alarms, dashboards, logs, and data ingestion. |
| **VPC endpoints** | Hourly endpoint fees and data processing charges per Region. |
| **KMS** | Customer-managed key storage and cryptographic API requests. |

Never assume all API calls are free or priced identically across Regions. Use the AWS Pricing Calculator and Cost Explorer for current rates.

### 22.1. Reducing Cost While Preserving Resilience

- Use SQS long polling and batch APIs where appropriate.
- Avoid rapid short polling on empty queues.
- Set retention and DLQ lifecycles to match business needs.
- Use SNS fan-out rather than having producers call many consumers directly when appropriate.
- Cache secrets with sensible TTLs instead of calling `GetSecretValue` on every request.
- Reuse STS credentials providers and AWS service clients.
- Monitor retries, duplicate processing, and poison messages.
- Limit log payload sizes and CloudWatch retention.

## 23. Runbook: Common Failures

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| SQS `SendMessage` `AccessDenied` | IAM identity/queue policy lacks `sqs:SendMessage`, endpoint policy denies. | Caller ARN, queue ARN, IAM policies, CloudTrail. |
| Wrong SQS queue URL | URL belongs to another account/Region or queue changed. | `GetQueueUrl` / queue metadata in the right Region. |
| Duplicate messages | At-least-once delivery, timeout, consumer crash before delete, expired visibility. | `ApproximateReceiveCount`, operation ID, consumer logs. |
| Message never disappears | Delete used an old receipt handle or wrong queue URL. | Receipt handle from the latest receive and delete response. |
| FIFO messages stalled | Earlier message in the same group not yet processed/deleted. | `MessageGroupId`, visibility, DLQ, and consumer status. |
| SNS publish `AccessDenied` | Missing `sns:Publish` or topic policy restriction. | Topic ARN, caller identity, policies, and Region. |
| SNS fails to deliver to SQS | Queue policy missing `sqs:SendMessage` for SNS or wrong `SourceArn`. | Subscription status, queue policy, delivery metrics. |
| Filter policy misses events | Attribute/body format or filter scope mismatch. | Message attributes, filter policy scope, and JSON shape. |
| STS `AssumeRole` `AccessDenied` | Caller policy or role trust policy denies. | Principal, target role ARN, external ID, SCPs, and CloudTrail. |
| STS credentials expired | Non-refreshing provider or expired source credentials. | Provider lifecycle, role duration, and source identity. |
| Secrets Manager `AccessDenied` | Missing `GetSecretValue`, secret resource policy, or KMS decrypt. | Secret ARN, IAM, resource policy, and key policy. |
| Stale secret after rotation | Cache TTL or connection pool has not refreshed. | `AWSCURRENT` version stage, cache age, and new connection test. |
| Secrets Manager timeout | VPC endpoint/DNS/SG/networking issue or throttling. | Endpoint, private DNS, retry metrics, and Region. |

### 23.1. Diagnostic Order

1. Confirm the target account, Region, and resource ARN/URL.
2. Call `GetCallerIdentity` to verify the active principal.
3. Distinguish identity policies, resource policies, trust policies, and KMS key policies.
4. Read the error code, HTTP status, and AWS request ID.
5. Inspect CloudTrail, CloudWatch metrics, and resource status.
6. Test a minimal request in a sandbox.
7. Retry only transient failures; never retry `AccessDenied` or validation errors endlessly.

## 24. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "SDK 2.x uses package `com.amazonaws`." | SDK 2.x uses `software.amazon.awssdk`; `com.amazonaws` is typically SDK 1.x or certain auxiliary libraries. |
| "Create a new `SqsClient` per request." | Clients are thread-safe; reuse them and close at application shutdown. |
| "Client Region automatically finds queues in other Regions." | Client Region sets the endpoint; resource ARNs/URLs must match that Region. |
| "SQS `SendMessage` returning a `messageId` means the message was processed." | It only confirms SQS accepted the message; consumers still have to process it. |
| "SQS Standard is exactly-once." | Standard is at-least-once; duplicates can occur. |
| "FIFO means consumers never re-run side effects." | FIFO handles queue-level dedup/ordering; consumers still need idempotency. |
| "You can `DeleteMessage` using `messageId`." | You must pass the current receive's `receiptHandle`. |
| "Batch APIs are transactions." | Batch entries can partially succeed and partially fail. |
| "Visibility timeout is a distributed lock." | It only hides messages temporarily; it does not replace idempotency/coordination. |
| "SNS publish success means all subscribers finished processing." | SNS acceptance/delivery is distinct from downstream business processing. |
| "SNS topic policy replaces the queue policy." | SNS → SQS requires a queue policy allowing the SNS service principal to send. |
| "`GetCallerIdentity` requires `sts:GetCallerIdentity` permission." | The API requires no IAM permissions per STS behavior. |
| "`AssumeRole` credentials live forever." | Temporary credentials expire; use a refreshing provider. |
| "Role chaining can request a 12-hour session." | Role chaining is capped at a 1-hour maximum session. |
| "Secrets Manager cache can hold secrets forever." | Caches need TTLs, refreshes, and rotation-aware handling. |
| "`DescribeSecret` returns the password." | `DescribeSecret` returns metadata; `GetSecretValue` retrieves the secret value. |
| "IAM `GetSecretValue` alone suffices for CMK-encrypted secrets." | You also need `kms:Decrypt` and an allowing KMS key policy. |
| "Retrying every SDK error is safe." | `AccessDenied`, validation, and business errors should not be retried blindly. |
| "VPC endpoints bypass IAM." | Endpoints provide a private network path; IAM, resource, and KMS policies still apply. |
| "Logging messages/secrets makes debugging easier." | That leaks PII and credentials; log redacted IDs, metadata, and error codes. |

## 25. Practice Exercises with Suggested Answers

### Exercise 1 — Choosing a Service for Background Invoicing

**Prompt:** Orders API must hand invoice generation off to a worker. The worker can take several minutes, needs retries, and must not block HTTP requests.

**Answer:** Use **SQS** to buffer and decouple producer from consumer. Set an appropriate visibility timeout, DLQ, and idempotency key tied to the order/payment operation. SNS is only needed if the same event must fan out to multiple independent subscribers.

### Exercise 2 — Fan-Out OrderCreated

**Prompt:** When an order is created, Inventory, Analytics, and Notification all need notifications while processing at different speeds.

**Answer:** Publish one message to an **SNS topic** with separate subscriptions per consumer, backing each subscription with its own SQS queue to buffer and isolate backlogs. Add a queue policy allowing the SNS principal scoped with `aws:SourceArn` to the exact topic.

### Exercise 3 — SQS Message Processed Twice

**Prompt:** A worker creates an invoice successfully, then crashes before calling `DeleteMessage`. After the visibility timeout, the message reappears.

**Answer:** This is expected at-least-once duplicate delivery. Consumers need a business operation ID and a transactional inbox or unique constraint so a second invoice is never created. Call `DeleteMessage` only after the business transaction commits.

### Exercise 4 — ReceiveMessage Returns an Empty List

**Prompt:** A worker long-polls for 20 seconds and gets an empty list.

**Answer:** This is normal whenever the queue receives no messages during the wait window. Do not treat an empty list as an error; let the worker continue polling on its normal cadence.

### Exercise 5 — Batch SendMessage Partial Failure

**Prompt:** A `SendMessageBatch` call sends 10 entries; the response lists 8 successful and 2 failed.

**Answer:** Retry only the 2 failed entries after classifying their error codes. Never resend the entire batch, or the 8 successful entries will be duplicated. Batch APIs are not transactional.

### Exercise 6 — FIFO Messages Stalled

**Prompt:** One message for `ORDER#10023` takes a long time; subsequent messages in the same group are not picked up by other workers.

**Answer:** FIFO enforces strict ordering within each `MessageGroupId`. Check visibility timeout, consumer processing, and DLQs. Never assign one global group ID across all orders if parallel processing across orders is desired.

### Exercise 7 — DLQ Growing Steadily

**Prompt:** A DLQ accumulates thousands of messages right after deploying a new consumer release.

**Answer:** Pause any automated redrive, inspect schemas, exceptions, and `ApproximateReceiveCount` to locate the common error. Roll back or fix the consumer, validate one message in a sandbox, then rate-limit redrive and reconcile operation IDs.

### Exercise 8 — SNS Publish Succeeds Yet SQS Receives Nothing

**Prompt:** SDK publish returns a `messageId`, yet the inventory queue stays empty.

**Answer:** Check subscription status, whether the queue policy grants `sqs:SendMessage` to `sns.amazonaws.com`, whether `aws:SourceArn` matches the topic ARN, and whether topic and queue share a Region or have valid cross-account policies. Publish success does not prove consumer delivery.

### Exercise 9 — Filter Policy Drops Events

**Prompt:** An SNS filter policy matches `eventType = OrderPaid`, yet the consumer receives nothing because the producer sends `event_type`.

**Answer:** Attribute names are exact and must match the policy. Check whether the filter scope targets message attributes or the message body, plus field names, data types, and JSON shape.

### Exercise 10 — STS AssumeRole AccessDenied

**Prompt:** `OrdersRuntimeRole` has `sts:AssumeRole`, yet still gets denied when assuming `BillingReadRole`.

**Answer:** Inspect both the caller's identity policy and `BillingReadRole`'s trust policy. Then verify SCPs, permissions boundaries, explicit `Deny` statements, `ExternalId`/conditions, and exact role ARN/account.

### Exercise 11 — Role Chaining

**Prompt:** A service already running under an assumed role attempts to assume a second role requesting a 4-hour session.

**Answer:** Role chaining caps the new session at a maximum of one hour. Restructure the source credentials or role chain appropriately; never assume the target role's `MaxSessionDuration` overrides the chaining cap.

### Exercise 12 — GetCallerIdentity Under Explicit Deny

**Prompt:** An IAM policy contains an explicit `Deny` on `sts:GetCallerIdentity`; operations wants to confirm the caller ARN.

**Answer:** `GetCallerIdentity` requires no permissions and still returns identity per STS semantics. Use it for diagnostics, without logging access keys or session tokens.

### Exercise 13 — Secret Rotated Yet App Still Uses Old Password

**Prompt:** A database secret rotated `AWSCURRENT` to a new version, yet some ECS tasks keep connecting with the old credential.

**Answer:** Inspect cache TTL/refresh logic, task startup settings, and the HikariCP connection lifecycle. Design controlled cache refreshes and new connection creation; never log secrets to debug.

### Exercise 14 — Secrets Manager AccessDenied with CMK

**Prompt:** A role has `secretsmanager:GetSecretValue`, yet receives `AccessDenied` on a secret encrypted with a customer-managed KMS key.

**Answer:** Beyond secret permissions, verify `kms:Decrypt` identity permissions, the KMS key policy/grants, and any explicit `Deny` or SCP. For cross-account access, check both the secret resource policy and the CMK policy.

### Exercise 15 — Long Polling Timeout

**Prompt:** `ReceiveMessage` sets `WaitTimeSeconds=20`, while the HTTP read timeout is only 5 seconds.

**Answer:** The client times out before the long poll completes. Configure the HTTP read timeout larger than `WaitTimeSeconds` plus network margin, and ensure `apiCallTimeout` is sufficient as well.

### Exercise 16 — AWS Client Created on Every Request

**Prompt:** A Spring controller builds a new `SqsClient` on every HTTP request without closing it.

**Answer:** This is a broken lifecycle causing overhead and resource leaks. Define a singleton bean, reuse the thread-safe client, and close it at application shutdown.

### Exercise 17 — Client Region Does Not Match Topic

**Prompt:** The SNS topic resides in `ap-southeast-1`, yet `SnsClient` targets the `ap-northeast-1` endpoint.

**Answer:** Build the client in the topic's Region or design explicit cross-Region routing. Never pass one Region's topic ARN to another Region's endpoint expecting the SDK to reroute automatically.

### Exercise 18 — Retry Causes Duplicate Publish

**Prompt:** SNS accepted `Publish`, then the response timed out; the producer retried and subscribers received two messages.

**Answer:** Embed a stable business event ID in the payload, deduplicate in consumers, and consider SNS FIFO when publish ordering/deduplication fits. Never rely on transport `messageId` to identify duplicate business operations.

## 26. Self-Check Questions

**Question 1.** What is the primary package for AWS SDK for Java 2.x?  
**Answer:** `software.amazon.awssdk`.

**Question 2.** How does the BOM help Maven and Gradle?  
**Answer:** Aligns compatible versions centrally across AWS SDK service modules.

**Question 3.** Where should a production ECS task obtain credentials?  
**Answer:** From its IAM task role via the default credentials provider chain.

**Question 4.** Are AWS SDK synchronous service clients thread-safe?  
**Answer:** Yes; reuse clients instead of instantiating one per request.

**Question 5.** Does `SqsClient`'s Region automatically locate a queue in another Region?  
**Answer:** No. Client Region selects the endpoint; configure the exact Region hosting the resource.

**Question 6.** How many messages at most can SQS `ReceiveMessage` return in one call?  
**Answer:** 10.

**Question 7.** What is the maximum wait time in seconds for SQS long polling?  
**Answer:** 20 seconds.

**Question 8.** Which field does SQS `DeleteMessage` require?  
**Answer:** The `ReceiptHandle` from the current receive call.

**Question 9.** Does SQS Standard provide exactly-once delivery?  
**Answer:** No; Standard is at-least-once and duplicates can happen.

**Question 10.** What does the visibility timeout do?  
**Answer:** Temporarily hides a received message so the consumer has time to process it.

**Question 11.** Why do consumers still need idempotency?  
**Answer:** Messages can be redelivered after worker crashes, timeouts, or failed deletes.

**Question 12.** Are SQS batch APIs atomic?  
**Answer:** No; responses can mix successful and failed entries.

**Question 13.** Within what scope is FIFO ordering guaranteed?  
**Answer:** Within the same `MessageGroupId`.

**Question 14.** How long is FIFO `MessageDeduplicationId`'s window?  
**Answer:** 5 minutes.

**Question 15.** How do messages move to a DLQ?  
**Answer:** Via the source queue's redrive policy and `maxReceiveCount`.

**Question 16.** What pattern does SNS fit best?  
**Answer:** Pub/sub fan-out to multiple subscribers.

**Question 17.** Does a successful SNS publish prove subscribers finished processing?  
**Answer:** No; monitor delivery and downstream business processing separately.

**Question 18.** Which queue policy is required for SNS to deliver to SQS?  
**Answer:** A queue resource policy permitting `sns.amazonaws.com` to call `sqs:SendMessage`, typically scoped with `aws:SourceArn`.

**Question 19.** What does `RawMessageDelivery` change?  
**Answer:** The SQS subscriber receives the raw payload body rather than the SNS JSON envelope.

**Question 20.** Which subscription protocol commonly pairs with SNS FIFO?  
**Answer:** SQS FIFO subscriptions per SNS FIFO capabilities.

**Question 21.** What does STS `GetCallerIdentity` return?  
**Answer:** Account, ARN, and UserId of the caller.

**Question 22.** Does `GetCallerIdentity` require `sts:GetCallerIdentity` permission?  
**Answer:** No.

**Question 23.** Which permissions are needed for `AssumeRole`?  
**Answer:** Caller identity policy allowing `sts:AssumeRole` and target role trust policy allowing the principal and conditions.

**Question 24.** What is the maximum session duration for role chaining?  
**Answer:** One hour.

**Question 25.** Why use `StsAssumeRoleCredentialsProvider`?  
**Answer:** It automatically manages fetching and refreshing temporary credentials for the client.

**Question 26.** Which Secrets Manager API retrieves the secret value?  
**Answer:** `GetSecretValue`.

**Question 27.** Does `DescribeSecret` return the password?  
**Answer:** No; it returns metadata/configuration. `GetSecretValue` returns the secret value.

**Question 28.** How do `SecretString` and `SecretBinary` differ?  
**Answer:** One holds a string value; the other holds binary bytes via SDK `SdkBytes`.

**Question 29.** When a secret uses a customer-managed KMS key, what extra permission is typically needed?  
**Answer:** `kms:Decrypt` alongside an allowing key policy or grant.

**Question 30.** What is `AWSCURRENT`?  
**Answer:** The staging label identifying the current active secret version.

**Question 31.** What is the risk of caching a secret forever?  
**Answer:** The application keeps using stale credentials after rotation.

**Question 32.** Do VPC endpoints bypass IAM authorization?  
**Answer:** No; endpoints only provide the network path—IAM, resource, and KMS policies still apply.

**Question 33.** How do SDK service exceptions differ from client exceptions?  
**Answer:** Service exceptions reflect errors returned by AWS services; client exceptions typically involve transport, configuration, or networking.

**Question 34.** Should `AccessDenied` be retried indefinitely?  
**Answer:** No; fix permissions, policies, or configuration first.

**Question 35.** Why do SQS/SNS payloads need a business event ID?  
**Answer:** So consumers can deduplicate and process idempotently when publishes or retries create duplicates.

## 27. Summary and Production Checklist

### 27.1. Remembering Each Service's Role

- **SQS:** pull-based queue, backlog buffering, visibility timeouts, retries, and DLQs.
- **SNS:** pub/sub fan-out, subscriptions, filter policies, and FIFO topics for per-group ordering.
- **STS:** identifies caller identity and issues temporary credentials via `AssumeRole`.
- **Secrets Manager:** stores, distributes, encrypts, and rotates secrets.

### 27.2. Pre-Production Checklist

1. Use the **AWS SDK for Java 2.x BOM** with all modules aligned on an approved release version.
2. Create thread-safe singleton clients in the right Region and manage shutdown cleanly.
3. Use IAM roles and the default credentials provider chain; never hardcode long-term access keys.
4. Set appropriate API attempt/call timeouts; ensure HTTP read timeout exceeds SQS long-polling wait time.
5. For SQS, configure visibility timeouts, long polling, DLQs, and redrive policies.
6. Design consumer idempotency, operation IDs, and transaction boundaries before calling `DeleteMessage`.
7. For batch APIs, handle partial failures and retry only failed entries.
8. For FIFO, pick `MessageGroupId` per aggregate and never mistake queue deduplication for business exactly-once.
9. For SNS, verify topic ARN/Region, subscription status, filter policies, and queue policies.
10. For STS, review identity policies, trust policies, `ExternalId`/conditions, session duration, and role chaining.
11. For Secrets Manager, scope `GetSecretValue` to specific secret ARNs, KMS decrypt, and cross-account policies.
12. Set cache TTL/refresh strategies aligned with rotation; coordinate connection pools and never log secrets.
13. Use VPC endpoints, private DNS, and endpoint policies for private-subnet workloads.
14. Monitor CloudWatch metrics, CloudTrail audits, AWS request IDs, and business outcomes.
15. Test `AccessDenied`, throttling, timeouts, duplicate delivery, DLQs, role expiration, and secret rotation in a sandbox.
16. Estimate SQS, SNS, Secrets Manager, CloudWatch, KMS, and VPC endpoint costs per Region.

**Conclusion:** AWS SDK for Java 2.x lets applications invoke SQS, SNS, STS, and Secrets Manager through a consistent API, yet safe operations depend on how you manage credentials, Regions, IAM/resource policies, retries, and message semantics. Treat SQS/SNS as delivery systems capable of retries, STS as a source of temporary identities, and Secrets Manager as a rotating credential store. Combining idempotency, cache refreshes, observability, and integration testing enables Java services to integrate with AWS reliably without leaking secrets or creating duplicate side effects.

### Official AWS Documentation

- [AWS SDK for Java 2.x Developer Guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html) — setup, credentials, Regions, clients, and retries.
- [Set up the AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup.html) — Maven/Gradle and BOM.
- [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — how the SDK resolves credentials.
- [Configure service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/client-configuration.html) — HTTP clients, timeouts, and lifecycles.
- [Amazon SQS Java examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sqs.html) — sending, receiving, and managing queues.
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) — message processing and duplicate delivery.
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html) — redrive policies and DLQs.
- [SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html) — ordering and deduplication.
- [Amazon SNS Java examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-sns.html) — publishing and subscriptions.
- [SNS FIFO topics](https://docs.aws.amazon.com/sns/latest/dg/fifo-topics.html) — ordering and deduplication.
- [SNS message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html) — subscription filter policies.
- [SNS to SQS fan-out](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html) — queue policies and delivery.
- [AWS STS AssumeRole](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — temporary credentials and role chaining.
- [STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — caller identity.
- [AWS SDK for Java 2.x STS credentials provider](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html) — assume-role provider.
- [Secrets Manager Java retrieval](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_java.html) — retrieving secrets from Java.
- [Secrets Manager caching](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html) — caching secrets in Java.
- [Secrets Manager rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html) — rotation lifecycle and staging labels.
- [Secrets Manager IAM policies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_iam-policies.html) — identity and resource permissions.


