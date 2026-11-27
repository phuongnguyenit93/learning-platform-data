# Comparing CPU Architectures and Selecting a Runtime Through Benchmarking

## 1. Why Benchmark CPU Architecture and Runtime?

A Java function can run on different CPU architectures and runtimes. The same source code can be deployed on `x86_64` or `arm64`; the same Java workload can run on a managed Java runtime, a custom runtime, or a native executable. These choices affect initialization time, execution duration, memory consumption, library compatibility, and cost.

There is no single best architecture or runtime for every function. An API that mostly waits on a database may see almost no change when switching CPUs; a function doing encryption, compression, or image processing may benefit noticeably from a different CPU instruction set and cache layout. A Spring app initializing many beans may be dominated by cold starts; a long-running batch worker may be governed by steady-state throughput after the JVM warms up.

Benchmarks answer these questions with real data:

- Does `arm64` improve latency or price per request compared to `x86_64`?
- Which memory setting best balances allocated CPU, duration, and cost?
- Which managed Java runtime fits your dependencies and support lifecycle?
- Does Native Image cut startup enough to offset build overhead and compatibility limits?
- How do cold starts, warm invocations, throughput, and p95/p99 change?
- Which choice meets the SLO under load and supports safe rollback?

In the CLOUD_SERVERLESS module, CPU/runtime selection must be evaluated alongside FaaS triggers, concurrency, memory, timeouts, dependencies, networking, and cost models. Never conclude from a single run or by looking only at average duration.

## 2. Two Independent Axes: CPU Architecture and Runtime

CPU architecture determines the instruction set and processor type used by the function. Runtime determines how the platform launches the program, receives events, and invokes the handler. The two decisions are related, yet distinct.

| Axis | Common Options | Key Questions |
|---|---|---|
| CPU architecture | `x86_64`, `arm64` | Are code and native dependencies compatible? On which architecture does the workload run faster/cheaper? |
| Java runtime | Managed Java 17/21/25, custom runtime, Native Image | Which JVM features are needed? What are startup, compatibility, and operational impacts? |
| Deployment format | ZIP/JAR, container image | What do artifacts, native libraries, image sizes, and build pipelines require? |
| JVM execution mode | JIT, SnapStart, Provisioned Concurrency | Should you optimize cold starts or steady-state throughput? |

For example, you can run the Java 21 managed runtime on both `x86_64` and `arm64`. You can also package a Java Native Image into an executable running on an OS-only runtime, provided the binary is built for the exact target Linux architecture.

AWS Lambda supports `x86_64` and `arm64` (AWS Graviton) for current managed runtimes. Availability of `arm64` depends on the Region; verify before deploying. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

## 3. Comparing x86_64 and arm64 on AWS Lambda

### x86_64

`x86_64` is the 64-bit x86 family architecture. It is typically the broadest compatibility option for native libraries, agents, extensions, and legacy binaries. If an application depends on a library publishing only x86 artifacts, `x86_64` may be the most practical option until an ARM64 build becomes available.

### arm64 and AWS Graviton

`arm64` is the AArch64 architecture running on AWS Graviton processors. AWS highlights potential benefits such as larger L2 cache per vCPU, faster performance for certain cryptographic operations, and instruction sets helpful for some compute workloads. Graviton can improve price/performance, though outcomes depend on code, runtime, and dependencies. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

AWS manages the underlying hardware and does not guarantee a function always runs on one specific Graviton generation. Applications must be compatible with the `arm64` architecture rather than assuming a fixed chipset.

| Criterion | x86_64 | arm64 |
|---|---|---|
| Processor family | x86 64-bit | ARM 64-bit, AWS Graviton |
| Pure Java bytecode | Usually runs without code changes | Usually runs without code changes |
| JNI/native libraries | Requires x86_64 binary | Requires ARM64 binary |
| Lambda layers/extensions | Must verify each layer/extension | Must have compatible ARM64 builds |
| Container image | Build for `linux/amd64` | Build for `linux/arm64` |
| Legacy dependency compatibility | Generally broader | May require updating native dependencies |
| Performance | Workload-dependent | Can be better on some workloads; must measure |
| Cost | Regional x86 pricing | Regional Arm pricing; may offer a cost advantage |

