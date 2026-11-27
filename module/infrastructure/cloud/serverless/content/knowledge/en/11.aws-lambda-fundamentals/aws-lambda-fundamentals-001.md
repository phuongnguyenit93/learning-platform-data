# AWS Lambda Application Structure and Resource Model

AWS Lambda is AWS's FaaS service: you deploy processing code, configure how it runs, and connect the function to trigger sources; AWS manages provisioning the execution environment, scaling, and the underlying server infrastructure. A Lambda application is therefore not just a single JAR file. It is a collection of interconnected resources: function, deployment code, runtime, execution role, invocation permissions, triggers, event source mappings, versions, aliases, network configuration, storage, concurrency, and operational observability components.

Understanding the resource model helps determine the right place to configure a behavior. For example, the execution role determines whether a function can read an object in S3 or write to DynamoDB; the resource-based policy determines which service or account is allowed to invoke the function; the event source mapping determines how Lambda reads messages from SQS or a stream; aliases help clients call a stable version while the team deploys a new version.

With Java, application code is usually packaged as a ZIP/JAR with dependencies or a container image. The runtime invokes the handler according to the Lambda contract. Shared objects such as AWS SDK clients can be initialized once in the execution environment for reuse, but business data and state that need to persist across invocations must be stored in a durable service such as S3, DynamoDB, or an appropriate database.

## 1. Viewing a Lambda Application as a Collection of Resources

A typical serverless application can consist of multiple functions, each responsible for a business step. Functions are connected via API Gateway, EventBridge, SNS, SQS, streams, workflows, or direct invocations.

~~~mermaid
flowchart LR
    C["Client"] --> APIGW["API Gateway"]
    APIGW --> F1["Order API function"]
    F1 --> DB[("DynamoDB / database")]
    F1 --> Q["SQS queue"]
    Q --> F2["Order worker function"]
    F2 --> S3[("S3 object storage")]
    EB["EventBridge rule"] --> F3["Notification function"]
    F3 --> SNS["SNS / email provider"]
    IAM["IAM roles and policies"] -.-> F1
    IAM -.-> F2
    IAM -.-> F3
    CW["CloudWatch logs and metrics"] -.-> F1
    CW -.-> F2
    CW -.-> F3
~~~

Resources can be divided into the following groups:

| Group | Typical resources | Role |
|---|---|---|
| Compute | Lambda function, runtime, architecture, memory, timeout | Determines which code runs and resource limits |
| Code packaging | ZIP deployment package, container image, Lambda layer | Provides code and libraries to the runtime |
| Identity and access | Execution role, trust policy, permission policy, resource-based policy | Controls which services the function calls and who can invoke the function |
| Invocation | API Gateway integration, Function URL, EventBridge rule, SNS subscription | Connects event sources to the function |
| Event consumption | Event source mapping, SQS queue, stream, batch settings | Controls how Lambda reads and passes messages into the function |
| Release | Published version, alias, weighted routing | Manages versioning and releases |
| State and storage | S3, DynamoDB, RDS, EFS, ephemeral storage | Stores durable or temporary data |
| Network | VPC, subnet, security group, VPC endpoint, NAT | Controls connectivity to network resources |
| Operations | CloudWatch Logs, metrics, alarms, tracing, destinations, DLQ | Observability, alerting, and recovery |

Some resources belong directly to the function configuration; others are standalone resources referencing the function. For example, memory and timeout are function configurations, whereas event source mappings and aliases are separate resources. When deploying with Infrastructure as Code, both the function and its connecting resources must be described, rather than just creating the function and configuring triggers manually.

## 2. What is a Lambda Function?

A Lambda function is the unit of code deployment and execution. Each function has a name, ARN, code package or image, runtime, handler, execution role, and settings such as memory, timeout, architecture, environment variables, VPC, layers, ephemeral storage, and tracing.

A function is not equivalent to a fixed server. AWS creates an execution environment when needed, may reuse an initialized environment for subsequent invocations, and may create additional environments as load increases. You do not directly manage the number of virtual machines or the underlying operating system.

