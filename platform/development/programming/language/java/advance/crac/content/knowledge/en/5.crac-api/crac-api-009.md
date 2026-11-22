# Weak References in Context and How to Keep a Resource Alive

In CRaC, an application registers an object implementing `Resource` with a `Context` so that the JVM invokes callbacks before checkpoint and after restore. An important detail is that registration should not be understood as the application transferring ownership of the object's lifecycle to `Context`. In a CRaC implementation that uses weak references to store registrations, `Context` can recognize a `Resource` while the object is alive, but that reference does not prevent the Garbage Collector from reclaiming the object.

Therefore, the application must hold a **strong reference** to each `Resource` throughout the period when callbacks are needed. If you only create the object and call `register()` without keeping it in a field, collection, or long-lived owner, the object may become unreachable and be reclaimed by GC before checkpoint. In that case, the callback expected by the application may not be invoked.

## 1. Context, Resource, and Object Lifecycle

`Resource` represents a resource or a component that needs to be prepared before checkpoint and restored after restore. For example: a connection pool, an application-managed socket, a background thread, a cache with state that needs synchronization, or a component integrated with a native library.

`Context` is where `Resource` instances are registered and unregistered. With the CRaC API, an application typically registers with the global context via `Core.getGlobalContext()` or an appropriate application-managed context.

A `Resource` typically implements two callbacks:

- `beforeCheckpoint(...)`: prepares the resource before the JVM creates the state snapshot. For example, completing in-flight work, closing or pausing connections that need to be recreated after restore, and putting the resource into a safe state.
- `afterRestore(...)`: restores or checks the resource when the process is restored. For example, reopening connections, recreating the pool, or restarting background tasks.

Calling `Context.register(resource)` registers the object with the CRaC lifecycle. However, in an implementation using weak references, this registration does not create a strong reference path from a GC root to `resource`.

## 2. How Do Strong References and WeakReference Differ?

The Garbage Collector determines whether an object is alive based on reachability from GC roots such as active static variables, active thread stacks, and objects reachable from those roots.

| Reference Type | Meaning for GC | Impact on Resource |
| --- | --- | --- |
| Strong reference | Keeps the object reachable; GC does not reclaim the object solely because it still has a strong reference | A field or collection of a live owner can keep the `Resource` alive. |
| Weak reference | Does not keep the object alive; the referent can be reclaimed when no strong references remain | If `Context` only holds a weak reference, registration does not guarantee the `Resource` remains alive. |
| Soft reference | Allows GC to reclaim the object when memory is needed; reclamation timing is unsuitable for mandatory lifecycle management | Do not use as a mechanism to guarantee CRaC callbacks are invoked. |
| Phantom reference | Used for tracking mechanisms after an object has become phantom reachable, typically combined with `ReferenceQueue` | Not used to keep a `Resource` alive for callbacks. |

Example of a standard weak reference in Java:

```java
Resource resource = new MyResource();
WeakReference<Resource> weak = new WeakReference<>(resource);

// The strong reference still exists, so resource is still reachable.
System.out.println(weak.get());

resource = null;
// If there are no other strong references, GC can reclaim the object.
// After being reclaimed, weak.get() returns null.
```

A weak reference only allows observing an object if it still exists. It does not replace owning and managing the object's lifecycle.

## 3. Why Can a Resource Be Reclaimed by GC After register?

Consider the following example:

```java
void registerResource() {
    MyResource resource = new MyResource();
    Core.getGlobalContext().register(resource);
}
```

The `resource` variable is only a local variable. When the method ends, the application no longer holds any strong reference through this variable. If `Context` only holds a weak reference, the object may be reclaimed by GC before checkpoint time.

A shorter form has the same problem:

```java
Core.getGlobalContext().register(new MyResource());
```

The object is created and registered, but not stored in an owner with a sufficiently long lifecycle. Completing the `register()` call does not mean the object will continue to exist until CRaC invokes the callback.

A collection containing only weak references does not solve the problem either:

```java
private final List<WeakReference<Resource>> resources = new ArrayList<>();
```

This collection only holds `WeakReference` wrappers, not strong references to the referenced `Resource` instances. When you need to guarantee that a Resource stays alive, the managing collection must hold the object directly with a strong reference.

## 4. Holding a Resource via a Field of a Long-Lived Owner

A simple approach is to store the `Resource` in a field of an object whose lifecycle is at least as long as the registration period. The owner itself must remain reachable from the application context or another GC root.

Example of an owner holding a CRaC resource:

```java
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceOwner {
    private final MyResource resource;

    public CracResourceOwner(MyDependency dependency) {
        this.resource = new MyResource(dependency);
        Core.getGlobalContext().register(this.resource);
    }
}
```

The `resource` field creates a strong reference from `CracResourceOwner` to `MyResource`. While the owner is alive, the Resource also remains reachable.

However, having a field alone is not enough if `CracResourceOwner` itself is not retained. For example, creating the owner inside a method and discarding it without storing the owner anywhere can still cause both the owner and the Resource to be reclaimed. The reference chain must have a live starting point:

