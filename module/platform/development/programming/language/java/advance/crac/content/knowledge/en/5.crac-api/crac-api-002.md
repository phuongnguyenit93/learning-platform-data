# Resource: declaring components that need to participate in checkpoint and restore

In CRaC, **Resource** is the contract for an application component to notify the runtime about what it needs to prepare before checkpoint and what it needs to recover after restore. A component implementing Resource can close connections, complete running work, and clean up temporary state before checkpoint; after restore, it can recreate connections, re-register listeners, or restart background tasks.

The important point is that **implementing Resource and registering its instance are two separate tasks**. A class that implements Resource but has not been registered with a Context does not automatically receive callbacks from CRaC. The application needs to register the exact instance that it wants the runtime to manage.

## 1. What is Resource?

org.crac.Resource is an interface in the CRaC API. It defines two callbacks:

- **beforeCheckpoint(...)**: called when the runtime is preparing to create a checkpoint. The Resource puts the resources it owns into a safe state.
- **afterRestore(...)**: called when the process is restored from a checkpoint. The Resource re-establishes the resources needed for the application to continue operating.

The API contract has the form:

~~~java
public interface Resource {
    void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception;

    void afterRestore(Context<? extends Resource> context)
            throws Exception;
}
~~~

This is an illustrative signature of the API; when writing an application, import the interface from the CRaC API that the JDK/runtime is using instead of redeclaring this interface yourself.

A Resource usually represents a component with a lifecycle that needs to be coordinated with checkpoint/restore, for example:

- A client connecting to a database, Redis, message broker, or HTTP service.
- A consumer receiving messages from a broker.
- A listener, socket, or background task that needs to be stopped and re-registered.
- A component holding a file, buffer, or operating system resource that needs to be closed and reopened.
- A component managing a subscription, lease, or working state that may expire while the process is paused.

There is no need to turn every Java object into a Resource. An object that only holds pure data in the heap, without owning resources that need preparation or recovery, usually does not need its own callback.

## 2. The two callbacks of Resource

### beforeCheckpoint

The runtime calls beforeCheckpoint during the checkpoint preparation phase. The component implementing the callback needs to put the resources it owns into a state that can be checkpointed safely.

Common tasks:

- Stop accepting new work through the application's coordination mechanism.
- Wait for operations currently using the resource to complete.
- Commit or roll back transactions according to business rules.
- Flush buffered data.
- Close connections or resources that are not guaranteed to be usable after restore.
- Pause consumers, listeners, or executors according to the library's guidelines.
- Release leases or distributed locks if ownership may expire while the process is inactive.

This callback should not contain new business work or perform operations that may produce side effects that cannot be safely repeated. The goal is to prepare resources and execution state for checkpoint.

### afterRestore

The runtime calls afterRestore when the process is restored. The Resource re-establishes the resources that the application needs in the current environment.

Common tasks:

- Recreate connections or clients that were closed before checkpoint.
- Restart consumers or listeners.
- Re-register subscriptions.
- Re-read configurations, credentials, or certificates that may have changed.
- Verify leases, ownership, and remote resource state.
- Check dependencies before the application accepts traffic.

Restore brings the process back to the checkpointed memory state, while external services continue operating in their real time. Therefore, afterRestore should create or verify resources based on the current state of external systems.

### Context parameter

Both callbacks receive a Context<? extends Resource> parameter. This is the context that the runtime passes in when calling the callback. A Resource may not need to use this parameter if it only manages an independent resource.

The context parameter in the callback is not a new Resource and is not a checkpoint call either. When registering an application-level Resource, initialization code usually uses the global context via Core.getGlobalContext().

### Exceptions in callbacks

The two methods declare throws Exception so that a Resource can report an error when it cannot prepare or recover a resource. Errors from closing connections, flushing data, or recreating required clients should not be caught and ignored. If a callback does not complete, the runtime may not be able to complete the corresponding checkpoint or restore phase.

The application needs to log errors with enough information to identify which Resource failed. For required dependencies, only mark the application as ready after recovery has succeeded.

## 3. Registering a Resource with Context

After having an instance that implements Resource, the application registers that instance with a Context. For application-wide components, the common approach is to register with the global context:

~~~java
Core.getGlobalContext().register(resource);
~~~

Core and Resource belong to the org.crac package:

~~~java
import org.crac.Core;
import org.crac.Resource;
~~~

The basic process consists of three steps:

