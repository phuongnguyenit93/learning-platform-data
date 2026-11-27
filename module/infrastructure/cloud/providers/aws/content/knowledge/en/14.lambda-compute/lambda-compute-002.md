# Lambda Runtimes, Handlers, and Deployment with ZIP or Container

## Learning Objectives

After this lesson, learners can:

- Explain **AWS Lambda**, **runtime**, **handler**, **event**, **context**, **execution environment**, and how Lambda initializes, executes, and reuses execution environments.
- Identify AWS-managed runtimes, custom runtimes, and the differences between **Java source code**, **compiled bytecode**, **dependency packaging**, and **deployment formats**.
- Write a Java handler using **RequestHandler** or **RequestStreamHandler**, configure the handler string properly, and distinguish direct invoke payloads from API Gateway, S3, and SQS events.
- Build and deploy **Java Lambda via JAR/ZIP**, handle classpath, Maven Shade, Lambda layers, size limits, and `ClassNotFoundException` errors.
- Build and deploy a **Lambda container image** from an AWS Java base image, using the Runtime Interface Client, ECR, the appropriate CPU architecture, and local testing.
- Choose between **ZIP and container** based on dependency complexity, artifact lifecycle, CI/CD workflow, package limits, and operational cost.
- Design **IAM execution role** permissions, resource-based permissions, AWS KMS, VPC, Secrets Manager, logging, and event access permissions.
- Manage **versions/aliases**, cold starts, memory/timeout, concurrency, error retries, idempotency, monitoring, resilience, and budgets.
- Diagnose Lambda failures to initialize, wrong handlers, inaccessible images, timeouts, out-of-memory errors, VPC connectivity issues, or missing AWS API permissions.

**Context:** This lesson belongs to the **Lambda Compute** chapter, module **CLOUD_PROVIDERS_AWS**. Within the AWS ecosystem of **Regions/AZs, IAM, VPC, EC2/ECS/EKS, S3, RDS, DynamoDB, SQS, API Gateway, and CloudWatch**, Lambda fits when you want to run event-driven logic without managing an always-on fleet of servers. The design goal is not merely to make the function run, but to make it **secure, observable, scalable, resilient, and cost-controlled**.

> **Scope:** This lesson uses a standard **AWS Lambda Event Function** with **Java 21**, deployed in two ways: JAR/ZIP and container image. Lambda has additional variants/compute modes over time; do not take a default quota of one model and generalize it to every Lambda mode. Examples use **illustrative** accounts, Regions, and ARNs; do not run them in production without review.

## 1. What Is AWS Lambda, and How Does It Differ from EC2/ECS?

**AWS Lambda** is an on-demand or event-driven code execution service. You provide the application artifact, runtime configuration, resources, IAM role, trigger sources, and limits. AWS manages most of the execution infrastructure and provisions additional **execution environments** to handle rising request volume within quota/configuration limits.

Example e-commerce system:

1. A user places an order via an API.
2. The application publishes an `OrderCreated` event to **Amazon SQS**.
3. Lambda receives a batch of messages and generates a PDF invoice or writes aggregated data.
4. Results are stored in **S3** and status is recorded in **DynamoDB/RDS**.
5. CloudWatch records metrics, logs, and alarms; errors are retried or sent to a DLQ per the event source mechanism.

~~~mermaid
flowchart LR
    Client[User] --> API[API Gateway / application]
    API --> Queue[(Amazon SQS)]
    Queue --> ESM[Event source mapping]
    ESM --> Lambda[Lambda function: Java handler]
    Lambda --> S3[(S3: invoices)]
    Lambda --> DB[(DynamoDB / RDS)]
    Lambda --> Logs[CloudWatch]
~~~

| Solution | What you manage | Best-suited operating pattern |
| --- | --- | --- |
| **EC2** | OS, patching, services/processes, machine capacity, and deployments | Long-running applications, custom host requirements |
| **ECS/EKS** | Images, services/tasks/Pods, networking/capacity depending on model | Continuous web/API/microservices, container orchestration |
| **Lambda** | Code, dependencies, runtime/config, IAM, and application behavior | Events, short jobs, bursty APIs, asynchronous processing |
| **Step Functions** | Workflows and orchestration state | Multi-step flows, retries/timeouts/compensation; can invoke Lambda |

**Lambda is not a container service running an HTTP server forever.** You provide a **handler**, and Lambda calls that handler when an event arrives. Even a Lambda container image must adhere to the **Lambda Runtime API**; you cannot simply drop in an arbitrary Docker image of a web server and expect it to work.

Lambda is especially useful for tasks that do not need dedicated servers, but you must account for **timeout, memory, concurrency, cold starts, request volume, networking, and cost**. Very long-running tasks, long-lived connections, specialized GPUs/hosts, or large datasets requiring dedicated attached filesystems may fit ECS, Batch, or other solutions better.

## 2. Runtime: The Layer Delivering Events to Application Code

The **runtime** is the software layer providing the language environment and communication between Lambda's execution system and your handler. The runtime receives the event/context, invokes the matching code, and sends the response or error back to Lambda.

### 2.1. Managed Runtimes

AWS maintains official runtimes for Java, Python, Node.js, .NET, and other published languages. When using **ZIP/JAR**, you pick a **runtime identifier** in the function configuration, for example:

| Java Runtime | Current identifier | Key note |
| --- | --- | --- |
| Java 25 | `java25` | Newer runtime on Amazon Linux 2023 |
| Java 21 | `java21` | Runtime used in this lesson's examples |
| Java 17 on AL2023 | `java17.al2023` | Distinct from `java17` on Amazon Linux 2 |
| Java 11 on AL2023 | `java11.al2023` | Suitable when Java cannot yet be upgraded |
| AL2-generation Java 17 | `java17` | Older runtime; check the specific deprecation schedule |

Supported runtimes and deprecation schedules change over time. Before using one, check the **Lambda runtimes** documentation, Region availability, and support window; do not pick an outdated runtime simply because a Maven project currently builds for that Java version.

**The runtime and compiler must be compatible.** For example, compiling Java 25 bytecode and running it on a Java 21 runtime can cause `UnsupportedClassVersionError`. When an application builds for Java 21, select the Java 21 runtime or an environment whose bytecode and dependencies have been tested.

### 2.2. Custom Runtimes

For languages or versions without a suitable managed runtime, you can use an **OS-only runtime** such as `provided.al2023` and implement calls to the **Lambda Runtime API**, typically through a **runtime interface client**. This offers greater flexibility at the cost of increased maintenance, security, and compatibility responsibility.

### 2.3. Runtimes in Container Images

With a **container image**, the runtime and handler usually reside inside the **image** (or are set via image configuration overrides). When creating an image-based function, you **do not supply `--runtime java21` and `--handler ...` as with ZIP functions**. The AWS Java Lambda base image already includes the runtime and Runtime Interface Client.

**Update responsibilities differ:**

- **ZIP + managed runtime:** Lambda manages and patches the runtime under runtime management policies, though you still must update dependencies and SDKs in your artifact.
- **Container image:** you control the image and must **rebuild, scan, push, and redeploy** whenever the base image or libraries need patches, even when starting from an AWS official base image.
- **Custom runtime:** you bear greater responsibility for runtime bootstrapping and integration layers.

## 3. Handler: The Entry Point for Event Processing

The **handler** is the function/method Lambda invokes on each call. Depending on the language, the handler receives the input event and context per the runtime. Java typically uses a class and method.

Java handler format:

~~~text
com.example.lambda.OrderHandler::handleRequest
        └── class name ┘    └── method name
~~~

**Common points of confusion:**

- `OrderHandler` is the **Java class**, not the JAR filename or Lambda function name.
- `handleRequest` must have a compatible signature; the method can be defined via a supported interface.
- `com.example.lambda` is the exact package; a single-character typo will fail class loading or method lookup.
- Lambda function `orders-zip-lab` is the AWS resource name, **not** the handler class.

### Two Standard Java Interfaces

AWS provides the `com.amazonaws.services.lambda.runtime` package:

| Interface | Input/output | When to use |
| --- | --- | --- |
| **`RequestHandler<I,O>`** | Java object input and output; runtime handles serialization/deserialization | Simple JSON events and responses, typed DTOs/records |
| **`RequestStreamHandler`** | `InputStream` and `OutputStream` | Manual byte stream handling, custom serialization |
| **Method without interface** | Compatible signature, typically taking input + optional `Context` | Simple handlers, still requires exact method naming |

