# Investigating Functions Not Triggered or Missing Access Permissions

When a serverless function does not run after an HTTP request or event, or logs show an AccessDenied error, do not rush to change handler code. The failure can occur before the function is even invoked, at the gateway's authentication/authorization layer, in trigger configuration, in event source read permissions, in the function's execution role, or in the target service accessed by the Java code.

An effective investigation traces the entire path of the request/event and identifies the **last boundary that succeeded**. For HTTP, you need to know whether the gateway received the request, whether the authorizer allowed it, whether the integration invoked the function, and whether the handler started running. For queues/events, you need to know whether the event was published, whether it sits in the subscription/queue, whether the event source mapping read it, whether it passed filters, whether it was invoked, and whether it was acknowledged properly.

This lesson builds a diagnostic workflow for Java serverless functions, applicable to HTTP triggers, queue consumers, and event-driven functions on AWS Lambda, API Gateway, EventBridge, SQS, Google Cloud Run/Cloud Functions, and Pub/Sub. The CLI examples only read state or simulate permissions; run them in the exact account/project, region, and environment experiencing the issue.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between a function not being invoked, an invocation being denied, and a handler running but failing.
- Trace a request path from producer/gateway to function and downstream services.
- Inspect HTTP routes, stages, authorizers, integrations, and function invoke permissions.
- Inspect queue subscriptions, event source mappings, filters, batches, retries, and DLQs.
- Distinguish function invoke permissions, event source read permissions, and execution role permissions.
- Analyze IAM policies, resource policies, service accounts, KMS, and cross-account access.
- Recognize network errors commonly mistaken for permission errors.
- Use request IDs, correlation IDs, metrics, logs, and traces to isolate the failure.
- Interpret Java SDK errors, Spring Security, and the credential chain in serverless runtimes.
- Remediate according to least privilege and verify with a real request/event.
- Write runbooks, permission tests, and post-deployment error monitoring.

## 1. Classify Symptoms Before Fixing

The same "function didn't run" symptom can point to very different failures. Classify using evidence before changing policies or redeploying.

| Category | Symptoms | Boundary likely failing |
|---|---|---|
| Producer did not emit event | Request/message/event missing at source | Client, publisher, network, publish permission |
| Trigger did not forward | Event exists in queue/bus, but function has zero invocations | Subscription, rule, mapping, filter, disabled trigger |
| Invocation denied | Gateway/event source reports 401/403 or access denied | Authorizer, invoke permission, resource policy |
| Function invoked but handler failed | Invocation metric rises, logs show exceptions | Java code, deserialization, timeout, dependency |
| Function runs but cannot read data | Handler logs show 403/AccessDenied | Execution role, resource policy, KMS, secret permission |
| Function cannot connect to dependency | Timeout, DNS error, connection refused | VPC, firewall, NAT, endpoint, DNS, routing |
| Function throttled | Throttles rise, queue age rises, 429/5xx requests | Concurrency, quota, reserved capacity, downstream saturation |
| Function processes but message returns | Duplicate invocations, visibility timeout, retries | Ack/delete timing, partial batch failure, idempotency |

A useful rule of thumb:

- **No invocations**: check producer, trigger, route, filter, and function invoke permissions.
- **Invocations present but handler does not complete**: check runtime, code, timeout, concurrency, and dependencies.
- **Handler runs but is denied when calling another service**: check the identity the function uses and permissions on the target resource.
- **Handler cannot connect to a resource**: check the network path before concluding it is IAM.

### General Path

~~~mermaid
flowchart LR
    P["HTTP client / Event producer"] --> S["Gateway / Queue / Event bus"]
    S --> A["Authentication and invoke authorization"]
    A --> T["Trigger routing / Event source mapping"]
    T --> F["Function invocation"]
    F --> R["Java handler and application logic"]
    R --> D["Database / Secret / Storage / API"]
    D --> O["Response / Ack / Result"]
~~~

Each arrow is a boundary that can fail. Investigate from left to right and record evidence at every step.

## 2. Collect Evidence and Preserve the Scene

Before changing configuration, record enough details to reproduce:

- Environment: development, staging, or production.
- Cloud account/project, region, function name, and version/alias/revision.
- Trigger type: HTTP, queue, event bus, object storage, or scheduler.
- Time of failure including timezone.
- Request ID, trace ID, event ID, message ID, or correlation ID.
- HTTP method/path/status or event source/partition/sequence.
- Calling principal name and the function's service account/execution role.
- Full error code, not just the phrase "permission denied".
- Last time the trigger worked and most recent changes to deployments, IAM, secrets, VPC, or resource policies.

Use UTC when comparing timestamps across gateways, brokers, functions, and downstream systems. Clocks across systems can drift; prioritize request IDs, event IDs, and trace context over comparing timestamps alone.

Do not paste tokens, cookies, private keys, database passwords, or payloads containing PII into tickets/logs. When sharing logs, mask identifiers while preserving error codes, resource ARNs/names, regions, and request IDs.

### Determine Whether Invocation Actually Occurred

Look for three types of evidence together:

1. **Trigger/gateway metrics:** requests received, events matched, messages received, delivery attempts.
2. **Function metrics:** invocation count, error count, duration, throttle count, concurrent executions.
3. **Function logs/traces:** platform request ID, handler start, exceptions, and downstream calls.

Missing logs do not prove the function never ran. Logs can be missing because the log group does not exist yet, the execution role lacks permission to write logs, wrong region/account, log retention, or querying the wrong time range. Platform invocation metrics are often more reliable independent evidence than application logs.

## 3. Investigate HTTP Triggers: Did the Request Reach the Right Function?

For HTTP APIs, trace the chain:

1. DNS/TLS and client sending to the right host.
2. Gateway/load balancer receives the request.
3. Route/method/stage is deployed.
4. Authorizer or IAM authentication accepts the caller.
5. Integration points to the right function/alias and right region.
6. Gateway has permission to invoke the function.
7. Function receives the event and runtime starts the handler.
8. Handler performs business authentication/authorization and returns a response.

### Inspect Routes, Stages, and Deployments

Common configuration mistakes:

- Client calls the wrong hostname, stage, or base path.
- Route is configured only for GET while the client sends POST.
- Route was created but the stage was never deployed.
- Gateway integration points to a different function, an old alias, or a different region.
- Path parameter/query mapping alters the event payload.
- Request body does not match the payload format expected by the adapter.
- Gateway times out before the function completes.
- CORS preflight is handled separately by the gateway, so it does not necessarily invoke the business handler.

Compare the active route against the API contract and deployment revision. Do not check only source/IaC configuration; inspect the actual deployed state.

### Distinguish 401 and 403

- **401 Unauthorized** usually means a missing token, bad signature, expired token, wrong issuer/audience, or unauthenticated principal.
- **403 Forbidden** usually means the principal was identified but policy denies the action; some gateways also use 403 for API keys, resource policies, or WAF rules.
- **404** can be used to hide a route/resource or indicate the route does not exist.
- **429** usually indicates rate/concurrency/quota throttling.
- **502/503/504** can be integration errors, invalid function responses, upstream unavailability, or timeouts; read gateway execution logs and function metrics to distinguish them.

Status codes alone do not pinpoint the exact failing layer. Inspect error type, gateway request ID, and invocation metrics over the same time window.

### Authorizers and Claim Mapping

For JWT/OIDC authorizers, check:

- Issuer is correct and trusted.
- Audience/client/resource server is correct.
- Token is not expired and is already valid (`nbf`).
- Signing keys/JWKS are up to date and reachable.
- Scope/role claims match the route.
- Clock skew is within acceptable bounds.
- The `Authorization` header is not stripped or rewritten by a proxy.
- Authorizer cache is not serving stale decisions after permissions changed.

If the gateway injects user/tenant headers for the function, only trust headers generated by the gateway after authentication. The gateway must strip any same-named headers sent by the client. If a function receives requests directly from the Internet, never trust `X-User-Id`, `X-Tenant-Id`, or `X-Role` simply because they appear in headers.

### Is the Gateway Allowed to Invoke the Function?

This is the gateway service/principal's **invoke function** permission, not the end user's database permission.

Check:
- Does the integration URI specify the right function, alias/version, and region?
- Does the function's resource-based policy allow the gateway service principal to invoke it?
- Is the policy scoped to the right API/stage/account/source ARN?
- Does the gateway call an alias while permission was only granted to the unqualified function or a different alias?
- If the integration uses an IAM role, does that role have permission to invoke the target function?
- Does the function policy contain an explicit deny or an unmatched condition?

Never grant invoke permission to every principal or every API just to clear a 403. Grant it to the exact principal and source ARN of the required API/stage.

## 4. Investigate Queue and Event Triggers

Queue/event triggers typically follow two patterns:

- **Pull/polling:** the platform or event source mapping reads messages from a queue/stream and invokes the function.
- **Push:** the event provider calls the endpoint/function when an event occurs.

Permission and delivery checks differ. With polling, a function may not be called because the mapping is disabled, it cannot read the queue, filters drop the event, or the consumer is throttled. With push, the endpoint's resource policy or invoker permission may reject the provider.

### For Queue Polling

Check in order:

1. Did the producer publish successfully?
2. Is the message in the right queue/subscription?
3. Is the message in the DLQ or filtered out?
4. Is the event source mapping/subscription `ENABLED`?
5. Does the mapping point to the right queue, topic, stream, and function alias?
6. Does the poller have permission to read/delete/ack messages?
7. Does the function have concurrency/quota to accept invocations?
8. Is one failing message causing the entire batch to retry?
9. Is the visibility timeout/ack deadline longer than processing time?
10. Is a retry policy, redrive policy, or maximum age expiring messages?

With AWS Lambda + SQS, the function's execution role needs the corresponding queue read permissions such as `sqs:ReceiveMessage`, `sqs:DeleteMessage`, and `sqs:GetQueueAttributes`; if the queue uses a KMS customer-managed key, the principal needs appropriate decrypt permissions and the key policy must allow it. Cross-account queues also require a resource policy on the queue. Queue polling permissions are distinct from the function's permissions to call a database or S3.

