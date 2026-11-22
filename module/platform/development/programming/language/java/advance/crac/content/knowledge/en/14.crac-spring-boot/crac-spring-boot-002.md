# Relationship Between Lifecycle, SmartLifecycle, and CRaC Callbacks

In a Spring Boot application, many components need to be started and stopped according to the lifecycle of `ApplicationContext`: message listeners, schedulers, consumers, connection managers, and background workers. Spring provides `Lifecycle` and `SmartLifecycle` to coordinate these components when the context is started, stopped, refreshed, or closed. CRaC, meanwhile, provides a different lifecycle at the process level: the `beforeCheckpoint` callback prepares resources before saving the state image, while `afterRestore` restores resources when the process is restored.

The two mechanisms can work together yet are not identical. Spring manages bean active state and start/stop ordering within the context. CRaC manages the timing of process checkpoint/restore. A bean having been created or an `ApplicationContext` having published `ApplicationReadyEvent` does not mean the application is ready for a checkpoint. Similarly, a successful restore does not mean every `SmartLifecycle` has automatically restarted or every dependency is ready.

A proper design usually uses a CRaC `Resource` as the coordination point, and then delegates stopping/starting components to Spring's `LifecycleProcessor` or to specific component lifecycles. You must understand the behavior of the Spring Boot version in use because some versions provide built-in CRaC support; avoid registering an extra coordinator that duplicates the framework's automatic mechanism.

## 1. Three Lifecycles to Distinguish

A Spring Boot application has at least three related event/lifecycle groups:

| Mechanism | Scope | Typical events/callbacks | Purpose |
| --- | --- | --- | --- |
| Spring Bean lifecycle | A bean inside the container | Constructor, dependency injection, `@PostConstruct`, `InitializingBean`, `@PreDestroy`, `DisposableBean` | Initialize and release objects/beans. |
| Spring Context lifecycle | Beans participating alongside `ApplicationContext` | `Lifecycle.start()`, `Lifecycle.stop()`, `SmartLifecycle`, `LifecycleProcessor.onRefresh()`, `LifecycleProcessor.onClose()` | Start/stop services, workers, and context-managed resources. |
| CRaC process lifecycle | JVM process being checkpointed/restored | `Resource.beforeCheckpoint(...)`, `Resource.afterRestore(...)` | Prepare process state before checkpoint and recover after restore. |

Do not substitute a callback from one lifecycle for another lifecycle. For example, `@PreDestroy` serves bean destruction; it is not a checkpoint callback. `ContextClosedEvent` fires when the Spring context closes; a CRaC checkpoint does not by default close `ApplicationContext`. `afterRestore` is a CRaC callback; it does not automatically re-run constructors or `@PostConstruct` on beans already existing in the heap.

## 2. Spring Bean Lifecycle Is Not CRaC Lifecycle

When Spring creates a bean, the container typically executes the following sequence of steps:

```text
Create instance
    |
    v
Inject dependencies
    |
    v
BeanPostProcessor before initialization
    |
    v
@PostConstruct / afterPropertiesSet / init-method
    |
    v
BeanPostProcessor after initialization
    |
    v
Bean ready in ApplicationContext
```

When the context closes, Spring can invoke bean destruction callbacks:

```text
ApplicationContext close
        |
        v
LifecycleProcessor stops Lifecycle beans
        |
        v
ContextClosedEvent
        |
        v
@PreDestroy / DisposableBean.destroy / destroy-method
        |
        v
BeanFactory is closed
```

Exact ordering details can depend on the context type and framework version, yet the key point to remember is that bean destruction callbacks are tied to the bean/context actually being closed.

In a normal CRaC checkpoint, the goal is preserving `ApplicationContext` and beans to continue using them after restore. Therefore:

- `@PostConstruct` does not automatically run again after restore.
- Constructors and dependency injection are not executed again merely because the process was restored.
- `@PreDestroy` does not automatically run merely because CRaC prepares for a checkpoint.
- Do not call `applicationContext.close()` inside `beforeCheckpoint` if the goal is restoring the same checkpointed context; closing enters the bean-destruction and context-shutdown path.
- Resources that must be closed/reopened across a checkpoint should have their own lifecycle or be coordinated via `Lifecycle`/`SmartLifecycle` and CRaC `Resource`.

If a bean holds a socket, scheduler, or connection pool, the fact that the bean object still exists after restore does not prove the underlying resource still works. Separate object lifecycle from the lifecycle of the resources that the object manages.

## 3. `Lifecycle`: Starting and Stopping with the Spring Context