A function typically has the following properties:

- **Function name:** an identifier name within an AWS account and Region.
- **Function ARN:** resource identifier referenced by policies, triggers, and clients.
- **Code:** ZIP package or container image URI.
- **Runtime:** an execution environment supported by Lambda, such as a Java runtime.
- **Handler:** the entry point that the runtime invokes.
- **Execution role:** the IAM role that Lambda assumes when running the function.
- **Memory size and timeout:** resource and time limits for an invocation.
- **Architecture:** CPU architecture such as x86_64 or arm64 if compatible with the runtime and package.
- **Environment variables:** configuration passed into the process.
- **VPC configuration:** subnets and security groups if the function needs access to resources in a VPC.
- **Layers and extensions:** libraries or extension processes attached to the execution environment.
- **Ephemeral storage:** capacity of local temporary storage.

A function can be invoked synchronously, asynchronously, or via an event source mapping. The invocation mode determines who waits for the result, who is responsible for retries, and how messages are acknowledged.

## 3. Java Handlers and Runtimes

The runtime is the component that starts the application and dispatches invocations to the handler. With Java, a handler is usually a class implementing an AWS Lambda Java Core interface or a class with a method matching a handler signature supported by the runtime.

Example using RequestHandler:

~~~java
package com.example.orders;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class OrderHandler
        implements RequestHandler<OrderRequest, OrderResponse> {

    @Override
    public OrderResponse handleRequest(
            OrderRequest request,
            Context context) {

        context.getLogger().log(
                "Processing order request: " + request.orderId()
        );

        return new OrderResponse(
                request.orderId(),
                "ACCEPTED"
        );
    }
}
~~~

In the function configuration, the handler is declared using the fully qualified class name, for example:

~~~text
com.example.orders.OrderHandler
~~~

The class and package names must match the contents of the deployment artifact. If you change the package or class without updating the handler, Lambda cannot load the entry point and the invocation fails immediately during initialization.

Common options:

- RequestHandler<Input, Output> for events mapped to Java types and returning an object.
- RequestStreamHandler when you need to read the input stream and write the output stream directly, often useful for custom payloads or adapters.
- Custom handler following the runtime contract when using a custom runtime or framework adapter.

The Context interface provides invocation and runtime information, such as request ID, function name, memory limit, remaining time, and logger. Do not store Context in a static field or use it as shared state across invocations.

With frameworks like Spring Boot, Quarkus, or Micronaut, you must use an adapter or integration suitable for the Lambda runtime. Not every traditional web server application can be dropped as-is into a function without adjusting bootstrap, handler, and request management.

## 4. Code Packaging: ZIP, JAR, Layers, and Container Images

Lambda supports multiple ways to package code. Choose the method that fits application size, dependencies, native libraries, build pipeline, and release organization.

### ZIP deployment package

A ZIP package contains compiled classes and required dependencies. With Java, a common approach is placing classes and resources at the root of the archive and dependency libraries in a `lib` directory according to the structure expected by the runtime. Inspect the artifact structure after building; a ZIP may upload successfully yet still fail if the handler or dependencies are not located where the runtime looks for them.

Illustrative structure example:

~~~text
function.zip
├── com/
│   └── example/
│       └── orders/
│           └── OrderHandler.class
└── lib/
    ├── aws-lambda-java-core.jar
    ├── jackson-databind.jar
    └── application-dependencies.jar
~~~

You can use the Maven Shade Plugin or Gradle Shadow Plugin to create a merged-dependency artifact, or build a ZIP in a structure supported by the runtime. If using a fat JAR, ensure that manifests, service loaders, resources, and dependency metadata are not incorrectly overwritten during merging.

### Lambda layers

A layer is a separate archive containing libraries, a custom runtime, or shared content for multiple functions. A function can attach multiple layers up to Lambda limits. Layers help separate shared dependencies from application code, but they also introduce an additional versioned component to manage.