**The interface checks types/signatures at compile time**, while whether the incoming event JSON matches your expected structure still requires testing. S3, SQS, and API Gateway events have different structures; do not assume every input is a flat `{"orderId": "..."}` object.

## 4. Writing a Complete Java RequestHandler

To keep focus on the runtime, this example uses a **direct invocation event**:

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND"
}
~~~

File `src/main/java/com/example/lambda/OrderHandler.java`:

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.Map;
import java.util.Objects;

public class OrderHandler implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    // Lambda may retain this instance for subsequent invocations.
    // Only hold shared state/objects when thread-safe and valid.
    public OrderHandler() {
    }

    @Override
    public Map<String, Object> handleRequest(Map<String, Object> event, Context context) {
        String orderId = Objects.toString(event.get("orderId"), "").trim();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }

        String currency = Objects.toString(event.getOrDefault("currency", "VND"));

        // Log only non-secret data; never log raw sensitive payloads.
        context.getLogger().log("Accepted order: " + orderId);

        return Map.of(
            "orderId", orderId,
            "currency", currency,
            "accepted", true
        );
    }
}
~~~

**Key points:**

- `RequestHandler<Map<String,Object>, Map<String,Object>>` lets the runtime deserialize the incoming JSON object into a `Map` and serialize the return value back to JSON.
- `Context` provides the request ID, remaining time, logger API, and invocation metadata; do not use `Context` to store secrets.
- `IllegalArgumentException` indicates a **function error** on invalid input. With asynchronous invocations, errors can be retried, so distinguish permanent data errors from transient failures.
- The constructor and initialization outside the handler may run during the **Init** phase; the **handler** runs during **Invoke**.
- This example does not write to a DB or S3 yet, so it does not require S3/KMS/DB permissions. Once you add API calls, grant the execution role permissions scoped to the actual resources.

### Why Not Read Every Event as `Map<String,String>` Across All Triggers?

For many events, the JSON contains nested maps, arrays, booleans, numbers, base64 payloads, or metadata. `Map<String,Object>` or typed event classes preserve structure far better. The `aws-lambda-java-events` library provides event DTOs for API Gateway, S3, or SQS; be sure to pick the exact trigger type and version.

**Do not confuse a direct invoke payload with an API Gateway event.** If API Gateway proxy integration passes `body` as a JSON string alongside headers and request context, code reading `event.get("orderId")` at the root will not find the expected data. You must parse `body` or use an appropriate adapter/framework.

## 5. RequestStreamHandler: When You Need Full Serialization Control

With `RequestStreamHandler`, Lambda gives you raw byte streams:

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class EchoStreamHandler implements RequestStreamHandler {

    @Override
    public void handleRequest(
        InputStream input,
        OutputStream output,
        Context context
    ) throws IOException {
        byte[] eventBytes = input.readAllBytes();

        // Example: reads the raw JSON event and echoes it as the JSON response.
        // Stream demonstration only; do not echo sensitive data in production.
        output.write(eventBytes);
        output.flush();
    }
}
~~~

Handler configuration:

~~~text
com.example.lambda.EchoStreamHandler::handleRequest
~~~

Stream handlers are useful when you want to pick your own parser or codec, avoid relying heavily on the runtime's default mapping, or handle custom data contracts. However, `readAllBytes()` **loads the entire event into RAM**, which is not appropriate for streaming large payloads in production. Lambda invocations remain subject to event payload size limits; to process large files, typically pass an **S3 object key** and stream the object via the SDK.

## 6. Event Sources and Invocation Types: What Data Does the Handler Receive?

A function can be invoked by many services. Distinguish **direct/synchronous invoke**, **asynchronous invoke**, and **event source mapping (poll-based)**:

| Source | Common flow | Payload/conditions | Error handling |
| --- | --- | --- | --- |
| **AWS CLI/SDK Invoke** | Synchronous `RequestResponse` or asynchronous `Event` | Client-supplied payload | Sync: inspect response/`FunctionError`; Async: retry/destination per policy |
| **API Gateway** | Synchronous | Event with headers, path, method, body, and context per integration | Response contract, timeout, HTTP status codes, integration errors |
| **Lambda Function URL** | Synchronous HTTP | HTTP event per payload format | IAM/NONE authorization, CORS, and corresponding HTTP response |
| **Amazon S3 notifications** | Asynchronous | Event with bucket/key/records | May arrive duplicated or out of order; must be idempotent |
| **EventBridge** | Asynchronous | Event with `source`, `detail-type`, `detail` | Retries and DLQ/destinations per service configuration |
| **SQS** | Event source mapping polls queue | Batch `Records` with receipt handle and message body | Batch/message retries, visibility timeout, DLQ |
| **Kinesis/DynamoDB Streams** | Event source mapping reads shards | Stream/batch records | Checkpointing, retries, ordering/bisect, or partial batch as supported |

**Key difference:** When API Gateway calls Lambda synchronously, a handler error can map to an HTTP error; with **SQS**, Lambda polls a batch of records and must handle success/failure cleanly to avoid duplicate processing or infinite loops. There is no single retry mechanism shared across all triggers.

Example SQS event (abbreviated):

~~~json
{
  "Records": [
    {
      "messageId": "m-123",
      "body": "{\"orderId\":\"ORD-1001\"}",
      "eventSource": "aws:sqs"
    }
  ]
}
~~~

If a Java handler expects `orderId` directly at the root, it will fail. With SQS, parse `Records[i].body` and process each message; combine **idempotency keys**, partial batch responses where supported, and proper DLQ/alerting.

## 7. Lambda Execution Environment and the Init / Invoke Lifecycle

To process events, Lambda allocates an **execution environment** containing the runtime, function code, and configured resources. Environments can be **reused** across multiple invocations, though AWS **does not guarantee the same instance stays alive forever**.

~~~mermaid
flowchart TD
    A[Event arrives at Lambda] --> B{Ready environment available?}
    B -->|No| C[Init: load runtime, code, dependencies]
    C --> D[Init handler class / static resources]
    B -->|Yes| E[Warm invoke]
    D --> F[Invoke handler]
    E --> F
    F --> G[Return / error / timeout]
    G --> H{Reusable?}
    H -->|Yes| I[Environment temporarily retained]
    I --> E
    H -->|No| J[Environment discarded]
~~~

### Init

Lambda prepares the runtime, loads code/dependencies, and executes initialization defined outside the handler. In Java, JVM startup, class loading, dependency injection, and static initialization can lengthen **cold starts**.

Best practices:

- Trim unnecessary dependencies/JARs;
- avoid booting an entire web server when only handling a simple event;
- create reusable AWS SDK clients/HTTP connection pools at instance/static scope when thread-safe;
- avoid heavy migrations or network calls without timeouts inside static initializers;
- set sensible timeouts and log init phases when relevant.

### Invoke

Lambda invokes the handler with the event. An environment in the standard Lambda Event Function model **does not process multiple invocations concurrently inside the same execution environment**, though the application itself may spawn background threads or async operations; you must manage thread safety and clean up resources properly.

### Freeze / Reuse

After invoke, Lambda may freeze and later reuse the execution environment. Static variables and `/tmp` contents **may remain**, but must never be treated as a durable database or shared state across environments.

**Do not store shopping carts, user sessions, or sole transaction results in Lambda RAM.** For durable state, use S3/DynamoDB/RDS/ElastiCache as appropriate.

### SnapStart and Provisioned Concurrency

For supported runtimes/configurations, **Lambda SnapStart** can reduce init time by saving and restoring the initialized state of a published version. Applications must ensure **uniqueness of secrets/random state, valid network connections, and state refreshed after restore**; an initialization snapshot is not a per-transaction checkpoint.

**Provisioned concurrency** keeps a set of initialized environments ready, reducing cold-start impact for provisioned traffic, at an additional cost and managed per alias/version. **SnapStart does not support all runtimes, package types, or configurations**; notably, it does not apply by default to Lambda container images.

## 8. ZIP and Container Image: The Two Primary Packaging Formats

AWS Lambda supports two package types for functions:

| Criterion | **ZIP/JAR** | **Container image** |
| --- | --- | --- |
| How runtime is defined | Select a managed/custom runtime identifier in config | Runtime/RIC lives inside the image |
| Artifact | ZIP or Java JAR, dependencies/layers | Linux OCI/Docker-compatible image |
| Maximum size | **50 MB zipped for direct upload**, **250 MB unzipped** including layers/custom runtime | **10 GB** unzipped image across all layers |
| Storage when deploying | Direct upload or fetched from S3 in the same Region | **Amazon ECR in the same Region** as the function |
| Lambda Layers | **Supported**, within limits | **Lambda layers not supported** like ZIP; bundle dependencies in the image |
| OS/dependency management | AWS-managed runtime; dependencies packaged by you | You choose base image/OS and rebuild for patches |
| Deployment tooling | CLI, Console, SAM, CloudFormation, CDK | Docker build + ECR + CLI/IaC |
| Minimal operations | Usually simpler for typical Java code/dependencies | Good fit for native libs, custom toolchains, existing Docker pipelines |
| Switch ZIP ↔ image on the same function | **Not allowed** | Must create a new function and migrate triggers/routing |

**The 250 MB limit** counts the **entire unzipped package plus all layers**, not 250 MB per layer. For ZIP files over 50 MB compressed that still fit within the unzipped limit, deploy through **S3 in the same Region**.

**The 10 GB container image limit** is a technical ceiling, not a recommendation. Oversized images still hurt build/push/scan times, security posture, and cold-start/operational behavior. Do not switch to containers just to avoid trimming unused dependencies.

### Why Can't PackageType Be Changed In-Place?

A function created with ZIP cannot be updated in-place with an ECR image as the same resource, and vice versa. To migrate package types:

1. Create a new function with the new package type.
2. Configure matching IAM role, VPC, env vars, KMS, timeout, memory, and triggers.
3. Test via integration aliases/routing where supported.
4. Cut over event sources, APIs, mappings, and permissions in a controlled manner.
5. Monitor errors/latency/retries before deleting the old function.

**Changing the artifact changes more than compression**: handler bootstrapping, runtime patching, IAM, and CI/CD pipelines also change.

## 9. Preparing a Java Lambda Project with Maven

Example using Java 21, Maven, and AWS Lambda Java Core.

Directory layout:

~~~text
order-lambda/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/lambda/
    │           └── OrderHandler.java
    └── test/
        └── java/  (unit tests, if present)
~~~

Minimal `pom.xml` for a **JAR with bundled dependencies**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-lambda</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.amazonaws</groupId>
      <artifactId>aws-lambda-java-core</artifactId>
      <version>1.2.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
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
          </execution>
        </executions>
        <configuration>
          <createDependencyReducedPom>false</createDependencyReducedPom>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Understanding dependencies:** `aws-lambda-java-core` provides `RequestHandler`, `RequestStreamHandler`, and `Context`. When handling SQS/S3/API Gateway typed events, add `aws-lambda-java-events`. When calling AWS S3 or DynamoDB, add the required **AWS SDK for Java v2** modules and manage versions with an appropriate BOM.

**Do not pick an arbitrary SDK version without compatibility testing.** Versions in this example illustrate Maven configuration; in production, use dependency management with CVE scanning, reproducible builds, and integration tests.

### Build the JAR

~~~bash
mvn -DskipTests=false clean package
~~~

The shaded artifact is typically produced at:

~~~text
target/order-lambda-1.0.0.jar
~~~

You can inspect classes/packages with the Java CLI tool:

~~~bash
jar tf target/order-lambda-1.0.0.jar
~~~

Look for `com/example/lambda/OrderHandler.class` and required dependency classes. If a build produces only a thin JAR without dependencies, Lambda may throw `NoClassDefFoundError` when those dependencies are missing at runtime.

### Shaded JAR, ZIP with `lib/`, and Java Classes

AWS Lambda Java also supports a ZIP layout containing JAR files under `lib/` on the classpath. **Maven Shade** builds a fat/uber JAR convenient for small examples; a **Gradle Zip task** can place the application JAR and runtime dependencies inside `lib/`.

**Packaging warning:** Some Java dependencies rely on `META-INF/services`, service loaders, Log4j2 plugin caches, Spring resource merging, or multi-release JARs. Shading without merging required metadata/service files can compile cleanly yet fail at runtime. Choose transformers matching your libraries and test the final packaged artifact rather than only running code in an IDE.

## 10. Deploying ZIP/JAR to Lambda with AWS CLI

> **Prerequisites:** Lab machine has JDK 21, Maven, and AWS CLI v2 installed; AWS credentials use SSO/roles/profiles rather than hardcoded access keys. You have IAM permissions to create/deploy Lambda and **`iam:PassRole`** for the execution role. Lab exercises incur invocation/log charges and potentially auxiliary resource costs.

### 10.1. Execution Role and Trust Policy

A Lambda function requires an **execution role**. Trust policy allowing the Lambda service to assume the role:

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

Assume the JSON is saved in lab file `lambda-trust.json`. With IAM permissions, you can create the role:

~~~bash
aws iam create-role \
  --role-name order-lambda-execution-lab \
  --assume-role-policy-document file://lambda-trust.json \
  --profile lab

aws iam attach-role-policy \
  --role-name order-lambda-execution-lab \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile lab
~~~

`AWSLambdaBasicExecutionRole` grants **basic CloudWatch Logs** permissions; it does not grant S3 read or DB access. If the function needs `s3:PutObject`, `dynamodb:PutItem`, or Secrets Manager, attach an identity policy scoped to the exact resource ARNs. Wait for IAM role/permission propagation before creating/invoking the function.

### 10.2. Create a ZIP-Based Function

~~~bash
aws sts get-caller-identity --profile lab

aws lambda create-function \
  --function-name orders-zip-lab \
  --package-type Zip \
  --runtime java21 \
  --handler com.example.lambda.OrderHandler::handleRequest \
  --role arn:aws:iam::111122223333:role/order-lambda-execution-lab \
  --architectures x86_64 \
  --memory-size 512 \
  --timeout 15 \
  --zip-file fileb://target/order-lambda-1.0.0.jar \
  --region ap-southeast-1 \
  --profile lab
~~~

ARNs and names are illustrative. If the function already exists, **`create-function` cannot be used to update code**; use `update-function-code` and `update-function-configuration` as needed.

### 10.3. Invoke a Test Event from a File

Create `event.json`:

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND"
}
~~~

Invoke directly:

~~~bash
aws lambda invoke \
  --function-name orders-zip-lab \
  --invocation-type RequestResponse \
  --payload fileb://event.json \
  --log-type Tail \
  --region ap-southeast-1 \
  --profile lab \
  response.json
~~~

Expected `response.json` (on success):

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND",
  "accepted": true
}
~~~

Inspecting CLI response metadata:

- `StatusCode=200` on a synchronous invoke **does not automatically prove the handler succeeded**. If `FunctionError` is present, the handler failed and the payload usually contains error details.
- `LogResult` is a base64-encoded log snippet returned when log tailing is requested and supported by the API.
- View complete logs in CloudWatch Logs group `/aws/lambda/orders-zip-lab`.

### 10.4. Update the ZIP Artifact

After modifying code and rebuilding:

~~~bash
mvn clean package

aws lambda update-function-code \
  --function-name orders-zip-lab \
  --zip-file fileb://target/order-lambda-1.0.0.jar \
  --region ap-southeast-1 \
  --profile lab

aws lambda wait function-updated \
  --function-name orders-zip-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

**Do not publish an old version before the update completes.** For rollback-ready releases, publish a **version** once code and configuration are ready, then point a production alias at it (see Section 16).

### 10.5. ZIPs Larger Than 50 MB

If the ZIP exceeds the direct upload limit while its unzipped contents stay within the 250 MB quota:

1. Upload the artifact to an **S3 bucket in the same Region**;
2. Deploy Lambda using `--code S3Bucket=...,S3Key=...` on creation or the corresponding S3 parameters on update;
3. Use object versioning/checksums and tight S3 access controls for immutable artifacts.

**You cannot bypass the 250 MB unzipped limit simply by uploading via S3.** When exceeding that quota, trim dependencies, split out layers (which still count toward the total limit), or evaluate container images where justified.

