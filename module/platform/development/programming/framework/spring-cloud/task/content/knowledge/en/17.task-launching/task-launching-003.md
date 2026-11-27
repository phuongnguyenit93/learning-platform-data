# Structure of TaskLaunchRequest in the Supported API Branch

## 1. Where Is TaskLaunchRequest Used?

**Spring Cloud Task** helps build **finite-lived** Spring Boot applications: launched, performing work, recording execution details in **TaskRepository**, and terminating. There are several ways to trigger a task: running `java -jar` from a terminal, having Kubernetes create a Job/CronJob, using an orchestrator, or receiving requests from another system.

In the **Launching** chapter, `TaskLaunchRequest` is the **object describing a launch request** in the **Spring Cloud Task with Spring Cloud Stream** integration branch. In this branch, a component sends a message containing a `TaskLaunchRequest`; **TaskLauncherSink** receives that object and uses a **Spring Cloud Deployer** `TaskLauncher` implementation to spawn the task process.

Key distinctions to keep in mind right away:

- **Not every Spring Cloud Task application needs to create a `TaskLaunchRequest`.** If you run `java -jar` directly or let a scheduler run a Job/Pod, you may not use this API at all.
- **`TaskLaunchRequest` is only data describing a launch request**, not a `TaskExecution` record already written by `TaskRepository`.
- **Receiving the message and calling the launcher successfully does not mean the business work is complete.** The launched task will continue running in another process/container.
- This API belongs to **the integration branch supported by the framework and Spring Cloud Stream version**. Do not assume older documentation examples using `@EnableTaskLauncher` work as-is on every modern Spring Cloud Stream release.

After this lesson, you will be able to identify the five fields of `TaskLaunchRequest`, construct the Java object with the proper constructor signature, classify command-line arguments/environment/deployment properties, design a safe message-to-launch pipeline, and track execution outcomes after a request is accepted.

## 2. Overview of the Message-Driven Launch Path

~~~mermaid
flowchart LR
    A["HTTP / event / scheduler"] --> B["Processor validating request"]
    B --> C["TaskLaunchRequest"]
    C --> D[("Spring Cloud Stream / message broker")]
    D --> E["TaskLauncherSink"]
    E --> F["Spring Cloud Deployer TaskLauncher"]
    F --> G["Finite task process / container"]
    G --> H[("TaskRepository")]
    G --> I[("Business data")]
    J["Monitoring tool"] --> H
~~~

The roles are:

| Component | Responsibility |
| --- | --- |
| **Request source** | Issues the command "run task X with input Y", whether via HTTP, broker, or event |
| **Producer/processor** | Validates permissions and input data; constructs a normalized `TaskLaunchRequest` |
| **Spring Cloud Stream** | Transports messages to the consumer/sink over the configured binder |
| **`TaskLauncherSink`** | Receives payloads of type `TaskLaunchRequest` and forwards the request to the launcher |
| **`TaskLauncher`** | Delegates process creation to the specific infrastructure, such as local or Kubernetes |
| **Launched Spring Cloud Task application** | Executes business logic and records run metadata via `TaskRepository` |
| **TaskRepository/TaskExplorer** | Stores and queries the lifecycle of task executions, not a message queue |

A sink is typically a **continuously running message-receiving application**, whereas the task application it launches is a **finite-lived application**. Therefore, you must not enable task auto-closing context behavior on a sink that needs to keep receiving messages without verifying the architecture first.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant M as Broker / Stream
    participant S as TaskLauncherSink
    participant L as TaskLauncher
    participant T as Task process
    participant R as TaskRepository
    P->>M: Message<TaskLaunchRequest>
    M->>S: Deliver typed payload
    S->>L: Request artifact launch
    L-->>S: Request accepted / infrastructure ID
    Note over S,T: Launch acceptance does not mean task completion
    L->>T: Create process / container
    T->>R: Start TaskExecution
    T->>T: Execute business logic
    T->>R: Write completion result (if reached in time)
    Note over R: Monitoring reads by TaskExecution or external correlation
~~~

## 3. Exact Structure of TaskLaunchRequest