1. Create an instance of the resource-managing component.
2. Register that instance with the appropriate context.
3. Let the CRaC runtime invoke the callbacks at the checkpoint and restore phases.

Example of registering a created Resource:

~~~java
RemoteClientResource resource =
        new RemoteClientResource(clientFactory);

Core.getGlobalContext().register(resource);
~~~

In the example above, clientFactory is the application's factory. Registration must point to the exact instance that owns the client the application uses. Creating one instance just for registration while the application uses a different instance will cause the callbacks to manage the wrong object.

Typically, the application registers a Resource during the initialization phase, after the required dependencies are ready and before a checkpoint can be performed. Ensure each instance is only registered intentionally; duplicate registration can cause callbacks to run multiple times on the same resource.

Having a class managed as a bean by Spring or another framework does not mean that class automatically becomes a CRaC Resource. Relying solely on dependency injection or component scanning is not enough, unless the framework being used has CRaC integration and the framework's documentation confirms that registration mechanism.

## 4. Example: Resource managing a remote client

Suppose the application uses a client to send data to an external service. The client can be closed before checkpoint and recreated after restore.

The example below defines the client and factory interfaces inside the same class to illustrate a complete Java file. In a real project, these interfaces can be replaced by the API of the library being used.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    public interface RemoteClient extends AutoCloseable {
        void publish(String message) throws Exception;

        @Override
        void close() throws Exception;
    }

    @FunctionalInterface
    public interface RemoteClientFactory {
        RemoteClient connect() throws Exception;
    }

    private final RemoteClientFactory clientFactory;
    private RemoteClient client;

    public RemoteClientResource(RemoteClientFactory clientFactory)
            throws Exception {
        this.clientFactory = clientFactory;
        this.client = clientFactory.connect();

    }

    public synchronized void publish(String message) throws Exception {
        if (client == null) {
            throw new IllegalStateException(
                    "Remote client is not available");
        }
        client.publish(message);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = clientFactory.connect();
    }
}
~~~

When the application initializes:

~~~java
RemoteClientResource remoteClient =
        new RemoteClientResource(clientFactory);
Core.getGlobalContext().register(remoteClient);
~~~

Illustrative lifecycle:

~~~text
Application initializes
       |
       v
Create RemoteClient
       |
       v
Register Resource with global Context
       |
       v
CRaC calls beforeCheckpoint()
       |
       v
Close RemoteClient and set client = null
       |
       v
Create checkpoint
       |
       v
Restore process
       |
       v
CRaC calls afterRestore()
       |
       v
Factory creates new RemoteClient
       |
       v
Application continues using client
~~~

The example shows the following points:

- implements Resource declares that the class can participate in the CRaC lifecycle.
- Core.getGlobalContext().register(remoteClient) registers the instance so the runtime knows to call the callbacks.
- beforeCheckpoint closes the managed client and releases the reference.
- afterRestore uses the factory to create a new client.
- clientFactory needs to be able to create connections in the post-restore environment, including reading valid configurations or credentials when needed.

The synchronized methods in the example prevent the publish operation from running concurrently with the callback closing or replacing the client field. In a real application, this is not yet the entire system-stopping mechanism. It is necessary to coordinate with the request-receiving layer, executors, and consumers to stop accepting new work, wait for running operations to finish, and ensure no access path bypasses the Resource to use the client directly.

## 5. Where to place Resource in the application architecture?

A Resource should be located close to the component that owns the resource's lifecycle. For example:

- If an adapter owns a broker client, the adapter or a lifecycle management class for the adapter can implement Resource.
- If a service manages its own pool, the pool management class can implement Resource.
- If multiple components depend on the same client, there should be a clear owner managing the client and registering one Resource for that lifecycle.

Multiple Resources should not close or recreate the same resource together. This can cause duplicate closes, opening multiple connections, or creating duplicate listeners after restore.

An application can register multiple Resources. Each Resource should manage a meaningful resource boundary with clear responsibilities. When resources depend on each other, consider the order of initialization, stopping, and recovery according to the documentation of the CRaC API/runtime version being used; do not let correctness depend on an unverified callback order.

For frameworks or libraries that already have CRaC integration, prioritize the provided mechanism. For example, a library may register its own Resource to manage its connection pool. Creating an additional external Resource to close the same pool can conflict with the built-in mechanism.

## 6. Principles when declaring and registering a Resource

**Register the right instance.** The registered instance must be the instance that actually owns the resource. Do not create an auxiliary Resource just for registration while another bean or service holds the real resource.

