# OCI Functions and Fn Project Architecture

## 1. Objectives and Position in OCI

In the **Containers and Functions** chapter of the **CLOUD_PROVIDERS_ORACLE** module, OCI Functions lets you deploy application logic as individual functions and execute them on demand. Operating them on OCI requires understanding source code, deployment artifacts, tenancy, compartments, IAM, VCN, system observability, and target resources such as Object Storage or Oracle databases.

After this lesson, learners will be able to:

- Explain the relationship between OCI Functions, Fn Project, Fn Server, Fn CLI, and FDK.
- Distinguish between application, function, invocation, and trigger.
- Describe the build, deploy, and invoke flow of functions using container images.
- Separate the function invocation path from the path a function uses to access resources inside a VCN.
- Design permissions, state management, scalability, and observability.
- Practice a Java function using a local Fn Server and identify the configuration required to deploy it to OCI.

## 2. How Are OCI Functions and Fn Project Related?

**OCI Functions** is an Oracle-managed Functions as a Service platform built on the open-source **Fn Project** engine. Developers supply logic and configuration; the service manages the execution infrastructure, receives requests, and scales the runtime environment. See [Overview of Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm).

Distinguish the components:

| Component | Role | How Do Learners Interact With It? |
| --- | --- | --- |
| OCI Functions | Managed function execution service on OCI | Console, API, SDK, OCI CLI, or Fn CLI |
| Fn Project | Open-source serverless platform | Development model and toolset |
| Fn Server | Engine that manages and executes functions in an Fn environment | Run locally when developing image-based functions |
| Fn CLI | `fn` command-line tool | Initialize, build, deploy, manage contexts, and invoke |
| FDK | Function Development Kit for a language | Passes invocation data to the handler and returns results |
| Handler | Function or method containing business logic | Java, Python, or supported language code |

Fn Server can run in a user-managed environment. With OCI Functions, learners use the managed service instead of deploying their own Fn Server cluster to operate it. Differences in endpoints, OCI authentication, and platform-specific features are described in [Differences between OCI Functions and Fn Project](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsdiffswithfn.htm).

### 2.1. Two Artifact Models to Distinguish

OCI Functions currently supports two deployment models:

| Aspect | Container-Image Function | Code-Only Function |
| --- | --- | --- |
| Artifact supplied by developer | Container image | Archive containing code and dependencies |
| Runtime | Packaged inside the image | Choose a supported managed runtime |
| Registry workflow | Build and publish image to OCIR | Does not require developer to publish an image manually |
| Update responsibility | Manage code, dependencies, and image contents | Manage code, dependencies, and runtime update choices |
| Best suited for | Needing control over base image, system libraries, and build chain | Wanting to deploy with an appropriate managed runtime |

This lesson uses the **container-image model** to explain the relationship with Fn Project and practice with Java. Do not infer that every OCI Functions workflow requires writing a Dockerfile or pushing an image. See [About Code-only Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functions-codeonly-about.htm).

## 3. Application, Function, Invocation, and Trigger

### 3.1. Application Is the Shared Configuration Scope

