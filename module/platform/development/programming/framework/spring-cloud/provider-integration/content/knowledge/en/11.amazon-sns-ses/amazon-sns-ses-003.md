# Subscription Filtering and Fan-Out Delivery from SNS to Multiple SQS Queues

## 1. Problem: One Event, Multiple Consumers

An e-commerce system written in Spring Boot emits **ORDER_CREATED**, **ORDER_PAID**, and **ORDER_CANCELLED** events. Upon receiving this information, the email service sends a confirmation message, the risk control service reviews unusual transactions, and the analytics system must record **every** event. If the order service calls each worker directly, it must know the list of recipients and depend on their availability.

**Amazon Simple Notification Service (SNS)** lets an application **publish** a message to a **topic**. Each **subscription** can deliver a notification copy to **Amazon Simple Queue Service (SQS)** and use a **filter policy** to receive only messages meeting its criteria. Workers pull messages from their own queues and process them asynchronously.

This lesson belongs to the **Amazon SNS and SES** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing connecting Spring Boot to managed services on AWS, Azure, and Google Cloud via their respective Spring Cloud libraries. The focus here is AWS messaging; the principles of identity, access permissions, secrets, integration testing, and cloud provider selection apply across the entire module.

After this lesson, you will be able to:

- Explain the **publisher → SNS topic → subscription filter → multiple SQS queues → workers** path.
- Design **FilterPolicy** rules for **MessageAttributes** and **MessageBody**, including AND, OR, prefix, and numeric conditions.
- Declare an SNS topic, three SQS queues, queue policies, and subscriptions using CloudFormation.
- Publish events from Spring Boot, observe fan-out, test filtering, and diagnose delivery failures.
- Distinguish raw delivery, SNS DLQs, SQS DLQs, IAM permissions, and subscription filter consistency.

## 2. Selective Fan-Out Architecture

Suppose the **order-events-dev** topic is connected to three queues:

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Publisher"] -->|"Publish"| T(("SNS topic<br/>order-events-dev"))
    T -->|"eventType=ORDER_CREATED"| E["SQS<br/>email-jobs-dev"]
    T -->|"eventType=ORDER_PAID<br/>AND riskLevel=HIGH"| F["SQS<br/>fraud-review-dev"]
    T -->|"no filter"| A["SQS<br/>analytics-events-dev"]
    E --> EW["Email worker<br/>may later call SES"]
    F --> FW["Fraud worker"]
    A --> AW["Analytics worker"]
~~~

A single message can be delivered to **multiple distinct queues**. SNS evaluates **each subscription's** policy independently. Queues have their own consumption rates, retries, visibility timeouts, and dead-letter queues (DLQs). SQS consumers actively call **ReceiveMessage** (or a Spring Cloud AWS listener) to receive messages; SNS does not execute business code inside workers.

| Published Message | Email Queue | Fraud Queue | Analytics Queue |
| --- | --- | --- | --- |
| **ORDER_CREATED**, LOW | Received | No | Received |
| **ORDER_PAID**, HIGH | No | Received | Received |
| **ORDER_PAID**, LOW | No | No | Received |
| **ORDER_CANCELLED**, LOW | No | No | Received |
| Missing **eventType**, HIGH | No | No | Received |

The analytics queue has no filter, so it receives every successfully delivered message. If all subscriptions have filters and a message matches none of them, SNS will not deliver the message to any queue; that is valid filtering behavior.

### Components to Distinguish

| Concept | Responsibility |
| --- | --- |
| **Publisher** | Calls SNS Publish, providing payload and message attributes |
| **SNS topic** | Central logical target identified by a topic ARN |
| **Subscription** | Links a topic and an endpoint, holding filter, raw delivery, and delivery settings |
| **SQS queue** | Buffers messages, enabling asynchronous worker processing |
| **Worker/consumer** | Polls the queue, executes business logic, deletes messages upon completion |
| **Amazon SES** | Sends transactional emails when called by the email worker; not responsible for fan-out routing |

