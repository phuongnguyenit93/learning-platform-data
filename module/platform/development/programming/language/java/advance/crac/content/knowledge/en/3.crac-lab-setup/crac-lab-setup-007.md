# Distinguishing criuengine, simengine, and Provider-Specific Mechanisms

In CRaC, the phrase checkpoint/restore can appear at several different layers. There is the API layer for the application to prepare resources, the engine that performs saving and restoring the process, and the cloud platform that provides its own snapshot mechanism and deployment lifecycle. These three layers are related to each other but are not synonymous.

criuengine is typically the engine that performs real checkpoint/restore using CRIU on Linux. simengine typically simulates the CRaC callback cycle so developers can test how the application closes and reopens resources. A provider-specific mechanism can snapshot an execution environment at the container, virtual machine, or serverless platform level, controlled by the provider. Some platforms support callbacks according to the CRaC API, but that does not mean they use CRIU or produce a checkpoint image that can be carried over to another CRaC environment.

To choose the right lab environment, you need to determine what you are testing: resource lifecycle logic, real process checkpoint/restore capability, or integration with a specific deployment platform.

## 1. Distinguishing CRaC, engine, and platform mechanisms

### What is CRaC?

CRaC (Coordinated Restore at Checkpoint) is a coordination model for an application to prepare before a checkpoint and restore resources after a restore. The CRaC API allows the application to register resources and implement lifecycle callbacks, most commonly:

- beforeCheckpoint: stop or prepare resources before the process is captured.
- afterRestore: recreate or verify resources after the process is restored.

This API describes the part the application needs to coordinate. It does not by itself decide whether the process image is created using CRIU, a virtual machine snapshot, or another technology.

### What is an Engine?

An engine is the runtime/JDK-side component that executes checkpoint and restore requests. The engine connects CRaC's coordination part to a specific execution mechanism. Engine names, configuration methods, capabilities, and support levels depend on the JDK build or vendor.

In the context of this lesson, the two names to distinguish are:

- criuengine: the engine that uses CRIU to perform real process checkpoint/restore on a compatible Linux environment.
- simengine: the engine that simulates the CRaC cycle, typically used to test callbacks without creating a process image that can be restored like CRIU.

Exact names and configuration values may differ between JDK distributions. You should not assume that every JDK supports both engines or uses the same startup parameters.

### What is a provider-specific mechanism?

A cloud provider or runtime platform may implement snapshots in its own way. The platform may capture the entire execution environment, manage when snapshots are created, store images, clone environments on demand, and invoke hooks at times defined by the platform.

The CRaC API can serve as the interface for the application to prepare resources in such a platform. However, the underlying snapshot technology, image format, environment limits, callback timing, and deployment workflow are still determined by the platform.

## 2. Position of each component in the checkpoint/restore flow

The layers can be visualized according to the following flow:

~~~mermaid
flowchart TD
    A[Java Application] --> B[CRaC Resource and callbacks]
    B --> C[Runtime / CRaC JDK]
    C --> D{Execution mechanism}
    D --> E[criuengine]
    D --> F[simengine]
    D --> G[Provider snapshot mechanism]
    E --> H[CRIU on Linux]
    F --> I[Callback lifecycle simulation]
    G --> J[Platform-managed snapshot]
~~~

The application uses callbacks to bring resources to a safe state. The Runtime/JDK coordinates the callbacks. The engine or platform performs the snapshot/restore part. Each layer has its own responsibility:

| Component | Main responsibility | Does not automatically guarantee |
|---|---|---|
| CRaC API and Resource | Tells the application when to prepare and restore resources | Does not automatically save databases, message brokers, or business data |
| criuengine | Coordinates process checkpoint/restore via CRIU | Does not make every kernel, socket, file descriptor, or native resource compatible |
| simengine | Simulates the cycle to test callbacks and lifecycle logic | Does not prove a real process image can be created and restored successfully |
| Provider-specific mechanism | Captures, stores, clones, and restores the environment per the platform's contract | Is not automatically compatible with CRIU or able to export/import images between providers |

