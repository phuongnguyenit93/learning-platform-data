# Queue Encryption and Producer/Consumer Access Control

An e-commerce system may accept orders via a REST API, notify inventory, and process payments asynchronously. The event-emitting service (**producer**) sends messages to **Amazon Simple Queue Service (Amazon SQS)**; worker processes (**consumers**) receive messages, execute business logic, and delete each message once processing succeeds. If misconfigured, producers might send sensitive data into an unprotected queue, unauthorized actors could read or delete messages, or the system might fail with **`KMS.AccessDeniedException`** even when IAM already allows **`sqs:SendMessage`**.

This lesson belongs to the **Queues and Notifications** chapter of the **CLOUD_PROVIDERS_AWS** module. The material places SQS and SNS within an AWS architecture covering Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless. The goal is to design **encryption, producer/consumer permissions**, monitoring, resilience, and cost controls under **least privilege**.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the roles of **producer, queue, and consumer**, the message lifecycle, visibility timeout, and dead-letter queues (DLQs).
2. Distinguish **SSE-SQS**, **SSE-KMS with an AWS managed key**, **SSE-KMS with a customer managed KMS key**, TLS, and application-level encryption.
3. Identify what is covered by **message body encryption** versus metadata excluded from SSE.
4. Design **IAM identity policies**, **SQS resource-based queue policies**, **KMS key policies**, and VPC endpoint policies.
5. Explain why an SSE-KMS producer needs both **`kms:GenerateDataKey` and `kms:Decrypt`**, whereas a consumer needs **`kms:Decrypt`**.
6. Configure permissions for **SNS → encrypted SQS**, **Lambda polling SQS**, cross-account access, DLQs, and key rotation.
7. Practice with the AWS CLI and Java SDK v2, diagnose `AccessDenied` errors, and build a production checklist.

## 2. How Do Producers, Queues, and Consumers Work Together?

~~~mermaid
flowchart LR
    P["API / Lambda / ECS<br/>Producer"] -->|"SendMessage"| Q["Amazon SQS<br/>orders-events"]
    Q -->|"ReceiveMessage"| C["Lambda / ECS / EC2<br/>Consumer"]
    C -->|"Success:<br/>DeleteMessage"| Q
    C -. "Failure / visibility expired:<br/>may be redelivered" .-> Q
    Q -->|"maxReceiveCount"| DLQ["Dead-letter queue"]
    C --> DB["DynamoDB / RDS / S3"]
~~~

The **producer** sends messages via **`SendMessage`/`SendMessageBatch`**. The **consumer** calls **`ReceiveMessage`**, processes the work, and calls **`DeleteMessage`** using the receipt handle upon completion. During processing, the **visibility timeout** temporarily hides the message from other consumers. If processing fails or deletion does not happen in time, the message can be received again. A **redrive policy** can move repeatedly failing messages to a DLQ.

| Component | Responsibility | What must be protected |
|---|---|---|
| **Queue** | Holds messages prior to processing | Encryption, access policy, retention, DLQ |
| **Producer role** | Sends messages only to the target queue | `SendMessage` and KMS permissions to generate data keys |
| **Consumer role** | Receives, processes, and deletes messages | `Receive`/`Delete`/`ChangeVisibility`, decrypt |
| **Visibility timeout** | Time window for consumer processing | Prevents premature reprocessing on long jobs |
| **Dead-letter queue** | Isolates failing messages | Encryption, inspection permissions, and redrive access |
| **SNS topic** | Fans out one notification to multiple subscribers | Topic publishing policy and SQS queue policy |

**SQS does not guarantee end-to-end exactly-once business side effects.** Standard queues deliver at least once and may not preserve strict order. FIFO supports per-message-group ordering and conditional deduplication, yet consumers still require **idempotency, retries, and transaction safety**.

### 2.1. Recommended runtime roles

| Runtime | IAM principal to grant SQS permissions | Avoid |
|---|---|---|
| AWS Lambda | **Lambda execution role** | Hardcoding access keys in environment variables |
| ECS/Fargate | **ECS task role** | Confusing it with the task execution role used for images/logs |
| EC2 | **EC2 instance profile role** | Baking access keys into AMIs |
| EKS | **EKS Pod Identity / IRSA** where appropriate | Pods inheriting an overly broad node IAM role |
| CI/CD or operator | Dedicated admin role with controlled change rights | Letting producer roles call `PurgeQueue`/`DeleteQueue` |

SQS is an **AWS Regional** service, not a queue placed inside a VPC subnet; applications in private subnets reach the SQS regional endpoint via a **VPC interface endpoint** or another permitted network path.

## 3. Three Encryption-at-Rest Options in SQS

SQS supports **server-side encryption (SSE)**. AWS enabled **default SSE-SQS encryption for new queues starting in 2022** when no other option is specified. Always **inspect the actual queue's attributes**, because older or reconfigured queues may use a different mode or have SSE disabled.

| Option | Protecting key | Strengths | What you must manage |
|---|---|---|---|
| **SSE-SQS** | SQS-owned key, AES-256 | Self-managed encryption, minimal complexity | IAM/SQS policy; no separate KMS permissions needed at runtime |
| **SSE-KMS with AWS managed key** | AWS KMS key **`alias/aws/sqs`** | Uses KMS without authoring a custom key policy | Cannot edit key policy; limits certain integrations/cross-account use |
| **SSE-KMS with customer managed key** | Customer-managed KMS key | Customizable permissions, lifecycle, audit, service/cross-account integrations | IAM + key policy, key rotation, KMS quotas, and charges |

**SSE-SQS is not the same as SSE-KMS using `alias/aws/sqs`.** Both modes cannot be active simultaneously on one queue. Key attributes to know:

- **`SqsManagedSseEnabled`:** indicates encryption with an SQS-owned key.
- **`KmsMasterKeyId`:** KMS key ID, ARN, or alias used for SSE-KMS.
- **`KmsDataKeyReusePeriodSeconds`:** how long SQS reuses a data key, from **60 to 86,400 seconds**, defaulting to **300 seconds**.

### 3.1. SSE-SQS requires no separate KMS IAM permissions

With SSE-SQS, once the producer is permitted by IAM/SQS policy to send and the consumer to receive, SQS encrypts and decrypts the message body automatically. No **`kms:GenerateDataKey`/`kms:Decrypt`** grants are needed on runtime roles just for SSE-SQS. This option fits when encryption at rest is required without needing customer-managed KMS key control.

### 3.2. SSE-KMS uses envelope encryption

~~~mermaid
flowchart TD
    P["Producer SendMessage"] --> SQS["Amazon SQS"]
    SQS -->|"GenerateDataKey when needed"| KMS["AWS KMS<br/>Customer managed / alias aws/sqs"]
    KMS -->|"Data key and encrypted key"| SQS
    SQS --> STORE["Store encrypted message body"]
    STORE -->|"ReceiveMessage"| SQS
    SQS -->|"Decrypt data key when needed"| KMS
    SQS -->|"Return plaintext body over API to authorized caller"| C["Consumer"]
~~~

In **envelope encryption**, the KMS key protects a **data encryption key (DEK)**; SQS uses the DEK to encrypt and decrypt the message body. Producers and consumers call the **SQS API** without calling KMS per message themselves, yet KMS permissions are still evaluated for the caller whenever SQS must operate on the key on their behalf.

### 3.3. Which fields does SSE encrypt?

