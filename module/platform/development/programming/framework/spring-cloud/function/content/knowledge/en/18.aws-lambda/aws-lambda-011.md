# Custom Runtime, Bootstrap, and Native Image Packaging

AWS Lambda can run Java applications using an AWS-managed runtime, yet it also allows you to supply your own startup mechanism and invocation handling. That mechanism is called a **custom runtime**. With Spring Cloud Function, a custom runtime is useful when you want control over the JVM, a specific runtime version, or to run an application compiled into a **GraalVM Native Image**. When deploying as a ZIP archive, Lambda looks for an executable file named **bootstrap** at the root of the package. This file starts the runtime and connects the application to the **Lambda Runtime API**.

This lesson belongs to the **AWS Lambda** chapter and explains how the runtime works, the responsibilities of bootstrap, differences between a managed Java runtime and an OS-only runtime, running Spring Cloud Function with a custom JVM, building a native image, packaging the ZIP, declaring AWS SAM, testing locally, and deploying. The later sections explain Spring AOT/native image limitations, adding runtime hints, common errors, and performance evaluation criteria.

The goal is to understand the full path from a **Function bean** to a **Lambda invocation**: Spring Cloud Function keeps business logic in Supplier, Function, or Consumer; the custom runtime receives events from AWS; the adapter/Runtime Interface Client (RIC) delivers events to the function; and bootstrap sends responses or errors back to Lambda.

## 1. Managed Runtime, Custom Runtime, and Native Image

Lambda can run code using an AWS-provided runtime or a user-managed runtime.

| Model | Runtime | Typical Artifact | Who Starts the Process |
| --- | --- | --- | --- |
| **Java managed runtime** | e.g., java21 | JAR/ZIP containing Java classes and dependencies | AWS Java runtime |
| **JVM custom runtime** | OS-only runtime plus JVM/launcher supplied by package or layer | ZIP with bootstrap, JVM or compatible Java runtime, JAR, and dependencies | Application's bootstrap |
| **Native image custom runtime** | OS-only runtime plus Linux executable | ZIP with bootstrap and native executable | Bootstrap launches executable; RIC must be in runtime |
| **Custom runtime container image** | Container image you build | OCI image in ECR | Lambda container entrypoint |

**Native Image does not run on a traditional JVM.** GraalVM analyzes the application at build time and produces an executable tailored to the target OS and architecture. Therefore, you cannot upload a JAR and ask Lambda to run a native image; you must package the executable alongside a bootstrap as a custom runtime.

~~~mermaid
flowchart TD
    A["Lambda invocation"] --> B{"Deployment model"}
    B --> C["Managed Java runtime"]
    B --> D["Custom runtime: JVM"]
    B --> E["Custom runtime: native image"]
    C --> F["AWS Java runtime"]
    D --> G["bootstrap -> JVM -> Spring Function"]
    E --> H["bootstrap -> native executable + RIC"]
    F --> I["Function bean"]
    G --> I
    H --> I
    I --> J["Response / error"]
~~~

### When Should You Choose a Custom Runtime?

Reasonable scenarios:

- You need a language/JVM version not yet offered by managed runtimes.
- You want control over the launcher, runtime libraries, or startup sequence.
- You want to run a GraalVM Native Image or another native binary.
- You have specialized RIC/runtime integration requirements.
- You want to standardize a shared runtime across multiple functions.

If a managed Java runtime already meets your needs and your Spring Cloud Function app runs via **FunctionInvoker**, that is usually the simpler choice. A custom runtime increases responsibility for bootstrap, RIC, OS compatibility, patching, and operations.

## 2. What Is an OS-Only Runtime?

OS-only runtimes belong to the **provided** family. AWS provides the Lambda operating system environment without a language runtime such as Java, Node.js, or Python. The current example for Amazon Linux 2023 is:

~~~text
provided.al2023
~~~

An OS-only runtime still provides the execution environment, environment variables, filesystem, logging integration, and the Runtime API endpoint. Your application must provide the remaining runtime layer.

**provided.al2023** is the illustrative choice for custom runtime ZIPs in this lesson. AWS maintains older runtimes through their respective deprecation periods, but for new deployments check the current runtime list and prefer Amazon Linux 2023 when compatible.

| Component | Provided by AWS | Package/Application Responsibility |
| --- | --- | --- |
| Lambda OS | Yes | Choose a compatible runtime family |
| Runtime API endpoint | Yes | Runtime client calls the API per contract |
| Bootstrap file | Not auto-generated for package | Provide at root and set executable permission |
| JVM | Absent in OS-only runtime | Package/supply via layer or use native executable |
| Spring Application | No | Build application and dependencies |
| RIC for native binary | Not automatically added to arbitrary binaries | Use an integration with RIC or integrate RIC directly |
| Function code | No | Implement Supplier/Function/Consumer |

Do not confuse an **OS-only runtime** with a regular EC2 instance or standard Linux container. Lambda still manages the execution environment lifecycle and interacts with your runtime through the Lambda Runtime API.