Use a layer when there are libraries or tools that are genuinely shared and need to be released independently. Do not put every dependency into a single shared layer just to reduce ZIP size; changing a layer version can affect multiple functions, making rollbacks and dependency tracking harder.

Layers are not a place to store business data and do not automatically grant access permissions to a function. With Java, verify the directory structure of the layer so the runtime picks up the JARs and classpath properly.

### Container image

A function can be deployed as a container image stored in Amazon ECR. This approach fits when you need control over the packaging environment, have native dependencies, or want to use a unified container build pipeline. The image must conform to the Lambda container image contract, including the runtime interface; AWS base images usually provide the required components.

Using a container image does not turn Lambda into a continuously running container service. Lambda still manages invocations, execution environments, scaling, and runtime limits. Images must be built for the configured CPU architecture and updated when runtime or dependency patches are released.

### Choosing a packaging format

| Criterion | ZIP/JAR | Layer | Container image |
|---|---|---|---|
| Application code | Packaged directly | Not the primary place for handlers | Packaged inside the image |
| Dependencies | Can be bundled with the package | Separates shared libraries | Installed in the image |
| Reuse across functions | Via build artifacts or layers | Primary purpose of a layer | Via base images/build pipelines |
| OS and native library control | Limited by the runtime | Limited by the layer contract | More flexible within Lambda limits |
| Release process | ZIP upload or S3 | Release separate layer versions | Build, scan, and push ECR image |

## 5. Execution Role and Resource-Based Policy

A common point of confusion is that the permissions a function uses to call other services differ from the permissions a service or principal uses to invoke the function.

### Execution role

An execution role is the IAM role that Lambda assumes during execution. The role's trust policy allows the Lambda service principal to assume the role. Permission policies attached to the role determine which actions the function can perform on AWS resources.

For example, an order worker might need to:

- Read messages from a specific queue through the trigger mechanism.
- Read or write a specific DynamoDB table.
- Write logs to CloudWatch Logs.
- Read required secrets from Secrets Manager.
- Invoke another function if business logic requires it.

Grant least-privilege permissions per function. Do not use a single broad execution role for all functions just because they belong to the same application. If a function only needs to write objects to a specific bucket prefix, the policy should restrict the bucket, prefix, and required actions.

### Resource-based policy

A Lambda resource-based policy specifies which principals are allowed to invoke the function or a qualifier of the function. This policy is commonly updated with permissions for services such as API Gateway, S3, SNS, or EventBridge to invoke the function.

For example, an S3 bucket can be permitted to invoke a function when an object is created under a specific prefix. Granting S3 invoke permission does not give the function permission to read every object in the bucket; the function still needs an execution role for the S3 actions it performs.

### Distinguishing the two permission directions

| Question | Primary mechanism |
|---|---|
| Can the function read S3 or write to DynamoDB? | Execution role and permission policies |
| Can EventBridge or S3 invoke the function? | The function's resource-based policy or corresponding integration mechanism |
| Can a user or service call API Gateway? | Authorization at API Gateway and related policies |
| Can a function invoke another function? | Execution role of the calling function, along with the target function's resource policy when needed |

For triggers and AWS integrations, check both sides: whether the source has permission to invoke the target, and whether the function has permission to access the resources required by its logic. Do not treat successful trigger creation as proof that all runtime permissions are correct.

## 6. Invocation Types and Triggers

Lambda can be invoked in multiple ways. The invocation type affects latency, responses, retries, and error handling.

### Synchronous

The caller waits for the function to process and receives a response. Common examples:

- API Gateway calling Lambda for an HTTP API or REST API.
- Application Load Balancer invoking a Lambda target.
- Function URL providing an HTTPS endpoint for a function.
- An application calling the Lambda Invoke API with invocation type RequestResponse.
- Another function directly invoking the target function.

If the function times out or returns an error, the caller receives an error result according to the integration. Clients may retry, so operations with side effects still require idempotency.

### Asynchronous