You cannot infer that `arm64` is faster from synthetic CPU benchmarks alone. A function waiting on I/O, bottlenecked by a database, or suffering framework cold starts may gain little from switching architectures.

## 4. Memory Also Determines CPU on Lambda

On AWS Lambda, users configure memory, and CPU is allocated proportionally to memory. Memory is configurable from 128 MB to 10,240 MB. At 1,769 MB, a function gets the CPU equivalent of one vCPU; the highest tiers provide up to six vCPUs. CPU is not an independently configurable parameter. <https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html>

This means increasing memory can sometimes make a function run substantially faster even when actual heap usage does not rise proportionally. For CPU-bound workloads, more CPU can cut duration. For I/O-bound workloads, adding CPU may improve little because the function is still waiting on the network or database.

For example, suppose a JSON-processing function takes 900 ms at 512 MB and 330 ms at 1,769 MB. The higher memory tier may cost roughly the same or less per invocation if execution time drops enough. Always calculate using actual Regional GB-second and request prices rather than comparing memory sizes alone.

When benchmarking architectures, keep memory identical across both architectures in each comparison pair. Only afterward sweep memory to find the optimal configuration. Changing CPU architecture and memory simultaneously makes it impossible to isolate what drove the difference.

## 5. Classify the Workload Before Benchmarking

Before picking a test matrix, identify which resource limits the function.

| Workload Type | Symptoms | What to Benchmark |
|---|---|---|
| CPU-bound | Computation, compression, encryption, image processing, heavy parsing; CPU busy during handler | Architecture, memory/CPU, JIT/native code, throughput |
| Memory-bound | Heap or native memory near limit, frequent GC, OOM | Memory, allocation rate, GC, object lifetimes |
| I/O-bound | Most time spent waiting on databases, HTTP, or object storage | Connection pools, network, concurrency, retries; CPU architecture may matter little |
| Cold-start-bound | Large `Init Duration`, high p99 latency on new environments | Runtime, framework startup, SnapStart, Native Image, Provisioned Concurrency |
| Batch-bound | Many records per invocation, long durations, large batches | Throughput per batch, memory, parallelism, partial failures |
| Burst-bound | Sudden traffic spikes, rapid concurrency climb | Scale-out latency, throttling, connection pressure, and queue age |

Do not use synthetic benchmarks like matrix multiplication to represent every workload. Use payloads, libraries, and dependencies resembling production with synthetic or sanitized data.

## 6. Choosing a Java Runtime

### Managed Java Runtime

Managed runtimes have their runtime environment, patches, and platform updates maintained by Lambda. This is usually the first choice for Java functions unless there are special runtime or binary requirements.

At the time of writing, AWS Lambda lists managed runtimes for Java 25 (`java25`), Java 21 (`java21`), Java 17 on Amazon Linux 2023 (`java17.al2023`), alongside older runtimes. Check the runtime support table and deprecation dates before choosing; do not rely on old examples in repositories. <https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html>

| Runtime | Considerations |
|---|---|
| Java 25 | Newer release featuring AOT cache for the Runtime Interface Client in the managed runtime and updated JVM defaults; test frameworks/dependencies |
| Java 21 | Modern LTS choice, managed runtime based on Amazon Linux 2023 |
| Java 17 | Fits systems whose dependencies/frameworks still require Java 17; prefer the AL2023 runtime for new functions |
| Older Java | Maintain only for compatibility reasons; check deprecation schedules and upgrade plans |

Lambda-supported runtimes run on both `x86_64` and `arm64`. Picking a Java version does not lock you into a CPU architecture. <https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html>

### Custom Runtime