`org.springframework.context.Lifecycle` is a simple contract for components that can be started and stopped:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

A bean implementing `Lifecycle` can manage a worker or listener:

```java
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public final class BackgroundWorker implements Lifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }
        startWorkerThread();
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        requestWorkerStop();
        awaitWorkerWithTimeout();
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    private void startWorkerThread() { /* application-specific */ }
    private void requestWorkerStop() { /* application-specific */ }
    private void awaitWorkerWithTimeout() { /* bounded wait */ }
}
```

`Lifecycle` only describes start/stop; it does not define complex dependency ordering, auto-start, or asynchronous completion callbacks. Those capabilities are extended by `SmartLifecycle`.

Start/stop calls from `ApplicationContext` are coordinated through `LifecycleProcessor`. Normally, the application does not need to manually find each bean and call `start()`/`stop()` if Spring already manages them in the context.

## 4. `SmartLifecycle`: Auto-Startup, Phases, and Asynchronous Stopping

`SmartLifecycle` extends `Lifecycle` with important capabilities:

- `isAutoStartup()` decides whether the bean starts automatically upon context refresh.
- `getPhase()` determines relative start/stop ordering among components.
- `stop(Runnable callback)` allows a component to notify Spring when an asynchronous stop operation has completed.

An illustrative skeleton:

```java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class MessageConsumerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (!running) {
            startConsumer();
            running = true;
        }
    }

    @Override
    public void stop() {
        stopConsumerWithTimeout();
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        stopConsumerWithTimeout();
        running = false;
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    private void startConsumer() { /* application-specific */ }
    private void stopConsumerWithTimeout() { /* bounded drain and stop */ }
}
```

The example above only illustrates the API. If `stopConsumerWithTimeout()` fails, the callback must not be invoked as though the consumer stopped successfully. Log the error and let the lifecycle coordinator detect that stopping failed to meet requirements; depending on the implementation, an exception may be propagated or the operation may time out per Spring's policy. With asynchronous implementations, invoke the callback only after stopping has truly finished.

### Phases Control Ordering

Spring uses phases to coordinate `SmartLifecycle` beans:

- Components with lower phase values start first.
- When stopping, the order reverses: higher phase values stop first.
- Components with the same phase can be processed in the same group; do not rely on bean registration order as a dependency contract.

Example service depending on a database pool:

```text
Startup (ascending phase)

DatabasePoolLifecycle       phase 10  -> starts first
MessageConsumerLifecycle    phase 20  -> starts next
RequestSchedulerLifecycle   phase 30  -> starts last

Shutdown/checkpoint stop (descending phase)

RequestSchedulerLifecycle   phase 30  -> stops first
MessageConsumerLifecycle    phase 20  -> stops next
DatabasePoolLifecycle       phase 10  -> stops last
```

As a result, the scheduler stops generating new work before the consumer; the consumer finishes in-flight work before the database pool closes. Choose phases based on actual application dependencies. Do not use phases as a substitute for draining requests or transactions.

## 5. `LifecycleProcessor` and `ApplicationContext`

`LifecycleProcessor` is the component coordinating beans that implement `Lifecycle`. `ConfigurableApplicationContext` provides `getLifecycleProcessor()` to access the context's processor.

Two relevant methods:

| Method | Meaning |
| --- | --- |
| `onRefresh()` | Notifies that the context was refreshed so the lifecycle processor starts components needing auto-start per Spring rules. |
| `onClose()` | Notifies the context close phase so the lifecycle processor stops running components in phase order. |

Important point: calling `LifecycleProcessor.onClose()` directly only coordinates stopping lifecycle components; it is not equivalent to calling `ApplicationContext.close()` and is not a command to destroy the entire bean factory. However, the name `onClose()` was designed for the context's close phase, so when using it in CRaC you need a coordinator that clearly owns stopping/starting and must verify behavior with the Spring version in use.

If an application calls `onClose()` in `beforeCheckpoint`, after restore it can call `onRefresh()` to restart components configured for auto-start. `SmartLifecycle` beans with `isAutoStartup() == false` will not start automatically just because `onRefresh()` was called; they must be controlled under their own policy. For beans implementing only `Lifecycle`, check how the context/processor manages their state and do not assume every component restarts automatically.

Do not call `applicationContext.close()` and expect `onRefresh()` to reopen the same context. Upon an actual close, the bean factory and singletons may already have been destroyed; that is a different lifecycle from stop/start for checkpointing.

