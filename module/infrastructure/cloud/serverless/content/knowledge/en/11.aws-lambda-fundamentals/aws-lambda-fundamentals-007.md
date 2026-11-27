# Managing Lambda Versions, Aliases, and Invoke Permissions

When deploying Java applications on AWS Lambda, updating a JAR or function configuration can immediately affect subsequent requests if callers invoke the function without a qualifier. That makes controlled releases, testing new versions, rolling back to a stable release, or restricting who can invoke a function difficult.

AWS Lambda provides **published versions** to freeze a snapshot of a function, **aliases** to create stable names pointing to versions, and two layers of IAM policies to control invoke permissions. These three mechanisms answer three distinct questions: which code and configuration run, which release callers invoke, and which principals are allowed to invoke.

This lesson covers managing the lifecycle of versions and aliases, routing traffic, distinguishing invoke permissions from execution permissions, and configuring least-privilege permissions for Java Lambda functions invoked via API Gateway or other AWS services.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish `$LATEST`, published versions, and aliases.
- Explain which components are frozen when publishing a version and which dependencies can still change.
- Use aliases to route new executions to a specific version.
- Understand weighted alias routing and how to use it for canary deployments.
- Distinguish identity-based policies, resource-based policies, and execution roles.
- Grant invoke permissions to IAM principals or AWS services following least privilege.
- Publish versions, update aliases, and grant permissions via the AWS CLI or Java SDK v2.
- Design rollouts, rollbacks, and invoke permission verification.

## 1. $LATEST, Published Versions, and Aliases

A Lambda function has three concepts to distinguish.

| Component | Meaning | Mutable? | ARN format |
|---|---|---|---|
| `$LATEST` | Working copy of the function being edited and updated | Yes | `...:function:order-handler` or qualifier `:$LATEST` |
| Published version | Snapshot of code and configuration at publish time | No | `...:function:order-handler:17` |
| Alias | Name pointing to a published version, supporting routing config | Yes | `...:function:order-handler:prod` |

**$LATEST** is the function's mutable working copy. When you upload code or update configuration without publishing, this copy changes. Callers invoking the unqualified function ARN typically execute `$LATEST`. While convenient during development, it is hard to control if production also calls the unqualified ARN.

**Published version** is a numbered snapshot. For example, version 17 represents the code and configuration at the time of publishing. Once created, that version cannot be edited; to make changes, update the function and publish a new version.

**Alias** is a mutable name such as `dev`, `staging`, `prod`, or `candidate`. An alias points to a primary version and can optionally distribute a percentage of traffic to a second version. Callers use the alias ARN so they do not need to know specific version numbers.

~~~mermaid
flowchart TD
    A["Lambda function: order-handler"] --> B["$LATEST (mutable)"]
    A --> C["Version 16 (immutable)"]
    A --> D["Version 17 (immutable)"]
    A --> E["Version 18 (immutable)"]
    F["Alias dev"] --> C
    G["Alias prod"] --> D
    H["Alias canary"] --> D
    H -. "5% traffic" .-> E
~~~

The diagram illustrates alias `prod` pointing to version 17, while alias `canary` splits a portion of traffic to version 18. An alias is an updatable pointer; a published version is an immutable release.

An alias can only point to a published version; it cannot point directly to `$LATEST`. If a development environment needs the latest unpublished code, callers can invoke the unqualified function in a separate dev environment.

### ARNs and Qualifiers

A base function ARN looks like:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler
~~~

Qualified ARNs:

~~~text
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:17
arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:prod
~~~

The qualifier is either a version number or an alias name. When calling an unqualified ARN, callers typically hit `$LATEST`. When calling an ARN with a version, callers hit that exact immutable version. When calling an ARN with an alias, Lambda resolves the alias according to its current configuration.

Use alias ARNs for integrations requiring a stable endpoint such as production. This lets you deploy a new version by updating the alias without changing configuration across all callers.

## 2. Publishing a Version

Once code and configuration are ready, publish a version to create a referenceable release point.

You can publish using the AWS CLI:

~~~bash
aws lambda publish-version \
  --function-name order-handler \
  --description "Release 2026-11-17"
