# Declaring Applications with Serverless Framework

## Learning Objectives

After this lesson, you can:

- Explain the role of Serverless Framework in describing and deploying serverless applications.
- Structure a Java project around the concepts of service, function, event, resource, and provider.
- Write `serverless.yml` to declare Lambda functions, HTTP APIs, queues, schedules, and AWS resources.
- Package Java artifacts with Maven and connect the artifact to deployment configuration.
- Manage stages, regions, environment variables, IAM permissions, and per-function settings.
- Deploy, inspect, update, and remove a service in a controlled manner.
- Design retries, idempotency, logging, and CI/CD pipelines for serverless applications.

## 1. What Is Serverless Framework?

Serverless Framework is an Infrastructure as Code (IaC) tool for describing and deploying serverless applications using a configuration file. For AWS, the main file is typically `serverless.yml`. This file declares the provider, functions, event triggers, IAM permissions, infrastructure resources, and deployment settings.

When you run the deploy command, Serverless Framework parses the configuration, packages the artifact as configured, generates a CloudFormation template, and deploys the required resources to AWS. Developers manage the application via source code and configuration that can be reviewed in Git.

Serverless Framework does not replace AWS Lambda, API Gateway, SQS, EventBridge, or DynamoDB. The framework describes how those services combine into an application. The runtime still executes functions; AWS services still handle triggers, storage, scaling, and security.

### 1.1. Overall Model

~~~mermaid
flowchart TD
    A[Java source and serverless.yml] --> B[Maven build]
    B --> C[JAR artifact]
    A --> D[Serverless Framework CLI]
    C --> D
    D --> E[CloudFormation template]
    E --> F[AWS resources]
    F --> G[Lambda functions]
    F --> H[API Gateway / SQS / EventBridge]
    H --> G
    G --> I[DynamoDB / S3 / other services]
~~~

Basic deployment flow:

1. Developers write Java handlers and declare infrastructure in `serverless.yml`.
2. Maven compiles source code and builds an artifact with required dependencies.
3. Serverless Framework reads the configuration, references the artifact, and creates the deployment package.
4. The framework creates or updates a CloudFormation stack.
5. AWS provisions the functions, event source mappings, API routes, IAM roles, and declared resources.
6. Event triggers invoke functions when matching requests or events arrive.

### 1.2. Key Concepts

| Concept | Meaning | Example |
|---|---|---|
| Service | Application unit deployed and managed together | `order-service` |
| Provider | Target cloud platform | `aws` |
| Function | An independently deployed unit of code | `createOrder`, `processOrder` |
| Event | Event that triggers a function | HTTP API, SQS, EventBridge |
| Resource | Declared infrastructure resource | DynamoDB table, SQS queue |
| Stage | Deployment environment | `dev`, `staging`, `prod` |
| Plugin | Extension to the Framework workflow | Local invoke or packaging plugin |

A service can contain multiple functions. Each function can have its own handler, memory, timeout, environment variables, and events. Functions can share resources such as a DynamoDB table or SQS queue declared in the same service.

### 1.3. Why Use Configuration Instead of Creating Resources Manually?

Declaring infrastructure via IaC enables:

- Reviewing infrastructure changes through pull requests and Git diffs.
- Recreating dev/test/prod environments with the same structure.
- Tracking relationships across functions, triggers, IAM, and resources.
- Reducing errors caused by inconsistent manual configuration.
- Auditing change history and reverting to earlier configuration versions easily.
- Automating deployments in CI/CD.

However, IaC configuration still requires design and testing. A syntactically valid YAML file can still grant overly broad permissions, wire wrong triggers, or exceed database capacity.

## 2. Java Project Structure with Serverless Framework

A simple Maven layout:

~~~text
order-service/
├── pom.xml
├── serverless.yml
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   ├── CreateOrderHandler.java
│                   └── ProcessOrderHandler.java
└── target/
    └── order-service-1.0.0.jar
~~~

`serverless.yml` sits at the service root directory. Java source is built with Maven. The resulting artifact is referenced from configuration so Serverless Framework includes it in the deployment package.

For Java on AWS Lambda, handlers typically implement `com.amazonaws.services.lambda.runtime.RequestHandler` or `RequestStreamHandler`. The AWS Lambda Java runtime invokes the handler according to the configured class name.

### 2.1. Dependencies for Java Handlers

Example minimal dependency in `pom.xml`:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-lambda-java-core</artifactId>
    <version>1.2.3</version>
  </dependency>
</dependencies>
~~~

The version here is illustrative. Pin a version verified to be compatible with the runtime and application libraries. Do not use floating versions in production pipelines.

An HTTP API handler can receive an event as a map and return a response matching the API Gateway HTTP API v2 payload format:

~~~java
package com.example;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.Map;
import java.util.Optional;

public final class HelloHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event,
            Context context) {

        Object rawQuery = event.get("queryStringParameters");
        String name = "world";

        if (rawQuery instanceof Map<?, ?> query) {
            name = Optional.ofNullable(query.get("name"))
                    .map(Object::toString)
                    .filter(value -> !value.isBlank())
                    .orElse("world");
        }

        return Map.of(
                "statusCode", 200,
                "headers", Map.of(
                        "content-type", "text/plain; charset=utf-8"),
                "isBase64Encoded", false,
                "body", "Hello " + name
        );
    }
}
~~~

This example illustrates an HTTP API response. In a real application, deserialize the request body into a DTO, validate inputs, authenticate the caller, and invoke an application service. Never treat client-supplied fields like `userId` or `tenantId` as authenticated identity.

### 2.2. Packaging Dependencies into the JAR

AWS Lambda requires runtime dependencies inside the deployment artifact. A common Maven approach uses the Maven Shade Plugin to build a JAR containing dependencies:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.0</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <createDependencyReducedPom>false</createDependencyReducedPom>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

After running `mvn clean package`, Maven produces a JAR bundled with dependencies. The filename depends on `artifactId` and `version` in the POM. Verify the exact path before configuring `package.artifact`.

If dependencies use the Java Service Provider Interface (SPI), some libraries may require merging service descriptors when shading. Check resources and metadata after packaging, especially when using the AWS SDK, logging backends, or drivers. A JAR can compile cleanly yet fail at runtime due to missing classes or resources.

## 3. The serverless.yml File

`serverless.yml` describes the service and related resources. Typical sections include:

- `service`: service name.
- `frameworkVersion`: required Serverless Framework version.
- `provider`: cloud provider and shared settings.
- `functions`: functions and event triggers.
- `resources`: additional CloudFormation resources.
- `plugins`: extension plugins.
- `package`: artifact packaging rules.
- `custom`: configuration for plugins or reusable expressions.

Minimal configuration example:

~~~yaml
service: order-service
frameworkVersion: '4'

provider:
  name: aws
  runtime: java21
  region: ap-southeast-1
  stage: dev
  memorySize: 512
  timeout: 15

package:
  artifact: target/order-service-1.0.0.jar

functions:
  hello:
    handler: com.example.HelloHandler
    events:
      - httpApi:
          method: GET
          path: /hello
~~~

This is an illustrative configuration. Before using it, ensure the Java runtime is supported by AWS Lambda at deployment time, the JAR exists at the specified path, and the handler class is inside the artifact.

### 3.1. Declaring Service and Provider

`service` names the deployment unit. This name is used in stack, resource, or artifact names according to Framework conventions.

`provider.name` identifies the target platform—`aws` in this lesson. `provider.runtime` sets the default runtime for functions unless overridden per function. `region` and `stage` determine the deployment location and environment.

Common shared settings:

~~~yaml
service: order-service
frameworkVersion: '4'

provider:
  name: aws
  runtime: java21
  region: ap-southeast-1
  stage: ${opt:stage, 'dev'}
  memorySize: 512
  timeout: 15
  architecture: arm64
  logRetentionInDays: 14
~~~

The `${opt:stage, 'dev'}` expression reads the `--stage` CLI option and defaults to `dev` if omitted. `architecture` can be `x86_64` or `arm64` depending on runtime and dependencies. If the JAR contains JNI or native binaries, build and test for the target architecture.

### 3.2. Function-Specific Configuration

Functions can override provider settings:

~~~yaml
functions:
  createOrder:
    handler: com.example.CreateOrderHandler
    memorySize: 1024
    timeout: 20
    events:
      - httpApi:
          method: POST
          path: /orders

  processOrder:
    handler: com.example.ProcessOrderHandler
    memorySize: 1536
    timeout: 60
    events:
      - sqs:
          arn:
            Fn::GetAtt:
              - OrdersQueue
              - Arn
          batchSize: 10
          functionResponseType: ReportBatchItemFailures
~~~

`createOrder` serves synchronous requests and needs a timeout aligned with client/API deadlines. `processOrder` processes messages and may need more time. `batchSize` controls how many messages arrive in a single batch; larger batches reduce overhead but increase memory usage, processing duration, and retry blast radius.

`functionResponseType: ReportBatchItemFailures` lets the handler report failed messages so the event source mapping retries only the failing items via partial batch response. The Java handler must return responses matching the AWS Lambda SQS event source mapping contract; setting the config alone without returning the matching response structure will not achieve the expected behavior.

## 4. Declaring Event Triggers

