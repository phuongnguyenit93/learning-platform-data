# SnapStart, Memory Configuration, and Runtime Compatibility Requirements

A Java Lambda can start slowly because it must load the runtime, initialize the Spring ApplicationContext, create beans, load configuration, and establish connections before handling its first invocation. **AWS Lambda SnapStart** reduces repeated initialization by taking a snapshot of the initialized execution environment when you publish a function version. When a new execution environment is needed, Lambda restores that snapshot instead of rerunning the entire init process.

SnapStart is neither a Spring annotation nor a change to the **Spring Cloud Function** programming model. Beans remain **Supplier**, **Function**, or **Consumer**; on a Java managed runtime, the handler can remain **FunctionInvoker**. However, snapshotting changes how you must think about initialization data, static state, network connections, random seeds, and credentials. Meanwhile, **MemorySize** controls RAM, CPU, and network performance together, while **EphemeralStorage** configures **/tmp** capacity independently of memory.

This lesson belongs to the **AWS Lambda** chapter and covers enabling SnapStart on published versions, understanding the snapshot/restore lifecycle, using Java **CRaC runtime hooks**, checking runtime compatibility, integrating with Spring Cloud Function, configuring AWS SAM/CLI, choosing memory and ephemeral storage, benchmarking, and troubleshooting. The goal is to make decisions based on workloads and runtime constraints rather than flipping a switch and assuming cold starts are solved.

## 1. Which Part of a Cold Start Does SnapStart Solve?

When a new Lambda execution environment is created, AWS must prepare the environment and execute application initialization. With Spring Boot, this process can include:

- Starting the Java runtime/JVM.
- Loading classes and dependencies.
- Creating the Spring ApplicationContext.
- Initializing beans and configuration.
- Creating serializers, HTTP clients, SDK clients, and connection pools.
- Running static initializers or **@PostConstruct** methods.
- Registering Function beans in **FunctionCatalog**.

With a SnapStart-supported runtime, Lambda performs initialization when you **publish a version**, captures the initialized memory/disk state, encrypts it, and saves a snapshot. When scaling out to new execution environments, Lambda restores the snapshot to avoid repeating startup work.

~~~mermaid
flowchart TD
    A["Publish Lambda version"] --> B["Init: runtime + Spring context + beans"]
    B --> C["beforeCheckpoint hooks"]
    C --> D["Lambda creates encrypted snapshot"]
    D --> E["Invoke / scale out"]
    E --> F["Restore snapshot"]
    F --> G["afterRestore hooks"]
    G --> H["Invoke Function handler"]
~~~

### SnapStart Does Not Eliminate All Overhead

SnapStart reduces the time to create an execution environment from an initialized state. Lambda still must:

- Restore the snapshot.
- Run post-restore hooks if present.
- Receive the event and invoke the handler.
- Execute business logic and downstream calls.

Therefore, SnapStart does not replace optimizing Function code, memory tuning, connection management, or observability. For APIs with very strict latency targets, measure both restore duration and request processing time.

### Comparison with Provisioned Concurrency

**Provisioned Concurrency** keeps pre-initialized execution environments warm to serve requests with low latency. SnapStart creates a snapshot to restore environments on demand. These two mechanisms serve similar goals yet **cannot be enabled simultaneously on the same function version**.

| Criterion | SnapStart | Provisioned Concurrency |
| --- | --- | --- |
| Preparation | Snapshot on version publish | Pre-initializes a configured number of environments |
| Scaling | Restores environments from snapshot | Uses provisioned environments; may require scaling configuration |
| Operations | Must check uniqueness, stale state, and restore hooks | Must forecast concurrency and manage ready environments |
| Combination | Not supported alongside Provisioned Concurrency | Cannot be used with SnapStart on the same function version |
| Best fit | Reduce startup latency without holding full idle capacity | Workloads with strict latency SLAs and predictable traffic |

If SnapStart does not meet your latency SLO, evaluate Provisioned Concurrency as a separate option and calculate the cost/capacity trade-offs.

## 2. Runtime Compatibility Requirements

SnapStart supports **Lambda managed runtimes** in AWS-published families, including **Java 11 and later**. Support applies to ZIP packages and supported Lambda base images. For container images using a custom base image, implement the SnapStart hooks/compatibility requirements per AWS documentation.

Incompatible runtimes and features include:

| Runtime/Feature | SnapStart |
| --- | --- |
| Java managed runtimes (Java 11 and later) | Supported |
| Python 3.12+ and .NET 8+ | Supported per AWS runtime list |
| OS-only runtimes such as **provided.al2023** | Not supported |
| Self-managed custom runtime ZIP | Not supported under OS-only runtime family |
| Native image ZIP running on **provided.al2023** | Does not support SnapStart |
| Container images | Conditional; use a supported Lambda base image or implement hooks per custom base image docs |
| Provisioned Concurrency | Cannot be combined |
| Amazon EFS | Not supported |
| Amazon S3 Files | Not supported |
| Ephemeral storage larger than 512 MB | Not supported |