~~~

The command returns the version number and ARN. For example, if the new version is 17, the ARN has qualifier `:17`.

You can use the Java AWS SDK v2:

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.PublishVersionRequest;
import software.amazon.awssdk.services.lambda.model.PublishVersionResponse;

public final class LambdaVersionPublisher {
    private final LambdaClient lambda;

    public LambdaVersionPublisher(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public String publish(
            String functionName,
            String expectedCodeSha256,
            String revisionId) {

        PublishVersionRequest request = PublishVersionRequest.builder()
                .functionName(functionName)
                .description("Release approved for production")
                .codeSha256(expectedCodeSha256)
                .revisionId(revisionId)
                .build();

        PublishVersionResponse response = lambda.publishVersion(request);
        return response.functionArn();
    }
}
~~~

This example passes `CodeSha256` and `RevisionId` to avoid accidentally publishing if code or configuration changed after verification. In a pipeline, obtain these values from reading the function configuration or from the corresponding build/deploy step. You may omit these conditions if your workflow does not require optimistic concurrency, but keep an explicit step verifying the artifact and configuration prior to publishing.

### What Does a Version Freeze?

A published version saves the code and most function configuration at publish time, such as runtime, handler, role ARN, memory, timeout, environment variables, layers, VPC configuration, and related service-level function settings.

However, a published version does not freeze the entire system:

- The role ARN is saved in the version, but policies attached to that IAM role can still be edited.
- A secret ARN or secret name in an environment variable may be frozen, but the secret value in Secrets Manager can change.
- Database schemas, data, queues, external APIs, and services the function calls are not inside the snapshot.
- Resource-based policies and integration configurations have their own scope; verify them upon release.
- AWS-managed runtimes can receive platform patches under the service's runtime management policy.

Thus, immutable versions make function code/config reproducible, but they do not automatically make the entire dependency environment immutable.

### Publish Only When Releasable Changes Exist

A new function version can be published when code or configuration has changed since the last publish. Pipelines should inspect what changed and record the version number, function ARN, code hash, commit/build ID, and release timestamp in a deployment record.

Do not use a version number as sole proof that an artifact was tested. Tie each version to a traceable build artifact and test results.

## 3. Creating and Updating Aliases

Aliases decouple environment names from version numbers. For example, alias `prod` can point to version 17 today and version 18 on the next release.

Create an alias via the AWS CLI:

~~~bash
aws lambda create-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --description "Production traffic"
~~~

Update an alias:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 18
~~~

In Java SDK v2:

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.UpdateAliasRequest;
import software.amazon.awssdk.services.lambda.model.UpdateAliasResponse;

public final class LambdaAliasManager {
    private final LambdaClient lambda;

    public LambdaAliasManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public String pointProductionTo(
            String functionName,
            String aliasName,
            String version) {

        UpdateAliasResponse response = lambda.updateAlias(
                UpdateAliasRequest.builder()
                        .functionName(functionName)
                        .name(aliasName)
                        .functionVersion(version)
                        .build());

        return response.aliasArn();
    }
}
~~~

Aliases are mutable configuration. Restrict alias update permissions to deployment roles and release operators. A function's runtime execution role normally does not need `lambda:UpdateAlias`.

### Aliases Do Not Modify Code

When updating an alias from version 17 to 18, Lambda does not alter version 17 or version 18. The alias simply changes where callers using that alias are routed. Callers invoking version ARN 17 directly still run version 17; callers invoking `$LATEST` still run the mutable copy.

Therefore, standardize across the team so production callers use alias ARNs. If one caller uses the alias and another calls `$LATEST`, the two callers can unintentionally run different code versions.

## 4. Weighted Alias Routing and Canary Deployments

An alias can point to a primary version while routing a percentage of invocations to a secondary version. This provides a simple canary deployment mechanism: send a small slice of traffic to the new release, monitor errors and latency, and then increase the percentage or fall back to the previous version.

Example setting alias `prod` to version 17 while routing 5% of invocations to version 18:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --routing-config '{"AdditionalVersionWeights":{"18":0.05}}'
~~~

The weight `0.05` assigns 5% to version 18; the remaining traffic goes to the primary version 17. Weighted routing supports one primary version and one additional version in an alias configuration. You cannot declare arbitrary numbers of additional versions within the same weighted alias configuration.

In Java SDK v2:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.AliasRoutingConfiguration;
import software.amazon.awssdk.services.lambda.model.UpdateAliasRequest;

public final class CanaryAliasManager {
    private final LambdaClient lambda;

