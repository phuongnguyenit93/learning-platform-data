# Callback Order: Reverse Registration Order Before Checkpoint, Forward After Restore

CRaC (Coordinated Restore at Checkpoint) allows an application to prepare resources before the JVM takes a checkpoint and restore resources after the process is restored. A real-world application often has many interdependent components: the HTTP server uses a service, the service uses a connection pool, and the connection pool uses configuration and credentials. If components are closed in the wrong order, the application may leave requests running on an already-closed connection or open a listener before dependencies are ready.

CRaC defines the callback order based on the resource registration order within the same context:

- **Before checkpoint (beforeCheckpoint)**: called in the reverse order of registration.
- **After restore (afterRestore)**: called in the exact order of registration.

This rule supports a symmetric lifecycle: initialize dependencies first, dependent components later; at checkpoint, stop dependent components first, dependencies later; at restore, restore dependencies first and then start dependent components.

## 1. Callback Order Rule

Suppose an application registers three resources in sequence:

    1. DatabasePool
    2. OrderService
    3. HttpServer

Where:

- **OrderService** needs **DatabasePool** to process business logic.
- **HttpServer** calls **OrderService** when receiving requests.

CRaC invokes callbacks as follows:

    Registration order
        DatabasePool
            ↓
        OrderService
            ↓
        HttpServer

    Before checkpoint: beforeCheckpoint (reverse)
        HttpServer
            ↓
        OrderService
            ↓
        DatabasePool

    After restore: afterRestore (forward)
        DatabasePool
            ↓
        OrderService
            ↓
        HttpServer

This can be remembered with two rules:

| Phase | Order | Purpose |
|---|---|---|
| Initialization and registration | Dependencies first, dependent components later | Later components can use earlier components |
| beforeCheckpoint | Dependent components first, dependencies later | Stop traffic and work before closing underlying resources |
| afterRestore | Dependencies first, dependent components later | Rebuild the foundation before opening external activity |

For example, the HTTP server should stop accepting requests before the service stops. The service should finish in-flight work before the database pool closes. After restore, the database pool needs to be ready before the service starts; the HTTP server should only accept requests after the service is ready.

## 2. Order Is Determined at Registration Time

Resources are registered with a **Context**, usually the global context obtained from **Core.getGlobalContext()**:

    Core.getGlobalContext().register(databasePool);
    Core.getGlobalContext().register(orderService);
    Core.getGlobalContext().register(httpServer);

The callback order is based on the **actual order of register(...) calls**, not on:

- Class names or variable names.
- File order in source code.
- Alphabetical order of packages.
- Importance level of the resource.
- Automatic dependency inference from object references.

If a framework creates beans in an order different from what is expected, the registration order may also differ. If resources are registered from parallel initialization threads, the registration sequence may be unstable. For resources with dependency relationships, design an explicit bootstrap sequence and register them in that sequence.

### 2.1. Register in the Order of Successful Initialization

A resource should be registered after it has initialized successfully and is ready to participate in the checkpoint/restore lifecycle. For example, if a database pool fails to open connections, an unready resource should not be registered as if it were ready.

Conceptual pattern:

    DatabasePool databasePool = DatabasePool.open(configuration);
    Core.getGlobalContext().register(databasePool);

    OrderService orderService = OrderService.start(databasePool);
    Core.getGlobalContext().register(orderService);

    HttpServer httpServer = HttpServer.start(orderService);
    Core.getGlobalContext().register(httpServer);

This is illustrative code for the sequence. How each resource is created and closed depends on the actual library. The key point to preserve is that foundational resources are created and registered before the resources that use them.

If a resource registers itself in its constructor, ensure that object creation and registration do not happen before the resource actually has a valid state. A constructor that only stores fields without opening connections yet can cause the registration order to not reflect the true readiness order of the system.

## 3. Small Example to Observe Callback Order

The rule can be observed using a resource that only logs. The example does not need a database or web framework; the goal is to verify the sequence executed by CRaC.

### 3.1. Logging Resource

