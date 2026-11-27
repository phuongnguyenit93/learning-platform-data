# Topic, Subscription, and SNS Notification Delivery Model

## 1. Problem Statement and Learning Objectives

Suppose a Spring Boot application has just recorded an order. For the same **ORDER_CREATED** event, the system needs to send a confirmation email, update analytics, and trigger the order fulfillment workflow. If the order service calls all three systems directly, it must know each destination address, invocation method, retry policy, and the health of its dependent services.

**Amazon Simple Notification Service (SNS)** allows an application to publish a message to a **topic**, after which SNS delivers the message to eligible **subscriptions**. This is the **publish/subscribe (pub/sub)** model and is commonly used for **fan-out**: a single event is distributed to multiple independent processing branches.

After this lesson, learners will be able to:

- Distinguish **publisher**, **topic**, **subscription**, **endpoint**, and delivered message.
- Design a fan-out flow from Spring Boot to SQS, Lambda, or HTTP/S; understand the role of subscription filters.
- Distinguish **SNS Standard** and **SNS FIFO**, including ordering, message duplication, and duplicate-processing prevention mechanisms.
- Configure permissions, publish events using Spring Cloud AWS, and observe delivery errors.
- Know when to use SNS, SQS, and SES in AWS managed service integration scenarios.

Within the scope of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, the focus is on how Spring Boot uses AWS identity and permissions to publish events, integrate messaging services, and test delivery behavior. The principles of configuration separation, least privilege, secret management, and integration testing can be applied when comparing with corresponding managed services on Azure and Google Cloud.

## 2. Core Components

| Component | Meaning | Example |
| --- | --- | --- |
| **Publisher** | Application calling the **Publish** API to send a message | Order service written in Spring Boot |
| **Topic** | Logical channel that receives events and distributes them to subscriptions | **order-events** |
| **Subscription** | Registration relationship between a topic and an endpoint, along with filtering and delivery attributes | Topic **order-events** → queue **order-email-jobs** |
| **Endpoint** | Actual destination that receives the message | SQS queue, AWS Lambda, HTTPS endpoint, email |
| **Message** | Message content (*body*) and optional attributes (*message attributes*) | Order JSON + **eventType=ORDER_CREATED** |

A topic is identified by an **ARN (Amazon Resource Name)**. For example:

~~~text
arn:aws:sns:ap-southeast-1:123456789012:order-events
~~~

A topic can have multiple subscriptions; an endpoint can also receive messages from multiple topics if configured appropriately. When a publisher calls **Publish** successfully, the returned result contains an SNS **MessageId**. **MessageId does not confirm that every subscriber has processed the message successfully**; delivery and processing happen afterward.

### 2.1. Illustrative Fan-Out Flow

~~~mermaid
flowchart LR
    A["Spring Boot<br/>Order Service"] -->|"Publish ORDER_CREATED"| T(("SNS topic<br/>order-events"))
    T -->|"Subscription A<br/>filter ORDER_CREATED"| Q["SQS queue<br/>order-email-jobs"]
    T -->|"Subscription B<br/>filter ORDER_CREATED"| L["AWS Lambda<br/>analytics-handler"]
    T -->|"Subscription C"| H["HTTPS webhook"]
    Q -->|"Poll + process"| W["Spring Boot<br/>Email Worker"]
~~~

According to the diagram, SNS **pushes** notifications to registered destinations; specifically, the worker reads SQS by **polling/pulling** from the queue. Placing SQS in between helps retain messages when the worker is temporarily down and allows the worker to control its processing rate. SNS is the routing/distribution layer; SQS is the buffering and asynchronous consumption layer.

Not every endpoint receives the same format. For example, with SQS and **RawMessageDelivery=false** (default), the SQS body contains an *SNS notification envelope* with fields such as **Type**, **MessageId**, **TopicArn**, **Timestamp**, **Message**, and other metadata. When **RawMessageDelivery=true** is enabled, the SQS body is the publisher's original **Message** content. Consumers need to read the configured format accurately.

## 3. Topic: Standard or FIFO?

SNS has two topic types serving different delivery requirements:

| Criterion | **Standard topic** | **FIFO topic** |
| --- | --- | --- |
| Goal | High throughput and flexible delivery | Preserve ordering within each message group and reduce duplicates |
| Ordering | **Best effort**; may arrive out of publishing order | Preserves order by **MessageGroupId** under supported delivery conditions |
| Duplication | Duplicate messages may be received; design **idempotent** consumers | Has deduplication via **MessageDeduplicationId** or content-based deduplication within a limited window |
| Topic name | E.g. **order-events** | Must have the **.fifo** suffix, e.g. **order-events.fifo** |
| Choose when | Activity notifications, metric updates, independent tasks | Events of the same entity must be consumed sequentially |

