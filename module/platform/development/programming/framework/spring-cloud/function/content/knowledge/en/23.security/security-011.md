# Least Privilege When Accessing Cloud Services and Brokers

## 1. The Problem: A Function Should Have Only the Permissions Needed for Its Job

An order-processing system uses Spring Cloud Function. The application has three functions:

- `receiveOrder` consumes events from a broker and validates data.
- `archiveOrder` writes order copies to object storage.
- `publishOrderStatus` emits status notifications to another topic.

If all three functions share one credential with administrative rights over buckets, queues, topics, and databases, a bug in any function can affect the entire system. A function meant only to write objects could delete data; a consumer meant only to read a queue could publish forged messages; an injection bug or compromised dependency could wield every privilege of the process.

**Least privilege** is the principle of granting a workload only the exact operations needed on the exact resources needed, for the duration needed. Applied to Spring Cloud Function, you must identify:

1. Under which **principal/identity** does the function run?
2. Which **actions** does the function need to perform?
3. To which **resources** do those actions apply?
4. By which **scope, conditions, network, and duration** are permissions bounded?
5. How do you verify the function cannot perform out-of-scope operations?

In the **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) module, business logic is structured using `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`, looked up via `FunctionCatalog`, composition, and message conversion. The function model decouples logic from transport protocols; **it does not grant or restrict cloud/broker access permissions**. Permissions are determined by the runtime's identity, service policies, and adapter/binder security configuration.

This lesson focuses on access permissions across AWS, Google Cloud, Azure, and Kafka/RabbitMQ brokers. Role names, actions, properties, and policy examples must be checked against your actual service, version, and deployment model.

## 2. Distinguishing Authentication, Authorization, and Network Access

Three layers of defense are often conflated into one:

| Layer | Question | Example |
| --- | --- | --- |
| **Authentication** | Who is calling? | IAM role, workload identity, managed identity, SASL/SCRAM, mTLS. |
| **Authorization** | What can the principal do on which resource? | IAM policy for `s3:GetObject`, Kafka `READ` ACL on a topic, RabbitMQ read permission on a queue. |
| **Network access** | Can the connection reach the endpoint? | VPC routes, security groups, firewalls, private endpoints, TLS. |

A successful TCP connection does not mean the principal may read a queue. Conversely, an IAM policy granting `s3:GetObject` will not let an app access a bucket if routes, DNS, or endpoints are blocked.

### 2.1. Identity, Action, and Resource

An authorization decision can typically be expressed as:

```text
Principal:  order-archiver-role
Action:     s3:PutObject
Resource:   arn:aws:s3:::order-archive/orders/*
Condition:  region / encryption / tenant / network (if needed)
```

This example shows only the permission intent. Effective access also depends on resource policies, explicit denies, permission boundaries, session policies, organization policies, and service conditions.

### 2.2. Function Permissions Differ from Caller Permissions

Access goes in two directions:

- **Inbound:** users, API gateways, schedulers, or brokers permitted to trigger the function.
- **Outbound:** the function permitted to call object storage, databases, secret managers, or brokers.