### For Event Bus Push

For example, EventBridge invoking Lambda:
- Is the rule `ENABLED`?
- Does the event pattern match the actual event?
- Does the target point to the right function/alias?
- Does target invocation permission allow the EventBridge service principal with the source rule ARN?
- Are retry policy and dead-letter queue configured?
- Was the event archived/filtered or was the rule recently modified?

For Pub/Sub push to Cloud Run/HTTP functions:
- Does the subscription push endpoint point to the right service/revision URL?
- Is the push authentication service account valid?
- Does that service account have permission to invoke the service (for example, Cloud Run Invoker)?
- Does the OIDC audience match the configured service URL/audience?
- Does the subscription show backlog, delivery attempts, or a dead-letter policy?

### Filter and Schema Mismatch

An event can be published successfully yet fail to match the event pattern/filter. Compare a real event against the deployed filter:
- Does the event name/type match case?
- Is the field at the expected JSON nesting level?
- Is the value a string, number, or array?
- Is there a filter on account, region, or source?
- Did a new schema version rename fields or change structure?

Do not temporarily remove all filters in production just to test if doing so could trigger many unwanted events. Use controlled test events or a staging environment.

## 5. Distinguish Three Crucial Permission Types

In serverless systems, the term "function role" is often used loosely for several distinct permissions. Separate them:

| Permission | Principal | Resource | Example |
|---|---|---|---|
| Invoke permission | API Gateway, EventBridge, Pub/Sub push identity, or caller | Function/HTTP service | Allowed to call the function |
| Event source access | Poller/function execution role | Queue, stream, topic, KMS key | Allowed to read/ack messages |
| Runtime execution permission | Function service account/execution role | Database, object storage, secret, API | Allowed to access dependencies |

A function can be invoked successfully yet fail with AccessDenied when reading a secret. A function role may read S3 fine while API Gateway still lacks permission to invoke the function. Fixing a policy at the wrong layer will not resolve the error.

### Java Function Identity

At runtime, the Java SDK should obtain credentials from the provider chain or workload identity supplied by the platform. Do not embed access keys/secret keys in code, images, environment variables, or committed config files.

Inspect the actual principal using the cloud provider's identity API in a controlled diagnostic environment. Compare that principal against the role/service account you expect the function to run as. A wrong alias, revision, deployment account, or service account binding can cause the function to run under an unexpected identity.

## 6. Read IAM Decisions: Identity Policies and Resource Policies

Whether a request is allowed or denied can depend on multiple policy layers:

- Identity-based policy attached to the user/role/service account.
- Resource-based policy attached to the function, queue, bucket, secret, or key.
- Trust policy defining who may assume the role/service account.
- Permission boundary or session policy capping maximum permissions.
- Organization policy/SCP or folder/project policy.
- Explicit deny in any applicable policy.
- Conditions such as source ARN, source account, principal tag, VPC endpoint, or encryption context.
- KMS key policy and grants.
- VPC endpoint policy or service perimeter.

**Always investigate explicit denies first.** An Allow in an identity policy never overrides an explicit deny in a resource policy, SCP, or boundary.

### Workflow for Analyzing an AccessDenied

1. Capture the exact error code/message and service request ID.
2. Identify the actual calling principal.
3. Identify the exact denied action, for example `secretsmanager:GetSecretValue`.
4. Identify the exact resource, including account/project, region, and ARN/name.
5. Check the principal's identity policy.
6. Check the resource policy and trust relationship.
7. Check explicit denies, boundaries, and SCP/session policies.
8. If encrypted with KMS, check both service permissions and the key policy/grants.
9. Check conditions, tags, source identity, and region.
10. Apply the minimal change, then re-run the exact operation that failed.

Do not diagnose from role names alone. A single role interacts with multiple policies, permission boundaries, session policies, and resource policies.

### Example: Secret Read Permission

A function needs to read secret `orders/db-password`. Possible causes of failure:
- The role lacks the secret-read action.
- The secret ARN specifies the wrong account or region.
- The secret has a resource policy with an explicit deny.
- The secret uses a customer-managed KMS key and the role lacks decrypt permission.
- The KMS key policy does not allow the role or Secrets Manager service path to use the key.
- The function is running with a role from another deployment.
- Secret rotation changed the reference/config and the code still reads the old secret.

Adding only the secret-read permission may not be enough if the actual failure is KMS decrypt or a resource policy.

## 7. Platform Diagnostics on AWS

This section illustrates AWS Lambda, API Gateway, SQS, and EventBridge. Resource names/ARNs must come from your real environment; the commands below are read-only examples requiring AWS CLI and read permissions.

### Inspect Function and Alias Configuration

~~~bash
aws lambda get-function-configuration \
  --function-name orders-api \
  --qualifier prod \
  --region ap-southeast-1
~~~