With **FIFO**, the producer assigns a **MessageGroupId**, such as the order ID; events in the same group are ordered. A **MessageDeduplicationId** or content-based deduplication configuration is also required. Ordered delivery and deduplication capabilities depend on the endpoint type and related configuration (especially FIFO queues in SNS–SQS integration). **Do not interpret FIFO as a guarantee that "each business operation runs strictly once"**: consumers must still handle idempotency, including during retries or after failures.

For example, if the system only needs to send an "order created" signal to three services, Standard is usually sufficient. If **ORDER_CREATED → ORDER_PAID → ORDER_CANCELLED** events for the same order must arrive in sequence and the target pipeline supports FIFO, consider SNS FIFO combined with SQS FIFO.

## 4. Subscriptions Determine Who Receives Messages

Subscribing an endpoint to a topic creates a **subscription**. Common protocols include **sqs**, **lambda**, **https**, **email**, **sms**; support and delivery details depend on the topic type and endpoint.

A subscription may require confirmation or additional permissions:

- **Email/HTTP(S):** the endpoint usually must confirm the registration request (*subscription confirmation*) before starting to receive notifications; the confirmation step must be designed into operations.
- **SQS:** the queue must have a **resource policy** allowing the specific SNS topic to perform **sqs:SendMessage**. A publisher's **sns:Publish** IAM permission does not automatically grant permission to send messages to the queue.
- **Lambda:** appropriate invoke permission for SNS is required on the Lambda function.

A removed subscriber will stop receiving new messages through that subscription. SNS also **does not provide a topic history replay mechanism** for a new subscription: you must use a message-retaining queue, an event store, or a custom replay design if the business logic requires re-reading past events.

### 4.1. Filtering by Message Attributes

Not every subscription needs to receive every event. With **FilterPolicy**, a subscription can receive only messages matching specific conditions. For example, the publisher attaches attributes:

~~~json
{
  "eventType": "ORDER_CREATED",
  "tenantId": "tenant-42"
}
~~~

These are conceptual values of **message attributes**. On subscription A, set **FilterPolicyScope=MessageAttributes** (the default scope) and the policy:

~~~json
{
  "eventType": ["ORDER_CREATED"],
  "tenantId": ["tenant-42"]
}
~~~

This subscription only matches if **both** keys satisfy the condition (AND across keys); values within the same list are matched with OR. If the publisher omits a required attribute, the message will not match the filter. **FilterPolicyScope=MessageBody** can be used to filter on fields in the JSON body, though the body must conform to the expected structure and filter policy.

Suppose there are two queues:

| Subscription | Filter | What is received? |
| --- | --- | --- |
| **order-email-jobs** | **eventType = ORDER_CREATED** | Signal to send order confirmation email |
| **order-cancel-jobs** | **eventType = ORDER_CANCELLED** | Signal to process order cancellation |

An **ORDER_CREATED** event passes through the topic, is evaluated by SNS against **each subscription's** policy, and is then sent only to the matching destination. Adding a filter is a change at the delivery layer; the publisher does not need to call each consumer sequentially.

**Note:** Changes to subscription attributes and filters may take time to propagate across the distributed system. During the transition period, tests should allow temporary discrepancies rather than assuming the configuration takes effect immediately.

## 5. Integrating SNS with Spring Boot and Spring Cloud AWS

In a Spring Boot application, **Spring Cloud AWS** can be used to configure the AWS client by region and the default credential provider chain. The following example uses **SnsClient** from AWS SDK for Java v2 via the AWSpring dependency; this approach makes the **Publish** call and message attributes explicit.

### 5.1. Declaring Dependencies

Example **Gradle (Groovy DSL)**, where **springCloudAwsVersion** is the BOM version chosen to be **compatible with the project's Spring Boot version**:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

This pattern uses the **Spring Cloud AWS 3.x** generation with the **io.awspring.cloud** namespace and AWS SDK v2. If the application uses an older generation, APIs, dependencies, and configuration names may differ; choose a consistent version set.

### 5.2. Configuring Region and Topic ARN

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}

app:
  sns:
    order-events-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

For example, set **ORDER_EVENTS_TOPIC_ARN** in runtime environment variables. **Do not put access keys/secret keys in source code or application.yml**. In an AWS environment, prefer the workload's IAM role (such as an ECS task role or EC2 instance role); on a development machine, an externally managed AWS profile can be used. The default credential chain searches for credentials from SDK-supported sources.

A least-privilege IAM policy for the publisher can restrict the **sns:Publish** action to the exact topic:

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

The ARN and account ID here are examples only. Permissions to create topics, create subscriptions, and modify queue policies usually belong to infrastructure provisioning and do not need to be granted to an application that only acts as a publisher.

### 5.3. Publishing Events and Filter Attributes

~~~java
package example.notification;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.MessageAttributeValue;
import software.amazon.awssdk.services.sns.model.PublishRequest;

