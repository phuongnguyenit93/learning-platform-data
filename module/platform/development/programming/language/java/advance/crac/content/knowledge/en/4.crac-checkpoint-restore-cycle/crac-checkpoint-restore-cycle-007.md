# Observing the Execution Continuation Point and the `main` Method Lifecycle

When a Java application is restored from a CRaC checkpoint, the JVM continues from the saved execution state. It does not relaunch the program as a new run and does not automatically call the `main(String[] args)` method again. The continuation point depends on where the process was executing at the time of the checkpoint: if the checkpoint was requested directly within a Java call, that thread continues after the call when restore completes; if the checkpoint was requested externally, the threads continue from the captured state.

This is a key point for understanding the CRaC lifecycle properly. A checkpoint saves the state of the entire process according to the capabilities of the runtime and environment, including the heap, class state, and execution state of the threads. Upon restore, the application continues using that state. Initialization code that ran before the checkpoint does not automatically run again; code located after the continuation point will still run when the process is restored.

## 1. `main()` is the program entry point, not the entry point of each restore

For a normal Java program, the Java launcher initializes the JVM, loads the main class, and invokes the `main(String[] args)` method. Static initializers and the required class initialization process take place before the corresponding code is executed. Afterward, `main()` controls the application's startup flow.

A simple example:

```java
public class Application {

    static {
        System.out.println("class initialized");
    }

    public static void main(String[] args) {
        System.out.println("main entered");
        initialize();
        serve();
    }

    private static void initialize() {
        System.out.println("application initialized");
    }

    private static void serve() {
        System.out.println("serving requests");
    }
}
```

In a cold run, the main thread goes through the steps in order: the class is initialized, `main()` is called, the application is initialized, and finally it starts serving. When the process is checkpointed after completing part of these steps, the completed state is preserved in the checkpoint.

Restoring is not equivalent to running the `java -jar application.jar` command again. A normal fresh launch creates a new JVM and calls `main()` from the beginning. A CRaC restore loads the saved process state, so the main thread continues from the stack frame and execution position that were checkpointed. Static initializers, the beginning of `main()`, and completed initialization steps are not automatically invoked again.

The difference can be remembered as follows:

| Cold startup | Restore from CRaC |
|---|---|
| Java launcher creates a new JVM process | Runtime restores the process from the checkpoint |
| Classes are loaded and initialized along the startup flow | Saved class state is restored |
| Launcher calls `main()` | Does not call `main()` again |
| Code runs from the beginning along the startup flow | Threads continue from the saved state |
| Application recreates objects and context | Heap and checkpointed states are recovered |

## 2. Observing the continuation point when calling `Core.checkpointRestore()`

An easy way to observe the continuation point is to request a checkpoint from within the application itself using the CRaC API. In the following example, the `Core.checkpointRestore()` call is the point where the execution thread pauses to create a checkpoint. When a process is restored from that checkpoint, the call completes and the thread continues with the next statement.

```java
import org.crac.Core;

public class CheckpointApplication {

    public static void main(String[] args) throws Exception {
        System.out.println("1. main entered");

        initializeApplication();
        warmUpApplication();

        System.out.println("2. requesting checkpoint");
        Core.checkpointRestore();

        System.out.println("3. execution resumed after restore");
        verifyExternalResources();
        startServing();
    }

    private static void initializeApplication() {
        System.out.println("initialize application");
    }

    private static void warmUpApplication() {
        System.out.println("warm up application");
    }

    private static void verifyExternalResources() {
        System.out.println("verify resources");
    }

    private static void startServing() {
        System.out.println("start serving");
    }
}
```

The example assumes the application runs with a CRaC-enabled JDK and the checkpoint is requested successfully. The line `Core.checkpointRestore()` represents the transition point from the preparation phase to checkpoint/restore. When the process is restored, execution continues after this call.

The main thread's stack can be visualized as follows:

```text
main(args)
  |
  +-- initializeApplication()
  |
  +-- warmUpApplication()
  |
  +-- Core.checkpointRestore()
        |
        +-- prepare and create checkpoint
        |
        +-- process is restored
        |
        +-- call completes in the restored thread
  |
  +-- verifyExternalResources()
  |
  +-- startServing()
```