## 3. How Subscription FilterPolicy Works

### 3.1. Filtering by MessageAttributes

The default scope of **FilterPolicyScope** is **MessageAttributes**. A publisher can send the event body as JSON along with two metadata attributes outside the body:

~~~json
{
  "Message": "{\"eventId\":\"evt-101\",\"eventType\":\"ORDER_PAID\",\"orderId\":\"ord-101\",\"riskLevel\":\"HIGH\"}",
  "MessageAttributes": {
    "eventType": {"DataType": "String", "StringValue": "ORDER_PAID"},
    "riskLevel": {"DataType": "String", "StringValue": "HIGH"}
  }
}
~~~

This is a **data illustration of PublishRequest**, not the literal body that a consumer receives from SQS.

Filter for the email queue:

~~~json
{
  "eventType": ["ORDER_CREATED"]
}
~~~

Filter for the fraud queue:

~~~json
{
  "eventType": ["ORDER_PAID"],
  "riskLevel": ["HIGH"]
}
~~~

**Key rules:**

1. **AND across keys:** the fraud filter requires both **eventType=ORDER_PAID** *and* **riskLevel=HIGH**.
2. **OR across values of the same key:** **{"eventType":["ORDER_CREATED","ORDER_PAID"]}** matches either one.
3. Attributes not mentioned in the filter do not affect matching.
4. A missing required attribute or mismatched type prevents the filter from matching; strings **HIGH** and **high** differ in standard matching.
5. A subscription **without a FilterPolicy** receives all topic notifications, subject to permissions and endpoint status.

### 3.2. Filtering by MessageBody

If the publisher emits a valid **JSON object** without separate metadata, set **FilterPolicyScope=MessageBody** to filter on fields inside the body.

Example body:

~~~json
{
  "eventId": "evt-101",
  "eventType": "ORDER_PAID",
  "risk": {
    "level": "HIGH",
    "score": 92
  }
}
~~~

Body-based JSON filter:

~~~json
{
  "eventType": ["ORDER_PAID"],
  "risk": {
    "level": ["HIGH"]
  }
}
~~~

**MessageBody** supports accessing nested fields in JSON. With **MessageAttributes**, field names refer to standalone message attribute names and do not automatically inspect fields inside the JSON body. When the scope is **MessageAttributes**, having **eventType** in the payload is not enough for a subscription to match if the publisher does not send an attribute with that name.

### 3.3. Useful Operators

| Need | FilterPolicy | Meaning |
| --- | --- | --- |
| Two event types | **{"eventType":["ORDER_CREATED","ORDER_PAID"]}** | OR |
| Exclude test environment | **{"environment":[{"anything-but":"sandbox"}]}** | Exclude value sandbox |
| Tenant with prefix | **{"tenantId":[{"prefix":"vip-"}]}** | String starting with vip- |
| High risk score | **{"riskScore":[{"numeric":[">=",80]}]}** | Numeric comparison |
| Trace ID present | **{"traceId":[{"exists":true}]}** | Require existence |

For attribute-based filtering, send an appropriate **Number** attribute when using numeric filters, and do not use **Binary** attributes as filter keys. Attribute names, types, casing, and values must be compatible with the policy. When there are many conditional branches, check current SNS filter combination and complexity limits instead of packing thousands of values into one policy.

**FilterPolicy changes do not always take effect immediately:** according to AWS documentation, changes can take **up to 15 minutes** to propagate fully. In integration tests, wait for configuration stability before concluding a message was filtered incorrectly.

## 4. Provisioning Three Queues and Subscriptions with CloudFormation

The following **CloudFormation** template deploys one Standard SNS topic and three Standard SQS queues. Each subscription has its own condition; the analytics queue intentionally has no filter. The example targets a sandbox/dev environment and is saved as **sns-fanout.yml** during practice.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Filtered SNS fan-out to three SQS queues

