# Assigning Per-Function Identities and Least Privilege Permissions

A serverless function is typically triggered by an API Gateway, a queue, object storage, a schedule, or another cloud service. During processing, the function may need to read data, write results, send messages, retrieve secrets, or call an internal service. If the function uses an identity with overly broad permissions, a bug in the code or exploitation of a vulnerability can escalate into unauthorized access across many resources in the cloud account.

The principle of least privilege requires each function to have only the exact permissions needed to complete its task, on the exact resources, for the exact duration, and in the exact context. The function's execution identity must be separated from the caller's identity, the triggering service's identity, and the deployment pipeline's identity. These identities represent different principals and carry different permissions.

This lesson covers how to assign per-function identities, design trust policies and permission policies, protect secrets, restrict function invocation permissions, handle cross-service events, and audit activity. After this lesson, you will be able to:

- Distinguish between caller identity, trigger service identity, execution identity, and deployment identity.
- Assign dedicated execution roles, managed identities, or service accounts based on function responsibility.
- Author permissions following a deny-by-default approach, scoping actions, resources, and conditions.
- Distinguish permissions to invoke a function from permissions the function uses to access other services.
- Use workload identities and short-lived credentials instead of embedding access keys in code.
- Store and retrieve secrets securely with rotation and auditing.
- Verify effective permissions, detect unused permissions, and troubleshoot access incidents.

## 1. Different Identities in a Serverless Flow

In a serverless flow, multiple principals may participate. Grouping all of them into a single shared role or account makes it difficult to determine who is allowed to do what and hard to contain the blast radius if one component is compromised.

For example, an API receives a report generation request and triggers a processing function; the function reads data from a bucket, writes the report to another bucket, and sends a notification to a queue. This flow may involve the following identities:

1. **Caller identity:** the user or application calling the API. This identity is authenticated using an appropriate mechanism such as OAuth/OIDC, JWT, mTLS, or IAM authentication.
2. **Trigger/service identity:** the cloud service sending an event or authorized to trigger the function. For example, a bucket sending a notification or a scheduler invoking the function on a schedule.
3. **Function execution identity:** the identity used by the function's code when calling object storage, queues, databases, a secret manager, or a logging service.
4. **Deployment identity:** the CI/CD pipeline or operator authorized to create/update the function and configure its role, environment, and triggers.
5. **Downstream service identity:** the identity of the target service when the function calls it; this may be a separate service account, database user, or workload identity.

~~~mermaid
flowchart TD
    U["User / application"] -->|Caller identity| G["API Gateway"]
    G -->|Invoke permission| F["Serverless function"]
    T["Event source / scheduler"] -->|Trigger permission| F
    F -->|Execution identity| S["Object storage / database / queue"]
    F -->|Workload identity| D["Internal service"]
    C["CI/CD deployment identity"] -->|Deploy and configure IAM| F
~~~

The key point is that the API caller's identity does not automatically become the function's execution identity. A function typically runs with the execution role or service identity attached to its runtime. If the application needs to know which end user requested the operation, it must securely pass the authenticated context and enforce authorization in business logic.

### Four Questions to Answer

- Who is allowed to invoke the function?
- Which resources is the function allowed to access at runtime?
- Who is allowed to modify the function's code, configuration, triggers, and permissions?
- Can the function act on behalf of a user or another workload when calling downstream services?

Each question corresponds to a separate permission boundary. You should not solve all of them by attaching an administrator role to the function.

## 2. What Is an Execution Identity?

An execution identity is the identity the platform provides to the serverless process when the function executes. Depending on the cloud provider, this mechanism may be called:

- An execution role or IAM role in some function services.
- A managed identity in cloud platforms that support platform-managed identities.
- A service account attached to the function or runtime.
- A workload identity federated with a service account or identity provider.

The platform typically provides temporary credentials to the runtime. Code uses those credentials to sign requests to cloud services without storing long-lived access keys in source code.

### Comparing Common Models

| Model | How It Works | What Needs to Be Managed |
|---|---|---|
| IAM execution role | The function assumes a role via a trust relationship; the runtime receives temporary session credentials | Trust policy, permission policy, session duration, and resource scope |
| Managed identity | The platform issues an identity for the compute resource | Role assignments from the identity to target resources and restricting where the identity is attached |
| Service account | The function runs under a designated service account | IAM bindings, impersonation permissions, and account scope |
| Workload identity federation | The workload's identity is federated with an identity provider | Issuer, subject, audience, trust conditions, and token exchange permissions |

