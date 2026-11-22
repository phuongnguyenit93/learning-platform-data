# Designing Callbacks That Can Handle Partial Initialization States

In a Java application, a resource is rarely created in a single operation. To open an HTTP server, the application might read configuration, create an executor, bind a socket, and register handlers. A connection pool might create multiple connections and run health checks before being put into use. Any step can fail partway through.

CRaC (Coordinated Restore at Checkpoint) adds two state transition points to the application's lifecycle: the pre-checkpoint callback and the post-restore callback. If a callback assumes every component is already fully initialized, an error occurring during startup can cause the callback to mistakenly close non-existent resources, miss partially opened resources, or mark the application as ready even though only some dependencies were restored.

A good design needs to track the actual state of each resource, handle initialization operations that fail partway through, close resources in the reverse order of opening, and only announce the application as ready after all required components are operational.

## 1. When does partial initialization occur?

A resource can be in an incomplete state in many situations:

- A constructor or factory opens part of the resources and then encounters an exception.
- Application startup is in progress when a checkpoint is requested.
- A required dependency fails to connect, while previous dependencies have already opened successfully.
- The application has optional resources that are only created when a feature is enabled.
- Restore succeeds for some resources, but the next resource cannot connect to an external system.
- A callback times out or is interrupted while closing/opening resources.

For example, initializing an HTTP server might consist of the following steps:

~~~text
NEW
 │
 ▼
Read configuration
 │
 ▼
Create executor
 │
 ▼
Bind socket
 │
 ▼
Register handler
 │
 ▼
Start accepting requests
 │
 ▼
READY
~~~

If binding the socket succeeds but registering the handler fails, the application has created an operating system resource, yet the server is not in a serving state. A single boolean variable like `initialized = true/false` cannot accurately describe this condition.

The callback needs to know which components were attempted to be opened, which components are actually active, and which components may need to be closed and cleaned up after an error.

## 2. State model for the resource lifecycle

Instead of inferring state from whether a field is non-null, model the lifecycle into explicit states.

| State | Meaning |
|---|---|
| NEW | The resource manager has been created, initialization has not started |
| INITIALIZING | Opening components in dependency order |
| READY | All required components initialized successfully |
| PREPARING | Stopping and releasing resources before checkpoint |
| PREPARED | Resources that need closing have been released, state is ready for checkpoint |
| RESTORING | Recreating resources after restore |
| FAILED | An initialization, closing, or restoration step failed |
| CLOSED | The application proactively ended the resource lifecycle |

Main state flow:

~~~text
                 startup succeeds
        NEW ──> INITIALIZING ─────────> READY
                     │                   │
                     │ startup fails     │ beforeCheckpoint
                     ▼                   ▼
                   FAILED            PREPARING
                                         │
                             close succeeds
                                         ▼
                                      PREPARED
                                         │
                                      restore
                                         ▼
                                     RESTORING
                                         │
                            restore succeeds
                                         ▼
                                       READY

        INITIALIZING / READY / RESTORING
                     │
               unrecoverable error
                     ▼
                   FAILED
~~~

Each callback should only accept states that are valid for its phase:

- `beforeCheckpoint` only starts when all required resources are in the `READY` state.
- `afterRestore` only restarts resources that have gone through the `PREPARED` phase.
- If startup or restore fails, the state must reflect `FAILED`; do not continue accepting traffic as if the application were ready.
- If the application is already `CLOSED`, callbacks should not arbitrarily reopen resources.

Checking state helps detect out-of-order execution early. A callback running while the resource is still `NEW` or `FAILED` must report an explicit error instead of silently skipping and letting the checkpoint contain an unsafe state.

## 3. Tracking each opened resource

A resource manager typically owns multiple resources: executors, sockets, connection pools, consumers, or schedulers. These resources are opened in a certain order and must be closed in the reverse order.

For example:

~~~text
Open:
1. Configuration
2. DatabasePool
3. OrderService
4. HttpServer

Close before checkpoint:
4. HttpServer
3. OrderService
2. DatabasePool
1. Configuration (if release is needed)
~~~

Do not store only a `ready` flag. Store a list or separate state for each part that has been initialized. When startup fails at step 4, the manager knows steps 1, 2, and 3 were attempted to be opened and need to be cleaned up.

An important principle is to **record an element before calling the start operation**. If `start` opens a socket and then throws an exception, the manager still knows to call cleanup for that element.

~~~java
for (Part part : parts) {
    attempted.add(part);
    part.start();
}
~~~