According to the Spring Cloud Task 3.0.4 Javadoc, the class resides in package:

`org.springframework.cloud.task.launcher.TaskLaunchRequest`

It is a Java class implementing `Serializable`. The full five-argument constructor is:

~~~java
TaskLaunchRequest(
    String uri,
    List<String> commandlineArguments,
    Map<String, String> environmentProperties,
    Map<String, String> deploymentProperties,
    String applicationName
)
~~~

The Javadoc also lists a **no-arg constructor** (since 2.0.0) for compatible construction/serialization scenarios. However, this API **does not provide setters for all five fields**; therefore, when constructing requests in application code, use the five-argument constructor rather than assuming `setUri(...)` or `setCommandlineArguments(...)` exist.

### 3.1. Five Fields to Remember

| Field | Java Type | Purpose | Illustrative Example |
| --- | --- | --- | --- |
| `uri` | `String` | Path/URI to **the task artifact to run** | `maven://com.example.batch:daily-close:1.4.2` |
| `commandlineArguments` | `List<String>` | Arguments passed to **the launched task process** | `["--businessDate=2026-11-23", "--tenantId=tenant-a"]` |
| `environmentProperties` | `Map<String,String>` | Environment variables for **the task process** | `{"SPRING_PROFILES_ACTIVE":"task"}` |
| `deploymentProperties` | `Map<String,String>` | Properties **for TaskLauncher/deployer** to deploy onto the platform | CPU, memory, placement settings... per deployer contract |
| `applicationName` | `String` | Application name/identifier assigned to the launched task | `daily-close` |

Getter names in the Javadoc:

~~~java
request.getUri();
request.getCommandlineArguments();
request.getEnvironmentProperties();
request.getDeploymentProperties();
request.getApplicationName();
request.setApplicationName("daily-close");
~~~

**Watch the spelling:** the Java Javadoc uses `getCommandlineArguments()` (lowercase `l` in `line`). Prose in reference docs may write `commandLineArguments` in camelCase. When writing Java code, use **the exact method name from your dependency version** instead of guessing getters from prose field names.

The Javadoc notes that `getCommandlineArguments()` returns **an unmodifiable list from the getter**. Do not expect to call `request.getCommandlineArguments().add(...)` to mutate the request after creation. Build the desired list beforehand and pass it to the constructor.

### 3.2. uri Is Not an Input Parameter File Path

`uri` identifies **the application artifact to deploy**, not a URI to a CSV file to process.

Example:

~~~text
uri                     = maven://com.example.batch:daily-close:1.4.2
commandlineArguments[0] = --inputFile=/data/invoices-2026-11-23.csv
~~~

`maven://...` is an artifact URI format commonly shown in the Spring Cloud Deployer branch. Maven repository lookup, caching, and URI resolution depend on **the actual `ResourceLoader`/`TaskLauncher`**. With another deployer, you may use whatever `Resource`/URI types it supports; you cannot swap in an arbitrary HTTP URL and expect it to run automatically.

Pin artifacts to **controlled release versions** rather than allowing user messages to specify arbitrary artifacts.

### 3.3. commandlineArguments Are Just Arguments, Not Ready-Made JobParameters

List elements are passed as arguments to the task application:

~~~text
--businessDate=2026-11-23
--tenantId=tenant-a
--dryRun=false
~~~

The Spring Boot application can read them via `ApplicationArguments` or `Environment` configuration. If the task runs Spring Batch and needs **JobParameters**, verify the Boot/Batch launcher rules for your application: some Batch launch paths distinguish `name=value` from Spring Boot arguments prefixed with `--`.

`TaskLaunchRequest` **does not validate** whether a date is valid, whether a tenant has access, or whether the task supports a given parameter name. Input validation must happen at the producer and be **re-validated inside the task**.

### 3.4. environmentProperties vs. deploymentProperties

These are the two most easily confused maps.

**`environmentProperties`** passes **environment variables** to the task process, such as:

~~~text
SPRING_PROFILES_ACTIVE=task
TZ=UTC
~~~