## 6. CRaC `Resource`: Process-Level Lifecycle

CRaC provides `org.crac.Resource` with two main callbacks:

```java
public interface Resource {
    void beforeCheckpoint(Context<? extends Resource> context) throws Exception;
    void afterRestore(Context<? extends Resource> context) throws Exception;
}
```

`beforeCheckpoint` is invoked during checkpoint preparation. This is when the application stops new work, drains workers/transactions, and closes or prepares resources that cannot persist across a checkpoint.

`afterRestore` is invoked when the process is restored. This is when endpoints/credentials are refreshed, connection pools are recreated, stopped components are started, and readiness is verified.

`Resource` does not replace `Lifecycle` or `SmartLifecycle`. It provides a hook into the CRaC cycle for the application to coordinate the appropriate lifecycle components. If every component registers its own separate Resource while also being managed by Spring's LifecycleProcessor, the same worker could be stopped twice or started in an unintended order.

A clean model:

```text
CRaC Resource coordinator
        |
        +--> Spring LifecycleProcessor
        |        |
        |        +--> Scheduler SmartLifecycle
        |        +--> Message consumer SmartLifecycle
        |        +--> Database pool Lifecycle
        |
        +--> Refresh credentials/configuration
        +--> Validate dependencies
        +--> Publish readiness
```

In this model, CRaC controls the timeline; Spring manages the start/stop order of beans; the application manages refreshing and readiness.

## 7. Coordinating Spring Lifecycle from a CRaC Resource

If the current Spring Boot version and dependencies do not provide automatic CRaC integration for the application's lifecycle, you can create a singleton bean implementing `Resource` to coordinate the context.

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.crac.Core;
import org.crac.Context;
import org.crac.Resource;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.LifecycleProcessor;
import org.springframework.stereotype.Component;

@Component
public final class SpringLifecycleCracResource implements Resource {
    private final ConfigurableApplicationContext applicationContext;
    private boolean registered;

    public SpringLifecycleCracResource(
            ConfigurableApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
        registered = true;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        LifecycleProcessor processor = applicationContext.getLifecycleProcessor();
        processor.onClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        LifecycleProcessor processor = applicationContext.getLifecycleProcessor();
        processor.onRefresh();
    }

    @PreDestroy
    public void unregister() {
        if (registered) {
            Core.getGlobalContext().unregister(this);
            registered = false;
        }
    }
}
```

This is a basic coordination example, not a configuration usable verbatim for every application. Consider the following points:

- `SpringLifecycleCracResource` must be a singleton bean kept alive throughout the lifecycle requiring checkpointing; `ApplicationContext` holds the bean and the bean holds the context.
- Register the Resource exactly once. If the Spring Boot version in use already registers lifecycle integration automatically, do not add a duplicate coordinator.
- `onClose()` coordinates stopping Lifecycle beans; do not call `applicationContext.close()`.
- `onRefresh()` starts components per Spring semantics; check beans that have `isAutoStartup() == false`.
- Readiness must be handled separately. `onRefresh()` returning does not prove databases, brokers, or external dependencies are healthy.
- Stop/start operations must have timeouts. With `SmartLifecycle.stop(Runnable)`, the component must invoke the callback only when genuinely stopped.
- If `beforeCheckpoint` fails after some components have already stopped, the coordinator must have appropriate rollback/restart logic.
- Do not rely on `afterRestore` as a rollback callback for an aborted checkpoint. If the checkpoint does not complete and the original process continues, the application needs its own recovery path per runtime semantics.

`@PreDestroy` in the example only unregisters the Resource when Spring genuinely destroys the bean. It is not called in place of `beforeCheckpoint`.

## 8. When Should You Control Individual SmartLifecycles Instead of the Whole Context?

Calling `LifecycleProcessor.onClose()` has broad scope: it can stop many lifecycle beans in the context. This is suitable when all those components must stop before checkpoint and are allowed to restart automatically after restore.

If only certain resources need closing/reopening, you can have a CRaC Resource invoke a specialized coordinator instead of stopping the entire context:

```java
public final class MessagingCracResource implements Resource {
    private final MessageConsumerLifecycle consumer;

