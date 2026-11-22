# Determining Checkpoint Timing Using Application Readiness Signals

In CRaC (Coordinated Restore at Checkpoint), the timing of creating a checkpoint directly affects the quality of the saved image. If a checkpoint is taken too early, the image may contain an application that has not finished initializing, has not loaded configuration, has not connected to dependencies, or has not completed warm-up. If a checkpoint is taken too late, the application may already be receiving requests, processing transactions, or running background tasks that are difficult to bring to a consistent state.

A reliable way to choose the timing is to use an **application readiness signal**. The application itself determines when the required conditions have been met, publishes that state to the controller, and then the controller requests CRaC to create the checkpoint.

A readiness signal does not create the checkpoint by itself. It is a contract between the application and the orchestration component: the application indicates that its current state satisfies the conditions to begin the checkpoint process; CRaC then runs the resource preparation callbacks before the image is actually created.

## 1. Why Is a Readiness Signal Needed?

A Java process can open an HTTP port very early during startup. That does not mean the application is ready to serve business logic. After the port opens, the application may still be:

- Loading and validating configuration.
- Initializing the dependency injection container and beans.
- Connecting to databases, message brokers, caches, or external services.
- Loading metadata, schemas, models, or reference data.
- Creating thread pools, schedulers, and connection pools.
- Running warm-up to load classes, JIT-compile hot code, or initialize caches.
- Registering consumers, listeners, and internal callbacks.

If a checkpoint is created as soon as the process appears or the port starts listening, the image may be created while some of the steps above are still incomplete. Upon restore, the application may continue from an intermediate state or have to re-run steps that were not executed.

Conversely, if you wait until the application receives traffic before checkpointing, the image may contain in-flight requests, open transactions, messages being consumed, or workers modifying data. These activities make bringing the application to a safe state more complex.

A readiness signal helps define an intentional transition point: the application has initialized enough components, completed the necessary warm-up, and can enter the checkpoint preparation process.

## 2. Distinguishing Readiness States

In service operations, the concepts of startup, readiness, and liveness serve different purposes. They should not be used interchangeably.

| State or signal | Meaning | Use for checkpoint decision? |
|---|---|---|
| Process started | The JVM is running and has a PID | Not sufficient; the application may not be initialized yet |
| Port open | The server has bound and is listening on a port | Not sufficient; dependencies or warm-up may not be complete |
| Startup complete | Main startup steps have finished | A useful condition, but does not prove all dependencies are ready |
| Readiness | The application can currently receive and process traffic per the operational contract | Useful, but traffic-serving readiness does not equate to a safe state for checkpointing |
| Liveness | The process is still alive and not stuck according to check criteria | Do not use as a checkpoint signal |
| Checkpoint-ready | Specific conditions to start the checkpoint process are satisfied | This is the appropriate signal for the controller to consider sending a checkpoint request |
| Quiesced | The application has stopped accepting new work and finished processing in-flight work | A condition close to image creation time, usually established in pre-checkpoint callbacks |

### 2.1 Startup probe

A startup probe tells the orchestration system whether the application has completed its startup phase according to configured criteria. In Kubernetes, this probe helps prevent liveness or readiness probes from evaluating the application too early when startup time is long.

Startup complete is a useful milestone, but the application may still need to check databases, populate caches, or run warm-up after that point. Therefore, a succeeding startup probe should not be assumed to mean checkpoint-ready.

### 2.2 Readiness probe

A readiness probe answers the question: can the application receive traffic at the current moment? When readiness fails, the orchestration platform typically stops sending new traffic to that instance.

Readiness usually reflects the ability to serve requests, whereas checkpoint-ready reflects the ability to start the image creation process. The two states are related but not identical.

For example, an application may have completed warm-up and met the conditions to create a checkpoint, yet not want to receive traffic because it is creating an image used to launch other instances. In this case, checkpoint-ready can be true while traffic-serving readiness remains false.

Conversely, an instance serving traffic normally may have readiness as true but not yet be checkpoint-ready because there are still long-running requests, unacknowledged messages, or a dependency undergoing a state change.

### 2.3 Liveness probe

A liveness probe answers the question: is the process still functioning properly according to check criteria, or has it entered a state requiring a restart? An application may not be ready to serve yet still be alive; for example, it is waiting for a database to start.