The source sends an event and does not wait for the final business result. Lambda places the event into an internal queue for later processing. Examples:

- S3 notification.
- SNS notification.
- EventBridge rule or event bus.
- Invoke API call with invocation type Event.

Retries, maximum event age, and a dead-letter queue or on-failure destination should be configured as needed. The fact that Lambda accepted an event does not mean the handler processed it successfully. An event may be retried and cause duplicate delivery; the consumer must be idempotent.

### Poll-based with event source mapping

For sources such as SQS, Kinesis Data Streams, DynamoDB Streams, Amazon MSK, or compatible sources, Lambda uses an event source mapping to read data and pass batches to the function. An event source mapping is a separate configuration resource.

It can control:

- The event source and target function.
- Batch size and maximum batching window.
- Starting position for streams.
- Filter criteria.
- Parallelization and concurrency controls.
- Partial batch response or bisect batch depending on the source.
- Retry, bisect, and destination/error handling according to source semantics.

With SQS, the event source mapping polls the queue and invokes the function in batches. With Kinesis or DynamoDB Streams, reading progress is tied to shards and sequence/iterator semantics. Do not apply the same acknowledgment model to every source.

### Comparison table

| Invocation type | Who waits for the result? | Component that typically manages retries | Examples |
|---|---|---|---|
| Synchronous | Caller | Caller or integration per configuration | API Gateway, Function URL |
| Asynchronous | Does not wait for handler result | Lambda async invocation configuration | S3, SNS, EventBridge |
| Event source mapping | Source is polled and batches are passed to function | Event source mapping and broker semantics | SQS, Kinesis, DynamoDB Streams |

## 7. Event Source Mapping as a Separate Resource

An event source mapping connects a supported event source to a Lambda function. It is not merely a property of the handler. AWS manages the poller or source reader according to the mapping configuration and then invokes the function.

Important properties depending on source type:

- ARN of the event source, such as a queue ARN or stream ARN.
- Target function ARN or qualifier.
- Enabled/disabled state.
- Batch size and batching window.
- Starting position and starting position timestamp for stream sources.
- Filter criteria.
- Maximum concurrency or scaling settings when supported by the source.
- Partial batch response, bisect batch, and retry policy.
- Tumbling window or destination for certain stream integrations.

With SQS, a function can receive multiple messages in a single invocation. If a message fails, partial batch response can be enabled to report only the failed message if the integration supports it. Otherwise, the entire batch may be redelivered; per-message idempotency is required.

With streams, records are divided by shard or partition and have ordering requirements. A failing record can block shard progress; configuring bisect batch or a failure destination can help isolate bad records. Understand the retry and checkpoint policies of each event source before changing batch size or concurrency.

An event source mapping typically requires permission to read the source in the function's execution role. For example, an SQS mapping needs permissions to receive, delete, and read queue attributes as required by Lambda; specific permissions should follow least privilege. When a mapping does not work, check mapping state, permissions, encryption key policy, network/dependencies, and source metrics.

## 8. Versions, Aliases, and Controlled Releases

Lambda provides versions and aliases to decouple function updates from how clients invoke the function.

- **$LATEST:** mutable version of the function that changes when code or configuration is updated.
- **Published version:** an immutable snapshot of code and versioned configuration at the time of publishing.
- **Alias:** a named pointer to a specific version; an alias can be updated to point to another version and supports weighted routing in appropriate cases.

An unqualified ARN references the function without specifying a version; a qualifier can be a version or an alias. When API Gateway, an event source mapping, or a client references an alias, the team can publish a new version and then shift the alias after testing.

Example workflow:

1. Update the code and configuration of $LATEST.
2. Run tests and verify the artifact.
3. Publish a new version.
4. Update the staging or production alias to point to that version.
5. If needed, split traffic between the current version and the new version by percentage.
6. Monitor error rates, latency, and business metrics.
7. Shift all traffic or roll back the alias to the previous version.