**Key takeaway across this AWS Lambda series:** Spring Cloud Function running on a **Java managed runtime** can use SnapStart if the Java version and Region are supported by AWS. The **provided.al2023** custom runtime/native image from the previous lesson cannot enable SnapStart this way because OS-only runtimes are not supported.

Supported runtimes and features can evolve. Before deploying, check the current SnapStart documentation and runtime status in your target Region; do not assume every Java runtime or custom runtime is automatically compatible.

AWS currently provides SnapStart in commercial Regions, with certain Asia Pacific exceptions such as New Zealand and Taipei. Because Regional availability can expand, check support at deployment time instead of hard-coding an assumption in your pipeline.

## 3. SnapStart Applies Only to Published Versions

SnapStart is configured with:

~~~yaml
SnapStart:
  ApplyOn: PublishedVersions
~~~

Lambda creates the snapshot when you publish a function version. You **cannot invoke SnapStart on unpublished $LATEST**. An alias such as **live** or **prod** must point to a published version for traffic to actually use the snapshot.

~~~mermaid
flowchart LR
    A["$LATEST"] --> B["Publish version 12"]
    B --> C["Init + snapshot"]
    C --> D["Version 12: Active"]
    D --> E["Alias live -> version 12"]
    E --> F["Client invokes alias live"]
~~~

### Version States

| State | Practical Meaning |
| --- | --- |
| **Pending** | Lambda is running init and creating the snapshot; do not invoke the version yet |
| **Active** | Snapshot is ready for restore/invocation |
| **Inactive** | A Java version's snapshot may be deleted after inactivity; Lambda must recreate the snapshot |
| **Failed** | Init or snapshot creation failed; inspect CloudWatch logs and version status |

With Java SnapStart, if a version receives no invocations for **14 days**, its snapshot can be deleted and the version transitions to **Inactive**. When invoked again, callers may receive **SnapStartNotReadyException** while Lambda builds a new snapshot. Monitor state and retry once the version returns to Active.

### Code or Configuration Changes Require Publishing a New Version

Snapshots are tied to **a published version**. Whenever you change code, environment variables, memory, or SnapStart configuration, ensure a new version is published and the alias points to it. Editing **$LATEST** does not update the snapshot created for an earlier version.

## 4. Enabling SnapStart with AWS SAM

Example Spring Cloud Function with an **uppercase** bean, using a Java managed runtime and **FunctionInvoker** handler:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function with Lambda SnapStart

Resources:
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/function-app-1.0.0-aws.jar
      MemorySize: 1024
      Timeout: 30
      EphemeralStorage:
        Size: 512
      SnapStart:
        ApplyOn: PublishedVersions
      AutoPublishAlias: live
      Environment:
        Variables:
          spring_cloud_function_definition: uppercase
      Policies:
        - AWSLambdaBasicExecutionRole
~~~

Key properties:

- **Runtime: java21**: uses a managed Java runtime; choose a version supported by AWS in your deployment Region.
- **Handler**: Spring Cloud Function **FunctionInvoker**, not the bean name **uppercase**.
- **CodeUri**: shaded JAR built per the Spring Cloud Function guide.
- **MemorySize**: e.g., 1,024 MB; must be benchmarked against your workload.
- **EphemeralStorage.Size: 512**: keeps **/tmp** at the SnapStart-compatible default.
- **SnapStart.ApplyOn**: tells Lambda to create snapshots for published versions.
- **AutoPublishAlias: live**: SAM creates a version and points the alias to the new version.
- **spring_cloud_function_definition**: selects the Function bean invoked by FunctionInvoker.
- **AWSLambdaBasicExecutionRole**: basic logging permissions; add least-privilege business permissions if the function calls other AWS services.

When using **AutoPublishAlias**, SAM creates version and alias resources for the function. Changes to code and versioned properties like **MemorySize**, **Environment**, or **SnapStart** can trigger publishing a new version per SAM rules. Inspect the CloudFormation change set and alias after deployment.

### Do Not Use This Template for Custom Runtime / Native ZIP

The template above uses a **managed Java runtime**. Do not switch Runtime to **provided.al2023** while keeping SnapStart expecting snapshots to work. OS-only runtimes do not support SnapStart. If you need a native image or custom runtime, follow the custom runtime model from the previous lesson and benchmark/optimize with mechanisms suited to that runtime.

## 5. Enabling and Verifying with AWS CLI

If the function already exists, enable SnapStart for published versions:

~~~bash
aws lambda update-function-configuration \
  --function-name spring-function \
  --snap-start ApplyOn=PublishedVersions \
  --memory-size 1024 \
  --ephemeral-storage '{"Size":512}'
~~~

After the configuration update completes, publish a new version:

~~~bash
aws lambda publish-version \
  --function-name spring-function
~~~

Obtain the version number from the publish output, then inspect that specific version's configuration:

~~~bash
aws lambda get-function-configuration \
  --function-name spring-function \
  --qualifier 12
~~~

In the output, verify:

~~~json
{
  "Version": "12",
  "State": "Active",
  "SnapStart": {
    "ApplyOn": "PublishedVersions",
    "OptimizationStatus": "On"
  }
}
~~~

The version/state values in the example are illustrative. While the version is **Pending**, wait for Lambda to finish snapshotting. If **OptimizationStatus** is not On or State is Failed, check LastUpdateStatusReason and CloudWatch logs.

Invoke the published version:

~~~bash
aws lambda invoke \
  --function-name spring-function:12 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

Or invoke the alias pointing to the version:

~~~bash
aws lambda invoke \
  --function-name spring-function:live \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

Do not invoke an unqualified function name to verify SnapStart and assume the feature is active; invocations must target a published version or an alias pointing to one.

## 6. Configuring MemorySize: RAM Also Controls CPU

Lambda allows configuring memory from **128 MB to 10,240 MB** in **1 MB** increments. Memory is not just the Java heap size. It is the total memory Lambda allocates to the execution environment, covering the runtime, Spring, extensions, heap, metaspace, thread stacks, direct buffers, and native memory.

Lambda allocates CPU proportionally to memory. At **1,769 MB**, a function receives CPU equivalent to one vCPU; increasing memory scales CPU proportionally up to 6 vCPUs at the 10,240 MB maximum. Network capacity can also scale with resource allocation. Consequently, raising memory sometimes speeds up a function even when the application does not use all available RAM.

| Configured Memory | Meaning |
| --- | --- |
| 128 MB | Lowest tier; suited for very lightweight functions |
| 512 MB | Small example configuration; measure with Spring runtime |
| 1,024 MB | Illustrative tier for Java apps with dependencies |
| 1,769 MB | Approximately one vCPU equivalent |
| 3,538 MB | Provides more CPU for parallel workloads |
| 10,240 MB | Maximum tier; up to roughly 6 vCPUs |

The middle rows are illustrative milestones, not fixed optimal profiles. I/O-bound, CPU-bound, and memory-bound workloads have different optimal points.

### Java Heap Does Not Equal MemorySize

Never set the JVM heap to the entire MemorySize. The JVM also needs memory for:

- Metaspace and class metadata.
- Thread stacks.
- JIT/compiler data on a managed JVM runtime.
- Direct ByteBuffers and network buffers.
- Native libraries, TLS, compression, and serialization.
- Spring/agents/extensions and other runtime overhead.

If the heap consumes nearly all of MemorySize, the process can hit out-of-memory errors even before heap hits your expected cap. Watch **Max Memory Used** in Lambda REPORT/CloudWatch and inspect heap/native memory when needed.

### Configuration in AWS SAM

~~~yaml
Properties:
  Runtime: java21
  MemorySize: 1769
  Timeout: 30
  SnapStart:
    ApplyOn: PublishedVersions
~~~

**1769 MB** in the example is a starting milestone for testing CPU-bound workloads, not a recommendation to set every function there.

### Updating Memory with AWS CLI

~~~bash
aws lambda update-function-configuration \
  --function-name spring-function \
  --memory-size 1769
~~~

This updates the function's configuration. With SnapStart, publish a new version and shift the alias to it so live traffic uses the new memory setting.

## 7. EphemeralStorage and /tmp Limits

**EphemeralStorage** is the temporary disk space Lambda provides at **/tmp**. It is independent of MemorySize:

- MemorySize measures execution environment memory.
- EphemeralStorage measures temporary file capacity on the filesystem.
- Increasing /tmp does not increase Java heap or CPU.
- Increasing MemorySize does not automatically increase /tmp capacity.

Lambda lets you configure ephemeral storage from **512 MB to 10,240 MB** in 1 MB increments. However, **SnapStart does not support ephemeral storage larger than 512 MB**. If you need SnapStart, keep EphemeralStorage at 512 MB.

Compatible configuration example:

~~~yaml
EphemeralStorage:
  Size: 512
SnapStart:
  ApplyOn: PublishedVersions
~~~

Example needing 2 GB /tmp:

~~~yaml
EphemeralStorage:
  Size: 2048
~~~

The second configuration **is incompatible with SnapStart**. If a workload needs large temporary storage, consider disabling SnapStart or redesigning to stream data, split files, or use appropriate storage. EFS is also on the list of SnapStart-incompatible features, so do not treat EFS as a direct expansion path for a SnapStart function.

### /tmp and Snapshot Data

SnapStart saves initialized memory and disk state. Therefore, never treat files written to /tmp during init as isolated per-environment storage after restore. Files may contain state copied from the snapshot. Create temporary files per invocation, check expiry, and never store secrets or unique business state there.

