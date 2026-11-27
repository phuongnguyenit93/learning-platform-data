# Publish and Subscribe Permissions, and Coordinating Topic Policies with Queue Policies

## 1. Problem Statement and Objectives

Suppose the **Order Service** is developed in Spring Boot and needs to publish **ORDER_CREATED** events. Another application reads events from Amazon SQS to send emails via Amazon SES. The team granted **sns:Publish** permission to the Order Service and created an **SNS → SQS** subscription, yet messages still do not reach the queue. The cause may lie in the **queue policy**, which is an independent permission layer from publish permissions.

To implement this correctly, distinguish three questions:

1. **Who is allowed to publish notifications to the SNS topic?** — the **sns:Publish** permission.
2. **Who is allowed to subscribe endpoints to the topic?** — the **sns:Subscribe** permission.
3. **Which SQS queues is SNS allowed to send messages into?** — the **sqs:SendMessage** permission in the **SQS queue resource policy**.

This lesson belongs to the **Amazon SNS and SES** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on hands-on Spring Boot integration with managed services on AWS, Azure, and Google Cloud, including identity/permissions, messaging, storage, data, secret protection, integration testing, and cloud provider selection. For SNS/SQS, understanding these permission layers is a prerequisite before integrating Spring Cloud AWS into production systems.

After this lesson, you will be able to:

- Distinguish **IAM identity-based policy**, **SNS topic resource policy**, and **SQS queue resource policy**.
- Grant publish and subscribe permissions following the **least privilege** principle, without granting infrastructure creation/modification rights to the publisher.
- Design policies for **SNS topic A → SQS queue B** within the same AWS account and across different AWS accounts.
- Use **aws:SourceArn** and the **sns.amazonaws.com** principal to restrict SNS delivery into a queue.
- Check **Subscription confirmation**, KMS encryption, and worker permissions to read from the queue.
- Diagnose a **Publish succeeded but no message in SQS** case using repeatable steps.

## 2. Three Permission Boundaries in an SNS → SQS Flow

~~~mermaid
flowchart LR
    P["Spring Boot<br/>Order Service"] -->|"1. sns:Publish<br/>IAM role"| T(("SNS topic<br/>order-events"))
    A["Subscription admin"] -->|"2. sns:Subscribe<br/>IAM + topic policy"| T
    T -->|"3. sqs:SendMessage<br/>SQS queue policy"| Q["SQS queue<br/>order-email-jobs"]
    Q -->|"4. sqs:ReceiveMessage<br/>sqs:DeleteMessage"| W["Spring Boot<br/>Email Worker"]
    W -->|"ses:SendEmail<br/>separate permission if needed"| E["Amazon SES"]
~~~

**These actions are controlled independently:**

| API Caller | API/Action | Target | Policies Typically Involved |
| --- | --- | --- | --- |
| Publisher (Spring Boot) | **sns:Publish** | SNS topic ARN | Workload's IAM policy; topic policy when needed |
| Subscription administrator | **sns:Subscribe** | SNS topic ARN | Caller's IAM policy; topic policy when cross-account |
| SNS delivery service | **sqs:SendMessage** | SQS queue ARN | **SQS queue policy** for principal **sns.amazonaws.com** |
| SQS worker | **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes** | SQS queue ARN | Workload's IAM policy; queue policy when cross-account |
| Worker sending email via SES | **ses:SendEmail** (or appropriate SES permissions) | Corresponding SES resources | IAM/SES identity policies depending on configuration |

SNS **Publish** returns success once SNS accepts the request; that **does not prove SNS delivered to every subscription**, let alone that the worker sent the email successfully.

### 2.1. How Does an IAM Policy Differ from a Resource Policy?

An **Identity-based policy** attaches to an IAM role/user and answers: *What actions can this identity perform on which resources?*

A **Resource-based policy** attaches to the resource itself (SNS topic, SQS queue) and answers: *Which principal can access this resource, with what actions, and under what conditions?* A resource policy has a **Principal** field; an identity policy normally does not.

Key permission evaluation rules to remember:

- **Implicit deny by default:** when no matching Allow exists, the request is denied.
- **Explicit Deny overrides any Allow:** a deny in IAM, resource policy, SCP, or applicable control policy blocks the request.
- **Same AWS account:** in typical IAM setups, either an identity policy or a resource policy can grant access; however, permission boundaries, session policies, SCPs, resource conditions, and principal types can alter the outcome.
- **Cross AWS account:** generally requires **the resource owner granting access via a resource policy** and **the calling principal holding appropriate identity-based permissions**. Never grant Allow only in the caller's account and assume it can access another account's resource.
- **AWS service principal:** when SNS delivers to SQS, the principal is the **sns.amazonaws.com** service, so policies on the publisher application do not replace the queue resource policy.

