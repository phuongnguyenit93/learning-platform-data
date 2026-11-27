# Publishing Notifications with SnsTemplate and Message Attributes

## 1. Real-World Problem

An e-commerce system written in Spring Boot emits **ORDER_CREATED**, **ORDER_PAID**, and **ORDER_CANCELLED** events. The email service only cares about **ORDER_CREATED**; the refund service cares about **ORDER_CANCELLED**; the analytics service needs to receive all three. If the publisher calls each service directly, every change in recipients can force source code changes.

**Amazon Simple Notification Service (SNS)** solves the distribution problem using **topics** and **subscriptions**. The application sends one message to a topic; SNS evaluates each subscription's policy and forwards the message to matching endpoints. With Spring Boot, **Spring Cloud AWS SnsTemplate** provides a Spring Messaging-style API to publish payloads and attach **message attributes**.

This lesson is part of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing connecting Spring Boot with AWS managed services, applying identity configuration, access permissions, messaging, secret protection, and integration testing. From the AWS example, learners can compare pub/sub concepts, routing metadata, and access permissions with corresponding solutions on Azure and Google Cloud. The focus here is **publishing notifications with SnsTemplate and message attributes** in the **Amazon SNS and SES** chapter.

**After this lesson, you should be able to:**

1. Add the SNS starter and configure the topic ARN, region, and AWS identity for a Spring Boot application.
2. Use **SnsTemplate** to send strings, JSON objects, and Spring Messaging **Message** instances.
3. Attach properly typed **message attributes** and create corresponding **subscription filter policies**.
4. Explain the difference between payload, message attributes, Spring headers, and SNS metadata.
5. Test the publishing path, handle errors, and determine when to drop down to **SnsClient**.

## 2. Where SnsTemplate Fits in the Architecture

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Publisher"] -->|"SnsTemplate.send"| T(("SNS topic<br/>order-events"))
    T -->|"Filter: ORDER_CREATED"| Q["SQS queue<br/>email-jobs"]
    T -->|"Filter: ORDER_CANCELLED"| R["SQS queue<br/>refund-jobs"]
    T -->|"No filter"| L["Lambda<br/>analytics"]
    Q --> W["Email worker"]
    W --> SES["Amazon SES"]
~~~

Execution flow distinctions to keep in mind:

- **Publisher:** uses **SnsTemplate** to send the payload and routing information.
- **Topic:** logical address identified by an ARN, e.g., **arn:aws:sns:ap-southeast-1:123456789012:order-events**.
- **Subscription:** connects a topic to an endpoint; may include a filter policy.
- **Endpoint/consumer:** SQS, Lambda, HTTP/S, or another supported SNS protocol. The consumer is responsible for executing business logic, retries, and duplicate handling.
- **SES:** transactional email sending service. When sending formatted emails to customers, a worker can call SES after receiving an event via SNS/SQS.

**SnsTemplate** is neither a message-storing queue nor an email sender. It is a Java API layer helping the application call **SNS Publish** via the AWS SDK. Publish acceptance by SNS **does not mean** all subscribers have finished processing.

### 2.1. Choosing SnsTemplate or SnsClient?

| Requirement | Approach |
| --- | --- |
| Quickly send a string or POJO via the Spring API | **SnsTemplate.sendNotification** |
| Send a payload with routing attributes | **SnsTemplate.send** with Spring **Message**, or **convertAndSend** with a headers map |
| Send with grouping and deduplication on a FIFO topic | **SnsTemplate.sendNotification** with **SnsNotification** or the **SnsOperations** interface |
| Need **PublishResponse.messageId** or fine-grained per-PublishRequest configuration | **SnsClient.publish** from AWS SDK v2 |
| Need dedicated SMS sending | **SnsSmsTemplate** from Spring Cloud AWS, depending on requirements |

This article uses the **Spring Cloud AWS 3.x** API (**io.awspring.cloud** package) alongside **AWS SDK for Java v2**. Spring Cloud AWS 2.x APIs differ; BOM selection must match the project's Spring Boot version.

## 3. Configuring Spring Boot

### 3.1. Adding the Starter and BOM