Because the element is added to the list before the `start()` call, its `stop()` method must tolerate the case where `start` only partially completed. If a library does not provide a safe close operation after a failed initialization, the application's adapter must release local resources itself before throwing the exception.

## 4. Registering resources and avoiding exposing incomplete objects

A common design mistake is registering `this` in the constructor and then continuing to initialize fields:

~~~java
public MyResource() {
    Core.getGlobalContext().register(this);
    openConnection();
    startWorker();
}
~~~

If `openConnection()` or `startWorker()` fails, the object has already been placed into the context even though the constructor did not complete. The JVM/CRaC may still hold a reference to the registered resource while the object is in an incomplete state. Subsequent callbacks would have to handle an object whose constructor failed.

There are two appropriate ways to organize this, depending on when the application allows a checkpoint.

### 4.1. Register a coordinator before starting initialization

When a checkpoint may be requested during application startup, create a resource coordinator with state `NEW`, register the coordinator first, and only then begin opening components. The coordinator's callback checks the state and rejects the checkpoint if startup is not complete.

~~~java
ManagedCracResource resource =
        new ManagedCracResource(parts);

Core.getGlobalContext().register(resource);

// Only READY after all required components have opened successfully.
resource.start();
~~~

The coordinator exists validly from the beginning, but has not yet declared its child resources ready. If a callback runs before `start()` begins, it sees the `NEW` state and reports an error so the checkpoint does not proceed with an incomplete application state. If startup already holds the lifecycle lock, the callback is serialized and only continues after startup finishes; at that point it sees `READY` or `FAILED`.

This approach avoids registering a child object whose constructor has not finished. The coordinator owns the entire lifecycle and tracks the initialization progress of the components.

If startup fails, the registered coordinator remains in the `FAILED` state. The application must maintain the `NOT_READY` state and follow the defined stop/restart policy; do not create a second coordinator on the same context and continue serving as if the previous initialization never happened.

### 4.2. Register after initialization completes

If the system has a reliable mechanism to prevent checkpoints during the startup phase, you can fully initialize the resource first and then register it. However, you must close the time window between when the resources are opened and when the resource is registered. If a checkpoint can occur in that window, the callback will not be called for the unregistered resource.

Therefore, do not choose the registration timing based solely on constructor convenience. Clearly determine when a checkpoint can be requested and which component is responsible for blocking checkpoints before the application is `READY`.

## 5. Initialization must be rollback-capable

When a startup step fails, the manager needs to close previously opened parts in reverse order. You should not let each failed startup create additional sockets, threads, or connections without a release path.

A useful contract for each component is:

- `start()` creates the resource and only returns successfully when the component is ready.
- If `start()` throws an exception after partial allocation, `stop()` must still be safe to call.
- `stop()` is idempotent: calling it when not yet started, calling it after a partial start failure, or calling it again after already closed does not create unnecessary secondary errors.
- The component releases temporary resources it created that have not yet been handed over to the manager.

Rollback pattern:

~~~java
List<Part> attempted = new ArrayList<>();

try {
    for (Part part : parts) {
        // Record first to clean up even if start fails partway through.
        attempted.add(part);
        part.start();
    }
} catch (Exception startupFailure) {
    Exception cleanupFailure = stopInReverseOrder(attempted);

    if (cleanupFailure != null) {
        startupFailure.addSuppressed(cleanupFailure);
    }

    throw startupFailure;
}
~~~

`stopInReverseOrder` needs to continue closing the remaining parts even if one close operation fails. If it stops immediately at the first exception, resources deeper in the dependency graph may remain open.

~~~java
private static Exception stopInReverseOrder(List<Part> parts) {
    Exception firstFailure = null;

    for (int i = parts.size() - 1; i >= 0; i--) {
        try {
            parts.get(i).stop();
        } catch (Exception failure) {
            if (firstFailure == null) {
                firstFailure = failure;
            } else {
                firstFailure.addSuppressed(failure);
            }
        }
    }

    return firstFailure;
}
~~~

The original initialization exception remains the primary error. Cleanup errors are attached using `addSuppressed` so logs preserve both the root cause and resource release errors.

## 6. Example of a coordinator managing state and callbacks

The following example uses a `Part` interface to represent a database pool, service, or HTTP server. Components are passed in dependency order: foundational components first, dependent components later.

~~~java
package com.example.crac;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.ArrayList;
import java.util.List;

public final class ManagedCracResource implements Resource {

    public interface Part {
        void start() throws Exception;
        void stop() throws Exception;
    }

