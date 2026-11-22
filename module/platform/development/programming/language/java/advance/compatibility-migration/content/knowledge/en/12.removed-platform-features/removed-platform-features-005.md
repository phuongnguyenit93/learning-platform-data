# RMI Activation and its impact on systems using the legacy activation mechanism

In some long-lived Java systems, remote objects are not created when the application starts, but only initialized when a client actually calls them. This mechanism was previously supported by Java RMI via **RMI Activation** and the **`rmid`** process. When upgrading the JDK, especially from Java 8 or Java 11 to Java 17 onward, systems relying on Activation can fail even though most regular Java RMI code continues to be supported.

The most important distinction: **RMI Activation has been removed, yet Java RMI in general has not been removed just because of this change.** Applications using `Remote`, `RemoteException`, `UnicastRemoteObject`, and the RMI registry can continue operating if source code, dependencies, configuration, and environment are compatible. Conversely, applications using `java.rmi.activation.*`, the `rmid` daemon, or the on-demand object activation model must have their service lifecycle redesigned.

This lesson explains the previous Activation architecture, version milestones across JDKs, impact on builds and runtime, replacement options, an RMI example without Activation, and a safe migration process in **Java Advance Compatibility Migration**.

## 1. Reviewing regular Java RMI

Java Remote Method Invocation (RMI) allows a Java program to invoke methods on a remote object through a remote interface. A typical RMI application has:

- **Remote interface:** declares methods that can be called remotely; usually the interface extends `java.rmi.Remote` and remote methods declare `RemoteException`.
- **Remote implementation:** the object implementing the business logic.
- **Exported remote object:** the object exported so the RMI runtime can receive remote calls; `UnicastRemoteObject` can be used.
- **RMI registry:** the place where names and remote references are registered for clients to look up via `Registry.lookup` or corresponding APIs.
- **Client:** obtains the remote reference and calls methods, handling network errors and business errors.

Simple flow:

~~~text
Server process                            Client process
+-------------------------+               +--------------------------+
| Create service object   |               | Locate RMI registry      |
| Export remote object    |               | Lookup service name      |
| Bind to RMI registry    |<-- lookup ----| Receive remote reference |
| Wait for remote calls   |<-- invoke ----| Call remote method       |
| Execute business logic  |---- reply --->| Handle result/error      |
+-------------------------+               +--------------------------+
~~~

In this model, **the server process must be running and the remote object must be exported** before a client can call it. The RMI registry does not start the server automatically if the process has stopped. It is a service for registering and looking up remote references, not a process supervisor.

RMI Activation previously added a separate mechanism to instantiate or reactivate objects on demand, instead of keeping every service always running ready.

## 2. What problem was RMI Activation designed to solve?

In a large system, some remote objects are rarely called. Keeping all server processes running continuously can consume memory, threads, connections, or administrative overhead. RMI Activation previously provided a way for a remote object with an **activation descriptor** to be registered in an activation system, and then activated when a remote call requested an object that was not yet active.

Conceptual model:

~~~text
                 Client
                   |
                   | Call remote object via activatable reference
                   v
          +-------------------+
          | Activation system |
          |       rmid        |
          +-------------------+
                   |
                   | Look up registration info
                   | Select/activate activation group
                   v
          +-------------------+
          | JVM/group process |
          |  Activated object |
          +-------------------+
                   |
                   | Object ready / remote reference
                   v
          +-------------------+
          | Remote invocation |
          +-------------------+
~~~

In principle, Activation allowed registering an object descriptor in advance and having the activation daemon help bring the implementation into a ready state when requested. In old systems, registration information could be recorded in the activation daemon's log/database, serving to restore registration state across daemon runs.

Key points to understand:

1. This is RMI's **remote object lifecycle mechanism**, not just another name for the RMI registry.
2. It could involve starting an activation group JVM/process, yet is not equivalent to a modern process supervisor.
3. Its operation depended on the `rmid` daemon, activation APIs, and appropriate runtime configuration.
4. RMI Activation did not automatically ensure business data was persisted durably; applications still had to manage state separately.
5. The fact that Activation previously supported on-demand startup **does not mean** you can remove the daemon and keep remote references unchanged when upgrading the JDK.

## 3. Legacy components to identify

Applications that used Activation typically have the following signs:

| Component or symbol | Historical role | Action needed when upgrading to a new JDK |
|---|---|---|
| `java.rmi.activation.Activatable` | Supports exported activatable remote objects | Move to another lifecycle, typically regular RMI or another protocol |
| `ActivationID` | Identifies an object in the activation system | Replace with an appropriate identity/lookup model |
| `ActivationDesc` | Describes how to activate an object | Move startup configuration to service deployment/config |
| `ActivationGroup` | Manages a group of activated objects | Replace with process/container/service lifecycle |
| `ActivationGroupDesc` | Describes activation group attributes | Migrate startup options, properties, and policies |
| `ActivationSystem` | Interface managing activation registrations | Cannot simply replace each method using Registry |
| `Activator` / `ActivationMonitor` | Coordinates activation and monitors status | Redesign readiness and observability mechanisms |
| `rmid` | External activation daemon outside the application | No longer provided starting in JDK 17 |
| `rmid` startup scripts | Usually configure ports, logs, policy, environment | Remove or replace with another supervisor |
| RMI registry/`rmiregistry` | Registers/looks up remote references | A separate component, not automatically removed with Activation |