## 8. Tuning Workflow for MemorySize and SnapStart

Never pick memory from a single run or a gut feeling that the app feels fast or slow. Build a repeatable measurement workflow:

1. **Choose a representative workload**: realistic small/large payloads, concurrency levels, and invocation frequency.
2. **Establish a baseline**: run the managed Java runtime without SnapStart at current memory.
3. **Measure resources**: Duration, Billed Duration, Max Memory Used, errors, throttles, and downstream latency.
4. **Test multiple memory tiers**: raise/lower MemorySize to observe how CPU, throughput, and duration change.
5. **Enable SnapStart on a published version**: publish a new version, wait for Active, and invoke the exact version/alias.
6. **Measure restore and invoke**: separate Restore Duration, handler time, and warm invocations.
7. **Calculate cost per workload**: higher memory increases per-millisecond price yet may cut duration enough to lower total cost across real invocation counts.
8. **Verify stability**: run enough cold restores, warm invocations, and concurrent bursts to avoid drawing conclusions from one sample.

### Metrics to Observe

| Metric | Meaning |
| --- | --- |
| **Init Duration** | Initialization time in applicable logs |
| **Restore Duration** | Time Lambda spends restoring the SnapStart snapshot |
| **Duration** | Invocation processing duration |
| **Billed Duration** | Billed duration per runtime configuration |
| **Max Memory Used** | Peak memory consumed |
| **Memory Size** | Configured memory allocation |
| **Errors/Throttles** | Failures and concurrency limits |
| **p50/p95/p99 latency** | Latency distribution rather than averages alone |

With SnapStart, **RESTORE_REPORT** logs help analyze restores. Never lump restore duration into business handler duration when comparing options.

### AWS Lambda Power Tuning

You can use the open-source **AWS Lambda Power Tuning** tool to run a workload across multiple memory allocations and compare duration/cost. The tool invokes real code and downstream services in your AWS account; use a staging function and test data so benchmarks never write accidentally to production.

### Fair Comparisons

When comparing standard JVM vs. SnapStart:

- Use the same artifact, Java runtime, Region, and architecture.
- Use the same payloads, dependencies, and downstream targets.
- Compare both cold starts and warm executions.
- Do not sample only the first invocation after publishing; wait until the version is Active.
- Collect enough samples for reliable p95/p99 metrics.
- Avoid changing memory at the same time as unrelated factors if you want to isolate the cause of improvements.

## 9. Consolidated Compatibility Matrix for Spring Cloud Function

The table below gives a quick deployment configuration check:

| Component | SnapStart Java Managed Runtime | Custom Runtime / Native Image |
| --- | --- | --- |
| Runtime | Supported Java managed runtime | e.g., provided.al2023 |
| Handler | FunctionInvoker::handleRequest | Per custom runtime/RIC integration |
| SnapStart | ApplyOn: PublishedVersions | Not supported on OS-only runtimes |
| Function definition | spring_cloud_function_definition | Per runtime integration/sample |
| MemorySize | 128-10,240 MB | 128-10,240 MB |
| EphemeralStorage | Must not exceed 512 MB | Per runtime quota; no SnapStart restriction |
| Version | Publish version and invoke alias/version | Manage versions per deployment model |
| Bootstrap | No separate bootstrap file needed | Required for custom runtime ZIP |

With Spring Cloud Function, verify **handler, function definition, and runtime** belong to the same model. Never take a managed Java Handler and move it to provided.al2023 while omitting RIC/bootstrap. Likewise, never enable SnapStart on a native image ZIP merely because the executable was built from the same Java source.

## 10. SnapStart Runtime Hooks with Java CRaC

A snapshot captures memory and disk state at checkpoint time. Some of that state may become invalid after Lambda restores the execution environment: sockets may be closed, tokens expired, caches may hold stale timestamps, or data meant to be unique per environment may be duplicated.

The Java runtime supports **runtime hooks** based on the **CRaC (Coordinated Restore at Checkpoint)** API. Two key callbacks:

- **beforeCheckpoint()**: runs before Lambda takes the snapshot; used to flush, close, or prepare resources that cannot be restored verbatim.
- **afterRestore()**: runs after Lambda restores the snapshot; used to validate and re-establish needed resources before the handler serves invocations.

CRaC has three components:

| Component | Role |
| --- | --- |
| **Resource** | Object implementing beforeCheckpoint/afterRestore |
| **Context** | Registers and coordinates Resources |
| **Core** | Provides the global context via Core.getGlobalContext() |

### Adding the CRaC Dependency

With Maven:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

The version above is an example per AWS guidance; pin a version compatible with your project's Java/Spring build and update per dependency policy.

With Gradle:

~~~groovy
dependencies {
    implementation 'org.crac:crac:1.4.0'
}
~~~

### Example Spring Bean Registering Lifecycle Hooks