Check:
- `State` and `LastUpdateStatus`.
- Runtime, handler, timeout, and memory.
- Role ARN.
- Environment/config version.
- VPC config.
- Function ARN/qualifier and revision.
- `LastUpdateStatusReason` if deployment has not finished.

If not using an alias, omit `--qualifier`. Verify you are inspecting the right account and region using `aws sts get-caller-identity` and CLI configuration.

### Inspect Resource-Based Invoke Policy

~~~bash
aws lambda get-policy \
  --function-name orders-api \
  --qualifier prod \
  --region ap-southeast-1
~~~

Verify the statement has:
- The right principal, such as `apigateway.amazonaws.com` or `events.amazonaws.com`.
- Action `lambda:InvokeFunction`.
- The right resource/qualifier.
- Conditions `AWS:SourceArn` and `AWS:SourceAccount` matching the actual source.

If a function alias is invoked, the policy must apply to the exact resource qualifier called by the integration.

### Inspect Event Source Mappings

~~~bash
aws lambda list-event-source-mappings \
  --function-name orders-worker \
  --region ap-southeast-1
~~~

Once you have the UUID:

~~~bash
aws lambda get-event-source-mapping \
  --uuid 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

Check:
- `State` / `StateTransitionReason`.
- `EventSourceArn`.
- `FunctionArn`.
- `BatchSize` and `MaximumBatchingWindowInSeconds`.
- `FilterCriteria`.
- `FunctionResponseTypes`, especially `ReportBatchItemFailures`.
- `MaximumRetryAttempts`, `MaximumRecordAgeInSeconds`, and `DestinationConfig`.
- `LastProcessingResult` if present.

With SQS, inspect queue attributes, redrive policy, visibility timeout, and encryption. If a function takes longer than the visibility timeout, messages can be redelivered while the prior invocation is still running.

### Inspect Concurrency and Throttling

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-worker \
  --region ap-southeast-1
~~~

Check reserved concurrency, account concurrency, and concurrent execution metrics. Reserved concurrency set to 0 blocks all invocations. A function hitting its concurrency limit can be throttled even when triggers and permissions are correct.

### Simulate IAM Policies

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/orders-worker-role \
  --action-names secretsmanager:GetSecretValue \
  --resource-arns arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:orders/db-password
~~~

Simulation helps inspect identity policy evaluation, but does not necessarily evaluate full resource policies, KMS key policies, SCPs, session policies, VPC endpoint policies, or every runtime condition. Treat the result as one piece of evidence, not the final conclusion.

### CloudWatch Logs and Metrics

Verify the exact log group/function/region and time range. With Lambda, the invocation metric can increment even if Java handler logs have not emitted a single line; failures can happen during init, class loading, or runtime startup. Conversely, logs may not appear if the role lacks CloudWatch Logs permissions or points to the wrong log group.

When inspecting log groups/streams, use the AWS Console or log-reading commands matching your current permissions. Do not enable broad payload logging in production if payloads contain sensitive data.

## 8. Diagnostics on Google Cloud Run and Cloud Functions

On Google Cloud, distinguish the identity invoking the service from the service account the function uses during execution.

### Inspect Service and Runtime Configuration

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=my-project
~~~

Check:
- URL and ingress settings.
- The revision's service account.
- Traffic split and which revision receives traffic.
- Container image/version.
- Environment/secret references.
- CPU/memory/concurrency/timeout.
- VPC connector or network egress settings.

With Cloud Functions gen2, functions run on top of Cloud Run; inspect both the function configuration and the generated Cloud Run service/revision. Do not confuse the function source name with the Cloud Run service/revision handling requests.

### Inspect Invoker IAM Policy

~~~bash
gcloud run services get-iam-policy orders-api \
  --region=asia-southeast1 \
  --project=my-project
~~~

The caller needs an appropriate invoker role (for example, `roles/run.invoker`) when the service requires IAM authentication. If Pub/Sub push calls Cloud Run, the service account used for push authentication must have permission to invoke the service, and the OIDC audience must match.

Do not grant `allUsers` invoker just to clear a 403 if the service requires private access. If public HTTP is intended, it must be an architectural decision with application-layer protection.

### Inspect the Runtime Service Account

The Cloud Run/function service account is the principal used when code calls Google Cloud APIs. It needs its own permissions on Secret Manager, Cloud Storage, Pub/Sub, databases, or other services. A caller's `roles/run.invoker` permission does not automatically grant the runtime service account access to read data.

Check:
- Which service account the revision actually uses.
- Whether the service account is bound in the right project.
- Whether IAM bindings on target resources list the right principal.
- Whether organization policies restrict service accounts or tokens.
- Whether the secret version is enabled and the service account has access.
- Whether the resource resides in a different project or region.

### Inspect Pub/Sub Delivery

Inspect the subscription, push endpoint, authentication configuration, backlog, ack deadline, retry policy, and dead-letter topic. If the push endpoint returns 401/403, check the push auth service account and audience. If the function is invoked but fails during processing and returns non-2xx, Pub/Sub retries according to the subscription policy; this differs from Pub/Sub being unable to invoke the service.