Create the class **TraceResource.java**:

    package com.example.crac;

    import org.crac.Context;
    import org.crac.Core;
    import org.crac.Resource;

    public final class TraceResource implements Resource {

        private final String name;

        public TraceResource(String name) {
            this.name = name;
            Core.getGlobalContext().register(this);
            System.out.println("registered: " + name);
        }

        @Override
        public void beforeCheckpoint(Context<? extends Resource> context) {
            System.out.println("beforeCheckpoint: " + name);
        }

        @Override
        public void afterRestore(Context<? extends Resource> context) {
            System.out.println("afterRestore: " + name);
        }
    }

Each instance holds a name so logs show which resource a callback belongs to. The constructor registers the instance into the global context as soon as it is created. In this example, the resource only logs, so registering directly in the constructor does not create an unready external resource.

### 3.2. Registering in Dependency Order

Create the class **CallbackOrderApplication.java**:

    package com.example.crac;

    import java.util.concurrent.CountDownLatch;

    public final class CallbackOrderApplication {

        private CallbackOrderApplication() {
        }

        public static void main(String[] args) throws InterruptedException {
            // Initialize dependencies first, dependent components later.
            new TraceResource("DatabasePool");
            new TraceResource("OrderService");
            new TraceResource("HttpServer");

            System.out.println("READY: waiting for checkpoint");

            // Keep the JVM alive so a checkpoint can be requested with jcmd.
            new CountDownLatch(1).await();
        }
    }

When the application starts, the expected registration log is:

    registered: DatabasePool
    registered: OrderService
    registered: HttpServer
    READY: waiting for checkpoint

Then request a JVM checkpoint using a CRaC-enabled JDK. During the checkpoint preparation phase, the expected callback log is:

    beforeCheckpoint: HttpServer
    beforeCheckpoint: OrderService
    beforeCheckpoint: DatabasePool

When restoring the checkpoint, the expected log is:

    afterRestore: DatabasePool
    afterRestore: OrderService
    afterRestore: HttpServer

The example directly confirms the reverse/forward relationship between the two phases. Invoking callbacks is orchestrated by the CRaC runtime; do not call the methods directly to simulate checkpoint or restore.

## 4. Why Does This Order Fit Dependencies?

### 4.1. Before Checkpoint: Stop from Outside In

A system typically receives work from edge components, then passes it into services and underlying resources. The shutdown sequence needs to follow that path in reverse.

With the HTTP server, service, and database pool example:

1. **HTTP server** stops accepting new requests. If there are requests in progress, the application needs to let them finish or handle them according to the designed shutdown policy.
2. **OrderService** stops accepting new work and finishes operations currently using the database.
3. **DatabasePool** closes connections after the service is no longer using them.

If the database pool is closed before the HTTP server, a new request may arrive while the service is still processing and encounter a connection error. If the service is stopped before the HTTP server while the server still accepts requests, requests may call into an already-stopped service.

### 4.2. After Restore: Restore from Inside Out

After restore, the order needs to be reversed:

1. **DatabasePool** recreates connections and verifies they can be used.
2. **OrderService** restores its operational state, caches, or required dependencies.
3. **HTTP server** opens its listener to accept requests.

If the HTTP server opens before the database pool, the application may receive traffic while the database is not ready. If the service starts before its dependencies, the first call may fail or expose an incomplete state.

### 4.3. Lifecycle Comparison Table

| Resource | Before checkpoint | After restore |
|---|---|---|
| DatabasePool | Close connections after consumers have stopped | Create and verify connections |
| OrderService | Stop accepting work, wait for in-flight processing | Restore service and dependencies |
| HttpServer | Stop accepting requests, close listener | Open listener last |

The callback rule produces this exact order if the registration sequence accurately reflects the dependency initialization sequence.

## 5. Designing Order in Multi-Resource Applications

In real-world applications, there may be more resource types than the three components in the example. Draw the dependency relationships before deciding the registration order.