In **build.gradle** (Groovy DSL):

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

**springCloudAwsVersion** is a version variable provided by the build, chosen according to the Spring Cloud AWS/Spring Boot compatibility matrix. If using Maven, import the **spring-cloud-aws-dependencies** BOM in **dependencyManagement**, then add **spring-cloud-aws-starter-sns**.

The starter typically auto-configures the **SnsClient** and **SnsTemplate** beans. There is no need to manually declare these two beans if the default configuration meets your needs.

### 3.2. Region and Topic ARN

In **application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}

app:
  messaging:
    sns:
      order-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

At runtime, for example:

~~~text
AWS_REGION=ap-southeast-1
ORDER_EVENTS_TOPIC_ARN=arn:aws:sns:ap-southeast-1:123456789012:order-events
~~~

**Use the full ARN** provisioned by Terraform, CloudFormation, CDK, or your infrastructure management process. SnsTemplate can accept a topic name for a resolver to determine the ARN; some resolver configurations may attempt to create the topic if it does not exist yet. Using an explicit ARN avoids relying on auto-creation behavior and only requires publish permission.

### 3.3. Identity and IAM

The AWS SDK uses the **credentials provider chain**; inside AWS, prefer an **IAM role** attached to the workload (ECS task role, EKS workload identity, or EC2 instance profile). On a development machine, a CLI profile can be used; do not hardcode access keys and secret keys in source code or YAML.

Minimal policy for the **publisher** role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
    }
  ]
}
~~~

This policy only permits publishing to the specific topic. Permissions such as **sns:CreateTopic**, **sns:Subscribe**, **sns:SetSubscriptionAttributes**, and SQS policy configuration are usually granted to the infrastructure management pipeline. If the topic is encrypted with a customer-managed KMS key, also check the corresponding key policy/IAM permissions.

## 4. Three Ways to Publish Notifications with SnsTemplate

### 4.1. Sending Strings and POJOs

SnsTemplate supports sending strings and converting Java objects to JSON using the configured message converter.

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SimpleSnsPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public SimpleSnsPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.messaging.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void publishText() {
        snsTemplate.sendNotification(
                topicArn,
                "Order service started",
                "Order service"
        );
    }

    public void publishObject() {
        snsTemplate.sendNotification(
                topicArn,
                new OrderStatus("ord-1001", "ORDER_CREATED"),
                "Order created"
        );
    }

    public record OrderStatus(String orderId, String eventType) {}
}
~~~

**sendNotification(destination, message, subject)** publishes the message and sets the SNS **subject** when the endpoint/protocol supports it. This is a synchronous call to the SDK, though the method does not return each subscriber's processing status.

**Object → JSON** only works properly when an appropriate message converter is available. In Spring Boot with Jackson, the starter can configure **MappingJackson2MessageConverter**; if you configure a converter yourself, ensure consumers understand how the payload is serialized.

### 4.2. Sending a Spring Message with Headers

A **Spring Messaging Message** contains a **payload** and **headers**. When sent via SnsTemplate, application-attached headers, if supported, are converted into **SNS message attributes**. Special SNS-specific headers such as subject, group ID, and deduplication ID are mapped to the corresponding request parameters.

Define a clear event type:

~~~java
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String eventType,
        String orderId,
        String tenantId,
        int schemaVersion,
        Instant occurredAt
) {}
~~~

Publisher:

~~~java
import io.awspring.cloud.sns.core.SnsTemplate;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final SnsTemplate snsTemplate;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventPublisher(
            SnsTemplate snsTemplate,
            ObjectMapper objectMapper,
            @Value("${app.messaging.sns.order-topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public void publish(OrderEvent event) throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader("eventType", event.eventType())
                .setHeader("tenantId", event.tenantId())
                .setHeader("schemaVersion", String.valueOf(event.schemaVersion()))
                .build();

        snsTemplate.send(topicArn, message);
    }
}
~~~

In this case, the **send** example explicitly serializes the POJO into a JSON String so the content sent to SNS has a predictable format. The **convertAndSend** approach in section 4.3 converts the payload using a message converter.

