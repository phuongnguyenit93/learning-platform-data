# Configuring Memory, Timeout, Ephemeral Storage, and CPU Architecture

## Learning Objectives

After this lesson, you will be able to:

- Explain the relationship between memory, CPU, execution duration, and cost in AWS Lambda.
- Estimate required memory for a Java function, distinguishing the Java heap from total execution environment memory.
- Set timeouts according to workload characteristics, caller deadlines, and downstream dependency durations.
- Use `/tmp` and configure ephemeral storage sized appropriately for temporary data.
- Choose `x86_64` or `arm64` based on performance, cost, and dependency compatibility.
- Measure, benchmark, and tune configurations using metrics rather than guesswork.
- Manage these configurations with AWS SAM, CloudFormation, or the AWS CLI.

## 1. Why Lambda Resource Configuration Matters

AWS Lambda runs functions inside execution environments managed by the platform. Developers do not manage physical servers, yet they must still select resource and time limits for each function. Those choices directly affect throughput, latency, reliability, and cost.

A Java function processing images might need substantial memory and temporary disk space to decompress, resize, and write output. An HTTP function that only validates a token and reads a single record may need far fewer resources. A function running CPU-intensive algorithms can finish significantly faster when given more memory because Lambda allocates more CPU capacity alongside memory.

Four configuration areas to understand:

1. **Memory:** the memory limit allocated to each execution environment, which also determines the function's CPU and network capacity.
2. **Timeout:** the maximum duration a single invocation is permitted to run.
3. **Ephemeral storage:** temporary disk capacity mounted at `/tmp`.
4. **CPU architecture:** the processor architecture the function runs on, typically `x86_64` or `arm64`.

These settings are related but do not substitute for one another. Increasing memory does not increase configured `/tmp` capacity; increasing ephemeral storage does not enlarge the Java heap; increasing timeout does not give the function more CPU. Setting each limit accurately lets the function complete its work without consuming unnecessary resources.

## 2. AWS Lambda Resource Model

An invocation runs inside an execution environment with its own resources and limits. Lambda can spin up multiple environments to handle concurrency. Therefore, a function's configuration must be evaluated at two levels:

- **Per environment:** memory, proportional CPU, `/tmp`, timeout, and runtime limits.
- **Whole function:** concurrent invocations, aggregate resource consumption, database connections, and load placed on downstream dependencies.

~~~mermaid
flowchart TD
    A[Lambda function configuration] --> B[Execution environment]
    B --> C[Memory allocation]
    B --> D[CPU capacity follows memory]
    B --> E[Ephemeral storage /tmp]
    B --> F[Invocation timeout]
    A --> G[CPU architecture]
    G --> H[x86_64 or arm64]
    I[Concurrency] --> J[Multiple execution environments]
    J --> B
~~~

For example, a function configured with 2 GB of memory and concurrency of 100 can have roughly 100 execution environments running concurrently when load and quotas permit. Each environment gets the memory and `/tmp` limits configured on the function. The aggregate impact on databases, external APIs, and shared services can be far greater than a single invocation alone.

Lambda may reuse an execution environment for subsequent invocations. This allows reusing the runtime, loaded classes, and properly initialized connections. However, you must never assume a subsequent invocation will land on the same environment, nor treat environment memory or `/tmp` as a shared data store.

### 2.1. Common Configuration Limits

Common Lambda limits to keep in mind:

| Configuration | Common configuration range | Default and increment | Meaning |
|---|---:|---|---|
| Memory | 128 MB to 10,240 MB | 128 MB; 1 MB increments | Memory allocated to the execution environment |
| Timeout | 1 second to 900 seconds | 3 seconds; 1 second increments | Maximum duration of a single invocation |
| Ephemeral storage | 512 MB to 10,240 MB | 512 MB; 1 MB increments | Temporary disk space at `/tmp` |
| CPU architecture | `x86_64` or `arm64` | Default `x86_64` | CPU architecture of the environment |

Limits, supported runtimes, and quotas can change over time or vary by integrated service. Check current AWS documentation and regional quotas during actual deployment. The values in the table show common configuration ranges to explain design concepts and do not replace verifying current limits.

Memory and ephemeral storage are typically configured in MB. Timeout is configured in seconds. Architecture is a function-level choice, not a parameter changed per invocation.

## 3. Memory Configuration and Its Impact on CPU

Memory is one of the most consequential Lambda settings. The memory value does more than cap how much RAM a function can use. Lambda also scales allocated CPU capacity proportionally with memory. Thus, raising memory can make a CPU-intensive task finish faster without changing a single line of code.

### 3.1. Memory Is More Than Just the Java Heap

Total memory consumed by a Java process can include:

- Java heap holding objects, collections, buffers, and application data.
- Metaspace holding class metadata.
- Thread stacks for active threads.
- Direct byte buffers and native memory regions.
- JIT compiler, code cache, and JVM runtime structures.
- Native libraries, JNI, and related OS/runtime components.
- Memory used for TLS, compression, serialization, drivers, and client SDKs.

