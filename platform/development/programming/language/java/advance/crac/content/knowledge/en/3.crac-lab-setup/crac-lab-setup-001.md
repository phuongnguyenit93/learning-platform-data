# Distinguishing a Standard JDK from a CRaC-Enabled JDK Build

When starting to work with CRaC (Coordinated Restore at Checkpoint), one of the first things to determine is whether the JDK being used actually supports checkpoint and restore. Two JDKs may both be based on Java 17 or Java 21, both run the same JAR file, and both provide the familiar tools, yet the capabilities of the JVM inside may differ.

**A standard JDK** provides a development and runtime environment for Java according to the features of the corresponding release. If the vendor has not integrated CRaC into that build, the JVM does not have the capability to checkpoint and restore processes using CRaC.

**A CRaC-enabled JDK build** is a JDK distribution or build that has integrated the necessary JVM-level support to coordinate creating a checkpoint and restoring a process. It is typically bundled with or used alongside the CRaC API so that applications can register resources that need to be handled before checkpoint and after restore.

The point to remember is that the Java version name is not enough to determine CRaC capability. You cannot conclude that every JDK 17, every JDK 21, or every OpenJDK build has CRaC. You need to check the exact vendor, build, version, and runtime environment.

## 1. What is a standard JDK?

A JDK (Java Development Kit) is a toolkit used for developing and running Java applications. A standard JDK typically includes:

- A JVM to run Java bytecode.
- The `javac` compiler and other development tools.
- Java platform libraries.
- Diagnostic and operational tools such as `jcmd`, `jstack`, `jmap`, or other tools depending on the distribution.

A standard JDK still supports familiar JVM capabilities such as class loading, garbage collection, JIT compilation, thread management, and executing Java applications. Spring Boot applications, web applications, command-line applications, or Java services can still run normally if they are compatible with that JDK version.

However, a JDK without CRaC integration cannot natively create a checkpoint of the Java process state and restore the process from a checkpoint using the CRaC mechanism. The fact that an application can compile and run on that JDK does not prove that the JVM supports checkpoint/restore.

For example, a team might develop an application using a standard JDK, build a JAR file, and run the application on a personal machine. When the team wants to create a checkpoint to start new instances faster, they need to check whether the JDK used in the checkpointing environment supports CRaC. If not, the checkpoint/restore operation will not be provided by that JVM.

## 2. What is a CRaC-enabled JDK build?

CRaC coordinates between the Java application and the JVM. The application needs an opportunity to prepare resources before the process state is saved, and then recreate or reconnect the necessary resources when the process is restored. The JVM needs to be able to participate in the process-level checkpoint/restore lifecycle.

A CRaC-enabled JDK build provides runtime-level integration to carry out this process. Depending on the vendor and version, the build may have changes or additional components compared to a standard JDK of the same Java line. These integrations allow the runtime environment to coordinate with the operating system's checkpoint/restore mechanism and invoke registered CRaC callbacks.

At a high level, the process consists of two points in time:

1. **Before checkpoint:** The JVM asks registered resources to prepare their state. The application can stop accepting new work, finish running tasks, close sockets, or release environment-dependent resources.
2. **After restore:** The JVM resumes the process from the checkpoint and asks resources to recover. The application can reopen connections, create new pools, refresh credentials, or restart background workers.

By saving the process state after the application has initialized and warmed up, CRaC can help reduce the work that has to be repeated when creating new instances. This capability depends on the JDK build, the checkpoint/restore platform, and how the application manages resources.

## 3. Comparing the two types of JDK

| Criterion | Standard JDK | CRaC-enabled JDK |
|---|---|---|
| Running standard Java applications | Yes, if the application is compatible | Yes, if the application is compatible |
| JVM and basic Java features | Yes | Yes, along with the build's CRaC integration |
| Creating a process checkpoint via CRaC | No, if the build does not integrate CRaC | Yes, in a supported environment |
| Restoring a process from a CRaC checkpoint | No, if the build does not integrate CRaC | Yes, according to the build's compatibility requirements |
| Executing the CRaC callback lifecycle | No CRaC JVM mechanism to trigger this lifecycle | JVM coordinates registered callbacks |
| `org.crac` API | Can use the API library as a compile-time dependency, but this does not add checkpoint capability to the JVM | Used according to the packaging and instructions of the JDK build |
| Operating system environment dependencies | According to standard JDK requirements | Additional requirements from the checkpoint/restore mechanism and CRaC build |
| Purpose of use | Developing, testing, and running Java applications | Running Java applications and supporting the checkpoint/restore workflow |

