# Supported runtimes and application code update responsibilities

## Lesson objectives

After this lesson, you will be able to:

- Explain what the runtime is responsible for when a serverless platform executes a function.
- Distinguish between provider-managed language runtimes, custom runtimes, and container images.
- Identify the criteria to check in a supported runtimes list.
- Clarify update responsibilities between the cloud provider and the application development team.
- Establish a workflow for runtime upgrades, compatibility testing, version releases, and safe rollbacks.

## 1. Runtimes in the serverless function model

The runtime is the software layer that receives invocation requests, passes events to the handler code, and returns results to the platform. A runtime typically includes the language execution engine, handler loading mechanism, and the communication protocol with the provider’s execution environment.

A function invocation usually goes through these steps:

1. The platform allocates or selects an execution environment for the function.
2. The runtime initializes the process and loads the code, libraries, and required configuration.
3. The runtime calls the handler with the event and context information.
4. The handler executes business logic, calls downstream dependencies, and returns a result.
5. The platform records the outcome, collects logs/metrics, and either terminates or reuses the execution environment.

An execution environment may be retained to handle subsequent invocations. Therefore, initialization code at module or process scope may run only once during the environment’s lifetime, while the handler runs on every invocation. However, do not rely on the environment always being reused: the platform can spin up a new environment or reclaim an existing one at any time.

For example, an order-processing function might initialize a storage service client at module scope to reuse connections. Each invocation only reads the event, validates data, performs the operation, and returns a result. Code must not assume that global variables, temporary files, or in-memory state will survive between two calls.

## 2. Common runtime models

Serverless platforms support different runtime models. Exact names and version lists vary by provider, region, CPU architecture, and time.

### 2.1. Provider-managed language runtimes

The provider supplies pre-built runtimes for popular languages such as Python, Node.js, Java, .NET, Go, or Ruby, depending on the service. The development team selects a supported version, provides a handler, and packages the code with required libraries.

Advantages:

- Fast to start because you do not need to package an entire operating system and execution engine.
- The provider manages most of the execution infrastructure and updates the runtime under the service’s policy.
- Direct integration with the platform’s deployment, logging, monitoring, and access-control mechanisms.

Limitations:

- The team must adhere to the runtime versions and configurations provided by the platform.
- Native libraries or OS-level dependencies may be constrained.
- When a runtime reaches end of support, the application must be tested and migrated to another version within the provider’s timeline.

### 2.2. Custom runtimes

A custom runtime lets the development team supply its own execution engine or invocation relay layer when built-in runtimes do not meet requirements. Startup code must typically implement the platform-defined protocol to receive events, invoke the handler, and return results.

This model is useful when an uncommon language, specific runtime version, or custom execution approach is needed. In return, the team assumes greater responsibility for bootstrapping, error handling, protocol compatibility, security patching, and testing after each change.

A custom runtime does not remove serverless platform limits. Execution duration, resources, system permissions, networking, and how the platform initiates invocations remain governed by the service.

### 2.3. Runtimes packaged in container images

Some platforms allow deploying functions as container images. The team packages the runtime, system libraries, and application code into an image matching the format required by the service.

The benefit is that dependencies are explicitly declared in a Dockerfile, native libraries are easier to include, and existing image build pipelines can be reused. However, the image must conform to the platform’s startup contract and invocation protocol. A container image does not equate to host admin rights or the ability to run unbounded workloads.

The team must build images compatible with the chosen CPU architecture, scan for vulnerabilities, update base images, and publish new images when the runtime or system libraries require security patches.

## 3. How to read a supported runtimes list

Before choosing a runtime, check the official support documentation for the specific service you use. Do not infer support solely because a language can be installed on a development machine.

Criteria to verify:

| Criterion | Questions to check | Impact |
|---|---|---|
| Language and version | Which versions does the service support? Is the version new, in maintenance, or nearing deprecation? | Determines syntax, libraries, and upgrade deadlines. |
| Deployment regions | Is the runtime available in every required region? | Affects multi-region deployment and disaster recovery capability. |
| CPU architecture | Does the runtime support x86_64, ARM64, or both? | Affects images, native libraries, and price/performance. |
| Handler and packaging | How are handlers declared, and what are the package layout and size limits? | Determines artifact build and packaging steps. |
| System libraries | Which shared libraries, certificates, binaries, or OS packages are preinstalled? | Affects whether native dependencies can run. |
| Execution limits | What are the maximum runtime duration, memory, temp storage, and concurrency? | Shapes task design and workload splitting. |
| Update policy | Is the runtime patched automatically, via configuration, or on a user-managed schedule? | Impacts test planning and change control. |
| End-of-support dates | When do patches stop, or when can new functions no longer be created with that runtime? | Sets hard upgrade deadlines. |