Do not reduce all of IAM to simple addition of two policies: explicit Deny, Organizations SCPs, permission boundaries, VPC endpoint policies, and request conditions can all affect evaluation. When diagnosing, check the **actual principal** calling the API, the **actual resource ARN**, and the **denied action**.

## 3. sns:Publish Permission for the Spring Boot Application

Assume a same-account topic has the ARN:

~~~text
arn:aws:sns:ap-southeast-1:111122223333:order-events
~~~

The Spring Boot publisher's IAM role only needs the **sns:Publish** action on this topic:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishOrderEventsOnly",
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

This is an **identity-based policy**, attached to the role of the workload running the application. For example:

- **ECS**: task role.
- **EC2**: instance profile role.
- **EKS**: the workload identity mechanism configured for the cluster.
- **Development machine**: AWS CLI profile/SDK credentials provider chain.

**Do not hardcode access keys/secret keys in application.yml, Java constants, or Git.** If application secrets must be managed, use an appropriate secret manager system and restrict secret-read permissions per workload.

The publisher **does not need** **sns:CreateTopic**, **sns:SetTopicAttributes**, **sns:Subscribe**, or **sqs:SendMessage** when its sole responsibility is publishing to a provisioned topic. Infrastructure creation/modification permissions belong to the IaC pipeline or administrators.

### 3.1. Must You Edit the Topic Policy in the Same Account?

When publisher and topic are in the same account, an IAM Allow on the role is usually sufficient to call **sns:Publish**, provided no Deny or other control condition blocks it. Do not add a broad Allow for **Principal: "*"** in the SNS topic policy just to make a same-account publisher work.

When **another AWS account** or an **AWS service** needs to publish to the topic, the topic resource policy is typically where external principals are granted access, optionally with source-restricting conditions. For service-to-service integrations such as S3 → SNS or EventBridge → SNS, principals and conditions must follow the **source service's documentation**, rather than mechanically copying a cross-account IAM role pattern.

### 3.2. Example Topic Policy for a Cross-Account Publisher

Suppose a specific role in account **444455556666** is permitted to publish to a topic in account **111122223333**. Add the following **statement** to the topic's SNS access policy (preserving existing valid administrative statements):

~~~json
{
  "Sid": "AllowExternalPublisherRole",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/external-order-publisher"
  },
  "Action": "sns:Publish",
  "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
}
~~~

At the same time, the **external-order-publisher** role needs permission to call **sns:Publish** on that ARN in its own account's IAM. Scope Principal down to the exact role that needs to publish; avoid granting an entire account without a clear governance reason.

**Operational warning:** The snippet above is a **single statement**, not a complete topic policy JSON. Do not overwrite an existing policy blindly with it; doing so could erase necessary topic management permissions. Update via IaC or fetch the current policy, edit carefully, and re-verify.

## 4. sns:Subscribe Permission and Subscription Ownership

**sns:Subscribe** is the permission to request creating a link between an SNS topic and an endpoint, for example:

~~~text
Topic:    arn:aws:sns:ap-southeast-1:111122223333:order-events
Protocol: sqs
Endpoint: arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs
~~~

The **Topic ARN** is the resource requiring **sns:Subscribe**; the **Endpoint** is the ARN of the receiving queue, not the topic ARN.

### 4.1. IAM Policy for the Subscription Creator

When the subscription admin belongs to the topic's account and is authorized to manage infrastructure:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubscribeOnlyOrderTopic",
      "Effect": "Allow",
      "Action": "sns:Subscribe",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

This permission **does not grant** rights to configure the queue, view messages, or process emails. When account B owns the SQS queue and wants to create a subscription to account A's topic itself, both **A's topic policy** and **the IAM policy of the subscribing principal in B** must allow it.

### 4.2. Topic Policy Allowing Another Account to Subscribe

Account A owns the **order-events** topic. Account B owns the **order-email-jobs** queue and the **queue-subscription-admin** role. In **A's SNS topic policy**, add the statement:

~~~json
{
  "Sid": "AllowExternalQueueOwnerToSubscribe",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/queue-subscription-admin"
  },
  "Action": "sns:Subscribe",
  "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events",
  "Condition": {
    "StringEquals": {
      "sns:Protocol": "sqs",
      "sns:Endpoint": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs"
    }
  }
}
~~~

On account B's side, attach an IAM policy to the **queue-subscription-admin** role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SubscribeToAccountATopic",
      "Effect": "Allow",
      "Action": "sns:Subscribe",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  ]
}
~~~

Condition keys **sns:Protocol** and **sns:Endpoint** restrict the **endpoint type** and **endpoint address** that can be subscribed. They belong to the SNS topic policy, unlike **aws:SourceArn** on the SQS queue policy in the next section.

**Subscription ownership responsibility:** For cross-account SNS → SQS, AWS recommends that the **queue owner create the subscription**, allowing the SQS subscription to be auto-confirmed in the supported flow. If a principal that does not own the queue creates the subscription, it may need to be confirmed via the confirmation message delivered to the queue before notifications arrive. For email/HTTP(S), endpoint confirmation follows its own rules. Never treat **PendingConfirmation** as ready to deliver messages.

After creating a subscription, use **SubscriptionArn** to track and manage its attributes. Unsubscribing/confirming has its own authentication and ownership rules; do not assume granting **sns:Subscribe** automatically permits administrative operations on all subscriptions.

## 5. Queue Policy: Allowing SNS to Call sqs:SendMessage

An SQS queue must grant permission to the **SNS service principal** to receive messages from a topic. This is a separate permission layer, even if the publisher can publish and the subscription already exists.

Suppose the queue is in account B:

~~~text
arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs
~~~

The **SQS queue access policy** should include the statement:

~~~json
{
  "Sid": "AllowOnlyOrderEventsTopic",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
    }
  }
}
~~~

**Field-by-field explanation:**

| Field | Value | Reason |
| --- | --- | --- |
| **Principal** | **Service: sns.amazonaws.com** | AWS SNS directly requests SQS to accept the message |
| **Action** | **sqs:SendMessage** | Allows only sending messages; does not grant read/delete permissions |
| **Resource** | **queue ARN** | Permission applies to the exact queue in account B |
| **Condition** | **ArnEquals aws:SourceArn = topic ARN** | Allows only messages originating from topic A, mitigating confused deputy risk |

If a queue receives from multiple topics, declare multiple appropriate statements/ARNs while respecting policy size limits; do not open **Principal: "*"** or drop source conditions merely to fix a delivery failure. **aws:SourceAccount** can add account-level constraints depending on the scenario, but when the exact topic is known, a specific **aws:SourceArn** is the clearer restriction.

**Important note:** **aws:SourceArn in a queue policy is the SNS topic ARN**, not the subscription ARN, publisher IAM role, or queue URL. When the queue uses encryption with a customer-managed AWS KMS key, a valid queue policy alone may still be insufficient: SNS may need **kms:GenerateDataKey** and **kms:Decrypt** on the KMS key via the key policy. KMS is covered in section 8.

### 5.1. Complete Queue Policy JSON

To configure in the SQS Access policy or Terraform/CloudFormation, wrap the statement above in a JSON policy with **Version** and **Statement**:

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
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:order-events"
        }
      }
    }
  ]
}
~~~

When the queue already has a policy serving other purposes, merge this statement into the existing policy and keep required permissions. Avoid applying a new document that overwrites active statements.

### 5.2. Policy for the SQS Worker Is a Separate Permission

A worker in account B reads from the queue and deletes messages upon completion:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrderEmailJobs",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs"
    }
  ]
}
~~~

This is the worker's **identity-based policy**, not the policy granted to the SNS principal. Granting read/delete permissions to SNS will not help the worker consume the queue; granting read/delete permissions to the publisher is also unnecessary if the publisher only publishes to the topic.

## 6. Coordinating Topic Policy and Queue Policy Across Two AWS Accounts

Example:

- **Account A (111122223333):** SNS topic **order-events**, Spring Boot publisher role.
- **Account B (444455556666):** SQS queue **order-email-jobs**, subscription admin role, and worker role.
- Both resources are in **ap-southeast-1** for easy practice. ARNs in this article are sample data only.