Suppose the application has a custom **ConnectionManager** managing connections to a downstream system. The interface name and two methods in the example are illustrative contracts; replace them with your application's actual client/pool.

File **src/main/java/example/lambda/SnapStartLifecycle.java**:

~~~java
package example.lambda;

import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class SnapStartLifecycle implements Resource {

    private final ConnectionManager connectionManager;

    public SnapStartLifecycle(
            ConnectionManager connectionManager) {
        this.connectionManager = connectionManager;

        // Register resource in the CRaC global context.
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            org.crac.Context<? extends Resource> context)
            throws Exception {

        connectionManager.closeConnectionsThatCannotBeResumed();
    }

    @Override
    public void afterRestore(
            org.crac.Context<? extends Resource> context)
            throws Exception {

        connectionManager.validateOrReconnect();
    }
}
~~~

Because **SnapStartLifecycle** is a Spring singleton bean, the Spring ApplicationContext holds a strong reference to this object. That matters: the CRaC Context registers Resources using a **weak reference**. If you register a temporary object without keeping a strong reference, the garbage collector can reclaim it and the hooks will never run.

### Hook Ordering and Time Limits

- **beforeCheckpoint()** runs in reverse registration order.
- **afterRestore()** runs in registration order.
- Hooks must be imported/initialized in the application; an unloaded class never registers its hook.
- **afterRestore()** and runtime loading must finish within the **10-second** restore limit. Exceeding it can cause Lambda to report **SnapStartTimeoutException**.
- **beforeCheckpoint()** counts toward Lambda's init/checkpoint time limit; hooks must not run migrations or unbounded tasks.
- Init and before-checkpoint have their own Lambda lifecycle time limits; never place unbounded work inside hooks.

Do not run database migrations, slow API calls, or load hundreds of megabytes in **afterRestore()**. Keep hooks short, bounded with timeouts, and safe to run repeatedly. If reconnecting can be slow, mark the client for refresh and perform lazy reconnection inside the handler with an appropriate deadline.

## 11. Data That Must Never Be Assumed Unique After Restore

Lambda can use **a single initial snapshot** to create many execution environments. Thus, values generated during init can be cloned across multiple environments.

Dangerous example:

~~~java
private static final String INSTANCE_ID =
    java.util.UUID.randomUUID().toString();
~~~

If the UUID is generated during class initialization before snapshotting, multiple restored environments can start with the exact same value. The same applies to:

- Random seeds or random bytes already buffered in memory.
- Tokens, secrets, or credentials generated during init.
- In-memory counters used to issue unique IDs.
- Timestamps recording per-environment startup time.
- Hostname/process metadata assumed to be unique identifiers.
- Caches holding data that must differ across environments.

### Generating Unique Values After Restore or in the Handler

If an ID serves individual business requests, generate it while handling the request:

~~~java
@Bean("createRequestId")
Supplier<String> createRequestId() {
    return () -> java.util.UUID.randomUUID().toString();
}
~~~

For data requiring cryptographic randomness, use **java.security.SecureRandom** or an AWS-supported CSPRNG mechanism. Never seed from current time during init and store it in a static field.

If you need a unique ID per execution environment, regenerate it after restore in a hook and verify the strategy cannot collide when multiple environments restore concurrently. If an ID must be globally unique or durable across invocations, use an external ID mechanism such as a database sequence/conditional write or standard application UUIDs rather than static counters.

### Avoiding Business Side Effects During Spring Initialization

With SnapStart, the Spring ApplicationContext and beans are initialized when Lambda publishes a version to take the snapshot. Therefore, actions in static initializers, constructors, or **@PostConstruct** can run during deploy/version-publish before any real request arrives.

Avoid:

- Creating a real order inside @PostConstruct.
- Sending emails or emitting business events when the Spring context starts.
- Running non-idempotent migrations during version publish.
- Issuing a business ID once and assuming each environment gets a distinct value.

Initialization should set up shared structures, configuration, and reusable clients. Business side effects must happen inside the Function handler with appropriate idempotency.

## 12. Network Connections, Credentials, and Temporary Data

### Network Connections

Connection state created during init **is not guaranteed** to remain valid after Lambda restores a snapshot. TCP connections, TLS sessions, DNS caches, or connection pools may be stale.

Ways to handle this:

1. Prefer clients/pools capable of detecting broken connections and reconnecting automatically.
2. Validate connections before use or recreate them as needed.
3. Use **afterRestore()** for short, predictable resets/reinitialization.
4. If connecting can take a long time, perform lazy reconnection inside the handler with a timeout/deadline.
5. Keep downstream timeouts smaller than Lambda's remaining time.

The AWS SDK typically recovers most connections via its built-in mechanisms; do not assume every custom socket or JDBC connection stays alive automatically.

### Credentials

Never read temporary credentials at init and store access keys/secrets/session tokens in static fields. Credentials can expire before an environment is restored.