An alias is not an independent function and does not create a separate execution role or storage. It is a reference point to a version. Weighted routing can support canary releases, but it does not replace database/schema compatibility testing or handling of in-flight events.

Environment variables and certain sensitive configurations must be managed alongside Lambda's versioning and deployment process. Verify clearly which properties are frozen when publishing a version and which can be changed outside of a version according to current AWS documentation.

## 9. Memory, Timeout, Architecture, and Concurrency

Lambda allows configuring resources and limits per function. These settings affect latency, throughput, scaling, and cost.

### Memory and CPU

The memory setting determines the memory allocated to the execution environment; CPU capacity is allocated proportionally to the memory configuration under Lambda's model. Increasing memory can reduce CPU-bound execution time and some initialization steps, though cost per unit of time also changes.

Benchmark multiple memory levels with the same artifact and workload. Compare p95/p99 latency, throughput, memory usage, and cost per successful invocation. Do not choose memory based solely on minimum JVM heap size.

### Timeout

Timeout limits how long a single invocation is allowed to run. Choose timeout based on SLA, dependency latency, batch size, and time needed to write results or handle errors. A timeout that is too long can hold resources and messages longer; a timeout that is too short causes unnecessary failures and retries.

### Architecture

Lambda supports architectures such as x86_64 and arm64 depending on the runtime. Packages and native dependencies must be compatible with the configured architecture. If using JNI, native libraries, or container images, build and test for the exact target architecture.

### Concurrency

Concurrency is the number of invocations running simultaneously. Key concepts:

- **Account concurrency limit:** concurrency limit at the account/Region level.
- **Reserved concurrency:** reserves and simultaneously caps maximum concurrency for a function.
- **Provisioned concurrency:** pre-initializes execution environments to reduce cold starts for the configured capacity.
- **Event source mapping maximum concurrency:** limits the rate or number of invocations generated by a mapping when supported by the source type.

Reserved concurrency helps protect dependencies and guarantees dedicated capacity for a function, but it can also limit that function's ability to scale. Provisioned concurrency helps reduce cold starts for traffic requiring consistent latency, but incurs ongoing maintenance cost. These serve two different goals; do not use them interchangeably.

When calculating concurrency, multiply maximum invocations by parallel calls, connection pools, and batch sizes. A function may scale well while a downstream database or partner API becomes the bottleneck.

## 10. Environment Variables, Secrets, and Configuration

Environment variables provide runtime configuration such as table names, buckets, endpoints, feature flags, or application timeouts. Do not put passwords, API keys, or long-lived credentials into source code or committed configuration files.

For secrets, prefer AWS Secrets Manager or Systems Manager Parameter Store with an execution role restricting read permissions. Consider caching secrets in the execution environment to reduce latency and cost, but include a TTL/refresh aligned with rotation. Do not cache revocable credentials indefinitely.

Key principles:

- Separate configurations by environment such as dev, staging, and production.
- Do not hardcode resource names when deploying across multiple stacks or Regions.
- Validate required configuration during function initialization.
- Do not log all environment variables.
- Encrypt environment variables using Lambda/KMS mechanisms when needed.
- Restrict KMS decrypt permissions by key and principal.
- Define how secrets are updated and when the function picks up new values.

Environment variables are not a state store. Values in a process may remain while an environment is reused, but can disappear when the environment is reclaimed.

## 11. VPC, Networking, and Private Resource Access

By default, Lambda can access AWS services through public service endpoints according to the platform's network configuration. If a function needs to access a database or service located only inside a VPC, the function can be attached to one or more appropriate subnets and security groups.

When attaching a VPC:

- Choose subnets with appropriate routes to target resources.
- The function's security group must allow required egress traffic.
- The database or service's security group must allow ingress from the function's security group.
- If public internet access is needed, design an appropriate NAT or egress path.
- Consider VPC endpoints for AWS services for private access and reduced NAT dependency.
- Check DNS, route tables, NACLs, security groups, and related quotas.