Events describe what causes a function to be invoked. Serverless Framework translates event declarations into the corresponding AWS integrations.

### 4.1. HTTP API

Example:

~~~yaml
functions:
  getOrder:
    handler: com.example.GetOrderHandler
    events:
      - httpApi:
          method: GET
          path: /orders/{orderId}

  createOrder:
    handler: com.example.CreateOrderHandler
    events:
      - httpApi:
          method: POST
          path: /orders
~~~

HTTP API fits REST endpoints and webhooks. The framework configures routes and API Gateway integration with Lambda. The handler must return responses matching the integration format, including status code, headers, and body.

Do not confuse `httpApi` with the `http` event of API Gateway REST API. They have different configuration, features, and payload contracts. Choose one API type deliberately and use the corresponding event shape in the Java handler.

### 4.2. SQS Queue

Queues decouple request ingestion from background processing:

~~~yaml
functions:
  processOrder:
    handler: com.example.ProcessOrderHandler
    timeout: 30
    events:
      - sqs:
          arn:
            Fn::GetAtt: [OrdersQueue, Arn]
          batchSize: 10
          maximumBatchingWindow: 5
          functionResponseType: ReportBatchItemFailures

resources:
  Resources:
    OrdersQueue:
      Type: AWS::SQS::Queue
      Properties:
        VisibilityTimeout: 185
~~~

Queue buffering absorbs traffic spikes. Lambda polls messages and invokes the worker via an event source mapping. Set the visibility timeout long enough so messages are not redelivered while a previous invocation is still running. AWS guidance generally recommends a visibility timeout of at least six times the function timeout, plus any batching window; verify current guidance and the actual event source mapping configuration.

When batching, one failing message can cause the whole batch to be redelivered unless partial batch response is enabled and handled properly. The handler must track each message and return the `batchItemFailures` list per the contract.

### 4.3. EventBridge Schedule

A function can run periodically using an EventBridge schedule:

~~~yaml
functions:
  dailySummary:
    handler: com.example.DailySummaryHandler
    timeout: 120
    events:
      - schedule:
          rate: cron(0 1 * * ? *)
          enabled: true
~~~

Traditional EventBridge schedule cron expressions evaluate in UTC. `cron(0 1 * * ? *)` means running at 01:00 UTC every day, not automatically in local time. If business requirements specify a local timezone, verify timezone support for the schedule type used or convert times accordingly.

### 4.4. EventBridge Event Pattern

A function can subscribe to events by source and detail type:

~~~yaml
functions:
  orderCreated:
    handler: com.example.OrderCreatedHandler
    events:
      - eventBridge:
          pattern:
            source:
              - com.example.orders
            detail-type:
              - OrderCreated
~~~

Event patterns filter events structurally. The handler still needs to validate the payload because events may lack fields or contain invalid data. Do not assume that arriving from EventBridge proves every value in `detail` is trustworthy.

### 4.5. S3 Event

You can subscribe a function to object-creation events in an existing bucket:

~~~yaml
functions:
  imageUploaded:
    handler: com.example.ImageUploadedHandler
    events:
      - s3:
          bucket: company-upload-bucket
          event: s3:ObjectCreated:*
          existing: true
~~~

`existing: true` is used when the bucket is managed outside this service. In that case, the deployment does not own the bucket's lifecycle. Ensure bucket notifications can be configured for the trigger and avoid multiple stacks overwriting the same bucket's notification configuration.

If Serverless Framework manages the bucket within the same stack, declare the resource explicitly and configure events according to documentation compatible with your Framework version. Watch out for circular dependencies between bucket notifications and Lambda invoke permissions.

## 5. Declaring Resources and IAM Permissions

A service often needs resources beyond Lambda, such as a DynamoDB table, SQS queue, S3 bucket, or EventBridge bus. Additional CloudFormation resources can be declared in the `resources` section.

### 5.1. Declaring a DynamoDB Table

Example:

~~~yaml
resources:
  Resources:
    OrdersTable:
      Type: AWS::DynamoDB::Table
      Properties:
        BillingMode: PAY_PER_REQUEST
        AttributeDefinitions:
          - AttributeName: orderId
            AttributeType: S
        KeySchema:
          - AttributeName: orderId
            KeyType: HASH
~~~

CloudFormation creates the table with the stack. `PAY_PER_REQUEST` fits variable workloads or unknown throughput; for steady workloads, evaluate provisioned capacity and autoscaling as needed.

Inside the function, the table name should be passed via an environment variable or CloudFormation reference rather than hardcoded. Example:

~~~yaml
provider:
  environment:
    ORDERS_TABLE:
      Ref: OrdersTable
~~~

In Java:

~~~java
String tableName = System.getenv("ORDERS_TABLE");
if (tableName == null || tableName.isBlank()) {
    throw new IllegalStateException("ORDERS_TABLE is not configured");
}
~~~

### 5.2. Granting Least-Privilege Permissions to Functions

Declaring a resource does not automatically grant functions access to it. The Lambda execution role requires the corresponding IAM permissions.

Example granting read/write item permissions on the specific table:

~~~yaml
provider:
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:UpdateItem
          Resource:
            Fn::GetAtt:
              - OrdersTable
              - Arn
~~~

Referencing the ARN from the resource avoids hardcoding account IDs or regions. If a function only needs to read, grant only `GetItem`; do not grant `Scan`, `DeleteItem`, or table admin actions unless required.

If functions have very different permission needs, consider per-function IAM roles rather than granting a broad set of permissions across the whole provider. Apply least-privilege permissions and review IAM diffs before deploying.

### 5.3. Declaring a Queue, Dead-Letter Queue, and Redrive

Example queue with a DLQ:

~~~yaml
resources:
  Resources:
    OrdersDeadLetterQueue:
      Type: AWS::SQS::Queue
      Properties:
        MessageRetentionPeriod: 1209600

    OrdersQueue:
      Type: AWS::SQS::Queue
      Properties:
        VisibilityTimeout: 185
        RedrivePolicy:
          deadLetterTargetArn:
            Fn::GetAtt:
              - OrdersDeadLetterQueue
              - Arn
          maxReceiveCount: 5
~~~

`maxReceiveCount` sets how many times a message is received before moving to the DLQ per the redrive policy. A DLQ isolates persistently failing messages for investigation and controlled reprocessing. Monitor DLQ message counts and define a replay procedure after fixing the root cause.

This example uses a 30-second function timeout and a 5-second batch window, so a 185-second visibility timeout matches six times the timeout plus the batch window. Adjust this according to your actual timeout and current AWS guidance.

### 5.4. Queue Read Permissions

If a function uses an SQS event source mapping, its execution role needs permissions to read and manage messages. Example:

~~~yaml
provider:
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - sqs:ReceiveMessage
            - sqs:DeleteMessage
            - sqs:GetQueueAttributes
            - sqs:ChangeMessageVisibility
          Resource:
            Fn::GetAtt:
              - OrdersQueue
              - Arn
~~~

Required permissions depend on the trigger and configuration. Do not grant `sqs:*` across all queues just to avoid permission errors. When using KMS encryption or custom queue policies, additional permissions may be needed for the relevant keys or principals.

## 6. Environment Variables and Stage Management

Stages separate deployment environments such as `dev`, `test`, `staging`, and `prod`. Each stage can use different resources, log retention, memory, concurrency, and dependency configurations.

### 6.1. Passing Stage into Configuration

A common approach:

~~~yaml
provider:
  stage: ${opt:stage, 'dev'}
  environment:
    APP_STAGE: ${sls:stage}
    LOG_LEVEL: info
~~~

Deploy the dev stage:

~~~bash
serverless deploy --stage dev
~~~

Deploy the production stage:

~~~bash
serverless deploy --stage prod
~~~

`${sls:stage}` resolves the stage determined by the Framework. `opt:stage` reads the CLI option. When using stage variables, include the stage in stack names and resource names so dev does not overwrite production or cause two environments to share resources unintentionally.

### 6.2. Stage-Specific Configuration

Pipelines can set different environment variables before running the deploy command. Example:

~~~yaml
provider:
  environment:
    APP_STAGE: ${sls:stage}
    ORDERS_TABLE: ${self:service}-${sls:stage}-orders
    LOG_LEVEL: ${env:LOG_LEVEL, 'info'}
~~~

CI can set `LOG_LEVEL=debug` for dev and `LOG_LEVEL=warn` for production. The Framework resolves variables at deploy time and writes the values into the Lambda configuration. Use this mechanism for non-sensitive settings; secrets should still be managed via Secrets Manager or Parameter Store.

### 6.3. Do Not Put Secrets Directly in serverless.yml

Never commit API keys, passwords, private keys, or credentials to Git. Use AWS Secrets Manager or Systems Manager Parameter Store to store secrets; grant read permissions to the appropriate execution role. You can reference values from secret sources using the Framework's variable syntax, but ensure secrets are never printed in logs, outputs, or package files.

Environment variables suit non-sensitive settings like table names, feature flags, or log levels. Secrets should have their own lifecycle, access controls, and rotation process.

## 7. Packaging and the Java Build Workflow

Serverless Framework needs a runtime-ready artifact. For Java, coordinate the Maven build with the `package` configuration.