Custom runtimes fit when you need direct control over bootstrap, the runtime interface, or a language/runtime not offered as a managed runtime. They increase build, patching, compatibility-testing, and operational ownership. Never choose a custom runtime assuming it is automatically faster than managed Java.

### GraalVM Native Image

GraalVM Native Image compiles Java bytecode and reachable code into a native executable at build time. On Lambda, Java Native Image typically runs on the OS-only `provided.al2023` runtime paired with the Lambda Runtime Interface Client (RIC). Binaries must be built for Linux on the exact `x86_64` or `arm64` architecture. <https://docs.aws.amazon.com/lambda/latest/dg/runtimes-provided.html>

Native Image can cut startup time and runtime footprint, but evaluate:

- Reflection, dynamic proxies, classpath scanning, and serialization require proper metadata.
- Libraries using JNI or native dependencies require builds for the target architecture.
- Native builds can take longer and be more complex than JVM JARs.
- Runtime behavior, GC, peak throughput, and memory must be benchmarked separately.
- Frameworks/plugins vary in AOT compatibility.
- OS-only runtimes do not provide the same managed Java update experience; the team owns the runtime interface and binary.

Native Image does not automatically mean faster everywhere. For long-lived warm functions or heavy CPU processing, JVM JIT can achieve higher throughput once optimized. For short-lived functions experiencing frequent cold starts, Native Image can offer significant advantages.

## 7. JIT, SnapStart, and Provisioned Concurrency

These are techniques for managing startup and runtime behavior, not CPU architectures.

### JVM JIT

The JVM interprets bytecode and compiles hot methods into native machine code. Tiered compilation balances startup speed against long-term performance. A short-lived invocation may finish before JIT reaches peak optimization; a long-lived warm worker benefits from optimizations accumulated across many invocations.

Lambda applies default JVM settings per Java runtime. According to current documentation, Java 17/21 default to stopping tiered compilation at level 1; Java 25 also uses level 1 by default, except when SnapStart or Provisioned Concurrency is enabled, where the JVM uses default tiered compilation. You can tune via `JAVA_TOOL_OPTIONS`, but always measure before changing defaults. <https://docs.aws.amazon.com/lambda/latest/dg/java-customization.html>

### SnapStart

SnapStart initializes the function when a version is published and saves a memory/disk state snapshot to create execution environments from the snapshot instead of booting from scratch. It supports Java 11 and later on corresponding managed runtimes, applying only to published versions and aliases pointing to versions. Verify compatibility for random/unique values, temporary credentials, and network connections created during initialization. <https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html>

### Provisioned Concurrency

Provisioned Concurrency keeps pre-initialized execution environments ready to reduce cold-start latency for workloads with strict response requirements. It incurs ongoing capacity costs even with zero traffic; compare against SnapStart and actual load patterns.

Do not benchmark SnapStart by invoking `$LATEST` when the feature applies to published versions. Never compare one function using Provisioned Concurrency against another without it and attribute the difference to CPU architecture.

## 8. Compatibility Checks Before Switching Architecture

Pure Java bytecode usually runs on either architecture, yet packages may embed native components. Inventory everything before moving from `x86_64` to `arm64`:

- JNI/JNA libraries and native executables.
- Lambda layers.
- Lambda extensions, telemetry agents, and security agents.
- Dependencies packaged inside JARs, ZIPs, or containers.
- Compression, cryptography, image/video codecs, and database drivers with native acceleration.
- Build/test/deploy tools and Docker base images.
- Bootstrap scripts checking `uname -m` or downloading architecture-specific binaries.

AWS recommends verifying that every third-party library/package has an ARM64 version, along with layers, extensions, and container images. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

Example checking a binary's architecture on Linux:

```bash
file native/libimagecodec.so
readelf -h native/libimagecodec.so | grep Machine
```

Output showing `AArch64`/`ARM aarch64` indicates ARM64; `Advanced Micro Devices X86-64` indicates x86_64. Run commands inside the target build container or an environment with matching toolchains.