A checkpoint should not be triggered just because liveness succeeds. Liveness does not indicate whether the application has finished warm-up, whether dependencies are ready, or whether in-flight work has been drained.

## 3. Building Checkpoint-Ready Conditions

The application needs to clearly define which conditions must be satisfied before emitting the checkpoint-ready signal. A composite condition typically includes the following groups.

### 3.1 Application initialization complete

Mandatory startup steps must be completed:

- Configuration has been loaded and validated.
- Core components have been created.
- Required beans, services, and listeners have been initialized.
- One-time initialization tasks have completed.
- No mandatory startup step is still running in the background whose result the checkpoint image needs to contain.

You should not rely solely on the event that the JVM is running or the HTTP server has bound a port. Choose a lifecycle milestone that reflects the actual state of the application.

### 3.2 Essential dependencies ready

Check dependencies that the application needs immediately after restore, such as:

- Databases can be connected to and authenticated.
- Message brokers are reachable.
- Caches or reference data stores have been loaded.
- Configuration services, secrets, and certificates are accessible.
- Required internal endpoints respond properly.

Not every optional dependency must be operational to checkpoint. Classify dependencies into essential and non-essential. Checkpoint-ready conditions should reflect the components needed for the application to start and serve its functionality properly after restore.

If a dependency only temporarily loses connection, the application can keep checkpoint-ready as false and retry under a bounded policy. Avoid emitting true simply because an old check once succeeded.

### 3.3 Warm-up complete

Warm-up may include:

- Loading initial caches.
- Loading models or metadata.
- Running initialization queries.
- Initializing serializers, parsers, templates, or schemas.
- Running representative operations to warm up the JIT and critical execution paths.

It is not necessary to run every possible workload before checkpointing. Choose warm-up steps that add value when the image is restored: they must reduce startup time or help the instance become ready faster without introducing transient data or unsafe state into the image.

Some warm-up tasks may need to re-run after restore if they depend on time, host, network addresses, or remote service state. Do not assume all caches remain valid just because the cache objects are retained in the heap.

### 3.4 CRaC resources registered and preparable

Resource-managing components need to be initialized and have their lifecycle registered with CRaC before a checkpoint is requested.

For example:

- Files and channels can be closed before checkpoint and reopened after restore.
- Connection pools can be stopped and recreated.
- Network connection clients can reconnect after restore.
- Schedulers and consumers can pause/resume in the proper order.

A checkpoint-ready signal can verify that these components have registered callbacks and can enter the preparation process. However, successful registration does not guarantee that the callbacks will complete successfully. The actual checkpoint attempt must still handle errors in callbacks.

### 3.5 No incomplete mandatory initialization work

Before allowing a checkpoint, you need to know which tasks must complete before taking the snapshot. For example:

- Schema migrations or checks.
- Mandatory background data loading.
- Creating initial accounts or configuration.
- Registering consumers with a broker.
- Creating resources with side effects in external services.

If a task is not yet complete, you can wait for it, cancel it safely, or save enough state to resume after restore. The decision must be based on the task's semantics; a one-time task should not unintentionally re-run after every restore.

## 4. State Model and Signal Timing

The lifecycle should be represented with explicit states rather than a single boolean. A simple model might include:

| State | Meaning |
|---|---|
| STARTING | The JVM and application are starting up |
| INITIALIZING | Initializing dependencies and components |
| WARMING | Running warm-up |
| CHECKPOINT_READY | Conditions for the controller to request a checkpoint are satisfied |
| QUIESCING | Stopping acceptance of new work and draining in-flight work |
| CHECKPOINTED | Checkpoint has been created successfully |
| RESTORING | The process has just restored and is rebuilding resources |
| SERVING | The application is ready to serve traffic |
| FAILED | An error prevents the application from continuing in the current lifecycle |

A general flow:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> INITIALIZING
    INITIALIZING --> WARMING
    WARMING --> CHECKPOINT_READY
    CHECKPOINT_READY --> QUIESCING: Controller requests checkpoint
    QUIESCING --> CHECKPOINTED: Preparation callbacks succeed
    QUIESCING --> FAILED: Drain or resource close fails
    CHECKPOINTED --> RESTORING: Restore image
    RESTORING --> SERVING: Recreate resources and checks complete
    RESTORING --> FAILED: Cannot restore dependencies
    SERVING --> QUIESCING: Checkpoint running instance
    SERVING --> FAILED: Unrecoverable error