    private enum State {
        NEW,
        INITIALIZING,
        READY,
        PREPARING,
        PREPARED,
        RESTORING,
        FAILED,
        CLOSED
    }

    private final Object lifecycleLock = new Object();
    private final List<Part> parts;

    // Includes the element whose start() is currently executing or has executed.
    private final List<Part> attempted = new ArrayList<>();

    private State state = State.NEW;

    public ManagedCracResource(List<Part> parts) {
        this.parts = List.copyOf(parts);
    }

    public static ManagedCracResource register(List<Part> parts) {
        ManagedCracResource resource =
                new ManagedCracResource(parts);

        Core.getGlobalContext().register(resource);
        return resource;
    }

    public void start() throws Exception {
        synchronized (lifecycleLock) {
            requireState(State.NEW);
            state = State.INITIALIZING;

            try {
                startInOrder();
                state = State.READY;
            } catch (Exception startupFailure) {
                Exception cleanupFailure =
                        stopInReverseOrder(attempted);
                attempted.clear();
                state = State.FAILED;

                if (cleanupFailure != null) {
                    startupFailure.addSuppressed(cleanupFailure);
                }

                throw startupFailure;
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        synchronized (lifecycleLock) {
            requireState(State.READY);
            state = State.PREPARING;

            Exception failure =
                    stopInReverseOrder(attempted);
            attempted.clear();

            if (failure != null) {
                state = State.FAILED;
                throw failure;
            }

            state = State.PREPARED;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        synchronized (lifecycleLock) {
            requireState(State.PREPARED);
            state = State.RESTORING;

            try {
                startInOrder();
                state = State.READY;
            } catch (Exception restoreFailure) {
                Exception cleanupFailure =
                        stopInReverseOrder(attempted);
                attempted.clear();
                state = State.FAILED;

                if (cleanupFailure != null) {
                    restoreFailure.addSuppressed(cleanupFailure);
                }

                throw restoreFailure;
            }
        }
    }

    private void startInOrder() throws Exception {
        for (Part part : parts) {
            // Record before start so partially initialized parts can be cleaned up.
            attempted.add(part);
            part.start();
        }
    }

    private static Exception stopInReverseOrder(List<Part> parts) {
        Exception firstFailure = null;

        for (int i = parts.size() - 1; i >= 0; i--) {
            try {
                parts.get(i).stop();
            } catch (Exception failure) {
                if (firstFailure == null) {
                    firstFailure = failure;
                } else {
                    firstFailure.addSuppressed(failure);
                }
            }
        }

        return firstFailure;
    }

    private void requireState(State expected) {
        if (state != expected) {
            throw new IllegalStateException(
                    "Expected state " + expected + " but was " + state);
        }
    }
}
~~~

Usage sequence:

~~~java
List<ManagedCracResource.Part> parts = List.of(
        databasePoolPart,
        orderServicePart,
        httpServerPart
);

ManagedCracResource resource =
        ManagedCracResource.register(parts);

resource.start();

// Only announce READY for the application after start() completes.
applicationReadiness.markReady();
~~~

The example illustrates several important points:

1. The coordinator is registered before opening child resources.
2. Callbacks do not assume components are always in the `READY` state.
3. The `attempted` list records elements before calling `start()`.
4. Failed startup rolls back in reverse order.
5. `beforeCheckpoint` only accepts the `READY` state.
6. `afterRestore` only restores when the checkpoint state is `PREPARED`.
7. Failed restore also rolls back components that were attempted to be opened and keeps the `FAILED` state.
8. Cleanup exceptions are attached to the original error instead of being ignored.

This is a lifecycle management skeleton. In a real application, you need to add timeout policies, proactive shutdown, readiness/health checks, fatal error handling, and synchronization with the framework's lifecycle.

The example calling `applicationReadiness.markReady()` illustrates initial startup. In a real application, readiness must be updated after both success paths: after initial `start()` and after `afterRestore()` completes and the coordinator transitions back to `READY`. Before starting to stop resources for checkpoint, the application should also transition readiness to `NOT_READY` so the load balancer or orchestration layer does not send more traffic.

## 7. Pre-checkpoint callbacks must handle unready states

`beforeCheckpoint` is the last opportunity for the application to stop work and bring resources into a safe state before taking a snapshot. The callback should not simply call `close()` on every field without checking state.

### 7.1. If startup has not completed

There are two common policies:

- **Reject the checkpoint:** if startup is in progress, throw a meaningful exception to indicate that the application has not reached a checkpointable state.
- **Wait for startup with a bound:** only use when startup can complete quickly, has a clear deadline, and the callback cannot get stuck indefinitely.

If using a waiting mechanism, there must be a timeout. Do not let the checkpoint thread wait indefinitely while the startup thread is hung due to a network connection or an unavailable dependency.

In the example coordinator, `start()` and the callbacks use the same lock. The callback only enters after startup releases the lock; then it checks the state. If startup succeeded, the callback sees `READY`; if startup failed, the callback sees `FAILED` and rejects the checkpoint.

This is a simple way to serialize state transitions. For startup with long I/O, production systems should use a lifecycle gate with a timeout or a separate readiness barrier, instead of holding a monitor for a long time without a bound.

### 7.2. If only some resources were opened

If the application allows callbacks to see partial states, it must rely on the list of resources that were attempted to be opened. Close in reverse order and let each `stop()` handle the case where it was not opened or only partially opened.

Do not use a condition like:

~~~java
if (initialized) {
    closeEverything();
}
~~~

This flag is usually only set after the entire startup succeeds. If startup fails partway through, it remains `false` even though sockets, threads, or connections have been created. As a result, cleanup is skipped.

## 8. Post-restore callbacks must restore in a controlled manner

After restore, the state in the checkpoint needs to indicate that the application completed the pre-checkpoint preparation phase. The example coordinator saves the `PREPARED` state before the snapshot. `afterRestore` only starts from that state.

### 8.1. Restore in dependency order

If at startup you opened:

~~~text
Configuration → DatabasePool → OrderService → HttpServer
~~~

then after restore, restore in this exact same order. The database pool must have valid connections before the service uses it; the HTTP server only opens its listener after the service is ready.

### 8.2. If restore fails partway through

Suppose the database pool and service restore successfully, but the HTTP server fails to bind the port. You should not mark the application `READY`. You can choose one of two policies depending on the architecture:

- **Fail restore:** stop the already restored components in reverse order, log the error, and keep the process from accepting traffic.
- **Intentional degraded mode:** only appropriate when the failed component is optional, all related requests are explicitly blocked, and health/readiness accurately reflects the state.

Do not automatically ignore errors from required resources. If the HTTP server is the only component receiving requests, the application cannot be considered ready when the listener cannot open.

### 8.3. Re-validate external resources

The checkpoint preserves process state, but external systems continue operating while the process is paused. After restore:

- Database connections may have been closed by the server due to timeout.
- Tokens or credentials may have expired.
- Distributed leases may have been granted to another instance.
- Message consumers may need to re-verify their processing position.
- DNS, endpoints, or network routes may have changed.

Therefore, `afterRestore` should recreate or re-validate resources that have an external lifecycle. Do not treat a Java object still sitting in the heap as proof that the socket or session it represents is still usable.

## 9. Optional resources and required resources

Not every resource needs to be present in every configuration. For example, an application might enable a message consumer in production but disable it in the development environment.

Build the resource list according to the configuration determined before startup:

~~~java
List<ManagedCracResource.Part> parts =
        new ArrayList<>();

parts.add(configurationPart);
parts.add(databasePoolPart);

if (messagingEnabled) {
    parts.add(messageConsumerPart);
}

parts.add(orderServicePart);
parts.add(httpServerPart);
~~~

Do not add `null` to the list and do not use a dummy element just as a placeholder. The order of the list must reflect the dependencies of the running configuration.

If an optional resource fails to initialize, the decision of whether the application can run in degraded mode or must fail startup needs to be clearly defined. If degraded mode is allowed, that resource must be marked as inactive and features depending on it must be disabled. Callbacks should not infer on their own that every exception can be ignored.

For required resources, initialization or restore errors must make the application not `READY`. This prevents checkpoints or traffic from passing through an incomplete state.

## 10. Synchronizing callbacks with running threads and requests

Managing resource state is not just managing fields. An HTTP server might still have requests being processed; an executor might still have tasks; a consumer might be processing messages.

Before checkpoint, the application should:

1. Stop accepting new work at boundary components.
2. Wait for in-flight work to complete within a bounded period of time.
3. Cancel or save the state of remaining work according to business policy.
4. Close dependencies after no consumers are using them.
5. Only report the callback as complete when the state is safe.

Do not close the database pool while running requests still hold connections. Do not close the executor before deciding whether executing tasks will finish or be canceled. Do not create a checkpoint when a thread might be modifying business data partway through without a recovery mechanism.

Use locks to protect state transitions, but avoid holding a lock while waiting for another thread that needs the same lock to finish. This is a common cause of deadlocks during shutdown. For wait operations, use a clear deadline and log the name of the resource being waited on.

## 11. Distinguishing initialization errors, cleanup errors, and restore errors

These three errors occur at different phases and need to be recorded separately:

| Phase | Example | Action |
|---|---|---|
| Startup | Database pool opens but service fails to create | Roll back attempted parts, not READY |
| beforeCheckpoint | HTTP server stops but database pool fails to close | Continue attempting cleanup of remaining parts, report callback failure |
| afterRestore | Database pool opens but HTTP server fails to bind port | Clean up restored parts, do not accept traffic |

When multiple errors occur, keep the original exception and attach cleanup errors using suppressed exceptions. Logs should include resource name, phase, before/after state, and operation duration.

Do not catch an exception and only write a generic log line like “checkpoint failed”. That information does not tell you which resource stopped, which resource is still open, or what state the application is in.

## 12. Common design mistakes

### Registering `this` too early in the constructor

If the constructor fails after registering the resource, the context may hold an incomplete object. Use a coordinator with explicit states or a factory that controls registration timing.

### Using only an `initialized` boolean

A boolean cannot describe the case where resources were partially opened. Use a state machine and track the components that were attempted to be opened.

### Only cleaning up when startup completes

If the `initialized` flag is only set after the final step, a startup that fails partway through will skip cleanup. Record each part before calling `start` and allow `stop` to handle partial state.

### Stopping immediately when one close fails

If one resource fails to close, other resources still need to be attempted to close. Collect errors instead of stopping the cleanup loop at the first exception.

### Restoring everything before checking for errors

If a foundational component is not ready, continuing to open the listener can let requests enter an unoperational service. Initialize by dependency and only mark `READY` after necessary health checks.

### Swallowing exceptions in callbacks

If a callback fails but still returns normally, the runtime may proceed with checkpoint or restore with an unsafe state. Report errors clearly so the process fails in an observable and investigable manner.

### Not bounding wait times

A hung request, connection, or thread can prevent a callback from finishing. Set timeouts, record what has not stopped, and handle according to the application's fail-fast or recovery policy.

## 13. Design verification process

Callbacks can be verified with intentionally induced failure scenarios, rather than only running the happy path.

| Test scenario | How to induce error | Expected result |
|---|---|---|
| Error at first resource | Make `start()` of the first resource throw an exception | Not READY; cleanup is called for the attempted part |
| Error at middle resource | Second resource opens partially then throws an exception | Second resource and previous resource are stopped in reverse order |
| Checkpoint before READY | Request checkpoint while startup is incomplete | Callback rejects or waits with a bound; no checkpoint created in partial state |
| Error during close | Make one `stop()` throw an exception | Still attempts to stop remaining resources; callback reports error |
| Error during restore | Make a `start()` after restore fail | Cleans up resources that were attempted to be restored; not READY |
| Optional resource absent | Disable a feature via configuration | No null entries; order of remaining resources stays correct |
| In-flight request | Hold a request while preparing checkpoint | Callback drains or times out according to designed policy |

When testing, save logs in sequence:

~~~text
resource=<name> phase=<phase> stateBefore=<state>
resource=<name> action=<start|stop> result=<success|failure>
resource=<name> stateAfter=<state>
application readiness=<READY|NOT_READY>
~~~

Failure testing needs to be performed in a dedicated test environment. Do not intentionally break a database or stop production resources to verify callbacks.

## 14. Design checklist before deploying to an application

Before integrating CRaC callbacks into an application with multiple resources, be able to answer the following questions:

- Which resources are required, and which are optional?
- Who owns each socket, thread, connection pool, consumer, and scheduler?
- Which resource depends on which resource?
- What state proves that startup is complete?
- If `start` fails after partial opening, who is responsible for cleanup?
- Is `stop()` safe when the resource is not yet open or only partially open?
- Can callbacks run during startup or while requests are being processed?
- When cleanup of one part fails, are the remaining resources still closed?
- After restore, how are external resources recreated or validated?
- Does the application only mark `READY` after all required resources are operational?
- Are there timeouts and logs detailed enough to identify the failing resource?

A reliable callback must accurately describe the true state of the process at every point in time. Register a lifecycle coordinator that can exist independently of child resources, manage state explicitly, record each initialization attempt, and perform cleanup in reverse order. When restoring, recreate dependencies in the original order and only announce `READY` after all required components have passed checks.

With this design, a startup that fails partway through, a checkpoint that arrives too early, or a restore that only partially succeeds all become states that can be detected and handled in a controlled manner.