- The Spring Message **Payload** is the JSON string serialized from **OrderEvent**, which goes into the SNS **Message**.
- Header **eventType=ORDER_CREATED** is used for subscription filters.
- Header **tenantId=tenant-42** enables routing events per tenant if the design requires it.
- Header **schemaVersion=1** helps consumers identify the event contract version.
- **eventId** is generated **before** publishing and preserved across retries of the same event; consumers can use it to prevent duplicate processing.

Example call site for the publisher:

~~~java
OrderEvent event = new OrderEvent(
        "evt-2026-0001",
        "ORDER_CREATED",
        "ord-1001",
        "tenant-42",
        1,
        java.time.Instant.now()
);

orderEventPublisher.publish(event);
~~~

**Note:** Spring's auto-generated **MessageHeaders.id** and **timestamp** should not be treated as stable business identifiers; use a dedicated **eventId** in the payload when cross-service tracing and idempotency are needed.

### 4.3. Using convertAndSend with a Headers Map

When you already have a Java object and a map of attributes, you can write this concisely:

~~~java
snsTemplate.convertAndSend(
        topicArn,
        event,
        java.util.Map.of(
                "eventType", event.eventType(),
                "tenantId", event.tenantId(),
                "schemaVersion", String.valueOf(event.schemaVersion())
        )
);
~~~

Compared to the **MessageBuilder** example, this keeps the same idea: passing **payload** separately from **headers**. Do not encode routing data into the topic name or spin up a separate topic per event type when filtering alone is sufficient.

## 5. Distinguishing Payload and Message Attributes

An outgoing message can be conceptualized as follows:

~~~json
{
  "Message": "{\"eventId\":\"evt-2026-0001\",\"eventType\":\"ORDER_CREATED\",\"orderId\":\"ord-1001\",\"tenantId\":\"tenant-42\",\"schemaVersion\":1,\"occurredAt\":\"2026-11-24T08:00:00Z\"}",
  "MessageAttributes": {
    "eventType": {
      "DataType": "String",
      "StringValue": "ORDER_CREATED"
    },
    "tenantId": {
      "DataType": "String",
      "StringValue": "tenant-42"
    },
    "schemaVersion": {
      "DataType": "String",
      "StringValue": "1"
    }
  }
}
~~~

This is a **conceptual illustration of the fields sent to the Publish API**, not the literal JSON generated by SnsTemplate or the body format every subscriber receives. In the SNS API, each attribute has a **DataType** and corresponding value; when SNS delivers to SQS in standard mode, the message usually sits inside a separate envelope.

| Component | Used For | Design Rule |
| --- | --- | --- |
| **Message body** | Full business content, e.g., order ID, timestamp, schema version | Contains data the consumer needs to process; versioned as schema evolves |
| **Message attributes** | Small metadata for routing/filtering, classification, and handling | Stable names, explicit types; avoid sensitive data |
| **SNS Subject** | Notification subject for supported endpoints | Does not replace event type and is not used by all protocols |
| **SNS MessageId** | ID assigned by SNS after accepting a publish call | Not identical to business **eventId** or confirmation of successful consumption |
| **Spring MessageHeaders** | Metadata passing through Spring Messaging | Some headers are reserved for the framework; select only headers needed for SNS |

### 5.1. Data Types and Basic Limits

SNS supports **String**, **Number**, **String.Array**, and **Binary** attributes. Each attribute has a name, type, and non-empty value; names are case-sensitive. Prefixes such as **AWS.** and **Amazon.** are reserved and should not be used for custom attribute names.

- **String:** fits eventType, tenantId, and schemaVersion represented as strings. This is the stable choice for exact-match filters.
- **Number:** fits numeric data requiring quantitative comparisons; must match filter expectations.
- **String.Array:** supports multiple values in a single attribute; content is represented using valid array syntax.
- **Binary:** used when binary metadata is genuinely needed; not used as a filter key in SNS filter policies.

**Message attributes count toward the SNS message size limit.** By default, SNS message payloads are typically capped at **256 KiB**, including attribute data. Do not attach large documents, secrets, or sensitive information when the consumer only needs an object ID.