Naming and configuration differ across providers. The general principle is to let the platform issue short-lived credentials to the workload, and then grant least-privilege permissions to that identity.

### Do Not Use User Accounts as Execution Identities

You should not configure a function to use a developer's personal credentials or an administrator account. When staff leave the team, passwords change, or user permissions shift, the function may stop working or continue holding overly broad privileges. Execution identities should belong to the workload, with clear ownership and a lifecycle managed alongside the application.

## 3. Each Function Needs a Dedicated Identity by Responsibility

If multiple functions share a single role, the role's permissions typically become the union of all permissions required by every function. An image-reading function might accidentally gain permission to delete objects; an email-sending function might gain permission to read customer data; a webhook handler might gain access to payment system secrets.

Separating execution identities by function responsibility helps limit the blast radius:

| Function | Responsibility | Illustrative Least-Privilege Permissions |
|---|---|---|
| image-resizer | Read input images, write thumbnails | Read objects in the input prefix; write objects in the thumbnails prefix |
| invoice-generator | Read invoice data, write PDFs | Read required records; write to the invoice-output bucket |
| email-dispatcher | Send notifications | Consume messages from the queue; call the email delivery service |
| token-validator | Validate tokens | Read appropriate public keys/JWKS or verification secrets; no write access to business data |
| cleanup-job | Delete expired data | List and delete within managed prefixes; no permission to delete the bucket |

A dedicated role per function is a safe starting point, especially when functions have different trust levels or handle different data. Sharing a role across functions is only appropriate when they share the same responsibility, data boundary, owner, and security requirements—not merely for configuration convenience.

### Separating by Environment and Tenant

Dev, staging, and production should have separate identities or roles. A function in a test environment should not have permission to write to a production bucket. In multi-tenant systems, if tenants have distinct data boundaries or compliance requirements, you must define isolation using accounts/projects/subscriptions, resource policies, conditions, or an application authorization layer.

Do not treat function names or tenant environment variables as proof of authorization. Clients can alter inputs; permissions must be enforced via trusted server-side identities and policies.

## 4. Distinguishing Trust Policy and Permission Policy

In models where a role can be assumed, there are typically two policy sets:

- **Trust policy:** defines which principals are allowed to assume the role or obtain its credentials.
- **Permission policy:** defines which actions the principal is allowed to perform on which resources after assuming the role.

The trust policy answers "who can wear this identity?" The permission policy answers "what can this identity do?"

A role with very narrow permissions whose trust policy allows any workload in the account to assume it can still be abused. Conversely, a trust policy restricted to the exact function combined with an administrator permission policy is still overly broad.

### What the Trust Policy Must Restrict

- The exact runtime service or workload identity provider.
- The exact account, project, subscription, or organization.
- The exact function, service account, namespace, or workload subject when supported by the platform.
- The exact audience, issuer, and subject when using federation.
- Confused deputy protections if the service supports external IDs or source ARN/account conditions.

Do not use broad wildcard principals without justification and additional constraining controls. With trust federation, verify the exact issuer, subject, and audience; an overly broad pattern can allow unrelated workloads to obtain the role.

### What the Permission Policy Must Restrict

- **Action:** only the required operations, such as reading objects rather than full storage permissions.
- **Resource:** specific ARNs, resource IDs, buckets/prefixes, queues, or secrets.
- **Condition:** restrictions by tag, encryption, network, source account, time, or context when supported by the platform.
- **Effect:** deny by default; allow only explicitly defined cases.

A good permission policy clearly states what the function can read, write, send, receive, or invoke. Avoid granting wildcards on actions and resources just to make `AccessDenied` errors disappear.

## 5. Function Invocation Permissions Differ from Resource Access Permissions

This is a common point of confusion in serverless architectures.

### Invoke Permissions

Invoke permissions determine which principals can call the function. Principals may include:

- API Gateway or an HTTP gateway.
- Event sources such as object storage, a scheduler, or a notification service.
- Another function.
- Users or applications calling directly.

Some platforms use a resource-based policy attached to the function to allow other services to invoke it. Others use trigger configurations, event subscriptions, or bindings. You must identify the specific mechanism used by the service.

### Execution Permissions