~~~

The CHECKPOINT_READY milestone should appear after the application completes startup, essential dependencies, and warm-up. The QUIESCING milestone should only appear once a checkpoint request has been made and the application begins stopping work. Separating these two states lets the controller know whether the application is eligible to start or is actually ready for the moment of image creation.

The CHECKPOINTED state should only be published after the checkpoint engine confirms the operation succeeded. Do not change the state to succeeded as soon as the checkpoint command is sent.

## 5. Coordination Architecture Between Application and Controller

A design typically has three components:

1. **Java application:** tracks startup, dependencies, warm-up, and checkpoint-ready conditions.
2. **Endpoint or status channel:** exposes the state to the controller, which can be an internal health endpoint, management API, or event.
3. **Checkpoint controller:** checks the signal, applies policy, and sends the checkpoint request via the mechanism provided by the CRaC runtime.

Operational flow:

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant Signal as Readiness Endpoint
    participant Controller as Checkpoint Controller
    participant CRaC as CRaC Runtime

    App->>App: Initialize configuration and dependencies
    App->>App: Run warm-up
    App->>Signal: Publish CHECKPOINT_READY
    Controller->>Signal: Read status
    Signal-->>Controller: Ready + conditions satisfied
    Controller->>CRaC: Send checkpoint request
    CRaC->>App: beforeCheckpoint callbacks
    App->>App: Stop accepting work, drain, and close resources
    App-->>CRaC: Callbacks complete
    CRaC-->>Controller: Checkpoint result
    Note over App,CRaC: Checkpoint image is created when preparation succeeds
~~~

The endpoint can return status information in JSON format:

~~~json
{
  "checkpointReady": true,
  "phase": "CHECKPOINT_READY",
  "conditions": {
    "startupComplete": true,
    "dependenciesReady": true,
    "warmupComplete": true,
    "resourcesRegistered": true
  },
  "reason": null
}
~~~

This is an example of an application-defined status contract, not a mandatory CRaC schema. You can add an update timestamp, application version, or startup ID so the controller can detect stale data.

Management endpoints should have restricted access permissions. Reading status may only require internal permissions, while sending a checkpoint request requires dedicated control permissions. Do not leave a public endpoint that allows any client to request a checkpoint.

## 6. Integrating with the Java Application Lifecycle

The checkpoint-ready signal should be emitted from the actual lifecycle of the application. Multiple events and conditions can be combined instead of tying it to a single callback.

### 6.1 Using startup events

In Spring Boot, ApplicationReadyEvent indicates that the application has completed Spring's startup phase and runners have been executed. This is a good milestone to start evaluating checkpoint-ready.

However, this event does not by itself guarantee that business caches have finished warming up or that all remote dependencies are operational. If the application has asynchronous initialization steps, wait for them to complete before emitting the signal.

Example:

~~~java
@Component
public final class CheckpointReadiness {

    private final AtomicBoolean startupComplete = new AtomicBoolean();
    private final AtomicBoolean dependenciesReady = new AtomicBoolean();
    private final AtomicBoolean warmupComplete = new AtomicBoolean();

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        startupComplete.set(true);
        publishIfReady();
    }

    public void onDependenciesReady() {
        dependenciesReady.set(true);
        publishIfReady();
    }

    public void onWarmupComplete() {
        warmupComplete.set(true);
        publishIfReady();
    }

    private void publishIfReady() {
        boolean ready = startupComplete.get()
                && dependenciesReady.get()
                && warmupComplete.get();

        if (ready) {
            // Publish CHECKPOINT_READY via a health indicator,
            // internal endpoint, or application event.
        }
    }
}
~~~

This is an illustrative example of combining conditions. In a real application, you also need to handle cases where a dependency loses connection after once being ready, warm-up fails, and multiple tasks complete concurrently. A readiness condition should be able to transition back to false when the underlying state changes.

### 6.2 Using a dedicated health indicator

You can create a dedicated health indicator, such as checkpoint readiness, for the controller to read via a management endpoint. This health indicator should reflect specific conditions:

- Startup has completed.
- Essential dependencies are operational.
- Mandatory warm-up has finished.
- Resource lifecycles are registered.
- No unhandled initialization errors exist.