    public CanaryAliasManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public void sendFivePercentToCanary(
            String functionName,
            String aliasName,
            String stableVersion,
            String canaryVersion) {

        AliasRoutingConfiguration routing =
                AliasRoutingConfiguration.builder()
                        .additionalVersionWeights(
                                Map.of(canaryVersion, 0.05))
                        .build();

        lambda.updateAlias(UpdateAliasRequest.builder()
                .functionName(functionName)
                .name(aliasName)
                .functionVersion(stableVersion)
                .routingConfig(routing)
                .build());
    }
}
~~~

### Canary Workflow

1. Publish a new version after building and testing.
2. Keep alias `prod` pointing to the stable version.
3. Configure a small percentage of traffic to the new version.
4. Monitor error rate, duration, throttling, timeouts, and business errors.
5. Increase the weight incrementally if metrics stay within thresholds.
6. Shift 100% of traffic to the new version once confident.
7. If issues arise, clear weighted routing and point the alias back to the stable version.

Canary routing only distributes invocations across versions; it does not verify business correctness automatically. Use CloudWatch metrics, logs, tracing, and business metrics to compare the two versions.

Do not assume every trigger type shares identical semantics or supports every rollout strategy. Especially for event source mappings, batches, retries, and asynchronous sources, verify how the integration behaves with weighted alias routing before using it in production. For workflows or events requiring version affinity across multiple steps, pass the chosen version/route explicitly rather than letting each step resolve the alias at different times.

### Alias Rollback

Rolling back new traffic generally means updating the alias back to the stable version:

~~~bash
aws lambda update-alias \
  --function-name order-handler \
  --name prod \
  --function-version 17 \
  --routing-config '{}'
~~~

This command returns alias `prod` to version 17 and clears additional routing. It does not undo side effects already executed by version 18, nor does it alter already completed invocations. If the new version wrote data or called external systems, a separate compensation or business reconciliation process is required.

## 5. Function Invoke Permissions: Two Directions to Distinguish

When a Lambda function is invoked, two permission questions arise:

1. **Does the caller have permission to invoke the function?**
2. **Once running, does the function have permission to access databases, queues, object storage, or other services?**

These are two separate permission paths.

~~~mermaid
flowchart LR
    A["Caller: user / role / AWS service"] -->|"lambda:InvokeFunction"| B["Lambda function"]
    B -->|"Assume execution role"| C["IAM execution role"]
    C -->|"s3:GetObject / sqs:SendMessage / ... "| D["AWS resources"]
~~~

- Callers need permission to invoke the function via an appropriate identity-based policy or resource-based policy.
- Lambda assumes the execution role to run code. The trust policy allows the `lambda.amazonaws.com` service principal to assume the role; permission policies on the role allow code to access other services.
- The execution role does not automatically allow API Gateway, EventBridge, or external users to invoke the function.
- A resource-based policy allowing external principals to invoke the function does not automatically grant code inside the function permission to read S3 or write DynamoDB.

### Identity-Based Policy

An identity-based policy attaches to the caller's IAM user, group, or role. The policy states which actions and resources the principal is allowed to invoke.

Example for a role allowed to invoke only alias `prod`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:order-handler:prod"
    }
  ]
}
~~~

Attach this policy to the IAM role used by the calling application or user. Do not grant `lambda:*` if the caller only needs to invoke one specific function.

### Resource-Based Policy

A resource-based policy attaches directly to the Lambda function, version, or alias. It allows a specific principal—often an AWS service or another account/role—to invoke the function.

For example, API Gateway needs permission to invoke Lambda. You can grant permission to the `apigateway.amazonaws.com` service principal and restrict it by the source ARN of the API/stage/method/resource. Constraining the source prevents another API Gateway resource under that service principal from inadvertently invoking the function.

