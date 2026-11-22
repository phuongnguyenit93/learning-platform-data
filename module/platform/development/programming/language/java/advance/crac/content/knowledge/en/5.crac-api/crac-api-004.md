# Core.getGlobalContext() and Context.register()

In Java CRaC, an application needs to notify the runtime about resources that must be prepared before checkpoint and restored after restore. A database connection, a socket to a message broker, a consumer receiving messages, or a client holding a session all have their own lifecycles. They may no longer be valid after the process is restored, even though the Java objects representing them still remain in the heap.

The `org.crac` API provides a mechanism to register these resources. `Core.getGlobalContext()` retrieves the global CRaC context in the current JVM. The `Context.register()` method registers an object implementing `Resource` into the context so that the runtime invokes that object's lifecycle callbacks. The two APIs are typically used together:

~~~java
Core.getGlobalContext().register(myResource);
~~~

This line registers `myResource` with the JVM's checkpoint/restore lifecycle. It does not automatically close connections, reopen connections, or save business data. Those actions must be implemented in `Resource.beforeCheckpoint()` and `Resource.afterRestore()`.

## 1. The Role of Core.getGlobalContext()

`Core` is the entry point of the CRaC control API. The static method `Core.getGlobalContext()` returns the global context used to register resources that the application wants CRaC to notify during checkpoint and restore.

Example:

~~~java
import org.crac.Core;

// Get the global CRaC context in the current JVM.
var context = Core.getGlobalContext();
~~~

From this context, the application can register objects implementing `Resource`:

~~~java
context.register(databaseResource);
context.register(brokerResource);
context.register(fileResource);
~~~

The name *global context* should be understood within the scope of the JVM. It is the shared context of the application running in that process, helping centralize the registration of resources that need to participate in the CRaC lifecycle. It is not a cluster-wide registry, is not shared across JVMs, and does not automatically register resources with a database, service discovery, or message broker.

If the application runs multiple replicas, each replica has its own JVM process and lifecycle. Each JVM must manage its own resources. A resource registered in one JVM does not represent the connections or state of another JVM.

`Core.getGlobalContext()` only provides the context. Calling this method does not checkpoint the application immediately, does not create a checkpoint, and does not automatically inspect all open resources. The runtime only knows about resources that are registered or integrated through the corresponding mechanism.

## 2. Context and the register() Method

`Context` is the place that collects `Resource` objects that need to be notified during the checkpoint/restore lifecycle. The `register()` method takes a resource and registers it with the context:

~~~java
Context<Resource> context = Core.getGlobalContext();
context.register(resource);
~~~

In this example:

- `Core.getGlobalContext()` retrieves the global context.
- `Context<Resource>` represents a context that can register objects of type `Resource`.
- `register(resource)` adds the object to the list of resources managed by the context.
- The registered object must implement `org.crac.Resource` and provide callbacks according to the API contract.

Registration is the step that connects the object to the CRaC lifecycle. `register()` itself does not call `beforeCheckpoint()` immediately at registration time, nor does it call `afterRestore()` immediately. The callbacks are invoked by the runtime when the process goes through the corresponding phases.

Therefore, register resources during application initialization, after the object has been created and is ready to manage the resource, while ensuring registration completes before the checkpoint begins. Do not wait until a checkpoint is already underway to find and register critical resources.

### 2.1. Which Objects Need to Be Registered?

Register the object responsible for managing the lifecycle of a resource that needs to be prepared or recreated. For example:

| Resource | Pre-checkpoint tasks | Post-restore tasks |
|---|---|---|
| Database connection pool | Stop issuing new connections, wait for in-flight operations, and close the pool | Create a new pool and verify connectivity |
| Message consumer | Stop receiving messages, complete or return in-flight work, close the consumer | Create a new consumer and register subscriptions |
| Socket to an external service | Stop data exchange and close the socket | Open a new connection, authenticate, and restore protocol state |
| File being written | Complete write operations, flush, and close the file | Reopen the file, check its state, and then continue |
| Client holding a session or token | Stop using the old session and release related resources | Re-authenticate or refresh the token, create a new session |

Not every Java object needs to be registered. An object containing only immutable data or pure heap data may not need its own callbacks. Focus on resources with lifecycles external to the JVM, native resources, or state that needs to be verified after restore.

If a library already provides CRaC integration and registers its own resources, use the mechanism supported by the library. Avoid registering another resource to close the same resource if doing so could cause the resource to be closed twice or have two callbacks manage the same state.

## 3. Resource and the Two Lifecycle Callbacks