    public MessagingCracResource(MessageConsumerLifecycle consumer) {
        this.consumer = consumer;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        consumer.stop();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        consumer.start();
    }
}
```

This example is only suitable when the component has synchronous, idempotent, and timed stop/start APIs. If a component implements `SmartLifecycle` and is already controlled by `LifecycleProcessor`, do not call `stop()` directly in the Resource at the same time the processor also stops it. Choose a single coordinating owner.

You can create a dedicated `CheckpointCoordinator` to coordinate a group of beans in business order: stop schedulers, drain consumers, flush outboxes, close database pools; after restore, refresh credentials, create pools, start consumers, and then start schedulers. The coordinator should invoke public component APIs or Spring's LifecycleProcessor rather than directly calling `beforeCheckpoint`/`afterRestore` callbacks of another Resource.

## 9. Readiness and Traffic in the Checkpoint–Restore Cycle

Spring lifecycle state and readiness to accept traffic are two different concepts. A bean having `isRunning() == true` does not necessarily mean the database is connected or the message broker is ready. Similarly, a refreshed context does not necessarily mean every external dependency has been verified.

In Spring Boot, the Availability API can be used to transition readiness state:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;

public final class ReadinessController {
    private final ConfigurableApplicationContext context;

    public ReadinessController(ConfigurableApplicationContext context) {
        this.context = context;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

A sound order:

**Before checkpoint**

1. Publish `REFUSING_TRAFFIC` so load balancers/orchestrators stop sending new requests.
2. Stop schedulers/consumers generating additional work.
3. Drain running requests, messages, and transactions.
4. Stop lifecycle components by phase.
5. Close/release connection pools and resources that must be recreated.
6. Allow CRaC to proceed only once application state is safe.

**After restore**

1. Keep readiness at `REFUSING_TRAFFIC`.
2. Refresh credentials, DNS, config, and secrets if they can change.
3. Recreate connection pools/clients and validate dependencies.
4. Start lifecycle components in phase order.
5. Verify health checks and consumer/scheduler state.
6. Publish `ACCEPTING_TRAFFIC` after all mandatory components are ready.

Do not publish `ACCEPTING_TRAFFIC` right at the start of `afterRestore` merely to signal the process is alive. Readiness must reflect actual ability to serve requests.

## 10. Spring Boot Events Do Not Replace CRaC Callbacks

Some Spring Boot events are commonly used to observe application state:

| Event | When published | Automatically re-published after CRaC restore? |
| --- | --- | --- |
| `ContextRefreshedEvent` | When ApplicationContext is refreshed | Not merely because the process restored. |
| `ApplicationReadyEvent` | When Spring Boot completes startup and is ready to serve per the startup flow | Does not automatically re-publish like a fresh boot. |
| `ContextClosedEvent` | When ApplicationContext closes | Does not automatically fire merely due to CRaC checkpoint. |
| `AvailabilityChangeEvent` | When the application changes availability/readiness state | Fires only when published by the application or framework. |
| CRaC `beforeCheckpoint` | When CRaC prepares to checkpoint | This is a CRaC callback, not a Spring application event. |
| CRaC `afterRestore` | When CRaC restores the process | This is a CRaC callback, not a Spring startup event. |

If resource refresh logic is attached solely to `ApplicationReadyEvent`, it may not run after restore. Put recovery logic in a CRaC Resource or a lifecycle coordinator invoked explicitly in `afterRestore`.

Similarly, do not use `ContextClosedEvent` to simulate a checkpoint without actually closing the context. Publishing an event manually also does not automatically execute all stopping, draining, and resource cleanup steps.

## 11. Phase Ordering and CRaC Resource Ordering Are Two Different Things

`SmartLifecycle.getPhase()` controls start/stop ordering when Spring's LifecycleProcessor runs. It does not control the callback order of multiple `org.crac.Resource` instances registered with a CRaC `Context`.

If an application registers individual beans separately as CRaC Resources, do not assume callback order will match SmartLifecycle phases. This can create races: the database pool closes before consumers finish draining, or consumers start before credential refresh completes.

When business ordering is required, use a single coordinator or an explicit coordination sequence:

```text
beforeCheckpoint
    |
    v
Refuse traffic
    |
    v
Stop scheduler
    |
    v
Drain consumer and requests
    |
    v
Finish/rollback transactions
    |
    v
Close database and network clients
    |
    v
Checkpoint

afterRestore
    |
    v
Refresh secrets and endpoints
    |
    v
Create database/network clients
    |
    v
Start consumers
    |
    v
Start schedulers
    |
    v