## 9. Java Runtime: Distinguish Authentication from Authorization Errors

Java code can call cloud SDKs, databases, secret managers, or external APIs. Read the full exception and identify the service, action, and resource.

| Exception/response | Investigation direction |
|---|---|
| `AccessDeniedException`, `AccessDenied` | IAM/resource policy/KMS/explicit deny |
| `UnrecognizedClientException`, invalid security token | Credential chain, expired/invalid credentials, wrong account |
| `SdkClientException` from connect timeout | DNS/network/TLS/endpoint |
| HTTP 401 from downstream | Missing token/API key, wrong issuer/audience/expiry |
| HTTP 403 from downstream | Principal identified, but policy denies access |
| `UnknownHostException` | DNS resolver, private zone, VPC DNS |
| `ConnectException: Connection refused` | Host reachable, but port/service is not accepting |
| `SocketTimeoutException` | Network path, downstream overload, or timeout too short |
| `SSLHandshakeException` | Truststore, certificate chain, TLS/SNI/clock |

Do not catch every exception and log a single line `"failed"`. Preserve error codes, service request IDs, masked resource identifiers, and correlation IDs.

### Use the Default Credential Provider

AWS SDK for Java or Google Cloud Java clients should obtain identity from the execution role, service account, or workload identity. Never configure static access keys in source code.

AWS SDK v2 example:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.services.sts.StsClient;

try (StsClient sts = StsClient.builder()
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build()) {
    var identity = sts.getCallerIdentity();
    // Only log permitted account/ARN details; never log credentials.
}
~~~

This example helps verify the principal resolved by the SDK at runtime. Restrict identity output in production logs per policy; never log session tokens or credentials.

With Google Cloud clients, use Application Default Credentials from the platform-provided service account/workload identity. Avoid bundling service account key JSON files into container images or repositories.

### Log at Boundaries, Never Log Secrets

In handlers, log:
- Function name/revision.
- Platform request ID.
- Correlation/trace ID.
- Operation being executed.
- Downstream service and error category.
- Duration and retry attempt if any.

Never log `Authorization` headers, raw JWTs, API keys, secret values, private keys, database URLs with passwords, or full request bodies. If an exception message contains resource names or user data, mask it before logging.

## 10. Access Denied or Network Failure?

Many errors are casually called "permission errors" even when the cause is networking.

| Symptom | Likely cause | How to distinguish |
|---|---|---|
| HTTP 403 from service | Policy/authorization | Response received from endpoint; inspect principal and policy |
| HTTP 401 | Authentication | Inspect token/credentials, issuer/audience/expiry |
| DNS lookup failure | DNS/network | Host cannot be resolved |
| Connection timeout | Route/firewall/NAT/endpoint or overload | No HTTP response; inspect VPC path |
| Connection refused | Port/service listener | Host reachable, but TCP connection rejected |
| TLS handshake failure | Certificate/TLS/SNI | TCP connection may have already succeeded |
| KMS `AccessDenied` | Key policy/permission | Service reachable, but decrypt denied |
| Database login failed | DB credentials/DB grants | Network reached DB, but DB authn/authz failed |

For functions inside a private subnet/VPC, check:
- Route tables and NAT gateways if Internet egress is needed.
- Outbound and inbound security groups/firewalls.
- Network ACLs.
- Private service endpoints/PrivateLink/Private Service Connect.
- DNS resolvers and private hosted zones.
- VPC connectors/egress modes.
- Database endpoints, ports, and TLS certificates.

If a function calls cloud APIs through a private endpoint, the endpoint policy can also deny the request even when the IAM role allows it. Check both the endpoint policy and the resource policy.

## 11. Logs, Metrics, and Traces: Reconstruct an Invocation

A good trace correlates:
- Gateway request ID.
- Function platform request ID.
- Application trace/span ID.
- Event/message ID.
- Downstream request ID.

For HTTP, propagate W3C Trace Context or correlation IDs across the gateway if the platform supports it. For queues/events, include the event ID and trace context in message attributes/envelopes; never use a user token as a correlation ID.

### Metrics to Inspect Together

| Metric | Interpretation |
|---|---|
| Gateway requests | Did the request reach the gateway? |
| Authorizer 4xx | Did authn/authz block before invoke? |
| Integration errors/latency | Did the gateway invoke the function successfully? |
| Function invocations | Was the function invoked? |
| Function errors | Did the handler/runtime error? |
| Throttles/concurrency | Was the function capacity-limited? |
| Queue visible messages | Are messages still waiting? |
| Oldest message age | Is the backlog aging? |
| DLQ depth | Are messages exceeding the retry policy? |
| Downstream 4xx/5xx/timeout | Are errors in resources called by the function? |

Read metrics over the same time window and in the same region/account. Compare baselines before and after deployments to spot regressions.

### Log Startup and Handler Start

In Java, you can log one marker during application initialization and one marker right at the start of the handler. These two markers help distinguish:
- Function invoked, but JVM/class initialization failed.
- Spring context startup failed.
- Handler started and failed inside an application service.
- Request blocked at the gateway so the function was never called.