Resources:
  OrderEventsTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: order-events-dev

  EmailQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: email-jobs-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  FraudQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: fraud-review-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  AnalyticsQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: analytics-events-dev
      MessageRetentionPeriod: 345600
      VisibilityTimeout: 60

  QueueAccessPolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref EmailQueue
        - !Ref FraudQueue
        - !Ref AnalyticsQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: AllowOnlyOrderEventsTopic
            Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource:
              - !GetAtt EmailQueue.Arn
              - !GetAtt FraudQueue.Arn
              - !GetAtt AnalyticsQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref OrderEventsTopic

  EmailSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt EmailQueue.Arn
      FilterPolicyScope: MessageAttributes
      FilterPolicy:
        eventType: [ORDER_CREATED]
      RawMessageDelivery: true

  FraudSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt FraudQueue.Arn
      FilterPolicyScope: MessageAttributes
      FilterPolicy:
        eventType: [ORDER_PAID]
        riskLevel: [HIGH]
      RawMessageDelivery: true

  AnalyticsSubscription:
    Type: AWS::SNS::Subscription
    DependsOn: QueueAccessPolicy
    Properties:
      TopicArn: !Ref OrderEventsTopic
      Protocol: sqs
      Endpoint: !GetAtt AnalyticsQueue.Arn
      RawMessageDelivery: true

Outputs:
  TopicArn:
    Value: !Ref OrderEventsTopic
  EmailQueueUrl:
    Value: !Ref EmailQueue
  FraudQueueUrl:
    Value: !Ref FraudQueue
  AnalyticsQueueUrl:
    Value: !Ref AnalyticsQueue
  EmailSubscriptionArn:
    Value: !Ref EmailSubscription
  FraudSubscriptionArn:
    Value: !Ref FraudSubscription
~~~

Deploy using the AWS CLI (Bash syntax):

~~~bash
aws cloudformation deploy \
  --template-file sns-fanout.yml \
  --stack-name sns-fanout-dev \
  --region ap-southeast-1

aws cloudformation describe-stacks \
  --stack-name sns-fanout-dev \
  --query "Stacks[0].Outputs" \
  --output table \
  --region ap-southeast-1
~~~

**Key points to understand in the template:**

- **!Ref OrderEventsTopic** returns the topic ARN, used for Publish routing and binding the queue policy.
- The SQS subscription **Endpoint** is the **queue ARN**, whereas AWS CLI **receive-message** uses the **queue URL**; do not swap these two values.
- **AWS::SQS::QueuePolicy** allows the SNS service to call **sqs:SendMessage**, but only when **aws:SourceArn** matches the specific topic. Avoid granting unrestricted send permissions.
- **DependsOn** ensures the queue policy is created before the subscriptions, reducing false observations right after deployment.
- **RawMessageDelivery=true** makes the worker receive the original body for easier parsing; this is a per-subscription setting, not a topic setting.
- **AnalyticsSubscription** has no FilterPolicy and therefore receives all messages. A queue can receive from multiple topics if configured, though this example keeps one topic to focus on fan-out.

The Spring Boot application's IAM **only needs sns:Publish** on the topic. Each SQS worker's IAM needs **sqs:ReceiveMessage**, **sqs:DeleteMessage**, and **sqs:GetQueueAttributes** on its assigned queue; the IaC pipeline needs additional permissions to manage topics/queues/subscriptions. Do not hardcode access keys/secret keys; use the workload's IAM role, or an AWS profile in development. Queues using a customer-managed KMS key require appropriate KMS permissions/key policies for the SNS → SQS flow.

## 5. Publishing Events from Spring Boot

Spring Cloud AWS 3.x provides **SnsTemplate**. Add the SNS starter and a BOM version compatible with Spring Boot:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

In **application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
app:
  sns:
    topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
~~~