Consequently, you cannot set the Java heap equal to the entire Lambda memory limit. If the heap occupies nearly the full limit, the process can still run out of memory when the runtime needs native memory allocations, spawns threads, or allocates off-heap buffers.

For instance, a function allocated 1,024 MB does not mean it is safe to set `-Xmx1024m`. Maximum heap must leave room for metaspace, thread stacks, direct buffers, and other native areas. Exact headroom depends on framework, thread count, libraries, and workload characteristics; measure in an environment close to production.

### 3.2. Lambda Allocates CPU Proportionally to Memory

Lambda increases CPU allocation as the selected memory increases; network throughput may also scale with memory. A commonly cited reference point is roughly 1,769 MB of memory corresponding to one vCPU under Lambda's allocation model. This is a reference point for understanding proportional scaling, not a guarantee that every task continuously utilizes a full core or achieves fixed bandwidth.

Increasing memory can improve:

- Compression/decompression, encryption, and hashing tasks.
- Image resizing, media transcoding, and data processing.
- Serialization/deserialization of large payloads.
- CPU-intensive computation or analytics tasks.
- Initialization time of certain Java frameworks when CPU is the bottleneck.

For mostly I/O-bound workloads, raising memory may not reduce latency significantly if the database, network, or external service is the bottleneck. Still, additional CPU can speed up pre- and post-I/O processing stages.

### 3.3. Higher Memory Can Lower Total Cost

Lambda compute cost depends on allocated memory and execution duration. Increasing memory raises the unit price per unit of time, but if the function finishes sufficiently faster, the cost per request can actually drop.

Illustrative example assuming the same task:

| Configuration | Memory | Duration | Memory × duration |
|---|---:|---:|---:|
| A | 1,024 MB | 1.0 second | 1,024 MB-seconds |
| B | 2,048 MB | 0.45 seconds | 921.6 MB-seconds |
| C | 3,072 MB | 0.35 seconds | 1,075.2 MB-seconds |

In this example, configuration B finishes faster and has a lower memory-time product than A. C is faster than B but has a higher memory-time product. This is only a qualitative comparison; actual cost also depends on architecture, request count, billed duration rounding, ephemeral storage, free tier, and current pricing.

Do not pick the lowest memory setting merely to minimize the per-millisecond rate. For some workloads, more memory cuts duration, raises throughput, and reduces how long database connections are held. Compare cost per successful task alongside latency and error rate.

### 3.4. Signs Memory Is Too Low

Common indicators include:

- Logs show `java.lang.OutOfMemoryError: Java heap space`.
- Runtime reports native memory exhaustion or inability to create threads.
- Execution environment is terminated abruptly when memory usage hits the limit.
- `Max Memory Used` consistently approaches allocated memory.
- Large payloads or large batches fail while small inputs run normally.
- Frequent garbage collection with rising pause times and degrading duration.

`OutOfMemoryError` does not always mean the heap is too small. It can stem from direct buffers, metaspace, threads, or native allocations. Conversely, the OS may terminate the process for exceeding total memory without producing a clear Java stack trace.

Distinguish memory errors from timeout errors. A function can time out with plenty of spare memory; adding memory helps if CPU is the bottleneck, but will not fix a hung database query or an infinite wait loop.

### 3.5. Estimating Memory for a Java Function

There is no single optimal memory value for every Java function. Start by identifying consumption components:

1. Measure footprint once the runtime and framework have initialized.
2. Measure heap while processing representative payloads.
3. Measure thread count and stack sizes.
4. Measure direct buffers/native memory if the app uses NIO, Netty, compression, or native libraries.
5. Measure peak memory when processing the largest permitted batch.
6. Leave headroom for load spikes, class loading, and error/retry branches.

A Spring/Quarkus/Micronaut function has a different footprint from plain Java. A handler parsing a small JSON differs from one extracting files or processing images. Benchmark with the exact artifact, runtime, framework, dependencies, and expected payload sizes for deployment.

## 4. Configuring Timeout and Time Budgets

Timeout limits how long a single invocation is allowed to execute. When the limit is exceeded, Lambda terminates the invocation. Timeouts protect the system from hung functions and bound processing time, but setting one too low causes valid tasks to fail; setting one too high ties up resources and forces clients to wait too long.

### 4.1. Choosing Timeout by Workload

Lambda's default timeout is typically 3 seconds and can be configured up to 900 seconds (15 minutes). Each function should have a timeout based on its actual execution time distribution:

- Functions handling HTTP auth and small data reads usually need short timeouts.
- Functions processing images or files may need longer timeouts depending on input size.
- Functions calling external APIs must account for connection time, response time, and retries.
- Batch-processing functions must account for the largest permitted batch, not just the average case.
- Functions running exports or long workflows should move to an asynchronous pattern rather than holding an HTTP invocation open for a long duration.

Do not use the maximum timeout as a default for every function. A longer timeout does not make a function run faster; it only allows a stuck invocation to hold resources longer before termination.

### 4.2. End-to-End Time Budgets

A request may traverse several layers:

~~~mermaid
flowchart LR
    A[Client deadline] --> B[API Gateway]
    B --> C[Lambda timeout]
    C --> D[HTTP client timeout]
    D --> E[Database or external API]