```text
Spring ApplicationContext / application root
                  |
                  | strong reference
                  v
          CracResourceOwner
                  |
                  | strong reference (field)
                  v
             MyResource
                  |
                  | weak registration
                  v
              Context
```

In a Spring application, a singleton bean managed by the Spring `ApplicationContext` is usually a suitable owner, provided that the bean is created and retained for the entire duration that CRaC callbacks are needed.

## 5. Example with a Spring Singleton Bean

The following example illustrates a bean holding a `Resource` via a field. Because the singleton bean is managed by the Spring container, the owner and Resource can exist throughout the application lifecycle.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;
import javax.sql.DataSource;

@Component
public class CracResourceRegistration {
    private final DatabaseResource databaseResource;

    public CracResourceRegistration(DataSource dataSource) {
        this.databaseResource = new DatabaseResource(dataSource);
        Core.getGlobalContext().register(this.databaseResource);
    }
}

final class DatabaseResource implements Resource {
    private final DataSource dataSource;

    DatabaseResource(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) throws Exception {
        // Prepare connections/resources managed by the application.
        // Specific handling depends on the type of DataSource and pool being used.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) throws Exception {
        // Verify or reinitialize resources needed after restore.
        // Do not assume old connections are always still valid.
    }
}
```

The example focuses on the reference relationship. Closing/opening the connection pool must be implemented according to the specific pool's API; you should not close a `DataSource` and assume it can be restarted if the implementation does not support that operation.

A few notes:

- Spring manages beans with singleton scope by default if no other scope is declared.
- The owner bean must actually be component-scanned or declared in configuration so that Spring creates and retains it.
- Do not create the owner bean with prototype scope and then drop the reference after initialization.
- If the owner is destroyed during shutdown or when the application context closes, synchronize unregistration with the resource's lifecycle.
- Dependencies held by the Resource through fields must also remain valid according to their own lifecycle; keeping a Resource alive does not automatically make a socket or database connection valid after restore.

## 6. Managing Multiple Resources with a Registry

When an application has many dynamically created resources, you can create a registry responsible for registering and holding strong references to active Resources.

```java
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Component
public class CracResourceRegistry {
    private final List<Resource> resources = new ArrayList<>();

    public synchronized void register(Resource resource) {
        Objects.requireNonNull(resource, "resource");
        Core.getGlobalContext().register(resource);
        resources.add(resource);
    }