**Note for SQS:** if a subscription has **Raw Message Delivery** enabled, SNS supports a maximum of **10 message attributes** on a message delivered to that SQS subscription. If more are needed, consider disabling raw delivery or trimming attributes.

## 6. Using Attributes to Filter Subscriptions

Instead of having three publish statements in publisher code targeting three topics, publish to **one topic**, and let subscriptions decide which messages to receive.

### 6.1. Filter Policy Example

Suppose the service sends a message:

~~~text
Message attributes:
  eventType     = ORDER_CREATED
  tenantId      = tenant-42
  schemaVersion = 1
~~~

Set **FilterPolicyScope=MessageAttributes** (the default value) on the subscription to **email-jobs**:

~~~json
{
  "eventType": ["ORDER_CREATED"],
  "tenantId": ["tenant-42"]
}
~~~

SNS applies **AND across keys** (must match **eventType** *and* **tenantId**) and **OR across values** within the same key. Attributes not mentioned in the filter, such as **schemaVersion**, do not affect the outcome.

Example with three subscriptions:

| Subscription | FilterPolicy | For ORDER_CREATED/tenant-42 |
| --- | --- | --- |
| **email-jobs** | eventType = ORDER_CREATED; tenantId = tenant-42 | **Received** |
| **refund-jobs** | eventType = ORDER_CANCELLED | **Not received** |
| **analytics** | No filter | **Received** |

Set the policy with the AWS CLI (replace with actual ARN and ensure the subscription already exists):

~~~bash
aws sns set-subscription-attributes --subscription-arn "arn:aws:sns:ap-southeast-1:123456789012:order-events:subscription-id" --attribute-name FilterPolicyScope --attribute-value MessageAttributes
aws sns set-subscription-attributes --subscription-arn "arn:aws:sns:ap-southeast-1:123456789012:order-events:subscription-id" --attribute-name FilterPolicy --attribute-value '{"eventType":["ORDER_CREATED"],"tenantId":["tenant-42"]}'
~~~

Single-quote syntax in the CLI example suits Bash-like shells; in PowerShell, pass JSON according to the shell's quoting rules or use a JSON file to avoid escaping errors.

In production, subscriptions and filters should be defined in infrastructure as code (IaC) and deployed alongside endpoint permissions.

### 6.2. Why Messages Are Filtered Incorrectly

- **Missing header:** the publisher does not send **eventType**, but the subscription requires that field.
- **Case mismatch:** **ORDER_CREATED** differs from **order_created**.
- **Type mismatch:** numeric filters and string attributes do not necessarily match, even if both display as "1".
- **Wrong scope:** the filter targets attributes, but the subscription uses **MessageBody**, or vice versa.
- **Malformed JSON:** missing square brackets around value lists, invalid structure.
- **Configuration changes not yet propagated:** filter policies may take time to synchronize; do not assume immediate effect.

When **FilterPolicyScope=MessageBody**, SNS evaluates fields in the JSON payload instead of message attributes; this is useful when the source cannot customize metadata. For self-managed Spring Boot publisher flows, using explicit **message attributes** is usually easier to test.

## 7. Considerations When Delivering to SQS

An SNS topic needs a subscription pointing to the queue; filter conditions are only part of delivery. The **Queue resource policy** must allow the topic to perform **sqs:SendMessage**, usually scoped by **aws:SourceArn** so only the designated topic has send permission.

Example statement for the **email-jobs** queue:

~~~json
{
  "Sid": "AllowOrderEventsSns",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:email-jobs",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
    }
  }
}
~~~

This statement belongs to the **SQS queue policy** and must be inside a valid policy applied to the queue. A publisher with **sns:Publish** permission cannot automatically grant SNS permission to send to SQS; both sides of permissions are configured independently.

**RawMessageDelivery=false** (usually the default): the SQS body contains the SNS notification envelope, where the **Message** field holds the content published by the publisher and **MessageAttributes** are represented inside the envelope. Consumers must unwrap the envelope layer before reading the event JSON.

**RawMessageDelivery=true:** the SQS body is directly the publisher's payload; message attributes are mapped to corresponding SQS message attributes within supported limits. Consumers reading under this configuration are simpler when the payload is business JSON, though the full SNS envelope is no longer in the body.