A function attached to a private subnet does not automatically have internet access. A route to an Internet Gateway from a private subnet does not assign a public IP to a Lambda ENI the way a public EC2 instance gets one. Design egress through NAT or endpoints as required.

VPC configuration affects connectivity and cold start behavior depending on service architecture. Do not attach a function to a VPC unless private resource access is required; if needed, measure latency and test network paths from the actual deployment environment.

## 12. Storage: Ephemeral Storage, S3, DynamoDB, and EFS

Lambda provides local temporary storage, typically accessed via the `/tmp` directory. This area is useful for intermediate files, archive extraction, or processing large payloads within an invocation/environment. It is not durable storage and may retain contents when an environment is reused.

| Storage | Characteristics | Used for |
|---|---|---|
| Memory/heap | Fast, exists only within the process | Small caches, objects within an invocation |
| /tmp ephemeral storage | Local temporary file storage for the execution environment | Extraction, file conversion, short-term staging |
| Amazon S3 | Durable, scalable object storage | File uploads, reports, artifacts, large payloads |
| DynamoDB | Managed NoSQL database | State, idempotency, metadata, lookups |
| RDS/Aurora | Relational database | Transactions and relational queries |
| Amazon EFS | Shared file system mountable to Lambda | Workloads requiring a durable/shared filesystem where supported |

If data needs to survive across invocations or be shared across multiple environments, store it in a durable service. Do not use a static map or `/tmp` as the single source of truth. With EFS, verify VPC, mount targets, security groups, throughput, and file permissions.

## 13. Layers, Extensions, and Runtime Configuration

Layers provide libraries or supplementary content for a function. Extensions are external or internal processes that can participate in the execution environment lifecycle, such as sending telemetry or fetching configuration. They help reuse tooling across multiple functions, but also consume resources and affect initialization time.

When adding a layer or extension:

- Identify the exact version and owner of the artifact.
- Verify runtime and architecture compatibility.
- Check file ordering or merging behavior if multiple layers contain overlapping paths.
- Measure impact on cold start, memory, and shutdown time.
- Restrict permissions of the extension and the endpoints it calls.
- Track versions and release security updates.
- Do not place core business logic inside an extension that is hard to observe or test.

Lambda extensions can run inside the execution environment alongside the function, but they are not separate functions invoked independently. Their lifecycle and resource limits must be understood in the context of the runtime.

## 14. Logging, Metrics, Tracing, and Destinations

CloudWatch Logs is commonly used to store function logs. The execution role needs appropriate log-writing permissions; when permissions are missing, the handler may run while logs fail to appear as expected. Logs should include request ID, correlation ID, function version or alias, outcome, and latency; do not log tokens, secrets, or sensitive payloads.

Observability layers:

- **Logs:** details of a single invocation and errors.
- **Metrics:** invocation count, error count, duration, throttles, concurrency, iterator age, or queue age depending on the source.
- **Tracing:** tracking request flow across API Gateway, Lambda, and dependencies using AWS X-Ray or OpenTelemetry as configured.
- **Alarms:** alerts when error rate, latency, throttling, DLQ, or backlog exceeds thresholds.
- **Destinations:** routing failed or successful asynchronous invocation results to target resources as configured.

Do not confuse an asynchronous invocation destination with a DLQ. Destinations can receive metadata and context about an invocation result; DLQs typically hold failed events/messages according to configuration semantics. Choose the mechanism based on investigation, replay, and downstream processing needs.

With event source mappings, monitor queue or stream metrics alongside Lambda metrics. A function may show a low error rate while queue age climbs due to low concurrency or throttled dependencies. With Kinesis/DynamoDB Streams, iterator age and shard-level progress are critical indicators.

## 15. Deploying Applications with Infrastructure as Code

A Lambda application requires many interconnected resources. Infrastructure as Code helps create consistent environments, review changes, control drift, and recreate stacks.

Common tools:

- AWS SAM: models Lambda, APIs, event sources, and serverless resources using templates.
- AWS CDK: defines resources in a programming language and synthesizes CloudFormation.
- CloudFormation: declares AWS resources in templates.
- Terraform: manages infrastructure via Terraform providers and state.