    public synchronized void unregister(Resource resource) {
        Core.getGlobalContext().unregister(resource);
        resources.remove(resource);
    }
}
```

In this example, `resources` holds a strong reference to each Resource. Because the registry is a singleton bean, the Spring container keeps the registry alive. When unregistration is needed, call `unregister()` on the Context and then remove the strong reference from the registry.

The order of operations should reflect the actual lifecycle:

1. Create the Resource and prepare its dependencies.
2. Register the Resource with the Context.
3. Keep the Resource in the registry for the entire time it needs to participate in checkpoint/restore.
4. When the resource reaches the end of its lifecycle and no longer needs callbacks, unregister it from the Context.
5. After unregistration completes, remove the strong reference so GC can reclaim the object when no other owners remain.

The sample registry uses `List` for illustration. In an application with concurrent registration/unregistration, design synchronization appropriate to the application's concurrency and lifecycle. You also need to decide how to handle duplicate registrations, errors during register/unregister, and cleaning up a Resource when initialization only partially completes.

## 7. When Should You Unregister and Release a Resource?

Holding a strong reference is necessary during the period when the Resource needs to participate in the CRaC lifecycle. That does not mean you must keep all Resources forever.

For example, a temporary connection created for a short-lived job. When the job finishes and the resource no longer needs to be managed by CRaC, the application should:

1. Ensure no callbacks or work are still using the Resource.
2. Call `Context.unregister(resource)` according to the API in use.
3. Remove the Resource from the registry/owner.
4. Release the dependencies owned by the Resource according to their rules.

Do not remove the Resource from the collection before unregistering if doing so drops the strong reference while Context still needs to manage it. Conversely, do not unregister too early while the application still needs callbacks before checkpoint or after restore.

If a Resource only needs to exist for the entire application lifecycle, a singleton owner or a field in an application service may be a simple choice. For dynamic resources, a registry with a clear lifecycle is easier to control.

## 8. Ineffective Ways to Hold a Resource

| Approach | Why It Does Not Guarantee the Resource Stays Alive |
| --- | --- |
| Only calling `Context.register(new MyResource())` | No strong reference is stored on the application side. |
| Storing `WeakReference<Resource>` in a field | The field only holds the weak reference wrapper, not keeping the referent alive. |
| Using the Resource as a key in a `WeakHashMap` | Keys are weakly held and can be reclaimed by GC. |
| Holding the Resource only in a local variable of an initialization method | When the method ends and no other strong path remains, the object can become unreachable. |
| Relying on `System.gc()` to test or keep the object | `System.gc()` is only a request/hint; it does not guarantee GC timing or outcome. |
| Keeping the Resource in a cache with eviction | The cache may evict the entry before checkpoint occurs. |
| Keeping the Resource in an owner that is itself no longer reachable | Both the owner and the Resource can be reclaimed together if there is no strong path from a GC root. |

A `static final` field can hold a Resource strongly, but you need to consider classloader lifecycle and initialization order. In a Spring application, a singleton bean or a container-managed registry usually expresses ownership and dependencies more clearly.

## 9. How to Diagnose When Callbacks Are Not Invoked

If the application expects a Resource to receive callbacks but does not see the corresponding callbacks, check both registration and reachability.

### Check Where the Resource Is Created

Find all places where the object is created and determine whether any owner still holds a strong reference after the `register()` call. Pay special attention to inline object creation, local variables, callback lambdas, or temporarily created anonymous classes.

### Check the Owner

If the Resource is stored in a field, confirm that the owner remains managed throughout the application lifecycle. With Spring, check whether the bean is instantiated, has an appropriate scope, and is destroyed prematurely.

### Check the Registry

If using a registry, confirm that the registry stores `Resource` directly in a strong collection such as an appropriate `List` or `Set`. Check that no code path removes the Resource or unregisters it before checkpoint time.

### Observe GC and the Heap

You can use a heap dump, debugger, or reference-inspection tool to see whether the Resource is still reachable. If using a `WeakReference` in a diagnostic check, you can observe `weakReference.get()` to see whether the referent still exists at the time of inspection. Do not use `System.gc()` as sole proof because GC is not required to run immediately when requested.

### Check Callback Logs

Log at registration, at the start/end of `beforeCheckpoint`, at the start/end of `afterRestore`, and at unregistration. Logs should include the Resource name or a stable identifier to distinguish instances. Avoid logging only `toString()` if the implementation does not produce an easily traceable identifier.

Conceptual log example:

```text
resource=database-pool event=registered
resource=database-pool event=beforeCheckpoint-start
resource=database-pool event=beforeCheckpoint-complete
resource=database-pool event=afterRestore-start
resource=database-pool event=afterRestore-complete
```

If the `registered` log appears but the callbacks do not appear, check reachability, unregistration, Context type, and runtime logs. The registration log itself only proves that the code called `register()`, not that the object remained alive until callback time.

## 10. Testing the Resource Lifecycle

A useful test should prove that the owner holds the Resource throughout the required lifecycle and that callbacks can still be invoked when performing checkpoint/restore in a real CRaC environment.

You can structure the test in the following steps:

1. Create the owner and Resource.
2. Register the Resource with the Context.
3. Verify that the owner stores the Resource with a strong reference.
4. Run the application long enough or create memory pressure in the test environment to observe that the Resource is still retained by the owner.
5. Perform a checkpoint using the runtime's CRaC mechanism.
6. Verify that `beforeCheckpoint` is invoked.
7. Restore and verify that `afterRestore` is invoked.
8. Unregister the Resource when its lifecycle ends and verify that the registry releases the reference.

Do not write tests that depend on `System.gc()` reclaiming an object at an exact time. GC has the right to delay collection. You can use `WeakReference` and `ReferenceQueue` in specialized tests to observe reclaimability, but final lifecycle testing must still run on the JDK/CRaC and checkpoint/restore environment that the application supports.

In addition, do not test solely by calling the two callbacks directly and concluding that CRaC works properly. Calling callbacks directly can test the Resource's internal logic, but does not verify Context registration, snapshot capability, or actual restore.

## 11. Checklist When Implementing a Resource

- [ ] Each Resource is created and registered once according to the lifecycle design.
- [ ] A live owner holds a strong reference to the Resource.
- [ ] The owner is retained by the Spring container or application root for the entire period callbacks are needed.
- [ ] Do not rely solely on weak references, `WeakHashMap`, cache eviction, or local variables.
- [ ] `beforeCheckpoint` prepares resources and handles errors intentionally.
- [ ] `afterRestore` restores or checks the required resources.
- [ ] The Resource is unregistered only when it no longer needs to participate in the CRaC lifecycle.
- [ ] After unregistering, the registry removes the strong reference to avoid retaining unnecessary objects.
- [ ] Logs identify the Resource at register, callback, and unregister times.
- [ ] Checkpoint/restore has been tested with the exact CRaC JDK and intended deployment environment.

## 12. Conclusion

Registering a `Resource` with a `Context` should not be regarded as a guarantee that the object will survive until checkpoint or restore. When Context uses weak references, GC can still reclaim the Resource if the application does not hold a strong reference elsewhere.

Have an owner with a sufficiently long lifecycle hold the Resource via a field or strong collection. In a Spring application, a singleton bean or a registry managed by `ApplicationContext` is usually suitable. When the resource reaches the end of its lifecycle, unregister first and only then release the strong reference. Clearly managing the reference chain and lifecycle in this way ensures CRaC callbacks are executed on the exact Resource the application intends.