When using the AWS SDK, prefer the **default credential provider chain** or the AWS-recommended provider for your runtime. With SnapStart enabled, Lambda uses the container credential endpoint so the SDK fetches fresh credentials after restore. Never hard-code credentials into code or snapshots.

Lambda supplies container credential endpoint variables such as **AWS_CONTAINER_CREDENTIALS_FULL_URI** and **AWS_CONTAINER_AUTHORIZATION_TOKEN** when SnapStart is active. The AWS SDK credential provider chain uses this mechanism; avoid manually reading access keys/session tokens at init and caching them in static fields.

### Temporary Data and /tmp

**/tmp** is ephemeral storage per execution environment. SnapStart can restore snapshotted disk state, so data written to /tmp during init must not be treated as isolated per-invocation or per-environment data after restore.

- Never store secrets or unique tokens in files created at init.
- Never rely on temporary files for durable business state.
- Clean up/recreate temporary files per invocation as needed.
- Check timestamps/expiry before using caches or files created pre-snapshot.

If data must survive across invocations or be shared across execution environments, use appropriate external storage.

## 13. Integrating with Spring Cloud Function

On a Java managed runtime, Spring Cloud Function continues using the AWS adapter:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

spring_cloud_function_definition:
  uppercase
~~~

Example Function bean:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SnapStartFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SnapStartFunctionApplication.class, args);
    }

    public record TextRequest(String value) {}

    public record TextResponse(String value) {}

    @Bean("uppercase")
    Function<TextRequest, TextResponse> uppercase() {
        return request -> {
            if (request == null || request.value() == null) {
                throw new IllegalArgumentException(
                    "value is required");
            }

            return new TextResponse(
                request.value().toUpperCase(Locale.ROOT));
        };
    }
}
~~~

SnapStart operates at the **Lambda runtime/execution environment** layer. FunctionInvoker and FunctionCatalog remain responsible for routing events to beans. You do not need to replace the Function with an AWS-specific handler just to enable SnapStart.

### What to Audit in Spring Boot

- Do beans initialized at startup cause side effects?
- Do HTTP/DB clients hold connections across the snapshot?
- Do caches contain timestamps, tokens, or IDs that must be unique?
- Are there mutable static fields or random seeds generated during init?
- Does any component spawn background threads/tasks that keep running after init?
- Is the hook resource initialized by Spring component scan?
- Does the CRaC Resource keep a strong reference throughout its lifecycle?
- Does the restore hook finish within 10 seconds?

If you have no special resources, do not add a CRaC hook just for the sake of having one. Start by auditing uniqueness, connections, credentials, and side effects; add hooks only when specific pre-checkpoint or post-restore actions are required.

## 14. Testing SnapStart for Spring Cloud Function

Split testing into layers because each layer verifies a different contract:

| Testing Layer | Goal |
| --- | --- |
| Unit test | Function logic, idempotency, and ID generation |
| Spring integration test | ApplicationContext, FunctionCatalog, bean lifecycle, and component scan |
| CRaC hook test | beforeCheckpoint/afterRestore invoke the right resource-management operations |
| Publish-version test | Lambda creates the snapshot and the version transitions to Active |
| Restore test | Environment is restored, hooks execute, and connections refresh |
| Load/latency test | p50/p95/p99, restore duration, memory, concurrency, and downstream latency |

### Unit Test for the Function Bean

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SnapStartFunctionTest {

    @Test
    void uppercasesRequest() {
        var app = new SnapStartFunctionApplication();

        var result = app.uppercase().apply(
            new SnapStartFunctionApplication.TextRequest(
                "hello lambda"));

        assertEquals("HELLO LAMBDA", result.value());
    }
}
~~~

This test verifies the business function directly. It does not verify SnapStart, the CRaC runtime, or Lambda versions.

### Testing CRaC Hooks with a Mock Collaborator

You can inject a mock **ConnectionManager** and call both callbacks to verify operation order:

~~~java
package example.lambda;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.crac.Context;
import org.junit.jupiter.api.Test;

class SnapStartLifecycleTest {

    @Test
    void closesBeforeCheckpointAndReconnectsAfterRestore()
            throws Exception {

        ConnectionManager manager =
            mock(ConnectionManager.class);

        SnapStartLifecycle lifecycle =
            new SnapStartLifecycle(manager);

        Context context = mock(Context.class);

        lifecycle.beforeCheckpoint(context);
        lifecycle.afterRestore(context);

        verify(manager).closeConnectionsThatCannotBeResumed();
        verify(manager).validateOrReconnect();
    }
}
~~~

This test checks the lifecycle class and its collaborator. Instantiating the class in a unit test also registers the resource with the test JVM's CRaC global context; in real test suites, consider separating registration from the constructor or using a Spring test context to avoid repeated registrations. Integration testing on staging Lambda is still required to prove the Lambda runtime actually invokes the hooks.