## 3. criuengine: real checkpoint/restore using CRIU

CRIU stands for Checkpoint/Restore In Userspace. It is a tool on Linux capable of saving the state of a process and restoring the process from the saved state, within the scope supported by the kernel, CRIU, and environment configuration.

When the JDK uses criuengine, the checkpoint request from the runtime is forwarded to the CRIU mechanism. Before capturing, CRaC callbacks give the application an opportunity to close or prepare resources. After the process is restored, resource restoration callbacks are invoked according to the CRaC lifecycle.

### Characteristics of criuengine

- Performs real process checkpoint/restore, including memory state and process states that CRIU supports in the running environment.
- Depends on Linux, kernel, CRIU version, CPU architecture, system permissions, and container or namespace configuration.
- Requires the CRIU tool and compatible system conditions in both the checkpoint creation and restore environments.
- Can test real-world issues related to processes, operating system resources, and restorability.
- The checkpoint image is tied to many details of the source environment. You should not assume an image can be freely moved across different machines, kernels, architectures, JDK versions, or container configurations.

### Conditions to check

Before practicing with criuengine, confirm:

1. The JDK in use is built with CRaC support and has the corresponding CRIU engine.
2. The operating system is Linux and the kernel version meets the requirements of the CRIU version.
3. CRIU is installed and can run in the target environment.
4. The user or container has the necessary permissions for CRIU to manipulate the process.
5. Limitations regarding cgroups, namespaces, filesystems, networking, and security of the container environment have been addressed.
6. Native libraries, sockets, file descriptors, and resources used by the application have appropriate handling.
7. The restore environment meets the compatibility conditions of the created image.

You can start checking at the operating system level with these commands:

~~~bash
uname -a
criu --version
criu check
java -version
~~~

The commands above only provide initial information. criu check verifies certain CRIU conditions on the host; a successful result does not prove a specific Java application will checkpoint/restore. You still need to test with the exact JDK, application, execution permissions, and deployment configuration.

### What criuengine does not solve for the application

CRIU handles process state within its supported scope. It does not turn a checkpoint into a distributed transaction. A database can still continue receiving transactions; a broker can still emit messages; tokens can still expire; leases can still be granted to another process. The application must use callbacks and business logic to close, verify, or recreate these resources.

For example, a JDBC connection still referenced on the heap does not mean the database still keeps the corresponding session. Before checkpoint, the application should close the connection pool according to the library's instructions; after restore, create a new pool and verify connectivity before accepting traffic.

## 4. simengine: simulating the lifecycle for development and testing

simengine is typically provided for developers to test CRaC integration without having to set up the full CRIU checkpoint/restore environment. The engine simulates the pre-checkpoint and post-restore callback sequence within the same process or in a simulated manner provided by the JDK.

Its goal is to help detect issues in resource management code:

- Does the application register resources properly?
- Does beforeCheckpoint close or flush the necessary resources?
- Does afterRestore recreate clients, pools, or subscriptions?
- Can callbacks handle cases where resources have not been initialized or are already closed?
- Can the application return to a ready state after the callback cycle?

### Testing scope of simengine

simengine is useful during initial development because it can quickly test callback logic without creating a real process image. It also helps bring resource lifecycle testing into the daily development workflow.

However, a simulated cycle does not fully reproduce the process being stopped, memory being saved, operating system state being restored, and the process continuing to run from a checkpoint image. Depending on the JDK implementation, the simulation may invoke callbacks in the same process without an actual pause period.

Therefore, simengine does not prove that:

- CRIU can capture and restore the process on the current kernel.
- All sockets, file descriptors, threads, file locks, or native resources can be restored.
- Containers, namespaces, volumes, and system permissions meet checkpoint requirements.
- External state does not change while the process is stopped.
- A checkpoint image can be transferred to another host or environment.
- The application behaves correctly when the process is actually replaced or when the platform creates multiple restore instances.

### Using simengine for the right purpose

Use it as an early check for application logic:

1. Register the CRaC resources that the application uses.
2. Run the application with the simulation engine according to the JDK distribution's instructions.
3. Trigger the simulated checkpoint/restore cycle.
4. Observe the logs of beforeCheckpoint and afterRestore.
5. Verify that connection pools, clients, schedulers, and consumers have transitioned to the desired state.
6. Send a business request after the simulation to verify the application still works.

If a callback fails or a resource is not recreated, fix the logic at this step before moving on to real checkpoint testing.

## 5. Provider-specific checkpoint/restore mechanisms

Some cloud platforms provide the ability to snapshot the execution environment to reduce startup time. Instead of requiring users to operate CRIU themselves, the platform manages initialization, state capture, image storage, and creating new environments from that image.

These mechanisms can snapshot at different layers:

- **Process level:** saves the state of a process or process group according to the runtime's capabilities.
- **Container level:** saves the state of the container environment along with the resources supported by the platform.
- **Virtual machine level:** saves the state of a virtual machine or virtualized execution environment.
- **Serverless level:** the platform creates a snapshot of the execution environment after the initialization phase and then restores copies when needed to handle invocations.

Names, scope, and behavior depend on the specific product. Not all of these mechanisms should be called a CRIU engine.

### Example: AWS Lambda SnapStart

AWS Lambda SnapStart is an example of a provider-managed snapshot mechanism. For a Lambda version configured with SnapStart, the platform takes a snapshot of the execution environment after the initialization phase and uses that snapshot to create restored environments when handling invocations.

For Java, the application can use CRaC-compatible hooks, such as resources implementing beforeCheckpoint and afterRestore, to prepare resources before the snapshot and refresh resources after the environment is restored. The platform manages creating and restoring the snapshot; the application does not need to operate CRIU itself for the SnapStart workflow.

This does not mean SnapStart uses criuengine. The underlying snapshot mechanism is managed by AWS and follows Lambda's limits, lifecycle, version configuration, and deployment rules. That snapshot image is not a CRIU image that a user can freely take to another Linux machine to restore.

This example also shows why the callback API needs to be separated from the engine. The application can reuse the idea of managing resources via CRaC hooks, while the platform executes snapshots using its own technology.

### Points to read in provider documentation

Before using a managed snapshot mechanism, specifically investigate:

- When is the snapshot created: at build time, at version publish time, after initialization, or on demand?
- Which hooks are supported? Does the platform accept the org.crac API or require a separate API?
- When are beforeCheckpoint and afterRestore called, in which process, and with what guarantees?
- Which resources are restricted or must be recreated after restore?
- Can the snapshot be used to create multiple concurrent instances?
- What information is preserved across restores and what information must be re-fetched from external services?
- Are there limits on deployment regions, CPU architecture, runtime versions, image size, or image retention time?
- How do you deploy a new version, roll back, delete snapshots, and observe restore errors?

In particular, determine whether the platform invokes hooks once when creating the snapshot or invokes them again for each restore instance. Do not infer the callback lifecycle solely from method names; follow the product's contract.

## 6. Comparison table of the three options

| Criterion | criuengine | simengine | Provider-specific mechanism |
|---|---|---|---|
| Goal | Real process checkpoint/restore | Simulate the CRaC cycle for development | Optimize initialization and restoration on a specific platform |
| Execution method | Uses CRIU on compatible Linux | Simulates callbacks as implemented by the JDK | Snapshot managed by the provider's runtime or infrastructure |
| Real process image | Yes, within CRIU's supported scope | Typically no | Has snapshots in the platform's own format and scope |
| CRIU requirement | Yes | Not necessarily | Not necessarily; depends on the platform |
| OS dependency | Very clear, mainly Linux and kernel/CRIU conditions | Usually less dependent for testing callbacks | Follows the provider's runtime, service, and deployment region |
| Application callback testing | Yes | Yes, this is the main goal | Yes if the platform supports corresponding hooks |
| OS resource restore testing | Yes in a real environment, but only within supported scope | Incomplete | According to the snapshot scope and platform contract |
| Image portability | Limited by environment and technical compatibility | No real image to move | Usually tied to the provider's service, version, and environment |
| Where suitable | Integration testing and self-managed CRaC deployment on Linux | Local development, early callback testing | Deploying on cloud services that support snapshots |