## 11. Lambda Layers with Java ZIP

A **Lambda layer** is an auxiliary artifact containing shared libraries, a custom runtime, or shared resources. When a ZIP function runs, layers are mounted into the environment at Lambda-defined paths.

For Java, reference layer layout:

~~~text
my-java-dependencies-layer.zip
└── java/
    └── lib/
        ├── dependency-one.jar
        └── dependency-two.jar
~~~

Java libraries in the layer are added to the classpath by Lambda's supported mechanism. Avoid placing JARs at the root of the ZIP when the runtime expects `java/lib`.

### When to Use Layers?

- Multiple ZIP functions share a large library with a relatively independent release lifecycle.
- You want to separate heavy packages from handler code for cleaner artifact management.
- Supporting custom runtimes or auxiliary extensions.

### Limits and Risks

- Each function can use up to **5 layers** under standard limits.
- The **total unzipped size** of the function package plus all layers still shares the combined limit (250 MB for standard ZIP functions).
- Layer references bind to a specific layer version; publishing a new layer version **does not automatically update functions pointing to an older version**.
- Duplicate packages/versions across layers and function code can trigger `ClassNotFoundException`, `NoSuchMethodError`, or `ServiceConfigurationError`.
- **Lambda container images do not support Lambda layers**: dependencies belong inside the image.

**Lesson:** Extracting layers does not automatically shrink cold starts or reduce total cost. Always measure artifact size, init latency, and real versioning operations.

## 12. Container Images for Lambda: How Do They Differ from ECS Containers?

A Lambda container image still runs inside the **Lambda execution model**, not as a long-running Docker daemon listening for HTTP on an arbitrary port. The image must implement the **Lambda Runtime API**.

### Three Image Options

1. **AWS Lambda language base images:** include the runtime (e.g., Java 21), Runtime Interface Client (**RIC**), and Runtime Interface Emulator (**RIE**) for local testing.
2. **AWS OS-only base images:** contain Amazon Linux and base tools; you add the runtime and compatible interface client.
3. **Custom base images (Debian/Alpine, etc.):** must include RIC or directly implement the Runtime API; verify OS and library compatibility.

### Key Requirements

- Images must be **Linux**; each Lambda image function targets a **single CPU architecture** (`x86_64` or `arm64`) — do not push a multi-architecture manifest expecting Lambda to pick one.
- The root filesystem operates **read-only**; the default writable directory is `/tmp`, configurable from **512 MB to 10,240 MB** within quota.
- AWS Lambda runs the image as a **least-privileged user**; code should not require `root` or write to `/var/task` or `/opt`.
- Maximum image size is **10 GB uncompressed**, including all layers; keep it much smaller whenever possible.
- Images must reside in **Amazon ECR in the same AWS Region** as the function; cross-account repositories are supported with proper ECR policies.
- Lambda does not support pulling images via ECR FIPS endpoints per AWS-documented limitations.
- **You must rebuild/push/redeploy** when updating the base image; overwriting an ECR tag **does not automatically update** the image digest resolved by an existing function.

## 13. Java 21 Dockerfile for Lambda

Using the same `OrderHandler` from Section 4, packaged into a container image.

### 13.1. Prepare Compiled Classes and Dependencies

Inside the Maven project directory:

~~~bash
mvn clean compile dependency:copy-dependencies -DincludeScope=runtime
~~~

Expected output:

~~~text
target/
├── classes/
│   └── com/example/lambda/OrderHandler.class
└── dependency/
    ├── aws-lambda-java-core-*.jar
    └── ... other dependencies ...
~~~

If your plugin setup outputs dependencies to a different folder, adjust the Dockerfile to match. Compilation must succeed before building the container; do not copy `.java` source files into the runtime image expecting Lambda to compile them.

### 13.2. Dockerfile Based on the Official Base Image

File `Dockerfile`:

~~~dockerfile
FROM public.ecr.aws/lambda/java:21

# LAMBDA_TASK_ROOT in the AWS Java base image maps to /var/task.
COPY target/classes/ /var/task/
COPY target/dependency/ /var/task/lib/

# Java handler uses package.Class::method.
CMD ["com.example.lambda.OrderHandler::handleRequest"]
~~~

**Why use this base image?**

- Includes the matching Java runtime and Runtime Interface Client.
- Knows how to pull events from the Lambda Runtime API.
- Includes the Runtime Interface Emulator for local testing.
- Eliminates writing your own bootstrap loop polling `/runtime/invocation/next`.

If using a non-Lambda base image, you must supply a compatible runtime interface client and entrypoint. A typical Java image that runs `java -jar app.jar` continuously is not automatically a valid Lambda image.

### 13.3. Build the Image for the Target Architecture

Example building a **linux/amd64** image for an `x86_64` function:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --load \
  -t orders-lambda:1.0.0 \
  .
~~~

AWS recommends `--provenance=false` in Lambda-compatible image build examples to prevent incompatible manifest/metadata formats. For ARM, choose `linux/arm64` alongside Lambda architecture `arm64`, ensuring native libraries match.

**There is no need to configure `EXPOSE 8080` to expose Lambda over public HTTP**: port 8080 in the base image/RIE is used for local invocation testing, not to turn the function into an ECS web server.

## 14. Testing the Lambda Container Locally

With AWS Java Lambda base images, RIE enables local invocation testing.

Start the container:

~~~bash
docker run --rm -p 9000:8080 orders-lambda:1.0.0
~~~

In another terminal:

~~~bash
curl -X POST \
  "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-1001","currency":"VND"}'
~~~

Expected JSON output contains `accepted: true`.

**Limitations of local testing:**

- RIE emulates part of the invoke protocol; it **does not fully replicate** IAM, VPC/ENIs, service limits, KMS, concurrency, or all behaviors of the AWS Lambda runtime.
- If the function calls the AWS SDK, provide local credentials via secure development mechanisms; never bake secrets into the image or `Dockerfile`.
- Java unit tests and integration tests in a real lab environment remain mandatory before release.
- On Windows/ARM laptops, double-check target image architecture and builder settings; Docker Desktop is a local tool, while the AWS function must declare the matching architecture.

## 15. Pushing the Image to Amazon ECR and Creating the Lambda Function

### 15.1. Create the Repository in the Right Region

~~~bash
aws ecr create-repository \
  --repository-name orders-lambda \
  --image-scanning-configuration scanOnPush=true \
  --region ap-southeast-1 \
  --profile lab
~~~

If the repository already exists, confirm its URI and policies instead of creating a duplicate.

### 15.2. Log Docker Into ECR

~~~bash
aws ecr get-login-password \
  --region ap-southeast-1 --profile lab \
  | docker login \
      --username AWS \
      --password-stdin 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

This is a **temporary ECR authentication token**, not a static secret to store in source control. Never log the `docker login` token or embed AWS access keys inside the image.

### 15.3. Tag and Push

~~~bash
docker tag orders-lambda:1.0.0 \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0

docker push \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0
~~~

### 15.4. Create the Function from the Image

~~~bash
aws lambda create-function \
  --function-name orders-image-lab \
  --package-type Image \
  --code ImageUri=111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0 \
  --role arn:aws:iam::111122223333:role/order-lambda-execution-lab \
  --architectures x86_64 \
  --memory-size 512 \
  --timeout 15 \
  --region ap-southeast-1 \
  --profile lab
~~~

**Note:** For package type `Image`, do not pass `--runtime java21`, `--handler ...`, or `--zip-file` to `create-function`. The handler comes from the image `CMD` (or image configuration override), and the runtime resides inside the image.

### 15.5. Invoke and Update the Image

Invoking works just like the ZIP function, only with the new function name:

~~~bash
aws lambda invoke \
  --function-name orders-image-lab \
  --payload fileb://event.json \
  --region ap-southeast-1 \
  --profile lab \
  image-response.json
~~~

When pushing a new `1.0.1` image:

~~~bash
aws lambda update-function-code \
  --function-name orders-image-lab \
  --image-uri 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.1 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lambda **resolves the image tag to a digest** when updating code. Simply **re-pushing the same tag name to ECR** does not make an existing function switch to the new digest. Best practice is to use **immutable image tags or SHA digests** and roll out versions/aliases through a tracked pipeline.

### 15.6. Cross-Account ECR Images