### 7.1. Specifying the Artifact

Example:

~~~yaml
package:
  artifact: target/order-service-1.0.0.jar
~~~

When `package.artifact` is specified, the Framework uses the pre-built artifact at that path. Consequently, the pipeline must run Maven before running `serverless package` or `serverless deploy`.

Basic sequence:

~~~bash
mvn clean package
serverless package --stage dev
serverless deploy --stage dev
~~~

`serverless deploy` normally packages before deploying; a separate `serverless package` step is helpful for inspecting the package or saving artifacts for later pipeline stages.

### 7.2. Per-Function Packaging

If each function has a different artifact, you can use function-level packaging configuration or `package.individually` depending on how the service is structured. This reduces each function's artifact size, though it increases the number of packages to manage and requires the build pipeline to produce the right JAR per handler.

Do not enable individual packaging without a clear reason if all functions share a single JAR. Before deploying, verify each package contains the right handler class and required dependencies.

### 7.3. Optimizing Java Artifacts

Ways to reduce artifact size and startup time:

- Include only genuinely required dependencies in the runtime artifact.
- Avoid bundling multiple duplicate versions of the same library.
- Verify resources and service descriptors after Maven Shade.
- Use a Java runtime and architecture compatible with dependencies.
- Split functions along bounded contexts when dependencies and scaling targets differ.
- Avoid creating an oversized JAR simply by bundling an entire application into one function.

If a function uses the AWS SDK, prefer only the required SDK modules and verify version compatibility. Do not rely on the runtime already providing every SDK version the application needs.

## 8. Plugins and Custom Configuration

Plugins extend Serverless Framework behavior—for example, supporting local execution, packaging, validation, or deployment tool integration. Configure plugins under `plugins`:

~~~yaml
plugins:
  - serverless-offline
~~~

The `serverless-offline` plugin can emulate parts of an HTTP API on a developer machine. It is useful for quickly checking routes and handlers, but it does not fully emulate IAM, retries, concurrency, cold starts, API Gateway, or the behavior of all AWS services.

Only add plugins with a concrete need. Pin plugin versions, check compatibility with Serverless Framework and the Java runtime, and manage plugins in a lockfile or appropriate dependency workflow.

`custom` is a configuration block for plugin settings or values reused in the file. Do not place arbitrary business logic or secrets inside `custom`; settings should be clearly named and easy to review.

## 9. Inspecting Resolved Configuration and Packages Before Deploy

YAML can reference variables from the CLI, environment, provider, or CloudFormation. Before deploying, inspect the configuration after the Framework substitutes variables.

Print the resolved configuration:

~~~bash
serverless print --stage dev
~~~

Create the package without deploying:

~~~bash
serverless package --stage dev
~~~

These steps catch unresolved variables, wrong artifact paths, missing files, or invalid function/event configurations before modifying the AWS stack.

Do not expose `serverless print` output publicly if the resolved configuration contains sensitive values from the environment or secret sources. Restrict read access to package files and CI/CD logs.

## 10. Deploying and Managing the Service Lifecycle

Serverless Framework provides commands to inspect, package, deploy, invoke functions, and tail logs. Distinguish deploying the whole service from updating only one function's code.

### 10.1. Preparing the Environment

Before deploying:

1. Install Node.js and the Serverless Framework CLI at the version standardized by the organization.
2. Install the AWS CLI and configure the deployment identity.
3. Select the target AWS account, region, and stage.
4. Enable required AWS services/APIs if demanded by your process.
5. Verify IAM permissions for the deployer and the CloudFormation service role.
6. Build the Java artifact with Maven.
7. Inspect resolved configuration and packages before modifying the stack.

Never commit AWS access keys into the repository. For CI/CD, prefer short-lived identities via OIDC or role assumption. Separate deployment permissions from Lambda runtime permissions: the deployer needs permissions to create/update resources, whereas the runtime role only needs permissions used by the function while executing.

### 10.2. Deploying the Service

Example:

~~~bash
mvn clean package
serverless print --stage dev
serverless package --stage dev
serverless deploy --stage dev --region ap-southeast-1
~~~

The Framework creates or updates the CloudFormation stack for the service. After deploying, verify outputs and the created function URLs or API endpoints. Do not assume a successful deployment guarantees every dependency call works; run smoke tests through real triggers.

For production, deploy to a staging/test environment first, verify requests/events, logs, permissions, and load, and then deploy to production.

### 10.3. Updating a Single Function's Code

You can run:

~~~bash
serverless deploy function --function createOrder --stage dev
~~~

This command updates only the specified function's code and is suitable when changing code without modifying infrastructure configuration. If you change events, IAM, environment variables, memory, timeout, or resources, deploy the full service so CloudFormation stays up to date.