If using Spring Boot Actuator, you can maintain the standard readiness state for traffic and a separate health group for checkpointing. This prevents changing the checkpoint state from accidentally altering traffic routing in unintended ways.

### 6.3 Using internal events

For applications without a health endpoint, the signal can be emitted via an internal event bus or a state interface accessed by an in-process controller. The important thing is that the signal has clear semantics and is only emitted after all mandatory conditions are complete.

Do not use a simple static variable without synchronization if multiple threads update conditions. Use atomic state, locks, or a state machine with atomic state transitions.

## 7. Distinguishing Pre-Traffic Checkpointing from Running-Instance Checkpointing

There are two common operational scenarios. They use readiness differently.

### 7.1 Creating a checkpoint after warm-up but before receiving traffic

This approach is suitable when you want to create a base image to launch multiple pre-initialized instances.

Sequence:

1. The JVM starts.
2. The application loads configuration and initializes dependencies.
3. Warm-up completes.
4. The application publishes CHECKPOINT_READY.
5. The controller requests CRaC to create the checkpoint.
6. After the checkpoint succeeds, the image is used to restore instances according to the deployment strategy.
7. The restored instance re-checks required dependencies and only then transitions to traffic-serving readiness.

In this model, traffic-serving readiness can remain false before checkpointing. That helps avoid receiving requests on the source instance while creating the image.

Note that a checkpoint image may be restored in a different environment. Information tied to host, IP, DNS, credentials, or external files needs to be re-verified after restore.

### 7.2 Creating a checkpoint from an instance serving traffic

If checkpointing an instance that is already receiving requests, a normal readiness signal is not enough. The controller must coordinate with the application to stop accepting new work and bring in-flight activities to a safe state.

A typical sequence:

1. The controller selects an eligible instance and requests to start checkpointing.
2. The application switches traffic-serving readiness to false.
3. The application closes the gate for accepting new work internally.
4. Wait for in-flight requests to complete within a time limit.
5. Pause consumers and schedulers; complete or roll back transactions according to rules.
6. CRaC Resource callbacks flush and close resources.
7. The checkpoint engine creates the image.
8. After restore, the application recreates resources and verifies dependencies.
9. The application only switches readiness to true once fully recovered.

Setting readiness to false in step 2 helps load balancers or service routing stop sending new traffic, but routing updates may not be instantaneous. Therefore, the application still needs an internal request gate and draining mechanism. Do not rely solely on a fixed wait time after changing readiness.

## 8. Role of Resource Callbacks

The checkpoint-ready signal determines when the controller can initiate a checkpoint request. CRaC's Resource interface manages the work that needs to be done around checkpoint and restore time.

Two important callbacks:

- **beforeCheckpoint(Context):** runs before the checkpoint is created. The application stops accepting new work, drains in-flight work, flushes data, and closes resources that need to be recreated.
- **afterRestore(Context):** runs after the process is restored. The application reopens resources, reconnects dependencies, and prepares the serving state.

Sketch example:

~~~java
import java.time.Duration;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApplicationCheckpointResource implements Resource {

    private final RequestGate requestGate;
    private final ManagedResources resources;
    private final ReadinessState readiness;

    public ApplicationCheckpointResource(
            RequestGate requestGate,
            ManagedResources resources,
            ReadinessState readiness) {
        this.requestGate = requestGate;
        this.resources = resources;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.markNotReady();
        requestGate.stopAcceptingNewWork();

        if (!requestGate.awaitDrained(Duration.ofSeconds(30))) {
            throw new IllegalStateException(
                    "Timed out while draining in-flight work");
        }

        resources.flushAndClose();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        resources.reopenAndValidate();
        requestGate.allowNewWork();
        readiness.markReady();
    }
}
~~~

The RequestGate, ManagedResources, and ReadinessState types here are application-built abstractions, not built-in CRaC classes. The example illustrates the relationship between the readiness signal and callbacks; the specific close/open order must follow the application's dependencies.

If draining or closing resources fails, the callback should throw an exception so the checkpoint is rejected. Do not ignore errors and allow an image to be created from an unsafe state.

In the afterRestore callback, if essential resources cannot be reopened, the application needs to keep readiness as false and report an error. Only transition to ready after mandatory dependencies have been verified.