## 3. Lambda Runtime API and Invocation Lifecycle

A custom runtime must communicate with the **Lambda Runtime API**. AWS passes the API address in the environment variable:

~~~text
AWS_LAMBDA_RUNTIME_API
~~~

A basic runtime executes the following steps:

1. Read environment configuration and initialize shared resources.
2. Call the **next invocation** endpoint to wait for the next event.
3. Read the event body and headers containing request ID, deadline, ARN, and trace metadata.
4. Construct the invocation context and call the handler/function.
5. On success, send output to the **response** endpoint.
6. On failure, send error details to the **error** endpoint.
7. Loop back to receive the next invocation.

~~~mermaid
sequenceDiagram
    participant L as Lambda service
    participant R as Runtime API
    participant B as bootstrap / RIC
    participant F as Spring Function

    L->>R: Supply invocation
    B->>R: GET /runtime/invocation/next
    R-->>B: Event body + request headers
    B->>F: Invoke function with event/context
    F-->>B: Result
    B->>R: POST /runtime/invocation/{id}/response
    R-->>L: Response recorded
    B->>R: GET /runtime/invocation/next
~~~

### Key Endpoints

The Runtime API uses versioned endpoints, for example:

~~~text
GET  /2018-06-01/runtime/invocation/next
POST /2018-06-01/runtime/invocation/{awsRequestId}/response
POST /2018-06-01/runtime/invocation/{awsRequestId}/error
POST /2018-06-01/runtime/init/error
~~~

- **next**: long-polls to receive the next invocation.
- **response**: sends a successful result.
- **error**: reports an invocation processing error.
- **init/error**: reports errors occurring during runtime initialization.

The runtime must use the exact request ID received in the response header to build the response/error path. Besides the event body, the runtime receives deadline, invoked function ARN, and trace ID headers.

### Propagating Trace Context

If the Runtime API response includes the **Lambda-Runtime-Trace-Id** header, the runtime must set the corresponding value in the **_X_AMZN_TRACE_ID** environment variable for the invocation so AWS X-Ray can correlate traces. A custom-built runtime must handle this properly. When using a framework-provided RIC, the RIC handles this protocol detail.

### Avoid Writing Your Own Runtime API Client Unnecessarily

A tested RIC handles many error-prone details: long polling, request IDs, deadlines, error payloads, trace headers, retry/connection behavior, and shutdown. With Spring Cloud Function, use the appropriate custom runtime integration or native sample before considering writing your own RIC.

## 4. What Is Bootstrap?

**bootstrap** is the executable entry point of a custom runtime ZIP. When Lambda starts an execution environment, it looks for bootstrap at the root of the deployment package (or layer depending on runtime rules). If the file is missing, lacks execute permissions, or has the wrong format, invocations can fail with errors such as **Runtime.InvalidEntrypoint**.

A bootstrap script typically includes:

- A shebang specifying the shell, e.g., **#!/bin/sh**.
- Changing the working directory to **LAMBDA_TASK_ROOT**.
- Starting the JVM/runtime or native executable.
- Using **exec** so the main process replaces the shell and receives signals/runtime lifecycle events properly.

Example custom runtime ZIP layout:

~~~text
lambda-custom-runtime.zip
├── bootstrap
├── function-sample-aws-native
└── lib/                         # only needed if app packages separate dependencies
    └── dependency.jar
~~~

Bootstrap must have execute permissions on Linux. Before creating the ZIP:

~~~bash
chmod 755 bootstrap
file bootstrap
head -n 5 bootstrap
~~~

If authoring the script on Windows, verify:

- The file uses LF rather than CRLF if the shell/runtime does not tolerate CRLF.
- The shebang points to a shell present in the runtime.
- The ZIP preserves the executable permission bit.
- Bootstrap sits at the root, not nested inside a subdirectory.
- The script does not depend on hard-coded build-machine paths.

**Do not simply rename a text file to bootstrap.** It must have a valid shebang and the executable bit set.

## 5. Spring Cloud Function on Custom Runtime: Two Deployment Paths

Spring Cloud Function provides a unified programming model, while the entry point depends on the runtime.

### 5.1. JVM Custom Runtime

In this approach:

1. The ZIP contains bootstrap, a compatible JVM, the application, and dependencies.
2. Bootstrap starts the Spring Boot application.
3. The custom runtime/RIC mechanism connects invocations to functions per the Spring Cloud Function version guide you are using.
4. The handler/function name is configured per the custom runtime contract.
5. The Function bean remains a normal Supplier/Function/Consumer.

Spring Cloud Function documentation notes that a JVM custom runtime can use **spring-cloud-function-web**'s HTTP export. In releases using this approach, add the Web module and enable:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-web</artifactId>
</dependency>
~~~

~~~properties
spring.cloud.function.web.export.enabled=true
~~~