~~~mermaid
sequenceDiagram
    participant IA as "Spring Boot / IAM role A"
    participant S as "SNS topic / account A"
    participant AD as "Subscription admin / account B"
    participant Q as "SQS queue / account B"
    participant W as "Consumer / IAM role B"

    AD->>S: Subscribe(topic A, queue ARN B)
    Note over AD,S: IAM role B + SNS topic policy A for sns:Subscribe
    S-->>AD: SubscriptionArn / confirmation status
    IA->>S: Publish(message)
    Note over IA,S: IAM role A for sns:Publish
    S->>Q: SendMessage(message)
    Note over S,Q: Queue policy B for sns.amazonaws.com and SourceArn=topic A
    W->>Q: ReceiveMessage
    Q-->>W: Message + ReceiptHandle
    W->>Q: DeleteMessage on successful processing
~~~

### 6.1. Recommended Configuration Workflow

1. **A creates the topic**, records the topic ARN, and grants **sns:Publish** to the publisher role.
2. **B creates the queue**, records the queue ARN/URL, and prepares worker permissions to read the queue.
3. **A updates the SNS topic policy** allowing B's subscription admin role to call **sns:Subscribe** on topic A. Protocol and endpoint can be restricted.
4. **B updates the queue policy** allowing service **sns.amazonaws.com** to call **sqs:SendMessage**, conditioned on **SourceArn=topic A**.
5. **B calls Subscribe** using the **queue owner** identity and monitors subscription status. If pending confirmation, complete confirmation per AWS procedure.
6. **A tests Publish** with the publisher role. **B verifies SQS receipt** and that the worker deletes the message after processing.
7. **Observe errors** at each step and add appropriate retries/DLQs; if using KMS, verify key policies.

**None of these three policies can automatically replace the other two.**

### 6.2. AWS CLI Commands for Verification

The commands below use two configured AWS CLI profiles: **topic-owner** for account A and **queue-owner** for account B. Replace ARNs/account IDs to match your actual environment.

Check active identities and permissions to inspect the topic:

~~~bash
aws sts get-caller-identity --profile topic-owner
aws sts get-caller-identity --profile queue-owner

aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --query 'Attributes.Policy' \
  --output text \
  --region ap-southeast-1 \
  --profile topic-owner
~~~

Inspect the queue policy using the queue **URL**:

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/444455556666/order-email-jobs \
  --attribute-names QueueArn Policy \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

Create the subscription **using the identity belonging to the queue-owning account**, after both policies are in place:

~~~bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --protocol sqs \
  --notification-endpoint arn:aws:sqs:ap-southeast-1:444455556666:order-email-jobs \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

This requires the **queue-owner** profile to use a principal permitted by the topic policy to Subscribe and holding the matching IAM permission; choosing the queue owner allows the subscription to auto-confirm per AWS guidance.

List subscriptions:

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --region ap-southeast-1 \
  --profile topic-owner
~~~

Publish a message and inspect the queue:

~~~bash
aws sns publish \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events \
  --message '{"eventId":"evt-1001","eventType":"ORDER_CREATED","orderId":"ord-1001"}' \
  --region ap-southeast-1 \
  --profile topic-owner

aws sqs receive-message \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/444455556666/order-email-jobs \
  --wait-time-seconds 10 \
  --max-number-of-messages 10 \
  --region ap-southeast-1 \
  --profile queue-owner
~~~

In practice, separate profiles may be needed for **publisher**, **subscription admin**, and **consumer** since **topic-owner/queue-owner** in this example only illustrate account boundaries. Reading from the queue requires **sqs:ReceiveMessage**; list/read commands require corresponding IAM read permissions. **A single empty receive-message call does not prove a message is absent**, especially if another consumer is polling or delivery is still in flight.

## 7. Integrating with Spring Boot

A Spring Boot application that only publishes messages does not need to know how many SQS queues are subscribed, and does not need the SQS SDK. The example uses **Spring Cloud AWS 3.x** with **SnsTemplate**.

**Gradle (Groovy DSL)**:

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-json")
}
~~~

Select a **springCloudAwsVersion** compatible with your project's Spring Boot version; use the BOM to manage versions consistently.

**application.yml**:

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

**Publisher**:

~~~java
package demo.notifications;

import io.awspring.cloud.sns.core.SnsTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationPublisher {
    private final SnsTemplate snsTemplate;
    private final String topicArn;

    public OrderNotificationPublisher(
            SnsTemplate snsTemplate,
            @Value("${app.sns.topic-arn}") String topicArn) {
        this.snsTemplate = snsTemplate;
        this.topicArn = topicArn;
    }

    public void sendOrderCreated(String orderId) {
        OrderCreated message = new OrderCreated("ORDER_CREATED", orderId);
        snsTemplate.sendNotification(topicArn, message, "Order created");
    }

    public record OrderCreated(String eventType, String orderId) {}
}
~~~