**ORDER_EVENTS_TOPIC_ARN** comes from CloudFormation Outputs. On AWS, prefer an IAM role; on a local machine, use the AWS credentials provider chain/profile configured outside source code.

Event definition:

~~~java
package demo.orders;

import java.time.Instant;

public record OrderEvent(
        String eventId,
        String eventType,
        String orderId,
        String riskLevel,
        Instant occurredAt
) {}
~~~

The publisher uses Spring Messaging **Message**. The payload is serialized to JSON before being passed to SnsTemplate, while **eventType** and **riskLevel** are attached as headers to be converted into message attributes:

~~~java
package demo.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventsPublisher {
    private final SnsTemplate snsTemplate;
    private final ObjectMapper objectMapper;
    private final String topicArn;

    public OrderEventsPublisher(
            SnsTemplate snsTemplate,
            ObjectMapper objectMapper,
            @Value("${app.sns.topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.objectMapper = objectMapper;
        this.topicArn = topicArn;
    }

    public void publish(OrderEvent event) throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        Message<String> message = MessageBuilder.withPayload(json)
                .setHeader("eventType", event.eventType())
                .setHeader("riskLevel", event.riskLevel())
                .build();

        snsTemplate.send(topicArn, message);
    }
}
~~~

Example invocation:

~~~java
publisher.publish(new OrderEvent(
        "evt-101", "ORDER_PAID", "ord-101",
        "HIGH", java.time.Instant.now()
));
~~~

In that example, SNS selects the fraud and analytics subscriptions, not email. If **ORDER_PAID** is sent with **LOW**, only analytics is selected.

**Distinguishing the two types of data:** the JSON body holds the business event; the SNS message attributes **eventType** and **riskLevel** are used for subscription filters. Spring-generated **MessageHeaders.id** is not a business ID. Generate **eventId** once when the event occurs and keep it unchanged across retries so consumers can prevent duplicate processing.

You can use **SnsClient.publish** (AWS SDK v2) directly when you need to build a **MessageAttributeValue** of a specific type such as **Number** or obtain **PublishResponse.messageId**. **SnsTemplate.send** is more convenient in Spring, but a successful call only indicates that SNS accepted the publish; it does not guarantee that all workers have finished processing.

## 6. Testing Fan-Out via AWS CLI

To verify filter logic independently of Spring Boot, use the AWS CLI to publish sample messages. In Bash, assign **TOPIC_ARN** from the actual CloudFormation output. Below are the publish commands:

**ORDER_CREATED, LOW**:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-201","eventType":"ORDER_CREATED","orderId":"ord-201","riskLevel":"LOW"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"ORDER_CREATED"},"riskLevel":{"DataType":"String","StringValue":"LOW"}}' \
  --region ap-southeast-1
~~~

**ORDER_PAID, HIGH**:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-202","eventType":"ORDER_PAID","orderId":"ord-202","riskLevel":"HIGH"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"ORDER_PAID"},"riskLevel":{"DataType":"String","StringValue":"HIGH"}}' \
  --region ap-southeast-1
~~~

Read each queue (substitute the queue URL from stack Outputs):

~~~bash
aws sqs receive-message \
  --queue-url "$EMAIL_QUEUE_URL" \
  --message-system-attribute-names All \
  --message-attribute-names All \
  --max-number-of-messages 10 \
  --wait-time-seconds 5 \
  --region ap-southeast-1
~~~

Inspect a subscription's configuration using the ARN returned by CloudFormation:

~~~bash
aws sns get-subscription-attributes \
  --subscription-arn "$FRAUD_SUBSCRIPTION_ARN" \
  --region ap-southeast-1
~~~

In the output, check **FilterPolicy**, **FilterPolicyScope**, **RawMessageDelivery**, **Endpoint**, and **TopicArn**. If you just modified a filter, wait sufficient propagation time before evaluating results.