Never log full event JSONs. Log only necessary and permitted fields.

## 12. Step-by-Step Diagnostic Workflow

Use this workflow when on-call receives a "function not running" alert:

~~~mermaid
flowchart TD
    A["Record request/event ID and timestamp"] --> B{"Evidence producer/gateway received request?"}
    B -->|No| C["Check client, DNS, publish, and network"]
    B -->|Yes| D{"Evidence of invoke/trigger delivery?"}
    D -->|No| E["Check route, filter, mapping, disabled trigger, and invoke permission"]
    D -->|Yes| F{"Function invocation metric increased?"}
    F -->|No| G["Check integration errors, quota, and provider delivery"]
    F -->|Yes| H{"Handler started?"}
    H -->|No| I["Check init, runtime, handler config, and log permissions"]
    H -->|Yes| J{"AccessDenied error?"}
    J -->|Yes| K["Identify principal, action, resource, and policy chain"]
    J -->|No| L["Check code, payload, timeout, and dependencies"]
    K --> M["Apply least-privilege fix"]
    L --> N["Fix root cause and test"]
    M --> O["Replay/canary and verify metrics"]
    N --> O
~~~

### Step 1: Reproduce with One Controlled Request/Event

Use a dedicated request ID or event ID. Record the UTC timestamp and minimal payload. Avoid sending bursts of events into production just to test permissions.

### Step 2: Find the Last Successful Boundary

For example:
- Gateway receives the request, but authorizer returns 403: never reached the function.
- Event is in the queue, but mapping is Disabled: not invoked yet.
- Function invocations rise and logs show handler start: trigger worked.
- Handler logs show `GetSecretValue` `AccessDenied`: failure is in runtime identity/resource policy.

### Step 3: Identify Principal and Action

Do not write "role lacks permission". State explicitly:
- Principal: which role/service account?
- Action: which API operation?
- Resource: which ARN/name?
- Context: account/project, region, source identity, encryption key?
- Policy decision: explicit deny, no matching allow, condition mismatch, or trust failure?

### Step 4: Minimal Change

Grant only the required action on the required resource. If an API Gateway needs to invoke a function, grant invoke permission to that exact source ARN. If a function needs to read a secret, grant minimal read/decrypt permissions on that exact secret and key. Never attach `AdministratorAccess`/`Owner`/`Editor` across the whole project to resolve an incident.

### Step 5: Verify After Fixing

- Resend the same controlled request/event type.
- Confirm invocation metrics and handler start.
- Confirm the downstream operation succeeds.
- Confirm queue ack/visibility/DLQ behavior is correct.
- Verify no unintended broad permissions were granted.
- Monitor errors, throttles, and backlogs over a sufficient observation window.

## 13. Symptom and Remediation Matrix

| Symptom | Check first | Remediation direction |
|---|---|---|
| HTTP 401 | Token, issuer, audience, expiry, JWKS | Fix identity/client/token configuration |
| HTTP 403 before invocation | Authorizer, gateway policy, invoke permission, WAF | Grant exact caller/source permissions |
| Gateway 502/504, invocations flat | Integration URI, invoke permission, timeout, region | Fix integration or permissions |
| Queue has backlog, invocations equal 0 | Mapping state, event source permissions, filter, concurrency | Enable/fix mapping and poller access |
| Event bus receives event, doesn't call function | Rule pattern, target, target permission | Fix pattern/target resource policy |
| Invocations rise, no Java logs | Init error, runtime/handler config, log permissions | Inspect platform init logs and role logging |
| Java logs show `AccessDenied` reading secret | Runtime identity, secret policy, KMS key | Grant minimal read/decrypt permissions |
| Java logs show 403 from downstream API | Token/service identity and resource policy | Fix authn/authz on downstream service |
| Timeout connecting to DB | VPC, routes, firewalls, DNS, pools | Fix network/capacity; do not broaden IAM |
| Messages redelivered repeatedly | Handler errors, ack/delete, visibility, batch response | Fix retries/ack and idempotency |
| Function throttled | Reserved/account concurrency, downstream capacity | Adjust concurrency and backpressure |
| Only one tenant/user fails | Membership/policy/claims/cache | Check tenant mapping and authorization data |

## 14. Real-World Scenarios

### Scenario A: API Gateway Returns 403 and Lambda Has Zero Invocations

Symptoms:
- Client receives 403.
- Gateway access log records the request.
- Lambda invocation metric does not increment.
- No application logs exist for the request.

Investigation:
1. Determine whether 403 came from the JWT authorizer, IAM auth, API resource policy, or WAF.
2. Check issuer/audience/scope and principal.
3. If the authorizer allows it yet gateway does not invoke Lambda, check Lambda resource policy/integration role.
4. Verify `SourceArn` matches the API ID, stage, and method/path being called.
5. Send a valid request and compare gateway request ID with Lambda request ID.

Conclude only after pinpointing the exact layer returning 403. Adding roles to the Java execution role will not help the gateway pass invoke permissions.

### Scenario B: SQS Has Messages, but Java Worker Does Not Run