None of the options replaces the responsibility of persisting business data and coordinating with external systems. The main differences lie in where the snapshot is performed, the development team's level of control, and the scope of supported environments.

## 7. Engine configuration and verifying the exact JDK build

You should not copy an engine selection parameter from one JDK's guide to another JDK without checking. CRaC distributions can differ in:

- Packaged engine names.
- Valid values for the engine selection parameter.
- How to enable checkpoint/restore and how to invoke the checkpoint operation.
- Path to CRIU and command-line options.
- Supported CRIU versions.
- How the CRaC API library and required modules are packaged.
- Whether simulation features are available in the build.

The safe workflow is to identify the exact vendor, JDK version, and corresponding documentation, then use the exact engine parameter published in that documentation. The startup command can be represented in general form as:

~~~bash
java <engine-selection-parameter-for-JDK> -jar application.jar
~~~

The `<engine-selection-parameter-for-JDK>` part is where you substitute the actual syntax of the JDK being used. This is not a literal Java parameter that can be used verbatim.

Before running, record versions so the environment can be reproduced:

~~~bash
java -version
criu --version
uname -a
~~~

When comparing two environments, record the JDK vendor, build version, CPU architecture, kernel, CRIU version, and container configuration. Simply noting "used CRaC" is not enough to explain why a checkpoint image works on one machine but fails on another.

## 8. Practice workflow from simulation to real environment

A reasonable practice roadmap can be divided into three levels.

### Level 1: testing callbacks with simengine

At this level, focus on application logic:

1. Create a resource that manages a connection to an external service.
2. Register the resource with the CRaC global context.
3. In beforeCheckpoint, stop accepting new work and close resources that need to be recreated.
4. In afterRestore, open a new connection and verify state.
5. Run the simulation cycle and check logs, resource state, and the ability to handle subsequent requests.

The goal is to find bugs in callbacks quickly and reproducibly.

### Level 2: testing checkpoint/restore with criuengine

Once callbacks are working, move to a Linux environment with CRIU:

1. Prepare the exact JDK, CRIU, kernel, permissions, and container configuration.
2. Run the application with the CRIU engine according to the JDK's instructions.
3. Create a checkpoint using the mechanism provided by the JDK build.
4. Perform restore following the exact supported procedure and environment.
5. Verify the application has restored process state and recreated external connections.
6. Test scenarios such as database restart, expired tokens, or files changed during the period the process was stopped.

The goal is to verify that the runtime, CRIU, operating system, and application all work together.

### Level 3: deploying on the provider's platform

If the destination is a managed snapshot service, move on to testing on that exact service:

1. Read the platform's snapshot contract and hook lifecycle.
2. Confirm the supported JDK/runtime and callback API.
3. Package the application according to the provider's deployment process.
4. Create a version or configure snapshot according to the service's instructions.
5. Trigger the restored environment and check hooks, readiness, connections, and business data.
6. Test multiple concurrent restored instances, rollbacks, and version updates.

The goal is to verify behavior in the exact intended production environment. Results from simengine or criuengine do not replace integration testing with the managed service.

~~~mermaid
flowchart TD
    A[Write and register CRaC Resource] --> B[Test callbacks with simengine]
    B --> C{Do callbacks work properly?}
    C -- Not yet --> D[Fix resource lifecycle logic]
    D --> B
    C -- Yes --> E[Check CRIU and Linux]
    E --> F[Real checkpoint/restore with criuengine]
    F --> G{Does real environment work properly?}
    G -- Not yet --> H[Investigate JDK, CRIU, kernel, and resources]
    H --> E
    G -- Yes --> I[If needed, integrate managed platform]
    I --> J[Check provider hooks and contract]
~~~

Not every project needs all three levels. If the application only runs on a managed platform, level 1 helps test callback logic and level 3 tests the platform's actual contract. If the team self-manages CRIU on Linux, level 2 is the main verification step.