AWS specifies that **SSE encrypts the message body**, and does not encrypt:

- **Queue metadata:** queue name and queue attributes.
- **Message metadata:** message ID, timestamps, and **message attributes**.
- **Per-queue metrics**.

Example business body:

~~~json
{
  "orderId": "ord-example-104",
  "customerReference": "cust-example-79",
  "eventType": "ORDER_CREATED"
}
~~~

If PII sits inside **message attributes** or queue names, **never assume it is protected by SSE**. Keep sensitive data out of tags, headers, logs, and metadata. If end-to-end payload confidentiality is required even against authorized SQS layers, consider **client-side/application-level encryption** with application-managed keys.

### 3.4. TLS and existing messages

**Encryption at rest does not replace HTTPS/TLS in transit.** For SSE-enabled queues, requests require HTTPS and Signature Version 4. You can add a **queue policy denying insecure transport** as an extra guardrail.

Changing a queue's encryption setting **does not re-encrypt the existing backlog**. Messages enqueued before enabling SSE are not retroactively encrypted; already-encrypted messages continue to require their original key even after settings change. Therefore, when rotating to a new KMS key, never disable or delete the old key before every message encrypted under it has been processed or drained.

## 4. Multiple Authorization Layers Evaluated Together

~~~mermaid
flowchart TD
    R["Producer / Consumer IAM role"] --> IAM["IAM identity policy<br/>Allows SQS actions"]
    IAM --> Q["SQS queue policy<br/>Principals, network, SourceArn"]
    Q --> ENC{"SSE mode"}
    ENC -->|"SSE-SQS"| OK["SQS processes request<br/>unless another Deny blocks it"]
    ENC -->|"SSE-KMS"| KEY["KMS key policy and IAM<br/>GenerateDataKey / Decrypt"]
    KEY --> OK
    GUARD["SCP, boundary, session policy,<br/>VPC endpoint policy, explicit Deny"] -. "May restrict" .-> OK
~~~

| Layer | Function | Example |
|---|---|---|
| **IAM identity policy** | Grants SQS API actions to a role/user | Producer: **`sqs:SendMessage`** |
| **SQS queue policy** | Resource policy for principals, services, cross-account, and guardrails | Allows SNS topic to send; denies non-TLS requests |
| **KMS key policy** | Grants or delegates IAM permissions to use the KMS key | Only specific roles/service sources may `Decrypt`/`GenerateDataKey` |
| **IAM KMS permission** | Allows principal to use the KMS key when key policy permits | Consumer: **`kms:Decrypt`** on the key ARN |
| **SCP, permission boundary, session policy** | Caps maximum effective permissions | Blocks KMS actions outside allowed conditions |
| **VPC endpoint policy** | Restricts access traversing the endpoint | Only specific queues/roles permitted through interface endpoint |

**An IAM Allow never overrides an Explicit Deny.** For example, a producer with **`sqs:SendMessage`** but lacking KMS permissions can fail on an SSE-KMS queue. Similarly, a queue policy denying requests outside a VPCE can block a role even when IAM permits it.

### 4.1. Same-account, cross-account, and AWS services