A CRaC-enabled JDK build is not a different Java language. The source code, bytecode, and most of how Java applications are developed remain familiar. The key difference lies in the capabilities of the runtime and the additional requirements when deploying checkpoint/restore.

## 4. Distinguishing the CRaC API from JVM CRaC support

This is the most easily confused point when setting up a project.

The CRaC API provides the types that application code uses to register and manage resources. The API is commonly used through the `org.crac` package, for example:

- `Resource`: the interface implemented by the component managing a resource.
- `Context`: the context passed into callbacks.
- `Core`: the entry point to the global CRaC context for registering resources.

Meanwhile, the JVM-level CRaC support is responsible for executing the checkpoint and restore process, as well as triggering the resource lifecycle at the right time.

You can visualize these two parts as follows:

```text
Java application code
       |
       | implements and registers Resource
       v
CRaC API (e.g., org.crac.Resource, Core, Context)
       |
       | JVM invokes callbacks during the checkpoint/restore lifecycle
       v
JVM from a CRaC-enabled build
       |
       | coordinates with the environment's checkpoint/restore mechanism
       v
Process checkpoint  <---->  Process restore
```

**Adding the API dependency does not automatically turn a standard JDK into a CRaC-enabled JDK.** The dependency helps the compiler recognize types like `Resource` and `Core`. It does not automatically add the necessary integration into the running JVM.

Conversely, merely installing a CRaC-enabled JDK does not guarantee that the application already manages resources properly. The application or relevant libraries still need to register and handle resources that may become invalid after a checkpoint.

### 4.1. Example of declaring the API in a project

A project can declare the CRaC API library as a dependency to compile code using `org.crac`. For example, with Gradle:

```groovy
dependencies {
    implementation("org.crac:crac:<appropriate-version>")
}
```

`<appropriate-version>` is the version to choose according to the documentation of the library, framework, and JDK build being used. You should not copy an arbitrary version from another project without checking compatibility.

Some distributions or integration guides may provide the API in their own packaging. Follow the vendor's documentation to avoid putting multiple incompatible API versions on the classpath.

Once the dependency is present at compile time, Java code can reference the `Resource` interface:

```java
import org.crac.Context;
import org.crac.Resource;

public final class CacheResource implements Resource {

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Stop updating the cache and put the resource into a safe state.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Check or refresh the cache state after restore.
    }
}
```

The resource-managing component needs to be registered with the appropriate context, for example the global context:

```java
import org.crac.Core;

CacheResource resource = new CacheResource();
Core.getGlobalContext().register(resource);
```

The code snippet above demonstrates implementing and registering callbacks. It does not create a checkpoint by itself. Whether the callbacks are invoked by the JVM depends on the CRaC runtime and the actual checkpoint/restore process.

### 4.2. What happens if you only have the API but run on a standard JDK?

The compiler can compile the code if the dependency provides the required API types. However, a standard JVM without CRaC integration will not be able to perform checkpoint/restore just because of that dependency.

The specific behavior of the API library when running on a runtime that does not support CRaC can depend on the version and how the API is implemented. Some integrations may allow the application to run in a non-checkpoint mode; an operation requesting a checkpoint may fail or report that it is unsupported. Therefore, you should not rely on the assumption that every CRaC API automatically becomes a no-op on every standard JDK.

If the project needs to run on both a standard JDK and a CRaC JDK, check the API and framework documentation, determine how to detect or configure the supported run mode, and test the two runtimes separately. Merely registering a resource does not prove that the checkpoint/restore workflow works.

## 5. Differences in the application lifecycle

With a standard JDK, the lifecycle of an instance typically begins when the JVM starts and ends when the process stops. The application initializes resources itself, serves requests, and closes resources on shutdown.

With a CRaC-enabled JDK, the lifecycle has additional state transition points: checkpoint and restore. Resources need to be coordinated through two main callbacks:

| Callback | Timing | Work typically performed |
|---|---|---|
| `beforeCheckpoint(...)` | Before saving the process state | Stop accepting new work, finish running tasks, close sockets or pools that need to be recreated |
| `afterRestore(...)` | After the process is restored | Reopen connections, create new pools, refresh tokens, or start workers |

For example, consider an application connecting to a database. On a standard JDK, the connection pool is typically created at startup and closed at shutdown. With CRaC, the connection pool needs to be prepared before checkpoint and recreated after restore if the old connections are no longer valid.

This is especially important because a checkpoint may be stored for a period of time before being used to create an instance. During that time, the database may drop connections, tokens may expire, DNS may change, or the network environment may be reconfigured.