Example:

    Configuration
        ├── DatabasePool
        │      └── OrderService
        │              └── HttpServer
        │
        ├── MessageConsumer
        │      └── EventHandler
        │
        └── CredentialProvider
               ├── DatabasePool
               └── ExternalApiClient

This diagram shows that some components can be independent, while some share dependencies. Within the same context, choose a registration sequence so that each dependency is registered before the resources that use it. At checkpoint, the reverse order will stop dependent resources first; at restore, the registration order will restore dependencies first.

One possible order is:

    1. Configuration
    2. CredentialProvider
    3. DatabasePool
    4. ExternalApiClient
    5. OrderService
    6. MessageConsumer
    7. EventHandler
    8. HttpServer

This is just one illustrative order for the diagram above. If the dependency graph has multiple branches, there may be multiple valid orders. The important thing is that every dependency relationship must be respected. For example, both **DatabasePool** and **ExternalApiClient** must be ready before **OrderService** if the service uses both.

### 5.1. When There Are Multiple Independent Resources

Two resources that do not depend on each other can be registered in any deterministic order, as long as that order is kept stable and does not create false dependencies. Even so, it is still best to choose a consistent order so logs are easy to read and operational results are predictable.

Do not rely on random collection order, hash maps, or thread races to determine registration order. If order matters for checkpointing, use an explicit bootstrap sequence.

### 5.2. When the Dependency Graph Changes

If a service starts using an additional new resource, review the initialization and registration sequence. For example, **OrderService** previously only used the database but now also calls **ExternalApiClient**; both dependencies must be initialized before the service.

Changing the registration order can change both callback phases. Therefore, reviewing bootstrap changes should consider the impact on **beforeCheckpoint** and **afterRestore**, not just the impact during normal application startup.

## 6. Registering Resources in Frameworks and Multi-Threaded Applications

Frameworks may create resources through dependency injection, lifecycle hooks, auto-configuration, or startup callbacks. Bean initialization order should not be inferred from class names or declaration order in configuration files if the framework does not guarantee it.

With Spring or similar frameworks, there should be an explicit CRaC lifecycle management component:

- Identify which beans need to participate in checkpoint/restore.
- Wait for beans to initialize successfully before registering the corresponding resources.
- Register in a clearly defined dependency order.
- Log the registration order for diagnostics.
- Avoid duplicate registration of the same resource across multiple lifecycle hooks.

If multiple threads register resources concurrently, the actual order may depend on thread execution scheduling. When callbacks require a specific order, consolidate registration into a sequential phase or a single coordinator.

An easy-to-control way to organize this is to create foundational resources first, then register layer by layer:

    Bootstrap
      ├── Create and register foundational dependencies
      ├── Create and register services that use dependencies
      └── Create and register edge listeners/consumers
              ↓
          Application READY

Do not mark the application as ready to receive traffic before all required dependencies have been created and registered successfully.

## 7. Callbacks Need to Be Safe When Closing and Restoring

Correct order is an important condition, but the callbacks themselves still need to be implemented safely.

### 7.1. beforeCheckpoint

The before-checkpoint callback should:

- Stop accepting new work at edge components.
- Wait for or handle in-flight requests/messages according to the application's policy.
- Stop schedulers or consumers to avoid generating new work.
- Close connections, sockets, and file handles that need to be recreated after restore.
- Log resource closing results so failing steps can be identified.

Do not close a dependency while other resources are still using it. If work cannot be stopped within the allowed time, handle the timeout and report an appropriate error; do not pretend that the resource is ready for checkpoint.

### 7.2. afterRestore

The after-restore callback should:

- Recreate connections and OS-dependent resources.
- Validate connection state instead of only checking that object references still exist.
- Refresh expired credentials or tokens if needed.
- Restore consumers/schedulers according to a policy that avoids duplicate processing.
- Only open listeners or accept work when dependencies are ready.

A Java object still existing after restore does not mean sockets, database sessions, or external leases are still valid. Callbacks must restore resources whose lifecycle is managed by the operating system or external systems.

### 7.3. Idempotency and Error Handling