Never use one single policy to describe both directions. On AWS, for example, the execution role grants Lambda code access to services, whereas a resource-based policy on the Lambda can allow another service/account to invoke the function. Those two policies serve distinct purposes. See [Managing Lambda permissions](https://docs.aws.amazon.com/us_en/lambda/latest/dg/lambda-permissions.html).

## 3. Identify the Principal the Function Actually Uses

A Spring bean can be invoked over HTTP, Stream, or serverless, yet credentials typically come from the **runtime/process or binder/client**, not from the bean name in `FunctionCatalog`.

| Runtime Environment | Typical Identity |
| --- | --- |
| AWS Lambda | Lambda execution role supplying temporary runtime credentials. |
| AWS ECS/EKS/EC2 | Task role, pod/workload identity, or matching instance profile. |
| Google Cloud Run/GKE/Functions | Service account attached to the workload or Workload Identity. |
| Azure Functions/Container Apps/AKS | Managed identity or workload identity. |
| Self-managed Kubernetes | Service account paired with OIDC federation or system-managed secrets. |
| Self-managed broker | Principal from SASL/SCRAM, Kerberos, mTLS certificate, or broker-supported auth. |

### 3.1. One Process Usually Shares One Workload Identity

Suppose a single Spring Boot process contains:

```java
@Bean
Function<OrderEvent, ArchiveResult> archiveOrder(ArchiveService service) {
    return service::archive;
}

@Bean
Function<OrderEvent, Notification> publishOrderStatus(
        NotificationService service) {
    return service::publish;
}
```

The two beans have different names, yet run inside the same process. If the process uses one AWS execution role, both functions can use that role's credentials through the AWS SDK default credential provider chain. **Beans do not automatically receive separate IAM roles simply because they are separate functions.**

When strong permission separation is required:

- Deploy functions as separate workloads/Lambdas, each with its own execution role.
- In certain architectures, a workload can assume another role via STS when explicitly designed; constrain trust policies, session durations, and assume permissions.
- Whenever functions share a process and credentials, treat the process's permission set as the maximum capability available to all code running in that process.

That is why splitting functions across deployment boundaries often matters more than separating beans within the same context.

## 4. Provisioning Credentials Safely to Spring Applications

### 4.1. Prefer Workload Identity Over Static Access Keys

The preferred order is generally:

1. Platform-provided **managed/workload identity**.
2. Federation/OIDC or short-lived STS sessions when a workload must assume a role.
3. Short-lived credentials from a secret manager when a broker does not support workload identity.
4. Static credentials only when no better option exists, with clear ownership, rotation, and tight scoping.

Never commit access keys, broker passwords, private keys, or tokens into Git, Docker images, JARs, `application.yml`, or logs. Never put secrets in function names or message headers.

### 4.2. AWS SDK Uses the Credential Provider Chain

Example creating an S3 client:

```java
@Configuration(proxyBeanMethods = false)
class CloudClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.of(System.getenv("AWS_REGION")))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
```

`DefaultCredentialsProvider` lets the AWS SDK resolve credentials from runtime-supported sources; in Lambda, the SDK uses the execution role's temporary credentials. The app never embeds access keys in code. Close the client with the Spring context lifecycle to release resources.

In production, verify the credential provider chain supported by your exact SDK version and prevent environment variables/local profiles from accidentally overriding the workload role.

### 4.3. Never Use Developer Identities in Production

An application running locally may use a broad personal profile. Deploying that configuration or baking credential files into a container can run the function with far more privileges than the workload needs.

Local development should use a dedicated limited profile; production must use dedicated roles/managed identities. Never use operator credentials for long-running workloads.

## 5. Design Policies by Action and Resource

Before writing policies, build a permission table per function:

| Function | Operation | Resource | Expected Least Privilege |
| --- | --- | --- | --- |
| `receiveOrder` | Consume events | Queue `orders.in` | Read/consume on the required queue or subscription and consumer group. |
| `archiveOrder` | Write objects | Prefix `orders/*` in bucket `order-archive` | Put object on the prefix. |
| `publishOrderStatus` | Publish events | Topic `orders.status` | Write/publish on the topic. |
| `loadShippingPolicy` | Read secret | Secret `shipping-api-key` | Get/read that exact secret. |

A solid policy restricts both **actions** and **resources**. `s3:*` on `*`, `pubsub.*` at the project level, or an `administrator` user across an entire broker is never right for an ordinary business function.

### 5.1. Do Not Grant Admin Rights Just So the App Creates Its Own Resources

Creating buckets, queues, topics, subscriptions, exchanges, and bindings is normally the job of provisioning/deployment pipelines or platform administrators. Runtime functions only need to read, write, consume, or publish.

In production environments, consider:

- Disabling topic/queue auto-creation when unneeded.
- Provisioning resources via IaC or a separate pipeline.
- Granting data-plane permissions to functions; keeping control-plane resource management on the deployment identity.
- Never sharing one principal for both infrastructure provisioning and message processing.

## 6. AWS IAM: Execution Roles and S3 Permissions

Every Lambda requires an execution role. The role has a **trust policy** letting the Lambda service assume it and **permission policies** stating which services the code can access. Permission for another service/account to invoke the Lambda can live in the Lambda's resource-based policy. See [AWS Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html) and [Managing Lambda permissions](https://docs.aws.amazon.com/us_en/lambda/latest/dg/lambda-permissions.html).

### 6.1. Read-Only Access to One Prefix

Suppose `loadOrderArchive` only needs to read objects under `orders/` in bucket `order-archive`. Illustrative identity-based policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrderArchiveObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::order-archive/orders/*"
      ]
    }
  ]
}
```

The policy above grants no permission to list buckets, write objects, delete objects, or access other prefixes. If the function needs `ListObjectsV2`, add `s3:ListBucket` on the **bucket ARN** constrained by an `s3:prefix` condition; never add `s3:ListAllMyBuckets` just for console convenience.

Separate statement example for listing one prefix:

```json
{
  "Sid": "ListOnlyOrderArchivePrefix",
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": ["arn:aws:s3:::order-archive"],
  "Condition": {
    "StringLike": {
      "s3:prefix": ["orders/", "orders/*"]
    }
  }
}
```

Bucket-level actions use the bucket ARN; object actions use the object ARN. This distinction is critical when debugging `AccessDenied`. See [How S3 works with IAM](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security_iam_service-with-iam.html) and [Permissions for S3 API operations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html).

### 6.2. Write-Only Access to One Prefix

`archiveOrder` only uploads objects:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteOrderArchiveObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::order-archive/orders/*"
      ]
    }
  ]
}
```

Do not add `s3:GetObject`, `s3:DeleteObject`, or `s3:*` if the function only uploads. If objects use SSE-KMS, KMS permissions such as `kms:GenerateDataKey` on the specific key may be required; reading encrypted objects may require `kms:Decrypt`. Both the key policy and IAM policy must allow the action. Grant only required KMS permissions and inspect encryption context/`kms:ViaService` where appropriate.

### 6.3. Do Not Forget Resource Policies and Explicit Denies

An S3 request can be governed by:

- Identity-based policy on the execution role.
- Bucket/access point policy.
- KMS key policy if objects use SSE-KMS.
- VPC endpoint policy.
- Organization SCPs, permission boundaries, or session policies.
- Explicit `Deny` in any applicable layer.

An `Allow` on the execution role does not override an explicit deny or another policy boundary.

## 7. AWS SQS: Distinguish Event Source Mapping from SDK Send

When Lambda connects to SQS via an **event source mapping**, Lambda polls the queue and feeds message batches into the function. The execution role needs corresponding receive/delete/attribute permissions, typically:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-in"
    }
  ]
}
```

If the queue is encrypted with KMS, `kms:Decrypt` on the corresponding key may also be required. AWS documents [Configuring SQS event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html), including execution role permissions and encrypted queues.

**These are the Lambda poller's permissions via the execution role.** If code inside the function calls the AWS SDK to send messages to `orders-out`, that is a separate operation requiring `sqs:SendMessage` on the target queue. Never grant `SendMessage` to a consumer merely because it reads from SQS.

### 7.1. DLQs and Retries Must Also Be Designed

When processing message batches:

- Match batch size and visibility timeout to processing time.
- Configure redrive policies, max receive counts, and DLQs.
- Use partial batch responses if supported by the adapter/trigger and app.
- Design for idempotency because messages may be redelivered.
- Grant only read/delete on the source queue and required permissions on the DLQ per actual roles.

Least privilege does not replace delivery semantics. A function with minimal permissions can still cause duplicate side effects if it processes duplicate messages non-idempotently.

## 8. Google Cloud Pub/Sub: Roles Per Topic and Subscription

Pub/Sub uses IAM and supports binding permissions at the project or resource level. For publish-only functions, `roles/pubsub.publisher` includes `pubsub.topics.publish` and can be granted directly on the topic. For consume-only functions, `roles/pubsub.subscriber` grants subscription consume rights and can be bound to the specific subscription. Avoid granting `roles/pubsub.admin` or broad basic roles to runtimes. See [Pub/Sub access control](https://docs.cloud.google.com/pubsub/docs/access-control).

| Function | Suggested Role | Scope |
| --- | --- | --- |
| `publishOrderStatus` | Pub/Sub Publisher | Topic `orders.status`. |
| `receiveOrder` | Pub/Sub Subscriber | Subscription `orders-normalizer-sub`. |
| `provisionTopics` | Separate admin role | Deployment pipeline only; never attached to function runtime. |

### 8.1. Workload Identity

Bind a service account/workload identity to the running workload. Avoid baking service account JSON keys into images or storing them in `application.yml`. For cross-project Pub/Sub, grant the service account permissions on the exact target topic/subscription; never grant project-wide rights when only one resource is needed.

### 8.2. Diagnosing `PERMISSION_DENIED`

Verify the active principal, the project owning the resource, the topic/subscription name, and the scope where the role is bound. A service account with publisher rights on topic A still cannot publish to topic B. IAM changes may experience propagation/cache delays.

## 9. Azure Service Bus: Managed Identity and Data Sender/Receiver

Azure Service Bus provides data-plane roles:

- **Azure Service Bus Data Sender:** sends messages to queues/topics.
- **Azure Service Bus Data Receiver:** receives messages from queues/subscriptions.
- **Azure Service Bus Data Owner:** broader data-plane administrative access; avoid for functions that only send or receive.

Assign roles at the narrowest scope: queue, topic, or subscription when supported, escalating to namespace/resource group/subscription only if truly necessary. Microsoft describes roles and scopes in the [Managed Identity guide for Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity).

| Function | Role | Scope |
| --- | --- | --- |
| `publishOrderStatus` | Data Sender | Topic `orders.status`. |
| `receiveOrder` | Data Receiver | Queue `orders.in` or specific subscription. |
| `manageBrokerTopology` | Separate admin role | Pipeline/provisioning identity. |

### 9.1. Managed Identity Over Connection Strings with SAS Keys

When the runtime supports it, use Managed Identity and Microsoft Entra authentication. Connection strings containing shared access keys can grant broad namespace permissions and obscure workload boundaries. If SAS policies are still required, create dedicated send-only or listen-only policies; never use `RootManageSharedAccessKey` for applications.

Azure role assignments can take time to propagate; Service Bus docs note delays up to several minutes. Immediately after assigning a role, verify the principal and scope before assuming the SDK or binder is broken.

## 10. Kafka: ACLs Must Restrict Topics and Consumer Groups

Kafka enforces two independent layers:

1. **Authentication:** the broker identifies the principal via SASL/SCRAM, SASL/OAUTHBEARER, Kerberos, or TLS client certificates.
2. **Authorization:** the authorizer evaluates ACLs for the principal across topics, groups, clusters, or transactional IDs.

A consumer needs to read a topic and join its consumer group. A producer needs to write to a topic. Cluster/topic administration rights are unnecessary for ordinary message-processing functions. See [Kafka authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/).

### 10.1. Basic Permission Matrix

| Role | Topic | Consumer Group | Cluster |
| --- | --- | --- | --- |
| Consumer `order-normalizer` | `READ` (and `DESCRIBE` when metadata is needed) on `orders.in` | `READ` on group `order-normalizers` | No admin rights needed. |
| Producer `order-status-publisher` | `WRITE` (and `DESCRIBE` when metadata is needed) on `orders.status` | No consumer group rights needed | No admin rights needed. |
| Topic provisioner | `CREATE`/`ALTER`/`DELETE` per task | Not attached to runtime | Only cluster permissions needed by the pipeline. |

Kafka CLI convenience flags `--producer` can create `WRITE`, `DESCRIBE`, and `CREATE` ACLs on a topic; `--consumer` creates `READ`, `DESCRIBE` on the topic and `READ` on the group. For least privilege, when topics are pre-provisioned, inspect exact ACLs and omit `CREATE` if producers never create topics.

### 10.2. Consumer Group Name Is Part of the Permission

A consumer with `READ` on a topic but missing `READ` on its group can fail with `GROUP_AUTHORIZATION_FAILED`. If an application changes `group` in Spring Cloud Stream, the group ACL must update as well. Never grant wildcard `READ` across all groups just to fix a mismatched group name.

### 10.3. Idempotent / Transactional Producers

Producers using idempotence or transactions may need additional ACLs such as `IdempotentWrite` on the cluster or permissions on transactional IDs, depending on broker version/config. Never grant `All` or cluster admin just to get producer transactions working; inspect the protocol error and add the exact missing resource/operation.

## 11. RabbitMQ: Vhosts and Regex Permissions

RabbitMQ controls permissions per **virtual host** and resource name. Three main permission groups:

- `configure`: declare, alter, or delete queues/exchanges/bindings.
- `write`: publish or write operations on resources.
- `read`: consume or read operations from resources.

Permissions are regexes evaluated against resource names within the vhost. The [RabbitMQ access control](https://www.rabbitmq.com/docs/access-control) docs cover `set_permissions`, `clear_permissions`, and virtual-host scoping.

### 11.1. Consumer Reading Only One Queue

Example granting principal `order-consumer` permission solely to consume `orders.input` in vhost `orders-vhost`:

```bash
rabbitmqctl set_permissions -p "orders-vhost" "order-consumer" "^$" "^$" "^orders\.input$"
```

The three regexes are `configure`, `write`, and `read` in order. The consumer cannot declare queues/exchanges, cannot publish, and can read only resources matching `orders.input`.

### 11.2. Producer Writing Only to an Existing Exchange

```bash
rabbitmqctl set_permissions -p "orders-vhost" "order-publisher" "^$" "^orders\.status$" "^$"
```

The exchange must be pre-provisioned by an identity with configure permissions. The producer can only publish to the `orders.status` exchange; it cannot consume or create resources.

### 11.3. Do Not Confuse Management Tags with Resource Permissions

Tags like `administrator`, `management`, or `monitoring` control access to the management UI/API. They are separate from configure/write/read permissions on resources. A worker never needs RabbitMQ admin privileges just to consume a queue. Never assign the `administrator` tag to a function's service account.

## 12. Securing the Kafka Binder in Spring Cloud Stream

Spring Cloud Function defines business functions; the Spring Cloud Stream binder connects functions to brokers. For the Kafka binder, client security settings pass via `spring.cloud.stream.kafka.binder.configuration`. The [Spring Cloud Stream Kafka security configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html) docs explain configuring SASL/JAAS and client properties.

Example consumer binding:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.in
          group: order-normalizers
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: >-
              org.apache.kafka.common.security.scram.ScramLoginModule required
              username="${KAFKA_USERNAME}"
              password="${KAFKA_PASSWORD}";
```

This illustrates configuration for a broker supporting SASL/SCRAM-SHA-512. Pair it with proper TLS trust settings and ACLs for the principal on the topic/group. `SASL_SSL` protects transport with TLS; SASL authenticates the principal; ACLs decide what the principal may do.

**Never commit `KAFKA_USERNAME` or `KAFKA_PASSWORD` values.** Supply them via a secret manager or managed injection. If using multiple Kafka clusters with different credentials, use multi-binder setups with separate security configs per binder rather than sharing one broad credential across the entire app.

### 12.1. Disable Auto-Create When Runtime Lacks Admin Permissions

In controlled environments, topics should be created by provisioning pipelines. Setting `autoCreateTopics: false` (per binder/version config) keeps the runtime from trying to create topics when the broker denies `CREATE`. Also review `autoAddPartitions`; leave partition-management features off if the workload does not need them.

### 12.2. Consumer Group Must Match ACLs

If a binding declares:

```yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.in
          group: order-normalizers
```

then the Kafka principal needs rights on topic `orders.in` and group `order-normalizers`. Changing the group name is a security-contract change, not merely an operational tweak.

## 13. RabbitMQ Binder and Workload-Specific Credentials

With the RabbitMQ binder, the app needs credentials scoped accurately to the vhost and resources. Example connection settings:

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: 5671
    virtual-host: orders-vhost
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
```

These are Spring Boot RabbitMQ connection properties; check your binder and version for how connection factories are shared. Supply username/password via secret injection, never hardcoded in files. TLS needs proper certificate-chain and hostname verification.

Consumers and publishers should use separate principals when they have different roles/permissions. If the same principal handles both, the process's effective capability is the union of both read and write permissions.

## 14. Example: Function Permitted Only to Write to One Prefix

A function can use the AWS SDK without knowing the underlying IAM policy details:

```java
@Configuration(proxyBeanMethods = false)
class ArchiveFunctions {

    @Bean
    Function<OrderArchiveCommand, String> archiveOrder(S3Client s3) {
        return command -> {
            String key = "orders/" + command.orderId() + ".json";

            s3.putObject(
                    PutObjectRequest.builder()
                            .bucket("order-archive")
                            .key(key)
                            .contentType("application/json")
                            .build(),
                    RequestBody.fromString(command.json()));

            return key;
        };
    }
}
```

The function calls only `PutObject`; its execution role needs only `s3:PutObject` on `arn:aws:s3:::order-archive/orders/*` (plus KMS rights if required by encryption policy). It needs neither `s3:GetObject`, `s3:DeleteObject`, nor bucket administration rights.

`orderId` and `json` here are the input contract. In multi-tenant systems, never trust arbitrary `tenantId`/object keys sent by callers. Authenticate/authorize the tenant at the boundary and derive keys from verified principals/claims; prefix policies are a secondary guard, not a replacement for business authorization checks.

## 15. Secrets, Rotation, and Connection Lifecycle

### 15.1. Fetch Only Needed Secrets

If a function needs an API key or broker password:

- Grant read access strictly to that exact secret/version for the workload.
- Never grant permission to list all secrets when reading a single known secret.
- Separate secrets by environment and by workload.
- Never place secrets in events, function outputs, exception messages, or logs.
- Restrict console secret-read access and deployment pipeline permissions.

### 15.2. Rotation Without Breaking Running Functions

When a secret rotates:

1. The broker/API accepts the new credential.
2. Secret Manager creates/activates the new version.
3. The workload fetches the new credential via its designed cache/refresh mechanism.
4. Client connection pools or broker connections reconnect cleanly.
5. The old credential is revoked after an appropriate overlap window.

Never assume a Spring singleton automatically reloads a password when Secret Manager rotates versions. If a binder/client reads credentials only when constructing the connection factory, implement controlled refresh/restart or rebind flows.

### 15.3. Never Log Credentials

Logging principal/service account IDs can help auditing; logging passwords, access tokens, SASL JAAS strings, private keys, or full connection URIs with embedded secrets never should happen. When logging exceptions, verify libraries do not dump sensitive config.

## 16. Trust Boundaries for Messages and Function Routing

Message headers and payloads can originate externally. Fields like `tenantId`, `role`, `principal`, `functionName`, or `routingExpression` do not constitute authorization proof on their own.

Example event:

```json
{
  "tenantId": "tenant-a",
  "orderId": "ORD-204",
  "action": "archive"
}
```

The function must verify that the caller/event source is authorized for `tenant-a` before constructing object keys or calling services. Never treat `tenantId` from a payload as access authority just because JSON parsed cleanly.

### 16.1. Broker ACLs Do Not Replace Domain Authorization

A Kafka ACL may let a service read `orders.in`; it does not guarantee every message in that topic belongs to a tenant the service may process. If a topic is multi-tenant, the application must verify tenant/ownership against a trusted source.

Conversely, in-code authorization does not replace broker ACLs. A consumer allowed to read every topic while checking tenants only inside code can still be misconfigured, read out-of-scope data, and widen the blast radius.

### 16.2. Routing Must Not Escalate Privileges

If using `FunctionCatalog` routing to pick functions from message headers:

- Allow only an explicit list of functions.
- Never let external events select administrative functions or side-effecting `Consumer` beans.
- Verify the header source; never trust client-supplied headers unless authenticated by the adapter.
- Audit the resolved route name and verified principal without logging secrets or sensitive payloads.

## 17. Diagnosing `AccessDenied` and Broker Authorization Errors

When a function hits an authorization error, identify the **principal, action, resource, and policy layer** before adding permissions.

| Error | First Questions to Ask |
| --- | --- |
| AWS `AccessDenied` | Which role is assumed? What are the exact action and ARN? Is there an explicit deny, bucket policy, KMS key policy, or SCP? |
| S3 `403 AccessDenied` | Does the object ARN match the prefix? Is `ListBucket` needed or only `GetObject`? Does the bucket use SSE-KMS? |
| SQS `AccessDenied` | Did the error come from the event source mapping poller or SDK code? Are queue ARN, region, and account exact? |
| GCP `PERMISSION_DENIED` | Which service account? At which topic/subscription/project scope is the role bound? |
| Azure `Unauthorized`/`Forbidden` | Is the Managed Identity right? Does the Data Sender/Receiver role have the right scope and has it propagated? |
| Kafka `TOPIC_AUTHORIZATION_FAILED` | Does the principal have `READ`/`WRITE` on the exact topic? |
| Kafka `GROUP_AUTHORIZATION_FAILED` | Does the consumer group match the ACL name? |
| RabbitMQ `ACCESS_REFUSED` | Does the principal have rights on the exact vhost and resource regex? |

### 17.1. Workflow for Resolving AWS `AccessDenied`

1. Read the principal ARN in the exception or CloudTrail event.
2. Confirm the actual Lambda execution role, not the deployer/user identity.
3. Identify the exact missing action and resource ARN.
4. Check identity policies, resource policies, KMS key policies, VPC endpoint policies, SCPs, and permission boundaries.
5. When listing S3, distinguish `s3:ListBucket` on the bucket ARN from `s3:GetObject` on the object ARN.
6. Add strictly the single needed permission/resource/condition.
7. Retry the denied operation and run negative tests to confirm out-of-scope actions remain denied.

AWS IAM Access Analyzer can generate policy templates from CloudTrail activity suggesting observed actions. Treat that as **review input, not a complete guarantee**: rare paths, error branches, periodic jobs, or new features may not appear in logs yet. AWS recommends using Access Analyzer to refine execution roles prior to production. See [AWS execution role least privilege](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html).

### 17.2. Never Fix Errors with Broad Wildcards

Resist the reflex to add:

```json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*"
}
```

or to grant `AdministratorAccess`, Kafka superuser, RabbitMQ administrator, or Azure Data Owner to a workload just because one request failed. Pinpoint the exact missing permission and resource scope.

## 18. Testing Least Privilege

Policies must be tested for both **permitted paths** and **forbidden paths**.

### 18.1. Positive Tests

| Function | Operation That Must Succeed |
| --- | --- |
| `archiveOrder` | Put object into `order-archive/orders/ORD-204.json`. |
| `loadOrderArchive` | Get object within the granted prefix. |
| `receiveOrder` | Consume from the designated queue/topic and group. |
| `publishOrderStatus` | Publish to `orders.status`. |

### 18.2. Negative Tests

| Function | Operation That Must Be Denied |
| --- | --- |
| `archiveOrder` | Get or delete objects; put into another bucket or prefix. |
| `loadOrderArchive` | Read another tenant's prefix or another bucket. |
| `receiveOrder` | Consume an unauthorized topic/group. |
| `publishOrderStatus` | Publish to another topic or create a new topic. |

### 18.3. CI/CD Verification

- Validate JSON/YAML policies and IaC.
- Use IAM policy simulators / Access Analyzer or equivalent cloud tools.
- Inspect Kafka ACLs with broker tooling; test actual consumer groups.
- Inspect RabbitMQ permissions per vhost/resource and test with non-admin users.
- Test workload identities in production-like environments; local mocks do not prove real cloud policies.
- Run post-deployment smoke tests and record verified principal/action/resource results.

LocalStack, emulators, and mock clients help test logic, yet do not replace authorization tests against real AWS/GCP/Azure or real brokers. Mocks often skip resource policies, KMS, ACLs, IAM propagation, or TLS configuration.

## 19. Workflow for Designing Permissions for a New Function

When adding a function to Spring Cloud Function:

1. **Describe business needs:** what does the function read, write, publish, consume, or which secrets/APIs does it call?
2. **Define workload boundaries:** does the function get its own process/deployment or share an identity with other functions?
3. **Select identity:** execution role, managed identity, service account, or broker principal.
4. **Enumerate actions/resources:** specify exact API operations, bucket prefixes, queues, topics, subscriptions, consumer groups, and secrets.
5. **Separate control plane from data plane:** provisioning creates resources; runtime only processes data.
6. **Author tight policies:** avoid action/resource wildcards without justification.
7. **Configure clients/binders:** use credential providers/workload identities, TLS, and secret injection.
8. **Run positive and negative tests:** verify required access works and unneeded access fails.
9. **Observe/audit:** record principals and resources, monitor denied events, rotation, and policy edits.
10. **Review periodically:** revoke unused permissions and re-evaluate whenever the function changes.

## 20. Hands-On Exercises

### Exercise 1 — Write-Only Access to One Prefix

Create an `archiveOrder` function using the AWS SDK `S3Client` to write objects into bucket `order-archive` under prefix `orders/`.

1. Attach a dedicated execution role to the Lambda.
2. Grant only `s3:PutObject` on `arn:aws:s3:::order-archive/orders/*`.
3. Invoke the function and verify uploads succeed.
4. Attempt `GetObject`, `DeleteObject`, and writing to `private/`; verify all are denied.
5. If SSE-KMS is enabled, grant KMS permission strictly on the right key and re-test.

### Exercise 2 — Kafka Consumer Reading Only One Topic/Group

1. Create principal `order-normalizer`.
2. Pre-create topic `orders.in` and consumer group `order-normalizers` via the admin pipeline.
3. Grant `READ`/`DESCRIBE` on the topic and `READ` on the corresponding group.
4. Configure the Spring Cloud Stream binding with the matching destination/group and `SASL_SSL`.
5. Verify consumption succeeds; switch to a different topic/group and confirm the broker denies it.
6. Verify the runtime lacks `CREATE`/`DELETE` topic permissions.

### Exercise 3 — RabbitMQ Producer/Consumer Permissions

1. Create vhost `orders-vhost`, queue `orders.input`, and exchange `orders.status`.
2. Grant `order-consumer` read permission solely on the queue.
3. Grant `order-publisher` write permission solely on the exchange.
4. Confirm the consumer cannot publish and the publisher cannot consume.
5. Confirm neither has configure permissions or an `administrator` tag.

### Exercise 4 — Isolate Functions by Identity

You have `archiveOrder` writing to S3 and `publishOrderStatus` publishing to Kafka. Deploy them as two separate workloads with distinct roles/credentials, then try using the first workload's credentials to perform the second workload's action. The request must be denied.

**Passing criteria:** explain why `FunctionCatalog` does not form a security boundary, why beans in the same process typically share a workload identity, and demonstrate both permitted and denied operations.

## 21. References

- [AWS Lambda — Execution role and least privilege](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html): execution roles, scoped policies, and IAM Access Analyzer.
- [AWS Lambda — Managing permissions](https://docs.aws.amazon.com/lambda/latest/dg/lambda-permissions.html): identity-based and resource-based policies.
- [AWS Lambda — SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): queue polling permissions and KMS.
- [Amazon S3 — IAM integration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security_iam_service-with-iam.html): bucket ARNs, object ARNs, and S3 permissions.
- [Google Cloud Pub/Sub — Access control](https://docs.cloud.google.com/pubsub/docs/access-control): Publisher/Subscriber roles and resource-level IAM.
- [Azure Service Bus — Managed Identity](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity): Data Sender/Receiver and RBAC scopes.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/): topic, group, cluster ACLs, and operations.
- [RabbitMQ — Access control](https://www.rabbitmq.com/docs/access-control): vhosts, configure/write/read permissions, and management tags.
- [Spring Cloud Stream — Kafka security configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html): SASL/JAAS and binder client properties.

Role names, properties, and binder behavior depend on versions. Cross-check release-specific docs and test against real brokers/cloud runtimes before promoting policies to production.

## 22. Conclusion

**Least privilege starts with the workload's identity and ends at each specific resource and action.** With Spring Cloud Function, `Supplier`, `Function`, `Consumer`, and `FunctionCatalog` structure business logic; they do not automatically restrict cloud or broker privileges. A single process can host multiple beans sharing one execution role or broker credential, so separating beans is not equivalent to separating security boundaries.

Secure design uses workload identities/managed credentials, separates inbound from outbound permissions, constrains actions and resources, separates provisioning from the data plane, applies broker ACLs by topic/group/vhost, manages secrets and TLS properly, and tests both permitted and denied operations. Whenever functions require distinct privilege levels, consider isolating them into separate workloads so each has an independent identity, policy, audit trail, and lifecycle.