## 9. Building Artifacts for the Right Architecture

### Pure Java JARs

If a JAR contains only Java bytecode and portable resources, the same artifact can run on both `x86_64` and `arm64`. However, any native dependencies embedded inside the JAR/layer must still include matching binaries selected properly at runtime.

### Container Images

Build images for the right platform:

```bash
# x86_64 Lambda
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --load \
  -t orders-function:x86_64 .

# arm64 Lambda
docker buildx build \
  --platform linux/arm64 \
  --provenance=false \
  --load \
  -t orders-function:arm64 .
```

`--platform` must match the Lambda function's architecture. AWS requires the image to match the function architecture; building on an ARM machine does not guarantee the right platform image unless explicitly specified. <https://docs.aws.amazon.com/lambda/latest/dg/java-image.html>

In this example, `--load` loads the single-platform image into the local Docker image store for testing. When building for deployment, replace `--load` with `--push` and tag the image with the corresponding ECR repository URI; the repository/image must also preserve the chosen architecture.

### GraalVM Native Image

Native Image must be built inside a Linux environment with a toolchain matching the target architecture. Never compile an x86_64 binary and upload it to an ARM64 function or vice versa. If CI runs on a different architecture, use supported cross-compilation/toolchains or build inside a container matching the target platform.

## 10. Designing a Fair Test Matrix

Benchmarks must isolate each variable. A starting matrix might look like:

| Variable | Test Values |
|---|---|
| CPU architecture | `x86_64`, `arm64` |
| Runtime | Java 21 managed, Java 25 managed; Native Image if applicable |
| Memory | 512 MB, 1,024 MB, 1,769 MB, 3,008 MB |
| Startup mode | On-demand cold, warm, SnapStart, or Provisioned Concurrency if supported |
| Payload | Small, medium, large matching production distribution |
| Concurrency | 1, typical level, peak, and burst |
| Region | Same Region supporting both architectures |
| Dependencies | Identical versions, endpoints, network paths, and test data |

You do not have to run the full Cartesian product from the start. A leaner sequence:

1. Pick a compatible runtime/deployment format and benchmark the `x86_64` baseline.
2. Sweep memory on the baseline to find the efficient configuration region.
3. Run `arm64` with identical runtime, artifact, memory, and workload.
4. Benchmark runtime variants (e.g., managed JVM vs. Native Image) on the suitable architecture.
5. Re-validate the top configuration under production-like concurrency and payloads.
6. Run canary traffic if needed to confirm real-world behavior.

If multiple variables change at once, you cannot tell which caused an improvement or regression. Every benchmark comparison pair must vary only one primary dimension.

## 11. Preparing Representative Benchmark Workloads

A useful benchmark must represent real work. Prepare a suite of scenarios:

| Scenario | Example | Goal |
|---|---|---|
| Startup | Initialize Spring context, load configuration, and dependency injection | Measure cold start/init |
| CPU hot path | Parse/validate JSON, transform, hash, or compress | Compare CPU architecture and memory |
| I/O path | Read DynamoDB, call HTTP services, or S3 | Identify network/dependency bottlenecks |
| Batch | Process 10/100/500 event records | Measure batch throughput and memory |
| Large payload | Deserialize large payloads, transform object graphs | Measure allocations, GC, and peak memory |
| Burst | Rapidly ramp concurrency | Measure scale-out, throttling, and connection pressure |

Test data should follow production size distributions. A tiny fixed payload can paint an overly optimistic picture. Use synthetic data or scrubbed data with sensitive info removed.

Hold constant:

- Commit/source code and dependency versions.
- Handler, event schema, payloads, and record counts.
- Region, VPC/subnets, security groups, and endpoints.
- Cache/database state and connection pools.
- Concurrency profile, run duration, and load generator.
- Log levels, tracing, extensions, and telemetry configuration.
- Timeouts, retry policies, and downstream service quotas.