### Spring FunctionCatalog Integration Test

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = SnapStartFunctionApplication.class)
class SnapStartCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void registersUppercaseFunction() {
        assertNotNull(catalog.lookup("uppercase"));
    }
}
~~~

If the lifecycle bean is part of component scan, verify it is also created in the Spring context. Checking FunctionCatalog alone does not prove the CRaC Resource is registered and strongly referenced; add a dedicated bean lifecycle test if needed.

### Testing Uniqueness and Connection Recovery

In staging, generate enough concurrency for Lambda to restore multiple execution environments from the same snapshot. Record:

- Lambda Request IDs.
- Business event IDs.
- Execution environment IDs if the application has a safe identification mechanism.
- Generated tokens/UUIDs.
- Connection resets/reconnects and downstream errors.

Confirm no business ID or secret repeats because it was created during init. For connection pools, verify the first request after restore does not use a stale socket and reconnecting does not exceed restore time.

## 15. Troubleshooting SnapStart and Memory

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| **SnapStartNotReadyException** | Java version is Inactive or snapshot is being recreated | Check State, wait for Active, and retry |
| **SnapStartTimeoutException** | afterRestore hook or runtime restore exceeded 10 seconds | Shorten hook, reconnect lazily, and set timeouts |
| Version stuck in **Pending** | Slow init, beforeCheckpoint, or VPC/network setup | Inspect logs, dependency startup, and resource hooks |
| **OptimizationStatus** is not On | Incompatible runtime/feature or snapshot not ready | Check runtime, Region, State, and SnapStart config |
| Invoking $LATEST shows no SnapStart | SnapStart applies only to published versions | Publish a version and invoke qualifier/alias |
| Alias still uses old behavior | Alias not pointing to new version | Check alias routing and published version |
| **Runtime.Unsupported** or config rejected | Using an OS-only runtime like provided.al2023 | Switch to a managed Java runtime for SnapStart |
| EFS attach fails with SnapStart enabled | EFS is incompatible | Disable SnapStart or redesign storage |
| /tmp larger than 512 MB rejected | SnapStart limits ephemeral storage | Lower to 512 MB or disable SnapStart |
| Duplicate IDs/secrets across environments | Unique value created during init and cloned in snapshot | Generate after restore/in handler, use CSPRNG or ID service |
| DB/HTTP connection fails after restore | Socket or pool state is stale | Validate/reconnect in hook or lazily in handler |
| Expired credentials | Cached temporary credentials created during init | Use AWS SDK default credential provider chain |
| CRaC hook never runs | Resource not imported/registered or garbage collected | Check component scan, registration, and strong reference |
| Restore hook runs slowly | Network call or heavy initialization in afterRestore | Keep hook short, defer work to handler |
| Lambda OOM | Low MemorySize or growing heap/native memory | Check Max Memory Used, heap, and native buffers |
| CPU-bound function runs slow | Low memory gives low CPU allocation | Test higher memory tiers and measure duration/cost |
| Slow despite spare memory | I/O/downstream-bound workload or cold starts | Measure network/downstream latency and restores separately |
| /tmp runs out of space | Temp files not cleaned or workload needs more storage | Clean files, stream data, or redesign storage |
| SnapStart build succeeds yet latency unchanged | Invoking wrong alias/version or init is not the bottleneck | Check qualifier, restore logs, and latency breakdown |

### Analyzing Logs

When SnapStart is active, inspect lifecycle logs such as **RESTORE_REPORT** alongside init/report logs. Separate three parts:

1. **Init/snapshot**: initialization cost during version publish.
2. **Restore**: time spent restoring the snapshot and running afterRestore.
3. **Invoke**: time the Function spends processing the event and calling downstream services.

If you look only at handler Duration, you can miss restore latency or startup time occurring in the publish workflow.

## 16. Checklist Before Enabling SnapStart

- [ ] Java runtime is on the list of SnapStart-supported managed runtimes.
- [ ] Function does not use an OS-only runtime or incompatible custom runtime ZIP.
- [ ] Function is published as a version; traffic targets that alias/version.
- [ ] SAM/CloudFormation sets SnapStart ApplyOn: PublishedVersions.
- [ ] Provisioned Concurrency is not enabled on the same version.
- [ ] No incompatible EFS or Amazon S3 Files mount is attached.
- [ ] EphemeralStorage does not exceed 512 MB.
- [ ] No unique IDs, secrets, or random seeds are generated at init and reused post-restore.
- [ ] AWS SDK uses a refresh-capable credential provider; no temporary credentials are cached.
- [ ] Network connections are validated/reconnected post-restore or inside the handler.
- [ ] Spring @PostConstruct/static initialization performs no business side effects.
- [ ] CRaC Resources are registered and strongly referenced if hooks are used.
- [ ] afterRestore completes within 10 seconds.
- [ ] MemorySize is benchmarked with representative payloads and concurrency.
- [ ] Init/Restore/Duration/Max Memory Used and p95/p99 are measured.
- [ ] Alias points to the right version and rollback is prepared.