## 6. Granting Permissions to AWS Services with AddPermission

Use the AWS CLI to allow API Gateway to invoke alias `prod`:

~~~bash
aws lambda add-permission \
  --function-name order-handler \
  --qualifier prod \
  --statement-id allow-orders-api-prod \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:ap-southeast-1:123456789012:api-id/prod/POST/orders"
~~~

Key parameters:

| Parameter | Meaning |
|---|---|
| `--function-name` | Target function being granted permission |
| `--qualifier prod` | Attaches the permission to alias `prod` |
| `--statement-id` | Unique statement ID within the resource policy |
| `--action` | Allowed action, here `lambda:InvokeFunction` |
| `--principal` | Service or principal permitted to invoke |
| `--source-arn` | Restricts invoke source, e.g. a specific API Gateway route |

If API Gateway calls alias `prod`, the integration URI must point to that exact alias ARN. Granting permission on an alias while configuring the integration to call the unqualified function ARN can cause calls to mismatch the policy or run an unintended version.

You can add source account constraints when supported by the integrated service and policy pattern to bind the source-owning account. Use the most specific source ARN provided by the service and avoid broad wildcards when unnecessary.

### Java SDK v2: Adding Resource Permissions

~~~java
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.AddPermissionRequest;

public final class LambdaPermissionManager {
    private final LambdaClient lambda;

    public LambdaPermissionManager(LambdaClient lambda) {
        this.lambda = lambda;
    }

    public void allowApiGateway(
            String functionName,
            String alias,
            String apiExecutionArn) {

        lambda.addPermission(AddPermissionRequest.builder()
                .functionName(functionName)
                .qualifier(alias)
                .statementId("allow-orders-api-prod")
                .action("lambda:InvokeFunction")
                .principal("apigateway.amazonaws.com")
                .sourceArn(apiExecutionArn)
                .build());
    }
}
~~~

This code should be executed by a deployment role authorized to manage Lambda resource policies. Do not place `AddPermission` inside a per-request handler; this is deployment-time infrastructure setup, not runtime business logic.

## 7. Invoke Permissions from AWS Services and Event Source Mappings

How permissions are granted also depends on which service triggers the function.

| Integration type | Invocation mechanism | Permissions typically required |
|---|---|---|
| API Gateway, S3 notification, SNS, EventBridge rule | Service pushes invocation to Lambda | Resource-based policy for the service principal, usually constrained by source ARN/account |
| IAM user or role calling SDK | Caller actively invokes Lambda API | Identity-based policy; cross-account also requires resource-side policy |
| SQS event source mapping | Lambda polls queue then invokes function | Execution role needs message read/delete and queue attribute permissions; mapping config targets function |
| Kinesis/DynamoDB Streams event source mapping | Lambda polls shard/stream | Execution role needs stream read and shard describe permissions; mapping manages checkpoints |
| Function URL | Client calls endpoint URL | AuthType configuration and URL-specific policies/actions |

With **push integrations** such as S3, SNS, or EventBridge, the service needs permission to invoke the function; Lambda's resource policy is typically where this permission is granted.

With **poll-based event source mappings** such as SQS, the Lambda service reads the queue using the function's execution role and then calls the handler. The role needs permissions like `sqs:ReceiveMessage`, `sqs:DeleteMessage`, and `sqs:GetQueueAttributes`; KMS-encrypted queues may also need decryption permissions. Do not confuse the execution role's queue-reading permissions with service-principal invoke permissions.

### Function URL

A Function URL supports AuthType `AWS_IAM` or `NONE`. With `AWS_IAM`, callers must sign requests with AWS credentials and hold appropriate invoke permissions. With `NONE`, the endpoint can be called publicly per the resource policy. Function URLs have dedicated permission actions such as `lambda:InvokeFunctionUrl`; certain setups also require the corresponding `lambda:InvokeFunction`. Configure according to the chosen AuthType and current Function URL documentation rather than copying an API Gateway policy verbatim.

Do not pick `NONE` merely to skip IAM configuration. If the endpoint accepts business data or performs writes, implement appropriate application-layer authentication/authorization and caller controls.