The point to note is that after restore, the main thread continues at the `verifyExternalResources()` statement. It does not return to the first line of `main()`. Therefore, the logs `1. main entered`, `initialize application`, and `warm up application` are not printed again just because the process was restored.

From this perspective, the checkpoint call looks like a normal function call: the program calls the function, waits for it to complete, and then runs the next statement. The difference lies in the fact that the runtime saves the process state during that transition. The code after the call only continues when the process is restored and the call can return to the execution thread.

## 3. The continuation point does not necessarily lie inside `main()`

A checkpoint can be requested from an in-program API or by an external operational tool. When a checkpoint is requested externally, there is no specific `Core.checkpointRestore()` line to serve as a marker in the source code. The runtime saves the state of the threads at the time of the checkpoint according to the environment's mechanism. After restore, each thread continues from its own saved state.

For example, a server application might have the following threads:

```text
JVM process
├── main thread
│   └── SpringApplication.run(...) has returned
├── HTTP acceptor thread
│   └── waiting for new connections
├── request worker thread
│   └── processing or waiting for work
└── scheduler thread
    └── waiting for the next run
```

If the checkpoint is requested when `main()` has finished but the server's non-daemon threads keep the JVM alive, the stack frame of `main()` is no longer active. Restoring does not make `main()` run again. The threads still alive in the checkpoint continue from their saved state, and the application continues operating from those threads.

Conversely, if the checkpoint occurs while `main()` is still executing, the stack frame of `main()` is also part of the saved process state. After restore, the main thread continues at the saved execution position. For example, if `main()` is waiting for a task to complete, it continues from the restored waiting state according to the capabilities of the runtime and environment.

This helps distinguish three cases:

1. **Checkpoint at an API call inside `main()`:** after restore, the call completes and `main()` runs the next statement.
2. **External checkpoint while `main()` is still active:** `main()` continues from the saved stack state, not starting over from the beginning.
3. **Checkpoint after `main()` has returned:** `main()` remains finished; other living threads continue their work after restore.

If all non-daemon threads have finished and the JVM has exited, there is no longer a running process to take a checkpoint in the normal way. Therefore, a server application usually still has serving threads or background threads keeping the process alive after `main()` returns.

## 4. Example with the Spring Boot `main()` lifecycle

A Spring Boot application typically has a very short `main()` method:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(...)` creates and starts the Spring `ApplicationContext`, initializes beans, runs Spring Boot startup steps, and starts the web server if the application has web configuration. When the call returns, the statement in `main()` ends and the `main()` method can return. The web server threads continue keeping the JVM alive and handling requests.

If the application is checkpointed after the Spring context has started, the checkpoint can contain the context state, beans, caches, and existing threads according to CRaC's support capabilities. Upon restore, the Spring context is restored along with the process state. `SpringApplication.run(...)` is not called again just because restore occurred; beans are not recreated from scratch following the cold startup flow.

This also means that callbacks or events that only run during initial startup are not automatically replayed. For instance, one should not assume that `@PostConstruct`, `ApplicationRunner`, `CommandLineRunner`, or startup events will automatically run again after restore. If a component needs to reopen connections or refresh data after restore, integrate that responsibility with the CRaC resource lifecycle.

Some tasks often need to be divided as follows:

| Task | Appropriate timing |
|---|---|
| Creating Spring beans and internal structures | Initial startup, before checkpoint |
| Loading stable caches and warming up execution paths | Before checkpoint |
| Stopping request intake, draining in-flight requests | Preparing for checkpoint |
| Closing or putting connection pools/clients into a safe state | `beforeCheckpoint` according to the library's guidelines |
| Recreating connections, re-authenticating, or refreshing leases | `afterRestore` |
| Allowing the load balancer to send traffic | After restore and readiness checks complete |

The example above only describes the conceptual lifecycle. Actual integration needs to follow the CRaC support of the Spring Boot version, JDK, connection pool, JDBC driver, HTTP client, and libraries that the application uses.

## 5. Where do CRaC callbacks sit relative to `main()`'s continuation point?

CRaC provides the `Resource` interface so that resource-owning components can participate in two phases of the lifecycle:

- `beforeCheckpoint(...)` runs during checkpoint preparation. The resource can stop related activities, flush data, or close resources that need to be recreated.
- `afterRestore(...)` runs during recovery. The resource can reopen connections, refresh expired credentials, or restart paused components.

A concise example:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConnectionResource implements Resource {

    private RemoteConnection connection;

    public ConnectionResource() {
        connection = RemoteConnection.open();
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (connection != null) {
            connection.close();
            connection = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        connection = RemoteConnection.open();
    }

    public static void register() {
        Core.getGlobalContext().register(new ConnectionResource());
    }
}
```