If you switch architecture while one function uses a different layer/extension or runs in a different subnet, the result is no longer a pure CPU comparison.

## 12. Separating Cold Starts and Warm Invocations

Cold starts and warm invocations measure different costs. Never merge them into a single average.

### Cold Start

A cold start can include:

- Creating the execution environment.
- Downloading the package/container and launching the runtime.
- Initializing the JVM, class loading, and framework.
- Initializing static fields, dependency injection, and clients.
- VPC/network initialization if the function uses a VPC.
- Restoring snapshots if using SnapStart.

In Lambda logs, `Init Duration` typically indicates the execution environment's initialization phase. With SnapStart, track restore-related telemetry and function version state as well. Do not treat handler duration as the entire cold start.

### Warm Invocation

Warm invocations measure the handler after the environment is ready. Invoke repeatedly on warm environments, noting that Lambda may reuse or spin up new environments depending on load. Classify samples via logs/request metadata and collect sufficient iterations.

### Separate Measurement Table

| Group | Metrics |
|---|---|
| Cold | Init Duration, restore duration if applicable, end-to-end first-request latency |
| Warm | Handler Duration, p50/p95/p99, throughput |
| Memory | Max Memory Used, OOMs, GC behavior if observable |
| Platform | Throttles, ConcurrentExecutions, errors, queue age |
| Cost | GB-seconds, request charges, snapshot/provisioned capacity, and telemetry costs |

Run cold-start tests across many new environments, not just a single first invocation. One sample cannot describe p95/p99.

## 13. Measuring Performance Metrics

Fundamental metrics:

- **Duration:** function execution time; examine distributions rather than averages alone.
- **Billed Duration:** time billed under Lambda's rounding rules.
- **Init Duration:** environment initialization time recorded in the report log.
- **Max Memory Used:** peak memory observed during the invocation/environment.
- **Concurrency:** number of execution environments processing concurrently.
- **Throttles:** invocations rejected due to concurrency/quota limits.
- **Error rate:** proportion of failed or timed-out invocations.
- **Throughput:** requests/events processed per second or per unit cost.
- **Cost per operation:** estimated cost per successfully completed request/event.

Do not compare solely on `Duration` if two functions have different error rates, retry counts, or outputs. A faster function that fails more often is not a better choice.

AWS Lambda logs `Duration`, `Billed Duration`, `Memory Size`, and `Max Memory Used` in the REPORT log. Because memory setting affects CPU, inspect duration and memory together. <https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html>

## 14. Designing Repeatable, Statistically Meaningful Benchmarks

Suggested benchmark procedure:

1. Deploy a function variant with locked configuration.
2. Wait for deployment completion and verify actual runtime/architecture.
3. Run a separate warm-up; exclude warm-up samples from warm latency datasets.
4. Collect cold-start samples on new environments or new versions in a controlled way.
5. Run the warm workload at fixed concurrency and payload mix.
6. Collect at least several hundred invocations for latency percentiles; exact counts depend on traffic and stability.
7. Repeat benchmark runs at multiple times to reduce platform noise.
8. Compute p50, p90, p95, p99, throughput, error rate, and cost.
9. Record runtime version, artifact hash, architecture, memory, Region, and test profile.
10. Compare results against baselines and SLOs before drawing conclusions.

With too few samples, p99 becomes noisy. Report sample counts and confidence/variance; never present a p99 from a few dozen invocations as a firm conclusion.

## 15. Example: Creating Two Lambda Functions to Compare Architectures

You can create two separate functions to avoid mutating configuration between test runs. Both share the same Java runtime, artifact, memory, timeout, and environment variables, differing only in architecture and function name.

AWS CLI example (assuming JAR is built and execution role exists):