Distinguish three milestones: the date creating new functions on the old runtime is blocked, the date security updates stop, and the date the platform stops executing the runtime altogether. Policies can differ across providers and runtimes. When receiving a deprecation notice, check the exact dates applicable to your service, region, and account.

Supported runtimes can also vary by deployment model. A version available as a managed runtime is not necessarily supported identically in a custom runtime or container image. Verify the runtime, architecture, and triggers the function will use together.

## 4. Dividing update responsibilities

Serverless reduces server operations, but does not shift all application operational responsibilities to the provider.

| Area | Cloud provider | Application development team |
|---|---|---|
| Execution infrastructure | Operates servers, scheduling, isolation, and execution environment provisioning. | Selects resource configurations and designs applications within service limits. |
| Managed runtime | Maintains the service-provided runtime and applies updates per published policy. | Tracks notices, chooses update policies if offered, tests compatibility, and deploys code changes when needed. |
| Function code and handler | Provides the invocation contract and execution environment. | Fixes business logic bugs, handlers, event parsing, timeouts, and retry logic. |
| Application dependencies | May provide certain documented platform libraries. | Manages package versions, lockfiles, framework libraries, and bundled dependencies. |
| Native libraries and container images | Maintains the container/serverless service and execution limits. | Builds for the right architecture, updates base images, binaries, and native libraries. |
| Custom runtime | Provides supported protocols and integration points. | Maintains the bootstrap, self-supplied runtime, protocol compatibility, and patches for those components. |
| Testing and release | Provides platform-level deployment, versioning, and monitoring mechanisms. | Owns business testing, releases, error tracking, and application code rollbacks. |

With managed runtimes, the provider may patch the underlying runtime or OS according to the service’s schedule and mechanism. The application team must still ensure code, libraries, and configuration remain compatible after updates. If the app uses removed APIs, relies on changed dependency behavior, or has incompatible native libraries, a platform patch can cause failures even when source code has not changed.

With custom runtimes or container images, the responsibility boundary shifts further toward the development team. The team must monitor vulnerabilities in self-packaged runtimes, base images, and system dependencies; rebuild patched artifacts; and deploy new versions.

## 5. Dependency management and application code compatibility

Function code often depends on multiple software layers:

- Language runtime and interpreter/virtual machine version.
- Frameworks and third-party packages.
- Native libraries such as image processing, cryptography, or database client libraries.
- Extensions or agents for monitoring, security, and telemetry.
- Environment variables, endpoint configuration, certificates, and access permissions.

To keep these dependencies under control:

1. Declare direct dependencies in package manifests such as `requirements.txt`, `poetry.lock`, `package-lock.json`, `go.mod`, or the language’s equivalent.
2. Pin appropriate versions and commit lockfiles so builds are reproducible.
3. Generate an SBOM or dependency report if required by security policy; scan for vulnerabilities before release.
4. Build native libraries in an environment compatible with the target runtime and architecture. A package compiled on Windows x86_64 may fail on Linux ARM64.
5. Check package size limits, layer counts, unzipped size caps, and libraries pre-supplied by the platform.
6. Avoid putting secrets like API keys or passwords in images, source code, or committed config files; use a secret management service and least-privilege access.

For example, a Python image-processing function may use a package containing native code. When migrating from one Python runtime version to a newer one, or switching architecture from x86_64 to ARM64, the team must reinstall or recompile the corresponding package and then test image decoding, transformation, and saving in an environment close to production.

## 6. Runtime configuration and update example

The AWS SAM example below declares a Python function. `python3.12` is only an illustrative configuration value; before deploying, verify that the version is still supported by the service in the chosen region and architecture.

~~~yaml
Resources:
  OrderHandler:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.12
      Handler: app.handler
      CodeUri: src/
      Architectures:
        - arm64
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          LOG_LEVEL: INFO
~~~

The corresponding handler might look like:

~~~python
def handler(event, context):
    order_id = event.get("order_id")
    if not order_id:
        return {
            "statusCode": 400,
            "body": "order_id is required"
        }

    # Execute business logic using the packaged dependencies.
    return {
        "statusCode": 200,
        "body": f"accepted: {order_id}"
    }
~~~

When upgrading a runtime, do not merely change the `Runtime` field. Check language syntax and APIs, framework versions, dependencies, native libraries, environment variables, permissions, and timeout behavior. If changing CPU architecture at the same time, rebuild native dependencies and separately benchmark performance impacts.