Some systems do not import `java.rmi.activation` directly in business modules yet still depend on it indirectly through libraries, utility JARs, or startup scripts. Therefore, source code, bytecode, packaging, and operational procedures must all be inspected.

### 3.1. Activation system differs from Registry

The RMI registry answers the question **“which remote reference does this service name map to?”**. The activation system answers the related question **“how will this registered object be activated when needed?”**.

Merely replacing `ActivationSystem.registerObject(...)` with `Registry.rebind(...)` does not recreate activation behavior. For clients to remain able to call it, the service must actively create/export the object and register the remote reference in the registry; at the same time, another mechanism must monitor the process and restart it when needed.

### 3.2. Activation group differs from modern process managers

RMI's activation group is tied to the specification and process/group organization of the Activation system. When migrating to systemd, Windows Service, container orchestrators, or schedulers, there is no exact equivalent “activation group” concept. Each requirement must be migrated individually: startup arguments, credentials, Java options, working directory, resources, restart policy, and isolation boundaries.

## 4. Version milestones: deprecate and remove are not the same

RMI Activation went through two important steps in the modern JDK roadmap:

| Java release | RMI Activation status | Migration significance |
|---|---|---|
| Java 8 | Has Activation API and `rmid` tool | Legacy applications may rely on the old activation mechanism |
| Java 9–14 | Has JPMS and runtime changes; Activation remains a legacy component | Should be reviewed before moving to newer Java |
| **Java 15** | **JEP 385: Deprecate RMI Activation for Removal** | API and tool marked for planned removal; prepare replacements |
| Java 16 | Transition phase with deprecation for removal | Should not build new development depending on Activation |
| **Java 17** | **JEP 407: Remove RMI Activation** | Activation API and `rmid` daemon are removed from the JDK |
| Java 21 and newer JDKs | Should not expect Java RMI Activation to return | Must operate with a design that does not depend on the removed mechanism |

Distinguish three concepts:

- **Deprecated:** an API discouraged from use yet may still exist.
- **Deprecated for removal:** an API marked with a plan for future removal, requiring priority migration.
- **Removed:** an API/tool is no longer provided in the corresponding JDK; dependent code may fail to compile or run.

A system that still starts on Java 11 does not prove Java 17 compatibility. If it depends on Activation, this is a **platform capability** gap rather than merely a compiler warning.

## 5. Regular Java RMI remains a separate mechanism

What was removed is **RMI Activation**, not the entire `java.rmi` module. Basic RMI capabilities still remain relevant on modern Java:

- `java.rmi.Remote` and `java.rmi.RemoteException`.
- `java.rmi.server.UnicastRemoteObject` to export remote objects.
- `java.rmi.registry.Registry` and `LocateRegistry` to register/look up.
- Remote invocation and RMI transport when configuration, dependencies, and networking are appropriate.
- Certain RMI mechanisms used in legacy systems or management tools, with their own security constraints.

For example, an application **not using Activation** can continue deploying an RMI server normally on JDK 17. However, this does not confirm every legacy RMI form will work: codebase downloading, dynamic class loading, Security Manager, serialization, JRMP connections, and old libraries need independent investigation.

### 5.1. Visual comparison

| Aspect | Regular RMI | RMI Activation |
|---|---|---|
| Server object lifecycle | Application creates/exports objects itself | Can activate objects upon registration and calls |
| Characteristic components | `UnicastRemoteObject`, `Registry` | `Activatable`, `ActivationDesc`, `rmid` |
| Service start | Performed by launcher/supervisor/application | Activation system can participate in starting processes |
| Lookup | Registry or another mechanism to obtain remote refs | Can use registry alongside activation references |
| Java 17 dependency | Basic RMI APIs still exist | Activation is removed |
| Migration | Check compatibility | Requires lifecycle architecture changes |

Do not use the phrase “RMI is no longer supported” to describe an issue of an application that only fails in `java.rmi.activation`. Precise phrasing helps the team pick a solution with the right scope and avoid unnecessary protocol rewrites.

## 6. Compile errors when source still uses java.rmi.activation

When moving a project to a JDK 17+ compiler with source still importing the Activation API:

~~~java
import java.rmi.activation.Activatable;
import java.rmi.activation.ActivationID;
~~~

The compiler may report that the package or symbol does not exist. Example symptom:

~~~text
error: package java.rmi.activation does not exist
error: cannot find symbol
    symbol: class ActivationID
~~~

This is an error of an **API removed from the JDK**, not simply because the package is concealed by JPMS. Options like `--add-opens` or `--add-exports` do not recreate missing classes.