## 17. Hands-on Exercises

**Exercise 1 — SnapStart lifecycle.** Diagram version publish, init, beforeCheckpoint, snapshot, restore, afterRestore, and invoke. Indicate which stages run at deploy time and which run when traffic arrives.

**Exercise 2 — Runtime compatibility.** One Spring Cloud Function app runs on Java 21 managed runtime. Another is a native image ZIP on provided.al2023. Identify which app can use SnapStart and explain why.

**Exercise 3 — Versions and aliases.** Enable SnapStart, publish a new version, and create a live alias. Write the CLI commands to check SnapStart OptimizationStatus and invoke the alias. Explain why invoking $LATEST does not test SnapStart.

**Exercise 4 — CRaC hooks.** Write a Resource managing a JDBC pool. Close non-resumable connections in beforeCheckpoint and validate/reconnect in afterRestore. Ensure the post-restore hook stays under 10 seconds.

**Exercise 5 — Weak reference.** Explain why registering an anonymous Resource and dropping its reference can prevent the hook from running. Design a Spring singleton bean holding a strong reference.

**Exercise 6 — Uniqueness.** A static UUID is generated in @PostConstruct. Describe how multiple execution environments restored from the same snapshot can share the same UUID. Move ID generation into the handler or a suitable ID mechanism.

**Exercise 7 — Connection recovery.** An application opens a JDBC connection during init before snapshotting. Design post-restore connection validation and a lazy reconnection strategy if the database is temporarily unavailable.

**Exercise 8 — Memory tuning.** Benchmark a function at 512, 1,024, 1,769, and 3,538 MB. Compare duration, memory, throughput, and cost. Explain why a higher memory tier can be cheaper if it cuts execution time enough.

**Exercise 9 — Ephemeral storage.** A function needs 2 GB /tmp to process files. Explain why that setting cannot be combined with SnapStart and propose a streaming/chunking design or alternative storage.

**Exercise 10 — Spring integration.** Write a FunctionInvoker bean, set spring_cloud_function_definition, and enable SnapStart in SAM. Verify FunctionCatalog, the published version, and the alias.

**Exercise 11 — Restore timeout.** An afterRestore hook calls an external API and takes 12 seconds. Analyze the failure and redesign so the hook completes within the limit while slow work runs in the handler.

**Exercise 12 — Benchmark.** Design an experiment comparing managed Java runtime without SnapStart, Java runtime with SnapStart, and Provisioned Concurrency. Measure p50/p95/p99, restore, billed duration, memory, and cost.

### Key Takeaways

- **SnapStart** takes a snapshot when publishing a version and restores execution environments from that snapshot to reduce repeated initialization.
- Invoke only **published versions or aliases pointing to versions**; $LATEST does not use SnapStart.
- SnapStart supports managed Java runtimes from Java 11 onward; **provided.al2023/OS-only custom runtimes** are not supported.
- Never combine SnapStart with Provisioned Concurrency, EFS, Amazon S3 Files, or EphemeralStorage larger than 512 MB.
- Java **CRaC Resource** provides beforeCheckpoint/afterRestore; retain a strong reference and finish afterRestore within 10 seconds.
- Never generate unique IDs, secrets, or random seeds at init and assume they remain unique after restore.
- Network connections and temporary credentials can go stale; validate/reconnect and use refresh-capable credential providers.
- MemorySize from 128 to 10,240 MB controls both memory and CPU; 1,769 MB equals one vCPU. EphemeralStorage is a separate /tmp allocation from 512 to 10,240 MB.
- Tune with real workloads, comparing restore, handler duration, Max Memory Used, p95/p99, and total cost before deciding.

### References

- [AWS Lambda — Improving startup performance with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html): runtime support, published versions, limitations, and compatibility.
- [AWS Lambda — Activating and managing SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-activate.html): enabling SnapStart via console/CLI, version states, snapshots, and AWS SAM.
- [AWS Lambda — Runtime hooks for Java](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-runtime-hooks-java.html): CRaC Resource, beforeCheckpoint, afterRestore, and registration.
- [AWS Lambda — Handling uniqueness with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-uniqueness.html): unique values, randomness, and execution environment clones.
- [AWS Lambda — SnapStart best practices](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html): networking, credentials, and startup optimization.
- [AWS Lambda — Troubleshooting SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-troubleshooting.html): restore timeouts, initialization, and snapshot failures.
- [AWS Lambda — Configure function memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html): memory range, CPU allocation, and memory tuning.
- [AWS Lambda — Configure ephemeral storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html): /tmp from 512 MB to 10,240 MB.
- [AWS SAM — AWS::Serverless::Function](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html): SnapStart, AutoPublishAlias, and version publishing.
- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, FunctionCatalog, routing, and deployment.