Symptoms:
- Queue visible message count increases.
- Lambda invocations do not rise.
- Messages have not moved to the DLQ.

Investigation:
1. Check whether the event source mapping is `ENABLED`.
2. Verify `EventSourceArn` and `FunctionArn`.
3. Verify the execution role has `ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes`.
4. If the queue uses a CMK, verify decrypt permission and key policy.
5. Check whether reserved concurrency is 0 or the function is throttled.
6. Check whether filter criteria are dropping the messages.
7. Check whether queue/region/account match the target environment.

Once the mapping is re-enabled, old messages may begin processing. Before doing so, assess the backlog, downstream capacity, and duplicate replay risk.

### Scenario C: Function Runs, but Cannot Read Secret

Symptoms:
- Invocation metric rises.
- Handler logs show `AccessDenied` when calling the secret service.
- Database connection has not opened yet.

Investigation:
1. Confirm the runtime principal via identity API or platform revision config.
2. Identify the action and secret ARN/version.
3. Inspect the role's identity policy and the secret's resource policy.
4. If using a KMS CMK, check decrypt permission and key policy/grants.
5. Check region and secret reference.
6. Grant least-privilege permission and retry.

Do not grant secret permissions to the HTTP caller user; the principal needing permission is the function's workload identity.

### Scenario D: Cloud Run Returns 403 on Pub/Sub Push

Symptoms:
- Subscription backlog rises.
- Pub/Sub delivery attempts rise.
- Cloud Run request log returns 403.
- Application logs may be absent if requests are blocked before the container.

Investigation:
1. Check whether the push endpoint matches the service/revision URL.
2. Identify the service account used to sign the OIDC token.
3. Verify the service account has permission to invoke the service.
4. Verify the audience in the token matches the audience accepted by Cloud Run.
5. Inspect ingress and service IAM policy.
6. Send a test event from the subscription or a controlled test publisher.

Permissions of the service account used for Pub/Sub push differ from the service account the container uses to call databases/Secret Manager.

### Scenario E: Function Times Out Accessing Database

Symptoms:
- Function invocations rise.
- Java logs show connection timeout or DNS failure.
- No HTTP 403 from the database.
- May occur after enabling a VPC connector or changing subnets.

Investigation:
1. Check hostname/port and DNS resolution.
2. Check routes, subnets, security groups/firewalls, and network ACLs.
3. Check NAT or private endpoints.
4. Check database connection limits and pools.
5. Check TLS/certificates.
6. Only examine IAM database authentication if connectivity works and the error indicates authn/authz.

Do not treat network timeouts by granting unrelated IAM permissions.

## 15. Safe Remediation and IAM Change Management

Once the root cause is identified, remediate in order:

1. Select the exact principal performing the action.
2. Select the exact action/API operation.
3. Select the exact resource ARN/name.
4. Add required conditions such as source account, source ARN, encryption context, or principal tags.
5. Verify trust policies if the principal must assume a role.
6. Check resource policies, KMS, and endpoint policies.
7. Deploy via IaC/change review if policies are managed as code.
8. Verify effective permissions and run real tests.

Do not:
- Attach broad admin permissions temporarily and forget to revoke them.
- Use wildcard resources when only one secret/bucket/queue is needed.
- Allow public invoke just to avoid configuring identity.
- Put credentials in code or logs.
- Edit production policies directly without change tracking/rollback.
- Change multiple policies at once before knowing which policy caused the failure.

If temporary permissions must be used to restore service, assign an owner, expiration time, audit trail, and explicit revocation task. Prefer updating policies through your IaC source of truth to prevent drift.

## 16. Testing Triggers and Permissions Before Production

Testing a function directly does not prove real triggers work. Test each boundary:

| Test | What to prove |
|---|---|
| Direct invoke test | Runtime and handler start cleanly |
| HTTP integration test | Route, authorizer, integration, and response mapping |
| Negative auth test | Invalid/expired/wrong-audience tokens are blocked |
| Invoke permission test | Gateway/event provider is permitted to invoke the right function |
| Queue delivery test | Messages from the queue are received, processed, and acked |
| Filter test | Matching events are received; non-matching events are intentionally ignored |
| Runtime IAM test | Function reads the intended secret/object/database |
| KMS test | Encrypted resources decrypt under the runtime principal |
| Network test | DNS/TCP/TLS to dependencies succeeds |
| Retry/DLQ test | Failures retry per policy and eventually appear in the DLQ |
| Concurrency test | Function does not exceed database/downstream capacity |

### Negative Tests Are Critical

Also test what must be denied:
- Wrong principal cannot invoke a private function.
- API Gateway from another API cannot invoke the function.
- Function role cannot read out-of-scope secrets.
- Queue consumer cannot read another queue.
- Users without tenant membership cannot call business operations.
- Tokens with the wrong audience are rejected.

A policy test suite with only positive cases can miss overly broad permissions.

## 17. Sample On-Call Runbook

When receiving a "function not triggered / AccessDenied" alert, fill in this runbook:

~~~text
Incident:
Environment:
Cloud account/project:
Region:
Function / alias / revision:
Trigger type:
Source resource:
First failure time (UTC):
Request ID / event ID:
Observed status / error code:

1. Producer/gateway accepted?       YES / NO / UNKNOWN
2. Trigger matched/delivery started? YES / NO / UNKNOWN
3. Invoke permission passed?        YES / NO / UNKNOWN
4. Function invocation observed?    YES / NO / UNKNOWN
5. Handler start observed?          YES / NO / UNKNOWN
6. Downstream call started?         YES / NO / UNKNOWN
7. Exact principal:
8. Exact action:
9. Exact resource:
10. Explicit deny / missing allow / condition mismatch:
11. Network path result:
12. Change made and reviewer:
13. Retest request/event ID:
14. Invocation/result verified:
15. Backlog/DLQ/throttle after fix:
16. Follow-up owner:
~~~

Do not mark an incident resolved solely because an HTTP request returned 200 or function invocation metrics rose. Verify the right business effect occurred, messages were acked or operations completed, no duplicate side effects happened, and backlogs are not continuing to grow.

## 18. Observability and Proactive Alerting

Useful alerts:

- HTTP 401/403 rate rising by route/authorizer.
- Gateway integration errors or latency exceeding thresholds.
- Function invocations dropping abnormally while request/event volume rises.
- Function errors, init errors, or throttles rising.
- Queue oldest message age and visible backlog growing.
- DLQ depth greater than 0 or growing rapidly.
- Event source mapping not in enabled state.
- `AccessDenied` from secrets, storage, KMS, or databases rising.
- Database connection acquisition/timeouts rising.
- Retry counts and duplicate processing rising.

Metric labels should stay bounded to function, route template, trigger type, outcome, and error category. Do not include user IDs, tokens, message payloads, or high-cardinality raw resource IDs in labels.

Alerts need:
- Threshold and evaluation window.
- Owner/on-call routing.
- Related dashboard/runbook links.
- Escalation conditions.
- Rollback or trigger-disable guidance if replay could cause harm.

## 19. Investigation Checklist for Untriggered Functions or AccessDenied

- [ ] Recorded environment, account/project, region, function alias/revision, and UTC timestamp.
- [ ] Obtained request ID/event ID/correlation ID for tracing.
- [ ] Confirmed producer published or gateway received the request.
- [ ] Confirmed route/stage/deployment and integration are correct.
- [ ] Confirmed authorizer, issuer, audience, scope, and token expiry.
- [ ] Confirmed trigger/rule/subscription/mapping is enabled.
- [ ] Checked filter/event pattern against actual schema.
- [ ] Confirmed gateway/provider invoke permission.
- [ ] For polling triggers, verified queue/stream read/ack and KMS permissions.
- [ ] Checked function invocation, error, throttle, and concurrency metrics.
- [ ] Identified the actual runtime principal.
- [ ] Identified the exact denied action and resource.
- [ ] Checked identity policy, resource policy, trust, boundary, and explicit deny.
- [ ] Checked KMS key policy, endpoint policy, and cross-account conditions.
- [ ] Distinguished 401/403 from DNS/TCP/TLS/timeouts.
- [ ] Checked log permissions and runtime initialization.
- [ ] Applied a least-privilege change through policy management processes.
- [ ] Retested with a controlled request/event.
- [ ] Verified business effect, acknowledgement, retries, and DLQ.
- [ ] Monitored error rate, throttles, and backlog after recovery.
- [ ] Documented root cause, change, and preventive measures.

## Self-Check

1. What is the difference between a function not being invoked and a handler running but failing?
2. Why is the absence of application logs insufficient to prove a function was not called?
3. Which layers can return HTTP 403 before a request reaches the handler?
4. How do function invoke permissions differ from execution role permissions?
5. For SQS polling, which read/ack permissions must be checked?
6. Why do EventBridge or API Gateway require resource-based invoke permissions?
7. If a function has permission to read a secret but the KMS key policy denies it, what happens?
8. How do explicit denies, permission boundaries, and SCPs affect effective permissions?
9. How do you distinguish `AccessDenied` from DNS or connection timeouts?
10. Why does the Cloud Run invoker for Pub/Sub push differ from the runtime service account?
11. Which metrics help determine that an event reached the trigger without invoking the function?
12. Why is a direct invoke test insufficient to prove HTTP or queue triggers work?
13. When should you check reserved concurrency or event source mapping state?
14. Why should incidents never be resolved using `AdministratorAccess` or public invoke?
15. After fixing permissions, what must be verified before closing the incident?

Effective serverless troubleshooting begins by determining how far a request/event traveled, which principal is performing which action on which resource, and what last piece of evidence proves a step succeeded. Separate invoke permissions, event source read permissions, and runtime execution permissions; distinguish IAM denials from network failures; fix policies using least privilege and verify via the real trigger. For Java functions, request IDs, structured logs, platform metrics, workload identity, and integration tests turn an ambiguous "not running" bug into a verifiable root cause and prevent recurrence.