```bash
aws lambda create-function \
  --function-name orders-java21-x86 \
  --runtime java21 \
  --architectures x86_64 \
  --handler com.example.orders.Handler::handleRequest \
  --role arn:aws:iam::123456789012:role/orders-lambda-role \
  --zip-file fileb://target/orders-function.jar \
  --memory-size 1769 \
  --timeout 30

aws lambda create-function \
  --function-name orders-java21-arm \
  --runtime java21 \
  --architectures arm64 \
  --handler com.example.orders.Handler::handleRequest \
  --role arn:aws:iam::123456789012:role/orders-lambda-role \
  --zip-file fileb://target/orders-function.jar \
  --memory-size 1769 \
  --timeout 30
```

This example fits when the JAR contains no native dependencies or all native dependencies support both architectures. If using layers or extensions, verify architecture compatibility for each component.

Verify configuration:

```bash
aws lambda get-function-configuration \
  --function-name orders-java21-arm \
  --query '{Runtime:Runtime,Architectures:Architectures,Memory:MemorySize,Timeout:Timeout}'
```

When a function already exists, `update-function-configuration` can change memory/architecture, though you must publish a new version and verify aliases/versions before benchmarking. Keeping two separate functions often makes storing results and rolling back easier.

## 16. Example: Configuring Architecture with AWS CDK Java

In CDK, architecture is selected via `Architecture.X86_64` or `Architecture.ARM_64`:

```java
import software.amazon.awssdk.Duration;
import software.amazon.awssdk.services.lambda.Architecture;
import software.amazon.awssdk.services.lambda.Code;
import software.amazon.awssdk.services.lambda.Function;
import software.amazon.awssdk.services.lambda.Runtime;

Function armFunction = Function.Builder.create(this, "OrdersArmFunction")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.ARM_64)
        .handler("com.example.orders.Handler::handleRequest")
        .code(Code.fromAsset("target/orders-function.jar"))
        .memorySize(1769)
        .timeout(Duration.seconds(30))
        .build();

Function x86Function = Function.Builder.create(this, "OrdersX86Function")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.X86_64)
        .handler("com.example.orders.Handler::handleRequest")
        .code(Code.fromAsset("target/orders-function.jar"))
        .memorySize(1769)
        .timeout(Duration.seconds(30))
        .build();
```

Both functions must have identical dependencies, environment variables, VPC, IAM policies, tracing, and triggers for a fair comparison. In a production stack, never attach two functions with real side effects to process the same event simultaneously; use test events or safe traffic mirroring.

## 17. Tuning Memory with AWS Lambda Power Tuning

AWS Lambda Power Tuning uses Step Functions to invoke a function across multiple memory tiers, collect durations and estimated costs, and visualize the performance/cost sweet spot. It is useful for memory tuning, while architecture and runtime should still be compared as separate variables.

Suggested workflow:

1. Select the function and a representative payload.
2. Pick a memory range, e.g., 512–3,008 MB.
3. Run tuning in a test environment against stable downstream dependencies.
4. Review duration, cost, and outputs per memory tier.
5. Repeat on the alternate architecture if comparing architectures.
6. Confirm the final configuration under production-like load/concurrency.

Never run power tuning on functions with non-idempotent side effects or uncontrolled billable downstream calls. The tool triggers many invocations; use test data, sandboxes, and load limits.

Reference: <https://github.com/alexcasalboni/aws-lambda-power-tuning>

## 18. Calculating Cost per Successful Operation

For economic comparison, use cost per successfully completed request/event rather than duration alone.

A simple estimate:

```text
Compute cost per invocation
  ≈ configured memory in GB
    × billed duration in seconds
    × price per GB-second for architecture/Region

Total cost per successful operation
  ≈ (compute + request + downstream + telemetry + network cost)
    / successful operations
```

Include retries, DLQs, API Gateway, SQS, databases, NAT, log ingestion, tracing, and related charges. For SnapStart, factor in snapshot caching/restore charges per current pricing; for Provisioned Concurrency, factor in reserved capacity charges. Pricing varies by Region, architecture, and over time; consult AWS Lambda Pricing or AWS Pricing Calculator rather than hardcoding an assumed savings percentage in code reviews.