## 9. Avoiding Stale Signals and Race Conditions

Readiness is a state that changes over time. The controller needs to avoid using a stale signal to request a checkpoint when the application has already transitioned to another state.

### 9.1 The signal must reflect the current state

Suppose the application publishes checkpoint-ready after warm-up. Immediately afterward, the database loses connection or a background task starts a migration. If the endpoint still returns true, the controller may request a checkpoint while the application is no longer eligible.

When an essential dependency changes state, the application needs to update checkpoint readiness accordingly. You can also publish the reason for not being ready so the controller can explain why checkpointing cannot proceed yet.

### 9.2 Atomic state transitions

When there are multiple threads or multiple controllers, two checkpoint requests might arrive nearly simultaneously. Only one request should be allowed to transition the application from CHECKPOINT_READY to QUIESCING.

Use a state machine with atomic transitions, locks, or a lease mechanism to ensure:

- Only one checkpoint request is processed at a time.
- An instance does not accept additional requests after starting to quiesce.
- The controller does not use a readiness result from an old startup.
- Duplicate requests do not close resources twice in a way that causes errors.

A status response can include a generation ID or startup ID so the controller can verify the signal belongs to the right instance and current lifecycle.

### 9.3 Do not use fixed sleeps instead of signals

A simple approach is to wait a period of time after the process starts and then send the checkpoint command. This approach is error-prone because startup time varies with load, host speed, dependency status, and cache state.

If startup takes 20 seconds on one machine but 90 seconds on another, a fixed sleep may checkpoint too early or waste time. Let the application emit a signal when conditions are genuinely complete; the controller can poll with bounded intervals or receive events.

### 9.4 Use timeouts and clear error states

The controller should not wait indefinitely. Set timeouts for:

- Startup.
- Dependency checks.
- Warm-up.
- Waiting for checkpoint-ready.
- Request draining.
- Resource closing.
- Resource recovery after restore.

On timeout, record the failing condition clearly and decide whether to retry, skip the instance, or stop the workflow. Do not transition to checkpoint-ready just to prevent the workflow from hanging.

## 10. Endpoint Design and Checking Policies

A checkpoint readiness endpoint should answer two questions: is the application eligible to start checkpointing, and if not, which condition is blocking it?

Example response when not ready:

~~~json
{
  "checkpointReady": false,
  "phase": "WARMING",
  "conditions": {
    "startupComplete": true,
    "dependenciesReady": true,
    "warmupComplete": false,
    "resourcesRegistered": true
  },
  "reason": "initial-cache-loading"
}
~~~

The controller can apply policies:

- Only request a checkpoint when checkpointReady is true.
- Check status from the exact instance, do not use cached results from another instance.
- Require the signal to be stable for a short period if dependencies frequently flap.
- Limit the number of attempts and wait time.
- Log the reason for rejection or failure.
- Confirm the checkpoint is complete before marking the image ready for use.

If using polling, the endpoint should be lightweight, not creating new connections or running new warm-up each time it is called. The health check should only read state already updated by the application.

For multi-instance systems, the controller needs to track each instance's state individually. One checkpoint-ready instance does not mean all instances in the deployment are ready.

## 11. Observability and Diagnostics

To operate reliably, record the timing and outcome of each phase.

Useful logs or metrics:

- Time from process start to startup complete.
- Dependency initialization time.
- Warm-up duration.
- When checkpoint-ready is turned on and off.
- Number of in-flight requests when quiescing begins.
- Drain duration and number of timed-out requests.
- Resource flush/close duration.
- Checkpoint outcome and failure cause.
- Duration of afterRestore, reconnect, and dependency checks.
- When traffic-serving readiness is turned back on.

Attach instance ID, startup generation, and checkpoint ID to logs to correlate pre-checkpoint events with post-restore events. This helps distinguish errors from a new startup from state inherited from an old image.

If checkpoint-ready never turns on, check which condition has not completed. If readiness flips between true and false continuously, check whether a dependency is flapping or health check logic is overly sensitive. If beforeCheckpoint callbacks fail, check for undrained requests, unclosed resources, or flush errors. If afterRestore fails, check dependency reachability and environment changes.

## 12. Testing Checkpoint Timing

Do not test only the fast, successful startup case. Test edge states:

1. **Slow-starting dependencies:** the application must not emit checkpoint-ready before essential dependencies are ready.
2. **Warm-up failure:** readiness must remain false and provide a reason.
3. **Dependency disconnects after being ready:** checkpoint-ready must be revoked if that dependency is a mandatory condition.
4. **Readiness changes while the controller is polling:** the controller must read the new state and not use the stale signal.
5. **Long-running requests when checkpoint starts:** the application must drain or reject the checkpoint according to the configured timeout.
6. **Two concurrent checkpoint requests:** only one request is allowed to enter QUIESCING.
7. **Resource-closing callback fails:** the checkpoint must not report success.
8. **Restore when dependencies are not ready:** traffic-serving readiness must remain false.
9. **Restore on a different host:** verify DNS, IP, mounts, certificates, credentials, and external files.
10. **Post-restore warm-up:** re-run only the parts truly needed and avoid repeating non-idempotent side effects.

Test both models: checkpointing after warm-up before traffic and checkpointing from a serving instance. The two models have different draining and readiness requirements.

## 13. Common Mistakes

### Using port open as the checkpoint trigger

The server having bound a port does not prove the application has completed startup or that dependencies are ready. Use a signal that reflects lifecycle and business conditions.

### Using liveness instead of readiness

Liveness only indicates that the process is alive according to check criteria. It does not prove the application is ready to serve or create a checkpoint.

### Using traffic-serving readiness as checkpoint-ready

Readiness being true may only mean the instance can receive requests. It does not guarantee there are no in-flight requests, open transactions, or consumers processing messages. Have dedicated checkpoint conditions.

### Relying solely on ApplicationReadyEvent

The framework's startup event is a useful milestone, but asynchronous warm-up or dependency checks may still be running. All mandatory conditions must be combined.

### Setting readiness to false and immediately checkpointing

Load balancers and service routing may need time to update. The application still needs to block new work internally and drain in-flight work.

### Marking checkpoint as succeeded as soon as the command is sent

The controller must wait for the actual result from the CRaC runtime or checkpoint engine. Sending the command successfully does not mean the image was created successfully.

### Keeping readiness true when restore is not complete

Java objects may have been restored, but sockets, pools, or external dependencies are not ready yet. Only publish readiness after callbacks and necessary verification steps complete.

### Using fixed sleeps

Startup time is inconsistent across environments. Condition-based signals are easier to operate and less dependent on machine configuration.

## 14. Recommended Implementation Process

When integrating readiness signals into a Java application using CRaC, you can follow this sequence:

**Step 1 — Define the checkpoint goal.** Clarify whether the image is created after warm-up before traffic or from a serving instance. This determines whether traffic draining and changing serving readiness are needed.

**Step 2 — List checkpoint-ready conditions.** Identify startup, dependencies, warm-up, resource registration, and mandatory tasks that must complete.

**Step 3 — Build lifecycle states.** Separate CHECKPOINT_READY from traffic-serving readiness, QUIESCING, and CHECKPOINTED. Define state transition conditions clearly.

**Step 4 — Publish the signal.** Create a health endpoint or internal event so the controller can read the current state and the reason for not being ready.

**Step 5 — Connect the controller to CRaC.** The controller only sends a checkpoint request when the state is valid, for the right instance, and still fresh. The command-sending mechanism depends on the CRaC JDK and checkpoint engine in use.

**Step 6 — Implement Resource callbacks.** Stop accepting work, drain, flush, and close resources in beforeCheckpoint; recreate resources and verify dependencies in afterRestore.

**Step 7 — Handle errors and timeouts.** Define behavior when warm-up, draining, checkpointing, or restore fails. Do not report ready if essential conditions are not met.

**Step 8 — Test and observe.** Test edge states, measure the duration of each phase, and store checkpoint IDs for tracing.

A good design makes the checkpoint decision explainable: the controller knows which conditions the application has satisfied, why that moment is appropriate, and whether the checkpoint outcome succeeded.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and the coordination role with the application.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): registering Resources and implementing pre-checkpoint and post-restore callbacks.
- [CRaC — Debugging](https://crac.org/reference/debugging/): diagnosing errors during checkpointing.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): lifecycle milestones and application events.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposing application health and status.
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): meaning and usage of probes in Kubernetes.