~~~

Deadlines across layers must align. If the client only waits 10 seconds while Lambda is configured for 60 seconds, the client may drop the request while the function continues running. The function keeps writing data or calling external services even though the client already timed out.

A useful rule of thumb is:

`function deadline < caller deadline - response margin`

Dependency call timeouts should be shorter than the remaining invocation time. Leave margin to write logs, close resources, persist state, and return a response. Never configure an HTTP client with a timeout longer than the time Lambda has left to run.

Across a multi-service chain, budget time for each step. For instance, if a request has an 8-second deadline, do not give the database an 8-second timeout and expect time afterward to serialize the response. Reserve time for authentication, queries, processing, and response marshaling.

### 4.3. Reading Remaining Time in Java

The AWS Lambda Java runtime provides `Context`, which exposes `getRemainingTimeInMillis()`. Handlers can use this value to avoid starting a new step when insufficient time remains:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public final class ReportHandler
        implements RequestHandler<ReportRequest, ReportResponse> {

    @Override
    public ReportResponse handleRequest(
            ReportRequest request,
            Context context) {

        int remaining = context.getRemainingTimeInMillis();

        if (remaining < 2_000) {
            throw new IllegalStateException(
                    "Not enough invocation time to start report generation");
        }

        return generateReport(request, remaining, context);
    }

    private ReportResponse generateReport(
            ReportRequest request,
            int remainingMillis,
            Context context) {
        // Propagate deadline down to repositories and HTTP clients.
        return new ReportResponse("accepted");
    }
}
~~~

This is an illustrative example; in real applications, use exceptions and error mappings matching the trigger contract. `getRemainingTimeInMillis()` reflects the remaining invocation time, not the client's deadline. If a caller deadline is passed, compare both and enforce the shorter limit.

Do not check remaining time only at the start of the handler. One step may take longer than anticipated; check before long operations, pass remaining timeout down to HTTP/database clients, and avoid retrying if insufficient budget remains.

### 4.4. Timeouts Do Not Automatically Cancel External Side Effects

When Lambda times out, the invocation stops, yet an external system may have already received the request and continued processing. For example, the function sends a shipment creation request, the shipping service succeeds, and the response fails to arrive in time. If the function is retried, a second shipment could be created.

For operations with side effects:

- Use a stable idempotency key per business operation.
- Set explicit connect and read timeouts on HTTP clients.
- Query operation status before retrying when the previous outcome is uncertain.
- Record operation IDs for post-timeout lookup.
- Avoid treating a timeout as proof that the operation failed.

Function timeout also does not replace database statement, socket, or SDK timeouts. Each dependency needs its own timeout so the invocation can terminate cleanly.

### 4.5. Timeouts and Trigger Types

How timeouts are handled depends on the invocation source:

- **Synchronous HTTP:** the caller usually receives an error or timeout and may retry. Idempotency is needed to prevent duplicate effects.
- **Asynchronous invocation:** Lambda applies retries based on configuration and error type; the event may be re-sent.
- **Queue/event source mapping:** messages may be redelivered if the batch is not acknowledged successfully. One failing message may affect others in the batch depending on partial batch response configuration.
- **Workflow engine:** task timeouts can transition state to retry/catch/failure paths defined in the workflow.

With Amazon SQS, visibility timeout must be long enough so messages are not redelivered while the prior run is still executing. AWS guidelines commonly recommend a visibility timeout at least six times the function timeout, plus any batching window. Verify current guidance for your event source mapping and retry settings.

### 4.6. When to Move to Asynchronous Processing

If a request must process tens of thousands of records, export large files, invoke multiple child workflows, or wait minutes on external systems, separate request intake from execution:

1. HTTP handler authenticates and creates a job.
2. Handler persists job state and starts a workflow/queue task.
3. Handler returns `202 Accepted` with a `jobId` or status lookup URL.
4. Worker processes in batches under bounded concurrency.
5. Client polls status or receives a notification when the job finishes.

This keeps HTTP invocations short and lets workflows manage their own timeouts, retries, and checkpoints. Lambda's maximum timeout should not be treated as a long-running job orchestrator.

## 5. Ephemeral Storage and the /tmp Directory

Lambda provides temporary disk storage per execution environment at `/tmp`. This serves as scratch space for intermediate files needed during processing.

### 5.1. Capacity and Characteristics

Default ephemeral storage is 512 MB and can be configured up to 10,240 MB. This capacity is provisioned per execution environment. Different environments do not share `/tmp`.

Key traits to remember:

- Files in `/tmp` may persist when an environment is reused for a subsequent warm invocation.
- Environments can be reclaimed at any time; there is no guarantee temporary data survives future initializations.
- `/tmp` contents are not shared across concurrent environments.
- This is not durable storage and does not replace S3, EFS, or databases.
- Stale data must be cleaned up; never assume each invocation starts with an empty directory.

Lambda encrypts ephemeral storage data at rest. Even so, applications should restrict access, avoid writing unnecessary secrets or sensitive data, and delete temporary files upon completion.

### 5.2. When to Increase Ephemeral Storage