A function in Account B can use an ECR image in Account A **in the same Region** when:

- The principal creating/updating the function has the required ECR permissions per the API;
- the **ECR repository policy** allows the Lambda service and appropriate account/principal to read the image across operational phases;
- the image and repository still exist and have not had the referenced digest purged by lifecycle policies.

**Do not equate an ECS task execution role with a Lambda execution role.** Lambda's permission to pull an image from ECR and your application code's permission to call S3 are two separate layers; check AWS's rules for **ECR repository permissions for Lambda**.

## 16. Versions, Aliases, and Safe Releases

Lambda provides **`$LATEST`**, **published versions**, and **aliases**.

- **`$LATEST`:** the working draft whose code and configuration can be updated.
- **Published version:** an immutable snapshot of most code and configuration at publish time; most attributes are locked against direct edits.
- **Alias:** a logical name like `dev`, `staging`, or `prod` pointing to a published version; can also be used for canary rollouts where supported.

~~~mermaid
flowchart LR
    CI[CI/CD build artifact] --> Latest[Lambda $LATEST]
    Latest --> V7[Published version 7]
    Latest --> V8[Published version 8]
    Alias[Alias prod] -->|90%| V7
    Alias -->|10%| V8
    Client[API Gateway / EventBridge / SDK] --> Alias
~~~

**Example: publish a version and create an alias:**

~~~bash
aws lambda publish-version \
  --function-name orders-zip-lab \
  --description "release-1.0.0" \
  --region ap-southeast-1 \
  --profile lab

aws lambda create-alias \
  --function-name orders-zip-lab \
  --name prod \
  --function-version 1 \
  --region ap-southeast-1 \
  --profile lab
~~~

**`--function-version 1` is only an example**; use the actual version ID returned by `publish-version`. If the function already has prior published versions, the new version will not be `1`.

Release workflow:

1. Update `$LATEST`, wait for the update status to finish, and run integration tests.
2. Publish a new version.
3. Update the `prod` alias to the new version or configure a **weighted alias** to split traffic between two published versions where supported.
4. Monitor error rate, latency, cold starts, dependencies, and business metrics.
5. On error, point the alias back to the known-good version while handling retried events and idempotency.

**Note:** Rolling back an alias **does not automatically undo** S3 or DB writes performed by the faulty version. Safe rollbacks require versioned schemas, idempotency, and a data remediation plan.

## 17. IAM: Two Very Easily Confused Permission Types

### 17.1. Execution Role: What Can the Function Do?

When Lambda runs the handler, the code receives temporary credentials from the **execution role**. That role's IAM policy determines which AWS APIs the function can call.

Example role that only needs to write `invoices/*` objects to S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteInvoices",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::orders-invoices-example/invoices/*"
    }
  ]
}
~~~

If the bucket uses **SSE-KMS**, also account for `kms:GenerateDataKey` with a customer-managed key and the **KMS key policy** as appropriate. When reading SSE-KMS objects, `kms:Decrypt` is usually required.

### 17.2. Resource-Based Policy: Who Can Invoke the Function?

API Gateway, EventBridge, or S3 triggers may need a **resource-based permission** on Lambda allowing that service to invoke the function. That is a distinct layer from the execution role.

| Question | Where it is controlled |
| --- | --- |
| Can S3/EventBridge **invoke Lambda**? | Lambda resource-based policy / event source permissions per integration |
| Can Lambda code **write S3 objects**? | Execution role, bucket policy, KMS policy |
| Who can **deploy/update the function**? | Identity policy, `iam:PassRole`, SCP/permissions boundaries, and related policies |
| Who can read **runtime secrets**? | Execution role + secret resource policy + KMS |
| Can the function reach **private RDS**? | VPC routes/SGs/DNS **and** DB auth, not IAM alone |

### 17.3. Trust Policy and PassRole

The execution role trusts `lambda.amazonaws.com`. The deploying principal may require `iam:PassRole` to attach that role to the function. Having `lambda:CreateFunction` **does not automatically grant permission to pass any role**.

**Security guideline:** Never embed AWS access keys in code, images, environment variables, or JARs. Prefer temporary IAM role credentials, least-privilege IAM conditions, Secrets Manager, encryption, and CloudTrail auditing.

## 18. Environment Variables, Secrets Manager, KMS, and Filesystem

### Environment Variables

You can declare `APP_ENV`, `TABLE_NAME`, or `LOG_LEVEL` in the function configuration. Environment variables are encrypted at rest by AWS per Lambda/KMS mechanics, but:

- Env vars **are not the right place for passwords/tokens**, especially if multiple users can inspect function configuration.
- Total environment variable size has a quota (typically **4 KB** in Lambda Event Functions).
- Updating env vars on `$LATEST` modifies the function config; older published versions retain their configuration snapshot.
- When using a customer-managed KMS key, IAM and key policies for administration and configuration access may need review.

### Secrets

For database passwords and API tokens, use **AWS Secrets Manager** or SSM Parameter Store as appropriate. Code fetches secrets via the SDK when needed and can safely cache them in the execution environment for an appropriate window.

Never log secrets, put secrets in Dockerfile `ENV` instructions, commit secrets to Git, or bake them into image layers (even if deleted in a later layer, earlier layers persist).

### Filesystem

- **Code/package root** is read-only at runtime; do not write business data into source or library directories.
- **`/tmp`** is a writable scratch area configurable from **512 to 10,240 MB** within supported limits.
- Data in `/tmp` may persist when an environment is reused, but persistence is **not guaranteed**.
- For a shared POSIX filesystem, you can integrate **Amazon EFS** when the function is configured with VPC/Access Points as required.
- For objects like invoices or images, **S3** is usually simpler than a shared filesystem.
- For structured data, use **RDS/Aurora/DynamoDB** or an equivalent datastore; never treat local `/tmp` as a persistent DB.

## 19. VPC: Connecting to Private RDS Is Not Automatic

A standard Lambda function does not need to be placed inside your VPC just to call AWS public endpoints allowed by IAM. However, if it needs to access **private RDS/private endpoints/EC2 inside a VPC**, you must configure **Lambda VPC networking** appropriately.

~~~mermaid
flowchart LR
    Event[SQS / API Gateway / EventBridge] --> Lambda[Lambda function]
    subgraph VPC["Application VPC"]
      SG[Lambda SG / private subnets] --> DB[(Private RDS)]
      SG --> Endpoint[VPC endpoints / NAT route]
    end
    Lambda --> SG
    Endpoint --> S3[S3 / Secrets Manager / AWS services]
~~~

**Checklist:**

1. Select appropriate subnets across **multiple AZs** if the application requires high availability, plus a security group for Lambda.
2. Allow outbound traffic to the required DB port, e.g., TCP/5432; allow inbound on the DB SG from the Lambda SG.
3. Ensure working DNS resolution/routing to private endpoints.
4. If the function calls public Internet endpoints, provide an appropriate NAT/egress path. **Attaching Lambda to a public subnet does not give the function a public IPv4 address or Internet access**.
5. When using VPC endpoints, verify private DNS, endpoint SGs, endpoint policies, and IAM.
6. The execution role needs the VPC/network-interface permissions specified by AWS guidelines. Do not grant full EC2 admin permissions unnecessarily.

**ZIP/container pitfall:** When Lambda deploys a **container image**, pulling the ECR image is handled by the Lambda service control plane — **it does not mean the function's VPC runtime needs NAT solely for ECR to pull the image at startup**. Only runtime code that itself calls ECR/S3/Secrets Manager requires the corresponding network path and IAM permissions.

### Cold Starts and VPC

VPC configuration can affect initialization/network behavior, but do not assume cold-start figures from older VPC architectures still apply. With Hyperplane ENIs and the current platform, benchmark against your actual subnets/SGs, load, runtime, and integrations. A timeout caused by a missing SG rule or route is a **connectivity error**, not proof of a JVM cold start.

## 20. Timeout, Memory, Concurrency, and Java Optimization

### 20.1. Timeout and Memory

Common limits for standard Lambda Event Functions:

| Attribute | Range/limit per AWS documentation | Impact |
| --- | --- | --- |
| **Timeout** | Up to **900 seconds (15 minutes)** for standard Event Functions | Handlers exceeding the limit are terminated; requires retry/idempotency |
| **Memory** | **128–10,240 MB** | CPU power scales with memory; not just RAM |
| **Temporary storage** | **512–10,240 MB** in `/tmp` | Scratch space, temp files, native libs needing writable paths |
| **Synchronous invocation payload** | Payload/request-response quotas per mode, e.g., **6 MB** for standard sync | Pass S3 keys for large files instead of embedding files in events |
| **Concurrency** | Account/Region limits and function-specific quotas | Throttling under load spikes; requires capping/coordination |

Newer Lambda modes may have different quotas or behavior; check the current **Lambda quotas** table for your exact function type.

### 20.2. Increasing Memory Can Make Functions Faster

Lambda allocates CPU proportionally to memory. A CPU-bound Java function can run dramatically faster when bumped from 512 MB to 1,024 or 2,048 MB. Because billing depends on memory and execution duration, higher RAM **can cut duration enough that total cost does not increase proportionally**, though you must benchmark.

### 20.3. Concurrency and Little's Law

Approximation rule for steady traffic:

\[
\text{Concurrency} \approx \text{Requests/second} \times \text{Duration (seconds)}
\]

For example, 300 RPS with 0.2 seconds average duration:

\[
300 \times 0.2 = 60\ \text{concurrent invocations}
\]

If duration climbs to 2 seconds due to a slow DB:

\[
300 \times 2 = 600\ \text{concurrent invocations}
\]

**Adding concurrency rarely solves a DB bottleneck**; Lambda may open even more DB connections and overload downstream systems.

### Reserved Concurrency and Provisioned Concurrency

| Type | Meaning | When to use |
| --- | --- | --- |
| **Reserved concurrency** | Caps/guarantees dedicated concurrency quota for a function per config | Prevent a function from overwhelming downstream systems, reserve capacity |
| **Provisioned concurrency** | Pre-initializes execution environments for a version/alias | Reduce cold starts on latency-sensitive traffic, incurs additional cost |
| **Event source maximum concurrency** | Concurrency limit/control on supported mappings or sources | Throttle SQS/stream consumers and protect downstream services |
| **Account concurrency quota** | Account/Region ceiling or configured quotas | Ensure headroom for other functions |

**Reserved concurrency = 0** can be used to temporarily block invocations in specific situations, but its operational impact is severe; never apply it in production without a change plan.

### Java Startup/Cold Start

Key optimizations:

- Keep the handler lean, reduce classpath size and beans/services created during init;
- stay on supported JDK/runtime versions, consider `arm64` architecture when dependencies are compatible and gains are measured;
- use singleton/reusable SDK clients with configured timeouts;
- avoid synchronous remote calls in static initializers;
- evaluate **SnapStart** or **provisioned concurrency** on eligible configurations;
- run Lambda Power Tuning/benchmarks with real data and compare p95/p99;
- inspect CPU, memory, GC, and I/O; do not blame every timeout on “Java cold start.”

## 21. Retries, DLQ, Idempotency, and Data Protection

Lambda can be invoked more than once due to event source retries, client retries, or failures between writing data and acknowledgment. **“At-least-once”** is an important practical reality for S3/SQS/EventBridge: code must be **idempotent**.

### Example: Duplicate Invoice Processing Bug

1. Lambda receives `OrderCreated: ORD-1001`.
2. Lambda writes `invoices/ORD-1001.pdf` to S3.
3. The handler times out **before the SQS batch is acknowledged**.
4. The SQS message is redelivered to Lambda.
5. Without checking `orderId`, the handler may generate the invoice twice, overwrite files, or send duplicate emails.

**Mitigation:**

- Use a stable idempotency key such as `orderId` or `eventId`;
- persist processing state in DynamoDB/DB using conditional writes or transactions;
- isolate external side effects and retries by design;
- configure DLQs, `maxReceiveCount`/visibility timeouts, and failure destinations per event source;
- handle partial failures in SQS batches where supported to avoid retrying already-succeeded messages;
- monitor retry/error/DLQ backlogs and configure alarms.

### There Is No Single Universal DLQ Across All Invocation Types

- **Asynchronous invocation** has Lambda-level retry settings, max event age, and destinations/DLQ.
- **SQS event source mapping** pulls from a queue, and errors make messages visible again after the visibility timeout; the **SQS queue's redrive policy/DLQ** governs dead-lettering.
- **Kinesis/DynamoDB Streams** follow event source mapping checkpoint/ordering/batch retry rules; do not extrapolate from SQS.
- **Synchronous APIs** return errors to the caller; clients/upstream services decide retries independently.

**Handlers must recognize the event type before deciding whether to throw an exception, return a response, or ack a batch.** Returning `{"accepted":false}` does not mean every event source will treat it as a failure.

## 22. Monitoring: Proving the Function Works Well

Combine **CloudWatch Logs**, **CloudWatch Metrics**, **X-Ray/traces**, and logs from calling systems.

| Metric/component | Question answered | When to alert |
| --- | --- | --- |
| `Invocations` | How many times was Lambda invoked? | Unexpected spikes or missing expected traffic |
| `Errors` | Are the handler/runtime failing? | Error rate breaches SLO |
| `Duration` | Processing time (p95/p99) | Approaching timeout, rising latency |
| `Throttles` | Is concurrency being throttled? | Sustained throttling and growing backlog |
| `ConcurrentExecutions` | Current concurrency usage | Approaching reserved/account quota |
| `IteratorAge` or mapping metrics | Are stream/batch consumers falling behind? | Rising backlog/lag |
| `DeadLetterErrors` / destination failures | Are failed events failing to reach the DLQ/destination? | Loss of ability to store/diagnose failed events |
| `Init Duration` in logs/reports/telemetry | How costly is cold start/init? | Init latency jumps after dependency updates |
| `Max Memory Used` in REPORT logs | Peak memory vs configured limit | Near OOM or excessive memory over-provisioning |
| S3/SQS/RDS/KMS metrics | Are downstream services slow or throttled? | Dependency bottlenecks causing timeouts |

### Viewing Logs via CLI

~~~bash
aws logs tail /aws/lambda/orders-zip-lab \
  --since 30m \
  --follow \
  --region ap-southeast-1 \
  --profile lab
~~~

For the image function, the log group matches function name `orders-image-lab`. The log group must be created/writable and the role must have Logs permissions; if init fails very early, expected stack traces may be missing.

### Structured Logging and Correlation IDs

In Java applications, emit structured JSON logs such as:

~~~json
{
  "level": "INFO",
  "service": "orders-invoice",
  "requestId": "aws-request-id-example",
  "orderId": "ORD-1001",
  "stage": "invoice-generated",
  "durationMs": 123
}
~~~

Avoid logging passwords, bearer tokens, PII objects, full request bodies, credentials, or sensitive connection strings. Propagate correlation IDs from API/SQS to connect traces across services. Consider **AWS Lambda Powertools for Java** and AWS X-Ray/OpenTelemetry according to system capabilities and policies.

### Do Not Confuse Deployment Success with Request Success

`LastUpdateStatus=Successful` only means the code/config update was accepted and applied. A function can update cleanly yet fail on invocation with `FunctionError=Unhandled`, time out, hit KMS `AccessDenied`, or return a response violating its contract. **Always test real invocations and business behavior.**

## 23. Security, Reliability, and Cost Across the Architecture

### 23.1. Security

- Use a **least-privilege** execution role, separating deploy roles, `iam:PassRole`, function resource policies, and data IAM/KMS permissions.
- Keep secrets out of ZIP/JARs, Docker images, plaintext ENV vars, and logs. Use Secrets Manager/SSM + customer-managed keys when required.
- Scan dependencies and images for CVEs; track runtime deprecations and updates.
- Enforce TLS for APIs, appropriate AuthN/AuthZ on API Gateway/Function URLs, and WAF/rate limiting where needed.
- When using VPCs, grant minimal subnet/SG/endpoint permissions.
- Use CloudTrail to audit code updates, configuration changes, IAM policies, and trigger permissions.

### 23.2. Resilience