Do not use single-function deploys as a substitute for IaC management. If only AWS code changes while source/deployment state falls out of sync, subsequent deploys can produce hard-to-trace discrepancies.

### 10.4. Invoking Functions and Inspecting Info

Invoke a function directly:

~~~bash
serverless invoke --function createOrder --stage dev --data '{"queryStringParameters":{"name":"Lan"}}'
~~~

Inspect service info:

~~~bash
serverless info --stage dev
~~~

Tail function logs:

~~~bash
serverless logs --function createOrder --stage dev --tail
~~~

Direct invocation does not traverse the full HTTP API or event source mapping path. To verify real integration, call the API Gateway endpoint or emit messages/events from the actual source service.

### 10.5. Removing a Service

The command:

~~~bash
serverless remove --stage dev
~~~

instructs the Framework to remove the service's CloudFormation stack and stack-owned resources according to their deletion policies. This can be destructive if stateful resources are configured to delete with the stack. Before running it, check retention policies, snapshots/backups, resources holding data, and resources shared with other systems.

Do not use the remove command to clean up production environments. For databases, buckets, or queues containing critical data, design retention and backups from the moment resources are declared.

## 11. Retries, Idempotency, and Error Handling

Serverless Framework declares triggers and certain service policies, while error handling logic still belongs to the application. Each trigger has its own semantics.

### 11.1. HTTP API

HTTP APIs typically invoke Lambda synchronously. If a client times out or encounters a network error, it may not know whether the function completed side effects. Client retries can create duplicate operations.

For order-creation or payment endpoints:

- Accept an Idempotency-Key header from the client or derive a stable business key.
- Persist the key and result in a database with a unique constraint.
- If the same key arrives again, return the stored result instead of executing the business action again.
- Set dependency timeouts shorter than the Lambda timeout and client deadline.
- Distinguish authentication failures, input errors, conflicts, and server errors.

### 11.2. SQS and Batch Processing

An SQS event source mapping polls messages and sends batches to Lambda. If the handler fails, messages can reappear after the visibility timeout. If one message in a batch fails and the handler does not use partial batch responses, the entire batch may be retried.

Handlers should process each message independently and return failed message IDs when ReportBatchItemFailures is enabled. Every message needs a stable idempotency key so redelivered messages do not duplicate side effects.

For permanent data errors, establish a quarantine or DLQ policy with alerting. Never let poison messages retry indefinitely without visibility.

### 11.3. Asynchronous Invocation and EventBridge

For asynchronous Lambda invocations, Lambda retries certain function errors according to service configuration. EventBridge also has target retry policies and dead-letter queues. These mechanisms differ from SQS event source mappings.

When declaring a trigger, verify the retry policy on the specific source service. Do not assume an SQS retry setting automatically applies to EventBridge or async invocations.

### 11.4. Idempotency Keys in Java

Example of a handler deriving a key from an event ID or business key:

~~~java
String idempotencyKey = eventId + ":" + operationVersion;
~~~

This only constructs the key. To be effective, the application must persist the key durably with an atomic operation, check completion state, and coordinate recording the result with the business side effect. An in-JVM HashSet or static Map does not prevent duplicates across multiple Lambda instances or restarts.

If side effects happen in an external service, use an idempotency key supported by that service or an outbox/inbox and reconciliation workflow. Do not assume a timeout means the external call failed.

## 12. Concurrency, Memory, and Downstream Limits

A service declaration can create multiple Lambda functions, each scaling independently. Total load on a database or external API is the sum of concurrent invocations across all related instances and functions.

### 12.1. Concurrency Limits

You can cap concurrency for a function with the corresponding setting:

~~~yaml
functions:
  processOrder:
    handler: com.example.ProcessOrderHandler
    reservedConcurrency: 20
~~~

Reserved concurrency both caps concurrent executions and reserves that capacity for the function under Lambda's concurrency model. Setting it too low can throttle the function; setting it too high can overwhelm downstream systems.

For SQS, tune batch size and maximum concurrency on the event source mapping to match system capacity. Account for all queues, functions, and other producers hitting the same database.

### 12.2. Memory and Timeout

Memory configuration affects both RAM and Lambda CPU capacity. Increasing memory can shorten duration for CPU-intensive workloads while increasing the per-millisecond rate. Timeouts must align with p95/p99 latency and trigger/caller deadlines.

Example:

~~~yaml
functions:
  resizeImage:
    handler: com.example.ResizeImageHandler
    memorySize: 2048
    timeout: 90
    ephemeralStorageSize: 2048
~~~