The application sees these environment variables at runtime if the `TaskLauncher` supports forwarding them properly.

**`deploymentProperties`** is sent to **the deployer** to govern **how the process/container is created**: resource limits, environment selection, or deployment parameters supported by the platform. Key names depend on the `TaskLauncher` implementation and version; there is no universal list of CPU/memory keys across all deployers.

For example, an arbitrary `memory` key in `deploymentProperties` **does not mean** every `TaskLauncher` will limit RAM to that value. To configure Kubernetes, the local deployer, or another orchestrator, check the documentation for that specific deployer.

**Never pass secrets as plaintext in these maps or command-line args** if they can end up in the broker, task history, logs, Kubernetes Pod specs, or audits. Instead, reference infrastructure-managed secrets and let the platform mount them at runtime with proper permissions.

### 3.5. applicationName vs. Business Key and taskExecutionId

`applicationName` is **the logical name assigned by the launcher to the launched application**. It may be used to name infrastructure resources, logs, and traces. It is not by default:

- **`TASK_EXECUTION_ID`** — the ID of a **single run** assigned by `TaskRepository`.
- **Business key** — e.g., `tenant-a:2026-11-23` used to prevent duplicate processing.
- **`spring.application.name` / `spring.cloud.task.name`** — properties that may influence the name the task application itself records in `TaskRepository` depending on configuration.

In a real system, verify whether the deployer name and `TASK_EXECUTION.TASK_NAME` match rather than assuming they are identical.

Reference documentation notes that when `applicationName` is omitted, an auto-generated name like `Task-<UUID>` is used; some Javadoc versions describe it as `Task-<hash/unique id>`. **Do not rely on the default name-generation algorithm.** Set an explicit, stable `applicationName` that conforms to your deployment platform's naming rules.

## 4. Creating TaskLaunchRequest in Java

The following example creates a request to run a daily reconciliation task for one tenant. It demonstrates **the object structure**, without yet sending a message to a broker or starting a process.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;

public final class LaunchRequestFactory {

    private LaunchRequestFactory() { }