- Lambda is **Regional** and executed by AWS across Regional infrastructure, though application HA also depends on VPC subnet selection and backend systems.
- With single-AZ RDS, Lambda auto-scaling does not turn the database into Multi-AZ.
- S3/DB writes require retries and idempotency; configure backup/versioning/replication per RPO/RTO.
- For cross-Region DR, deploy functions, artifacts, triggers, roles, KMS keys, and data in the backup Region and test routing — never assume code exists automatically in another Region.
- If a single event takes longer than 15 minutes, consider Step Functions, ECS/Fargate, Batch, or splitting the job into appropriate steps.

### 23.3. Cost: Account for Everything Beyond the Function

Total cost typically comprises:

1. **Request/invocation counts**;
2. **Compute GB-seconds** based on memory and duration in the applicable pricing model;
3. **Provisioned concurrency/SnapStart or feature charges** where applicable;
4. **Ephemeral storage beyond the standard free allocation**, plus streaming/network per pricing schedules;
5. **CloudWatch Logs/Metrics/X-Ray**;
6. **ECR image storage/scanning**, S3 artifacts/layers, NAT Gateways/VPC endpoints, and data transfer;
7. **SQS/S3/DynamoDB/RDS/KMS** calls made by the handler.

Rough compute formula for an On-Demand Event Function:

\[
\text{GB-seconds} \approx
\text{invocations} \times
\frac{\text{memory (MB)}}{1024}\times
\text{billed duration (seconds)}
\]

Example with **1,000,000 invocations**, **512 MB**, **0.2 seconds**:

\[
1{,}000{,}000\times 0.5\times 0.2
=100{,}000\ \text{GB-seconds}
\]

This is a **simplified estimate**, excluding free tier, duration rounding, init/snapshot fees, request pricing, provisioned concurrency, or newer pricing modes. Use **AWS Pricing Calculator / Cost Explorer / AWS Budgets** for your specific Region and function type.

**Cost takeaway:** There is no universal rule that ZIP or container image is “always cheaper per invoke.” Package type primarily changes artifact workflows, dependency/runtime management, and ECR/CI costs; compute billing still depends on memory, duration, concurrency, and configuration.

## 24. Troubleshooting: From Build to Invocation

| Symptom | Possible cause | Right way to investigate |
| --- | --- | --- |
| `ClassNotFoundException` or `HandlerNotFound` | Wrong package/class, handler string, missing class in artifact | Compare `--handler`, `jar tf`, source package, and build output |
| `NoClassDefFoundError` | Dependency missing from JAR/ZIP or wrong layer path | Check Shade config, `lib/`, layer `java/lib`, dependency versions |
| `UnsupportedClassVersionError` | Compiled bytecode newer than active runtime | Check `maven.compiler.release`, Java runtime ID, base image Java version |
| `ExceptionInInitializerError` | Static initializer failed, DB/secret call in init, missing env | Check CloudWatch init logs, static fields, timeouts, IAM/network |
| `Task timed out after ...` | Slow DB/API, broken network path, unbounded retries, low memory/CPU | Check Duration, DNS/VPC/SG, SDK timeouts, DB metrics, and code |
| `Runtime.OutOfMemory` or OOM | Memory configured too low, loading huge payloads/files into heap | Check REPORT Max Memory Used, JVM heap settings, file streaming |
| ZIP fails with `RequestEntityTooLargeException` | Direct upload >50 MB or unzipped exceeds quota | Check ZIP/JAR size, S3 deployment, trim dependencies, 250 MB limit |
| Cannot create function from image | Wrong ECR Region, missing repo policy, bad manifest/architecture | Check ECR URI/Region, Lambda permissions, image digest, `docker buildx` |
| `Runtime.InvalidEntrypoint` / image startup failure | ENTRYPOINT/CMD not implementing Lambda Runtime API, broken native binary | Check Dockerfile, RIC, handler string, local RIE logs |
| Works in local Docker but fails on AWS | RIE does not fully emulate IAM/VPC/KMS/platform | Test on AWS, check CloudWatch, SGs, image architecture, IAM |
| Container cannot write files | Read-only root filesystem, insufficient user permissions | Write only to `/tmp`, fix file permissions, avoid needing root |
| `AccessDenied` calling S3/KMS | Role missing `s3:...`, `kms:...`, explicit Deny in bucket/key policy | Check caller identity via SDK/logs, IAM/S3/KMS policies |
| Cannot reach private RDS | Lambda not in VPC, wrong subnet/SG/route/DNS | Check VPC config, DB SG, DNS resolver, TCP connectivity, CloudWatch logs |
| Cannot reach Internet after attaching VPC | Private subnet lacks NAT/appropriate endpoint | Check route tables, SGs, NACLs, NAT/endpoints, DNS |
| API Gateway returns 502 despite invoke success | Handler response violates proxy integration format | Verify event contract and response headers/statusCode/body |
| SQS message processed twice | Retries, batch failure, visibility timeout, non-idempotent handler | Check event source mapping, DLQ, message ID, idempotency store |
| Image tag updated but old code still runs | Lambda resolves tag to digest at deploy time | Run `update-function-code` with new URI, verify `get-function` and version logs |
| Cannot publish version | No changes since previous version or update still in progress | Check `LastUpdateStatus`, code SHA/digest, deployment state |
| Logs missing | Basic execution role/CloudWatch Logs permissions missing, early runtime crash | Check role, log group, init errors, CloudTrail, Logs retention |
| Costs rising rapidly | Higher memory/duration, retry loops, provisioned concurrency, NAT/logs | Check Cost Explorer, invocation/error/concurrency metrics, budgets |

### Step-by-Step Investigation Procedure

~~~text
1. Identify account, Region, function name, package type, and alias/version.
2. Inspect GetFunction/GetFunctionConfiguration:
   runtime/handler or ImageUri, role, memory, timeout, architecture, VPC.
3. Check LastUpdateStatus, State, and artifact (JAR classes / ECR digest).
4. Invoke with a contract-compliant event; inspect CLI FunctionError and payload.
5. Read CloudWatch Logs, INIT/REPORT lines, stack traces, memory/timeout.
6. If service access fails: inspect IAM execution role + S3/KMS/secret/DB policies.
7. If connectivity fails: inspect VPC subnets, SGs, routes, DNS, NAT/endpoints, DB SG.
8. If trigger fails: check invoke type, retries, DLQ, event source mapping,
   calling service permissions, and idempotency.
9. Apply the smallest fix, build/deploy a new revision, test canary/rollback.
10. Monitor errors/latency/cost and document the root cause.
~~~

**Never “fix” errors by** attaching `AdministratorAccess` to the Lambda role, opening a DB SG to `0.0.0.0/0`, baking access keys into images, or removing retries/idempotency. Those shortcuts destroy data protection and mask the root cause.

## 25. Reference Architecture: Order Invoicing with Java Lambda

Problem: an e-commerce platform must generate PDF invoices, store them in S3, and send notifications after orders are placed.

~~~mermaid
flowchart TB
    User[Customer] --> API[API Gateway + Auth]
    API --> Order[Order API / Lambda or ECS]
    Order --> DB[(RDS / DynamoDB: order)]
    Order --> Q[(SQS: OrderCreated)]
    Q --> Map[Lambda event source mapping]
    Map --> Handler[Lambda Java OrderInvoiceHandler]
    Handler --> S3[(S3 invoices / SSE-KMS)]
    Handler --> Audit[(DynamoDB: idempotency)]
    Handler --> Email[SES / notification]
    Handler --> CW[CloudWatch Logs/Metrics]
    Q --> DLQ[(SQS DLQ)]
    S3 --> Backup[Versioning / lifecycle / backup]
~~~

### Layer-by-Layer Design

- **Event:** SQS record contains `orderId`/metadata; do not pass entire PDFs or passwords inside the event.
- **Handler:** reads `Records`, validates input, uses idempotency key `orderId`, fetches order data, generates the PDF, and writes to S3.
- **Artifact:** Java 21 ZIP if dependencies are moderate; container image if native PDF rendering tools or specific vetted fonts/binaries are required.
- **IAM:** separate task/API/handler roles; handler has SQS permissions per integration, `s3:PutObject` on the invoice prefix, `kms:GenerateDataKey`, and required DB/DynamoDB permissions.
- **VPC:** attach the function to a VPC only if accessing a private DB or private resources; manage NAT/VPC endpoints for S3/Secrets Manager.
- **Data:** S3 SSE-KMS, versioning/retention, DLQ/retries, DB backups, and idempotency store.
- **Monitoring:** CloudWatch Errors/Duration/Throttles, SQS queue age, DLQ count, S3/KMS access errors, and business rate of completed invoices.
- **Availability:** Multi-AZ for DB/queue per AWS features, sufficient bounded concurrency, DLQ replay procedure, and recovery testing.
- **Cost:** event volume, PDF generation duration, memory/CPU, KMS API calls, S3 requests, logs, and NAT/ECR storage depending on package type.