An **application** groups related functions and provides a shared configuration context. In OCI Functions, an application is tied to subnet selection, configuration, and runtime isolation boundaries between applications. See [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

For example, an `order-events` application can contain `validate-order` and `create-order-summary`. Group functions that have compatible configuration and governance needs; belonging to the same business domain alone is not enough to ignore permission or networking differences.

### 3.2. Function Is the Deployable Definition

A **function** has executable code and metadata such as artifact source, memory, and timeout. The function name, function OCID, and image version are identifiers serving different purposes.

For example, the `create-order-summary` function can be updated to a new image while retaining the same business role. Release records must capture both the function identifier and the approved artifact.

### 3.3. Invocation Is a Single Call

An **invocation** is a request to execute a function. A function can receive many invocations over time or concurrently. The invocation payload is per-call data; function configuration is operational data shared across calls.

### 3.4. Trigger Is the Request Source

A **trigger** is the event or action that causes an invocation request to be sent. Functions can be invoked directly or integrated with supported event sources.

The relationships among these four concepts are described in [OCI Functions Concepts](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsconcepts.htm).

Design example:

| Element | Illustrative Value |
| --- | --- |
| Application | `order-events` |
| Function | `create-order-summary` |
| Trigger | New object event requiring processing |
| Payload | Namespace, bucket, object name, and event ID |
| Result | Summary written to the designated storage location |

Payloads should carry references to large data. A function receiving "the address of the object to process" can download the exact data when needed, rather than forcing every intermediate layer to carry the entire object content.

## 4. Overall Architecture: From Source Code to Runtime Environment

The diagram below depicts the **container-image flow**. Boxes represent logical responsibilities, not an internal server architecture that users build themselves.

~~~mermaid
flowchart TB
    subgraph DEV["Development or CI environment"]
        CODE["Java code and func.yaml"] --> CLI["Fn CLI and context"]
        CLI --> BUILD["Build using FDK"]
    end

    BUILD -->|Push image| OCIR["OCIR"]
    CLI -->|Create or update metadata| META["Application and function on OCI"]

    CALL["Caller or integrating service"] -->|Authenticated invocation request| INVOKE["Invoke endpoint"]
    INVOKE --> EXEC["OCI-managed execution environment"]
    META --> EXEC
    OCIR -->|Prepare image when needed| EXEC
    EXEC --> FDK["FDK → Java handler"]

    FDK --> PRIVATE["Resources in VCN"]
    FDK --> SERVICE["Authorized OCI services"]
    EXEC --> OBS["Logs, metrics, and tracing when configured"]
~~~

The architecture can be read across three flows:

1. **Release flow:** build artifact, publish artifact, create or update function definition.
2. **Execution flow:** authenticate request, prepare or reuse runtime environment, invoke handler, handle response.
3. **Dependency access flow:** code inside the function connects to other services using the appropriate network path and identity.

For example, CI can deploy successfully while the function still fails to read Object Storage. In that case, check the function's permissions and access path to Object Storage; deployment success confirms only part of the architecture.

### 4.1. Control Plane and Invocation Flow

In this lesson, **control plane** refers to resource management operations: creating an application, setting subnets, updating a function, and configuring memory and timeouts.

The invocation flow uses the function's endpoint to send execution payloads. The regional management API endpoint and the function's invoke endpoint serve two different purposes. When integrating, retrieve the endpoint from metadata or supported tooling rather than constructing it manually from the function name. Oracle describes retrieving it with `fn inspect function` in [Differences between OCI Functions and Fn Project](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsdiffswithfn.htm).

### 4.2. User and Service Responsibilities

| Concern | Primary Responsibility |
| --- | --- |
| Provisioning and operating service execution servers | OCI Functions |
| Business logic and input validation | Development team |
| Packaged dependencies and base image | Image-owning team |
| IAM, compartments, subnets, and routes | OCI deployment team |
| Artifact retention, releases, and rollback plan | Operations and CI/CD team |
| Latency, cost, load targets, and alerting | Application-owning team |

Serverless reduces server management. Decisions about data, permissions, connectivity, and failure behavior still must be designed.

## 5. What Does FDK Do When Running a Java Function?

The FDK provides the integration layer between Fn's execution protocol and language-specific code. For image-based functions, the toolkit includes a build base image, a runtime base image, and a handler support library. See [Function Development Kits](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionssupportedlanguageversions.htm).

A Java flow can be understood as:

~~~text
Invocation payload
    → FDK receives and converts input
    → invokes the declared handler method
    → receives return value or error
    → constructs response per platform mechanism
~~~

Simple handler example:

~~~java
package com.example.fn;

public class HelloFunction {
    public String handleRequest(String input) {
        String name = (input == null || input.isEmpty()) ? "world" : input;
        return "Hello, " + name + "!";
    }
}
~~~

Corresponding entry point:

~~~yaml
cmd: com.example.fn.HelloFunction::handleRequest
~~~

This is a handler model; you do not write an HTTP request loop or start a web server in the example. A container that runs standalone does not automatically prove it satisfies Fn's invocation contract; custom images must ensure compatibility with platform requirements.

The Java example and project layout are introduced in [Introduction to Fn with Java](https://fnproject.io/tutorials/JavaFDKIntroduction/).

## 6. Execution Lifecycle, Cold Starts, and Scalability

### 6.1. Preparing and Reusing Environments

On an invocation requiring a fresh environment, the platform must allocate execution resources and initialize the runtime. For Java, initialization also involves the JVM and application components. An invocation that can reuse an already-warm environment typically avoids part of that startup cost.

Oracle refers to initial provisioning as a **cold start** and reusing warm infrastructure as a **hot start**. **Provisioned concurrency** keeps execution capacity warm for a configured concurrency level. See [Reducing Initial Latency Using Provisioned Concurrency](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingprovisionedconcurrency.htm).

Design implications:

- Do not assume every invocation gets a brand-new environment.
- Do not assume the same environment will persist indefinitely.
- Do not use static variables or data inside the container as the sole business record.
- Reuse clients or caches only when doing so is safe and does not leak data across invocations.

For example, a catalog cache should only accelerate lookups; the application must still behave correctly if the cache disappears. Conversely, a state such as "order has been paid" must reside in an appropriate durable data store.

### 6.2. Concurrency Affects the Entire Downstream System

**Concurrency** is the number of simultaneous executions. A scaling function can open many database connections, send many requests to external APIs, or perform many Object Storage operations.

Estimation example:

~~~text
Arrival rate:                  40 requests/second
Average processing duration:   0.5 seconds
Average concurrency:           approximately 40 × 0.5 = 20
~~~

This is a steady-state estimate, not a provisioning guarantee. Bursts, processing time variance, and retries can push actual concurrency much higher.

If each execution opens multiple connections, total system connections can be far larger than projected from a single test call. Limit downstream resource usage, set timeouts on every operation, and perform load testing.

OCI Functions enforces regional limits on applications, functions, memory for concurrent execution, and provisioned concurrency. Effective values depend on tenancy; see [Viewing Current Limit Values for OCI Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsviewinglimits.htm).

### 6.3. Memory and Timeout

Memory affects a function's processing capacity and is a factor in evaluating resource consumption. Timeout caps execution duration; timeouts on callers or integration tiers may be even shorter.

Per current documentation:

| Parameter | Value to Know |
| --- | --- |
| Default Sync timeout | 30 seconds |
| Maximum Sync timeout | 300 seconds |
| Maximum Detached timeout | 3,600 seconds |
| Memory for this lesson's Java example | Start measuring at 256 MB |

Oracle recommends a minimum of 256 MB memory for Java functions. After modifying `func.yaml`, you must redeploy for the setting to take effect on the service; also verify the deployed function definition. See [Changing Default Memory and Timeout Settings](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscustomizing.htm).

In real projects, measure initialization time, business execution time, and memory before choosing settings. Increasing a timeout does not fix a hung query or a misconfigured network path.

## 7. Sync, Detached, and Result Contracts

OCI Functions supports two invocation types:

| Type | Caller Behavior | How Results Are Managed |
| --- | --- | --- |
| Sync | Waits for function completion and receives response | Result is returned to caller |
| Detached | Regains control once processing starts | Function handles the outcome; an appropriate destination can be configured |

With Detached, HTTP `202` does not mean business processing has completed. You must define where state and results are stored and how failures are tracked. Fn CLI is suited for development; Oracle does not recommend using it for invocations in production. See [Invoking Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsinvokingfunctions.htm).

Examples:

- Validating a value and returning an immediate answer can use Sync.
- Longer data processing can consider Detached if limits and result delivery fit.
- A multi-step workflow requires explicit state, recovery mechanisms, and proper orchestration.

Do not treat Detached as an "exactly-once processing" guarantee. Callers or integrating services may retry after errors; business design must tolerate duplicate invocations when they occur.

## 8. VCN: Function Invocation Path and Outbound Path

### 8.1. Application Subnet Serves the Execution Environment

When creating an application, the deployer selects a VCN, subnet, and compute architecture. Images must match the application's architecture; for example, an AMD64-only image cannot run on an ARM-only application.

A regional subnet is recommended by Oracle to better support availability across availability domains. See [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

Examples of required connectivity paths:

| Target Accessed by Function | Factors to Define |
| --- | --- |
| Database with private endpoint | DNS, routes, NSG/security lists, connection port, and DB authentication |
| OCI services over an appropriate private path | Service Gateway, routes, and IAM |
| External public API | Appropriate egress path, DNS, HTTPS, and timeouts |
| Artifact for image-based function | Service ability to access a valid image |

This is a checklist for designing connectivity. Each path must be verified against the target service's networking documentation and the actual tenancy configuration.

### 8.2. A Private Subnet Does Not Automatically Lock Down the Invoke Endpoint

Key point: **placing an application in a private subnet does not automatically block access to the invoke endpoint from the Internet**. Oracle requires IAM to control invoke permissions; network source conditions can also be evaluated when appropriate. See [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm).

Distinguish clearly:

~~~text
Caller → invoke endpoint:
    Check caller identity, invoke permissions, and entry-point architecture.

Function → target resources:
    Check runtime environment networking and permissions to access those resources.
~~~

If using API Gateway as the application's entry point, separately design client authentication, Gateway permissions to invoke the function, and the HTTP contract. Having a Gateway does not replace the function's permissions to read buckets or connect to databases.

## 9. IAM: Three Identities, Three Permission Scopes

### 9.1. Deployer Identity, Caller Identity, and Execution Identity

| Entity | Need | Question to Answer |
| --- | --- | --- |
| Developer or CI | Create/update applications, functions, and artifacts | Is it allowed to deploy in this compartment? |
| Caller | Send invocations | Is it allowed to invoke this function? |
| Running function | Call other services | Is it allowed to read the target object or secret? |

Do not infer runtime permissions from developer administrative permissions. A deployer may be able to read a bucket while the function does not yet have read access; likewise, a caller invoking a function does not automatically gain permission to manage the function.

Workflow permissions also span networking, OCIR, and observability. Write policies scoped to required resources and compartments rather than granting broad tenancy-wide permissions by default. See [Creating Policies to Control Access to Network and Function-Related Resources](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingpolicies.htm).

### 9.2. Example Invoke Permission for One Function

Assume group `FunctionCallers` belongs to the `Default` domain and the function resides in the `AppDev` compartment:

~~~text
Allow group 'Default'/'FunctionCallers' to use fn-invocation in compartment AppDev where target.function.id = '<FUNCTION_OCID>'
~~~

Replace `<FUNCTION_OCID>` with the actual value. If using Fn CLI to look up resources by name, the caller may also need corresponding metadata read permissions; execution and lookup permissions serve different operations.

Evaluate the union of all granted policies. A policy scoped to one function does not revoke permissions already granted by another broader policy. Patterns for restricting by function or application are in [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm).

### 9.3. Resource Principal for a Function Calling OCI Services

A function running on OCI can use a **resource principal** via the OCI SDK. A dynamic group defines which functions belong to the group; policies grant permissions on target resources.

Example rule for a specific function:

~~~text
ALL {resource.type = 'fnfunc', resource.id = '<FUNCTION_OCID>'}
~~~

Example policy allowing dynamic group `OrderFunctions` to read objects in a designated bucket:

~~~text
Allow dynamic-group 'Default'/'OrderFunctions' to read objects in compartment AppData where target.bucket.name = 'order-input'
~~~

This grants object read permissions; if business logic needs to write outputs, design additional write permissions accordingly. Do not broaden permissions before identifying the exact required operations.

Resource principals allow code on OCI to authenticate using the resource's identity, avoiding bundling a developer's API private key into the image. The SDK must be configured to use the resource principal provider. See [Accessing Other Oracle Cloud Infrastructure Resources from Running Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm).

## 10. Practicing Fn Project with Java Locally

The goal of this section is to observe Fn CLI, Fn Server, FDK, and the handler together in an end-to-end flow. The commands are instructions for learners to run, not pre-run output from a tenancy.

### 10.1. Prerequisites

Use a suitable Linux or WSL environment with:

- A compatible, running container engine.
- Fn CLI compatible with the Java runtime to be used.
- Network connectivity to download base images and project dependencies.
- Local port `8080` not already occupied by another service.

In the first terminal, start Fn Server:

~~~bash
fn start
~~~

Keep this terminal running. Local Fn Server provides a development endpoint at `http://localhost:8080`. See [Using Fn Server to Develop Functions Locally](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingwithfnserverlocally.htm).

### 10.2. Creating a Dedicated Local Context

In a second terminal:

~~~bash
fn create context fn-architecture-local --provider default
fn use context fn-architecture-local
fn update context api-url http://localhost:8080
fn update context registry fnlocal
fn list contexts
~~~

A context determines which endpoint the CLI calls and which registry prefix it uses. Before deploying, check the active context marker to avoid accidentally running commands against a different environment. See [Fn Development with Multiple Contexts](https://fnproject.io/tutorials/basics/UsingContexts/).

### 10.3. Initializing a Java Function

In a new lab directory:

~~~bash
fn init --help
fn init --runtime java17 hello-java
cd hello-java
~~~

`java17` is an example runtime; check the options supported by your installed CLI version. Use the CLI-generated project to keep FDK and base image versions aligned. Guidance on identifying runtimes is in [Function Development Kits](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionssupportedlanguageversions.htm).

Main project components:

~~~text
hello-java/
├── func.yaml
├── pom.xml
└── src/
    ├── main/java/com/example/fn/HelloFunction.java
    └── test/java/com/example/fn/HelloFunctionTest.java
~~~

| Component | Meaning |
| --- | --- |
| `func.yaml` | Development metadata and function configuration |
| `pom.xml` | Dependencies, Java build, and test support |
| `HelloFunction.java` | Handler containing logic |
| `HelloFunctionTest.java` | Starter test generated by the skeleton |

You can use the handler from section 5. If you alter return behavior, update the corresponding test in your lab project.

In `func.yaml`, check the following fields and set memory and timeout for the lab:

~~~yaml
schema_version: 20180708
name: hello-java
version: 0.0.1
runtime: java17
memory: 256
timeout: 30
cmd: com.example.fn.HelloFunction::handleRequest
~~~

This is a **field excerpt**, not an instruction to replace the entire file. Keep the `build_image`, `run_image`, and dependency settings generated by the CLI. Do not copy an old FDK tag verbatim from a lesson into every new project.

### 10.4. Deploying and Invoking Locally

~~~bash
fn create app fn-architecture-local
fn deploy --app fn-architecture-local --local
printf '%s' 'OCI' | fn invoke fn-architecture-local hello-java
~~~

With the handler from section 5, expected output:

~~~text
Hello, OCI!
~~~

Test empty input:

~~~bash
printf '%s' '' | fn invoke fn-architecture-local hello-java
~~~

Expected output:

~~~text
Hello, world!
~~~

During deploy, the CLI builds the image and registers the function with the local Fn Server. The invocation flows through Fn Server and the FDK to the handler. The Java workflow is introduced in [Introduction to Fn with Java](https://fnproject.io/tutorials/JavaFDKIntroduction/).

### 10.5. Limitations of Local Results

Local success validates the handler and packaging. It does not verify IAM, VCN, service limits, or database connectivity on OCI.

A function's resource principal on OCI is not tested by a local Fn Server call. For code calling the OCI SDK, use mocks or a dedicated development authentication config; never embed personal keys into artifacts pushed to the cloud. This limitation is noted in [Using Fn Server to Develop Functions Locally](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingwithfnserverlocally.htm).

## 11. Moving the Development Flow to OCI Functions

### 11.1. Preparing Cloud Resources

Before deploying, ensure you have:

| Resource or Config | What to Confirm |
| --- | --- |
| Region and compartment | Where the application and function are created |
| VCN and subnet | Aligned with the resources the function will access |
| Application | Created on OCI with an architecture compatible with the image |
| Developer/CI IAM | Sufficient permissions for function, network, and artifact operations |
| OCIR | Registry and repository receiving the image |
| Tool authentication | OCI profile and registry login credentials |
| Logging | Log storage configured to inspect the first invocation |

In the lab, create the `fn-architecture-oci` application via the Console, selecting the prepared VCN and subnet. If the image is built for AMD64, choose a compatible application architecture; when using a multi-architecture application, prepare corresponding multi-arch artifacts.

Application creation and architecture choices are described in [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

### 11.2. Creating a Dedicated OCI Context

Bash example for the Ashburn region:

~~~bash
export FUNCTIONS_COMPARTMENT_OCID='REPLACE_WITH_FUNCTIONS_COMPARTMENT_OCID'
export IMAGE_COMPARTMENT_OCID='REPLACE_WITH_IMAGE_COMPARTMENT_OCID'
export TENANCY_NAMESPACE='REPLACE_WITH_REAL_NAMESPACE'
export REGISTRY='ocir.us-ashburn-1.oci.oraclecloud.com'

fn create context fn-architecture-oci --provider oracle
fn use context fn-architecture-oci
fn update context api-url https://functions.us-ashburn-1.oci.oraclecloud.com
fn update context oracle.compartment-id "$FUNCTIONS_COMPARTMENT_OCID"
fn update context oracle.image-compartment-id "$IMAGE_COMPARTMENT_OCID"
fn update context oracle.profile DEFAULT
fn update context registry "$REGISTRY/$TENANCY_NAMESPACE/learning"
fn list contexts
~~~

Replace the placeholders and ensure the `DEFAULT` profile is configured for the right tenancy, user, and region. `oracle.compartment-id` is where the function resides; `oracle.image-compartment-id` is where the image repository resides. See [Creating an Fn Project CLI Context to Connect to Oracle Cloud Infrastructure](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatefncontext.htm).

With function `hello-java` and the registry prefix above, the expected repository is `learning/hello-java`. Check the actual repository name and compartment used by your workflow, especially if a repository with that name already exists.

### 11.3. Authenticating to OCIR and Deploying

Log in to the registry with your full tenancy username and auth token:

~~~bash
export OCIR_USERNAME='REPLACE_WITH_FULL_OCIR_USERNAME'
docker login "$REGISTRY" --username "$OCIR_USERNAME"
~~~

When prompted for a password, enter the OCI auth token. Registry login handles image pushes; the `oracle` provider and OCI profile handle OCI APIs. Both authentication setups must be prepared separately. You can follow [Functions QuickStart on Cloud Shell Using Container Images](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartcloudshell.htm).

From the `hello-java` directory, with the OCI context verified:

~~~bash
fn deploy --app fn-architecture-oci
fn inspect function fn-architecture-oci hello-java
printf '%s' 'OCI' | fn invoke fn-architecture-oci hello-java
~~~

The expected output remains `Hello, OCI!`. However, this call additionally tests the cloud integration path: API, artifact, application, and the OCI execution environment.

Record the function OCID, region, application, deployed image reference/digest, commit ID, and invoke output. That data helps cross-check during re-releases or change investigations.

### 11.4. Interpreting Results Layer by Layer

| Observed Outcome | What Has Been Proven | What Still Needs Verification if Business Requires It |
| --- | --- | --- |
| Build succeeds | Code and dependencies package cleanly | IAM and networking on OCI |
| Push succeeds | Publishing identity can upload image to OCIR | Function execution capability |
| Deploy succeeds | Function definition created/updated | Connectivity path to business data |
| Invoke returns expected greeting | Invocation path and handler work | Permissions to read buckets, secrets, or databases |
| Target service call succeeds | Specific integration flow works | Concurrent load, failures, and recovery |

This table helps avoid concluding that a "Hello World" test verifies an entire production system.

## 12. Configuration, Secrets, and State

### 12.1. Shared Configuration and Per-Function Configuration

Custom configuration can be set on an application or a function. Function configuration overrides values with the same key on the application; values are also exposed as environment variables. See [Passing Custom Configuration Parameters to Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionspassingconfigparams-about.htm).

Example:

~~~bash
fn config app fn-architecture-oci APP_ENV dev
fn config function fn-architecture-oci hello-java MESSAGE_PREFIX Hello
~~~

Configuration commands are documented in [Specifying Custom Configuration Parameters](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionspassingconfigparams.htm). Setting `MESSAGE_PREFIX` does not automatically alter the sample handler; code must explicitly read that value if needed.

Separate operational values from per-invocation data:

| Type | Example |
| --- | --- |
| Operational config | Target bucket name, log level, service endpoint |
| Per-invocation data | Order ID, object name, event ID |
| Secrets | DB password, external API token |
| Durable state | Processing outcome, deduplication key, workflow progress |

Secrets should be managed through a mechanism such as OCI Vault suited to the architecture. Never place secrets in source code, images, or logs; functions should fetch values only when authorized and needed.

### 12.2. Statelessness and Idempotency

**Stateless** means the correctness of an invocation does not depend on a previous call leaving data behind in the same runtime environment.

**Idempotency** means processing the same request repeatedly does not produce unintended duplicate business side effects.

Order-processing design example:

~~~text
Receive event with eventId
    → determine business key
    → record or check key via a consistent operation
    → if already completed: return existing result
    → if not: execute and save result
~~~

This is a conceptual model. If "check" and "record" are split without atomicity, two concurrent invocations can still produce duplicate records.

With Oracle Database, you can use unique constraints and appropriate transactions for business keys. When side effects hit an external API, also consider API idempotency keys or coordination mechanisms; a local transaction does not automatically guarantee atomicity across two systems.

## 13. Observability: Logs, Metrics, and Tracing

### 13.1. Logs to Explain a Single Execution

Enable OCI Logging for the application and assign an appropriate log group. Logs should include data connecting an invocation to business work, such as request ID or event ID, processing step, and operation duration.

Example of deliberately structured application logs:

~~~json
{
  "eventId": "evt-order-001",
  "operation": "create-summary",
  "status": "completed",
  "durationMs": 84
}
~~~

You do not need to log entire payloads to investigate every issue. Select essential fields and control sensitive data.

OCI Functions supports configuring log line formats; to query JSON fields, emit valid JSON logs and pick a matching format. See [Storing and Viewing Function Logs](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsexportingfunctionlogfiles.htm).

### 13.2. Metrics to Spot Trends

The Functions metrics namespace is `oci_faas`. Metrics track invocation counts, execution duration, error responses, and throttling. See [Function Metrics](https://docs.oracle.com/en-us/iaas/Content/Functions/Reference/functionsmetrics.htm).

| Observation | Operational Question |
| --- | --- |
| Invocations rising | Is this real traffic, retries, or an event loop? |
| Execution duration rising | Is latency in the handler, initialization, or target service? |
| Error rate rising | Input errors, permission errors, resource limits, or business errors? |
| `429` responses rising | Are effective capacity or concurrency limits exceeded? |
| DB load rising with concurrency | Do connections and intake rate need throttling? |

Set alarms aligned with service objectives, combining sample counts and evaluation windows. A single isolated error and a sustained rise in error rates require different responses.

### 13.3. Tracing to Find Slow Segments

When tracing is enabled on the appropriate application and function, APM can inspect execution steps. Tracing is useful when total duration increases but logs do not reveal which operation took the time. See [Troubleshooting OCI Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionstroubleshooting.htm).

When measuring the system, separate at least:

~~~text
Latency observed by caller
    = intermediate tier latency
    + queuing and initialization if any
    + function processing time
    + response transmission
~~~

This is an investigative breakdown. Do not treat handler duration measured by a timer inside code as the entire latency experienced by users.

## 14. Cost, Availability, and Recovery

### 14.1. Estimating from Workload

A rough model for resource volume is:

~~~text
GB-seconds volume
    ≈ invocation count × average execution duration × memory in GB
~~~

For example, assuming 100,000 invocations each running 0.2 seconds with 1 GB of memory gives a reference volume of 20,000 GB-seconds. This is a technical estimate prior to billing rules, not a price quote.

When budgeting, include all components actually used: artifacts, logs, network egress, downstream services, and provisioned concurrency if enabled. Consult current pricing tables, free-tier terms, and billing rules at deployment time.

Cost controls should address root causes:

- Reduce unnecessary wait time with timeouts and optimized data access.
- Measure memory and latency before picking configurations.
- Avoid excessive logging under high throughput.
- Cap retries and detect function invocation loops.
- Monitor load imposed on databases or APIs billed separately.

Provisioned concurrency is an option for strict initial-latency requirements. Measure p95/p99 targets and concurrency demand before configuring it; do not treat one "warm" call as representative of every load state.

### 14.2. Availability of the Function and the End-to-End Flow

Managed function execution does not automatically guarantee that all application dependencies are available.

For example, the function may still run while the database is temporarily unreachable. The design must specify timeouts, error responses, where unprocessed state is recorded, and retry conditions. Retries must respect idempotency and database load limits.

Evaluate all of the following:

| Scope | What to Prepare |
| --- | --- |
| Runtime | Memory, timeout, architecture, and limits |
| Network | Subnet, routes, DNS, and target connectivity |
| Data | Consistency, backups, and recoverability |
| Artifacts | Released builds remain accessible and redeployable |
| Observability | Logs, metrics, and alarms in the right places |
| Standby region if required | Matching resources, artifacts, config, permissions, and data |

A recovery package needs more than a source file. Manage configuration with reproducible processes and test deployment in the standby environment according to system objectives.

## 15. Troubleshooting by Architectural Layer

| Symptom | Layer to Check First | Evidence to Collect |
| --- | --- | --- |
| Runs locally, OCI deploy fails | Context, profile, and deploy permissions | Active context, region, compartment, and error message |
| Image push fails | OCIR and publishing credentials | Target repository, identity, and push error |
| Invoke denied | Caller identity and invoke permissions | Function OCID, active policies, and request ID |
| Runtime init fails | Artifact, handler, or architecture | Image in use, `cmd`, dependencies, and logs |
| Slow only on first call | Initialization and cold start | Measurements across multiple states, not a single call |
| DB call times out | Network, DNS, and DB service | Connection target, wait duration, and connection settings |
| Bucket read denied | Resource principal and data permissions | Dynamic group, policies, and target bucket |
| Retries duplicate data | Business contract | Event ID, idempotency key, and transactions |
| Higher traffic triggers errors | Concurrency and dependencies | Functions metrics, DB connections, and retry rate |

This table provides triage directions and does not replace reading actual errors. During investigation, record timestamp, function OCID, deployment version, and correlation ID; strip secrets before sharing logs.

## 16. When Should You Choose OCI Functions?

OCI Functions fits when you have a clear unit of processing triggered by requests or events, able to complete within platform limits, and managing durable state externally.

Evaluate more carefully for workloads requiring long-lived processes, persistent connections, deep OS control, or runtimes exceeding platform limits. In those cases, consider container or compute platforms matched to specific requirements.

Once Functions is chosen for a design, the core questions to answer are:

1. Is the artifact an image or an archive, and who owns runtime updates?
2. Which application, compartment, and region does the function belong to?
3. Who deploys, who invokes, and what data is the function allowed to access?
4. How are payloads and results represented, and are duplicate calls handled?
5. What impact does concurrent load have on databases, APIs, and budget?
6. Is there enough information to detect failures and redeploy an approved build?

A complete architecture ties all of these decisions to the same business flow. Fn Project supplies the development model and tooling; OCI Functions adds the managed execution environment along with the OCI integrations required to bring functions into production systems.