## 9. Shared resource example for CRaC-supported environments

The Resource API allows an application to describe how to manage the lifecycle of a resource. The example below illustrates a client that needs to be closed before checkpoint and reconnected after restore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExternalClientResource implements Resource {
    private volatile ExternalClient client;

    public ExternalClientResource() {
        Core.getGlobalContext().register(this);
        client = connect();
    }

    public ExternalClient client() {
        ExternalClient current = client;
        if (current == null) {
            throw new IllegalStateException("Client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        ExternalClient current = client;
        client = null;
        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        client = connect();
    }

    private ExternalClient connect() {
        // Create a new client according to the current configuration and credentials.
        return ExternalClient.connect();
    }
}
~~~

ExternalClient in the example is an illustrative application class, not a built-in JDK class. In a real project, replace it with the specific client and apply the close/open procedure supported by the library.

The code snippet shows that the application manages resource lifecycle through the CRaC API. It does not choose the engine and does not decide how the snapshot is created. The same callback idea can be tested with simengine, run with criuengine on a CRIU-supported JDK, or integrated with a managed platform if the platform supports the corresponding API.

In practice, a quiescing step should be added to ensure no request is using the client when beforeCheckpoint closes it. afterRestore also needs to handle cases where the service is not yet ready, perform bounded retries, and report readiness only after the required connections are working.

## 10. Common misconceptions

| Misconception | Reality |
|---|---|
| CRaC is CRIU | CRaC provides the coordination model and API; CRIU is a Linux tool that an engine can use for checkpoint/restore |
| criuengine and simengine only differ in speed | They differ in purpose and execution level: one performs a real checkpoint, the other simulates the lifecycle |
| Passing tests with simengine means it can be deployed with CRIU | Simulation does not fully test the kernel, permissions, container, CRIU, and OS resource restoration capability |
| Having criuengine means any Linux can run it | Actual capability depends on the kernel, CRIU, architecture, permissions, and environment configuration |
| A platform having CRaC hooks means it uses CRIU | A platform may use its own snapshot technology and only reuse the callback API |
| A provider's snapshot can be restored with CRIU | Images are usually tied to the provider's format and service |
| The afterRestore callback makes all external services work automatically | The application still has to recreate connections, refresh tokens, verify leases, and check readiness |
| One checkpoint creates only one instance | Some platforms can use a snapshot to create multiple instances; identity and distributed state must be handled |
| The simulation engine can replace production testing | Each environment has its own contract, limits, and restore behavior that must be tested directly |

## 11. Choosing an environment by goal

Start from your testing goal:

- If you need to quickly test beforeCheckpoint, afterRestore, pool closing/opening, and readiness state, start with simengine.
- If you need to prove a Java process can be genuinely checkpointed and restored on team-managed Linux, use criuengine with the exact JDK, kernel, CRIU, and deployment configuration.
- If the application runs on a cloud service with its own snapshot mechanism, follow that service's documentation and test the hooks the service supports. Do not assume the snapshot image is compatible with CRIU.
- If you want to move from a self-managed environment to managed snapshots, keep the business logic and resource management principles at the application layer, then adjust the integration part according to the platform's contract.

Before concluding that the environment is ready, check all three groups:

1. **Application:** resources are registered properly, callbacks are safe, operations are repeatable, and caches and business state are verified.
2. **Runtime and engine:** exact JDK, exact engine, exact versions, and exact checkpoint/restore procedure.
3. **Platform:** kernel, container, permissions, storage, network, external services, and provider snapshot rules all meet requirements.

Clearly distinguishing criuengine, simengine, and provider-specific mechanisms helps choose the right tool for each step. simengine shortens the callback development loop; criuengine verifies real checkpoint/restore using CRIU on Linux; managed mechanisms leverage platform-operated snapshots under their own contract. Regardless of which option is chosen, the application must still proactively manage resources, persistent data, and external systems throughout the checkpoint/restore lifecycle.