Scenarios often requiring larger `/tmp` capacity:

- Downloading compressed archives from S3 and extracting them before processing.
- Generating intermediate CSV, PDF, ZIP, or report files.
- Transcoding audio/video with tools like FFmpeg.
- Resizing or stitching multiple large images.
- Loading models or reference datasets for in-invocation processing.
- Using libraries that only work with files rather than streams.

If stream processing is feasible, writing everything to disk may be unnecessary. For example, streaming object reads and streaming output writes can cut both temporary disk and memory usage. However, streaming can be more complex if a library requires seeking or the complete input file upfront.

### 5.3. Distinguishing Memory and Ephemeral Storage

| Requirement | Configuration/resource |
|---|---|
| JVM objects, collections, and buffers | Memory, specifically Java heap |
| Metaspace, thread stacks, and native allocations | Total process memory |
| Intermediate files on disk | Ephemeral storage at `/tmp` |
| Data that must persist after invocation | S3, EFS, or database |
| Data shared across multiple environments | Shared storage services like S3/EFS/database |

Increasing `/tmp` does not increase the Java heap. Increasing memory does not automatically raise `/tmp` capacity. A function can have plenty of heap yet run out of disk, or have plenty of disk yet hit `OutOfMemoryError`.

### 5.4. Managing Temporary Files in Java

