# Designing Least Privilege for Each Function

In a serverless system, each function typically performs only a small part of a workflow: receiving an HTTP request, processing a message, writing data, sending a notification, or orchestrating a workflow step. If every function shares a single execution role with permissions to read every bucket, write to every table, and invoke every service, a bug in one function can escalate into a system-wide security incident.

**Least privilege** means granting each workload identity only the actions needed on the right resources, within the necessary scope and time window. To apply this principle, you need to distinguish between the caller's identity, the function's runtime identity, the permission to invoke the function, and the function's permissions to access downstream services. Private networks, firewalls, and endpoint policies add a layer of protection, but they do not replace identity and access control.

This lesson focuses on designing permissions for individual Java functions in a serverless system, using AWS Lambda/IAM and Google Cloud service accounts as examples. You will learn how to separate execution roles, restrict resource ARNs, configure trigger permissions, call services with temporary credentials, control networking, and test both allowed and denied access paths.

## Learning Objectives

After this lesson, you can:

- Distinguish between end-user identity, caller identity, function execution identity, and resource identity.
- Explain why each function or workload should have its own workload identity.
- Design an AWS Lambda execution role with a least-privilege trust policy and permission policy.
- Distinguish between identity-based policies, resource-based policies, and event source mapping permissions.
- Restrict actions, resources, conditions, and KMS permissions to exact requirements.
- Configure a dedicated service account for Cloud Run and distinguish invoke permissions from runtime permissions.
- Use AWS SDK for Java 2.x or Google Application Default Credentials without storing access keys in code.
- Combine IAM with VPCs, security groups, private endpoints, and ingress controls.
- Separate runtime permissions from deployment permissions, audit permissions, and test negative cases.

## 1. Four Types of Identities to Distinguish

A serverless request can involve multiple principals. Without identifying the right principal at each step, development teams easily grant permissions in the wrong place.

| Identity | Who or what does it represent? | Example |
|---|---|---|
| End-user identity | The end user performing the action | User logged in via Cognito or Identity Platform |
| Caller identity | The principal calling the endpoint or invoking the function | API Gateway, EventBridge, IAM role of another service |
| Workload/runtime identity | What the function or container uses when calling other services | Lambda execution role, Cloud Run service account |
| Resource policy/target | The resource receiving the request and the policy defining which principals are allowed | S3 bucket policy, Lambda resource policy, Cloud Run IAM policy |

A request flow might look like this:

~~~mermaid
flowchart TD
    U["End user / upstream service"] --> A["API Gateway / Event trigger"]
    A -->|"Invoke permission"| F["Java Lambda function"]
    F -->|"Assume execution role"| R["Function runtime identity"]
    R --> D["Database / Queue / Object storage / Secret"]
    F --> Z["Application authorization"]
    U -. "JWT claims / principal context" .-> Z
~~~

- Users are authenticated at API Gateway or the application authentication layer.
- API Gateway or the event service needs permission to invoke the function according to the integration mechanism.
- The function runs with its own runtime identity to access databases, queues, secrets, or storage.
- Business code must still check whether the user is authorized to operate on a specific order, tenant, or resource.

**The execution role is not the end user's identity.** Just because Lambda has permission to read all orders does not mean the user sending the request is allowed to read all orders. Business authorization must check the subject, tenant, ownership, and policy from the authenticated context.

## 2. Why Should Each Function Have Its Own Identity?

Suppose an ordering system has the following functions:

- `order-api`: receives requests and creates orders.
- `inventory-reserver`: reserves inventory stock.
- `payment-processor`: calls the payment gateway.
- `invoice-writer`: generates invoices in object storage.
- `notification-sender`: sends emails or notifications.

If all five functions share a single role that can read/write the database, S3, SQS, Secrets Manager, and invoke any Lambda, each function can do far more than its actual responsibility.

Separated permission design:

| Function | Resources to access | Typical required permissions |
|---|---|---|
| order-api | Orders table, order-created queue | Read/write operations needed on orders; send messages to the queue |
| inventory-reserver | Inventory table, reservation queue | Conditional update on inventory; read source messages |
| payment-processor | Payment secret, payment provider | Read only the specific secret; call outbound API |
| invoice-writer | Invoice bucket | Write objects under the invoices prefix |
| notification-sender | Notification queue/provider secret | Read messages; send notifications |