Validate health and accept traffic
```

In each step, clearly define timeouts, failure behavior, and rollback. Never let Resource A's callback directly invoke Resource B's callback; invoke application-level lifecycle APIs to avoid duplicate callbacks or breaking ownership.

## 12. Timeouts When Spring Stops SmartLifecycle

A `SmartLifecycle` can stop asynchronously. When Spring's LifecycleProcessor waits for the callback to finish, a stuck consumer or non-draining worker can slow down or stall the checkpoint process.

Spring Boot provides the configuration property `spring.lifecycle.timeout-per-shutdown-phase` to limit the wait time per phase when the lifecycle processor stops components. Choose a value appropriate for drain times and operational requirements. This is a per-phase Spring timeout; it does not automatically bound every network call, database query, or CRaC dump operation.

Principles:

- `stop(Runnable)` must invoke the callback when the component has truly finished stopping.
- Do not wait indefinitely on `Future.get()`, `Thread.join()`, or `CountDownLatch.await()` inside stop logic.
- Configure separate timeouts for HTTP, database, broker, and I/O; per-phase timeout does not replace client timeouts.
- If a component does not stop within the deadline, do not report false success. Let the coordinator know checkpoint preparation is unsafe.
- Do not hold application locks while waiting for workers or making network calls.
- Log duration, phase, component name, and active task count during stop.

## 13. Handling Failures and Aborted Checkpoints

Suppose `beforeCheckpoint` called `LifecycleProcessor.onClose()` and stopped all workers. If a subsequent preparation step fails, the original process may need to resume serving traffic. The application must have a plan to return components to a safe operating state or keep readiness at `REFUSING_TRAFFIC`.

Do not use `afterRestore` as a rollback callback for an aborted checkpoint. `afterRestore` belongs to the restore flow; a checkpoint failure does not mean a new restore occurred. Handle errors right inside the coordinator when possible, and understand specific runtime semantics when a dump operation fails after preparation callbacks have completed.

A usable state machine:

```text
RUNNING
   |
   v
REFUSING_TRAFFIC
   |
   v
QUIESCING
   |
   v
STOPPING_LIFECYCLE
   |
   +---- preparation error ----> ROLLING_BACK
   |                                  |
   |                                  v
   |                           RUNNING or NOT_READY
   |
   v
READY_FOR_CHECKPOINT
   |
   v
CHECKPOINT
   |
   v
RESTORE
   |
   v
RECONNECTING
   |
   v
STARTING_LIFECYCLE
   |
   v