import java.util.Map;

@Service
public class OrderEventPublisher {
    private final SnsClient snsClient;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventPublisher(
            SnsClient snsClient,
            ObjectMapper objectMapper,
            @Value("${app.sns.order-events-topic-arn}") String topicArn) {
        this.snsClient = snsClient;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public String publishOrderCreated(String eventId, String orderId, String tenantId)
            throws JsonProcessingException {
        String body = objectMapper.writeValueAsString(Map.of(
                "eventId", eventId,
                "eventType", "ORDER_CREATED",
                "orderId", orderId,
                "tenantId", tenantId
        ));

        Map<String, MessageAttributeValue> attributes = Map.of(
                "eventType", MessageAttributeValue.builder()
                        .dataType("String")
                        .stringValue("ORDER_CREATED")
                        .build(),
                "tenantId", MessageAttributeValue.builder()
                        .dataType("String")
                        .stringValue(tenantId)
                        .build()
        );

        return snsClient.publish(PublishRequest.builder()
                .topicArn(topicArn)
                .message(body)
                .messageAttributes(attributes)
                .build()).messageId();
    }
}
~~~

**Key points to understand in this code:**

1. **OrderEventPublisher** only knows the topic ARN, not the list of subscribers.
2. **body** is the JSON containing the event data. **messageAttributes** is metadata so SNS can evaluate subscription filters.
3. **eventId** is a business event identifier generated once and preserved across retry attempts; the consumer side can store/check this ID to skip duplicate processing. The **MessageId** returned by SNS is an identifier assigned by SNS when accepting the publish call.
4. The **publish** call may throw an exception due to permissions, configuration, network, or service limits; the application must decide on an appropriate retry strategy. If the event must be tightly coupled with a database update transaction, consider the **transactional outbox** pattern to avoid writing data successfully while failing to publish the event.

Some Spring Cloud AWS solutions also provide **SnsTemplate** to simplify publishing; **SnsClient** is used here to clearly illustrate the SNS API and attribute-based filtering.

## 6. Creating an SNS Topic and SNS → SQS Subscription

The example illustrates using the **AWS CLI**. First, create the topic and queue via the Console, CLI, or infrastructure as code (Terraform/CloudFormation/CDK). Two basic CLI commands:

~~~bash
aws sns create-topic \
  --name order-events \
  --region ap-southeast-1

aws sqs create-queue \
  --queue-name order-email-jobs \
  --region ap-southeast-1
~~~

Retrieve **TopicArn** from the topic creation output; retrieve **QueueArn** using **sqs get-queue-attributes** with the **QueueArn** attribute. Assuming both are in account **123456789012**, create the subscription:

~~~bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-southeast-1:123456789012:order-events \
  --protocol sqs \
  --notification-endpoint arn:aws:sqs:ap-southeast-1:123456789012:order-email-jobs \
  --region ap-southeast-1
~~~

**Before testing delivery**, configure a **resource policy** on the queue so SNS can send messages. Example statement in the queue access policy (set via Console/IaC and replace with actual ARNs):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyOrderEventsTopic",
      "Effect": "Allow",
      "Principal": {
        "Service": "sns.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-email-jobs",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
        }
      }
    }
  ]
}
~~~

Restricting by **aws:SourceArn** reduces the risk of another SNS topic sending messages into the queue. With custom KMS encryption, you must also check appropriate KMS permissions for the delivery path.

After the subscription has been created, **FilterPolicy** can be attached via CLI (replace **SUBSCRIPTION_ARN** with the received subscription ARN):

~~~bash
aws sns set-subscription-attributes \
  --subscription-arn "$SUBSCRIPTION_ARN" \
  --attribute-name FilterPolicy \
  --attribute-value '{"eventType":["ORDER_CREATED"]}'
~~~

Or place the equivalent configuration in IaC for version control and to avoid manual configuration drift across environments. The example above uses the default **FilterPolicyScope=MessageAttributes**; the message in Java from section 5.3 will match the filter.

## 7. Retries, Delivery Failures, and Reliability

Three failure points must be clearly separated:

| Stage | Failure Example | How to Handle |
| --- | --- | --- |
| **Publisher → SNS** | Missing **sns:Publish**, wrong region/ARN, timeout | Log the cause; retry with backoff when appropriate; use outbox if post-commit publish guarantees are needed |
| **SNS → endpoint** | Queue policy denies, webhook returns error, destination unavailable | Check permissions and delivery status; use SNS retry mechanisms and a **subscription DLQ** when applicable |
| **Consumer processing** | Worker receives SQS message but database fails | Use retries/visibility timeout and an **SQS DLQ**; design idempotently |