    public static TaskLaunchRequest dailyClose(
            String tenantId, String businessDate) {

        // Only allow tenant IDs with lowercase letters, digits, and hyphens.
        if (tenantId == null
                || !tenantId.matches("[a-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }

        LocalDate parsedDate = LocalDate.parse(businessDate);
        String date = parsedDate.toString();

        List<String> args = List.of(
                "--tenantId=" + tenantId,
                "--businessDate=" + date,
                "--workKey=" + tenantId + ":" + date
        );

        Map<String, String> environment = Map.of(
                "SPRING_PROFILES_ACTIVE", "task"
        );

        // Left empty in this example; in real deployments only use
        // keys supported by the corresponding TaskLauncher/deployer.
        Map<String, String> deployment = Map.of();

        return new TaskLaunchRequest(
                "maven://com.example.batch:daily-close:1.4.2",
                args,
                environment,
                deployment,
                "daily-close"
        );
    }
}
~~~

Explanation:

1. `uri` comes from an **approved** artifact allowlist, not directly from an untrusted HTTP request.
2. `businessDate` is parsed into a `LocalDate`, avoiding malformed date formats.
3. `workKey` is stable for **the same business job**, even if the request is resent after a timeout; the receiving task must actually use it to enforce idempotency.
4. `environmentProperties` contains only non-sensitive operational settings in this example.
5. `deploymentProperties` is intentionally empty; do not invent keys for Kubernetes or Cloud Foundry before choosing a deployer.
6. `applicationName` is set explicitly. If the platform requires a unique application name per launch, maintain separate conventions for **deployment instance** and **business key**.

### Reading It Back to Inspect the Structure

~~~java
TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

System.out.println(request.getUri());
System.out.println(request.getApplicationName());
System.out.println(request.getCommandlineArguments());
System.out.println(request.getEnvironmentProperties());
System.out.println(request.getDeploymentProperties());
~~~

Expected data output:

~~~text
maven://com.example.batch:daily-close:1.4.2
daily-close
[--tenantId=tenant-a, --businessDate=2026-11-23, --workKey=tenant-a:2026-11-23]
{SPRING_PROFILES_ACTIVE=task}
{}
~~~

The display order of a `Map` should not be treated as part of a protocol, even though the example has one key-value pair.

## 5. Data Sent Through a Message Broker

According to the Spring Cloud Task Reference, a processor can construct a `GenericMessage<TaskLaunchRequest>` and send it to the sink. The payload **must be converted into a valid `TaskLaunchRequest`** before the handler receives it. If the payload carries a different type without proper conversion, the sink may throw an exception.

Producer example:

~~~java
import org.springframework.cloud.task.launcher.TaskLaunchRequest;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

Message<TaskLaunchRequest> message =
        MessageBuilder.withPayload(request)
                .setHeader(
                    "correlationId",
                    "tenant-a:2026-11-23")
                .build();
~~~

**This example only builds the message in Java; it does not yet send it to the broker.** The producer still needs a mechanism to publish to the appropriate binding/channel, and the consumer needs the right binder, converter, schema, or trusted types configured.

### 5.1. JSON Illustrating the Logical Structure

A message could conceptually represent the request as follows:

~~~json
{
  "uri": "maven://com.example.batch:daily-close:1.4.2",
  "applicationName": "daily-close",
  "commandlineArguments": [
    "--tenantId=tenant-a",
    "--businessDate=2026-11-23",
    "--workKey=tenant-a:2026-11-23"
  ],
  "environmentProperties": {
    "SPRING_PROFILES_ACTIVE": "task"
  },
  "deploymentProperties": {}
}
~~~

**Do not treat this JSON as a wire contract automatically accepted by the framework in every version.** Serialized property names can depend on Jackson and JavaBean naming rules—for instance, `commandlineArguments` compared to docs writing `commandLineArguments`; conversion also depends on the binder and content type. Test **round-trip serialization/deserialization** with your actual producer/sink applications rather than trusting a hand-written JSON snippet.

In systems with strict security requirements, instead of letting the consumer deserialize an arbitrary Java class from a message, define a simple, versioned, validated JSON DTO/protocol and **map it to `TaskLaunchRequest` in a trusted adapter layer**. Never enable arbitrary Java class deserialization from an untrusted broker.

### 5.2. Spring Cloud Stream Function Processor Example

A function-based processor can transform an incoming validated Java record business command into a `TaskLaunchRequest`:

~~~java
import java.util.function.Function;

import org.springframework.cloud.task.launcher.TaskLaunchRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LaunchProcessorConfiguration {

    public record DailyCloseCommand(
            String tenantId,
            String businessDate) { }

    @Bean
    public Function<DailyCloseCommand, TaskLaunchRequest>
    toTaskLaunchRequest() {

        return command -> LaunchRequestFactory.dailyClose(
                command.tenantId(),
                command.businessDate());
    }
}
~~~

With proper binder/function configuration, the input is a validated/decoded `DailyCloseCommand` payload and the output is a `TaskLaunchRequest`. In a real application, configure **input/output destinations, content types, and message converters** according to your Spring Cloud Stream version; the snippet above only illustrates **where the request object is constructed**.

Correctness does not end when the producer publishes a message: the sink must receive the expected payload type, the launched task must receive the right arguments, and results must be verified via metadata and business data.

## 6. The TaskLauncherSink and @EnableTaskLauncher Branch

In the API branch described by the Spring Cloud Task Reference and its Javadoc, the sink application is declared as:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.launcher.annotation.EnableTaskLauncher;

@SpringBootApplication
@EnableTaskLauncher
public class TaskSinkApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskSinkApplication.class, args);
    }
}
~~~

`@EnableTaskLauncher` imports the `TaskLauncherSink` configuration, allowing the sink to receive a `TaskLaunchRequest` and invoke `TaskLauncher` to launch the task. **It does not supply all infrastructure pieces on its own**:

- There must be an **actual `TaskLauncher`** from Spring Cloud Deployer or configured by the application.
- You must configure a **Spring Cloud Stream binder**, destination, and decoding mechanism to receive the typed payload.
- You must select **compatible Spring Boot, Spring Cloud Task, Spring Cloud Stream, and Spring Cloud Deployer BOMs**. Spring Cloud Stream generations differ in programming models (e.g., annotation-based vs. function-based); do not paste old examples into newer releases without checking.
- A sink meant to continuously receive messages generally needs to **keep its context alive**, whereas the spawned task process must **terminate cleanly at the end of its lifecycle**.

In some legacy-model sink versions, the `TaskLauncherSink` Javadoc shows the handler:

~~~java
// Illustrative signature from the Spring Cloud Task branch containing TaskLauncherSink
void taskLauncherSink(TaskLaunchRequest taskLaunchRequest)
        throws Exception;
~~~

In deployment styles with an input channel named `input`, the binding destination can be configured with:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: task-launch-requests
~~~

**Version note:** the `input` binding style in this example corresponds only to the **annotation/channel-based sink branch** supported by the framework. With modern Spring Cloud Stream functional bindings, binding names and consumer wiring can differ. Verify against your actual runtime version rather than assuming `@EnableTaskLauncher` and `input` configuration remain the recommended default for every new project.

### Do Not Confuse TaskLauncherSink with TaskLauncher

- **`TaskLauncherSink`**: the **message-receiving** adapter in the Spring Cloud Stream integration.
- **`TaskLauncher`**: the **Spring Cloud Deployer** SPI responsible for **deploying the task artifact onto the infrastructure**.
- **`TaskLaunchRequest`**: the DTO/command describing the request received by the sink.
- **`AppDeploymentRequest`**: the deployer-layer request type used when interacting directly with `TaskLauncher` under the Spring Cloud Deployer contract.
- **`TaskExecution`**: metadata about **a single run** of the spawned application, persisted via `TaskRepository`.

Never write code calling `taskLaunchRequest.launch()`, because the request class **is not an executable task**. It owns no `JobRepository`, runs no `ApplicationRunner`, and has no API to report business success.

## 7. Result Lifecycle: "Launch Accepted" Is Not "Task Succeeded"

Suppose an internal API receives a report generation request:

~~~text
POST /reports/daily
tenantId=tenant-a
businessDate=2026-11-23
~~~

The processor validates it and emits a message containing a `TaskLaunchRequest`. These states should be kept distinct:

| Stage | Observable Signal | Accurate Interpretation |
| --- | --- | --- |
| API receives request | HTTP 202 or request record | Request accepted, **not** job finished |
| Broker receives message | Publisher receives acknowledgment | Message accepted, **not** guaranteed sink processed it |
| Sink calls `TaskLauncher` | Launch call returns or yields an infrastructure ID | Process may have just been requested/created |
| Task process starts | `TASK_EXECUTION` gets a start time | Task started, **not** completed |
| Task process finishes | `TASK_EXECUTION` gets an end time/exit code | Framework recorded lifecycle outcome; still reconcile business data |
| Report appears in target system | Verifiable business artifact | Confirms concrete success criteria |

`TaskLaunchRequest` **is not a return result** from `TaskRepository`. A sink that invokes the launcher and returns normally cannot know at which step the worker might fail.

### Querying TaskRepository