This configuration illustrates an image-processing function that may need larger memory and /tmp storage. `ephemeralStorageSize` configures Lambda's temporary storage at /tmp; verify property support in your Serverless Framework version and runtime before deploying.

### 12.3. Sizing Capacity from Downstream Systems

Suppose each Lambda invocation opens up to 5 database connections and the function runs at concurrency 40. The database could receive around 200 connections from that function alone. If other functions or services share the database, total connections will be even higher.

Size pool sizes, reserved concurrency, event source maximum concurrency, and batch sizes based on actual downstream capacity. Raising concurrency will not increase useful throughput if the database is already the bottleneck.

## 13. Logging, Monitoring, and Cost

Serverless Framework can configure log retention and provision required resources, while operations still rely on CloudWatch metrics, dashboards, and alarms.

### 13.1. Logs and Metrics

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Invocation count | Number of times the function is invoked |
| Duration p50/p95/p99 | Execution duration by percentile |
| Errors | Count of failed invocations |
| Throttles | Count of invocations throttled by concurrency limits |
| Concurrent executions | Concurrent execution level |
| Iterator age or queue age | Event/queue processing lag |
| DLQ messages | Failed messages requiring investigation |
| Max memory used | Indicator of memory pressure |
| Downstream latency | Wait time on databases or APIs |

Logs should contain request ID, event ID, operation ID, and outcome codes for tracing. Never log credentials, tokens, or unnecessary personal data. For HTTP APIs, propagate a correlation ID end-to-end across client, API Gateway, Lambda, and dependencies.

### 13.2. Log Retention

Log retention can be configured at the provider level:

~~~yaml
provider:
  logRetentionInDays: 14
~~~

Choose retention based on investigation needs, security policies, and storage costs. Long-term logs can be exported to an appropriate archive store; avoid retaining logs indefinitely without a requirement.

### 13.3. Cost Drivers

Application cost goes beyond Lambda invocations:

- Lambda request counts and memory-weighted compute duration.
- API Gateway requests and data transfer.
- SQS requests, message retention, and DLQs.
- EventBridge events and rule invocations.
- DynamoDB reads/writes, storage, and backups.
- S3 storage, requests, and data transfer.
- CloudWatch log ingestion, retention, and metrics.
- NAT Gateway or network egress if used by the architecture.

A service with low invocation counts can still incur substantial cost from NAT Gateways, log volume, or always-on resources. During design, estimate cost per successful request/job and track spend by stage and tag.

## 14. CI/CD for Serverless Framework

CI/CD should reproduce the exact same build, package, validation, and deployment steps. Never rely on leftover JAR files from an earlier build on a developer's machine.

A simple pipeline:

~~~mermaid
flowchart TD
    A[Commit or pull request] --> B[Compile and unit test]
    B --> C[Maven package]
    C --> D[Validate serverless.yml]
    D --> E[Serverless package]
    E --> F[Review artifact/template]
    F --> G[Deploy test stage]
    G --> H[Smoke test and check logs]
    H --> I[Approval or policy gate]
    I --> J[Deploy production]
~~~

Typical steps include:

1. Check out source and install the exact Java/Maven/Node versions.
2. Run unit tests and static checks.
3. Build the JAR with dependencies.
4. Validate `serverless.yml` and resolved variables.
5. Generate the CloudFormation package and artifacts.
6. Store artifacts tagged by commit/version for traceability.
7. Deploy to the test stage.
8. Run smoke tests through HTTP APIs or event triggers.
9. Inspect logs, IAM diffs, error rates, and downstream behavior.
10. Deploy to production per organizational approvals and procedures.

In CI/CD, obtain AWS credentials via OIDC or role assumption with least privilege. Never store long-lived access keys in configuration files or pipeline logs.

### 14.1. Versioning and Rollback

Record code version, Maven artifact, Serverless Framework version, and deployment config under the same commit. When a deployment fails, you can redeploy a known-good artifact or restore the CloudFormation stack following your rollback procedure.

Code rollback does not necessarily reverse data changes already applied. For database schema, queue payload, or event contract changes, design backward compatibility and dedicated migrations. Do not treat CloudFormation rollback as a business-level undo mechanism.

## 15. Common Mistakes