Benefits:

1. **Limit blast radius:** if one function is compromised, the attacker only gets the permissions of that role.
2. **Easier auditing:** CloudTrail or audit logs show which workload identity performed an action.
3. **Easier detection of excess permissions:** a function that does not need S3 has no S3 permissions.
4. **Independent deployment:** permissions for one function can be changed without elevating permissions for others.
5. **Separation of responsibilities:** teams owning each function can clearly define resource contracts.

Separate roles by function or by workload boundary that shares the same risk profile and lifecycle. There is no need to create a new role for every tiny helper if they truly share the same trust boundary and permission set; however, functions handling sensitive data or critical side effects should have dedicated identities.

## 3. AWS Lambda Trust Policy and Permission Policy

AWS Lambda uses an IAM execution role. It has two main parts:

- **Trust policy:** defines which principal is allowed to assume the role.
- **Permission policy:** defines which actions code running with the role can perform on which resources.

Basic trust policy for Lambda:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This trust policy allows the Lambda service to assume the role. It does not grant code permission to read S3, DynamoDB, or secrets. Those permissions belong in the permission policy attached to the role.

For workloads requiring stricter constraints, you can add source conditions to the trust policy to restrict which function/account is allowed to use the role. Illustrative example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:lambda:ap-southeast-1:123456789012:function:order-api"
        }
      }
    }
  ]
}
~~~

Conditions must match the actual ARN/account and how Lambda assumes the role in the deployment environment. When a function is renamed or moved to another account/region, the trust policy must be updated along with the deployment.

Example permission policy for an order processing function:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteOrderRecords",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:ap-southeast-1:123456789012:table/Orders"
    },
    {
      "Sid": "PublishOrderCreated",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-created"
    },
    {
      "Sid": "WriteFunctionLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/lambda/order-api:*"
    }
  ]
}
~~~

This policy is an example only. If the function needs to create the log group for the first time, it may need `logs:CreateLogGroup` scoped appropriately; another approach is creating the log group via infrastructure deployment. Identify the exact APIs your code and runtime require, then grant permissions according to each action's resource-level support.

Do not attach `AdministratorAccess` or `PowerUserAccess` to an execution role just to resolve an AccessDenied error. Identify the denied action and resource, then add only the required permission.

### Separating Logging Permissions from Business Permissions

Logging is part of operations, but it should not be used as an excuse for broad permissions. You can pre-create the log group via IaC and grant the role permission only to write log streams/events within that function's log group. If using CloudWatch Logs subscriptions or destinations, managing subscriptions typically belongs to the deployment role.

## 4. Restricting Actions and Resources

An IAM statement should restrict at least three elements:

1. **Action:** what is the function allowed to do?
2. **Resource:** on which resources is the function allowed to act?
3. **Condition:** under what circumstances is the action allowed?

Anti-pattern example:

~~~json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*"
}
~~~

If a function only reads one secret, the policy can restrict it:

~~~json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/payments/provider-*"
}
~~~

If a function only writes invoice files under a single S3 prefix:

~~~json
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::company-invoices/prod/*"
}
~~~

If bucket metadata needs to be read, an action like `s3:ListBucket` applies to the bucket ARN, whereas `s3:GetObject` applies to the object ARN. Do not mix the two resource ARN types assuming the policy will work the same way.

Some actions do not support resource-level permissions or require `Resource: "*"`. In that case, isolate those actions into a separate statement, use condition keys if supported by the service, and document the reason. Do not broaden the entire policy just because one action requires a wildcard.

### Condition Keys

Conditions can restrict permissions by:

- Source ARN or source account for a service principal invoking Lambda.
- VPC endpoint through which the request passes, if supported by the service and action.
- Encryption context or KMS key context.
- Principal tags, resource tags, or organization ID where appropriate.
- TLS or security conditions supported by the service.

Conditions must be based on keys actually supported by the service for that action. A miswritten condition can break permissions or create a false sense of security. Test both valid requests and requests that must be denied.

## 5. Function Invoke Permissions Differ from Resource Access Permissions

One of the most common IAM mistakes is confusing Lambda invocation permissions with the execution role.

### Caller Invoking Lambda Directly

If an IAM role for service A invokes Lambda B using the SDK, A's role needs `lambda:InvokeFunction` on the specific function/alias ARN:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:inventory-reserver:prod"
    }
  ]
}
~~~

Function B still uses its own execution role to read the inventory table or write to the reservation queue. Invoke permission does not grant the caller permission to read the data accessed by the function.

### AWS Services Invoking Lambda

For push invocation services such as S3, SNS, or EventBridge, a Lambda resource-based policy typically allows the service principal to invoke the function. Example EventBridge rule:

~~~bash
aws lambda add-permission \
  --function-name order-event-handler \
  --statement-id allow-orders-rule \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-southeast-1:123456789012:rule/orders-created
~~~

For production integrations, restrict the source ARN and source account when appropriate. If the trigger invokes an alias, grant the permission on the exact qualifier and configure the target to point to that same alias.

With S3 notifications, the source ARN is typically the bucket ARN, and a source account can be added. Ensure the bucket and Lambda are in compatible regions as required by the integration. Do not grant permission to an entire service principal without source constraints if the service supports source conditions.

### SQS and Stream Event Source Mapping

SQS uses a poll-based event source mapping model. The Lambda service polls the queue using the permissions of the execution role configured for the function. The role typically needs actions such as:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-queue"
    }
  ]
}
~~~

If the queue is encrypted with a customer-managed KMS key, also check KMS permissions and the key policy. For cross-account queues, a queue resource policy allowing the appropriate principal may also be needed.

DynamoDB Streams or Kinesis also require appropriate stream/shard read permissions on the execution role, such as `dynamodb:DescribeStream`, `dynamodb:GetRecords`, `dynamodb:GetShardIterator`, `dynamodb:ListStreams`, or the corresponding Kinesis actions for the mapping. Some listed actions may require a resource wildcard because they do not support resource-level scoping; isolate them into a separate statement. Do not grant write access to the entire table if the function only consumes the stream.

### Distinction Matrix

| Integration | Where are invoke/poll permissions? | What else does the runtime role need? |
|---|---|---|
| API Gateway → Lambda | Lambda resource policy for the API Gateway service principal or configured invoke mechanism | Permissions to read/write data performed by the code |
| EventBridge → Lambda | Lambda resource policy for the rule/source ARN | Permissions to access business resources |
| S3 notification → Lambda | Lambda resource policy for the bucket/source account | `s3:GetObject` only when code actually reads objects |
| SQS event source mapping | Execution role allowing poll/delete messages | Database, secret, output queue permissions per logic |
| DynamoDB/Kinesis stream mapping | Execution role with stream read permissions | Read/write permissions on other resources per logic |
| Service A calls Lambda B via SDK | A's identity policy has `lambda:InvokeFunction` | B's execution role has permissions to handle the work |

Do not grant `s3:GetObject` to Lambda just because S3 is the event source if the function only reads metadata in the event. Only grant object read permissions when code actually calls the S3 API.

## 6. Per-Function KMS and Secret Permissions

When a function reads a secret, its role needs permission to read that exact secret. If the secret is encrypted with a customer-managed KMS key, the role may need `kms:Decrypt`, and the key policy must allow the principal to use the key.

Example with two separate statements:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPaymentSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/payments/provider-*"
    },
    {
      "Sid": "DecryptPaymentSecret",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    }
  ]
}
~~~

Both the KMS key policy and IAM policy participate in permission evaluation depending on how the key is configured. Do not grant `kms:*` on all keys. If the key policy supports appropriate encryption context conditions, you can further restrict by secret or service context.

A function that only sends emails does not need permission to read the database password. A function that only handles inventory does not need the payment API key. Separating secrets by domain and permissions by function reduces the chance that one leaked credential compromises the whole system.

## 7. Java: Using the Default Credential Provider

Java code should not contain access keys or secret access keys. AWS SDK for Java 2.x can use the default credentials provider chain to fetch temporary credentials from the runtime environment, including execution role credentials provided by Lambda.

Example:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class InventoryRepository {
    private final DynamoDbClient dynamoDb;

    public InventoryRepository() {
        this.dynamoDb = DynamoDbClient.builder()
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    // Repository methods use the client to access the permitted table.
}
~~~

In Lambda, the execution role provides temporary credentials and the SDK automatically refreshes them via the provider mechanism. SDK clients should be reused within the same execution environment if thread-safe; do not create a new client per request. Never log credentials, session tokens, or all environment variables.

On Google Cloud, Java client libraries typically use **Application Default Credentials (ADC)**. When running on Cloud Run, attach a user-managed service account as the runtime identity; the client library fetches short-lived credentials from the metadata server. Do not generate and mount a JSON service account key if the environment supports attached service accounts.

## 8. Google Cloud: Dedicated Service Account per Cloud Run Service

A Cloud Run service has two important identities:

- **Caller identity:** the principal needing permission to invoke the target service, typically `roles/run.invoker`.
- **Runtime service account:** the identity the container uses when calling Google Cloud APIs.

Architecture example:

| Service | Runtime service account | Granted permissions |
|---|---|---|
| orders-api | `orders-api-runtime@` | Write orders, publish to the right topic |
| inventory-worker | `inventory-runtime@` | Read subscription, update inventory |
| invoice-worker | `invoice-runtime@` | Write objects to the invoice bucket |
| payment-worker | `payment-runtime@` | Read the specific secret and call the payment provider |

Attach the service account to the service during deployment. Example:

~~~bash
gcloud run deploy orders-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1 \
  --region REGION \
  --service-account orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated
~~~

Grant permission for a caller to invoke the service:

~~~bash
gcloud run services add-iam-policy-binding orders-api \
  --region REGION \
  --member serviceAccount:frontend-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker
~~~

`roles/run.invoker` allows the principal to invoke the Cloud Run service; it does not grant the container permission to read Secret Manager or write to a bucket. Those permissions must be attached to the separate runtime service account.

Do not use the default compute service account for every service if it has broad permissions. Create user-managed service accounts per workload, grant roles at the smallest possible resource scope, and do not create static keys when attached identities meet the need.

## 9. Service-to-Service and Cross-Account Permissions

When function A calls function B, both sides must be defined:

- A has permission to invoke B.
- B can verify the caller or receive requests authenticated by the integration.
- B uses B's own runtime identity to access data.
- If two different accounts/projects are involved, both sides need corresponding policies.

For AWS cross-account Lambda invocation, the caller role in account A needs an identity policy allowing `lambda:InvokeFunction` on function B; function B's resource-based policy in account B must allow the principal/account A. If using an alias, grant permission on the exact alias ARN.

For Google Cloud service-to-service, the caller service needs invoke permission on the target Cloud Run service and must send an ID token with the matching audience. The calling service's runtime service account does not automatically become the end user's identity.

Never pass service A's access keys in an event payload for service B to reuse. Use the platform's workload identity and temporary credentials, or supported token exchange mechanisms.

## 10. Combining IAM with Network Controls

IAM defines which principal is allowed to perform an action. Network controls define which network path a request can take and which endpoints it can reach. The two layers complement each other.

For example, a Lambda may have IAM permission to read a specific secret, yet still need a valid network route if the function is placed in a VPC and accesses Secrets Manager via a private endpoint. Conversely, a function inside a private subnet does not automatically have permission to read a secret just because it sits on an internal network.

### AWS Lambda in a VPC

When Lambda needs to access resources in a private subnet:

- Choose appropriate subnets and security groups.
- Restrict outbound rules on the security group attached to Lambda; on the database side, allow inbound traffic only from Lambda's security group on the required port.
- Use VPC endpoints for supported AWS services when private network access is desired.
- With endpoint policies, restrict principals/actions/resources if supported by the service.
- Check route tables, DNS, NACLs, and security groups when requests time out.
- If the function needs public internet access from a private subnet, design appropriate NAT egress; VPC attachment alone does not create an outbound internet path.
- Do not place a function in a VPC if it does not need to access private resources; VPC configuration can add complexity and affect cold start/networking.

Security groups control network traffic, not IAM. If a function has outbound access to the internet, you still must protect endpoints with TLS, authentication, and application-layer authorization.

### Google Cloud Run

Cloud Run can configure ingress to restrict request sources, use IAM Invoker for service-to-service calls, and configure Direct VPC egress or Serverless VPC Access when private network access is required.

- Ingress controls where requests can enter the service from.
- IAM Invoker determines which principals can invoke the service.
- The runtime service account governs permissions to access Google Cloud APIs.
- VPC/firewall controls govern network routes to private resources.

Do not treat internal ingress as a replacement for application authorization if the service still has multiple callers or requires per-user/tenant authorization.

### Control Layer Selection Table

| Threat or Requirement | Control Layer |
|---|---|
| Unauthorized caller invokes function | IAM identity policy/resource policy |
| Function reads the wrong table or secret | Execution role/service account and resource scope |
| User reads another tenant's data | Authorization in Java service and query scope |
| Request originates from an unwanted network | Ingress, VPC, firewall, endpoint policy |
| Credentials leaked in source code | Secret manager, workload identity, short-lived credentials |
| One function is compromised | Dedicated identity, least privilege, restricted egress, and audit |

## 11. Separating Deployment Permissions from Runtime Permissions

Deployment permissions are usually broader than runtime permissions. A pipeline may need to create functions, update images, publish versions, attach roles, update aliases, and configure triggers. A runtime function only needs to read/write business resources during execution.

Separate at least two principals:

- **Deployment identity:** allowed to create/update functions and configure infrastructure. On AWS, `iam:PassRole` must be restricted to approved execution roles.
- **Runtime identity:** attached to the function and granted only the permissions needed at runtime.

Do not attach `iam:PassRole`, `iam:CreatePolicy`, `lambda:UpdateFunctionCode`, or `iam:AttachRolePolicy` to a function's execution role. If runtime code can modify its own role or update the function, an application bug can turn into infrastructure takeover.

On Google Cloud, the service account used for deployment is also distinct from the runtime service account. The deployer needs permission to attach the service account per organization policy; the container only receives the permissions of the attached runtime identity.

## 12. Least-Privilege Design Workflow

A workflow you can apply per function:

1. **Document responsibilities:** what triggers does the function receive and what business logic does it perform?
2. **List API calls:** identify which AWS/GCP APIs the code, SDK, extensions, or event source mapping actually invoke.
3. **Identify principals:** caller, runtime identity, service principal, and relevant resource policies.
4. **List resources:** target tables, buckets, queues, secrets, keys, or functions; record exact ARNs/names.
5. **Create minimal policies:** only needed actions on specific resources; use conditions where appropriate.
6. **Configure networking:** subnets, security groups, ingress, and endpoints only for required paths.
7. **Test positive and negative cases:** valid operations succeed; out-of-scope operations return AccessDenied.
8. **Observe production:** monitor AccessDenied, API usage, audit logs, and resource access.
9. **Review periodically:** remove unused actions/resources, check for role drift and secret access.
10. **Document owners:** every role/service account has a clear workload owner and change process.

### Example Permission Matrix

| Function | Trigger | Runtime resources | Permissions it should NOT have |
|---|---|---|---|
| order-api | API Gateway | Orders table, order queue | Payment secret, invoice bucket |
| inventory-worker | SQS | Inventory table | Orders API invoke, payment key |
| payment-worker | SQS | Payment secret, payment provider | Inventory table, invoice bucket |
| invoice-worker | EventBridge/SQS | Invoice bucket, invoice metadata table | Payment secret, user directory |
| notification-worker | SQS | Notification secret/provider | Database admin, function deployment |

This matrix is a starting point for authoring policies. Next, verify every actual SDK operation, event source mapping, KMS key, and resource policy.

## 13. Testing and Auditing Permissions

A policy that deploys successfully is not necessarily correct. Both allowed and denied behaviors must be verified.

### Positive Tests

- The order-api function can write to the Orders table.
- The order-api function can publish messages to the right queue.
- The payment worker can read the right payment secret.
- The invoice worker can write objects under the granted prefix.
- Valid callers can invoke the function alias or Cloud Run service.

### Negative Tests

- The Order API cannot read the payment secret.
- The payment worker cannot write to the invoice bucket.
- The invoice worker cannot read the Orders table if not needed.
- Unauthorized callers cannot invoke the production function.
- Other principals cannot invoke internal Cloud Run services.
- A function cannot access resources in another environment.

IAM Policy Simulator can help evaluate certain identity policies, but it does not replace integration tests involving resource policies, trust policies, KMS key policies, service integrations, and actual runtime conditions. Run tests in an account/project without production data.

### Auditing and Detecting Excess Permissions

- Use AWS CloudTrail to inspect API calls by roles and resources; enable data events for tracked resource types where appropriate.
- Use IAM Access Analyzer to detect externally shared resource policies or unintended access.
- Use Google Cloud Audit Logs to check which principals access resources and IAM policy changes.
- Track AccessDenied and permission errors by function/revision.
- Review roles/service accounts no longer attached to any workload.
- Remove unused policy statements after verifying over a sufficient observation window.

Do not remove permissions solely because no invocations were seen over a short period. A function might run on a schedule or handle rare events. Combine owner input, schedules, triggers, and audit history before revoking permissions.

## 14. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| All functions share an admin role | Large blast radius | Separate workload identities and policies |
| Confusing invoke permission with execution role | Caller or function lacks permission at the wrong layer | Map principal flow for each step |
| Using `Resource: "*"` for every action | Function gets access to unrelated resources | Narrow ARNs; isolate actions requiring wildcards |
| Relying solely on private subnets | Internal services can still be miscalled or have overly broad data access | Combine IAM, app authorization, and network controls |
| Putting access keys in environment variables | Long-lived credentials can be leaked | Use workload identity and temporary credentials |
| Granting KMS permissions on all keys | A function can decrypt out-of-scope secrets | Restrict key ARN and key policy |
| Giving the runtime role deploy permissions | Code bugs can alter infrastructure or roles | Separate the deployment identity |
| Not testing negative cases | Excess permissions go undetected | Attempt out-of-scope actions and verify denial |
| Trusting client-supplied claims | Can bypass tenant/user authorization | Use authorizer context and verify ownership server-side |

## 15. Least-Privilege Checklist for Java Serverless

- [ ] Each sensitive function has its own workload identity.
- [ ] Caller identity, end-user identity, and runtime identity are clearly separated.
- [ ] Trust policy allows only the right runtime/service to assume the role.
- [ ] Permission policy contains only required actions.
- [ ] Resource ARNs are scoped to specific tables, bucket prefixes, queues, secrets, or functions.
- [ ] Actions lacking resource-level scoping are isolated and justified.
- [ ] Lambda resource policy restricts service principals using source ARN/account when appropriate.
- [ ] SQS/stream event source mappings have poll/read permissions on the exact source.
- [ ] KMS permissions and key policies allow only the necessary keys.
- [ ] Java SDK uses default credential providers/ADC without static keys.
- [ ] Cloud Run services use per-workload user-managed runtime service accounts.
- [ ] Callers have separate invoke permissions; runtime service accounts have separate resource access permissions.
- [ ] Cross-account invocations are permitted on both caller and resource sides when needed.
- [ ] Network ingress, egress, VPC, and endpoint policies match actual traffic flows.
- [ ] Deployment identity is separated from runtime identity; `iam:PassRole` is restricted.
- [ ] Positive and negative tests exist for each function.
- [ ] Audit logs and AccessDenied alerts are monitored.
- [ ] Policies are reviewed when triggers, resources, or function responsibilities change.

## Self-Check

1. How do end-user identity, caller identity, and function execution identity differ?
2. Why should two functions handling payments and notifications not share a role that can read all secrets?
3. Which two questions do Lambda's trust policy and permission policy answer?
4. When API Gateway calls Lambda, why must invoke permission be distinguished from Lambda's permission to read the database?
5. With SQS event source mapping, what permissions does the execution role need to poll the queue?
6. When a function only receives S3 event metadata without reading the object, does it need `s3:GetObject`?
7. Why does cross-account Lambda invocation require policies on both the caller and resource sides?
8. Does a private network replace IAM and per-tenant authorization?
9. Why must the deployment role be separated from the runtime execution role?
10. What types of permission bugs do negative tests catch that positive tests cannot?

Designing least privilege starts from each function's responsibilities and actual principal flow. Each workload uses its own identity and is allowed to call only the necessary actions on specific resources; triggers, runtime, and end users are controlled at their proper boundaries. By combining IAM, resource policies, network controls, temporary credentials, auditing, and negative testing, a compromised function is far less likely to spread to out-of-scope data and services.