**Practical boundary:** If PDF generation exceeds timeout/memory limits or requires very heavy binaries, use **Step Functions + ECS Fargate/AWS Batch** rather than forcing everything into a single Lambda.

## 26. Applied Exercises

### Exercise 1 — Reading Runtime and Handler Correctly

**Prompt:** Function `orders-zip-lab` uses `runtime=java21` and handler config `com.example.lambda.Handler::handleRequest`, yet the JAR contains `com/example/lambda/OrderHandler.class` implementing `RequestHandler`.

1. Predict the error type on invocation.
2. State the correct handler configuration.
3. Show how to verify the JAR with `jar tf` and Lambda logs.
4. Explain the difference between the Lambda function name and the Java class name.

**Hint:** The runtime must locate the exact class and method loadable from the classpath.

### Exercise 2 — Choosing ZIP vs. Container Image

**Requirements:**

- Function A: receives small JSON payloads, uses AWS SDK, runs in under 1 second, built with Java 21 Maven.
- Function B: generates thumbnails needing native libraries installed in the OS image, with an existing controlled Docker/ECR pipeline.
- Function C: app unpacks to 300 MB due to heavy dependencies and team wants to upload via S3 and deploy as ZIP.
- Function D: team wants to convert an existing ZIP-deployed function into an image in-place on the same function resource.

**Expected:** Prefer ZIP for A; evaluate image for B; for C, S3 upload **does not bypass** the 250 MB limit — trim artifacts or use an image; for D, a new function must be created.

### Exercise 3 — Execution Role vs. Trigger Permissions

An S3 event notification invokes Lambda `invoice-processor`. The event arrives, but the function reports `AccessDenied` when writing an object to another bucket.

Distinguish:

- Who has permission to invoke Lambda?
- Does the execution role have `s3:PutObject` and `kms:GenerateDataKey`?
- Does the bucket policy or KMS key policy deny access or lack an allow statement?
- Why does adding `lambda:InvokeFunction` to the execution role fail to fix S3 write permissions?

### Exercise 4 — Calculating Concurrency and Downstream Capacity

An API reaches **500 RPS**, with each invocation taking **0.4 seconds**:

\[
\text{Concurrency} \approx 500 \times 0.4 = 200
\]

If RDS only supports 100 concurrent connections in its current configuration, why can setting reserved concurrency to 500 cause an outage? Propose connection pooling/RDS Proxy, caching, queuing, or query optimization, and identify which metrics to monitor.

### Exercise 5 — CI/CD and Rollback Design

An image-based function uses tag `v1`; the team pushes a new image under the **same tag** and believes production has updated.

Explain:

1. When does Lambda resolve an image tag to a digest?
2. Why is overwriting the tag insufficient for production to run new code?
3. Steps to build, scan, push immutable artifacts, update code, publish a version, and shift an alias.
4. How to roll back an alias when `Errors` or p95 latency rises.
5. Why rolling back does not undo S3 objects or DB records written by the faulty release.

### Exercise 6 — Java Cold Starts and Timeouts

A Java Lambda has a 2-second cold start, 0.3-second business logic, 512 MB memory, and a 3-second timeout; occasionally a DB call takes 2 seconds.

Do the following:

- distinguish init latency from handler duration;
- propose benchmarking higher memory, init optimization, SDK timeouts, and DB performance;
- evaluate SnapStart or provisioned concurrency if eligible;
- explain why merely raising the timeout can increase concurrency and cost.

### Exercise 7 — Retries and Idempotency

SQS delivers 10 messages per batch. Lambda writes invoices for 9 messages and then throws an exception on the 10th message.

**Task:** Explain the risk of reprocessing the first 9 messages, propose using partial batch responses where supported, idempotency keys/conditional writes, and DLQ handling. Contrast this with API Gateway synchronous invocation.

## 27. Pre-Production Deployment Checklist

- [ ] Confirmed Lambda is a good fit for the workload's runtime duration, memory, event model, and latency sensitivity.
- [ ] Verified the runtime is still supported, Java bytecode version matches, and architecture is appropriate.
- [ ] Handler class/method/signature are exact; tested with trigger-accurate events rather than only direct invocations.
- [ ] Chose ZIP vs. Image intentionally; aware that package type cannot be switched in-place on the same function.
- [ ] For ZIP: built artifact with dependencies, verified classpath, compressed/unzipped sizes, layers, and S3 Region where applicable.
- [ ] For Image: single-arch Linux, proper RIC/runtime, ECR in same Region/with proper policy, immutable digest, writes only to `/tmp`.
- [ ] No passwords/access keys in JAR/image/ENV/logs; secrets and KMS are properly managed.
- [ ] Least-privilege execution role, resource-based policy restricted to valid invoke sources; deployer has minimal `iam:PassRole`.
- [ ] VPC config applied only when needed, with matching subnets/SGs/routes/DNS/NAT/endpoints and verified DB/service connectivity.
- [ ] Memory, CPU, timeout, and `/tmp` sized from benchmarks rather than defaults alone.
- [ ] Evaluated concurrency/quotas, reserved/provisioned concurrency, and downstream load capacity.
- [ ] When using S3/SQS/EventBridge, designed retries, idempotency, failure destinations/DLQs, and alerts.
- [ ] CloudWatch logs/metrics, structured tracing, error rates, p95/p99, throttles, and cost tracking are in place.
- [ ] Each release uses versioned artifacts/versions/aliases, integration tests, canary/rollback, and backward-compatible data.
- [ ] Runtime/image dependencies are scanned/patched, with retention policies cleaning old ECR images/ZIP layers without breaking published versions.
- [ ] Backups/DR exist for S3/DB and business recovery is tested; Lambda scaling does not replace database HA.
- [ ] Invocations, GB-seconds, ECR, logs, NAT, KMS, and downstream services have clear budgets and tags.

## 28. Summary

The **AWS Lambda runtime** is the environment that receives events and invokes your application; the **handler** is the entry point whose class/method/signature must match; **ZIP/JAR and container images** are two distinct deployment formats, each with its own responsibilities, limits, and pipeline.

With **Java 21**, a foundational workflow is: **write `RequestHandler` → build shaded JAR → create execution role → deploy ZIP → invoke and inspect CloudWatch Logs**. When native dependencies or Docker ecosystems are needed, you can: **build a Lambda-compatible image → test with RIE → push to ECR in the same Region → deploy an Image function → invoke and monitor**.

Remember that **a successful deployment does not equal a healthy application**. Bringing Lambda into a real AWS architecture requires integrating **IAM/KMS, Regions/AZs, VPC, S3/SQS/RDS/DynamoDB, monitoring, retries/idempotency, concurrency, backups, and budgets**. That is how serverless workloads stay secure, resilient, and aligned with user demand.

### Official References

- [AWS Lambda runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html)
- [Building Lambda functions with Java](https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html)
- [Define Lambda handler in Java](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html)
- [Deploy Java functions with ZIP/JAR](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html)
- [Working with layers for Java](https://docs.aws.amazon.com/lambda/latest/dg/java-layers.html)
- [Deploy Java Lambda with container images](https://docs.aws.amazon.com/lambda/latest/dg/java-image.html)
- [Create a Lambda function using a container image](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [Lambda quotas and deployment limits](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Lambda execution environment lifecycle](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)
- [Manage Lambda versions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html)
- [Use Lambda aliases](https://docs.aws.amazon.com/lambda/latest/dg/configuration-aliases.html)
- [Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)
- [Configure Lambda functions to access resources in a VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [Lambda invocation models](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS CLI Lambda command reference](https://docs.aws.amazon.com/cli/latest/reference/lambda/)

**Implementation note:** Runtime identifiers, policies, quotas, package support, features, and pricing can change by Region, function type, and over time. Always verify against current AWS documentation and test in an actual account/Region before applying to production.