READY
```

Rollback must know which components stopped and which did not. `SmartLifecycle.start()` should be idempotent or the coordinator should track state so components are not started twice. If full recovery is impossible, keep readiness refusing traffic and report failure to orchestration.

## 14. Does Spring Boot Have Built-In CRaC Integration?

Integration capability depends on Spring Boot version, Spring Framework version, CRaC JDK, and classpath dependencies. Some Spring Boot versions have built-in CRaC support to coordinate the application lifecycle. Before writing a custom `Resource` yourself, check the documentation for the exact version and confirm which steps the framework performs automatically.

Decision workflow:

1. Confirm actual Spring Boot and Spring Framework versions.
2. Confirm the CRaC dependency (`org.crac`) and supported JDK runtime.
3. Read the CRaC documentation for the exact Boot version to learn which lifecycle components stop/start automatically.
4. Check whether there is auto-configuration or a framework-registered Resource.
5. Add custom Resources only for application parts not yet managed by the framework.
6. Avoid calling `LifecycleProcessor.onClose()` again if the framework already performs the equivalent.
7. Test callback logs to confirm each component stops/starts only the right number of times.

Do not infer that merely adding `org.crac:crac` causes every custom resource to be handled automatically. The framework may support lifecycle beans yet cannot understand how to close a custom client, refresh secrets, or verify application business logic.

## 15. Common Mistakes

| Symptom | Likely cause | How to handle |
| --- | --- | --- |
| `@PreDestroy` does not run at checkpoint | Checkpoint does not close ApplicationContext and does not destroy beans | Use `Resource.beforeCheckpoint` or Lifecycle stop for resources needing preparation. |
| `@PostConstruct` does not run after restore | Bean already exists in the image; restore does not recreate beans | Put resource recovery into `afterRestore` or a lifecycle coordinator. |
| Consumer stops twice | Both Boot CRaC integration and a custom Resource call the processor | Designate a single lifecycle owner and remove duplicate coordination. |
| Consumer does not restart | `isAutoStartup()` is false or coordinator only calls `onRefresh()` | Start the component per its own policy or configure autoStartup appropriately. |
| Database pool starts before consumers finish draining | Relied on Resource callback order instead of Spring phases/coordinator | Use phases or an explicit coordination sequence. |
| Checkpoint hangs while stopping | `stop(Runnable)` fails to invoke callback or tasks lack timeouts | Add bounded waits, cancellation, and stop-duration logging. |
| Application accepts traffic too early after restore | Readiness is enabled immediately when process lives or when start is called | Publish `ACCEPTING_TRAFFIC` only after dependencies and health checks pass. |
| Context stops working after restore | `ApplicationContext.close()` was called before checkpoint | Do not close the context; stop only needed lifecycle/resources. |
| Checkpoint aborted yet workers stay stopped | No rollback for completed preparation | Coordinator tracks component state and safely restarts/resumes. |
| Spring event handler does not run after restore | Logic attached only to `ApplicationReadyEvent` or `ContextRefreshedEvent` | Invoke recovery logic explicitly from CRaC callbacks. |

## 16. Testing the Relationship Between Spring Lifecycle and CRaC

Testing should verify both callback order and the application's operational state.

### Testing Spring Lifecycle Independently

1. Initialize `ApplicationContext`.
2. Verify auto-start `SmartLifecycle` beans start in phase order.
3. Send stop via the lifecycle processor and verify reverse stop order.
4. Verify `stop(Runnable)` signals completion only after the component truly stops.
5. Check that `isAutoStartup() == false` does not start unintentionally.

### Testing Integrated CRaC

1. Start the application on a compatible CRaC JDK.
2. Confirm readiness is `ACCEPTING_TRAFFIC` and lifecycle components are active.
3. Request a checkpoint.
4. Confirm readiness transitions to `REFUSING_TRAFFIC`, schedulers stop, consumers drain, and pools close in the right sequence.
5. Restore from the checkpoint.
6. Confirm resources are refreshed, pools are recreated, and lifecycle components start exactly once.
7. Confirm readiness transitions to `ACCEPTING_TRAFFIC` only after health checks.
8. Send test requests and messages to confirm the application truly works.

### Failure Testing

- Consumer fails to drain before timeout.
- `SmartLifecycle.stop(Runnable)` fails to call the callback.
- One component stops successfully while the next component fails.
- Credentials or database are not ready after restore.
- Checkpoint is aborted after lifecycle components have already stopped.
- Repeated restores or a component receives a start request while already running.
- Boot integration and custom Resource are both present, to detect duplicate stop/start.

Unit tests for phases and state machines are useful, yet you need actual checkpoint/restore tests on the target CRaC JDK and environment. Merely calling `beforeCheckpoint()`/`afterRestore()` directly does not prove the runtime can create or restore the process image.

## 17. Design Checklist

- [ ] Distinguish bean initialization/destruction, Spring context lifecycle, and CRaC process lifecycle.
- [ ] Do not use `@PreDestroy` as a checkpoint callback.
- [ ] Do not use `@PostConstruct` as a restore callback.
- [ ] Do not call `ApplicationContext.close()` if the same context must continue being used after restore.
- [ ] Each lifecycle component has one clear start/stop owner.
- [ ] Use `SmartLifecycle` phases to express start/stop dependencies.
- [ ] `stop(Runnable)` signals completion only after the component truly stops.
- [ ] Have timeouts for each phase and for each I/O/database/broker operation.
- [ ] Confirm whether the Boot version has built-in CRaC integration before registering custom Resources.
- [ ] Avoid registering two coordinators that both stop/start one component.
- [ ] Use CRaC Resources to coordinate pre-checkpoint and post-restore steps.
- [ ] Refresh credentials, endpoints, and configuration that can change across checkpoint duration.
- [ ] Have rollback when preparation fails or checkpoint is aborted per runtime semantics.
- [ ] Readiness refuses traffic during quiescing/reconnecting.
- [ ] Accept traffic only after lifecycle components and dependencies are ready.
- [ ] Test ordering, timeouts, stop/start failures, and actual checkpoint/restore.

## 18. Conclusion

Spring Bean lifecycle manages bean creation and destruction; `Lifecycle`/`SmartLifecycle` manages starting and stopping components within `ApplicationContext`; CRaC `Resource` manages when to prepare for checkpoint and recover after restore. These mechanisms complement each other yet do not automatically replace one another.

Let Spring's LifecycleProcessor coordinate beans by phase, use CRaC Resources as the process-level integration point, and manage readiness separately so traffic is not accepted while resources are unready. Confirm built-in CRaC support for your exact Spring Boot version before registering a custom coordinator. With a clear division of responsibilities, the application can stop workers, drain transactions, close resources before checkpoint, and restart in the right order after restore without closing/destroying ApplicationContext.