Here **SnsTemplate** uses the Jackson message converter to serialize the POJO to JSON; manual JSON string concatenation is unnecessary. In a real application, include **eventId** and **schemaVersion** in the event contract. If filtering by **MessageAttributes** is required, use Spring Messaging headers or the SDK **MessageAttributeValue** to send matching metadata.

**Runtime credentials:** The AWS SDK uses the credentials provider chain. In AWS, grant permissions to the runtime role; on development machines use an AWS CLI profile. Never embed access keys in source code. If the SDK reports AccessDenied on **sns:Publish**, check the role and topic policy before debugging SQS.

## 8. KMS Encryption and the Limits of Standard Policies

When encrypting with a **customer-managed KMS key**, an additional permission layer applies beyond IAM/topic/queue policies.

### 8.1. Queue Using SSE-KMS with a Customer-Managed Key

If the queue in account B uses a customer-managed KMS key, the **KMS key policy** must allow **sns.amazonaws.com** to use the appropriate actions so SNS can deliver messages into the queue, typically **kms:GenerateDataKey** and **kms:Decrypt**. Illustrative statement in the **KMS key policy**:

~~~json
{
  "Sid": "AllowSNSToEncryptForQueue",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*"
}
~~~

**Resource: "*" in a KMS key policy** refers to the KMS key to which the policy is attached; it is **not** a recommendation to grant **kms:*** across all keys to an application. In production, add appropriate source/account condition constraints per KMS/SQS documentation to avoid overly broad permissions. Workers reading an encrypted queue also need **kms:Decrypt** when required by KMS configuration. KMS key policies, IAM roles, and key types must be evaluated together.

### 8.2. Topic Also Using SSE-KMS

If the **SNS topic** itself is encrypted with a customer-managed key, the publisher may need additional KMS permissions; if an AWS service acts as publisher, the KMS key policy must allow the source service to perform the required operations. Queue KMS usage and topic KMS usage are two separate hops: verify each key ARN and its permissions according to the encryption setup.

### 8.3. Filters Do Not Solve Permission Issues

A **Subscription FilterPolicy** only decides whether a message matches delivery criteria. It **does not grant permissions** to publish, subscribe, or send to SQS; a message matching a filter without a valid queue policy can still fail to be delivered. Conversely, a message dropped because it does not match a filter is intended design behavior, not an AccessDenied error.

## 9. Diagnosing Each Type of AccessDenied and Delivery Failure

| Symptom | Where to Check | Action |
| --- | --- | --- |
| Spring Boot **AccessDenied** on Publish | Publisher IAM role, topic ARN, topic policy, SCP/permission boundary, topic KMS | Identify runtime principal; verify **sns:Publish** |
| Account B **AccessDenied** on Subscribe | Role B's IAM policy and A's SNS topic policy | Grant **sns:Subscribe** for the exact role/ARN, do not use wildcards |
| Subscription remains **PendingConfirmation** | Creator does not own the queue or endpoint has not confirmed | Confirm following the SNS procedure for SQS/endpoint |
| Publish succeeds but queue is empty | **SQS queue policy**, aws:SourceArn, subscription, queue ARN/URL, KMS, filter | Inspect queue policy and SNS delivery metrics |
| SNS delivers to queue but worker receives nothing | Worker IAM, SQS visibility timeout, competing consumers, queue URL | Check **sqs:ReceiveMessage**, metrics, and consumer logs |
| Worker receives but cannot delete | Worker IAM missing **sqs:DeleteMessage** or wrong receipt handle | Update permissions and DeleteMessage logic |
| Message reaches queue but worker fails to decode | **RawMessageDelivery** and SNS envelope format | Align subscription setting with parser |
| Multiple copies of the same event processed | At-least-once delivery or retries | Use **eventId** and an idempotent consumer |

Troubleshooting should begin at the first point where a request is denied: *who is calling what action on which ARN?* If **Publish succeeds** yet SQS has no messages, check the subscription, filter, and queue policy; inspect CloudWatch SNS metrics, delivery errors, and the subscription DLQ if configured. If the message is already in SQS, inspect the worker, retries, and SQS DLQ next.

An **SNS subscription DLQ** handles messages that SNS could not deliver to an endpoint. An **SQS consumer DLQ** handles messages that entered the main queue but failed worker processing across receive attempts. These two DLQs operate at different stages and must also have appropriate permissions configured.