An object registered with a context typically implements the `org.crac.Resource` interface. This interface defines two main callbacks:

~~~java
void beforeCheckpoint(Context<? extends Resource> context) throws Exception;
void afterRestore(Context<? extends Resource> context) throws Exception;
~~~

`beforeCheckpoint()` is called when CRaC prepares for a checkpoint. The resource uses this callback to bring the resource into a safe state: stop accepting new work, complete or cancel in-flight operations according to policy, flush necessary data, and close connections that cannot continue to be used safely.

`afterRestore()` is called when the process is restored. The resource uses this callback to recreate connections, refresh credentials, restore subscriptions, and verify external dependencies.

The `Context<? extends Resource>` parameter is the context associated with the callback notification. In a simple implementation, the resource may not need to use this parameter, but it must still declare the exact method signature required by the interface.

A minimal implementation:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExampleResource implements Resource {

    public ExampleResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        System.out.println("Prepare resource before checkpoint");
        // Stop work and release resources here.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        System.out.println("Restore resource after checkpoint");
        // Recreate resources and verify dependencies here.
    }
}
~~~

The constructor registers the newly created object itself. After the application instantiates `ExampleResource`, CRaC can invoke the two callbacks as the process goes through the checkpoint/restore lifecycle.

This example only illustrates how to register and the callback signatures. A real application must replace the print statements with concrete resource management operations. Logging does not make a socket, connection pool, or session safe upon restore.

## 4. Example: Registering a Resource That Manages a Socket