A function template needs to declare or reference properties such as:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: order-api
      Runtime: java21
      Handler: com.example.orders.OrderHandler
      Role: !GetAtt OrderExecutionRole.Arn
      Code:
        S3Bucket: deployment-artifacts
        S3Key: orders/order-function.zip
      MemorySize: 1024
      Timeout: 15
      Architectures:
        - arm64
      Environment:
        Variables:
          ORDERS_TABLE: orders
~~~

This is a simplified CloudFormation example illustrating the resource model. The runtime value must be in the list of runtimes supported by AWS at deployment time; bucket, key, role, and resource names must be adjusted per environment. A production template also requires policies, logging, tracing, VPC if needed, versions/aliases, triggers, and data protection settings.

Deploy in dependency order: create roles and policies, create the function, publish a version, create an alias, and then connect APIs/triggers/event source mappings using the desired qualifier ARN. CloudFormation can manage dependency relationships if proper resource references are declared.

Do not modify production resources directly outside IaC without updating the source of truth. Manual changes easily introduce configuration drift and cause subsequent deployments to overwrite important settings.

## 16. Resource Model Example for an Order Processing Application

Suppose an application has an order creation API, a payment processing worker, and a notification function.

| Resource | Main configuration or permissions | Purpose |
|---|---|---|
| API Gateway route | POST /orders, authorizer, integration | Receives requests and invokes Order API |
| Order API Lambda | Java handler, memory, timeout, execution role | Validates and writes orders |
| Order execution role | Write to Orders table, publish to queue, write logs | Outbound permissions for API function |
| Orders table | Partition key by order ID or tenant design | Stores order state |
| Payment queue | Retention, visibility timeout, redrive policy | Decouples payment processing from request |
| Payment worker Lambda | Event source mapping, batch size, concurrency | Processes payment messages |
| Payment worker role | Consume queue, update order status, call secret service | Outbound permissions for worker |
| Notification rule/queue | EventBridge or SNS depending on flow | Emits notifications at appropriate states |
| Notification Lambda | Java handler and permission to send notifications | Sends notifications |
| Versions and aliases | Published version and production alias | Controlled release/rollback |
| CloudWatch | Logs, metrics, alarms, tracing | Monitors errors, latency, and backlog |

Processing flow:

1. Client calls API Gateway.
2. API Gateway authenticates and invokes Order API Lambda.
3. The function checks permissions, validates data, and writes the order with status PENDING_PAYMENT.
4. The function sends a message to the payment queue and returns 202 or 201 depending on the business contract.
5. Event source mapping polls the queue and invokes Payment worker.
6. The worker calls the payment provider, updates order status, and acknowledges the message per contract.
7. When payment succeeds, an event is emitted for the notification function to send a notification.
8. CloudWatch metrics and logs help trace each step via correlation ID.

Each function has its own execution role with only the required permissions. The queue has a DLQ or redrive policy; the worker handles duplicate messages using idempotency. API, worker, and notification can be versioned independently while maintaining event contract compatibility.

## 17. Naming, Tagging, and Environment Separation

As the number of functions grows, naming and tagging help identify owners, environments, costs, and purposes. A naming convention might include product name, domain, workload, and environment, for example:

~~~text
orders-api-dev
orders-worker-staging
orders-notification-prod
~~~

Tags can include:

- Application or system.
- Environment.
- Team/owner.
- Cost center.
- Data classification.
- ManagedBy or IaC stack.
- Repository or release identifier if policy permits.

Do not put secrets, personal information, or sensitive data into function names or tags. Function names, ARNs, and tags may appear in logs, metrics, audits, and consoles.

Separate accounts or environments along appropriate security and operational boundaries. Do not share a production role with staging just to reduce the number of policies. Endpoints, buckets, tables, and secrets should be passed per environment and validated at deployment time.

## 18. Costs and Limits to Account for in the Resource Model