You cannot assume every consumer will receive the exact same JSON structure: Lambda, SQS, HTTP/S, and email have different delivery formats.

## 8. Publishing to SNS FIFO with SnsTemplate

If the ordering of events within the same order is a business requirement, consider a **.fifo** topic with FIFO-supported endpoints and configurations. With Spring Cloud AWS 3.x, **SnsNotification** lets you set **groupId** and **deduplicationId**:

~~~java
import io.awspring.cloud.sns.core.SnsNotification;
import io.awspring.cloud.sns.core.SnsTemplate;

public void publishOrderedEvent(
        SnsTemplate snsTemplate,
        String fifoTopicArn,
        OrderEvent event) {

    SnsNotification<OrderEvent> notification =
            SnsNotification.builder(event)
                    .groupId(event.orderId())
                    .deduplicationId(event.eventId())
                    .header("eventType", event.eventType())
                    .header("tenantId", event.tenantId())
                    .build();

    snsTemplate.sendNotification(fifoTopicArn, notification);
}
~~~

- **MessageGroupId:** group that needs ordered processing, e.g., events sharing the same **orderId**.
- **MessageDeduplicationId:** identifies duplicate messages within the limited deduplication window. Use a stable **eventId** across retries of the same event.
- **eventType/tenantId headers:** still serve attribute-based filter policies.

FIFO does not replace **idempotent consumer** design. Ordering and deduplication mechanisms only apply under supported conditions and subscription/endpoint types; business logic can still be invoked again after processing errors or retries at other layers.

## 9. Error Handling and Ensuring Consistency

### 9.1. Do Not Conflate Three Distinct States

1. **Publisher calls SnsTemplate successfully:** the Publish request has been accepted by SNS.
2. **SNS delivers successfully:** an endpoint/subscription received the message.
3. **Consumer processes successfully:** the business effect, such as DB writes or sending an email via SES, has completed.

SnsTemplate's **send**, **convertAndSend**, and **sendNotification** do not return a list of subscribers that processed the message. If the publishing application immediately needs the **SNS MessageId** from PublishResponse, use **SnsClient.publish** rather than assuming SnsTemplate's void API provides that response.

### 9.2. Common Errors

| Symptom | Check |
| --- | --- |
| **AccessDeniedException** when publishing | Does the IAM role have **sns:Publish** on the exact ARN? Is KMS permission missing? |
| **NotFound** or wrong topic | Do ARN, account, and region match the runtime environment? |
| Publish succeeds but SQS is empty | Is the subscription confirmed/correct? Does the queue policy have **sqs:SendMessage**? Does the filter match attributes? |
| Consumer receives unexpected body format | Are **RawMessageDelivery** and the consumer parser consistent? |
| Duplicate processing occurs | Does the consumer use **eventId** to prevent duplicate processing? |
| FIFO rejected | Does the topic end with **.fifo**, are groupId/deduplicationId valid, and does the target support FIFO? |

If writing the order to the DB and publishing to SNS are two separate operations, a situation can occur where the DB commits successfully but SNS Publish fails. For high-reliability workflows, consider **transactional outbox**: write the event to an outbox table in the same DB transaction, then have a worker publish it idempotently.

For transient failures, apply bounded retries with backoff, monitor CloudWatch metrics/logs, and place dead-letter queues (DLQs) at the appropriate stages. Distinguish an **SNS subscription DLQ** (SNS fails to deliver a message to the endpoint) from an **SQS DLQ** (the consumer fails to process a message already in the queue).

## 10. Testing the Application

### 10.1. Unit Tests on the Publisher

Use Mockito to mock **SnsTemplate**, invoke the publish method, capture the arguments to **snsTemplate.send**, and verify:

- The destination matches the configured topic ARN.
- The payload contains the expected **eventId**, **eventType**, **orderId**, and **schemaVersion**.
- Headers **eventType** and **tenantId** have the exact expected values.
- When an SDK exception is thrown, the application reacts according to the defined error-handling strategy rather than silently treating the publish as successful.