Callbacks can fail due to unavailable external systems, expired credentials, or resources that cannot be reopened. Design open/close operations to check the current state before executing, avoiding closing twice or creating duplicate listeners/pools.

If a callback fails, the checkpoint/restore operation may not complete as expected. Let the error be reported clearly, logging the resource and phase where the failure occurred. Do not swallow exceptions and continue treating the application as ready. Also do not rely on the assumption that CRaC will automatically roll back all callbacks that ran before the failing callback; design clear error states and recovery procedures.

## 8. How to Verify Callback Order

You can verify using the logs of the **TraceResource** example:

1. Run the application with a CRaC-enabled JDK.
2. Confirm the registration logs appear in the order **DatabasePool**, **OrderService**, **HttpServer**.
3. Use **jcmd -l** to find the application's PID.
4. Send the command **jcmd <PID> JDK.checkpoint**.
5. Read the **beforeCheckpoint** logs and confirm the order **HttpServer**, **OrderService**, **DatabasePool**.
6. Restore the checkpoint with the matching compatible JDK.
7. Read the **afterRestore** logs and confirm the order **DatabasePool**, **OrderService**, **HttpServer**.

Example commands on Linux, with a new checkpoint directory:

    java -XX:CRaCCheckpointTo="$PWD/checkpoint-order" \
         -cp target/classes:target/dependency/* \
         com.example.crac.CallbackOrderApplication

From another terminal:

    jcmd -l
    jcmd <PID> JDK.checkpoint

After the checkpoint completes:

    java -XX:CRaCRestoreFrom="$PWD/checkpoint-order"

The classpath in the example assumes classes and dependencies have been prepared in the corresponding directories; adjust according to the project's build structure. Importantly, both checkpoint and restore must use a CRaC-enabled JDK compatible with the environment that created the checkpoint.

### 8.1. Evidence to Keep

When testing callback order in a real project, keep:

- The order in which resources were registered.
- Logs of each callback, including resource name and phase.
- Checkpoint and restore results.
- Post-restore health check results.
- JDK/CRaC version and execution environment.

If logs show an order different from expected, check where **register** is called, which lifecycle hook runs first, whether registration occurs from another thread, and whether there are duplicate registrations. Do not infer the order from a dependency diagram without verifying the actual registration sequence.

## 9. Common Misconceptions

### Thinking beforeCheckpoint runs in registration order

If you register database, service, server, then **beforeCheckpoint** runs server, service, database. Using forward order in this phase can close a dependency while a consumer is still active.

### Thinking afterRestore runs in reverse registration order

**afterRestore** runs database, service, server in the original registration order. This is the necessary sequence so that dependent components only start after dependencies are ready.

### Thinking CRaC automatically analyzes the dependency graph

CRaC executes according to the registration order in the context. The runtime does not read object references to figure out which service depends on which database or which server depends on which service. The application is responsible for registering in the right order.

### Thinking bean initialization order is always registration order

Frameworks may initialize beans via dependency injection, lazy initialization, parallel initialization, or lifecycle hooks. Only the order of calling **Context.register(...)** determines the callback order within the corresponding context.

### Thinking callbacks can replace all shutdown operations

Callbacks do not automatically know how to drain requests, finish transactions, acknowledge messages, or close pools for each library. The application must implement the appropriate logic for each resource.

## 10. Design Principles to Remember

When integrating CRaC, determine the dependency graph and successful initialization order first. Register resources in that order within the context. CRaC will invoke **beforeCheckpoint** in reverse order to stop dependent components first, then invoke **afterRestore** in forward order to restore dependencies first.

With the **DatabasePool → OrderService → HttpServer** example, the full sequence is:

    Initialization/registration:
    DatabasePool → OrderService → HttpServer

    beforeCheckpoint:
    HttpServer → OrderService → DatabasePool

    afterRestore:
    DatabasePool → OrderService → HttpServer

Keep the registration order stable, log it for verification, and handle callback errors clearly. That way, the application can stop from the edge inward to dependencies and restore from dependencies outward to the edge, reducing the risk of a component operating when the resources it needs are not yet ready.