A typical update workflow:

1. Verify the target runtime is supported and available in deployment regions.
2. Create a change branch, update runtime config and dependencies, and commit the lockfile alongside source code.
3. Build a clean artifact in an environment compatible with the target runtime/architecture.
4. Run unit tests, integration tests, and dependency security checks.
5. Deploy to a staging environment configured close to production; inspect cold starts, execution duration, memory, logs, and business results.
6. Publish the new version. If the platform supports versions/aliases or traffic splitting, keep the old version and shift a fraction of traffic to the new version before ramping up.
7. Monitor error rate, timeouts, latency, throttling, and cost. Halt rollout or point the alias back to the prior version if metrics cross thresholds.
8. Once stable, retire old dependencies and configuration, and update operational docs and the next upgrade schedule.

For example, on AWS Lambda, a team can update the code package and runtime configuration, wait for the update to complete, then publish an immutable function version and point the `live` alias to it. Aliases enable traffic shifting and quick rollback to the prior version. On Azure Functions or Google Cloud Run functions, mechanisms for selecting stacks/runtimes, creating revisions, and shifting traffic have different names; the principle remains testing the new artifact before sending all traffic to the new version.

## 7. Trade-offs when choosing a runtime model

| Option | Strengths | Costs and risks |
|---|---|---|
| Managed runtime | Low operational overhead, tight platform integration, and provider-managed update cadence. | Tied to supported versions; requires proactive testing when runtimes are updated or deprecated. |
| Custom runtime | Flexibility in language and execution model. | Team must maintain the bootstrap, protocol, runtime, and security patches. |
| Container image | Explicit control over system dependencies, easier native libraries, and reuse of image build pipelines. | Larger images can increase pull/startup time; team must update base images and scan for vulnerabilities. |
| Layers or extensions | Share libraries and agents across multiple functions. | Can introduce version conflicts, increase package size, startup time, and attack surface. |

A newer runtime is not automatically the best choice. Weigh remaining support window, dependency compatibility, performance, startup time, artifact size, CPU architecture, and team operational capacity. If an application runs stably on a managed runtime, staying on that model typically minimizes maintenance. If specialized system libraries are required, a container image may fit better, provided the team maintains the image update cycle.

## 8. Post-update verification

Use a staging environment or test alias to verify before shifting production traffic.

- **Configuration check:** confirm runtime, architecture, handler, timeout, memory, environment variables, and region match the target.
- **Initialization check:** observe cold-start duration, package import errors, bootstrap failures, and extension errors.
- **Invocation check:** send events covering the happy path, missing fields, malformed data, dependency errors, and retries.
- **Dependency check:** verify native packages load, certificates validate, network connections succeed, and secrets have proper permissions.
- **Resource check:** compare duration, memory consumption, concurrency, throttling, and timeout rate before vs. after the update.
- **Security check:** scan dependencies and images, ensure no secrets were packaged, and verify least-privilege execution permissions.
- **Rollback check:** rehearse shifting the alias or traffic back to the prior version and confirm invocations recover.

On AWS Lambda, you can use CloudWatch logs, invocation/error/duration/throttles metrics, and function update status for verification. On Azure Functions or Google Cloud Run functions, use the corresponding logs, metrics, and deployment/revision status. Compare metrics against a pre-upgrade baseline rather than relying solely on a successful deployment status.

## 9. Runtime management checklist

- [ ] Runtime and version are on the supported list for the target service, regions, and architecture.
- [ ] Deprecation dates, security patch deadlines, and upgrade plans have been checked.
- [ ] Handler, frameworks, and dependencies are compatible with the target runtime.
- [ ] Lockfile is committed and artifacts are reproducible.
- [ ] Native libraries are built for the right OS and architecture.
- [ ] Base images, custom runtimes, and extensions have a clear patching process.
- [ ] Secrets are excluded from source code, images, and deployment packages.
- [ ] Unit tests, integration tests, and realistic invocation tests have been run.
- [ ] Cold starts, duration, memory, errors, and throttling were compared against baseline.
- [ ] A verified prior version or rollback plan exists.
- [ ] An owner is assigned to track runtime notices and the next upgrade cycle.

## Conclusion

The runtime determines how function code is initialized and executed on a serverless platform. Choosing a supported runtime keeps the application compatible with the service and provides a clear maintenance path. The provider manages infrastructure and managed runtimes under platform policy; the development team owns application code, dependencies, custom runtimes or self-packaged images, compatibility testing, and safe version releases. An upgrade process backed by testing, monitoring, and rollback lowers risk whenever runtimes evolve or approach end of support.