### 9.1. Proactive Permission Verification Exercises

In an **AWS sandbox**, do not test by elevating a role to **AdministratorAccess**. Make intentional changes and observe:

1. Remove **sns:Publish** from the publisher role: Publish must be denied unless another valid Allow exists.
2. Remove **sns:Subscribe** from role B or the statement for role B on topic A: cross-account Subscribe requests must be denied.
3. Restore Subscribe permission, but remove the **sqs:SendMessage** statement from the queue policy: the subscription can exist, yet SNS cannot deliver messages to the queue.
4. Change **aws:SourceArn** in the queue policy to another topic ARN: messages from the original topic are blocked.
5. Restore the queue policy but set a non-matching filter: messages are filtered out and do not enter the queue, without necessarily causing a delivery failure.
6. With a KMS key on the queue, test permissions of the SNS principal and consumer in a test environment; observe encryption errors separately from SQS policy errors.

Operational experiments in a shared sandbox can affect delivery flows and message counts, so use dedicated test resources only. Restore policies via managed IaC after each scenario.

## 10. Review Questions and Hands-on Exercise

**Self-check questions:**

1. Why does a publisher role having **sns:Publish** not guarantee that the SQS queue receives messages?
2. In account A's topic policy, when must you add account B's role as a **Principal**?
3. Is **sns:Subscribe** evaluated on the topic ARN or the queue ARN?
4. Who is the principal in the queue policy when SNS delivers to SQS, and why should **aws:SourceArn** be the topic ARN?
5. Two accounts configured Subscribe, yet one stays in **PendingConfirmation**: how would you check who created the subscription first?
6. If a subscriber received a message but the consumer cannot delete it, which permission is missing?
7. Why can an overly broad Allow in an SQS queue policy create a **confused deputy** vulnerability?
8. Where might an encrypted topic and an encrypted queue require different KMS permission checks?

**Hands-on exercise:**

- Provision an SNS topic in account A and an SQS queue in account B.
- Attach an **sns:Publish** IAM policy to the Order Service role in A.
- Attach an **sns:Subscribe** IAM policy to the subscription admin role in B, and add an SNS topic statement granting permission to that role.
- Attach an SQS queue policy for **sns.amazonaws.com** with **aws:SourceArn** pointing to topic A.
- Create the subscription using a principal in account B and verify the subscription status.
- Publish an event and verify the queue receives it; run a consumer with permissions to read and delete messages.
- Intentionally introduce one fault in each permission layer, recording the failing API, error code, root-cause policy, and fix.

**Completion criteria:** the publisher can only publish to the exact topic; the subscription admin can only register the intended endpoint; SNS can only send to the queue from the designated topic; the consumer only has permissions on the queue it reads; every failure is traced back to the exact permission layer.

## 11. References

- [AWS SNS — Using identity-based policies](https://docs.aws.amazon.com/sns/latest/dg/sns-using-identity-based-policies.html): differences between IAM and SNS topic policies, plus condition keys **sns:Protocol**/**sns:Endpoint**.
- [AWS SNS — Subscribing an SQS queue to a topic](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html): queue policies and **aws:SourceArn**.
- [AWS SNS — Sending SNS messages to SQS in another account](https://docs.aws.amazon.com/sns/latest/dg/sns-send-message-to-sqs-cross-account.html): cross-account conditions and subscription confirmation.
- [AWS SQS — Subscribe a queue to SNS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html): steps on the queue owner side and per-account permissions.
- [AWS SNS — Access policy examples](https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-use-cases.html): practical topic and queue policies.
- [AWS SNS — Server-side encryption with encrypted SQS](https://docs.aws.amazon.com/sns/latest/dg/sns-enable-encryption-for-topic-sqs-queue-subscriptions.html): KMS permissions when SNS delivers to an encrypted SQS queue.
- [AWS SQS — Least-privilege KMS policies](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-least-privilege-policy.html): protecting keys, service producers, and consumers.
- [Spring Cloud AWS 3.x — Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.3.1/reference/html/index.html): SNS starter, SnsTemplate, AWS credentials/region.

**Expected outcome:** learners can independently configure a **Spring Boot → SNS → SQS** flow, clearly separating **sns:Publish**, **sns:Subscribe**, **sqs:SendMessage**, worker IAM, and key policies; while accurately verifying cross-account mechanics and diagnosing delivery issues across each permission boundary.