Execution permissions determine what the function can do once running. For example, a function may read objects from bucket A and write results to bucket B. Allowing API Gateway to invoke the function does not automatically grant the function permission to read bucket A.

Conversely, giving a function permission to read a bucket does not mean any principal can invoke the function. Both permission sets must be configured independently.

### Event Push vs. Event Pull

With push-based events, the source service calls the endpoint or function. The function usually needs permissions allowing that specific source service to invoke it. With pull-based events, an event source mapping or poller reads messages from a queue and then invokes the function; queue read permissions may belong to the execution role or the poller's identity depending on the platform. Inspect the actual architecture rather than applying a single permission pattern to every trigger.

## 6. Designing Policies by Action, Resource, and Condition

A practical approach is to build a permission matrix before writing policies:

| Operation in Code | Required Action | Resource | Permissions Not Needed |
|---|---|---|---|
| Read source image | Get/read object | Input bucket, `uploads/` prefix | Delete bucket, list all buckets |
| Write thumbnail | Put/write object | Output bucket, `thumbnails/` prefix | Read all objects, delete objects if unnecessary |
| Receive job | Receive/consume message | `image-jobs` queue | Purge queue, delete queue |
| Retrieve API token | Read secret value | Specific secret | List and modify all secrets |
| Write logs | Create stream/append events | Function's log group | Delete log group or alter retention |

### Least-Privilege Permission Policy Example