## 8. Execution Role: Permissions Used by Lambda Code

Every function needs an execution role. Its trust policy lets the Lambda service assume the role. Basic trust relationship example:

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

Permission policies on the role grant permissions to the code. Example where the function only needs to write logs and read objects from a specific bucket:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/lambda/order-handler:*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-input/*"
    }
  ]
}
~~~

This is an illustrative policy example; exact CloudWatch Logs permissions also depend on whether the log group is pre-created and how deployment is structured. For production, you can start from an appropriate managed policy and scope down resources as needed.

Do not grant broad permissions like `s3:*` on `*` if the function only reads one prefix. Separate roles across functions with different responsibilities so compromising one function does not automatically grant access to all application data.

## 9. Permissions for Aliases and Versions

Lambda resource-based policies can be attached at the function, version, or alias level. This matters when callers must invoke a specific release.

For example:

- Alias `prod` points to version 17.
- API Gateway integration invokes ARN `:prod`.
- Resource policy attached to alias `prod` allows API Gateway to invoke.
- Deployment role has permission to update the alias.
- Runtime execution role has permission to access the required database and logs.

When alias `prod` shifts to version 18, callers still use the same alias ARN. Verify policies and integrations on the alias after each release, especially if deployments create new aliases or rename aliases.

A policy attached to the unqualified function has a different scope from one attached to a specific qualifier. Do not assume permissions on `$LATEST` automatically apply as expected to aliases/versions. Read the resource policy of the exact ARN callers actually invoke and test with a real principal.

### Cross-Account Invocation

If an IAM role in account A invokes a Lambda in account B, permission is generally required on both sides:

1. Identity-based policy in account A allowing the role to invoke the function/alias ARN in account B.
2. Resource-based policy in account B allowing that principal or account A to invoke that function/alias.

If an AWS service in another account invokes the function, the resource policy must restrict both principal and invoke source appropriately. Avoid granting permissions to an entire account or broad principal when only a specific role/service needs access.

## 10. Least Privilege and Preventing Confused Deputy

When allowing an AWS service to invoke a function, specifying only a principal like `events.amazonaws.com` or `apigateway.amazonaws.com` can be overly broad without source constraints. A service principal can represent many resources across many accounts.

Use `SourceArn` to bind a specific source resource, and `SourceAccount` when the integration pattern supports it and you need to bind the source-owning account. This mitigates confused deputy risks: another resource exploiting the service's permissions to invoke your function unintentionally.

Principles to apply:

- Grant permissions to the exact principal, exact action, and exact function qualifier.
- Restrict source ARN/account on service principals whenever possible.
- Do not use wildcards across an entire API, bucket, or event bus if only one source needs to invoke.
- Separate deploy/publish/alias-update permissions from the function's runtime permissions.
- Audit resource policies and IAM policies periodically.
- Revoke stale statements when triggers or integrations are deleted.
- Verify permissions using the IAM policy simulator or test invocations from the actual principal in a test environment.

## 11. Version and Alias Release Pipeline

A release pipeline can follow this sequence:

1. Build the JAR and store an immutable artifact tagged by commit/build ID.
2. Update `$LATEST` code and configuration in the target environment.
3. Run smoke or integration tests against `$LATEST`/staging.
4. Publish a version after verifying code hash and configuration.
5. Update the `staging` alias to the new version and run integration tests.
6. Update `canary`/`prod` aliases per the chosen traffic strategy.
7. Monitor metrics and logs per version.
8. Promote 100% traffic or roll back the alias.
9. Record deployment metadata: version, alias, artifact hash, commit, timestamp, deploying user/role, and outcome.
10. Delete old versions only when confident no alias, caller, event source mapping, or rollback procedure still needs them.

~~~mermaid
flowchart TD
    A["Build Java artifact"] --> B["Update $LATEST"]
    B --> C["Smoke test"]
    C --> D["Publish version N"]
    D --> E["Move staging alias"]
    E --> F["Integration test"]
    F --> G["Canary on prod alias"]
    G --> H{"Metrics acceptable?"}
    H -->|Yes| I["Promote 100% to N"]
    H -->|No| J["Rollback alias"]
    I --> K["Record release and retain prior version"]
~~~

### Post-Deployment Permission Verification

A release may work when a developer tests with a broad role yet fail when API Gateway or EventBridge invokes via a service principal. Verify both directions:

- Can the caller invoke the exact alias ARN?
- Does the resource policy have the right principal and source ARN?
- Can the function assume the execution role?
- Does the execution role have read/write permissions on required resources?
- Are KMS key policies, VPC endpoint policies, or bucket policies blocking requests?
- Are triggers/event source mappings pointing to the right function ARN/alias?

Do not rely solely on console test events; console tests do not prove that production integration principals have invoke permissions.

## 12. Real-World Scenario: API Gateway Calling Java Lambda via Alias prod

Suppose a `POST /orders` API invokes Java Lambda `order-handler`. Production alias `prod` points to version 17.

Recommended setup:

- API Gateway integration URI points to the alias ARN of `order-handler`.
- Lambda resource policy allows principal `apigateway.amazonaws.com` to invoke alias `prod` from the exact API, stage, method, and resource.
- Function execution role allows writing logs and accessing the exact tables/databases needed.
- Deployment role is permitted to update function code/config, publish versions, update aliases, and add/remove permissions.
- External callers are authenticated at API Gateway using the API's auth mechanism.

When releasing version 18:

1. Upload the new JAR to `$LATEST` and update configuration.
2. Test the function in staging.
3. Publish version 18.
4. Keep API Gateway invoking alias `prod`.
5. Switch alias `prod` to version 18 or enable weighted routing if appropriate for the trigger.
6. Monitor error rate, latency, throttling, and business errors.
7. If errors occur, point the alias back to version 17.
8. Retain version 18 for investigation; do not delete immediately after rollback.

Callers continue sending requests to the same API URL. API Gateway continues invoking the same alias ARN; the alias controls which version executes.

## 13. Checklist for Managing Versions, Aliases, and Invoke Permissions

- [ ] Production does not accidentally invoke `$LATEST` when stable releases are required.
- [ ] Every release is published as an immutable version tied to an artifact/build ID.
- [ ] `prod`/`staging`/`canary` aliases point to tested versions.
- [ ] Callers use the designed alias ARN or version ARN.
- [ ] Weighted routing is enabled only when triggers and integrations support verified semantics.
- [ ] Alias rollback is rehearsed and teams understand it does not reverse side effects.
- [ ] Identity-based policies grant invoke permissions to the right callers and function ARNs.
- [ ] Resource-based policies grant permissions to the right service principals and source ARNs/accounts.
- [ ] Execution role has a Lambda trust policy and least-privilege permission policies.
- [ ] Invoke permissions are not confused with permissions used by code to access AWS resources.
- [ ] SQS/stream event source mappings have source read permissions in the execution role.
- [ ] Function URLs use appropriate AuthType and permission actions.
- [ ] Cross-account invocations have allowing policies on both sides when needed.
- [ ] Deployment role is separated from the runtime execution role.
- [ ] Old resource policy statements are cleaned up when deleting integrations or triggers.
- [ ] Invocations have been tested from real principals and logs/metrics verified per version.

## Self-Check

1. When a caller invokes an unqualified function ARN, which copy does Lambda run? Why can this be dangerous in production?
2. Which settings does a published version freeze, and which dependencies can still change?
3. How does an alias differ from a published version?
4. How can weighted alias routing support canary deployments?
5. How do identity-based policies and resource-based policies differ in attachment point and principal specification?
6. Does an execution role grant API Gateway permission to invoke a function? Explain the two permission directions.
7. Why should permissions for service principals be constrained with `SourceArn` and potentially `SourceAccount`?
8. With an SQS event source mapping, why does the execution role need queue read permissions?
9. When rolling back an alias to an older version, which side effects still need separate handling?

Managing Lambda versions and aliases gives precise control over which code release executes at each stage. IAM identity policies, Lambda resource policies, and execution roles protect different access directions. When callers target stable aliases, versions are published immutably, and permissions are scoped to exact principals and invoke sources, development teams can roll out Java functions incrementally and recover cleanly.