Suppose the application maintains a socket connected to an external service. When the JVM is paused for a checkpoint, the server side may close the connection due to a timeout or network policy. After restore, the old socket should not be treated as an active connection. The resource needs to close the socket before checkpoint and open a new connection after restore.

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ServiceSocketResource implements Resource {
    private final String host;
    private final int port;
    private Socket socket;

    public ServiceSocketResource(String host, int port)
            throws IOException {
        this.host = host;
        this.port = port;

        // Create the initial resource.
        connect();

        // Register the resource's lifecycle with CRaC.
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeSocket();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        connect();
    }

    private void connect() throws IOException {
        Socket candidate = new Socket();
        try {
            candidate.connect(
                    new InetSocketAddress(host, port),
                    5_000
            );
            socket = candidate;
        } catch (IOException error) {
            try {
                candidate.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            throw error;
        }
    }

    private void closeSocket() throws IOException {
        Socket current = socket;
        socket = null;

        if (current != null) {
            current.close();
        }
    }
}
~~~

In the example:

1. The constructor takes the service address and creates the initial connection.
2. After the connection is created, `Core.getGlobalContext().register(this)` registers the resource with the global context.
3. When preparing for checkpoint, `beforeCheckpoint()` closes the current socket and clears the reference to it.
4. Upon restore, `afterRestore()` calls `connect()` to create a new socket.

This code demonstrates the basic lifecycle of a socket. A real protocol may require additional steps such as authentication, handshake, client registration, subscription restoration, or application state synchronization after the connection is opened. Those steps need to be included in the corresponding recovery flow.

Additionally, closing the socket does not by itself guarantee that no other thread is still using the socket. Before the callback closes the resource, the application needs to stop accepting new work and wait for in-flight operations to finish within an appropriate deadline. Method-level synchronization only protects the methods in the example; it does not replace an application-wide request draining mechanism.

## 5. Registration Order and Callback Order

Registration order matters when multiple resources depend on each other. According to the rules of CRaC Context, resources in the same context are notified in the following order:

- `beforeCheckpoint()`: in the reverse order of registration.
- `afterRestore()`: in the order of registration.

This rule creates a stack-like lifecycle: resources created earlier can be restored earlier, while dependent resources are closed before the underlying resources they need are closed.

Suppose an application has two resources:

- `databasePool` manages database connections.
- `orderService` uses `databasePool` to process business logic.

`orderService` depends on `databasePool`, so the pool needs to be ready before the service starts serving. When registering, register the pool first and then register the service:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApplicationResources {
    public void register(
            Resource databasePool,
            Resource orderService) {

        Context<Resource> context = Core.getGlobalContext();

        // Register the foundational resource first.
        context.register(databasePool);

        // Register the dependent component afterward.
        context.register(orderService);
    }
}
~~~

The callback order will be:

| Phase | Order | Reason |
|---|---|---|
| Before checkpoint | `orderService` then `databasePool` | Stop the component using the pool first, then close the pool |
| After restore | `databasePool` then `orderService` | Create the pool first, then restart the service |

If registered in the reverse order, the callbacks may run in the wrong order relative to the dependency relationship. In that case, the service might still be stopping or starting while the pool is already closed or not yet ready.

With multiple resources, map out the dependency relationships before deciding the registration order. If A needs B to operate, typically register B before A so that A is stopped before B and restored after B. The entire dependency graph should be checked to avoid dependency cycles or two callbacks managing the same resource.

## 6. Where Should Resources Be Registered in the Application?

A good place for registration is typically the bootstrap phase, when the application creates infrastructure components. For example, a web application might create the connection pool, broker client, and business services during startup. After the resource objects are created and able to manage their lifecycles, the application registers them with the global context.

A clean way to organize this is to group registrations into a configuration class or resource initialization class:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceRegistrar {

    public void registerAll(
            Resource databasePool,
            Resource messageConsumer,
            Resource externalClient) {

        Context<Resource> context = Core.getGlobalContext();

        context.register(databasePool);
        context.register(messageConsumer);
        context.register(externalClient);
    }
}
~~~

This example registers three resources in a centralized location. The order should be adjusted according to the actual dependency relationships among them. If the message consumer needs the database to process messages, the database pool must be restored before the consumer, and the consumer must stop before the pool.

Some organizational principles:

- Register a resource after identifying the object that actually owns the resource's lifecycle.
- Ensure each resource has a clear lifecycle owner.
- Perform registration during a controlled initialization phase, avoiding scattered registrations across multiple request-handling branches.
- Keep the registration order readable and reflective of dependency relationships.
- Avoid registering the same resource multiple times due to constructors or initialization functions being called repeatedly.
- If a library already integrates with CRaC, check how the library manages resources before adding custom callbacks.

Centralized registration helps maintainers know which resources the application is managing through CRaC and how the callback order is formed. For large applications, resources can be divided into groups by component, while still controlling the order between dependent groups.

## 7. What register() Does Not Do

A common misconception is assuming that simply calling `register()` will make CRaC automatically make the resource safe. In reality, `register()` only registers the object so the runtime invokes its callbacks. The actual resource management logic remains the responsibility of the application or integrating library.

| Misconception | Actual behavior |
|---|---|
| Calling `register()` will close the connection immediately | Registers the resource; closing the connection must be written in `beforeCheckpoint()` |
| CRaC automatically reopens all connections after restore | The application or library must recreate connections in `afterRestore()` |
| Global context synchronizes state with the database | Context only manages callbacks in the JVM; the database has its own lifecycle and state |
| Registering an object means its data is durable | Checkpoint may preserve heap state, but it does not replace a storage system |
| Every object in the application is automatically registered | Only registered resources or those integrated via a corresponding mechanism participate in callbacks |
| Global context is shared across all replicas | Each JVM has its own CRaC lifecycle |
| Callbacks can ignore dependency relationships | Registration order affects callback order within the same context |

Therefore, treat `Core.getGlobalContext()` and `Context.register()` as the mechanism that connects application resources to the CRaC lifecycle. They do not replace designing transaction handling, idempotency, data synchronization, or connection protocols with external systems.

## 8. Error Handling in Callbacks

`Resource` callback methods are allowed to declare `throws Exception` because preparing or restoring a resource can fail. For example:

- The database cannot close the pool because an operation is still using a connection.
- A socket fails to close due to an I/O error.
- The database or broker is not yet ready when `afterRestore()` attempts to reconnect.
- A token has expired and the token-issuing service is temporarily unreachable.
- A required file or volume has not been remounted yet.

Do not catch all exceptions and ignore them. If `beforeCheckpoint()` cannot bring a resource into a safe state, continuing the checkpoint may cause the image to contain an inconsistent state. If `afterRestore()` cannot restore a required dependency, the application should not accept business traffic as if it were ready.

Some error-handling principles:

1. Only report a callback as complete when the required operations have reached a well-defined outcome.
2. Log enough information to identify the resource and the failed phase, without logging tokens, passwords, or sensitive data.
3. Use timeouts for connections and wait operations so callbacks do not hang indefinitely.
4. Use bounded retries, backoff, and jitter when external dependencies may be temporarily unavailable.
5. Keep readiness in a not-ready state until required dependencies have been restored.
6. Make close and restore operations able to handle already-closed or partially initialized states.

Callback errors can prevent the checkpoint or restore process from completing as the application expects. How the runtime reports errors and how the deployment environment reacts depend on the CRaC version and platform. Check the runtime logs and test both success and failure paths.

## 9. Designing Callbacks That Can Run Safely

A good callback should have a clear outcome and be repeatable within reasonable bounds. For example, calling `close()` twice should not put the application into an unrecoverable state; calling `connect()` when a connection already exists should also have clear rules.

Consider the following aspects:

### Stop Work Before Closing Resources

If a consumer is processing a message or a request is using a connection pool, closing the resource immediately can leave operations unfinished. The application needs to transition to a state where it stops accepting work, drain in-flight operations, handle transactions according to policy, and only then close the resource.

### Restore in Dependency Order

Recreate foundational components before starting components that use them. For example: restore the network client before the consumer; restore the connection pool before the business service.

### Verify External State

Do not only check whether a Java variable is non-`null`. Verify connections, sessions, lease ownership, tokens, and data versions with the authoritative system.

### Keep Callbacks Time-Bounded

Callbacks may need to perform I/O, but they must have timeouts and failure policies. Do not let a callback wait indefinitely on an external service that is down.

### Do Not Put Arbitrary Business Work into Callbacks

Callbacks should focus on preparing and restoring resources. Avoid creating new business transactions, sending payments, or emitting business messages simply because a callback was invoked. If an external operation must be performed, design for idempotency and persist the result durably.

## 10. Workflow for Using the Two APIs in an Application

You can implement this in the following sequence:

1. Identify which resources need to be closed, refreshed, or verified across checkpoint/restore.
2. Create a class implementing `Resource` for each lifecycle owner or group of resources sharing the same rules.
3. Write `beforeCheckpoint()` to stop activity, complete necessary work, and release resources.
4. Write `afterRestore()` to recreate resources, authenticate, and verify dependencies.
5. Obtain the context using `Core.getGlobalContext()` during the bootstrap phase.
6. Register resources using `Context.register()` in dependency order.
7. Test checkpointing while the application has traffic, then restore and verify external dependencies.
8. Test connection errors, timeouts, and the case where multiple instances are created from the same checkpoint.

Overall flow:

~~~mermaid
flowchart TD
    A[Initialize application] --> B[Create Resource]
    B --> C[Core.getGlobalContext]
    C --> D[Context.register Resource]
    D --> E[Application running]
    E --> F[beforeCheckpoint]
    F --> G[Close or prepare resources]
    G --> H[CRaC checkpoint]
    H --> I[CRaC restore]
    I --> J[afterRestore]
    J --> K[Recreate and verify resources]
    K --> L[Application ready]
~~~

`Core.getGlobalContext()` and `Context.register()` are the two steps that connect a `Resource` object to the CRaC lifecycle. Proper design requires clearly identifying who owns each resource, what the callbacks must do, which resources depend on which, and when the application is allowed to resume accepting work.

## 11. Testing Resource Registration

Testing should not only confirm that the program can call `register()`. It must prove that the runtime actually invokes the callbacks and that resources can be recovered in the deployment environment.

Some scenarios to test:

- Does the registered resource run `beforeCheckpoint()` when a checkpoint occurs?
- Does the resource have `afterRestore()` invoked after the process is restored?
- Do multiple resources execute callbacks in the expected registration order?
- If a resource depends on a database pool, is the pool ready before that resource restores?
- If a callback fails while closing a resource, does the checkpoint process report the error clearly?
- If the database or broker is not ready after restore, does the application keep readiness in the appropriate state?
- If multiple replicas are created from the same checkpoint, does each replica create its own connections and identity?
- If a resource is initialized multiple times during bootstrap, does the application avoid duplicate registrations?

Run tests on the exact CRaC-enabled JDK, operating system, container runtime, and intended checkpoint/restore configuration. APIs may differ by JDK distribution or CRaC version; verify the dependencies and documentation corresponding to the environment in use.

## 12. Summary of How the Two APIs Work Together

| API | Responsibility | Typical usage |
|---|---|---|
| `Core.getGlobalContext()` | Retrieves the global CRaC lifecycle context in the JVM | Called during initialization to obtain the registration context |
| `Context.register(Resource)` | Registers a resource to receive checkpoint/restore callbacks | Called for each object implementing `Resource` |
| `Resource.beforeCheckpoint(Context)` | Prepares and releases resources before checkpoint | Drain work, flush data, close connections |
| `Resource.afterRestore(Context)` | Restores resources after restore | Reconnect, authenticate, register subscriptions, and check readiness |

When used properly, these two APIs provide a centralized registration point for the application to coordinate resource lifecycles. `Core.getGlobalContext()` provides the context, `Context.register()` registers the object, and the actual logic resides in the `Resource` callbacks. As a result, the application can prepare resources before checkpoint and proactively restore them after restore.