The JSON example below illustrates a function that only reads objects in an input prefix and writes objects in a thumbnail prefix. The action names and resource ARNs follow an IAM-style example; replace them with the exact syntax and permissions of your cloud provider.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadUploadedImages",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::media-input/uploads/*"
    },
    {
      "Sid": "WriteThumbnails",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::media-output/thumbnails/*"
    }
  ]
}
~~~

The policy does not grant permissions to list buckets, delete objects, or access other buckets. If the code needs to read metadata via `HeadObject` or list a prefix, identify the additional action and scope the corresponding resource/condition. Do not add permissions merely because an online example includes more actions.

### Be Careful with Wildcards

Wildcards in resources can be useful for scoping to a prefix, but check how the provider evaluates ARNs and conditions. Wildcards in actions like `storage:*` or `iam:*` often grant massive privileges. Prefer listing explicit actions and validating policies with the provider's permission analysis tools.

### Permission Boundaries and Organization Policies

In larger environments, permission boundaries, service control policies, organization policies, or equivalent guardrails can cap the maximum permissions a role/function may receive. These layers do not replace workload permission policies; they establish an upper bound or additional constraints.

When investigating `AccessDenied`, inspect directly attached policies, resource policies, boundaries, organization policies, session policies, and conditions. An `Allow` in one place does not guarantee a request is permitted if there is an explicit `Deny` or an unsatisfied condition.

## 7. End-to-End Example: Image Processing Function

Suppose a system has an input bucket receiving images, a function resizing images, an output bucket storing thumbnails, and a queue recording processing errors.

Identities are separated as follows:

| Principal | Permissions |
|---|---|
| Object storage event service | Only allowed to invoke the function from the designated input bucket |
| `image-resizer` execution role | Read objects in the `uploads` prefix; write objects in the `thumbnails` prefix; write logs |
| Deployment pipeline | Update function code and configuration; attach approved roles |
| Uploading user | Only allowed to upload via the granted mechanism, cannot assume the execution role |

Processing flow:

1. The user uploads an image to the bucket via an API or pre-signed URL.
2. Object storage emits an event to the function.
3. The trigger policy verifies that the legitimate source is authorized to invoke.
4. The function receives its own execution identity.
5. The function reads the input object, generates the thumbnail, and writes the output object.
6. On failure, the function writes logs and can send a message to the error queue according to granted permissions.

The function does not need permissions to delete buckets, manage IAM, create users, read unrelated secrets, or access another tenant's data. If the function needs to call another service, add only the exact permissions for that resource after verifying the requirement.

## 8. Assigning Identities for AWS Lambda, Azure Functions, and Google Cloud

Naming and interfaces differ, but the model is similar: attach a workload identity to the function, then grant permissions to that identity on target resources.

### AWS Lambda

- Attach an execution role to the Lambda function.
- The trust policy allows the Lambda service to assume the role within the required scope.
- Permission policies on the role define which services the function can call.
- The function's resource-based policy can allow API Gateway, S3, or specific principals to invoke the function.
- Use temporary STS credentials provided by the runtime; do not embed long-lived access keys in environment variables.

Minimal trust policy example following the AWS model:

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

In production, the trust relationship may require additional conditions to restrict the account or source per AWS guidance and your deployment model. The execution role also needs logging permissions and least-privilege business permissions.

### Azure Functions

- Use a system-assigned or user-assigned managed identity when supported by the hosting plan and runtime.
- Assign appropriate roles on storage, Key Vault, Service Bus, or target services.
- Prefer managed identities to obtain tokens from the platform rather than storing client secrets.
- For triggers/bindings, identify which identity is used to access the event source; behavior depends on the extension, configuration, and runtime version.

A system-assigned identity has its lifecycle tied to the function app; a user-assigned identity can be attached to multiple resources when there is a clear operational reason. Sharing an identity increases the blast radius, so review carefully before sharing.

### Google Cloud Functions and Cloud Run Functions

- Choose a dedicated runtime service account per function or per workload group sharing the same responsibility.
- Grant IAM roles at the required resource level, such as a specific object, Pub/Sub subscription, or Secret Manager secret.
- Separate the runtime service account from the build/deploy service account.
- Use Application Default Credentials or the runtime's identity mechanism to obtain short-lived credentials.
- Restrict service account impersonation permissions and function deployment permissions.

A service account can be attached to multiple workloads, but each binding must be evaluated against trust boundaries. Do not grant `Editor` or `Owner` to a runtime service account just to avoid permission errors.

## 9. Secrets, Tokens, and Credentials

Secrets include API keys, database passwords, private keys, webhook signing secrets, and tokens that the application needs to authenticate with external systems. You should not:

- Hard-code secrets in source code or container images.
- Commit secrets to Git or configuration files.
- Pass long-lived secrets into build arguments.
- Write secrets to logs, exceptions, or traces.
- Share a single secret across multiple unrelated functions.

### Using Secret Manager or Key Vault

Functions should fetch secrets from a secret management service using their execution identity. Grant read access to the exact secret and version if supported by the platform. If a secret is only needed at startup, consider loading it once and managing caching within runtime lifecycle limits. If rapid secret rotation is required, provide a refresh mechanism that does not require redeploying the entire function.

Secret managers typically provide encryption at rest, access policies, versioning, auditing, and rotation integration. These features do not automatically secure the application if the function can read all secrets or leaks secret values in logs.

### Short-Lived Credentials

Short-lived credentials reduce the window of usefulness for a leaked token. You should:

- Use platform-issued identities.
- Restrict token lifetimes within service capabilities.
- Avoid writing tokens to the filesystem or shared caches unnecessarily.
- Never send tokens to clients or untrusted services.
- Handle refresh/renewal using official SDKs and runtime providers.
- Revoke or downgrade identity permissions when compromise is detected.

Do not build custom token signing mechanisms or store custom credentials if the cloud provider already offers an appropriate workload identity.

## 10. Propagating User Identity to Functions and Downstream Services

A function may need to perform actions on behalf of a user, such as reading a report the user is authorized to view. Two common patterns exist:

### Application-Level Authorization

API Gateway authenticates the caller and passes verified claims to the function. The function checks the tenant, role, and business permissions before reading data. The function's execution role remains the technical identity for accessing cloud services; code must enforce authorization based on the caller context.

### Token Exchange or Delegated Identity

In some architectures, a function needs to call a downstream service on the user's behalf. OAuth token exchange, an on-behalf-of flow, or an equivalent delegation mechanism can be used. When doing so, restrict the audience, scope, lifetime, and token types allowed for exchange.

Do not forward the caller's raw bearer token to every downstream service. The token may have an inappropriate audience, overly broad permissions, or leak through logs. Forward or exchange tokens only when the authentication and authorization design explicitly requires it.

### Do Not Trust Input for Authorization Decisions

A payload containing `userId`, `tenantId`, or `role=admin` does not prove the sender owns that identity. The function must obtain the caller identity from a context verified by the gateway or identity provider, and then verify permissions against trusted data.

## 11. Permissions for Event Sources and Triggers

Each trigger type has a different permission model:

| Trigger | Permissions to Consider |
|---|---|
| HTTP/API Gateway | Caller allowed to invoke route; gateway allowed to invoke function; function has separate execution permissions |
| Object storage notification | Storage service allowed to emit events or invoke function; restrict source bucket/account |
| Scheduler | Scheduler has permission to invoke function; function execution role remains separate |
| Queue | Poller/event source mapping needs permission to read queue and manage visibility/acknowledgement per platform |
| Pub/Sub or event bus | Publisher allowed to publish; subscription/consumer allowed to receive; function triggered per configuration |
| Database stream | Consumer needs permission to read stream/checkpoint; function needs separate downstream permissions |

For push events, a resource policy can restrict the specific service principal and source. For pull events, the integrating service may use the function's role or a dedicated identity for the event source mapping. Verify the actual permissions required by each service.

### Preventing Confused Deputy

A confused deputy occurs when a service with legitimate permissions is tricked by another party into exercising those permissions on unauthorized resources. To mitigate this risk:

- Restrict invoke sources using source account, resource ARN, organization, or equivalent conditions.
- Use an external ID when required by cross-account models.
- Do not allow a generic service principal to invoke all functions.
- Separate publisher, subscriber, and execution permissions.
- Validate the event's tenant/account before processing.

Do not rely solely on event names or caller-supplied fields; verify the source using platform metadata and policies.

## 12. Calling Downstream Services and Workload-to-Workload Authentication

When a function calls a database, internal API, or another service, use an appropriate workload identity:

- Database authentication via IAM tokens or identity integration where supported.
- OAuth client credentials or workload federation for internal APIs.
- mTLS when mutual authentication between workloads is required.
- Service account/managed identity with permissions assigned on the target resource.

Avoid storing long-lived database passwords in environment variables when tokens or a secret manager can be used. If a password is required, store it in a secret manager, restrict read access, and maintain a rotation plan.

### One Function Should Not Inherit Another Function's Permissions

If function A calls function B, do not share A's execution role with B by default. A only needs permission to invoke B; B has its own execution identity to access its data. This separation contains the impact if A is compromised.

## 13. Network Policies Do Not Replace IAM

Private subnets, firewalls, security groups, or VPC connectors can restrict the network paths a function uses. However, network reachability does not equate to authorization.

- A function with a network route to a database still needs appropriate credentials and database permissions.
- A function without a public IP can still have overly broad IAM permissions.
- An internal API may be reachable over a private network yet still require caller authentication.
- Egress restrictions help reduce exfiltration risk but do not replace permission policies.

Combine identity policies, resource policies, network segmentation, TLS, and application authorization to protect both the access path and permitted operations.

## 14. Managing Identities in CI/CD and IaC

Deployment pipelines typically need permissions to create/update functions, attach execution roles, configure triggers, and publish code. These are control-plane administrative permissions, distinct from the function's runtime permissions.

### Separating Deployment Identity and Runtime Identity

A deployment identity may be permitted to:

- Create or update functions within a specific project/account.
- Attach a pre-approved execution role.
- Update aliases, versions, or triggers within the application's scope.
- Read deployment status and necessary logs.

The deployment identity should not by default have permission to administer all IAM roles or create arbitrary policies. If a pipeline can attach any role to a function, anyone controlling the pipeline can indirectly acquire overly broad permissions.

### Infrastructure as Code

Defining roles, trust policies, permission policies, triggers, and functions in IaC enables peer review and reproducibility. In pull requests, inspect:

- Newly added permissions and their business justification.
- Whether resource ARNs or scopes were broadened.
- Whether there are wildcard actions/resources.
- Whether trust principals were broadened.
- Whether secrets or credentials are exposed in state/plan/logs.
- Whether old roles have unused permissions that should be revoked.

IaC state files can contain sensitive information; store them in a protected, encrypted, access-controlled backend.

### Federation for CI

Prefer OIDC/workload federation between the CI provider and the cloud instead of long-lived access keys. Trust conditions should restrict repository, branch, environment, or workflow identity. A token from an untrusted fork or branch should not have permission to deploy to production.

## 15. Auditing and Observing Permissions

To know which permissions a function actually uses, combine:

- IAM/control-plane audit logs.
- Service access logs such as object storage, queues, secret managers, and databases.
- Runtime logs and distributed traces.
- Provider policy simulators or permission analysis tools.
- Cloud asset inventory and credential/policy change detection.

Monitor these events:

- Role assumptions, token issuances, or managed identity token requests.
- Successful/failed function invocations.
- `AccessDenied` or authorization failures downstream.
- Changes to trust policies, permission policies, or resource policies.
- Changes to triggers, environments, and execution identities.
- Anomalous or spiking secret accesses.

Do not log raw access tokens, private keys, passwords, or full secret values. Logs should include request ID, principal ID, resource, action, outcome, and necessary context without exposing credentials.

### Detecting Unused Permissions

Periodically review:

- Actions granted that do not appear in audit logs over an appropriate time window.
- Resources no longer accessed by the workload.
- Roles no longer used by any function.
- Temporarily granted administrative permissions that have not been revoked.
- Legacy secrets or unused versions.

Do not remove permissions based solely on a short log window. Seasonal jobs or rarely executed emergency tasks may exist. Coordinate with owners, business schedules, and testing before revoking.

## 16. Workflow for Assigning Least-Privilege Permissions to a New Function

1. **Describe the task:** what inputs the function receives, what outputs it produces, and which services it calls.
2. **List resources:** buckets, queues, tables, secrets, log groups, APIs, and encryption keys.
3. **Identify principals:** caller, trigger, execution, and deployment identities.
4. **Create a dedicated identity:** appropriate role, managed identity, or service account.
5. **Restrict trust:** only the authorized runtime/function or workload can assume the identity.
6. **Write permission policies:** specific actions, specific resources, and required conditions.
7. **Configure invoke access:** allow only intended gateways/event sources/principals to call the function.
8. **Positive testing:** verify legitimate operations work.
9. **Negative testing:** verify out-of-scope access is denied.
10. **Enable auditing and alerts:** monitor assumptions, invocations, and downstream access.
11. **Post-deployment review:** compare declared permissions against observed usage and revoke excess permissions.

### Positive and Negative Testing

Example for an image processing function:

- Positive: can read objects in the `uploads` prefix.
- Positive: can write thumbnails to the `thumbnails` prefix.
- Negative: cannot read the `payroll` bucket.
- Negative: cannot delete input objects if the task does not require it.
- Negative: cannot modify IAM policies or create users.
- Negative: principals outside the approved event source cannot invoke the function.

Negative testing proves that policies actually constrain permissions, rather than merely verifying the happy path.

## 17. Troubleshooting Identity and Permission Issues

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| Function fails to start due to assume role failure | Incorrect trust policy, mismatched service principal or subject | Check trust relationship, account, issuer, audience |
| Function runs but receives `AccessDenied` | Permission policy missing action/resource or unsatisfied condition | Identify API call, principal, resource, and explicit `Deny` |
| Trigger cannot invoke function | Missing invoke permission or misconfigured event source mapping | Check resource policy, subscription, mapping, and source scope |
| Can read bucket A but not bucket B | Policy only permits resource A | Verify requirement and add permission for the exact prefix if valid |
| Secret retrieval fails | Missing secret permission, KMS decrypt permission, or network route | Check secret policy, key policy, identity, and endpoint |
| Credentials expire mid-execution | Application caches tokens improperly or fails to refresh | Use official SDK/runtime credential providers |
| Fails only in production | Identity, resource policy, or secret differs by environment | Compare role bindings, trust, account, and secret versions |
| CI deploys successfully but function cannot access services | Deployment identity can deploy, but execution identity lacks runtime permissions | Inspect both identities separately |
| Downstream function call denied | Wrong audience, scope, token exchange, or service account binding | Inspect token claims and target policy |
| Permissions broader than expected | Shared role or deployment identity allowed to attach arbitrary roles | Audit role attachments, trust, and deployment permissions |

When encountering `AccessDenied`, do not add administrator permissions to test. Extract the action, resource, principal, and request context from logs; then identify which policy is evaluating the request.

## 18. Per-Function Policy Example

Suppose a system has three functions:

| Function | Resources to Access | Granted Permissions |
|---|---|---|
| order-validator | Public key set and order read table | Read approved key material; read exact table/index |
| order-writer | Order table and event queue | Insert/update exact table; publish to exact queue |
| notification-sender | Notification queue and messaging provider secret | Consume queue; read one secret; send via provider |

If a shared role is used, all three functions receive the combined permissions of all three groups. When identities are separated, a vulnerability in `notification-sender` does not automatically grant write access to the order table. This is the benefit of separation by responsibility.

### AWS Policy Example for a Queue Consumer

Illustrative policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeNotificationQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:notification-jobs"
    }
  ]
}
~~~

The actual action list must match the event source mapping, polling behavior, and queue encryption configuration. If the queue uses a customer-managed KMS key, decrypt permissions on that exact key may be required and the key policy must allow the principal. Do not grant queue purge or queue management permissions if the function only needs to consume messages.

## 19. Common Mistakes

1. **Using a single admin role for all functions:** one minor vulnerability can expose the entire system.
2. **Confusing invoke permissions with execution permissions:** the gateway can call the function, yet the function still lacks resource access, or vice versa.
3. **Using personal credentials:** function lifecycle becomes tied to employee accounts whose permissions are often too broad.
4. **Embedding access keys in code or environment variables:** secrets can leak via repositories, logs, or configuration snapshots.
5. **Scoping actions without scoping resources:** the function can operate across every bucket, queue, or secret.
6. **Overly broad trust policies:** unrelated workloads can assume the role.
7. **Trusting `tenantId` or `userId` from input:** clients can spoof authorization context.
8. **Sharing identities across environments:** staging can access production.
9. **Forgetting KMS or resource policies:** the function's policy allows access, but the target resource still denies it.
10. **Skipping negative permission tests:** only proving valid operations work without proving out-of-scope operations are blocked.
11. **Failing to revoke temporary permissions:** debug or deployment privileges persist longer than necessary.
12. **Logging tokens/secrets:** creates another credential leakage path.

## 20. Per-Function Identity Checklist

- [ ] Caller, trigger, execution, and deployment identities are documented.
- [ ] Each function has a dedicated role/managed identity/service account by responsibility.
- [ ] Trust policy allows only the authorized runtime or workload to assume the identity.
- [ ] Permission policy contains only required actions.
- [ ] Resource scope is restricted to exact buckets, prefixes, queues, tables, secrets, or keys.
- [ ] Conditions and explicit denies are used where needed to protect boundaries.
- [ ] Invoke permissions are configured separately from execution permissions.
- [ ] Push triggers and pull event sources follow the platform's exact model.
- [ ] No long-lived access keys or personal credentials are used in the function.
- [ ] Secrets are stored in a secret manager with rotation enabled.
- [ ] Caller identity is verified; client-supplied user/tenant fields are never trusted.
- [ ] Deployment identity cannot arbitrarily attach administrative roles to functions.
- [ ] Network policies complement IAM and application authorization.
- [ ] Audit logs record principal, action, resource, and outcome without exposing secrets.
- [ ] Both allowed operations and denied operations have been tested.
- [ ] Owners, review processes, and revocation timelines exist for unused permissions.

## 21. Applied Exercise

A serverless system has two functions:

- `invoice-reader` reads invoice data from a database and creates PDF files in the `invoice-output` bucket.
- `email-sender` receives messages from a queue, retrieves an email provider API key from a secret manager, and sends emails to customers.

Currently, both functions share a single execution role with permissions to read/write all buckets, read all secrets, manage queues, and update IAM policies.

1. List the risks of the current shared role.
2. Propose dedicated execution identities and least-privilege permissions for each function.
3. Which principals need permission to invoke each function? Where should those permissions be configured?
4. Why should the deployment identity be separated from the execution identity?
5. List at least three negative tests to prove permissions are properly constrained.
6. If `email-sender` is exploited, how does the new architecture limit the blast radius?

Hint: `invoice-reader` only needs to read the exact database/table and write PDFs to the `invoice-output` prefix. `email-sender` only needs to consume a specific queue, read one secret, and call the email sending endpoint. Trigger services or callers are allowed to invoke via resource policies/event configurations; each function's execution role does not replace invoke permissions. The deployment pipeline may only update functions and attach approved roles. Negative tests include reading another secret, deleting buckets, updating IAM, reading out-of-scope tables, or invoking the function from an unauthorized principal.

## Conclusion

Assigning per-function identities and least-privilege permissions starts by separating caller, trigger, execution, and deployment identities. Each function should run with a workload identity aligned to its specific responsibility; the trust policy limits who can assume the identity, while the permission policy limits actions, resources, and conditions. Invoke permissions must be managed separately from downstream service access permissions. Using short-lived credentials, secret managers, audit logs, IaC reviews, and negative testing reduces the blast radius when code, dependencies, or a principal is compromised.