An architecture with lower duration yet different GB-second pricing or a higher error rate may not be cheaper per successful transaction. Compare both latency SLOs and unit economics.

## 19. Measure End-to-End Latency, Not Just Handler Time

A serverless request may traverse API Gateway, Lambda, SQS, workers, and a database. Handler time does not capture total user-observed latency.

Measure:

- API Gateway integration latency and total latency.
- Lambda `Init Duration` and `Duration`.
- Queue `ApproximateAgeOfOldestMessage` and wait time before a worker receives the message.
- Database/client latency and connection acquisition.
- Retries/backoff and delivery count.
- End-to-end completion time from when the request is accepted until business state completes.

Maintain consistent trace/correlation IDs to distinguish a slow function from queue backlogs or slow dependencies. Looking only at the handler can make one architecture look faster while users still wait due to queues or databases.

## 20. Evaluating Benchmark Results

Example table of hypothetical results illustrating how to read metrics (not AWS-guaranteed numbers):

| Variant | p50 warm | p95 warm | p95 cold/init | Max memory | Cost/success |
|---|---:|---:|---:|---:|---:|
| Java 21 x86_64, 1,769 MB | 42 ms | 78 ms | 820 ms | 640 MB | 1.00× |
| Java 21 arm64, 1,769 MB | 39 ms | 71 ms | 790 ms | 625 MB | 0.86× |
| Java 25 arm64, 1,769 MB | 37 ms | 68 ms | 730 ms | 620 MB | 0.84× |
| Native Image arm64, 1,024 MB | 45 ms | 82 ms | 180 ms | 310 MB | 0.91× |

In this example, Native Image has lower cold start while its warm p95 trails the Java 25 managed runtime. If the SLO focuses on cold starts, Native Image may be worth testing; if the workload is warm and CPU-intensive, a managed runtime may fit better. Cost values are purely illustrative multipliers and must not be used for budgeting.

Evaluate in order:

1. Does the variant meet p95/p99 SLOs?
2. Do error rates, timeouts, or throttling increase?
3. What is the cost per successful operation?
4. Do cold starts impact user journeys significantly?
5. Are native dependencies, build pipelines, and operational overhead acceptable?
6. Are results reproducible across multiple runs and under concurrency?

## 21. Canary Rollouts and Switching Architectures

After sandbox benchmarking, run a canary rollout to verify on live traffic. AWS recommends staged deployments and alias routing to split a portion of traffic between x86 and ARM versions and compare metrics. <https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html>

A safe rollout process:

1. Build and test artifacts compatible with the target architecture.
2. Deploy the new version in staging.
3. Run integration/load tests and verify native dependencies.
4. Publish a version and configure alias/traffic shifting appropriately.
5. Start with a small canary traffic percentage.
6. Monitor latency, errors, throttles, memory, and cost.
7. Increase traffic if thresholds pass; roll back if SLOs breach.
8. Once stable, shift remaining traffic while keeping a rollback option.

If architecture is a function/version-level setting in your deployment setup, verify alias routing across versions and confirm each version actually runs on its intended architecture. Never assume two aliases/versions can point to arbitrary configurations if the deployment model does not support it.

## 22. Common Benchmarking Mistakes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Running a single invocation | Skewed by cold starts or noise | Repeat many runs; separate cold and warm |
| Changing architecture and memory together | Cannot tell which variable caused the change | Hold one variable constant per comparison pair |
| Using overly tiny payloads | Fails to represent real workloads | Use production-like payload distributions |
| Skipping JNI/layer checks | Function may fail or fall back unexpectedly | Inspect every native dependency/extension |
| Building image for wrong platform | Binary fails to run on Lambda | Target `linux/amd64` or `linux/arm64` accurately |
| Looking only at average duration | Hides tail latency | Compare p50/p95/p99 and cold starts separately |
| Omitting retries/errors | Underestimates cost per request | Compute cost per successful operation |
| Benchmarking against a noisy database | Noise masks CPU differences | Keep datasets, endpoints, and concurrency steady |
| Disabling telemetry/extensions | Production incurs different overhead | Match production observability config |
| Concluding ARM is always faster/cheaper | Performance depends on workload and dependencies | Measure on real workloads and check Regional pricing |
| Using Native Image without testing reflection | Runtime errors or missing classes/resources | Configure metadata and run full integration tests |
| Using SnapStart without handling uniqueness | State/secrets/random values may repeat | Re-initialize unique values post-restore and check connections |