- **Not building the JAR before deploying:** the Framework cannot find the declared artifact.
- **JAR missing dependencies:** the function compiles cleanly but throws ClassNotFoundException at runtime.
- **Wrong handler name:** the class does not exist or does not implement the expected interface.
- **Confusing HTTP API and REST API:** event payloads and integration contracts do not match.
- **Stage configurations sharing resources:** dev and prod accidentally write to the same table or bucket.
- **Overly broad IAM roles:** functions gain access to unnecessary resources.
- **Forgetting visibility timeout:** SQS redelivers messages while a prior invocation is still processing.
- **Missing idempotency:** retries create duplicate orders or side effects.
- **Omitting DLQs:** poison messages have nowhere to be isolated and investigated.
- **Using single-function deploy after infrastructure changes:** the CloudFormation stack is not updated with the new config.
- **Removing a stack without checking retention:** stateful resources may be deleted along with their data.
- **Assuming local emulators behave identically to AWS:** differences in IAM, event delivery, retries, and scaling only surface in the cloud.
- **Ignoring supporting service costs:** logs, networking, and databases can dominate total cost.

## 16. Pre-Production Deployment Checklist

- [ ] serverless.yml defines service, provider, stage, and runtime explicitly.
- [ ] Java handlers implement the proper AWS Lambda handler interfaces.
- [ ] Maven artifact includes all runtime dependencies at the expected path.
- [ ] Function/event mappings match payload contracts.
- [ ] HTTP endpoints have appropriate authentication/authorization.
- [ ] SQS/EventBridge retries and DLQs are defined.
- [ ] Handlers enforce idempotency for operations with side effects.
- [ ] IAM roles grant only least-privilege permissions.
- [ ] Environment variables contain no hardcoded secrets.
- [ ] Memory, timeout, and concurrency fit the workload.
- [ ] Visibility timeout aligns with function timeout and batch window.
- [ ] Resources use stage-specific names and appropriate retention policies.
- [ ] serverless print and serverless package succeed cleanly.
- [ ] Deployed to a test stage and smoke-tested through real triggers.
- [ ] Logs, metrics, dashboards, and alarms are in place.
- [ ] CI/CD uses short-lived deployment identities and archives artifacts by commit.
- [ ] Code rollback and data migration plans are prepared.

## 17. Self-Check

**Question 1.** What role does Serverless Framework play in a Java serverless application?

**Suggested Answer:** The Framework reads service, function, event, resource, and provider configuration; packages artifacts; and creates/updates a CloudFormation stack to provision AWS resources. Java logic still runs inside the Lambda runtime.

**Question 2.** Distinguish service, function, event, and resource.

**Suggested Answer:** A service is the deployment unit; a function is the code executed by Lambda; an event is the trigger invoking the function; a resource is an infrastructure component such as a queue, table, or bucket.

**Question 3.** Why must the Java JAR be built before running Serverless Framework deploy when using package.artifact?

**Suggested Answer:** The Framework uses the existing artifact at the declared path. If Maven has not produced the file or the JAR lacks dependencies, packaging/deployment fails or the function crashes at runtime.

**Question 4.** Why is serverless deploy function inappropriate after changing IAM or event triggers?

**Suggested Answer:** That command only updates a single function's code and does not synchronize infrastructure changes in CloudFormation. When configuration or resources change, deploy the whole service so the stack is updated.

**Question 5.** Why are separate stages and stage-scoped resource naming needed?

**Suggested Answer:** Stages isolate dev/test/prod. Stage-scoped resource names prevent environments from overwriting each other's data or sharing resources unintentionally.

**Scenario Exercise:** Design a Java service that receives orders via an HTTP API, writes orders to DynamoDB, and sends messages to SQS. Another worker processes messages and emits an OrderProcessed event to EventBridge. Declare functions, events, resources, environment variables, and IAM permissions in serverless.yml. Specify memory, timeout, batch size, visibility timeout, DLQ, and idempotency key. Propose commands to build, package, deploy to dev, and smoke test.

**Hint:** Split createOrder and processOrder into two functions. The HTTP handler validates input, generates a stable order ID, and writes data; after committing, publish the message or use an outbox to avoid losing messages between the two steps. The worker reads SQS batches, processes each message idempotently, and returns partial batch failures. Declare the DynamoDB table, SQS queue, DLQ, and EventBridge event bus/rule as needed. Grant PutItem to the producer, message read/delete permissions to the worker, and event publish permissions to the worker. Set visibility timeout to at least six times the timeout plus batch window per current AWS guidance. Run Maven package, inspect resolved configuration, package, deploy dev, then send an HTTP request and verify the item, message, event, and logs.

## Conclusion

Serverless Framework turns service configuration into serverless resources that can be deployed and managed as IaC. For Java, Maven builds the artifact while serverless.yml declares the provider, handlers, events, resources, IAM, stages, and packaging. A solid configuration accurately expresses trigger contracts, least-privilege permissions, retries/idempotency, concurrency limits, and data lifecycles. A stage-based workflow of build, print, package, deploy, and smoke testing catches issues before production. In operations, monitor Lambda alongside API Gateway, queues, databases, logs, and networking to control reliability and cost across the entire service.