If a new module targets Java 17 yet the code still relies on Activation, tweaking flags is not a solution. You need to change how lifecycle is provided or replace the API library.

### 6.1. Libraries compiled on old JDKs can fail at runtime

A JAR pre-compiled with Java 8 may contain references to classes in `java.rmi.activation`. It has an older class-file version that a Java 17 JVM can read, yet when needing to load or link Activation classes, the runtime may encounter:

~~~text
java.lang.NoClassDefFoundError: java/rmi/activation/Activatable
~~~

or, if the code looks up classes via reflection:

~~~text
java.lang.ClassNotFoundException: java.rmi.activation.Activatable
~~~

The actual error type depends on how the class is referenced and when the JVM resolves, initializes, or loads it. Do not infer from “class file compatible” that “every dependency already exists in the new JDK”.

### 6.2. Errors only appearing when triggering a business branch

Some services may start successfully yet only register or activate remote objects after an administrative operation. Therefore, a “process started” smoke test is insufficient. You must verify registration, lookup, invocation, process restart, and post-failure recovery paths.

## 7. Operational error: rmid no longer exists

Legacy systems may have a startup script:

~~~bash
# Historical example; do not use to start on JDK 17+
rmid -port 1098
~~~

`rmid` is RMI's activation daemon, not `rmiregistry`. On JDK 17+, the `rmid` tool is no longer provided, so scripts may report command not found or fail to start the daemon.

A chain of incidents may occur:

1. Deploy the new JDK yet the script still tries to run `rmid`.
2. The daemon does not exist, so activation registrations are not served.
3. Legacy remote references related to Activation are no longer activated as designed.
4. Client lookup may succeed in some states yet invocation fails; or lookup also fails if bindings are not recreated.
5. Monitoring that looks only at the main process may miss failures in the activation mechanism.

Do not replace the name `rmid` with `rmiregistry` in scripts and declare migration complete. Registry does not store and execute activation descriptors.

### 7.1. Legacy registration data

An Activation system may maintain registration data and metadata in the daemon's storage area. When removing Activation, you need to know what that data means:

- Which Activation IDs and references are clients currently holding?
- Where is the logical mapping between service names and implementations stored?
- Which descriptors contain startup properties and paths to implementation JARs?
- Do activation group configurations contain credentials or JVM arguments?
- Is any business state mistakenly assumed to be durably persisted by Activation itself?

You should not assume the “`rmid` database” can be migrated directly into the RMI registry or service manager. Extract the required configuration information appropriately before shutting down the old environment and rebuild registration/lifecycle on the new platform.

## 8. Inventorying Activation dependencies in source, artifacts, and scripts

Before editing code, look for direct and indirect signs.

### 8.1. Searching in source and configuration

With a text search tool such as ripgrep:

~~~bash
rg -n 'java\.rmi\.activation|Activatable|ActivationID|ActivationDesc|ActivationGroup|ActivationSystem|\brmid\b' .
~~~

Results should be classified:

- Direct Java imports.
- Fully qualified class names configured as strings.
- Code generation templates.
- Build scripts, deployment scripts, and startup services.
- Operational documentation and old commands.
- Test fixtures or examples meant only for illustration.

Not every match found is actually executed. Verify whether the related module still runs in production.

### 8.2. Checking dependencies and bytecode

If the application does not import Activation yet third-party JARs use it, analyze:

- Actual compile classpath and runtime classpath.
- List of packaged JARs or those provided by the application server.
- Dependency tree and transitive dependency versions.
- Bytecode references in suspected classes.
- Java compatibility release notes of libraries.

`jdeps` can be used with the appropriate dependency environment to analyze missing dependencies:

~~~bash
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Note: `jdeps --jdk-internals` specializes in finding certain JDK internal API dependencies; **it is not a dedicated tool for detecting references to removed RMI Activation**. Combine source search, dependency graph inspection, and test compiling/loading under the target JDK.

For fat JARs containing nested JARs (such as launcher frameworks), it may be necessary to extract or analyze the inner JARs separately. Do not conclude “clean” just because a command on the outer JAR found no dependency.

### 8.3. Checking actual runtime

On each environment, record:

~~~bash
java -version
javac -version
~~~

And check startup configurations, systemd units, Windows Services, container entrypoints, job schedulers, CI pipelines, or deployment scripts for references to `rmid`.

You can inspect which modules the runtime still provides:

~~~bash
java --list-modules
~~~

Module `java.rmi` may still appear, yet that does **not** prove Activation still exists inside it. To determine removed APIs, check the target release and specific classes/packages.

## 9. Classifying how the system actually uses Activation

Not every application containing the name `Activatable` has the same risk. Categorize into cases:

| Case | Signs | Strategy |
|---|---|---|
| Import remains in unbuilt code | Legacy module/tool outside deployment scope | Decide to remove or isolate with evidence |
| Compile-time dependency | Source uses `ActivationID` or `Activatable` | Refactor source and API design |
| Runtime library dependency | Old JAR uses Activation | Upgrade/replace library or replace functionality |
| Actual Activation server | Has `rmid`, registration, activation groups | Redesign service lifecycle |
| Client holds activatable references | Remote references stored or passed across other systems | Check compatibility and re-discovery |
| Historical integration tests | Tests start `rmid` or Activation daemon | Rewrite tests for the new lifecycle |
| Code generation/templates | Generator emits Activation code | Update generator and regenerate |
| Deployment depends on daemon | Scripts/configs prepare `rmid` | Change orchestration and startup system |

An accurate analysis clarifies **Activation's role**: whether it is just an old implementation detail, or a critical business requirement such as on-demand startup, process isolation, or service self-recovery.

## 10. Moving from Activation to regular RMI with external lifecycle

When Java clients still need to communicate over RMI and the server interface remains suitable, the minimal change approach is usually:

1. Keep the remote interface when possible.
2. Replace activatable object creation logic with creating and exporting regular RMI objects.
3. Use the RMI registry to register remote references when the server process starts.
4. Use systemd, Windows Service, container supervisor, or orchestrator to manage processes.
5. Store and recover business state via an explicit database or storage.
6. Update client discovery and retries when the server restarts.
7. Verify registry port, exported object port, firewalls, and advertised hostname.

Post-migration architecture:

~~~text
             Service manager / orchestrator
                        |
               Start / restart server
                        |
                        v
     +-----------------------------------------+
     | Long-running JVM service                |
     |  - Construct implementation             |
     |  - Export UnicastRemoteObject           |
     |  - Bind remote reference in Registry    |
     |  - Handle remote requests               |
     +-----------------------------------------+
                 ^                 ^
                 | lookup          | remote calls
                 |                 |
             RMI registry        Client
                 ^
                 |
       Bind/rebind at startup
~~~

If the registry is created directly inside the server JVM, the registry dies when the JVM dies. If the registry is a separate process, bindings may persist in some cases while the remote object is gone; clients still must handle stale references and the server needs to rebind after restart. Therefore, **a registry does not replace health checks or managed-lifecycle service discovery**.

### 10.1. Semantic differences that must be accepted

Regular RMI with a continuously running server does not automatically recreate **lazy activation** per remote call. If saving resources via on-demand startup is a core requirement, another orchestration solution or communication design is needed. If only “the service runs and restarts automatically” is needed, a process supervisor is usually simpler and easier to observe than the old Activation mechanism.

## 11. Java RMI code example without Activation on a newer JDK

The example below consists of a remote interface, implementation, server, and client. It uses regular RMI APIs, **without importing `java.rmi.activation.*`**.

### 11.1. Remote interface

File `src/example/rmi/GreetingService.java`:

~~~java
package example.rmi;

import java.rmi.Remote;
import java.rmi.RemoteException;

public interface GreetingService extends Remote {

    String greet(String name) throws RemoteException;
}
~~~

Remote methods need to declare `RemoteException` per the RMI contract so clients recognize remote communication errors.

### 11.2. Implementation

File `src/example/rmi/GreetingServiceImpl.java`:

~~~java
package example.rmi;

import java.rmi.RemoteException;

public final class GreetingServiceImpl implements GreetingService {

    @Override
    public String greet(String name) throws RemoteException {
        return "Xin chao, " + name;
    }
}
~~~

The implementation does not need to extend `Activatable`. It is an ordinary Java object exported by the server.

### 11.3. Server

File `src/example/rmi/GreetingServer.java`:

~~~java
package example.rmi;

import java.rmi.Remote;
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;
import java.rmi.server.UnicastRemoteObject;

public final class GreetingServer {

    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingServiceImpl();

        // Export service endpoint on a stable port for deployment/firewall.
        Remote stub = UnicastRemoteObject.exportObject(service, 12099);

        // Demo: registry runs inside this same JVM process.
        Registry registry = LocateRegistry.createRegistry(1099);
        registry.rebind("GreetingService", stub);

        System.out.println("GreetingService ready on port 12099");
    }
}
~~~

In this example:

- Port 1099 is for the RMI registry.
- Port 12099 is for the remote object endpoint.
- The process must be started by an external lifecycle management tool.
- When the server restarts, it creates/exports the object and re-registers the binding.
- Using a fixed port makes firewall configuration easier; production needs to consider TLS, authentication, and network architecture.

This is a minimal educational example, not yet including shutdown hooks, health checks, metrics, retry policies, or security hardening.

### 11.4. Client

File `src/example/rmi/GreetingClient.java`:

~~~java
package example.rmi;

import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public final class GreetingClient {

    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "localhost";

        Registry registry = LocateRegistry.getRegistry(host, 1099);
        GreetingService service =
                (GreetingService) registry.lookup("GreetingService");

        System.out.println(service.greet("Mai"));
    }
}
~~~

The client must have the compatible `GreetingService` interface on its classpath. It does not require server implementation classes to be on the client classpath.

### 11.5. Compiling and running

Example with a Linux/macOS shell from the project directory:

~~~bash
mkdir -p out
javac --release 17 -d out src/example/rmi/*.java

# Terminal 1
java -cp out example.rmi.GreetingServer

# Terminal 2
java -cp out example.rmi.GreetingClient localhost
~~~

When running in a real network environment, check the server address embedded in the remote reference. In some NAT, container, or JVM-selected hostname scenarios, the address is unreachable from clients. It may be necessary to configure `java.rmi.server.hostname` appropriately for the deployment network and ensure both the registry port and exported service port are actually open.

This example proves **regular RMI can still be designed and compiled with JDK 17**. It does not prove old RMI Activation remote references are directly compatible or can be reused unchanged.

## 12. The RMI registry is not responsible for starting services

A common migration design mistake is thinking that when a client calls `Registry.lookup`, the server JVM will be created. With regular RMI:

- `lookup` only looks up an already-registered name.
- `rebind` updates the binding to a remote reference.
- The registry does not instantiate implementation classes or processes by itself.
- When the process exporting the remote object stops, references can become stale.
- When a new process runs, it must export and register again itself.
- If a client holds an old reference, it may need to look up again and retry new requests under a safe policy.

Example client must tolerate:

~~~text
Client lookup ok
     |
     v
Server restart between lookup and invoke
     |
     v
RemoteException / connection failure
     |
     v
Re-discover service and retry if operation is safe
~~~

Retrying operations that update balances, create orders, or execute payments must consider **idempotency**, correlation IDs, and commit state. Do not retry blindly because the client does not always know whether the previous operation was already processed by the server.

If the old Activation system provided an experience of “calling an object regardless of whether the process is running”, migration needs to preserve the **external contract** through service management and explicit error handling, rather than just changing an import.

## 13. When to replace with systemd, container orchestrators, or schedulers?

Removing Activation forces process lifecycle management to move to infrastructure or application logic. The choice depends on needs.

| Need | Mechanisms to consider | Differences compared to Activation |
|---|---|---|
| Continuously running service | systemd, Windows Service, container supervisor | Always starts and keeps the process ready |
| Automatic restart on crash | Supervisor/orchestrator restart policy | Usually recovers the process proactively, without waiting for an invocation |
| Deploying and scaling multiple replicas | Container orchestration, load balancing | Requires service discovery and state design |
| Event-triggered execution | Queue consumer, scheduler, job controller | Trigger is an event/job instead of an RMI activation reference |
| Initializing expensive logic on request | Lazy initialization inside a running process | The process already exists before requests arrive |
| Saving resources when there are no requests | Suitable scale-to-zero or on-demand service platform | Not drop-in compatible with the RMI/JRMP protocol |
| Multiple small services sharing resources | Application server/service host with lifecycle management | Differs from activation groups and remote object identity |

Do not describe systemd socket activation or scale-to-zero as direct drop-in replacements without modifying the system. RMI has its own transport/registry setup and remote references; any connection-triggered startup mechanism must be designed, tested for protocol compatibility, and managed with appropriate timeouts/lookups.

### 13.1. Example of a continuously running service

In a Linux deployment, systemd services can be used to start the JVM. Example file:

~~~ini
[Unit]
Description=Legacy RMI service (without RMI Activation)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=rmi-service
WorkingDirectory=/opt/orders
ExecStart=/usr/bin/java -jar /opt/orders/orders-service.jar
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
~~~

This is an illustrative configuration of **process lifecycle**, not directly applicable to the `GreetingServer` example above because that example uses `-cp` and a main class instead of an executable JAR. Before applying to a real environment, adjust paths, users, permissions, secret handling, logging, memory options, restart behavior, and the artifact launch command.

A process supervisor does not automatically guarantee the remote service has registered successfully in the registry; appropriate readiness checks are needed.

## 14. Handling state, identity, and data persistence

RMI Activation previously allowed **registering activation metadata** and instantiating objects when needed. That does not mean the activation daemon saved the object's business state.

When replacing Activation, separate:

1. **Service identity:** the logical name or service key that clients use to find it.
2. **Remote object/reference identity:** the handle in RMI transport, which can change after restart.
3. **Configuration:** constructor info, port, JVM flags, group description.
4. **Business state:** order data, sessions, jobs, in-progress work.
5. **Runtime state:** caches, threads, sockets, connection pools, in-memory counters.

If legacy code keeps an `ActivationID` as a persistent identifier, do not replace it with a serialized RMI stub of `UnicastRemoteObject` expecting it to stay permanently stable. Using application-level IDs in a database or service registry is a cleaner design direction.

### 14.1. Recovery after restart

A modern service typically needs:

- Reading configuration from files, environment, or a config service.
- Loading persistent state from a data store on startup.
- Recovering pending tasks according to application semantics.
- Initializing dependencies and exporting remote objects.
- Registering the endpoint once ready to serve.
- Removing/rebinding registration on stop/restart if needed.
- Having logging, metrics, health checks, and failure escalation.

If a process is lost while processing a request, transaction and retry rules are needed to avoid losing or duplicating work. RMI Activation previously could not replace business logic ensuring exactly-once processing either.

## 15. Systems using old clients: need a protocol compatibility plan

A server-side migration alone is insufficient if clients hold or store **activatable remote references**.

You may encounter:

- Clients looking up via the registry get a stub tied to Activation.
- Remote references were serialized into a database/file.
- An intermediary system sends remote references to other clients.
- Clients use libraries with generated code involving `ActivationID`.
- Client versions deploy slower than the server, creating a coexistence period.

After removing Activation, it may be necessary to:

1. Switch clients to looking up the new endpoint by service name.
2. Update client libraries to remove `java.rmi.activation` types from APIs.
3. Update places storing serialized references, not treating old data as active references.
4. Replace with logical identifiers and dynamic service lookup.
5. Design versioning for interface/method signatures if changed.
6. Roll out changes in an appropriate order: client readiness, server deployment, migration/rollback window.

A safe approach is avoiding long-term client dependence on implementation classes or serialized remote references. Contracts should be expressed via remote interfaces, service names, exchanged data, and error/retry rules.

## 16. Options for rewriting communication: HTTP, gRPC, messaging

Keeping regular RMI can help reduce migration scope, yet is not always the best target architecture. If the system is overhauling deployment or has multi-language clients, APIs or message-based architectures can be considered.

| Direction | When suitable | Things to consider |
|---|---|---|
| Keep RMI, remove Activation | Many existing Java clients; want minimal changes | RMI networking, registry, serialization, versioning |
| HTTP/REST | Public service API, multiple platforms | HTTP semantics, contracts, authentication, payload format |
| gRPC | Typed RPC contracts, multiple languages, streaming | Protobuf, load balancing, tooling, backward compatibility |
| Messaging/event-driven | Asynchronous processing, durable delivery required | At-least-once, idempotency, consumer lifecycle, ordering |
| Scheduler/job service | Scheduled jobs or stateful requests | Job identity, persistence, retry, monitoring |
| In-process module | No need to distribute across processes | Changes deployment and failure isolation |

No single technology automatically replaces all semantics of RMI Activation. You must rewrite the **usage contract**, **lifecycle**, **error handling**, and **state management**, not just translate client call syntax.

### 16.1. How to decide the scope of change

If the goal is moving to JDK 17 quickly and safely, keeping regular RMI may be the lower-risk option. If legacy RMI Activation comes with many operational, security, or cross-language integration issues, this migration can be used to plan a gradual shift to a new protocol. Separate the two decisions and use evidence to control risk.

## 17. RMI, Security Manager, and related yet independent changes

Legacy RMI systems may use security policies, codebase loading, Java Security Manager, custom socket factories, or dynamic class loading. These features have their own change history apart from the removal of RMI Activation.

Points to inspect:

- JVM flags and policy files serving old security mechanisms.
- Class downloading from codebases and class-loading assumptions.
- Serialized data and object types that can be deserialized over the network.
- SSL/TLS or custom RMI socket factories.
- Firewalls and server addresses/hostnames in remote references.
- Authentication, authorization, and auditing.
- Deserialization filters and restricting untrusted data sources.
- Timeout, reconnect, retry, and exception-handling rules.

**Removing Activation does not automatically solve RMI security.** If the system continues using Java serialization over the network, check trust boundaries and serialization filters suitable for the target JDK/runtime. Restrict access to registry and remote ports on trusted networks, avoiding exposing uncontrolled endpoints.

When doing a major JDK upgrade, also check the Security Manager support status on the target version and how the application's RMI libraries depend on that mechanism. Do not assume historical policies/configurations still have the same effect.

## 18. Post-migration errors and investigation directions

| Symptom | Primary hypothesis | Action |
|---|---|---|
| `package java.rmi.activation does not exist` | Source still uses removed Activation API | Refactor or replace dependency |
| `rmid: command not found` | Script still launches old daemon | Replace lifecycle script/service manager |
| `NoClassDefFoundError: ... Activatable` | Old JAR references missing runtime Activation API | Upgrade/replace JAR, remove Activation |
| `ClassNotFoundException` when loading Activation class via reflection | Old class name in config/plugin | Replace config/implementation |
| `NotBoundException` on lookup | Server has not bound the name yet or uses wrong registry | Initialize and rebind at the right time |
| `ConnectException` / `ConnectIOException` | Server not running, incompatible host/port/firewall | Check network and exported endpoint |
| Error after server restart | Client holds stale remote reference | Look up again and safely retry |
| Stub contains unreachable internal host | Incorrect RMI export hostname/NAT | Configure host and networking |
| Process runs yet client still fails | Registry ready yet object not exported/bound or port blocked | Check end-to-end readiness |
| Job executed twice | Retry without idempotency | Add request ID and transaction semantics |
| Startup works yet data is lost | Old state lived only in RAM | Design persistence and restore |

Do not read a `RemoteException` and immediately conclude Activation was removed. RemoteException has many causes: TCP reset, timeout, serialization, server crash, lookup, authentication, or failure inside the application. You need stack traces, logs from both sides, and service manager status.

## 19. Migration testing does not stop at compilation

To prove the system no longer depends on Activation, both functional and operational checks are needed.

### 19.1. Static checks

- Source no longer imports `java.rmi.activation.*` in active build paths.
- Dependencies no longer contain classes actually using the Activation API.
- Deployment scripts, Docker entrypoints, and service managers do not invoke `rmid`.
- No configs/serialized objects requiring activation-specific references remain.
- Artifacts compile with the target JDK and Java release.

### 19.2. Functional tests

- Server creates/exports remote objects successfully.
- Client looks up the exact service name.
- Remote calls return results and report errors properly.
- Authentication, authorization, and input validation are preserved.
- Data transmitted via the remote interface is compatible within the client-supported scope.
- Rare branches or administrative calls still work.

### 19.3. Lifecycle tests

Mandatory scenarios should include:

1. Server is not running yet; client must receive errors/retry as designed.
2. Supervisor starts server and registers service.
3. Client calls successfully from real host/network.
4. Server crashes between two remote calls.
5. Supervisor restarts the process and the remote object is exported again.
6. Client holding an old stub encounters an error and then re-discovers the endpoint.
7. Restart registry, verify bindings are recreated according to real topology.
8. Database/message broker temporarily unavailable at startup.
9. Perform rolling update in a multi-client-version environment.
10. Roll back according to plan if a critical error occurs.

For non-idempotent operations, do not use retry tests that cause duplicate writes without a proper environment and compensation rules.

### 19.4. Non-functional tests

Compare with baseline:

- Time from process startup to readiness.
- Cold start and steady-state latency.
- Throughput and p95/p99 remote call latency.
- CPU, heap, threads, sockets, and connection count.
- Recovery speed after crash.
- Number of retries and lookup failures.
- Timeouts, queue size, and saturation under heavy load.

Changing from on-demand activation to a continuously running service can increase baseline resources while reducing cold start latency. You must measure and evaluate against the system's operational requirements, rather than assuming one direction is better.

## 20. JDK upgrade process for systems still having RMI Activation

### Step 1: Record the current state

Save the JDK version, build tool, artifacts, list of remote interfaces, activation descriptors, group configurations, server/client topology, rmid startup scripts, registry bindings, and recovery scenarios. Identify the application owner and external dependencies.

### Step 2: Determine the removal scope

Group into direct imports, library dependencies, operational daemons, serialized references, and scripts/tests. Clearly note whether each component is still used in production or is merely inactive old code.

### Step 3: Choose the target architecture

Decide whether to keep RMI transport. If kept, choose how objects are exported, registry topology, process supervisor, service discovery, and state store. If switching to HTTP/gRPC/messaging, API contracts and client migration must be designed.

### Step 4: Replace the server lifecycle

Remove Activation registration, move startup logic to application bootstrap and/or orchestrator, export objects via regular RMI when appropriate, bind/rebind names based on readiness, and handle graceful shutdown and restart.

### Step 5: Adjust clients

Do not store or use activation-specific remote references. Clients need to find new endpoints, handle stale stubs, timeouts, safe retries, and versioning. If parallel old/new clients are needed, design a bridge only while an old runtime and supported communication boundary still exist; do not assume Java 17 can run an Activation server.

### Step 6: Handle data and configuration

Migrate necessary service metadata from activation descriptors to a config store; move business state into appropriate persistence. Record JVM flags, ports, credentials, and environment variables under the new deployment model.

### Step 7: Compile, package, and test on the new JDK

Use the target toolchain and appropriate `--release`. Verify source, dependencies, class-file versions, and startup. Run integration tests in an environment as close to production as possible.

### Step 8: Test failure scenarios and rollback

Simulate crashes, restarts, network partitions, registry failures, stale client references, and concurrent requests. The rollback process must account for differences in data, interfaces, and deployment; merely swapping JDK binaries cannot roll back if state or clients have already been migrated.

### Step 9: Remove legacy components

Only after confirming no consumers remain, stop `rmid` in old environments, delete obsolete scripts and configs, and update monitoring, runbooks, and operations training documents. Do not delete historical data before confirming retention and rollback obligations.

## 21. Change management table template

A project can build a table:

| Item | Current state | Replacement | Completion evidence |
|---|---|---|---|
| Server object registration | `Activatable` / `ActivationDesc` | `UnicastRemoteObject` + registry or new protocol | Source diff, compile |
| Process activation | `rmid` | Supervisor/orchestrator | Startup/restart test |
| Activation group flags | Group descriptor | Service/container config | Deployment review |
| Client reference | Activatable reference | New lookup logic | Client integration test |
| Metadata persistence | Activation daemon log | Config store | Config migration verification |
| Business state | In-memory or old store | Durable persistence | Recovery test |
| Monitoring | Inspect old `rmid`/JVM | Liveness/readiness/metrics | Alert test |
| Security | Old policy/RMI flags | Updated network/security config | Security validation |
| JDK baseline | Java 8/11 | Java 17+ target | Build/run reports |
| Rollback | Restore activation environment | Phased fallback path | Runbook rehearsal |

An important column is **evidence**: changing code does not yet prove the change has been deployed and recovers properly. The report should save runtime versions, artifact checksums, launch configurations, and test results.

## 22. Common mistakes

### 22.1. “Java 17 removes RMI completely”

Wrong in scope. The basic Java RMI API and `java.rmi` module continue to exist; what was removed is **RMI Activation**. How to handle errors depends on libraries and whether the design uses Activation or not.

### 22.2. “Switching to rmiregistry is enough”

Incorrect. The RMI registry stores remote names/references; it does not start implementations automatically based on activation descriptors. A new process lifecycle and registration are required.

### 22.3. “Adding --add-opens revives Activation”

Incorrect. `--add-opens` can resolve certain reflective access errors to packages that still exist; it does not restore removed `java.rmi.activation` or `rmid`.

### 22.4. “Compilation success means runtime is fine”

Incorrect. An old library compiled on JDK 8 can still contain references to Activation that are missing on JDK 17. In addition, remote calls still depend on networking, registry, serialization, class loaders, and service lifecycle.

### 22.5. “Supervisor restart is equivalent to on-demand object activation”

Not necessarily. A restart policy recovers a stopped process, whereas lazy activation on remote invocation has different semantics. If on-demand cold start is a mandatory feature, a workload-specific design is needed.

### 22.6. “Keeping serialized remote references unchanged is compatible”

Unsafe. Clients holding references belonging to old Activation may not work with the replaced server. A new lookup mechanism and client upgrade handling are needed.

### 22.7. “Data held by rmid is application state”

Do not assume this. Activation metadata and business state serve different roles. Business state needs to be inventoried, migrated, and recovery-tested separately.

## 23. Practical questions when choosing an option

**An application only uses `java.rmi.registry.Registry` and `UnicastRemoteObject`, without `rmid`; does RMI need to be replaced?**

Not because of JEP 407. It is still necessary to verify the JDK, dependencies, security, and runtime; however, that is not an Activation system requiring redesign.

**An application has source importing `java.rmi.activation.*` yet that code never runs; can it be kept?**

If the module is still compiled with JDK 17+, missing imports and symbols can cause the build to fail before considering runtime. That code should be removed, isolated reasonably, or refactored instead of letting “dead code” block migration.

**Can a JAR manually add java.rmi.activation to the classpath to run as before?**

There is no basis to treat that as a fully compatible replacement. Activation ties into multiple JDK components and the removed `rmid` daemon. One should not expect merely adding API stubs to restore the old activation mechanism.

**Do we need to migrate the application to JPMS to solve RMI Activation?**

No. Conversely, an application can stay on the classpath and still must remove Activation if running JDK 17+. JPMS modularization is a separate decision.

**Should we switch straight to REST or gRPC?**

Depends on long-term goals. If fast risk reduction is needed, migrating Activation to regular RMI and a managed lifecycle may involve fewer changes. If interoperability, scalability, and new API contracts are needed, a phased protocol migration with client compatibility tests can be planned.

**If an object is only used a few times a day, how do we keep on-demand startup?**

Separate the needs: is a background-running service acceptable, or is scale-to-zero/lazy start truly required? If on-demand is needed, design an appropriate trigger/job/queue/orchestration and accept the differences compared to an RMI Activation reference. Measure cold start and handle client timeouts/retries.

## 24. Key principles to remember

- **RMI Activation was marked deprecated for removal in Java 15 (JEP 385) and removed in Java 17 (JEP 407).**
- **Regular Java RMI does not mean RMI Activation.** The `Remote`, `UnicastRemoteObject`, and `Registry` APIs remain separate components.
- **`rmid` is not `rmiregistry`.** The registry does not start processes based on Activation registrations.
- **Do not fix removed API errors with module flags.** `--add-opens`/`--add-exports` do not bring back missing classes or daemons.
- **Must inventory source code, libraries, bytecode, startup scripts, and client references.** Activation can hide in dependencies or operations.
- **Lifecycle changes are central.** You need a process manager, startup/restart, export, bind, health checks, and state recovery.
- **Lazy activation and always-on services are not the same.** Clarify semantic requirements before choosing a solution.
- **Keeping regular RMI is a valid option** if it fits clients, deployment, and security; rewriting the protocol is a separate decision.
- **Tests must include real failures and restarts**, not just compiling successfully or checking process startup.
- **Separate activation metadata and business state.** Do not assume the old daemon is a business data store.
- **The migration process must consider client compatibility and rollback** if multiple versions operate simultaneously.

When upgrading a Java system still using the legacy RMI activation mechanism, the key question is not “how do we turn `rmid` back on in the new JDK?” but **“how should the service be initialized, discovered, monitored, and recovered without Activation?”**. Answering with a clear lifecycle design, controlled inputs/configuration, compatible communication, and end-to-end testing helps remove historical dependencies while preserving system operability on modern JDKs.