Example query for runs by the name recorded by the application (do not assume it equals the deployer's `applicationName`):

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-close'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

If the app has a different actual name, use the `TASK_NAME` observed in logs or configured by the task itself. When multiple runs share the same name, find **the exact execution ID** or match with other correlation data rather than grabbing an arbitrary latest row for an HTTP request.

You can include a non-sensitive **request ID/work key** in `commandlineArguments` and task logs, and persist a mapping table `requestId → platformExecutionId → taskExecutionId` when those IDs are available. Storing and matching IDs must be designed intentionally, not based on assuming the launcher ID and `TaskRepository` ID are always equal.

## 8. Message Safety, Retries, and Idempotency

### 8.1. Fields That Easily Become an Attack Surface

If callers are allowed to control the entire `TaskLaunchRequest`, they could:

- Supply a `uri` pointing to a malicious artifact or unapproved version.
- Pass CLI arguments that swap datasources, activate unintended profiles, or access unauthorized data scopes.
- Inject environment variables affecting Spring Boot startup.
- Supply deployment properties altering resources, namespaces, or platform quotas.
- Flood identical requests, causing high compute cost or duplicate business side effects.

**Security principle:** public or internal APIs should never accept and forward a raw `TaskLaunchRequest` from a client. Instead, accept a **constrained business command**, verify tenant/date/permissions, select the artifact and deployment properties from a **server-side allowlist**, and construct the request in a trusted layer.

~~~mermaid
flowchart LR
    A["Untrusted client"] --> B["Constrained business DTO"]
    B --> C{"Authz + input validation"}
    C -->|Valid| D["Allowlisted artifact / profile / deployer options"]
    D --> E["Build TaskLaunchRequest"]
    E --> F["Message broker"]
    F --> G["TaskLauncherSink"]
    C -->|Invalid| H["Reject + audit"]
~~~

Do not log the full `TaskLaunchRequest.toString()` without knowing what fields it might contain. Especially avoid placing tokens, passwords, or sensitive data into `commandlineArguments` or `environmentProperties` where brokers and infrastructure may store or expose them.

### 8.2. At-Least-Once Message Delivery and Duplicate Launch Requests

In most message brokers with retry mechanisms, a message can **be redelivered** after a connection drop or when the consumer finishes calling launch before acknowledging the message. As a result, a single request can trigger **two launches**, even with bug-free Java code.

Example:

1. The sink receives request `workKey=tenant-a:2026-11-23`.
2. `TaskLauncher` accepts process creation.
3. The sink loses connection before the broker records the acknowledgment.
4. The broker redelivers the same message.
5. The sink receives it a second time and may launch a second process.

`TaskLaunchRequest` has no built-in `idempotencyKey` field in its five-argument constructor. For idempotency, create a **business key/correlation ID** at the application layer, store request acceptance with a unique constraint or proper coordination, and design **the task itself to handle re-runs safely**.

Commonly combined safeguards:

- Persist requests with a unique key on tenant + processing period + task type + source version.
- Check state before deciding to relaunch, but **never rely on an unlocked SELECT-then-INSERT** which invites race conditions.
- Limit concurrent executions in the scheduler/deployer or use appropriate locking when needed.
- Enforce unique constraints, conditional UPSERTs, or idempotent consumers on business data.
- Retry with backoff, caps, dead-letter queues, and an investigation workflow.
- Distinguish "launch failed before creating a process" from "launch timed out when a process may already have been created"; the latter requires reconciliation before retrying.

**Do not use `applicationName` as an exactly-once mechanism.** Two sequential runs can share the same name and still produce duplicate side effects; conversely, infrastructure may require a distinct resource name per run while the business work shares a single work key.

### 8.3. Deploying Under Least Privilege

The consumer/sink needs permission to create processes on the infrastructure, but that does not mean it should be allowed to launch **any** application or read every secret. Restrict artifact URIs, namespaces, service accounts, resource quotas, and runtime settings; authenticate message sources, encrypt channels, set sensible retention, and control who can publish to the destination.

## 9. Concrete Use Cases

### Scenario A — Report Generation Request API

A reporting API receives `tenantId` and `businessDate`, authorizes the caller, builds a request with a fixed `uri`, `applicationName=report-generator`, arguments containing a work key, environment containing the profile, and platform-configured deployment properties.

**Design:** return `202 Accepted` with a request ID; the frontend shows "processing" until monitoring confirms `TaskExecution` and the output file. Do not return `200 SUCCESS` as if the report were already generated right after publishing the message.

### Scenario B — Event-Driven Task Execution

Once a new data file is confirmed fully uploaded, a producer emits an import command. The artifact URI is controlled; the input path/manifest is passed via a non-sensitive argument; the worker verifies checksums and versions.

**Design:** if the same event is redelivered, the system uses the work key and business constraints to prevent duplicate imports. An acknowledged message does not prove the target database was updated.

### Scenario C — Running Tasks on Kubernetes

`TaskLauncher` deploys a Kubernetes Job/Pod. `deploymentProperties` are built from system configuration matching the deployer API to cap resources and set the namespace; `environmentProperties` adds the profile. The task process records its own `TaskExecution` in the database.

**Design:** monitor both the Kubernetes Job/Pod and `TaskRepository`. The deployer-created resource and `TASK_EXECUTION_ID` are distinct identifiers; timeouts must not be handled by blindly resending the message immediately.

### Scenario D — Running Spring Batch Inside a Task

The task is launched via the sink, and Spring Boot then executes a Spring Batch Job. **`TaskRepository`** stores the process run; **`JobRepository`** stores `JobExecution`/`StepExecution`, checkpoints, and Batch status.

**Design:** pass `JobParameters` compatible with your Spring Boot/Batch version and monitor both repositories. If the Job runs asynchronously and the task runner returns early, `TaskExecution` may look finished before the Batch data actually completes.

## 10. Common Errors and How to Investigate

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Sink reports wrong payload type | Message was not converted to `TaskLaunchRequest` or binder/converter misconfigured | Check content type, schema, serialization, and trusted types |
| `getUri()` string looks right but launch fails | Artifact missing, unsupported URI scheme, Maven repo unreachable | Check resource resolution and `TaskLauncher` logs |
| Sink does not create a process | No valid `TaskLauncher` bean, missing permissions/namespace, or deployment error | Check beans/config and platform logs |
| Process runs but lacks `--businessDate` | Producer built `commandlineArguments` incorrectly, or launcher forwarded args improperly | Inspect request at trusted boundary and actual process command |
| Environment variable missing inside task | Wrong key name, deployment didn't propagate env as expected, profile override | Safely inspect deployer config and process environment |
| `deploymentProperties` ignored or errors out | Using keys from another deployer or version | Verify the official property list of the active `TaskLauncher` |
| Pod name differs from `TASK_NAME` | Launcher `applicationName` and `spring.cloud.task.name` do not match | Cross-check task configuration and ID logs |
| Launch accepted but no `TaskExecution` | Process failed before bootstrap, broken DataSource/schema, worker never scheduled | Inspect infrastructure, startup logs, and metadata connectivity |
| Two tasks share the same work key | Broker redelivery, retries, duplicate API calls | Inspect request IDs, idempotency/locks, and process count |
| `TaskExecution` has no `END_TIME` | Task still running, killed, or failed to write completion | Cross-check PID/Pod, logs, and business state; do not conclude from metadata alone |
| API reports success too early | Confusing publish/launch accepted with task completed | Use multi-phase status and verify final business output |

### Investigation Workflow for a Launch Request

1. Confirm the client **was authorized** to request this task and the input has a clear business key.
2. Locate the **request ID/correlation ID** at the API or producer.
3. Verify the message reached the right destination, with the right type/schema, and was acknowledged by the consumer or sent to a dead-letter queue.
4. Check whether the sink **actually called `TaskLauncher`** with the approved artifact and deployment options.
5. Find the infrastructure ID and process/container status; do not equate it with the `TaskRepository` execution ID.
6. Correlate task bootstrap timestamps, business logs, and `TASK_EXECUTION` rows by actual name/ID.
7. Confirm `END_TIME`, exit code, error messages, and **business output**.
8. If there was a timeout or uncertainty about whether launch occurred, **reconcile before retrying** to avoid spawning two unintended processes.

## 11. Practice Verifying the Request Structure

You can start with a lab **requiring no real deployment** to verify object correctness:

**Test 1 — Valid request**

~~~java
TaskLaunchRequest request =
        LaunchRequestFactory.dailyClose(
                "tenant-a", "2026-11-23");

assert request.getUri().contains("daily-close");
assert request.getApplicationName().equals("daily-close");
assert request.getCommandlineArguments().size() == 3;
assert request.getEnvironmentProperties()
              .get("SPRING_PROFILES_ACTIVE").equals("task");
assert request.getDeploymentProperties().isEmpty();
~~~

Java `assert` statements only execute when JVM assertions are enabled (`-ea`). In a real project, use JUnit `assertEquals`/`assertThrows` for reliable tests that do not depend on VM flags.

**Test 2 — Invalid value**

~~~java
try {
    LaunchRequestFactory.dailyClose(
            "TENANT WITH SPACES", "2026-11-23");
    throw new AssertionError("Expected invalid tenantId");
}
catch (IllegalArgumentException expected) {
    // Input was rejected.
}
~~~

Also test invalid dates, missing arguments, and tenants outside the user's permissions. Never let consumers accept arbitrary artifact URIs or deployment properties from untrusted inputs.

**Test 3 — Integration with an Actual Stream Branch**

1. Choose a **compatible** set of Spring Boot, Cloud Task, Cloud Stream, and Deployer versions, and confirm `@EnableTaskLauncher`/sink is present.
2. Configure a valid `TaskLauncher` for the test environment and a binder capable of transporting `TaskLaunchRequest` payloads.
3. Send a `Message<TaskLaunchRequest>`; verify the sink calls the expected launcher via observation or mocking in an integration test.
4. Send an invalid payload type or disallowed artifact; verify error handling and dead-letter/retry without spawning an unintended process.
5. Launch a small task application with a finitely terminating `ApplicationRunner` and a persistent `TaskRepository`.
6. Query `TaskExecution`, exit code, and business data; verify you do not treat the `TaskLauncher` response as the final outcome.
7. Resend the same work key and verify idempotency/reconciliation logic.

### Pre-Production Checklist

- [ ] Understand this is the **Spring Cloud Stream / TaskLauncherSink branch**, not a mandatory API for every task.
- [ ] `TaskLaunchRequest` contains all five fields with the matching Java types.
- [ ] Artifact `uri` is chosen from an allowlist using a scheme supported by the deployer.
- [ ] `commandlineArguments` are validated and contain no secrets.
- [ ] `environmentProperties` contain only permitted environment values.
- [ ] `deploymentProperties` use exact keys for the actual `TaskLauncher` implementation.
- [ ] `applicationName` is explicit and not mixed up with business keys or `TaskExecution` IDs.
- [ ] Producer/sink round-trip payload serialization is tested with exact types/schemas, without arbitrary deserialization.
- [ ] `TaskLauncher` bean, binder, infrastructure permissions, and artifact repository config are in place.
- [ ] Correlation/request IDs trace across messages, platform processes, and `TaskRepository`.
- [ ] Business success is never reported solely upon message publish or launch acceptance.
- [ ] Broker redeliveries and retries are handled safely with idempotency/reconciliation.
- [ ] Metrics, timeouts, dead-letter handling, and resource limits are configured as required.
- [ ] If running Spring Batch, `TaskExecution` is distinguished from `JobExecution`.

## 12. Key Takeaways

**`TaskLaunchRequest` represents launch request data in Spring Cloud Task's supported Spring Cloud Stream API branch**, consisting of five fields: **`uri`**, **`commandlineArguments`**, **`environmentProperties`**, **`deploymentProperties`**, and **`applicationName`**. `TaskLauncherSink` receives valid objects, while `TaskLauncher` is responsible for creating the task on the infrastructure. Only after the spawned task runs does it record a **`TaskExecution`** in `TaskRepository`.

When designing systems, separate **request accepted**, **process created**, **task finished**, and **business succeeded** into distinct states. Strictly control artifacts, arguments, environment, deployment properties, and publish permissions; use business keys, idempotency, and observability so the application can re-run safely if messages or requests are duplicated.

### References

- [Spring Cloud Task — Spring Cloud Stream Integration: Launching a Task](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/stream.html)
- [Spring Cloud Task 3.0.4 API — TaskLaunchRequest](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html)
- [Spring Cloud Task 3.0.4 API — EnableTaskLauncher](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/annotation/EnableTaskLauncher.html)
- [Spring Cloud Task Reference Guide — Launching a Task from a Spring Cloud Stream](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud Deployer — TaskLauncher API and deployment concepts](https://docs.spring.io/spring-cloud-deployer/docs/current/reference/html/)