Example assertions for a Spring Message captured from a mock:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals("ORDER_CREATED", capturedMessage.getHeaders().get("eventType"));
assertEquals("tenant-42", capturedMessage.getHeaders().get("tenantId"));
var json = new ObjectMapper().readTree((String) capturedMessage.getPayload());
assertEquals("ORDER_CREATED", json.path("eventType").asText());
~~~

This is an illustrative check inside a test method declared with **throws Exception**; **capturedMessage** is the object obtained via **ArgumentCaptor** in a unit test. No real AWS calls are needed for unit tests.

### 10.2. Integration Tests with SNS and SQS

An AWS sandbox environment or LocalStack can be used to test the integration path (evaluate the emulator's feature support before treating it as a production benchmark):

| Step | Action | Expected Result |
| --- | --- | --- |
| 1 | Provision an SNS Standard topic, two queues, and subscriptions + queue policies | Both queues have permission to receive from SNS |
| 2 | Attach filter **ORDER_CREATED** to queue A, **ORDER_CANCELLED** to queue B | Two distinct delivery routes |
| 3 | Publisher sends **ORDER_CREATED** with header **eventType** | Queue A receives, queue B does not |
| 4 | Publisher sends **ORDER_CANCELLED** | Queue B receives, queue A does not |
| 5 | Publisher omits header **eventType** | Message does not satisfy filters requiring this field |
| 6 | Test both RawMessageDelivery modes | Consumer decodes either envelope or raw payload properly |
| 7 | Publish the same **eventId** repeatedly | Idempotent consumer does not apply business effects twice |
| 8 | Revoke SNS→SQS permission in the test environment | Delivery failures are recorded and metrics/DLQ behave as configured |

Right after modifying a filter, integration results can be temporarily inconsistent due to policy propagation time. Wait for policies to stabilize before evaluating delivery results to avoid flakiness.

## 11. Hands-on Exercise

**Requirement:** Build a Spring Boot service with a **publishOrderEvent(OrderEvent event)** method using **SnsTemplate**. Each event needs **eventId**, **eventType**, **orderId**, **tenantId**, **schemaVersion**, and **occurredAt**. Attach at least **eventType** and **tenantId** as message attributes.

1. Create an SNS topic **order-events** and two queues **order-created-jobs** and **order-cancelled-jobs**.
2. Create subscriptions, queue policies, and corresponding FilterPolicies.
3. Publish both event types and verify which messages reach each queue.
4. Try omitting **eventType** from headers, changing letter casing, or using the wrong scope to observe filtering behavior.
5. Toggle **RawMessageDelivery** on/off and adjust the consumer parser accordingly.
6. Observe retry behavior and implement idempotency using **eventId**.
7. *Advanced:* switch the pipeline to SNS FIFO + SQS FIFO, setting **groupId** to **orderId**.

**Self-Check Questions:**

- At what abstraction layer does SnsTemplate differ from SnsClient?
- Why should **eventType** be included in attributes even when the JSON payload already contains that field?
- A message being received by subscription A but not B represents what behavior in pub/sub design?
- How does missing **sns:Publish** differ from missing **sqs:SendMessage**?
- Why can the publisher not rely on the success of **sendNotification** to conclude that an email was sent via SES?
- In what scenario should a **MessageBody** filter be used instead of **MessageAttributes**?

## 12. References

- [Spring Cloud AWS 3.3.1 — SNS Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html#sns-integration): starter, SnsTemplate, SnsOperations, and publishing.
- [Spring Cloud AWS 3.3.1 — SnsTemplate API](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/apidocs/io/awspring/cloud/sns/core/SnsTemplate.html): send, convertAndSend, and sendNotification methods.
- [Amazon SNS — Message attributes](https://docs.aws.amazon.com/sns/latest/dg/sns-message-attributes.html): data types, usage, limits, and raw delivery.
- [Amazon SNS — Subscription filter policies](https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html): filtering by message attributes or message body.
- [AWS IAM — SNS Access Policies](https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-use-cases.html): topic access permissions and resource policy principles.

**Expected outcome:** You can publish events from Spring Boot via **SnsTemplate**, separate payloads from **message attributes**, configure subscriptions for conditional delivery, and verify both access permissions and the actual message path.