## 6. Operating system and runtime environment requirements

CRaC capability does not depend solely on the JAR file. A checkpoint is the state of a running process, so creating and restoring it also depends on the operating system mechanism, kernel, CPU architecture, container runtime, and JDK build.

In many CRaC deployment environments on Linux, CRIU (Checkpoint/Restore In Userspace) is a key component in the checkpoint/restore process. Depending on the JDK distribution and deployment method, the system may require a compatible CRIU version, a kernel with the necessary features, specific container permissions or configurations, and filesystem settings.

You should not assume that a checkpoint created on a development machine can be restored on any server. Before deploying, confirm the vendor's support matrix for:

- CRaC JDK version and build.
- Operating system, kernel version, and CPU architecture.
- CRIU version or checkpoint/restore mechanism required by the build.
- Container runtime, permissions, and security configuration.
- Native libraries, file paths, mounts, and external resources.
- How checkpoints are stored, distributed, and protected.

A checkpoint must also be treated as sensitive data. Process memory can contain secrets, tokens, user information, or business data. Only authorized people and services should read or write checkpoints.

## 7. How to identify the JDK in use

You should not just look at the installation directory name or the Java version number. A machine can have multiple JDKs installed, and the `java` command may point to a different build than the `JAVA_HOME` used by the build tool.

First, inspect the runtime information:

```bash
java -version
```

This command helps identify the version, vendor, and build information that the current `java` command is invoking. You can also view additional environment properties:

```bash
java -XshowSettings:properties -version
```

In the output, pay attention to properties such as `java.home`, `java.vendor`, `java.version`, `os.name`, and `os.arch`. They help determine the actual runtime, operating system, and architecture running.

On Windows, you can check the executable path:

```powershell
where.exe java
```

On Linux or macOS:

```bash
which java
```

The commands above identify the runtime found by the shell. They are not enough to conclude that the runtime supports CRaC. Once you know the vendor, version, and build, cross-check them with the release documentation for that exact JDK.

## 8. How to verify a build supports CRaC

Verification should be based on both build information and a checkpoint/restore test in the target environment.

**Step 1: Identify the exact binary running.** Record the output of `java -version`, `java.home`, `java.vendor`, `java.version`, and `os.arch`. Check both the JDK used to build and the JDK used to run the application; these two environments can differ.

**Step 2: Read the vendor's documentation.** Find the exact product name, version, build type, and supported operating systems. Confirm that the build is announced as having CRaC, the corresponding API version, system requirements, and supported JVM options or checkpoint tools.

**Step 3: Check the API and dependencies.** Confirm that the project is using the exact `org.crac` version or API packaging required by the vendor. Check to avoid version conflicts between application libraries, frameworks, and the API provided by the runtime.

**Step 4: Run a minimal test.** Use a small example with a registered resource. Launch it with the exact CRaC JDK intended for deployment, perform a checkpoint according to the vendor's instructions, and then restore from the checkpoint. Observe the logs to confirm that the before-checkpoint and after-restore callbacks are invoked at the right time.

**Step 5: Test in the real deployment environment.** Repeat the test in the image, kernel, container runtime, permissions, and configuration intended for production. A successful test on a development machine does not guarantee that the production container environment meets the requirements.

If the vendor provides JVM options or diagnostic commands to verify CRaC, use the exact syntax for that version. Do not copy JVM flags from another JDK because option names, supportability, and checkpoint procedures may differ.

## 9. Example workflow with both types of JDK

A development team can use a standard JDK for part of their work and a CRaC JDK for checkpoint/restore integration testing. Sample workflow:

```text
Application source code
       |
       v
Standard Java build and tests
       |
       v
Check dependencies and CRaC API code
       |
       v
Build/launch with a CRaC-enabled JDK
       |
       v
Initialize application and run warm-up
       |
       v
Create checkpoint per JDK documentation
       |
       v
Restore in a compatible environment
       |
       v
Verify callbacks, connections, readiness, and requests
```

In CI/CD, separate jobs can be organized:

| Job | Runtime | Purpose |
|---|---|---|
| Compile and unit test | Project's standard JDK | Verify source code, business logic, and basic Java compatibility |
| CRaC integration test | CRaC-enabled JDK build | Verify resource callbacks and checkpoint/restore capability |
| Restore test | Same build and compatible environment | Verify the checkpoint can be restored and the application is ready |
| Deployment validation | Actual production runtime | Verify image, kernel, permissions, and external resources |