Verify bootstrap, dependencies, and handler conventions against the sample for your exact release line. With Spring Cloud Function's custom runtime, the Handler field typically carries the function bean name (e.g., **uppercase**); bootstrap remains the entry point filename at the ZIP root. Do not mix Spring Cloud Function 3.x/4.x samples with 5.x dependencies without checking migration notes.

### 5.2. GraalVM Native Image

In this approach:

1. Spring AOT and GraalVM produce a Linux executable.
2. The executable contains the compiled application and the required runtime/RIC mechanism.
3. The ZIP has bootstrap at the root alongside the native executable.
4. Lambda uses an OS-only runtime such as **provided.al2023**.
5. Bootstrap runs the executable without launching a JVM.

Spring Cloud Function provides an AWS Lambda native image sample. The package layout described in documentation:

~~~text
lambda-custom-runtime.zip
├── bootstrap
└── function-sample-aws-native
~~~

Minimal bootstrap:

~~~sh
#!/bin/sh

cd "$LAMBDA_TASK_ROOT"
exec ./function-sample-aws-native
~~~

This bootstrap is for a sample where **the native executable already embeds the required RIC/integration**. If you compile a plain Spring Boot native executable without a Lambda Runtime Interface Client, launching the binary from bootstrap alone is not enough to receive invocations. You must include a compatible RIC or use Spring Cloud Function's AWS native integration per the sample.

## 6. Example Function Bean for a Custom Runtime

We use a simple Function so the focus stays on the runtime:

File **src/main/java/example/lambda/NativeFunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NativeFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            NativeFunctionApplication.class, args);
    }

    public record TextRequest(String value) {}

    public record TextResponse(String value) {}

    @Bean("uppercase")
    Function<TextRequest, TextResponse> uppercase() {
        return request -> {
            if (request == null
                    || request.value() == null) {
                throw new IllegalArgumentException(
                    "value is required");
            }

            return new TextResponse(
                request.value().toUpperCase(Locale.ROOT));
        };
    }
}
~~~

Direct invoke payload:

~~~json
{
  "value": "hello lambda"
}
~~~

Business result:

~~~json
{
  "value": "HELLO LAMBDA"
}
~~~

The Function logic does not need to know whether it is running inside a managed JVM runtime or a GraalVM native image. The adapter is responsible for receiving events and converting inputs/outputs according to the runtime contract.

### Functional Bean Registration

Spring Cloud Function also supports functional bean registration via **ApplicationContextInitializer** and **FunctionRegistration**. This reduces some runtime bean configuration overhead and can help very small applications with strict cold-start targets.

Conceptual example:

~~~java
FunctionRegistration<Function<TextRequest, TextResponse>> registration =
    new FunctionRegistration<>(function)
        .type(FunctionType.from(TextRequest.class)
            .to(TextResponse.class));
~~~

This snippet illustrates the registration API, not a complete application. Use the exact API for your pinned Spring Cloud Function version. Functional registration does not automatically eliminate AOT limits or replace the RIC.

## 7. Configuring a JVM Custom Runtime with Bootstrap

A JVM custom runtime can launch a Java process from the package. Example shell bootstrap:

~~~sh
#!/bin/sh
set -eu

cd "$LAMBDA_TASK_ROOT"

CLASSPATH=".:lib/*"

exec java \
  -Dspring.main.web-application-type=none \
  -Dspring.jmx.enabled=false \
  -cp "$CLASSPATH" \
  example.lambda.NativeFunctionApplication
~~~