Lambda cost is not just the number of function invocations. Depending on configuration and integrations, costs can include requests, duration weighted by memory, provisioned concurrency, ephemeral storage beyond included capacity, data transfer, CloudWatch Logs, API Gateway, queues, databases, NAT, and other services.

Settings that affect cost:

- Memory and execution duration.
- Number of invocations and concurrency.
- Provisioned concurrency and how long it is maintained.
- Log size, retention, and trace sampling rate.
- Number of retries, batch size, and message backlog.
- Number of connections and requests to dependencies.
- Data transfer across NAT or between AZs/Regions.
- Object storage, versioning, and lifecycle.

Measure cost by business flow rather than by function alone. A cheap function that makes excessive database calls or emits verbose logs can drive overall application costs high. Limiting concurrency can reduce downstream load and cost, but setting it too low increases queue age and completion time.

## 19. Process for Designing and Deploying a Function

You can follow this sequence for each function:

1. **Define responsibility:** the function performs a clear business step with an input/output contract.
2. **Choose trigger:** HTTP, direct invocation, async event, or event source mapping.
3. **Choose runtime and handler:** determine Java runtime, handler signature, and framework adapter.
4. **Package artifact:** ZIP/JAR, layers, or container image; verify dependencies and architecture.
5. **Create execution role:** trust policy for Lambda and least-privilege permissions to required resources.
6. **Configure resources:** memory, timeout, ephemeral storage, environment variables, VPC, and concurrency.
7. **Grant invoke permissions:** resource-based policy or appropriate integration for principals/triggers.
8. **Design state and retries:** database, queue, idempotency, DLQ, and timeout.
9. **Create release resources:** publish version, alias, and traffic shifting strategy.
10. **Observability:** logs, metrics, traces, alarms, and destinations.
11. **Deploy with IaC:** declare the function along with triggers and dependencies.
12. **Test and release:** verify permissions, triggers, duplicate events, timeouts, scaling, rollbacks, and costs.

A useful check is tracing permissions in both directions: from caller to function and from function to resources. If you cannot identify which principal invokes the function, which role the function assumes, what permissions that role has, and where the trigger is configured, the resource model is not yet complete.

## 20. AWS Lambda Application Review Checklist

Before promoting a function to production, check:

1. Are the function name, ARN, Region, and account correct?
2. Are the runtime, handler, and artifact compatible?
3. Does the ZIP package or image contain all required classes, resources, and dependencies?
4. Does the function architecture match the artifact and native libraries?
5. Does the execution role have the proper trust policy and least-privilege permissions?
6. Does the resource-based policy restrict the right principals and invoke sources?
7. Is the trigger synchronous, asynchronous, or an event source mapping?
8. Do retry, timeout, batch, visibility/ack, and DLQ settings match source semantics?
9. Does the function persist important state to a durable service?
10. Have memory, timeout, ephemeral storage, and concurrency been benchmarked?
11. Do VPC, subnets, security groups, routes, and endpoints allow required connections?
12. Are secrets and environment variables managed securely?
13. Do versions and aliases support release/rollback?
14. Are logs, metrics, tracing, and alarms sufficient for troubleshooting?
15. Does IaC manage the function and all related resources?
16. Have duplicate events, bursts, dependency failures, and permission denials been tested?
17. Are costs tracked for both Lambda and all dependencies?

## Conclusion

An AWS Lambda application is a collection of resources linked around a function: code package, runtime, handler, execution role, triggers, event source mappings, resource policies, storage, networking, concurrency, versions/aliases, and operational components. The function defines the code and execution configuration; IAM governs permissions in both directions; triggers or event source mappings determine how events enter; versions and aliases control releases.

With Java, choose an appropriate runtime and handler, package dependencies reproducibly, reuse thread-safe clients within the execution environment, and store business state in durable services. When resources are modeled with IaC, granted least privilege, thoroughly observed, and tested against invocation semantics, a Lambda application is easier to deploy, scale, and operate.