## 23. Process for Selecting Architecture and Runtime

1. **Define SLOs:** p95/p99 latency, cold start, throughput, error rate, and target cost.
2. **Classify workload:** CPU-bound, I/O-bound, memory-bound, cold-start-bound, or burst-bound.
3. **Pick baseline runtime:** prefer a supported managed Java runtime unless custom needs require otherwise.
4. **Check dependencies:** JNI, layers, extensions, container base images, and native binaries.
5. **Establish x86_64 baseline:** lock runtime, memory, payloads, and network.
6. **Sweep memory:** locate the optimal duration/cost region.
7. **Compare arm64:** hold remaining variables fixed and gather sufficient warm/cold samples.
8. **Compare runtime variants:** managed Java, SnapStart, Provisioned Concurrency, or Native Image when justified.
9. **Measure end-to-end:** include queue delays, downstream latency, and retries.
10. **Compute unit economics:** cost per successful operation per Region.
11. **Canary:** roll out incrementally and watch production metrics.
12. **Document decision:** archive benchmark reports, artifact hashes, runtime, architecture, and date for future re-testing after upgrades.

## 24. Pre-Production Checklist

- [ ] SLOs and representative workloads are defined.
- [ ] CPU architecture and runtime are benchmarked as separate axes.
- [ ] Target Region supports the chosen architecture.
- [ ] All JNI/native libraries, layers, extensions, and container images are compatible.
- [ ] Native binaries are built for the exact target Linux architecture.
- [ ] Memory sweep is completed and CPU/memory bottlenecks are classified.
- [ ] Cold starts and warm invocations are measured separately.
- [ ] p50/p95/p99, throughput, error rates, and throttling are recorded.
- [ ] Tests use identical payloads, dependencies, Region, VPC, and telemetry config.
- [ ] Cost per successful operation includes requests, compute, retries, network, and observability.
- [ ] SnapStart/Provisioned Concurrency are benchmarked on published versions with accurate pricing.
- [ ] Native Image is verified for reflection, serialization, JNI, and resource metadata.
- [ ] CI/CD builds for the target architecture platform and records artifact hashes.
- [ ] Canary/rollback plan is prepared.
- [ ] Runtime support/deprecation dates are re-checked before release.

## AWS References

- [Selecting and configuring a Lambda instruction set architecture](https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html)
- [AWS Lambda Java runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html)
- [AWS Lambda runtime support and deprecation](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html)
- [Configure Lambda memory and CPU allocation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html)
- [Customize Java runtime startup behavior](https://docs.aws.amazon.com/lambda/latest/dg/java-customization.html)
- [Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [OS-only runtimes and Native AOT](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-provided.html)
- [Deploy Java Lambda functions with container images](https://docs.aws.amazon.com/lambda/latest/dg/java-image.html)
- [AWS Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning)

## Conclusion

Choose CPU architecture and Java runtime by benchmarking on representative workloads. `arm64`/Graviton can improve price/performance, while `x86_64` offers compatibility advantages with certain native dependencies; managed Java runtimes are typically simpler to operate, whereas Native Image can reduce startup at the expense of stricter build and compatibility requirements. Before deciding, inspect native libraries, hold memory and workloads constant, separate cold starts from warm latency, measure p95/p99, and calculate cost per successful operation. Canaries paired with a rollback plan enable evidence-based transitions while protecting SLOs in production.