`RemoteConnection` is an illustrative class. In a real application, you must use the API of the corresponding client/driver and coordinate with threads currently using the connection before closing it.

When a checkpoint is requested from `Core.checkpointRestore()`, registered resources participate in the checkpoint/restore process. After the process is restored and the related recovery steps complete, the calling thread continues after the API call point. Therefore, code after `Core.checkpointRestore()` can check resource states and continue the process of bringing the application into service.

You should not place post-restore connection-opening logic at the beginning of `main()` assuming that `main()` will run again. The beginning of `main()` only runs during initial startup. The `afterRestore` callback or an equivalent lifecycle mechanism is the appropriate place for resource recovery.

## 6. Checkpointing does not unwind the Java stack like a normal shutdown

Checkpointing is an operation that saves process state, not an application termination following the normal shutdown flow. When a process is checkpointed, stack frames and execution state are saved so they can continue upon restore. The program does not automatically step through the remaining statements in `try`, does not automatically unwind the stack, and does not run `finally` just because a checkpoint occurred.

Example:

```java
try {
    performWork();
    Core.checkpointRestore();
    continueWorkAfterRestore();
} finally {
    releaseResource();
}
```

`finally` is not a checkpoint callback. It runs when control flow leaves the `try` block according to normal Java rules, such as when the block completes or an exception occurs. The process being checkpointed is not equivalent to exiting the `try` block. If `releaseResource()` needs to run before checkpoint, handle it via `beforeCheckpoint` or an appropriate resource management mechanism. If the resource needs to be recreated, handle it after restore.

Similarly, you should not rely on shutdown hooks, `@PreDestroy`, or application-closing callbacks to prepare for checkpoint. Those mechanisms serve the application termination lifecycle. CRaC resource callbacks serve the checkpoint/restore state transition and must be designed specifically for it.

## 7. How to observe the continuation point in practice

To observe the lifecycle accurately, place logs at different milestones instead of only logging a generic message like “application started”. An example could use the following labels:

```java
public static void main(String[] args) throws Exception {
    log("MAIN_ENTERED");

    initialize();
    log("INITIALIZATION_COMPLETED");

    warmUp();
    log("WARMUP_COMPLETED");

    Core.checkpointRestore();
    log("MAIN_CONTINUED_AFTER_RESTORE");

    verifyConnections();
    log("DEPENDENCIES_READY");

    serve();
}
```

When reading logs, interpret them by execution point:

| Log marker | Meaning |
|---|---|
| `MAIN_ENTERED` | `main()` was called during initial startup |
| `INITIALIZATION_COMPLETED` | Pre-checkpoint initialization steps completed |
| `WARMUP_COMPLETED` | Warm-up completed |
| `MAIN_CONTINUED_AFTER_RESTORE` | The thread continued after the checkpoint/restore point in the example |
| `DEPENDENCIES_READY` | Required dependencies were verified after restore |

When restoring from a checkpoint created at the API call in the example, the markers `MAIN_ENTERED`, `INITIALIZATION_COMPLETED`, and `WARMUP_COMPLETED` are not printed again by that restore. The marker `MAIN_CONTINUED_AFTER_RESTORE` appears when the restored thread continues past the checkpoint call. If the checkpoint is requested externally, place logs in `Resource` callbacks and at key business-processing points to observe the recovery of each thread.

Logs need to distinguish between initial startup, checkpoint preparation, resource recovery, and readiness milestones. You can add a newly issued instance identifier after restore to differentiate restored instances. Avoid using an identifier generated before the checkpoint as a unique identifier for every restored copy.

## 8. One checkpoint can create multiple independent continuation points

In a deployment environment, a single checkpoint can be used as the source to launch multiple restored processes. Each process starts from the saved state and continues at the same execution point in the snapshot, but afterward operates as an independent process.