A **Subscription DLQ** (SNS redrive) handles messages that SNS could not deliver to the endpoint after its retry policy. An **SQS DLQ** on the consuming queue handles messages that entered SQS but the consumer could not process. The two DLQ types belong to **two different stages**.

For reliable operation:

- **Idempotency:** store or recognize processed **eventId** values; do not send duplicate emails or double-record entries on redelivery.
- **Observability:** track publish counts, delivered/failed message counts, message age in SQS, DLQ message count, and consumer processing errors. Attach a correlation ID or event ID to logs.
- **Security:** grant only necessary IAM permissions, protect HTTPS endpoints, apply encryption and KMS as required, and avoid putting secrets or unnecessary sensitive data in the body.
- **Event contract:** include **eventType**, **eventId**, timestamp, and schema version when needed; consider backward compatibility because multiple subscribers may upgrade at different times.
- **Size limits:** adhere to SNS message size limits (regular messages up to **256 KiB**); for large payloads, store the object in storage and publish an event containing only an identifier or controlled access path.

Important note: **Successful Publish ≠ successful delivery to all endpoints ≠ successful business processing**. All three stages must be observed.

## 8. Integration Testing SNS and SQS

Flows can be tested using an AWS sandbox environment or an SNS/SQS-compatible service emulator such as LocalStack. Unit tests should verify that the publisher builds the **PublishRequest** with the right topic, body, and attributes; integration tests should verify **actual delivery** through subscriptions and queues.

Minimal integration scenario:

| Step | Action | Expected Result |
| --- | --- | --- |
| 1 | Create a Standard topic, two queues, two subscriptions, and valid queue policies | Both subscriptions are ready to receive |
| 2 | Set filter on queue A to **ORDER_CREATED**, queue B to **ORDER_CANCELLED** | Each queue has clear filter conditions |
| 3 | Publish **ORDER_CREATED** with the **eventType** attribute | Only queue A receives the matching new message |
| 4 | Publish **ORDER_CANCELLED** | Only queue B receives the matching new message |
| 5 | Publish without **eventType** | Neither queue receives it if both filters require this field |
| 6 | Check **RawMessageDelivery** and consumer parser | Consumer accurately reads **Message** in the envelope or the raw body |
| 7 | Simulate consumption failure, reprocess message, or send two events with the same **eventId** | Business logic applies effects only once; retry/DLQ works as designed |

For newly modified subscription filters, avoid immediate assertions due to configuration propagation delay. Besides payload, check queue policy, region, ARNs, IAM/KMS permissions, and metrics when messages do not arrive.

## 9. When to Use SNS, SQS, and SES?

| Service | Primary Responsibility | Example |
| --- | --- | --- |
| **SNS** | Publish events and fan out to multiple subscribers | One order event going to three processing branches |
| **SQS** | Buffer messages for workers to actively pull and process | Email-sending job queue with retries and DLQ |
| **SES (Simple Email Service)** | Send application or transactional emails with sender identity management and email operations | Order confirmation email with body, template, and verified domain |

**SNS email subscriptions** fit certain notification types for recipients who have confirmed their subscription. When building email functionality for end customers, consider **SES**: a worker receives events from SQS and calls SES to send emails. SNS does not directly replace the full application email capabilities of SES.

Common design:

~~~mermaid
flowchart LR
    O["Spring Boot<br/>Order Service"] --> S(("SNS<br/>order-events"))
    S --> Q["SQS<br/>email-jobs"]
    Q --> W["Spring Boot<br/>Email Worker"]
    W --> E["Amazon SES"]
    E --> U["Customer"]
~~~

This design isolates order creation from email sending while allowing new subscribers to be added without changing the event-publishing code.

## 10. Hands-on Exercise and Self-Check Questions

**Exercise:** Build a Spring Boot application that publishes **ORDER_CREATED** and **ORDER_CANCELLED** to an SNS Standard topic. Create two SQS queues with corresponding filters, configure queue policy permissions, write a consumer to read messages and log **eventId**. Test both **RawMessageDelivery** modes, then add duplicate-processing prevention to the consumer.

Questions you should be able to answer:

1. Why can a single **Publish** call trigger multiple business workflows without the publisher knowing each consumer's address?
2. How does a **topic** differ from a **subscription**? If a subscription lacks permission to send to SQS, what will the publisher observe?
3. Why does the **MessageId** returned from SNS not prove that the email has been sent?
4. When should **FilterPolicyScope=MessageBody** be used instead of **MessageAttributes**?
5. How does a **Subscription DLQ** differ from an **SQS DLQ**?
6. When should FIFO be chosen, and why should a consumer still be idempotent even with FIFO?

**Expected outcome:** learners can describe and implement the **Spring Boot publisher → SNS topic → subscription filter → SQS/Lambda/HTTPS endpoint** journey, attach proper AWS permissions, observe delivery stages, and choose SES when the final goal is sending application emails.