- **Same-account IAM principal:** an `Allow` in either the identity policy **or** the queue resource policy can grant access under IAM evaluation, provided no `Deny` or guardrail blocks it. Clean auditable practice: use IAM role policies for applications and queue policies for guardrails and service integrations.
- **Cross-account principal:** requires an `Allow` in **both the caller account's identity policy** and **the owning account's queue policy**, plus cross-account KMS grants when using SSE-KMS.
- **AWS services** such as SNS, S3, or EventBridge delivering events: require a **queue policy granting the service principal** constrained by **`aws:SourceArn`**/**`aws:SourceAccount`**. For SSE-KMS queues, also grant the service in the **customer-managed KMS key policy**.

Avoid using **`Principal = "*"` in an unconditional `Allow`** to troubleshoot errors. A **`Deny`** statement with principal `"*"` enforcing TLS is a different case and must still be tested against integrated AWS services.

## 5. Producer / Consumer / Operator Permission Matrix

| Action | Producer | Consumer | Operator |
|---|---|---|---|
| **`sqs:SendMessage`** | Required | Not by default | During intentional redrive/publish |
| **`sqs:ReceiveMessage`** | No | Required | Only for authorized message inspection |
| **`sqs:DeleteMessage`** | No | Required after processing succeeds | During authorized redrive |
| **`sqs:ChangeMessageVisibility`** | No | Needed for long jobs | Usually no |
| **`sqs:GetQueueAttributes`** | SDK-dependent | Usually needed | Needed for inventory/audits |
| **`sqs:GetQueueUrl`** | When resolving queue by name | When resolving queue by name | Needed for inventory/audits |
| **`sqs:SetQueueAttributes`** | No | No | IaC / admin roles only |
| **`sqs:PurgeQueue`/`DeleteQueue`** | No | No | Sensitive permissions requiring strict controls |
| **`kms:GenerateDataKey`** (SSE-KMS) | Required | No if read-only | Needed when redriving into an SSE-KMS queue |
| **`kms:Decrypt`** (SSE-KMS) | Required | Required | Needed when reading/redriving encrypted messages |

**Why does a producer also need `kms:Decrypt`?** When the **data key reuse period** expires, the next **`SendMessage`/`SendMessageBatch`** call can cause SQS to call both **`GenerateDataKey`** and **`Decrypt`** to validate the new data key. A producer granted only `GenerateDataKey` may succeed briefly before starting to fail.

An SSE-KMS consumer needs **`kms:Decrypt` on every KMS key used to encrypt messages still residing in the queue**. If the key was changed while older backlog remains, permissions on only the new key are insufficient to drain the queue.

### 5.1. Least-privilege boundaries for data and cost protection

Producers do not need **`ReceiveMessage`**. Consumers do not need **`SendMessage`** if they only process and delete. Actions like **`PurgeQueue`**, **`DeleteQueue`**, and **`SetQueueAttributes`** can wipe data or disable protections across the entire system; keep them out of runtime roles and behind change management.

## 6. Example IAM Policy for an SSE-KMS Producer

Assume:

| Resource | Example value |
|---|---|
| Region | **ap-southeast-1** |
| AWS account | **111122223333** |
| Queue | **orders-events** |
| Queue ARN | **arn:aws:sqs:ap-southeast-1:111122223333:orders-events** |
| KMS key ARN | **arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID** |
| Producer runtime | **ECS task role / EC2 instance role / Lambda execution role** |

Attach the policy below to the **producer IAM role**. Replace placeholder ARNs with real ARNs before use:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendToOnlyOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    },
    {
      "Sid": "UseOnlyOrdersQueueKmsKeyForProducer",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID"
    }
  ]
}
~~~

**Do not grant `sqs:ReceiveMessage`, `sqs:DeleteMessage`, or `sqs:PurgeQueue`** to a send-only producer. If the app looks up the queue URL by name, add **`sqs:GetQueueUrl`** on that queue as needed. KMS permissions take effect only when the **key policy** permits that role to use the KMS key or delegates authorization to account IAM policies.

### 6.1. Tightening KMS permissions with conditions

With a customer-managed KMS key, organizations may restrict usage via **`kms:ViaService`** and encryption context where supported by AWS KMS/SQS—for example, allowing key use only through **`sqs.ap-southeast-1.amazonaws.com`**. Never add conditions to a production key policy without verifying the **actual request context**, especially with cross-account flows, SNS/S3/EventBridge service principals, and redrive tasks.

**Do not attach an SNS `aws:SourceArn` condition to an application producer role's IAM policy expecting it to behave like SNS.** Service-to-service calls and direct SDK calls carry different principals and contexts.

## 7. Example IAM Policy for a Consumer

A Java worker on ECS using an **ECS task role** could use:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ProcessOnlyOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    },
    {
      "Sid": "DecryptOrdersMessages",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID"
    }
  ]
}
~~~

**`ChangeMessageVisibility`** is needed only if the consumer extends or resets visibility. **`GetQueueAttributes`** is commonly called by polling clients/libraries to inspect settings. If the worker reads a DLQ or messages encrypted under **multiple keys over time**, grant permissions scoped to those specific **DLQ ARNs** and **KMS key ARNs**—never open `kms:Decrypt` on `*`.

### 7.1. Consumers must delete messages at the right time

A well-behaved consumer should:

1. Receive the message and retain **`messageId`** and **`receipt handle`**.
2. Validate schema and execute an idempotent handler.
3. On success, call **`DeleteMessage`** with the **current receive's receipt handle**.
4. On failure, skip deletion and let retries or the DLQ handle it per design.
5. For long jobs, size **`visibility timeout`** or use bounded **`ChangeMessageVisibility`** calls.

**Deleting before committing the transaction can lose work.** Conversely, committing successfully and crashing before `DeleteMessage` can trigger redelivery. Idempotency and transactional design bridge that gap.

### 7.2. Permission to read SQS does not equal permission to read databases

Having **`kms:Decrypt`** for the queue does not grant access to other KMS-encrypted data, DynamoDB, or S3. Downstream resources require their own IAM permissions, resource policies, VPC networking, and authentication. Likewise, having **`sqs:ReceiveMessage`** on an SSE-KMS queue alone will not yield plaintext unless the KMS key policy also grants access.

## 8. Queue Policies: Principals, TLS, and Source Restrictions

An **SQS queue policy** is a **resource-based policy** attached directly to a queue to allow AWS services or cross-account principals to send messages, or to enforce guardrails. Unlike an **IAM identity policy**, a resource policy specifies a **`Principal`** and conditions such as **`aws:SourceArn`**, **`aws:SourceAccount`**, **`aws:SecureTransport`**, and **`aws:sourceVpce`** where supported.

### 8.1. Denying unencrypted HTTP

An illustrative statement to include in a **queue policy**:

~~~json
{
  "Sid": "DenyInsecureTransport",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "sqs:*",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events",
  "Condition": {
    "Bool": {
      "aws:SecureTransport": "false",
      "aws:PrincipalIsAWSService": "false"
    }
  }
}
~~~

This is a **single statement**, not a complete policy document. The **`aws:PrincipalIsAWSService`** condition prevents accidentally denying direct AWS service principals in service-to-service contexts that lack standard transport context. Still verify every AWS service actually calling the queue, especially if a service assumes an IAM role rather than calling as a service principal.

**Never turn a `Deny` into an `Allow` with `Principal: "*"`.** SQS SSE also requires HTTPS/SigV4; an explicit `Deny` acts as an extra guardrail against misconfiguration and makes audit posture explicit.

### 8.2. VPC endpoints and queue policies

If consumers run in a private VPC, an **SQS interface endpoint** lets them reach SQS without traversing the Internet or a NAT Gateway for that traffic. Two layers apply:

- **VPC endpoint policy:** restricts which principals, actions, and queues can traverse the endpoint.
- **SQS queue policy:** can use **`aws:sourceVpce`** to restrict access to a specific endpoint.

Architectural example:

~~~mermaid
flowchart LR
    WORKER["ECS / EC2 private subnet"] -->|"HTTPS 443"| VPCE["SQS Interface VPC Endpoint"]
    VPCE --> SQS["SQS orders-events"]
    SQS -->|"SSE-KMS when needed"| KMS["AWS KMS"]
    ROLE["ECS task role / EC2 profile"] -. "IAM permissions" .-> WORKER
    QUEUE["Queue policy: VPCE/TLS guardrails"] -. "Resource authorization" .-> SQS
~~~

**Do not blindly deny all requests lacking a `VPCE`** if SNS, S3, EventBridge, or another AWS service must deliver messages **directly via a service principal**. Service-to-service calls carry different network contexts and would get denied. Craft precise exceptions for authorized principals/services/sources, and test fan-out after every change.

KMS does not ride inside the SQS VPC endpoint. If your application calls the KMS API directly from a private subnet, you may need a **KMS interface endpoint** or another network path; when SQS invokes SSE-KMS on the caller's behalf, distinguish internal service-to-service calls from your SDK caller's network path.

### 8.3. Preventing confused deputy with `SourceArn` and `SourceAccount`

When an AWS service delivers to SQS on behalf of another resource, the queue policy should pin the **exact source**:

- **`aws:SourceArn`:** ARN of the authorized SNS topic, EventBridge rule, or event-emitting resource.
- **`aws:SourceAccount`:** AWS account owning the source when supported by the service/context.
- **`Principal.Service`:** exact producer service, e.g., **`sns.amazonaws.com`**.

This mitigates **confused deputy** attacks: another principal cannot trick a trusted service into pushing messages to your queue from an unauthorized source. Verify which condition keys the integrated service actually populates; missing keys in the request context prevent the statement from matching.

## 9. SNS → Encrypted SQS: Open Both SQS and KMS

With **Amazon SNS fan-out**, the application publisher calls **`sns:Publish`** on the SNS topic—**not** `SendMessage` directly on subscribed SQS queues. **SNS** then acts as the producer delivering notifications to each subscribed SQS queue.

~~~mermaid
flowchart LR
    PUB["Publisher app"] -->|"sns:Publish"| SNS["SNS orders-topic"]
    SNS -->|"sqs:SendMessage"| Q1["SQS orders-billing<br/>SSE-KMS"]
    SNS -->|"sqs:SendMessage"| Q2["SQS orders-warehouse<br/>SSE-KMS"]
    Q1 --> L["Lambda consumer<br/>kms:Decrypt"]
    Q2 --> ECS["ECS consumer<br/>kms:Decrypt"]
    KMS["Customer-managed<br/>KMS key policy"] -. "Allow SNS to use<br/>GenerateDataKey/Decrypt" .-> Q1
    KMS -. "Matching key for Q2" .-> Q2
~~~

### 9.1. Queue policy allowing a specific SNS topic

Illustrative statement **attached to the `orders-billing` queue**:

~~~json
{
  "Sid": "AllowOnlyOrdersTopic",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-billing",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-topic"
    },
    "StringEquals": {
      "aws:SourceAccount": "111122223333"
    }
  }
}
~~~

**This is a queue policy fragment, not an SNS topic policy.** The app publisher needs **`sns:Publish`** on the topic; creating subscriptions requires matching subscription permissions/policies. The SQS queue must trust the **SNS** service principal, not merely the application's publisher role.

### 9.2. KMS key policy allowing SNS to publish to an SSE-KMS queue

For an SSE-KMS queue using a customer-managed KMS key, grant **`sns.amazonaws.com`** in the **key policy** of that exact KMS key. Illustrative statement:

~~~json
{
  "Sid": "AllowSNSServiceUseKeyForSqs",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "aws:SourceAccount": "111122223333"
    }
  }
}
~~~

**`Resource: "*"` inside a KMS key policy statement** refers only to the key carrying that policy; it does not grant SNS access to every KMS key in the account. This is **only one statement**—a complete key policy also requires administrative grants, consumer permissions, and recovery safeguards. Tighten further with **`SourceArn`** when supported by the service/scenario and verified against actual request context.

**The AWS-managed KMS key `alias/aws/sqs` does not let you edit its key policy.** Therefore, when SNS, S3, EventBridge, or cross-account publishers deliver to an encrypted SQS queue and require custom service-principal KMS grants, the standard choice is a **customer-managed KMS key**. Do not confuse SSE on the SNS topic with SSE on the subscribed SQS queue; each side has its own key policy, permissions, and charges.

### 9.3. EventBridge, S3 notifications, and other sources

Sources such as **EventBridge rules**, **S3 event notifications**, and **SNS subscriptions** can deliver messages to SQS where supported. Each path needs:

1. Service/producer permissions in the **SQS queue policy**.
2. Under SSE-KMS, **`kms:GenerateDataKey`/`kms:Decrypt`** permissions in the **customer-managed KMS key policy** for the source service.
3. Properly configured rules, subscriptions, filters, and target ARNs in compatible Regions/accounts, respecting each source's FIFO/Standard support.

Never inspect only the initial application's IAM role and assume SNS permissions suffice. **SNS, S3, and EventBridge are distinct service principals**, each with its own event behavior and condition keys to verify.

## 10. Cross-Account Producers and Consumers

Suppose **Account A** hosts the producer and **Account B** owns the SQS queue:

| Step | Where configured | Requirement |
|---|---|---|
| **1. Identity policy** | Account A | Producer role has **`sqs:SendMessage`** on B's queue ARN |
| **2. Queue policy** | Account B | Allows the specific role/account A to call `SendMessage` on B's queue |
| **3. KMS key policy** (if SSE-KMS) | Account B or key-owning account | Grants Account A's principal required KMS actions via a customer-managed key |
| **4. IAM KMS permission** | Account A | Allows producer to use the shared KMS key ARN |
| **5. SCP/endpoint/network** | Both accounts | No `Deny` blocking the path or service integration |

Example **queue policy statement** for a specific role in Account A:

~~~json
{
  "Sid": "AllowOneExternalProducer",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/external-orders-producer"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
}
~~~

A cross-account consumer needs **`Receive`/`Delete`/`GetQueueAttributes`** following the same pattern, plus `Decrypt` for SSE-KMS. With cross-account SSE-KMS, **you cannot edit the AWS-managed KMS key policy** to grant external access; use a **customer-managed key** configured for cross-account access.

**Note:** a role trust policy and `sts:AssumeRole` are needed only if Account A is designed to **assume a role in Account B**. When Account A's producer calls SQS directly using Account A's IAM role as permitted by the queue policy, that is **resource-based cross-account authorization** and does not require assuming a role in B.

### 10.1. Knowing a queue URL does not grant access

Possessing a queue URL or ARN **confers zero access permissions**. Every request must still be signed by an IAM principal's credentials and evaluated by IAM, queue, KMS, and endpoint policies. A queue URL is an API address, not a secret.

## 11. Lambda as a Consumer of Encrypted SQS

With **AWS Lambda event source mapping** for SQS, the Lambda service polls the queue, fetches batches, and invokes your function. The **Lambda execution role** needs at minimum:

- **`sqs:ReceiveMessage`**
- **`sqs:DeleteMessage`**
- **`sqs:GetQueueAttributes`**
- **`kms:Decrypt`** if the queue is encrypted with a KMS key requiring explicit grants

Often the managed policy **`AWSLambdaSQSQueueExecutionRole`** provides the baseline SQS permissions, though you should inspect the current policy and **add KMS key permissions only as needed**. For cross-account queues or customer-managed KMS keys, verify queue policies, key policies, and same-Region constraints on the event source mapping.

~~~mermaid
flowchart TD
    SQS["Encrypted SQS queue"] --> POLL["Lambda event source mapping<br/>Poll + batch"]
    POLL -->|"Invoke batch"| FN["Lambda function<br/>Execution role"]
    FN -->|"Success"| DELETE["Lambda/SQS deletes<br/>processed messages"]
    FN -->|"Error / partial failure"| RETRY["Retry after visibility<br/>or DLQ"]
    KMS["KMS key"] -. "Execution role: Decrypt" .-> POLL
~~~

### 11.1. Visibility timeout and batch failures

A message can be delivered multiple times when handlers fail, time out, or consumers are interrupted. When integrating Lambda with SQS:

- Set **visibility timeout** high enough for function execution, retries, and throttling; AWS advises at least **6 times the function timeout** in typical setups, adjusted for any batching window.
- Depending on the use case, enable **partial batch responses** with **`ReportBatchItemFailures`** to retry only failed messages instead of the whole batch.
- Keep consumers **idempotent** and respect FIFO message-group ordering when partial failures occur.
- Cap concurrency if downstream RDS or APIs cannot absorb sudden spikes.

**A Lambda consumer role does not need `sqs:SendMessage` to read a queue.** By contrast, a **producer Lambda** sending into a queue needs `SendMessage` plus `GenerateDataKey`/`Decrypt` under SSE-KMS. Grant permissions by **action performed**, not by the service name Lambda.

## 12. Dead-Letter Queues (DLQs), Encryption, and Redrive

A **DLQ** captures messages exceeding **`maxReceiveCount`** in the source queue's redrive policy. It serves diagnostics and controlled retries—not indefinite backup storage. Give the DLQ long enough retention for operators to detect and analyze failures before messages expire.

### 12.1. Common encryption misconception when moving to a DLQ

Per SQS documentation, **SQS moving a message to a DLQ does not change that message's encryption**:

| Source queue | DLQ | State of moved message |
|---|---|---|
| SSE-KMS encrypted | SSE-SQS / unencrypted | A message encrypted with the source KMS key still requires the **source key** to decrypt |
| Unencrypted | SSE-KMS DLQ | A moved message does not become encrypted under the DLQ's KMS key |
| Source rotated keys over time | DLQ holds messages from multiple periods | Consumers/redrive may need **both old and new KMS keys** |

**Never rely on a DLQ to “encrypt” an unencrypted backlog.** Likewise, never disable a source customer-managed KMS key right after messages move to a DLQ; reading or redriving them may still require that key.

### 12.2. Permissions to inspect a DLQ vs. permissions to redrive

An operator inspecting a DLQ needs **`ReceiveMessage`** and, to read SSE-KMS bodies, **`kms:Decrypt`** on the right key. By contrast, running **`StartMessageMoveTask`** to move messages in bulk from a DLQ back to the source or another queue requires a distinct permission set:

| Resource | Redrive-related permissions |
|---|---|
| **Source DLQ of move task** | **`sqs:StartMessageMoveTask`**, **`sqs:ReceiveMessage`**, **`sqs:DeleteMessage`**, **`sqs:GetQueueAttributes`** |
| **Destination queue** | **`sqs:SendMessage`** |
| **KMS keys for DLQ / older messages** | **`kms:Decrypt`** if encrypted |
| **KMS key of destination queue** | **`kms:GenerateDataKey`** and **`kms:Decrypt`** when using SSE-KMS |
| **Monitor/cancel move task** | **`sqs:ListMessageMoveTasks`** and **`sqs:CancelMessageMoveTask`** as authorized |

The DLQ's **SQS redrive allow policy** controls which source queues may target that DLQ; it is **not** the same as the **queue access policy** or the operator's IAM policy.

Redriving a backlog can cause consumers to reprocess many transactions. Before starting, verify the **root cause is fixed**, idempotency, ordering (especially FIFO), redrive rate, downstream capacity, and data permissions. Never permit bulk redrives from regular runtime roles.

### 12.3. Illustrative redrive policy

A source queue can define its redrive policy attribute as:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-dlq",
  "maxReceiveCount": "5"
}
~~~

This is the **value of `RedrivePolicy`**, not an IAM policy. Source queue and DLQ must share **compatible queue types** (Standard with Standard, FIFO with FIFO); validate service permissions, retention, and live data before applying changes. **`maxReceiveCount = 5`** is only an example, not a universal threshold.

## 13. KMS Key Rotation, Data Key Reuse, and Total Cost

### 13.1. Data key reuse period

SQS SSE-KMS **reuses data keys** over a configurable interval to reduce KMS API calls. Parameter:

~~~text
KmsDataKeyReusePeriodSeconds = 60 ... 86400
Default = 300
~~~

A short reuse period increases KMS API calls and costs; a longer period cuts overhead within your organization's security and audit policies. SQS also scopes caching by **requester** credentials and certain policy contexts, so you cannot simply divide message count by reuse period to predict exact KMS call volume.

**Do not think setting a 300-second reuse period means messages are only encrypted for 5 minutes.** Message bodies stay encrypted at rest until SQS deletes them; the reuse period governs **data key caching** and KMS call frequency.

### 13.2. Changing keys vs. automatic key rotation

Two distinct concepts:

- **KMS automatic/on-demand key rotation:** KMS rotates the backing key material of the **same logical key** where supported; older ciphertexts remain decryptable under that key's lifecycle.
- **Switching a queue to a different KMS key ARN:** existing messages retain their original encryption key. You must keep the **old KMS key active with decrypt permissions** until all older messages in the main queue, DLQ, and related records are drained.

Disabling or deleting the old key too early causes **`KMS.DisabledException`**, **`KMS.NotFoundException`**, or **`AccessDenied`** when reading remaining backlog—even if the queue now shows the new key.

### 13.3. Cost items to budget

| Item | Calculation / consideration |
|---|---|
| **SQS API requests** | Send, Receive, Delete, batches, long polling, and actual call volume |
| **SSE-SQS** | No separate KMS charges for SQS-owned encryption |
| **SSE-KMS** | Monthly KMS key storage fee for customer-managed keys plus KMS API request charges |
| **Data key reuse period** | Affects KMS request volume and potential KMS throttling errors |
| **DLQ/retries** | Extra receives/sends, logs, and engineering triage time |
| **SNS/EventBridge** | Publish, delivery, ingestion, and retry charges |
| **Compute** | Lambda invocations/duration or ECS/EC2 capacity |
| **Networking/logging** | Interface endpoints, data transfer, CloudWatch, and CloudTrail data events if enabled |

Do not choose SSE-KMS solely from a single low reference price line item. Base the decision on **compliance, key policies, cross-account integrations, auditability, KMS quotas**, and operational cost using current pricing for your Region and workload.

## 14. AWS CLI Inventory for Encryption and Queue Permissions

**The commands below are read-only** and safe to run in an authorized lab or account. Substitute your Region, queue name, and AWS profile.

### 14.1. Verify IAM principal and queue ARN

~~~bash
# Who is signing AWS requests?
aws sts get-caller-identity --output json

# Resolve QueueUrl from queue name.
aws sqs get-queue-url \
  --region ap-southeast-1 \
  --queue-name orders-events \
  --output json

# Inspect ARN, SSE mode, key, queue policy, and DLQ settings.
aws sqs get-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attribute-names QueueArn SqsManagedSseEnabled KmsMasterKeyId KmsDataKeyReusePeriodSeconds Policy RedrivePolicy RedriveAllowPolicy \
  --output json
~~~

Output omits attributes not configured on that queue. For **SSE-SQS**, verify **`SqsManagedSseEnabled = true`**; for **SSE-KMS**, inspect **`KmsMasterKeyId`**. Never assume “missing `KmsMasterKeyId`” means the queue is completely unencrypted.

### 14.2. Inspect KMS key and scheduled deletion

~~~bash
aws kms describe-key \
  --region ap-southeast-1 \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID \
  --query 'KeyMetadata.{Arn:Arn,State:KeyState,Enabled:Enabled,KeyManager:KeyManager,DeletionDate:DeletionDate}' \
  --output json
~~~

If the key resides in another account, metadata read restrictions or cross-account policies can block this command. **`DescribeKey` succeeding does not prove `GenerateDataKey`/`Decrypt` are permitted**; check the key policy, IAM, permission boundaries, SCPs, and KMS errors.

### 14.3. Configure encryption in a test environment

These commands **mutate SQS resources**; run them only with authorization and a plan for backlog and key lifecycles:

~~~bash
# Example: assign a customer-managed KMS key to a lab queue.
aws sqs set-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attributes KmsMasterKeyId=arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID,KmsDataKeyReusePeriodSeconds=300
~~~

This sample assumes the queue is in a compatible state to switch to SSE-KMS. Because SQS allows only one SSE mode at a time, if the queue currently uses **SSE-SQS**, verify how **`SqsManagedSseEnabled`** and SSE-KMS transition under current AWS CLI/API rules so conflicting options are not sent together. Always re-read attributes after writing.

**Never disable encryption** or switch to a key missing producer/consumer grants. Test first with synthetic messages in staging, verifying queue access, KMS permissions, DLQs, and fan-out integrations.

### 14.4. Test Send/Receive in a lab

The following commands **mutate queue state** and should only run with dummy payloads on a non-production lab queue:

~~~bash
# Lab producer, containing no PII or secrets.
aws sqs send-message \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --message-body '{"eventType":"LAB_TEST","id":"test-001"}'

# Lab consumer receiving at most 1 message; note message enters in-flight state.
aws sqs receive-message \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --max-number-of-messages 1 \
  --wait-time-seconds 10
~~~

Never run **`ReceiveMessage`** on a production queue just to “peek”, because it alters visibility and can disrupt live consumers. To validate permissions, test with **two separate IAM roles in a lab**: the producer can `Send` but gets denied on `Receive`; the consumer can `Receive`/`Delete` but gets denied on `Send`; unauthorized roles must receive `AccessDenied`.

## 15. AWS SDK for Java v2: Separating Producer and Consumer Responsibilities

AWS SDK for Java v2 uses the **default credentials provider chain** to obtain temporary credentials from a Lambda execution role, ECS task role, EC2 instance role, or configured profile. **Never hardcode AWS access keys in Java source code, Docker images, or Git**.

### 15.1. Producer sending a message

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrdersProducer {
    private static final String QUEUE_URL =
        "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events";

    public static void main(String[] args) {
        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            sqs.sendMessage(SendMessageRequest.builder()
                .queueUrl(QUEUE_URL)
                .messageBody("{\"eventType\":\"LAB_TEST\",\"id\":\"test-001\"}")
                .build());
        }
    }
}
~~~

With SSE-KMS, application code **does not encrypt the body before `SendMessage`**. SQS applies the queue's encryption settings; the process's role simply needs **`sqs:SendMessage`** and the producer KMS permissions. The sample payload contains no real data; production requires JSON serialization, schema versioning, correlation IDs, backoff retries, and idempotency.

### 15.2. Consumer: `DeleteMessage` only after processing succeeds

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;

public final class OrdersConsumer {
    private static final String QUEUE_URL =
        "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events";

    public static void main(String[] args) {
        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            var result = sqs.receiveMessage(ReceiveMessageRequest.builder()
                .queueUrl(QUEUE_URL)
                .maxNumberOfMessages(5)
                .waitTimeSeconds(10)
                .build());

            for (Message message : result.messages()) {
                // Lab-only: idempotent processing; production must validate schema.
                boolean processed = process(message.body());
                if (processed) {
                    sqs.deleteMessage(DeleteMessageRequest.builder()
                        .queueUrl(QUEUE_URL)
                        .receiptHandle(message.receiptHandle())
                        .build());
                }
                // If false: do not delete; message can retry or move to DLQ.
            }
        }
    }

    static boolean process(String body) {
        // Demo only, executes no side effects.
        return body.contains("LAB_TEST");
    }
}
~~~

This short sample **is not a complete production consumer**: production code needs a polling loop, lifecycle/shutdown handling, retries, exception handling, an idempotency store, DLQ alerts, visibility extensions, and concurrency limits. When processing produces side effects and the consumer dies before `DeleteMessage`, the message can be redelivered—so **at-least-once** must be designed in from day one.

## 16. Workflow for Deploying a Secure Encrypted Queue

### Step 1 — Classify data and paths

Identify whether producers are app IAM roles, **SNS**, **S3**, **EventBridge**, or external accounts. Are consumers Lambda event source mappings, ECS tasks, or EC2 services? Map sources and destinations explicitly, for example:

~~~mermaid
flowchart LR
    USER["REST API"] --> APP["Lambda producer<br/>IAM role A"]
    APP -->|"SendMessage"| Q["orders-events<br/>SSE-KMS CMK"]
    Q -->|"ReceiveMessage"| WORKER["ECS consumer<br/>IAM task role B"]
    WORKER -->|"Idempotent write"| DB["DynamoDB"]
    Q --> DLQ["orders-events-dlq"]
    KMS["Customer-managed KMS key"] -. "Producer: GenerateDataKey/Decrypt<br/>Consumer: Decrypt" .-> Q
    IAM["IAM + queue + key policies"] -. "Least privilege" .-> Q
~~~

The output should be a matrix of **principal × queue × action × encryption key × network path**, with owners and data-residency/retention rules. Put **minimal business data** in the message body and never embed passwords or access tokens.

### Step 2 — Choose encryption mode

- **SSE-SQS** if default encryption at rest suffices without custom KMS key policies.
- **SSE-KMS customer managed key** if fine-grained KMS permissions, key rotation governance, or service/cross-account integrations exceed AWS-managed key capabilities.
- Verify support across **Region, source services, and queue type**, and account for KMS fees, quotas, and key-recovery plans.

**Choose a customer-managed KMS key before configuring SNS/S3/EventBridge** whenever those services need explicit key-policy grants; changing modes midstream affects producers, consumers, and queued backlogs.

### Step 3 — Separate IAM roles

Create a **producer role** limited to sending; a **consumer role** limited to receiving, deleting, and decrypting; and an **infrastructure deployment role** managing queue and key policies. Give each role a trust policy matching its runtime. For SSE-KMS, ensure the key policy allows IAM delegation or directly names the specific principals and service sources.

### Step 4 — Configure queue policies and networking

Add queue policies for **service principals/`SourceArn`** or cross-account IAM principals. Include TLS guardrails; when using VPCEs, confirm VPC clients traverse the endpoint while service integrations remain unblocked. For private subnets, check DNS, endpoint security groups, TCP 443, NACLs, and route tables.

### Step 5 — Protect DLQs and key lifecycles

Create a matching-type DLQ, redrive policy, redrive allow policy, encryption, retention, and restricted inspection/redrive operator permissions. Track messages encrypted with older keys; never disable an old key while messages or recovery workflows still depend on it.

### Step 6 — Run positive and negative permission tests

At minimum test:

| Test | Expected |
|---|---|
| Producer role calls `SendMessage` on target queue | **Allow** |
| Producer role calls `ReceiveMessage` | **Deny** |
| Consumer role calls `Receive`/`Delete` on target queue | **Allow** |
| Consumer role calls `SendMessage` | **Deny** unless explicitly assigned |
| SNS from authorized topic sends to encrypted queue | **Allow** with proper queue and KMS policies |
| SNS from unauthorized topic/account | **Deny** |
| Role lacking KMS decrypt reads SSE-KMS queue | **Deny** |
| Worker in private subnet calls through allowed endpoint | **Allow** |
| Runtime role calls `PurgeQueue` | **Deny** |
| DLQ redrive by authorized operator only | **Allow**; denied for runtime roles |

In production, instead of sending/receiving dummy live messages to verify `Deny` rules, use **IAM Policy Simulator / Access Analyzer** where applicable, inspect policies, and run dynamic tests in staging. For KMS, simulators do not completely replace testing **actual key policies and service integrations**.

## 17. Monitoring, Auditing, and Sensitive Data

### 17.1. SQS CloudWatch metrics

SQS publishes metrics in the **`AWS/SQS`** namespace. Key operational signals:

| Metric | Meaning | What to investigate on anomaly |
|---|---|---|
| **`ApproximateNumberOfMessagesVisible`** | Ready-to-receive backlog | Producer burst, slow consumer, or errors |
| **`ApproximateNumberOfMessagesNotVisible`** | In-flight messages | Stalled workers, excessive visibility timeouts, or oversized batches |
| **`ApproximateAgeOfOldestMessage`** | Age of oldest message per SQS semantics | Risk of missing SLO; consumers falling behind |
| **`NumberOfMessagesSent`** | Successful sends counted by API | Detect sudden drops or producer anomalies |
| **`NumberOfMessagesReceived`** | Messages returned to consumers | Can exceed sent counts due to retries |
| **`NumberOfMessagesDeleted`** | Successful deletes counted | Does not equal unique business events completed |
| **`NumberOfEmptyReceives`** | Polls returning no messages | Evaluate long polling efficiency and cost |
| **DLQ `ApproximateNumberOfMessagesVisible`** | Failing messages awaiting diagnosis | Alert on poison messages or processor failures |

Because SQS is distributed, **many metrics are approximate**. **`NumberOfMessagesReceived`** can count the same message multiple times; **`NumberOfMessagesDeleted`** counts delete calls rather than proving unique completed transactions. For a DLQ, messages moved automatically from a source queue do not necessarily increment **`NumberOfMessagesSent`** like manual sends. Alert on **backlog, age, errors, and SLOs**, not just send/delete counts.

### 17.2. CloudTrail and KMS auditing

**CloudTrail** aids investigations of recorded AWS API activity, including queue configuration, key usage, and interactions depending on configured event types. When **message-level access** auditing is required, check supported data-event types and enable collection explicitly—never assume every `Send`/`Receive` appears in default CloudTrail management event history.

With **SSE-KMS**, CloudTrail KMS events reveal **`GenerateDataKey`/`Decrypt`** calls and key errors, though data-key reuse means **there is not a separate KMS event for every message**. During investigations, correlate:

1. **SQS API error response**, timestamp, and operation.
2. **Caller identity/role**, account, and Region.
3. **SQS queue policy and queue encryption attributes**.
4. **KMS key ARN, key state, IAM/key policies, and KMS events**.
5. **VPC endpoint policies, SCPs, and permission boundaries**, if applicable.

### 17.3. Application logging without exposing sensitive contents

Producers and consumers should log:

- Correlation ID, event type, schema version, and queue ARN or safe identifier.
- Timestamps for send, receive, process, delete, retry, and DLQ events.
- Error categories such as **`KMS AccessDenied`, `authorization denied`, `timeout`, `schema invalid`**.
- Processing latency, retry counts, and success rates.

Never log **entire message bodies** containing customer data, payment info, or secrets; never log AWS access keys, authorization headers, unnecessary decrypted payloads, or public receipt handles. Enforce log redaction, retention, and least-privilege log-read IAM controls.

## 18. Runbook for Diagnosing Encryption and Access Errors

~~~mermaid
flowchart TD
    A["SendMessage / ReceiveMessage error"] --> B["Record caller role, account,<br/>Region, action, and queue ARN"]
    B --> C{"Did error originate from SQS or KMS?"}
    C -->|"SQS AccessDenied"| Q["IAM identity policy + queue policy<br/>SCP, endpoint, SecureTransport"]
    C -->|"KMS.AccessDenied"| K["Queue SSE-KMS key ARN<br/>key policy, IAM permissions, key state"]
    C -->|"Timeout / network"| N["DNS, TLS, routes, VPC endpoint,<br/>security group / NAT"]
    Q --> R["Verify exact principal,<br/>SourceArn, VPCE, and explicit Deny"]
    K --> R
    N --> R
    R --> T["Apply least-privilege fix in staging<br/>verify positive/negative tests"]
~~~

| Symptom | Likely cause | Check in order |
|---|---|---|
| **SQS `AccessDenied` on `SendMessage`** | Missing `SendMessage`, queue policy `Deny`, wrong queue ARN | STS caller identity, IAM/queue policies, SCP |
| **SQS `AccessDenied` on `ReceiveMessage`** | Consumer lacks `ReceiveMessage`, VPCE condition, or queue policy `Deny` | Caller, queue ARN, queue/endpoint policies |
| **`KMS.AccessDeniedException` on `SendMessage`** | Missing `GenerateDataKey` or `Decrypt`; key policy denies | Queue `KmsMasterKeyId`, producer IAM, KMS key policy |
| **Works for a few minutes then `KMS AccessDenied`** | Data key reuse expired; caller lacks `kms:Decrypt` | Key reuse period, logs, and both KMS actions |
| **`ReceiveMessage` fails with `KMS Decrypt` error** | Consumer lacks `kms:Decrypt` or message uses older key | Consumer IAM, key policy, key-change history |
| **`KMS.DisabledException` / `NotFoundException`** | Key disabled, pending deletion, or wrong ARN | `DescribeKey` state, key lifecycle, backlog |
| **SNS subscription receives zero messages** | Queue policy omits SNS, KMS key policy omits SNS, wrong filter | Subscription status, `SourceArn`, SNS delivery metrics, key policy |
| **S3/EventBridge events fail to enter queue** | Missing service principal, wrong condition, unsupported integration | Source ARN, queue policy, KMS key policy, events/errors |
| **Cross-account caller allowed by IAM still fails** | Missing queue resource `Allow` or cross-account KMS policy | Both accounts, queue policy, key policy, SCP |
| **SSE-KMS `alias/aws/sqs` fails cross-account** | Cannot edit AWS-managed key policy | Migrate carefully to a customer-managed key |
| **ECS in private subnet times out on SQS** | Missing endpoint/NAT/DNS/SG/route | VPC endpoint, TCP 443, private DNS, and routes |
| **Queue readable via VPCE but SNS fails to deliver** | Non-VPCE `Deny` blocks service-to-service traffic | Inspect `aws:sourceVpce` condition and service principal exceptions |
| **DLQ has messages that cannot be read** | Source key disabled; missing decrypt grant for old key | DLQ message history, source keys, IAM |
| **Redrive `AccessDenied`** | Missing `StartMessageMoveTask`, `Receive`/`Delete`, `Send`, or KMS permissions | DLQ/destination permissions and keys |
| **Rising receive count / message age** | Consumer errors, slow processing, short visibility | App logs, DLQ, visibility timeout, database |
| **Message processed twice** | At-least-once delivery; timeout between commit and delete | Idempotency keys, business transactions, receipt handling |
| **Sudden spike in KMS costs** | Many requesters, short reuse period, high throughput | Key reuse period, KMS usage, SQS requests, pricing |

### 18.1. Step-by-step response when `AccessDenied` occurs

1. Capture the **actual role ARN** via **`aws sts get-caller-identity`** inside the exact runtime/account.
2. Separate **`SQS.AccessDenied`** from **`KMS.AccessDeniedException`**; record full error metadata and request IDs.
3. Read **`SqsManagedSseEnabled`/`KmsMasterKeyId`** to confirm whether SSE-SQS or SSE-KMS is active.
4. Verify exact **IAM actions** on the **queue ARN** and, for SSE-KMS, **KMS actions** on the **key ARN**.
5. Inspect the **queue policy**, **KMS key policy**, SCPs/boundaries, and VPC endpoint policies for explicit `Deny` statements or unmatched conditions.
6. For SNS/S3/EventBridge, inspect the **service principal** and **`SourceArn`/`SourceAccount`**, not just the originating app role.
7. Test a **targeted least-privilege fix** in staging and verify both allowed and denied paths. Never open wildcard permissions to “rescue” production.
8. After fixing, cross-check **CloudWatch metrics, backlog, DLQ, and actual data** to ensure messages were neither dropped nor processed out of spec.

## 19. Practical Scenarios

### Scenario A — Producer has `SendMessage` yet fails after 5 minutes

An ECS worker sends messages to an SSE-KMS queue with **`KmsDataKeyReusePeriodSeconds = 300`**. Minutes later, requests fail with **`KMS.AccessDeniedException`**. The producer IAM role has **`kms:GenerateDataKey`** but not **`kms:Decrypt`**.

**Question:** Why weren't valid SQS permissions enough?

**Hint:** When the reuse period expires, SQS may require both **`GenerateDataKey`** and **`Decrypt`**. Grant the exact missing action on the key ARN and verify the key policy, IAM, and SCPs—never grant account-wide `kms:*`.

### Scenario B — SNS fails to deliver to an SSE-KMS queue

An application already has **`sns:Publish`** on the topic. The subscribed queue has a policy allowing **`sns.amazonaws.com`** with the matching `SourceArn`, yet receives nothing. The queue uses **`alias/aws/sqs`**.

**Question:** What should be checked?

**Hint:** Check SNS delivery errors/filters, the queue policy, and then the **KMS key policy for the SNS service producer**. Because AWS-managed keys cannot have custom policies added, consider a **customer-managed KMS key** with proper SNS service-principal grants.

### Scenario C — Cross-account Lambda consumer

The queue belongs to Account B, while the Lambda function runs in Account A. The Lambda execution role grants **`sqs:ReceiveMessage`**, **`DeleteMessage`**, and **`GetQueueAttributes`** on the queue ARN, yet polling fails; the SSE-KMS queue uses a key in B.

**Question:** Which permission layers are required?

**Hint:** Account A's IAM policy, Account B's queue resource policy, cross-account KMS key policy + decrypt permissions, plus matching networking, Region, and quotas. If using the AWS-managed key `alias/aws/sqs` whose policy cannot be edited, switch to a customer-managed key per guidance—do not simply keep tweaking `ReceiveMessage`.

### Scenario D — DLQ cannot decrypt messages after key change

A source queue migrated from KMS key **`K1`** to **`K2`**. Operations immediately disabled **`K1`** assuming messages already in the DLQ were encrypted under the DLQ's key. Opening the DLQ failed with decryption errors.

**Question:** What went wrong?

**Hint:** Automatic movement to a DLQ **does not change a message's encryption**. Messages encrypted under `K1` still require `K1`; keep the old key and decrypt permissions active for backlogs/DLQs before planning retirement.

### Scenario E — Enforcing a VPC endpoint breaks SNS fan-out

A queue policy denies all requests missing a specific **`aws:sourceVpce`**. ECS workers receive messages cleanly via the endpoint, yet the SNS topic fails to deliver.

**Question:** Why?

**Hint:** AWS service-to-service requests carry a different context than workers inside a VPC. Review explicit `Deny` statements and craft verified exceptions by service principal/`SourceArn` instead of opening the entire queue; retest queue and KMS policies afterward.

### Scenario F — Consumer deletes message before writing to DB

A Java consumer calls **`DeleteMessage`** right after `ReceiveMessage`, then attempts the database write. When the database times out, the order vanishes from the queue unprocessed.

**Question:** In what order should this be fixed?

**Hint:** Process idempotently and commit successfully before calling `DeleteMessage`; on failure, skip deletion so SQS retries and routes to a DLQ if needed. Add transactional deduplication to handle redeliveries after a commit.

### Scenario G — SSE-SQS queue, but auditor demands KMS logs per dedicated key

The system uses SSE-SQS for encryption at rest. An auditor requires customer-owned key policies, lifecycle management, and KMS-level audit events.

**Question:** Can you simply attach an IAM KMS policy to the producer and call the requirement met?

**Hint:** No. SSE-SQS is not SSE-KMS. Plan a migration to an **SSE-KMS customer-managed key**, reviewing permissions, KMS cost/quotas, existing backlogs, service integrations, and rotation mechanics before making the change.

## 20. Production Deployment Checklist

- [ ] Identified all producers, consumers, service sources, and exact queue/Region/account boundaries.
- [ ] Selected **SSE-SQS** or **SSE-KMS** based on data sensitivity, audit, cross-account, and budget requirements.
- [ ] Verified **message bodies** are SSE-encrypted; kept PII/secrets out of **message attributes, queue names, and logs**.
- [ ] Enforced HTTPS/TLS and SigV4; queue policy guardrails remain compatible with service integrations.
- [ ] Producer IAM grants only **`SendMessage`** (and `GetQueueUrl` if needed), without `Receive`/`Delete`/`Purge`.
- [ ] Consumer IAM grants only **`Receive`/`Delete`/`GetQueueAttributes`/`ChangeVisibility`** as required.
- [ ] Under SSE-KMS, producers have **`kms:GenerateDataKey` + `kms:Decrypt`**, and consumers have **`kms:Decrypt`** on the exact key ARN.
- [ ] KMS key policy permits the exact roles and service principals; never rely on IAM `Allow` alone if key policy omits it.
- [ ] Queue policy pins service principals, **`SourceArn`/`SourceAccount`**, and cross-account principals accurately.
- [ ] With SNS/S3/EventBridge, verified **both the queue policy and KMS key policy**.
- [ ] For cross-account setups, verified identity IAM, SQS resource policies, and customer-managed key grants.
- [ ] For VPCE setups, verified endpoint policies, DNS, SGs, TCP 443, and avoided blocking service-to-service traffic.
- [ ] Configured visibility timeouts, retries/idempotency, FIFO group semantics, and DLQs properly.
- [ ] DLQ encryption, retention, redrive allow policies, and inspect/redrive permissions are limited to approved operators.
- [ ] When rotating KMS keys, planned for older messages and kept old keys enabled until backlogs/DLQs drained.
- [ ] Validated positive/negative permission tests, AWS SDK flows, and service integrations in staging.
- [ ] Monitored backlog, oldest age, processing errors, DLQs, and KMS `AccessDenied`/usage.
- [ ] Restricted administrative **`SetQueueAttributes`/`PurgeQueue`/`DeleteQueue`** actions and retained audit logs per policy.
- [ ] Budgeted for SQS APIs, KMS requests/keys, retries, compute, DLQs, networking, and CloudWatch.
- [ ] Prepared runbooks for IAM, KMS, networking, key rotation, and redrive incidents.

## 21. Key Takeaways

**SQS SSE-SQS** encrypts message bodies with an SQS-owned key, keeping complexity low with no runtime KMS permissions required. **SSE-KMS** uses an AWS KMS key where **producers need `kms:GenerateDataKey` and `kms:Decrypt`**, and **consumers need `kms:Decrypt`**; the KMS key policy must also authorize those grants. The **IAM identity policy** defines what an application role may do, the **SQS queue policy** governs service, cross-account, and source access to the queue, and the **KMS key policy** governs key usage—none of the three layers substitutes for another.

When wiring **SNS → SQS**, check both the **SNS service principal in the queue policy** and the **encrypted queue's KMS key policy**; whenever custom policies for AWS services or cross-account access are needed, use a **customer-managed KMS key**. **DLQs do not re-encrypt moved messages**, so retain older keys until backlogs drain. Finally, security is complete only when combining **TLS, least-privilege IAM, data minimization, idempotent consumers, monitoring, and recovery planning**.

### Official AWS Documentation for Reference

- [What is Amazon SQS?](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) — overview of queues, producers, and consumers.
- [Encryption at rest in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-server-side-encryption.html) — SSE-SQS, SSE-KMS, message body scope, and DLQs.
- [Configure SSE-SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sqs-sse-queue.html) — SQS-owned encryption keys.
- [Configure SSE-KMS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sse-existing-queue.html) — key ARNs and queue encryption.
- [Amazon SQS key management](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-key-management.html) — producer/consumer KMS permissions, reuse periods, and key rotation.
- [Least privilege policies for encrypted queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-least-privilege-policy.html) — IAM, SQS, KMS, DLQs, and confused deputy protection.
- [Troubleshoot AccessDenied in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/troubleshooting-access-denied.html) — IAM, queue, KMS, VPCE, and SCP checks.
- [Amazon SQS security best practices](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-security-best-practices.html) — TLS, least privilege, and network endpoints.
- [Subscribe Amazon SQS to Amazon SNS topic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html) — fan-out, `SourceArn`, and cross-account access.
- [Configure SQS Lambda trigger](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-lambda-function-trigger.html) — execution roles and polling encrypted queues.
- [SQS dead-letter queue redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html) — DLQ permissions, redrive, and KMS.
- [Available CloudWatch SQS metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html) — backlog, age, and receive/delete metrics.
- [Amazon SQS API SetQueueAttributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html) — SSE queue attributes.
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/), [AWS KMS pricing](https://aws.amazon.com/kms/pricing/), and [AWS Pricing Calculator](https://calculator.aws/) — current pricing estimates.