The example above illustrates launching a Spring application with dependency JARs under **lib/**. It assumes the ZIP provides a Java executable on PATH or bootstrap configures the path to the packaged JVM.

**Important:** simply launching Spring Boot does not by itself create a complete custom runtime. There must be a RIC or compatible custom runtime mechanism polling the Lambda Runtime API and dispatching events to the function. With Spring Cloud Function, follow the exact custom runtime sample for your release; do not copy this JVM bootstrap into a native image package.

### JVM Custom Runtime ZIP

Example layout:

~~~text
lambda-jvm-runtime.zip
├── bootstrap
├── bin/
│   └── java
├── lib/
│   ├── app.jar
│   └── dependency-1.jar
└── runtime/
    └── ...                      # JVM files if packaging the JVM separately
~~~

The actual layout depends on how you supply the JVM and RIC. If a Lambda layer provides the Java runtime, bootstrap must point to the exact path inside the layer and the layer must match the OS/architecture.

### When to Use a Managed Java Runtime

If you do not need to manage the JVM yourself, choose a managed runtime such as **java21** and use the **FunctionInvoker::handleRequest** handler. Then no bootstrap is needed. That is the model covered in earlier AWS Lambda lessons; pick a custom runtime only when runtime or native-image requirements genuinely call for it.

## 8. GraalVM Native Image and Spring AOT

**GraalVM Native Image** performs ahead-of-time compilation (AOT). Instead of a JVM loading classes and optimizing code at runtime, the native-image compiler analyzes entry points, reachable code paths, and build-time metadata to produce an executable.

Spring Boot includes **Spring AOT** processing to generate bean definitions, proxies, and runtime hints for GraalVM.

~~~mermaid
flowchart TD
    A["Java source + dependencies"] --> B["Spring AOT processing"]
    B --> C["Generated bean definitions"]
    B --> D["Reflection / resource / serialization hints"]
    C --> E["GraalVM native-image compiler"]
    D --> E
    A --> E
    E --> F["Linux native executable"]
    F --> G["bootstrap + ZIP"]
    G --> H["AWS Lambda provided.al2023"]
~~~

### Differences Compared to the JVM

| Aspect | JVM | Native Image |
| --- | --- | --- |
| Compilation | Bytecode runs on JVM; JIT optimizes at runtime | AOT compiled to a binary at build time |
| JVM runtime | Requires a JVM | No separate JVM required |
| Reflection | Dynamic access at runtime | Requires hints for dynamic paths not inferred statically |
| Classpath | Classes can be loaded via JVM mechanisms | Fixed at build time |
| Class loading | Supports lazy loading | No JVM-style lazy class loading |
| Spring bean definitions | Typically processed at app startup | Spring AOT pre-generates metadata/code |
| Artifact | JAR/ZIP | Native executable + bootstrap |
| Portability | Bytecode is largely OS/CPU-independent | Binary depends on OS, libc, and architecture |

### Closed-World Assumption

Native Image assumes the set of reachable code is known at build time. Classes or resources loaded dynamically by string name may be omitted from the binary unless the compiler knows they are needed.

Restrictions to note:

- Reflection requires appropriate hints.
- Resources read via dynamic names/paths may need resource hints.
- Serialization must know which types and members are accessed.
- Dynamic proxies must be registered ahead of time.
- The classpath cannot be extended dynamically at runtime.
- Spring configurations that alter the bean set dynamically at runtime may be restricted in native mode.
- Some libraries using JNI, dynamic class loading, or runtime bytecode generation may be incompatible.

Do not immediately blame AWS Lambda for native image errors. An application may run fine on the JVM yet fail AOT compilation due to missing hints or incompatibility.

## 9. Adding Runtime Hints When Needed

Spring AOT and Spring libraries supply many hints automatically. Add manual hints only when build/runtime reports show a type, field, constructor, method, or resource was not recognized.

Example registering reflection for DTOs:

~~~java
package example.lambda;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(TextRuntimeHints.class)
class NativeHintsConfiguration {
}

class TextRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            NativeFunctionApplication.TextRequest.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS);

        hints.reflection().registerType(
            NativeFunctionApplication.TextResponse.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
~~~

This illustrates the Spring Runtime Hints API. DTO records may already be handled automatically by the framework/serializer depending on version and conversion path; avoid adding redundant hints just to force a build through.

### Resource Hints

If your application reads template or schema files via dynamic paths, ensure those resources are included in the native image. Register resource patterns with RuntimeHints:

~~~java
hints.resources().registerPattern("templates/*.txt");
~~~

The pattern must match real resource paths on the classpath. Avoid overly broad patterns when only a few files are needed.

### Checking with the Native-Image Agent

The GraalVM Native Image Agent can observe a JVM run and record reflection/resource/serialization accesses. The captured config helps identify missing hints, yet the agent only records code paths executed during observation. It does not prove all paths are covered.

Sensible workflow:

1. Run tests with representative inputs/events.
2. Collect agent configuration if needed.
3. Review generated config and remove unneeded entries.
4. Translate into Spring Runtime Hints or native-image metadata appropriately.
5. Rebuild the native executable and test the corresponding paths.

## 15. Testing Spring AOT and Native Image

JVM unit tests remain valuable, yet they do not guarantee the native image will work. Also verify:

- Does Spring AOT complete cleanly?
- Did the native compiler find all needed reflection/resources/proxies?
- Does Jackson/serialization recognize the DTOs?
- Do dependencies use JNI or native libraries compatible with Linux?
- Does FunctionCatalog register the intended function in native mode?
- Are function definition and environment variables read as expected?
- Does the AWS Runtime Interface Client receive events and send responses?

### Testing on the JVM

~~~bash
./mvnw test
~~~

### Building the Native Image

~~~bash
./mvnw -Pnative native:compile
~~~

### Testing with SAM Local

~~~bash
sam local invoke NativeFunction --event events/request.json
~~~

### Testing on Staging Lambda

Deploy the ZIP to a staging function, invoke with a representative event, and verify:

- Init duration and duration.
- Request ID, logs, and runtime errors.
- Output serialization.
- Memory used and configured memory.
- Timeouts, downstream access, and IAM.
- Behavior on empty/malformed-schema payloads.
- Differences between cold start and warm invocation.

Native images must be tested on the exact Linux architecture Lambda runs on. Never run unit tests on Windows/macOS alone and assume the binary is deployment-ready.

## 16. GraalVM Native Image and Cold Starts: Measure Before Choosing

Native Image can lower application startup time and memory footprint compared to some JVM applications. However, there is no guarantee it is always faster or cheaper for every Lambda.

Total cold-start time also includes:

- Lambda preparing the execution environment.
- Downloading/extracting the deployment package.
- Starting bootstrap and the RIC.
- Initializing the Spring context.
- Initializing SDK clients, connection pools, and beans.
- Executing the first event-processing step.

A native executable can initialize Spring faster while increasing build times, binary size, optimization effort, and compatibility constraints. With managed Java runtimes, mechanisms like **SnapStart** can be considered where supported by the runtime and workload.

| Criterion | JVM Managed/Custom Runtime | GraalVM Native Image |
| --- | --- | --- |
| Build | Bytecode compiles faster | AOT compilation takes longer and uses more build resources |
| App startup | Includes JVM and Spring startup | Can be faster without a JVM |
| Warm execution optimization | JIT can optimize after warm-up | No comparable runtime JIT |
| Dynamic Java | More flexible | Requires hints; restricts dynamic class loading |
| Runtime maintenance | Managed runtime or self-managed JVM | Binary must be rebuilt on dependency/toolchain updates |
| Debugging | Rich JVM tooling | Native debugging/observability differs |
| Portability | Cross-platform bytecode | Binary is tied to OS/architecture |
| Overall cold start | Depends on JVM, Spring, and Lambda | Depends on build, bootstrap, RIC, and Lambda |

### Benchmarking Properly

Do not compare only Spring startup times on a laptop. Measure in staging Lambda with:

- Identical payloads and business logic.
- Same region and architecture.
- Fairly tuned memory/timeout settings.
- Multiple cold starts and warm invocations.
- Duration, Init Duration, billed duration, and memory.
- Error rates and downstream processing time.

Decide based on real workloads. Do not choose native image based on a single isolated benchmark or laptop startup numbers.

## 17. Security and Maintenance of a Custom Runtime

When managing the runtime yourself, the development team carries more responsibility:

- **Patch OS/runtime**: pick an AWS-maintained OS-only runtime and update packages as needed.
- **Patch the JVM** if bundling a JVM in the ZIP/layer.
- **Update the RIC**: use a version compatible with the Lambda Runtime API.
- **Supply chain**: pin dependencies, verify artifacts, and scan images/packages.
- **Least privilege**: the execution role should have only required permissions.
- **Secrets**: fetch from Secrets Manager/Parameter Store or an approved secrets mechanism; never bake secrets into native binaries.
- **Logging**: avoid logging payloads/tokens/PII; record request IDs and needed error metadata.
- **Rebuild the native image** whenever dependencies or runtime hints change.
- **Architecture**: publish separate artifacts for x86_64 and arm64 if supporting both.
- **Rollback**: retain previous artifacts and tested versions/aliases.

Native image does not make a binary immune to dependency vulnerabilities. Libraries compiled/linked into the executable must still be updated by rebuilding and re-releasing.

## 18. Troubleshooting Custom Runtime and Bootstrap

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| **Runtime.InvalidEntrypoint** | Missing bootstrap at root or file not executable | Check ZIP layout and mode 755 |
| **Permission denied** | Bootstrap/native binary lacks execute permission | chmod 755 before zipping |
| **Exec format error** | Binary built for Windows/macOS or wrong architecture | Check `file` on binary, Linux target, and x86_64/arm64 |
| **No such file or directory** despite file existing | Missing dynamic loader or native library | Check ELF interpreter, glibc, and linked libraries |
| Bootstrap exits immediately | Shell syntax, wrong path, or binary exit code | Check shebang, working directory, and stderr |
| Runtime does not receive events | Missing RIC or custom runtime not calling Runtime API | Verify RIC/integration and AWS_LAMBDA_RUNTIME_API |
| Invocation timeout | Runtime fails to call next/response properly or app hangs at startup | Check polling, deadline, and initialization |
| Cannot send response | Wrong request ID or response/error endpoint | Cross-check Runtime API contract |
| Traces not linked | Failed to propagate Lambda-Runtime-Trace-Id | Check _X_AMZN_TRACE_ID |
| Spring cannot find Function | Function bean not registered or wrong definition | Check FunctionCatalog and function definition |
| ClassNotFound in JVM custom runtime | Classpath/lib layout missing dependencies | Check bootstrap classpath and ZIP |
| Native image missing class | Code path/reflection stripped at build time | Read native-image report, add hints |
| JSON parse/serialize fails only in native | Insufficient reflection/serialization hints | Check Spring AOT and serializer hints |
| Cannot read config/resource | Resource not bundled into image | Add resource hints and check package |
| Beans differ between JVM and native | Dynamic runtime conditionals/profiles/configs | Review closed-world/AOT restrictions |
| Works locally yet fails on AWS | Differences in libc, architecture, IAM, or Runtime API | Test on staging Lambda with exact artifact |
| ZIP deploys yet invocation fails | Valid ZIP structure but broken binary/RIC | Check bootstrap and CloudWatch logs |
| Binary too large | Unneeded dependencies or native metadata | Analyze dependencies and reachability report |

### Reading Startup Logs

When a custom runtime fails to start, errors can occur before the Spring Function is ever called. Classify in order:

1. Did Lambda find bootstrap?
2. Did bootstrap execute?
3. Can the binary/JVM run on the target Linux environment?
4. Did the RIC connect to the Runtime API?
5. Did the Spring ApplicationContext initialize?
6. Did FunctionCatalog find the function?
7. Did payload conversion and business logic succeed?
8. Did the runtime send the response/error back to AWS?

Fixing the right layer avoids modifying Function code when the real issue lies in ZIP permissions, architecture, or the RIC.

## 19. Custom Runtime Release Checklist

- [ ] Clearly choose between JVM custom runtime and native image.
- [ ] Choose a supported OS-only runtime, e.g., provided.al2023.
- [ ] Spring Boot and Spring Cloud Function versions are compatible.
- [ ] Custom runtime includes an appropriate Runtime Interface Client.
- [ ] Bootstrap sits at ZIP root with executable permissions.
- [ ] Bootstrap uses the right shell, line endings, and working directory.
- [ ] Native executable is built for Linux and the exact target architecture.
- [ ] Binary is compatible with runtime libc/system libraries.
- [ ] Spring AOT build succeeds with complete runtime hints.
- [ ] FunctionCatalog/bean definition is verified.
- [ ] ZIP contains only required artifacts with proper root layout.
- [ ] SAM template uses Runtime/Handler/CodeUri matching the custom runtime.
- [ ] IAM execution role follows least privilege.
- [ ] Timeout, memory, and environment variables are tuned.
- [ ] Unit tests, native build, SAM local, and staging invocation all pass.
- [ ] Logs/metrics/alarms and rollback are prepared.

## 20. Hands-on Exercises

**Exercise 1 — Distinguishing runtimes.** Compare Java managed runtime, JVM custom runtime, and GraalVM native image. For each, state who supplies the runtime, which artifact is packaged, and which component starts the process.

**Exercise 2 — Runtime API.** Diagram an invocation lifecycle from GET next through POST response/error. Show where request ID, deadline, and trace headers appear.

**Exercise 3 — Bootstrap.** Write a bootstrap script launching a native binary. Explain the shebang, LAMBDA_TASK_ROOT, exec, and execute permissions.

**Exercise 4 — JVM custom runtime.** Package a Spring Cloud Function JVM app with bootstrap and dependencies. Configure handler/function name per the matching release sample; verify the RIC receives events.

**Exercise 5 — Native build.** Add Native Build Tools to Maven, run Spring AOT and GraalVM native compile. Record build duration and executable location.

**Exercise 6 — Architecture.** Produce two Linux builds for x86_64 and arm64. Explain why Windows/macOS binaries cannot run on Linux Lambda.

**Exercise 7 — ZIP layout.** Create a ZIP containing bootstrap and the native executable at root. Inspect with unzip -l and verify permissions after extracting on Linux.

**Exercise 8 — Runtime hints.** Create a DTO read by Jackson via reflection or a resource loaded dynamically by name. Run the native image, analyze failures, and add the required RuntimeHints.

**Exercise 9 — SAM local.** Define a resource with Runtime provided.al2023, Handler bootstrap, and CodeUri pointing to the native ZIP. Run sam local invoke with a JSON event and classify errors if the invocation does not reach the Function bean.

**Exercise 10 — Cloud staging.** Deploy the native ZIP to a staging Lambda. Inspect init duration, duration, memory, logs, architecture, IAM, and response.

**Exercise 11 — Comparing JVM vs. native.** Run the same business function on managed Java runtime and native custom runtime. Measure cold starts, warm duration, billed duration, memory, and cost for the workload.

**Exercise 12 — Runtime operations.** Establish a process to update the RIC, OS-only runtime, GraalVM, and dependencies. Design versioning/aliases/rollbacks for native artifacts.

### Key Takeaways

- **Custom runtimes** use bootstrap as the entry point; bootstrap and the RIC must integrate with the Lambda Runtime API.
- **provided.al2023** is an OS-only runtime on Amazon Linux 2023; Lambda does not provide a JVM or language runtime in this model.
- Spring Cloud Function supports custom runtimes for both JVM and GraalVM native images. Use samples from the exact release line so handler, RIC, dependencies, and bootstrap align.
- **Native image** produces a Linux OS/architecture-specific executable, not a JAR. The ZIP normally places bootstrap and the native binary at root.
- **Spring AOT** generates bean definitions and hints for reflection/resources/serialization/proxies. Native image has closed-world restrictions, so dynamic code may require adjustments.
- Build native executables for **Linux x86_64 or arm64** matching your Lambda; check libc and shared libraries.
- Native images can reduce startup time and memory yet increase build time and compatibility constraints. Benchmark on real Lambda before choosing.
- Testing must progress through unit tests, AOT/native build, SAM local, and cloud staging; a passing build does not prove Runtime API, IAM, or triggers are right.

### References

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): custom runtime, bootstrap, GraalVM Native Image, handler, routing, and sample packages.
- [AWS Lambda — Building a custom runtime](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-custom.html): Runtime API, initialization, invocation loop, bootstrap, and RIC.
- [AWS Lambda — Runtime API](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-api.html): endpoints for receiving invocations, responses, errors, and context headers.
- [AWS Lambda — OS-only runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html): provided runtime family, Amazon Linux 2023, and native executable requirements.
- [AWS Lambda — Creating a Bash custom runtime](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-walkthrough.html): bootstrap script, Runtime API, and package permissions.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): AOT, closed-world assumptions, generated hints, and native limitations.
- [Spring Boot — Building a native executable](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): Maven/Gradle Native Build Tools and buildpacks.
- [GraalVM Native Build Tools — Maven guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): configuring native-maven-plugin and building executables.
- [Spring Cloud Function — Native Image blog](https://spring.io/blog/2020/05/04/spring-cloud-function-native-images/): Spring Cloud Function native image example on AWS Lambda.

## 10. Building a Native Image with Maven

To produce a native executable, the project needs a compatible combination of Spring Boot, Spring Cloud Function, and GraalVM Native Build Tools.

Core Spring Cloud Function AWS dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Native Build Tools plugin:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
</plugin>
~~~

With a compatible **spring-boot-starter-parent**, Spring Boot can provide the **native** profile and associated AOT configuration. If not using this parent, configure the Spring AOT and Native Build Tools goals manually per your version's documentation.

Command to build the native executable in a compatible GraalVM/Linux environment:

~~~bash
./mvnw -Pnative native:compile
~~~

With globally installed Maven:

~~~bash
mvn -Pnative native:compile
~~~

The executable is created under **target/**. The exact binary filename depends on artifact/plugin configuration and must be checked in practice.

### Gradle

With Gradle, add the Native Build Tools plugin to the project:

~~~groovy
plugins {
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}
~~~

The Spring Boot Gradle plugin activates the corresponding AOT tasks when the native plugin is applied. Build the executable:

~~~bash
./gradlew nativeCompile
~~~

The binary usually resides under **build/native/nativeCompile/**. The filename depends on the project name and plugin settings. If building a native container image instead of a ZIP, you can use **bootBuildImage**; in that case, the deployment model is container image and requires a Lambda-compatible base image/entrypoint.

### Building with Containers/Buildpacks

Spring Boot also supports building an OCI image containing the native executable using Cloud Native Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

This command builds a **container image**; it does not automatically produce a ZIP with a bootstrap for a custom runtime. If choosing Lambda PackageType Image, use an appropriate Lambda-compatible base image/entrypoint. If choosing ZIP with **provided.al2023**, extract or build the native executable, add bootstrap, and package the ZIP separately.

### Choosing the Right OS and Architecture

The native executable must be built for Linux and Lambda's exact CPU architecture:

| Lambda Architecture | Native Build Target |
| --- | --- |
| **x86_64** | Linux AMD64 / x86-64 |
| **arm64** | Linux AArch64 / ARM64 |

Building on Windows produces a Windows executable that cannot run on Linux Lambda. Building on macOS likewise does not automatically produce a compatible Linux executable. Build inside an appropriate Linux container/CI image or use the configured container-build support of Native Build Tools.

Beyond architecture, pay attention to **glibc** and linked native libraries. A binary built on a newer Linux distribution may depend on a glibc version missing in the Lambda environment. Build in an Amazon Linux 2023-compatible environment or inspect dependencies with appropriate Linux tools.

## 11. Packaging the Native Image into a ZIP

Suppose the native executable has been built and is named:

~~~text
target/function-sample-aws-native
~~~

Create the package directory:

~~~bash
mkdir -p target/lambda-package
cp target/function-sample-aws-native target/lambda-package/
~~~

Create bootstrap at the package root:

~~~sh
#!/bin/sh
set -eu

cd "$LAMBDA_TASK_ROOT"
exec ./function-sample-aws-native
~~~

Set execute permissions:

~~~bash
chmod 755 target/lambda-package/bootstrap
chmod 755 target/lambda-package/function-sample-aws-native
~~~

Create the ZIP:

~~~bash
cd target/lambda-package
zip -r ../lambda-native.zip bootstrap function-sample-aws-native
cd ../..
~~~

Inspect contents:

~~~bash
unzip -l target/lambda-native.zip
~~~

The package must have two entries at root:

~~~text
bootstrap
function-sample-aws-native
~~~

Do not zip a parent folder around them:

~~~text
lambda-native.zip
└── lambda-package/
    ├── bootstrap
    └── function-sample-aws-native
~~~

If the ZIP wraps a parent directory, Lambda will not find bootstrap at the expected location.

### Inspecting the Binary on Linux

In the Linux build environment:

~~~bash
file target/function-sample-aws-native
ldd target/function-sample-aws-native
~~~

**file** shows the format/architecture. **ldd** checks dynamic libraries if the binary is dynamically linked. Not every native executable supports ldd in the same way; if the binary is static or the tool reports it does not apply, inspect using a method suited to your toolchain.

## 12. AWS SAM Template for a Native Image ZIP

Example **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function GraalVM native image

Resources:
  NativeFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: provided.al2023
      Handler: uppercase
      CodeUri: target/lambda-native.zip
      Architectures:
        - x86_64
      MemorySize: 512
      Timeout: 20
      Policies:
        - AWSLambdaBasicExecutionRole

Outputs:
  NativeFunctionArn:
    Description: Lambda function ARN
    Value: !GetAtt NativeFunction.Arn
~~~

Key points to understand:

- **Runtime: provided.al2023** selects the OS-only runtime on Amazon Linux 2023.
- **Handler: uppercase** is the function bean name that the Spring Cloud Function custom runtime will select. The OS-only runtime startup file must still be named **bootstrap** at the ZIP root; that is the runtime entry point, not the function bean name.
- **CodeUri** points to the packaged ZIP.
- **Architectures** must match the architecture of the native executable.
- **MemorySize/Timeout** are illustrative values that require benchmarking.
- **spring_cloud_function_definition** selects the bean when your application/adapter supports this property.
- **AWSLambdaBasicExecutionRole** grants basic logging permissions; if the Function calls S3, SQS, DynamoDB, or other services, add matching least-privilege permissions.

With Spring Cloud Function's custom runtime, **Handler: uppercase** represents the function bean invoked by the runtime; the **bootstrap** file remains the executable Lambda looks for at the ZIP root. If your sample release uses the **spring_cloud_function_definition** property instead of handler to select the bean, keep both consistent per the sample guide. When you have multiple functions and want dynamic routing, use **functionRouter** if supported by the runtime integration. Do not copy the managed Java **FunctionInvoker::handleRequest** setting to an OS-only native runtime, as a native package does not run a Java handler class on a JVM.

### SAM Build and Deploy

Since the native ZIP was built beforehand, you can validate the template:

~~~bash
sam validate
~~~

Then deploy:

~~~bash
sam deploy --guided
~~~

SAM/CloudFormation creates or updates the Lambda resource. If you want SAM itself to manage the native build/package, declare a suitable build workflow (Makefile/custom build) that generates the Linux executable and properly structured ZIP. Do not assume SAM's default Java builder automatically builds a GraalVM native image for Spring Cloud Function.

## 13. Creating the Lambda with AWS CLI

Once you have the ZIP and execution role, you can create the function via CLI:

~~~bash
aws lambda create-function \
  --function-name spring-function-native \
  --runtime provided.al2023 \
  --handler uppercase \
  --architectures x86_64 \
  --role arn:aws:iam::123456789012:role/lambda-execution-role \
  --zip-file fileb://target/lambda-native.zip \
  --timeout 20 \
  --memory-size 512
~~~

The role ARN and function name above are placeholders. The command creates real resources in an AWS account and may incur charges when invoked. Use a dev account/region and an appropriately scoped role.

Inspect the function:

~~~bash
aws lambda get-function-configuration \
  --function-name spring-function-native
~~~

Invoke with a JSON payload:

~~~bash
aws lambda invoke \
  --function-name spring-function-native \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

View the output:

~~~bash
cat response.json
~~~

If passing the Spring Cloud Function definition via environment variable, verify the value configured on the Lambda:

~~~text
spring_cloud_function_definition=uppercase
~~~

Do not treat a successful **aws lambda create-function** call as proof the native executable runs properly. Only a real invocation tests bootstrap, ABI, RIC, AOT hints, and event conversion.

## 14. Testing the Custom Runtime Locally with SAM Local

SAM local can launch a Lambda runtime container via Docker and send events into your custom runtime package:

~~~bash
sam local invoke NativeFunction --event events/request.json
~~~

Sample event file:

~~~json
{
  "value": "hello lambda"
}
~~~

With a native ZIP, verify:

- Docker can run the matching runtime container.
- The ZIP contains the executable bootstrap at root.
- The binary is a Linux executable.
- The binary architecture matches the container/target environment.
- Runtime configuration in SAM is **provided.al2023**.
- The native executable includes the RIC or matching integration.

### Testing the Binary Before Passing to SAM

In the Linux build environment, you can run the binary directly if the sample supports a local/test mode. However, a **Lambda native executable with a RIC** may require Runtime API environment variables that exist only inside the Lambda/SAM container. Therefore, running the binary directly in a terminal is not always a complete invocation test.

Distinguish between:

1. **Unit test**: tests Function logic on the JVM.
2. **Native smoke test**: verifies the binary starts without missing libraries.
3. **SAM local invoke**: tests bootstrap, runtime container, and event path.
4. **Cloud integration**: verifies AWS Runtime API, IAM, event sources, and real behavior.