To avoid confusion during testing, use dedicated queues and unique **eventId** values; ensure no leftover messages remain from previous test runs and no other consumer is pulling messages. SQS has at-least-once semantics, and an empty **receive-message** call does not prove the queue is definitely empty. A received message reappears after its visibility timeout if **DeleteMessage** is not called.

## 7. Raw Message Delivery and SQS Body Format

**RawMessageDelivery=false:** SNS sends a notification envelope to SQS. The SQS body contains a JSON object with **Type**, **MessageId**, **TopicArn**, **Timestamp**, **Message**, and other SNS fields. Abbreviated example:

~~~json
{
  "Type": "Notification",
  "TopicArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events-dev",
  "Message": "{\"eventId\":\"evt-201\",\"eventType\":\"ORDER_CREATED\"}"
}
~~~

**RawMessageDelivery=true:** the SQS body is the raw original JSON content:

~~~json
{
  "eventId": "evt-201",
  "eventType": "ORDER_CREATED",
  "orderId": "ord-201",
  "riskLevel": "LOW"
}
~~~

When raw=true, supported message attributes are mapped to SQS message attributes, and the SNS envelope does not wrap the body. **SNS → SQS with raw=true supports at most 10 message attributes**; exceeding the limit prevents delivery to the raw subscription. Do not use attributes as an unbounded metadata store.

**Filter conditions do not depend on whether raw delivery is enabled.** The filter selects *which queue* receives the message; RawMessageDelivery determines *the body format the consumer reads*. When toggling raw mode, update the worker's parser and integration test assertions accordingly.

## 8. Permissions, Retries, DLQ, and Observability

Three locations must be clearly distinguished:

| Location | What Can Happen? | How to Handle |
| --- | --- | --- |
| **Publisher → SNS** | Wrong topic ARN/region, missing **sns:Publish**, timeout | Check IAM, logs, retry with backoff; use transactional outbox when needed |
| **SNS → queue** | Queue policy denies **sqs:SendMessage**, wrong KMS, or endpoint error | Check subscription, SQS queue policy, SNS delivery metrics, and subscription DLQ |
| **Queue → consumer** | Worker fails while processing, visibility timeout expires, message is redelivered | Idempotent worker, retries, and **SQS consumer DLQ** |

An **SNS subscription DLQ** is a queue that receives messages SNS could not deliver to the endpoint after service-managed retries. A **worker SQS DLQ** is a queue that receives messages that landed in the main queue but repeatedly failed consumer processing. These belong to two different stages and do not replace each other.

Monitor **SNS CloudWatch metrics** for published messages, succeeded/failed deliveries, and filtered-out messages. Monitor **SQS metrics** for visible messages, in-flight messages, age of oldest message, and DLQ counts. In the worker, log **eventId**, processing duration, attempt count, and business errors.

Ensure sensitive data is not fanned out to unnecessary subscribers. Grant only **least privilege**, use encryption/KMS as required, and manage credentials via AWS roles or an appropriate secret manager; do not attach tokens or passwords to messages. Standard SNS has a **256 KiB** message size limit including message attributes; large payloads should be stored in storage with only a controlled identifier/reference sent in the event.

### Standard vs. FIFO

The sample uses **SNS Standard → SQS Standard**: high throughput, at-least-once delivery, with possible duplicates and out-of-order arrival. If business logic requires ordering per **orderId**, consider an **SNS FIFO topic** paired with an **SQS FIFO queue**, setting stable **MessageGroupId** and **MessageDeduplicationId** values. An SNS FIFO topic can also subscribe an SQS Standard queue if the consumer on that branch can tolerate Standard semantics.

Do not conclude that FIFO eliminates the need for business-level idempotency; workers must still guard against side effects when receiving duplicate events. SNS FIFO supports a different set of protocols than SNS Standard, so do not assume you can subscribe HTTP/S or email directly to a FIFO topic.

## 9. Test Matrix and Troubleshooting

When running integration tests against an AWS sandbox or an SNS/SQS emulator that supports filtering, verify the following results in an isolated queue environment:

| Test | Input Data | Email | Fraud | Analytics |
| --- | --- | --- | --- | --- |
| A | ORDER_CREATED / LOW | 1 | 0 | 1 |
| B | ORDER_PAID / HIGH | 0 | 1 | 1 |
| C | ORDER_PAID / LOW | 0 | 0 | 1 |
| D | ORDER_CANCELLED / LOW | 0 | 0 | 1 |
| E | Missing eventType / HIGH | 0 | 0 | 1 |
| F | order_created (wrong case) / LOW | 0 | 0 | 1 |

In the table, **1** means the matching subscription is selected for delivery in the ideal model, **not a guarantee that each worker receives it strictly once**. Use **eventId** to identify exact test messages rather than relying on total message counts.

Additional scenarios to test:

1. Revoke SNS permission to send to the email queue in sandbox: Publish can still succeed, yet the email queue receives nothing; inspect SNS delivery failure/DLQ.
2. Switch scope to **MessageBody**, send a JSON body with eventType and no attributes: verify body-based matching.
3. Set **RawMessageDelivery** to false: verify the consumer unwraps the SNS envelope before reading the JSON payload.
4. Force the worker to fail before deleting the message: verify retries, visibility timeout, idempotency, and SQS DLQ.
5. Update FilterPolicy and test after configuration propagation; avoid false conclusions from eventual consistency.

**Failures to diagnose:**

- **Publish gets AccessDenied:** check IAM **sns:Publish** permission, topic ARN, and KMS.
- **Publish succeeds but all queues are empty:** wrong topic/subscription, queue policies, KMS, metrics, or test reading the wrong queue.
- **Only one queue is empty:** filter policy, FilterPolicyScope, missing attribute, wrong case/type, or filter not yet fully propagated.
- **Worker fails to parse JSON:** RawMessageDelivery and parser do not match.
- **Worker processes twice:** faulty idempotency or message redelivery.
- **Consumer fails yet SNS reports no failed delivery:** SNS delivered to SQS successfully; inspect worker logs and SQS DLQ.

## 10. Exercise and References

**Exercise:** Create the **order-events-dev** topic and three queues from the CloudFormation template in section 4; write a Spring Boot publisher emitting the four events in the test matrix; build three workers that log **eventId**. Next, change the fraud filter to **riskScore >= 80**, compare MessageAttributes/MessageBody, test raw delivery, and simulate consumer failures to observe the SQS DLQ.

**Self-check questions:**

1. Why can the same message appear in both the analytics queue and the email queue?
2. In a filter with two keys, does SNS apply AND or OR? What about one key with two values?
3. The body contains **eventType**, but the scope is **MessageAttributes** and no matching attribute is sent: does the message match?
4. Why do both Spring Boot's IAM role and SQS's resource policy need to be configured?
5. At what stage does an SNS subscription DLQ differ from an SQS consumer DLQ?
6. What does RawMessageDelivery change, and why does it not replace FilterPolicy?
7. Why is idempotency still required even when using a managed queue?

**AWS and Spring Cloud AWS documentation:**

- [Amazon SNS — Message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html)
- [Amazon SNS — Subscription filter policies](https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html)
- [Amazon SNS — Filter policy scope](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering-scope.html)
- [Amazon SNS — Applying a filter policy](https://docs.aws.amazon.com/sns/latest/dg/message-filtering-apply.html)
- [Amazon SNS — Subscribe an SQS queue](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html)
- [Amazon SNS — Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [Amazon SNS — Dead-letter queues](https://docs.aws.amazon.com/sns/latest/dg/sns-dead-letter-queues.html)
- [CloudFormation — AWS::SNS::Subscription](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-sns-subscription.html)
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html)

**Expected outcome:** You can deploy and test the **Spring Boot → SNS topic → filtered subscriptions → multiple SQS queues** path, configure proper permissions on both publisher and queues, and observe success/failure across each delivery branch.