Not every project needs to run on two types of JDK. If production only uses a CRaC JDK, you can choose that exact build as the primary runtime for builds and integration tests to reduce environmental differences. If the application needs to be compatible with multiple runtimes, corresponding tests must be maintained.

## 10. Common misconceptions

### 10.1. Thinking that every JDK with the same Java version has CRaC

The Java version indicates the platform line and corresponding Java features. It does not by itself prove that the vendor has integrated CRaC into the build. You must check the exact artifact and release documentation.

### 10.2. Thinking that adding the CRaC dependency is enough

The dependency provides the API for source code to reference `Resource`, `Context`, or `Core`. The ability to create and restore checkpoints needs to be supported at runtime. A standard JDK does not gain checkpoint/restore features merely by adding a dependency.

### 10.3. Thinking that a CRaC JDK can only run special applications

A CRaC-enabled JDK is still a Java runtime environment. Standard Java applications can still run if they are compatible with the JDK. CRaC adds an operational capability; an application only benefits when it is prepared for the checkpoint/restore lifecycle.

### 10.4. Thinking that you can create a checkpoint on one JDK and restore it with any JDK

A checkpoint contains the state of a specific process, including runtime state and system resources. It is not like a JAR file or standalone bytecode. Restoring requires a build and environment that meet the vendor's compatibility requirements.

### 10.5. Thinking that registering a `Resource` means CRaC is already supported

Registering a resource only declares how the application prepares and recovers resources. You must perform an actual checkpoint and restore on a supported JDK, then verify that the callbacks are invoked and the resources work properly.

### 10.6. Thinking that a CRaC JDK always makes applications run faster

CRaC helps reuse prepared state upon restore. It does not guarantee every request is faster in every situation. If a checkpoint is created before warm-up, or if restore takes a long time to recreate connections and load data, the overall benefit may be lower than expected. You need to benchmark under the same conditions as a normal startup.

## 11. Criteria for selecting a JDK for a project

When choosing a JDK, start from the application's deployment requirements.

If the application only needs to run Java in the standard way, a supported JDK compatible with the framework can fully meet the need. There is no need to choose a CRaC build just because it has extra features.

If the goal is to reduce the time to create new instances via checkpoint/restore, choose a CRaC-enabled JDK build supported by the vendor for the deployment environment. Then verify the API, operating system, kernel, container runtime, and related libraries.

If the application needs to run in multiple environments—for example, development machines using a standard JDK while production uses a CRaC JDK—clearly define how dependencies and run modes are managed. CI needs at least one integration test running on the actual CRaC runtime; unit tests on a standard JDK cannot replace this test.

Some criteria should be documented in the project documentation:

- JDK vendor and distribution name.
- Java version, build number, and specific patch.
- Where to obtain the binary and how to pin the version in build/deploy.
- CRaC API version and frameworks with CRaC integration.
- Supported operating system, kernel, CPU architecture, and container runtime.
- Required checkpoint/restore tools or services.
- Process for creating, storing, distributing, restoring, and deleting checkpoints.
- Test results for callbacks, readiness, latency, and error rates after restore.

## 12. Verification checklist before using CRaC

- [ ] Have you identified the exact JDK binary used to build and run the application?
- [ ] Have you recorded the vendor, version, build number, and architecture?
- [ ] Does the vendor documentation confirm that exact build supports CRaC?
- [ ] Is the `org.crac` version or API packaging compatible?
- [ ] Have you confirmed the required operating system, kernel, CRIU, or checkpoint/restore mechanism?
- [ ] Have the container runtime and required permissions been configured?
- [ ] Are resources registered and equipped with appropriate logic for both callbacks?
- [ ] Has a test successfully created a checkpoint and restored it on the target runtime?
- [ ] Have connections, background workers, secrets, and readiness been verified after restore?
- [ ] Are checkpoints stored and permissioned as sensitive data?
- [ ] Does CI/CD test with the exact CRaC JDK build intended for deployment?

## Conclusion

Both a standard JDK and a CRaC-enabled JDK build can run Java applications. The core difference is the capability of the JVM: a standard JDK does not have CRaC integration if the build does not provide this feature, whereas a CRaC JDK can coordinate process checkpoint and restore in a supported environment.

The CRaC API and the CRaC runtime are two related parts that do not substitute for each other. The API helps the application register resources and define how to prepare or recover them. The CRaC-enabled JDK build provides JVM-level integration to execute the checkpoint/restore lifecycle. Therefore, verify the exact JDK build, API dependency, and operating system environment, and run an actual restore test before putting CRaC into deployment.