This has an important consequence: state inside the checkpoint can be cloned. If the snapshot contains an instance ID, a lease, a local counter, or scheduler state, multiple restored instances may start with the exact same value. If each restored instance continues executing a side effect such as sending a message, running a scheduled task, or writing data, the side effect can occur across multiple instances.

Therefore, post-restore code and the `afterRestore` callback need to consider operations that depend on instance identity or ownership:

- Generate or register a new instance identifier according to the deployment environment.
- Reacquire leases or leader election rights using an external coordination mechanism.
- Rejoin consumer groups and let the broker distribute partitions according to the current state.
- Start schedulers according to a policy of running on one or multiple instances.
- Ensure operations can be retried or have appropriate idempotency keys when repeated execution is possible.

You should not assume that a piece of post-checkpoint code only runs once system-wide. It can run once in each process restored from the same snapshot. Uniqueness must be guaranteed by a distributed system or an external allocation mechanism, and cannot rely solely on variables in the checkpointed heap.

## 9. Common misconceptions

### Thinking that restore calls `main()` again

This is the most common misconception. Restore recovers the saved process and resumes the threads. It does not relaunch the application from the beginning. Place post-restore work in resource callbacks or at the appropriate continuation point.

### Thinking that static initializers will run again

Static initializers already ran before the checkpoint and class state is saved in the checkpoint. Restore recovers that state. If a static value depends on an environment that has changed, refresh it explicitly after restore.

### Thinking that `@PostConstruct` and startup runners will run again

These callbacks belong to bean creation and context startup. If the context is restored from a checkpoint, they are not automatically re-executed as in a cold startup. Components that need to recover connections or resources should participate in the CRaC lifecycle.

### Thinking that `finally` or shutdown hooks will clean up resources

Checkpointing is not a normal stack unwind or shutdown operation. Use `beforeCheckpoint` to prepare resources and `afterRestore` to recover resources.

### Thinking that a log at the start of `main()` proves restore restarted the application

That log might only have appeared during initial startup. Add markers at the post-checkpoint continuation point, in recovery callbacks, and at readiness to observe the true sequence.

### Thinking that a post-checkpoint side effect only happens once

If multiple processes are restored from the same snapshot, each process can continue running the same code. Design distributed operations to be idempotent or use appropriate ownership/locking mechanisms.

## 10. How to reason when debugging a CRaC application

When a log appears multiple times or a piece of code seems not to run after restore, determine four pieces of information:

1. Was the checkpoint requested from an API inside the application or from an external tool?
2. Which threads were executing at the time of the checkpoint, and where were their stacks?
3. Was `main()` still active or had it already returned before the checkpoint?
4. After restore, which resource callbacks ran, and have readiness conditions been satisfied?

Then match the logs against the actual continuation point. For a checkpoint called in source code, check the statement immediately following the call. For an external checkpoint, check the stacks of the threads and where they continue. If `main()` has already finished, track the living server, worker, or scheduler threads instead of waiting for `main()` to appear again.

To verify behavior, you should observe at least two scenarios: a checkpoint called directly via `Core.checkpointRestore()` and a checkpoint requested externally while the application is running. Log before/after the call point, inside `beforeCheckpoint`, inside `afterRestore`, and at readiness. Also check external dependencies after restore to ensure that restored memory state is not mistaken for a still-valid connection state.

## 11. Conclusion

The execution continuation point is the key to understanding the `main()` lifecycle in CRaC. Cold startup calls `main()` to begin a new program; restore recovers the saved process and resumes threads from the checkpointed state. If the checkpoint occurs at `Core.checkpointRestore()`, the calling thread continues after that call when restore completes. If the checkpoint is requested externally, threads continue from their saved execution state. If `main()` has already returned, it remains in the finished state and other living threads continue their work.

When designing and debugging, clearly distinguish between initial startup code, checkpoint preparation callbacks, recovery callbacks, and post-continuation-point code. Components that need to reconnect, refresh leases, or generate new identifiers must handle them according to the CRaC lifecycle. Observing in this way helps avoid re-running initialization logic, missing resource recovery, and creating duplicate side effects when multiple processes are restored from the same checkpoint.