**Register after successful initialization.** Complete setting up the required fields and dependencies before registering. Avoid letting an incomplete instance receive callbacks.

**Register intentionally and avoid duplicates.** Control where Resources are created so as not to register the same instance multiple times or multiple wrappers for the same resource.

**Manage both directions of the lifecycle.** If beforeCheckpoint closes a resource, afterRestore needs to know how to recreate the resource or verify that another integration has recovered it.

**Keep callbacks focused on the lifecycle.** Do not put unrelated business logic into callbacks. Separate close, flush, reconnect, and health check logic into methods that can be managed and tested independently.

**Coordinate with active flows.** Closing a resource while requests or consumers are still using it can cause errors. The application needs to stop accepting new work and drain running work before closing.

**Use current state after restore.** The recovery factory should read valid configurations, credentials, and service addresses. Do not reuse old sessions or tokens just because the representing object is still in the heap.

**Do not hide errors.** If a required resource cannot be safely closed or recreated, let the error be reported and prevent the application from operating in an unready state.

**Design for multiple cycles.** A Resource needs to work properly across multiple beforeCheckpoint and afterRestore calls. Avoid creating new listeners, threads, or connections without releasing the previous cycle's resources.

**Handle failed checkpoints.** Do not assume every run of beforeCheckpoint will definitely lead to an afterRestore. If the checkpoint process is rejected or fails after the Resource has closed its resources, the application needs a recovery approach suitable for the runtime and checkpoint coordination mechanism being used.

## 7. Common misconceptions

**Just implementing Resource is enough.**

Not enough. The class needs to be registered with a Context. Without registration or a corresponding automatic CRaC integration, the runtime does not know which instance needs to receive callbacks.

**Registering the class instead of the instance.**

Context.register(...) takes an object implementing Resource. The application must register the instance that owns the resource, not pass a class name or merely declare a bean without a registration step.

**Calling callbacks manually to simulate restore.**

Callbacks belong to the lifecycle orchestrated by the CRaC runtime. Business code should not call beforeCheckpoint or afterRestore directly as a substitute for a real checkpoint/restore. You can test close and recreate logic by separating it into private/dedicated methods, then perform integration testing on the CRaC runtime.

**Resource is where all application state is stored.**

Resource is only a lifecycle participation contract. Business data still needs to be stored in an appropriate storage system; callbacks do not turn checkpoints into database backups or distributed transactions.

**A single Resource can close all application resources.**

A Resource should manage the resources it owns. Closing another component's resources can create conflicts over ownership and lifecycle order.

**After restore, only the wrapper object needs to be recreated.**

Creating a wrapper object does not guarantee that server-side connections, subscriptions, leases, or credentials are valid. The Resource must recover or verify the actual resource that the wrapper represents.

## 8. Testing a Resource

A Resource can be tested at two levels.

At the unit level, separate close and recreate operations into dedicated methods to test:

- The resource is closed when preparing for checkpoint.
- Calling close when the resource has not been created does not raise unexpected errors.
- The factory is called to create the resource after restore.
- Errors from the factory are propagated so the application recognizes a failed recovery state.
- Multiple close and recreate cycles do not increase the number of connections or listeners unexpectedly.

At the integration level, run the application on a JDK/runtime with CRaC support and verify:

- The registered Resource actually receives callbacks.
- The application stops or drains work before resources are closed.
- The checkpoint is created successfully once Resources have finished preparing.
- After restore, the client can connect to external services.
- Dependency restarts or credential changes during checkpoint time are handled properly.
- The application only accepts traffic after essential Resources have recovered.
- No consumers, schedulers, or listeners are registered in duplicate across multiple cycles.

A test that only calls the two callback methods directly can test the class's logic, but does not prove that the CRaC runtime has registered and orchestrated the Resource properly. Real checkpoint/restore testing is needed to confirm the entire lifecycle.

## 9. Conclusion

Resource is the extension point for an application to intentionally participate in the checkpoint and restore lifecycle. A class implementing this interface defines how to prepare resources in beforeCheckpoint and how to recover resources in afterRestore. After creating an instance, the application registers it with a Context, usually Core.getGlobalContext() for application-level resources.

Declaring and registering Resources properly helps the CRaC runtime call the right components at the right phases. Implementation quality depends on clearly identifying resource ownership, coordinating with running work, handling errors, and recreating connections based on the current state of external systems.