The following example checks available space, creates a temporary file, and deletes it after processing:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TemporaryFileService {

    public Path createTemporaryFile() throws IOException {
        Path tempDirectory = Path.of("/tmp");
        FileStore fileStore = Files.getFileStore(tempDirectory);

        long usableBytes = fileStore.getUsableSpace();
        long requiredBytes = 100L * 1024 * 1024;

        if (usableBytes < requiredBytes) {
            throw new IOException("Insufficient ephemeral storage");
        }

        return Files.createTempFile(
                tempDirectory, "lambda-work-", ".bin");
    }

    public void process() throws IOException {
        Path tempFile = createTemporaryFile();

        try {
            // Write or download data into tempFile.
            // Process the file and store results durably in S3/database.
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

This is a skeleton example. For real read/write streams, use try-with-resources to close streams and always delete files in `finally`. If a file must stay across steps within the same invocation, delete it only after the final step finishes using it.

Do not construct filenames solely from client input because two concurrent executions or tasks could collide or overwrite each other. Use `Files.createTempFile` or unique names per invocation/task ID. Do not rely solely on end-of-invocation cleanup for safety: the process could be terminated before `finally` runs, so also clean up stale files when an environment is reused.

### 5.5. Controlling Capacity and File Lifecycle

When using `/tmp`:

- Estimate input file size, extracted file size, and output file size; all may coexist simultaneously.
- Account for library temp files, caches, and parallel tasks within the same environment.
- Check `getUsableSpace()` before starting large operations.
- Delete files once no longer needed and purge stale files safely.
- Avoid loading entire files into the heap when streaming is possible.
- Enforce input file size limits to prevent abnormal requests from filling disk.
- Monitor `/tmp` usage via custom metrics or logs; Lambda does not automatically emit detailed per-file application usage metrics.

If multiple tasks run concurrently inside one invocation, sum the temporary space all tasks can consume. Limiting local concurrency also prevents parallel tasks from exhausting `/tmp` simultaneously.

## 6. Choosing CPU Architecture: x86_64 or arm64?

AWS Lambda supports two common CPU architectures: `x86_64` and `arm64`. The chosen architecture is set at the function level and determines the type of execution environment Lambda provisions. For Java, JVM bytecode is generally portable across both architectures, though not every dependency and artifact is automatically compatible.

### 6.1. Comparing the Two Architectures

| Criterion | `x86_64` | `arm64` |
|---|---|---|
| CPU platform | x86-64 processors | AWS Graviton2 processors |
| Native ecosystem | Very broad, often default for older libraries | Requires dependencies or binaries with ARM64 builds |
| Pure Java bytecode | Usually runs | Usually runs |
| JNI/native libraries | Must have compatible x86-64 binaries | Must have compatible ARM64 binaries |
| Price/performance | Depends on workload and pricing | May offer price/performance advantages |
| Decision | Choose when required by dependencies or benchmarks | Benchmark when optimizing cost/performance |

`arm64` on Lambda runs on AWS Graviton2 processors. Many workloads achieve strong performance and cost efficiency on ARM64, though you should not assume ARM64 is always faster. Results depend on instruction mix, native libraries, runtime optimizations, memory, I/O, and data characteristics.

### 6.2. Java Bytecode and Native Libraries

Java bytecode inside a JAR is usually CPU-architecture independent. If a function uses only the Java standard library and pure-Java dependencies, switching architectures is typically straightforward.

Verify these components carefully:

- JNI libraries packaged inside JARs or layers.
- Compression, image processing, media, or cryptography libraries containing native binaries.
- Drivers or SDKs using native acceleration.
- Java agents or profilers with native components.
- Executables invoked from Java via `ProcessBuilder`.
- GraalVM native executables or AOT-compiled artifacts.
- Container images and Lambda layers holding architecture-specific binaries.

For example, a JAR might include an `.so` library built for x86-64. The JAR builds cleanly on a developer machine, yet the `arm64` function fails at library load time with an architecture mismatch error. Verify that packaged binaries match the target format, ABI, and architecture.

### 6.3. Container Images and Lambda Layers

If a function uses a container image, the image must support the architecture configured on Lambda. Do not assume an image built on an x86 machine runs unmodified on ARM64 if it contains native binaries.

When building images for ARM64, specify the target platform in the Docker build pipeline and verify the manifest/image architecture. For Lambda layers, inspect layer contents and architecture compatibility metadata; layers containing native binaries must be built for the same architecture as the function.

A pure-Java package can be shared across both architectures, yet build/release pipelines should still verify actual dependencies and artifacts. If producing two image or layer variants, label them clearly to prevent deploying the wrong variant.

### 6.4. Detecting Architecture in Java

You can log runtime diagnostics at startup:

~~~java
public final class RuntimeDiagnostics {

    public static void logRuntime() {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("maxHeapBytes=" + runtime.maxMemory());
        System.out.println("totalHeapBytes=" + runtime.totalMemory());
        System.out.println("freeHeapBytes=" + runtime.freeMemory());
    }
}
~~~

On ARM64, `os.arch` typically reports values like `aarch64`; on x86-64 it may report `amd64`. Exact strings depend on the JVM. `availableProcessors()` reflects the CPUs visible to the JVM, but should not be treated as a guarantee of physical cores or sustained parallel capacity.

Do not log sensitive diagnostic details or environment variables containing secrets. The values above are useful for verifying the environment during benchmarking and incident investigation.

### 6.5. Process for Choosing an Architecture

A safe workflow:

1. Inventory dependencies, layers, containers, and native executables.
2. Verify artifacts have builds compatible with the target architecture.
3. Deploy a test version using identical memory, timeout, and representative data.
4. Measure cold starts, warm duration, memory, error rate, and throughput.
5. Run both CPU-intensive and I/O-bound workloads if the function serves mixed request types.
6. Compare cost per successful request using current pricing.
7. Shift traffic gradually via alias or test environment, watching for errors before full cutover.

Do not compare ARM64 against x86-64 using two runs with different memory, payloads, or concurrency levels. Otherwise you cannot tell whether differences stem from architecture or from the other settings.

## 7. Configuring with AWS SAM and AWS CLI

Memory, timeout, ephemeral storage, and architecture should be managed as reviewable, version-controlled deployment configuration. Avoid making manual tweaks in the Console and leaving IaC templates out of sync with what is running.

### 7.1. AWS SAM Example

The following example configures a Java function using ARM64, 2 GB memory, a 45-second timeout, and 2 GB ephemeral storage:

~~~yaml
Resources:
  ImageProcessorFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: target/function.zip
      Handler: com.example.ImageHandler
      Runtime: java21
      Architectures:
        - arm64
      MemorySize: 2048
      Timeout: 45
      EphemeralStorage:
        Size: 2048
      ReservedConcurrentExecutions: 20
~~~

Meaning:

- `MemorySize: 2048`: allocates 2,048 MB memory per execution environment.
- `Timeout: 45`: caps a single invocation at 45 seconds.
- `EphemeralStorage.Size: 2048`: allocates 2,048 MB to `/tmp` per environment.
- `Architectures: [arm64]`: selects ARM64 architecture.
- `ReservedConcurrentExecutions: 20`: sets reserved concurrency for the function, controlling downstream load in this example.

Values are illustrative only. Do not copy them to production without measuring peak memory, processing duration, file sizes, and downstream capacity. If the function does not need large `/tmp`, keeping the default is simpler and cheaper.

### 7.2. Updating Configuration via AWS CLI

Example run in a Bash shell:

~~~bash
aws lambda update-function-configuration \
  --function-name image-processor \
  --memory-size 2048 \
  --timeout 45 \
  --ephemeral-storage '{"Size":2048}' \
  --architectures arm64
~~~

Read back configuration after updating:

~~~bash
aws lambda get-function-configuration \
  --function-name image-processor \
  --query '{Memory:MemorySize,Timeout:Timeout,Storage:EphemeralStorage.Size,Architectures:Architectures}'
~~~

The update command may return while the configuration update is still in progress. Wait until the function reaches a ready state before running benchmarks or shifting traffic. When changing architecture, confirm code packages, layers, and container images are compatible with the new architecture.

### 7.3. Configuring in the Console

In the AWS Lambda Console:

1. Open the target function.
2. Go to **Configuration**.
3. Select **General configuration** to adjust memory and timeout.
4. Select **Ephemeral storage** to modify `/tmp` capacity.
5. Select **Architecture** to view or change `x86_64`/`arm64`.
6. Save configuration, wait for the update to complete, and verify with a test invocation.

Some label names and positions may vary across console UI versions. When managing functions via IaC, update the corresponding template so future deployments do not overwrite manual changes.

### 7.4. Published Versions and Aliases

Lambda configuration belongs to a function version. When using published versions, a published version retains the configuration captured at release time. If you change memory, timeout, ephemeral storage, or architecture on `$LATEST`, publish a new version and update the alias so traffic uses the new configuration.

A controlled release workflow:

1. Update the template and build a compatible artifact.
2. Deploy to `$LATEST` or a test environment.
3. Run smoke tests and benchmarks with representative payloads.
4. Publish a new version.
5. Point the alias to the new version or use a weighted alias for gradual traffic shifting.
6. Monitor errors, duration, memory, and dependency load.
7. Roll back the alias if a regression is detected.

Aliases decouple clients from specific version numbers and support controlled traffic shifting and rollbacks. Changing configuration without checking which version and alias serve live traffic is a common reason teams benchmark one configuration while production runs another.

## 8. Measuring Memory, Timeout, and /tmp in Java

Good configurations must be backed by metrics from actual function executions. Lambda reports metrics on duration, errors, throttles, and concurrency; invocation logs display configured memory size and peak memory used. For ephemeral storage, applications should measure remaining space themselves if detailed visibility is needed.

### 8.1. Metrics and Logs to Monitor

| Indicator | Observation source | How to use |
|---|---|---|
| `Duration` | CloudWatch Metrics | Track latency and percentiles |
| `Errors` | CloudWatch Metrics | Detect failed invocations |
| `Throttles` | CloudWatch Metrics | Detect concurrency/quota exhaustion |
| `ConcurrentExecutions` | CloudWatch Metrics | Track concurrent execution levels |
| `Init Duration` | Lambda REPORT log | Track initialization overhead |
| `Max Memory Used` | Lambda REPORT log | Compare peak memory against allocation |
| `/tmp` usable space | Custom log/metric | Detect risk of exhausting ephemeral storage |
| Timeout count | Application logs/metrics | Detect functions hitting deadlines |
| Downstream latency | Dependency traces/metrics | Distinguish CPU bottlenecks from I/O bottlenecks |

Default CloudWatch Metrics do not expose detailed per-file `/tmp` usage. If needed, record `FileStore.getUsableSpace()` and emit custom metrics carefully. Avoid high-cardinality metric dimensions such as `requestId` or `itemId`.

### 8.2. Logging Heap and Temporary Storage

Java example:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceSnapshot {

    public static void log() throws IOException {
        Runtime runtime = Runtime.getRuntime();
        FileStore tempStore = Files.getFileStore(Path.of("/tmp"));

        System.out.println("heap.max.bytes=" + runtime.maxMemory());
        System.out.println("heap.total.bytes=" + runtime.totalMemory());
        System.out.println("heap.free.bytes=" + runtime.freeMemory());
        System.out.println("tmp.usable.bytes=" + tempStore.getUsableSpace());
        System.out.println("cpu.visible="
                + runtime.availableProcessors());
        System.out.println("architecture="
                + System.getProperty("os.arch"));
    }
}
~~~

`Runtime.maxMemory()` is the heap limit available to the JVM, not Lambda's total memory. `freeMemory()` is likewise not the execution environment's remaining RAM; it only reports currently unused space inside the already-allocated heap. To observe total memory, combine REPORT logs, Lambda Insights, or appropriate monitoring tools.

Log snapshots at meaningful points such as post-initialization, before/after large batches, or when processing large files. Logging inside every loop iteration is unnecessary and increases log cost and noise.

### 8.3. Reading the REPORT Log

A REPORT line displays fields such as `Duration`, `Billed Duration`, `Memory Size`, and `Max Memory Used`. When analyzing:

- If `Max Memory Used` approaches `Memory Size`, test higher memory or reduce peak allocations/batch size.
- If memory has headroom yet `Duration` is high, inspect CPU, I/O, locks, retries, and dependency latency.
- If `Init Duration` is high, examine framework overhead, class loading, dependency initialization, and cold starts.
- If the function times out, check the last completed step, caller deadline, and dependency timeouts.
- If logs show insufficient disk errors, inspect existing files, `/tmp` capacity, and leftover files from prior invocations.

Do not inspect just a single invocation. Examine distributions over time and payload sizes: p50, p95, p99, worst-case inputs, cold starts, and warm invocations.

## 9. Configuration Tuning Workflow

Tuning is the process of finding settings that meet workload latency, reliability, and cost goals. Changing one parameter can affect several others. For example, raising memory raises both RAM limits and CPU; if the function runs faster, timeout might be tightened, though it must be re-measured on large payloads and slow dependencies.

### 9.1. Defining a Representative Workload

Before changing configurations, characterize the workload:

- Trigger type: HTTP, SQS, EventBridge, S3, or workflow.
- Typical, p95, and maximum payload sizes.
- Ratio of CPU, I/O, disk, and dependency wait time.
- Items per batch and intra-invocation concurrency.
- Invocation rate, function-wide concurrency, and per-tenant concurrency.
- Latency targets, deadlines, and acceptable error rates.
- Business impacts when retries or timeouts occur.

Do not benchmark with only a small payload. A function that handles a 1 MB file smoothly may run out of memory or `/tmp` on a 200 MB file. Use representative data and boundary inputs matching product limits.

### 9.2. Tuning Memory

A practical process:

1. Pick an initial memory size sufficient to initialize the function and process test payloads.
2. Run the exact same dataset across several memory levels.
3. Hold architecture, runtime, artifact, concurrency, and dependency settings constant across comparisons.
4. Record `Duration`, `Billed Duration`, `Max Memory Used`, error rate, and estimated cost.
5. Repeat for cold starts, warm invocations, and near-production concurrency.
6. Choose a setting that meets latency targets with memory headroom, not merely the setting with the lowest duration.
7. Re-validate after changing dependencies, frameworks, payloads, or thread counts.

You can use AWS Lambda Power Tuning to test multiple memory settings and compare duration/cost. This tool aids decision-making, but results are only meaningful when inputs, concurrency, and test environment represent production.

### 9.3. Tuning Timeout

Set timeout based on high-percentile execution duration and business limits. For example, if function p99 is 4 seconds, a 4-second timeout is not safe; add margin for variance, associated cold starts, internal retries, and response writing.

Key principles:

- Timeout must be shorter than the caller deadline if the caller awaits a synchronous result.
- Dependency timeouts must be shorter than Lambda's remaining time.
- Retries must fit inside the overall time budget.
- The largest permitted batch must finish before timeout or be split smaller.
- If execution time can grow unpredictably, move to an asynchronous job.
- Investigate actual timeouts rather than simply bumping timeout whenever errors appear.

Do not use timeout to throttle system rate. If a dependency is overloaded, longer timeouts hold connections and resources longer, worsening congestion.

### 9.4. Tuning Ephemeral Storage

Estimate peak disk space, not just input file size:

`peak temporary space ≈ input files + extracted files + intermediate files + output files + concurrent workspaces`

For example, a 300 MB ZIP file may extract to 1.2 GB. If the function simultaneously keeps the ZIP, extracted folder, and a 500 MB output file, demand far exceeds 300 MB. If two tasks run concurrently inside one environment, include both workspaces.

Start with 512 MB if the workload is small. Increase gradually when measurements show peak usage needs more space. Leave headroom for library-created temp files and input size fluctuations. Also consider streaming, batching, or staging intermediates in S3 if `/tmp` is unsuitable.

### 9.5. Benchmarking Architecture

To compare `x86_64` and `arm64`, hold constant:

- Memory and ephemeral storage.
- Runtime version and framework.
- Code version, dependencies, and configuration.
- Input dataset, iteration count, and concurrency level.
- Deployment region and downstream dependency conditions.

Measure cold starts separately from warm durations. Measure both latency and cost per successful invocation. If dependencies contain native libraries, check both compatibility and error behavior under high load. A single faster run does not prove an architecture is better if error rate or memory usage climbs.

### 9.6. Sample Benchmark Matrix

| Trial | Architecture | Memory | Timeout | `/tmp` | Goal |
|---|---|---:|---:|---:|---|
| A | `x86_64` | 1,024 MB | 30 seconds | 512 MB | Baseline |
| B | `x86_64` | 2,048 MB | 30 seconds | 512 MB | Measure memory/CPU impact |
| C | `arm64` | 2,048 MB | 30 seconds | 512 MB | Compare architecture |
| D | `arm64` | 2,048 MB | 60 seconds | 2,048 MB | Test large-file workload |

This is an illustrative matrix, not a universal configuration recommendation. When comparing memory, change only memory; when comparing architecture, keep all other parameters equal. Trial D changes both timeout and storage to test a different workload—do not use Trial D's results to isolate architecture impact alone.

## 10. Reference Configurations by Workload Type

The profiles below are starting points for designing experiments. Final values must rest on measurements and application limits.

| Function type | Memory | Timeout | Ephemeral storage | Architecture |
|---|---|---|---|---|
| Small HTTP handler, mostly I/O | Start low and measure | Short per API deadline | Default if no files used | Either; benchmark dependencies |
| Small JSON/batch processing | Based on peak heap and CPU | Based on batch size | Default or low | Either |
| Image resizing/file extraction | Often needs higher memory | Based on file size | Sum of input + output + intermediate | Benchmark both |
| CPU-intensive | Test multiple memory tiers since memory scales CPU | Based on p99 processing time | Increase only if temp files used | Benchmark both |
| Queue-reading worker | Based on payload and messages per batch | Enough for batch without exceeding visibility budget | Based on file handling | Depends on native dependencies |
| Large export/report | Split batches or run asynchronously | Short for intake; worker gets appropriate limit | Based on intermediate files or use S3 | Benchmark by workload |

A small HTTP function may run well on low memory yet still require checking Java runtime and framework cold starts. An image worker may need high memory for CPU and buffers while also needing large `/tmp` for extracted files. Both needs must be measured independently.

## 11. Common Configuration Mistakes

- **Equating memory with Java heap:** setting heap close to total Lambda memory can cause native memory or thread stacks to breach the limit.
- **Throwing memory at every slowness bug:** if the bottleneck is a database or external API, adding memory may not fix the root cause.
- **Setting timeout from average duration:** p99 requests or large batches can time out even when average cases pass.
- **Using long timeouts to mask dependency failures:** the function holds resources longer while downstream services stay unresponsive.
- **Confusing `/tmp` with memory or durable storage:** temporary files have their own limits, can vanish when environments are reclaimed, and are not shared across environments.
- **Forgetting to clean temp files:** subsequent warm invocations can hit disk-full errors due to leftover files.
- **Choosing ARM64 without checking JNI/layers:** the function deploys cleanly yet fails when loading native libraries.
- **Benchmarking with mismatched configs:** changing memory, architecture, and batch size together obscures what caused performance shifts.
- **Ignoring function-wide concurrency:** many concurrent invocations can overwhelm databases or external APIs even when one invocation works fine.
- **Forgetting to update IaC:** Console tweaks get overwritten on the next template deployment.
- **Forgetting published versions/aliases:** traffic may still hit an older version even though `$LATEST` has the new configuration.

## 12. Checklist Before Promoting Configuration to Production

- [ ] Memory suffices for peak heap and native memory with appropriate headroom.
- [ ] Timeout satisfies caller deadlines and p99 workload durations.
- [ ] HTTP/database client timeouts are shorter than remaining Lambda execution time.
- [ ] Retries and idempotency are designed for operations with side effects.
- [ ] `/tmp` capacity covers concurrent input, extracted, intermediate, and output files.
- [ ] Temp files are created with safe unique names, streams are closed, and files are cleaned up.
- [ ] Data requiring persistence is stored in S3/EFS/databases.
- [ ] Architecture is compatible with JARs, layers, container images, JNI, and native executables.
- [ ] Concurrency aligns with quotas and downstream capacity.
- [ ] Cold starts, warm durations, memory, disk, and error rates have been benchmarked.
- [ ] IaC templates accurately reflect the validated configuration.
- [ ] Published versions and aliases point to the validated configuration.
- [ ] Dashboards/alerts cover duration, errors, throttles, concurrency, and memory.
- [ ] Custom logs/metrics track `/tmp` if the workload depends on temporary disk space.

## 13. Self-Check

**Question 1.** Why can increasing Lambda memory make a function run faster even when the Java heap is not the bottleneck?

**Answer hint:** Lambda increases CPU allocation alongside memory. CPU-intensive tasks or serialization, compression, and data-processing stages can finish faster when the function receives more CPU.

**Question 2.** Why should you not set `-Xmx` equal to the full Lambda memory limit?

**Answer hint:** Total memory also includes metaspace, thread stacks, direct buffers, JIT/code cache, and native libraries. Letting the heap consume the entire limit can starve the process of off-heap memory.

**Question 3.** How does ephemeral storage differ from memory?

**Answer hint:** Memory holds data used by the running process/JVM; ephemeral storage is temporary disk space at `/tmp`. Increasing one does not automatically increase the other. `/tmp` is neither durable storage nor shared across execution environments.

**Question 4.** When should you increase timeout versus switching to asynchronous processing?

**Answer hint:** Increase timeout when work has bounded, measurable duration that still fits within caller deadlines. Switch to asynchronous processing when work is long, highly variable, or requires multiple child tasks/batches unsuitable for synchronous HTTP invocations.

**Question 5.** Does Java bytecode run on both `x86_64` and `arm64`?

**Answer hint:** Pure Java bytecode is generally portable across both architectures, but JNI, native libraries, executables, layers, and container images can be architecture-dependent. Verify artifacts and run real benchmarks.

**Scenario exercise:** A Java Lambda downloads a 250 MB ZIP file from S3, extracts it to roughly 900 MB, processes CSVs, and writes a 300 MB output file. The function currently has 1,024 MB memory, a 30-second timeout, and 512 MB `/tmp`. Some invocations fail with `No space left on device` and some time out, while heap never reaches its limit. Propose adjustments to memory, timeout, and ephemeral storage; identify when to stream or batch; explain how to verify architecture and which metrics to monitor.

**Hint:** Current `/tmp` capacity is definitely insufficient if the ZIP, extracted data, and output file coexist. Estimate peak disk space across all concurrent files, raise ephemeral storage accordingly, and clean up files after processing; consider streaming CSVs or writing multipart output to reduce scratch space. Set timeout from p95/p99 large-file processing duration and trigger/caller deadlines; if duration exceeds acceptable synchronous limits, convert to an asynchronous job. Heap not hitting its limit does not mean CPU is sufficient; benchmark higher memory tiers to see if added CPU cuts duration. Verify native dependencies and layers before testing ARM64. Monitor `Duration`, `Max Memory Used`, `Errors`, timeouts, `/tmp` usable space, concurrency, and S3 latency.

## Conclusion

Lambda memory both caps RAM and scales CPU capacity; for Java, leave headroom for both the heap and JVM native regions. Timeouts must align with end-to-end deadlines and dependency timeouts. Ephemeral storage at `/tmp` serves temporary files, follows the execution environment lifecycle, and does not replace durable storage. `x86_64` and `arm64` must be selected based on compatibility and apples-to-apples benchmarks. Managing configuration via IaC, measuring cold/warm invocations, and monitoring peak memory, duration, concurrency, and temporary disk usage help functions achieve the right performance and cost.
