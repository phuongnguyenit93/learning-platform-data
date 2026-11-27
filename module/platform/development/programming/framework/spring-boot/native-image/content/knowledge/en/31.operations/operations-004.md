# Graceful shutdown, shutdown hooks, and request completion timeouts

A Spring Boot service should not stop by terminating the process immediately upon receiving a stop command. When deploying a new version, scaling down, or replacing a Pod, the application needs to stop accepting new work, complete in-flight requests, stop consumers and schedulers, release connections, flush remaining data, and exit within the platform's allowed time window.

This process is called **graceful shutdown**. It is especially important for Spring Boot Native Image because containers typically launch the native executable directly. The binary must receive OS termination signals properly, Spring must close the `ApplicationContext`, the web server must drain requests, and background components must finish before the container runtime sends `SIGKILL`.

This lesson explains the relationship between Java shutdown hooks, GraalVM Native Image signal handlers, the Spring lifecycle, HTTP request drain times, Docker, and Kubernetes. You will configure graceful shutdown, manage background tasks, calculate a shutdown time budget, test with in-flight requests, and handle forced process termination cases.

## 1. What problem does graceful shutdown solve?

A service processing requests may simultaneously hold:

- In-flight HTTP requests and incomplete responses.
- Active database transactions or connections in use.
- Messages received from a broker but not yet acknowledged.
- Tasks running inside executors or schedulers.
- Files, sockets, locks, or JNI/native resources.
- Unflushed log, trace, and telemetry buffers.

If the process exits immediately, clients may receive connection resets or timeouts; transactions may roll back; unacknowledged messages may be redelivered; files may remain unflushed. Clients often retry, so a business operation can be submitted multiple times.

Graceful shutdown organizes termination into steps:

1. Receive the termination request signal.
2. Transition the application so it stops accepting new traffic/work.
3. Wait for in-flight requests and active work to finish within the allowed deadline.
4. Stop consumers, schedulers, and executors in dependency order.
5. Close connection pools, clients, files, and application resources.
6. Exit the process before the container runtime deadline.

The goal is to preserve accepted work and allow new requests to be routed to other instances. Graceful shutdown cannot guarantee every task finishes if it exceeds the deadline or the process receives `SIGKILL`.

## 2. Distinguishing shutdown hooks, signal handlers, and Spring lifecycle

These three mechanisms serve distinct roles:

| Mechanism | Role | Example |
|---|---|---|
| OS signal | Notifies the process that the OS or container wants it to stop | `SIGTERM`, `SIGINT` |
| Shutdown hook | Executes shutdown logic when the runtime starts the shutdown sequence | `Runtime.addShutdownHook` |
| Spring lifecycle | Stops the web server, beans, consumers, and releases resources in `ApplicationContext` | `SmartLifecycle`, `@PreDestroy`, `DisposableBean` |

Spring Boot automatically registers a shutdown hook with the runtime to close the `ApplicationContext` when the application exits. When the context closes, Spring lifecycle callbacks are invoked. Therefore, most applications only need to manage resources through the Spring bean lifecycle.

With Native Image, the OS signal must be translated into the runtime's shutdown sequence so shutdown hooks get a chance to run. Spring then closes the context and runs the corresponding callbacks.

Avoid registering multiple independent shutdown hooks to close the same resource. Hooks may execute concurrently with no guaranteed order, easily creating race conditions between custom hooks and the hook managed by Spring Boot.

## 3. How do Java shutdown hooks work?

On the JVM, an application can register a hook via `Runtime.getRuntime().addShutdownHook`. When the shutdown sequence starts, the runtime launches registered hooks. Execution order across hooks is unspecified and they may run concurrently.

Minimal example:

~~~java
Runtime.getRuntime().addShutdownHook(
    new Thread(() -> {
        System.out.println("Process is shutting down");
    }, "custom-shutdown-hook")
);
~~~

Shutdown hooks suit process-level operations outside the Spring lifecycle, such as an independent native component not managed by Spring. For datasources, message listeners, executors, or application beans, prefer Spring's shutdown mechanisms.

A hook should:

- Run quickly and enforce a time bound.
- Be safe if invoked idempotently when required by design.
- Avoid deadlocks and unbounded waits.
- Avoid blindly depending on another hook that may already be closing resources.
- Never call `System.exit` from inside a shutdown hook.
- Never assume `finally` blocks or callbacks will run if the process receives `SIGKILL`.

A hung shutdown hook can prevent the runtime from completing the shutdown sequence until the OS forcibly kills the process.

## 4. How does Native Image receive SIGTERM?

A native executable does not run inside HotSpot, so you should not assume all signal behavior is identical to the JVM. GraalVM Native Image includes an exit handler mechanism to handle termination signals and trigger shutdown hooks.

Depending on the GraalVM version:

- In older versions, you may need to build the executable with `--install-exit-handlers` to install signal/exit handlers.
- Starting with GraalVM 25, exit handlers are enabled by default for native executables; the `--install-exit-handlers` option is deprecated and can usually be omitted.
- Behavior for shared libraries differs from executables; Spring Boot applications deployed as processes are typically executables.

Check the exact GraalVM distribution and release notes in use. Do not blindly copy build arguments from an older version into every pipeline without verification.

You can inspect the toolchain on the build machine:

~~~bash
native-image --version
native-image --help
~~~

Cross-check the version and accepted builder options against GraalVM release notes. If building with Buildpacks, check the GraalVM version inside the builder image and build logs rather than only checking the JDK on the machine running Maven/Gradle.

When signal handlers are installed and the runtime receives `SIGTERM`, Native Image can start the shutdown sequence, run Spring Boot's hook, and close the context. If handlers are not active, default OS signal handling may terminate the process without running expected cleanup.

## 5. Distinguishing SIGTERM, SIGINT, and SIGKILL

| Signal | Common source | Can be handled gracefully? |
|---|---|---|
| `SIGTERM` | Docker stop, Kubernetes, or process supervisor | Yes, if supported by runtime and application |
| `SIGINT` | Ctrl+C in terminal | Yes, if runtime installs an appropriate handler |
| `SIGKILL` | Timeout expiration, forced kill, or OS | Cannot be caught or ignored |

`SIGTERM` requests that a process terminate, giving it a chance to close resources before exiting. `SIGKILL` terminates the process immediately at the OS level; no shutdown hook, `@PreDestroy`, or Spring lifecycle callback can intervene.

Consequently, graceful shutdown always needs a deadline. If work cannot complete within that window, business design must specify how retries, rollbacks, or redelivery behave.

## 6. SpringApplication closes ApplicationContext on exit

Every `SpringApplication` registers a shutdown hook to close the `ApplicationContext` when the runtime shuts down. Standard Spring callbacks can be used:

- `@PreDestroy` on beans.
- `DisposableBean.destroy()`.
- Destroy methods declared in bean definitions.
- `Lifecycle` and `SmartLifecycle` for components requiring ordered start/stop.
- `ContextClosedEvent` when reacting to context closure events.

Example of a bean logging and flushing a buffer when the context closes:

~~~java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class ExportBuffer {

    private final AtomicBoolean closed = new AtomicBoolean();

    @PreDestroy
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        flushPendingRecords();
    }

    private void flushPendingRecords() {
        // Flush remaining data using the application's API.
    }
}
~~~

This snippet illustrates the callback, not a universal flush mechanism for every library. In a real application, flushing must enforce a deadline, log errors, and handle already-closed states. If a resource is already managed by another Spring bean, do not close the same resource manually in multiple places.

Using `jakarta.annotation.PreDestroy` suits Spring Boot 3 and newer. Spring Boot 2 projects use `javax.annotation.PreDestroy` and its corresponding dependency.

Do not disable `SpringApplication`'s default shutdown hook if your application relies on it to close the context, unless you explicitly provide an alternative shutdown mechanism.

## 7. Enabling graceful shutdown for the web server

Spring Boot supports graceful shutdown for its integrated embedded web servers. When the context closes, the web server stops accepting new requests and gives in-flight requests a grace period to finish.

Explicit configuration in `application.yml`:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Or in `application.properties`:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Current Spring Boot 4.2 documentation notes that graceful shutdown is enabled by default for embedded Jetty, Reactor Netty, and Tomcat. You can set `server.shutdown=immediate` to disable it. Older Spring Boot versions required setting `server.shutdown=graceful` to enable it; verify against your project's exact version documentation.

`spring.lifecycle.timeout-per-shutdown-phase` configures the timeout per lifecycle phase. This is not necessarily the total shutdown time for the whole application if multiple sequential phases exist.

## 8. What happens to in-flight requests?

When graceful shutdown begins, the web server stops accepting new requests via its server-specific mechanism. Already-accepted requests are given a chance to complete within the grace period.

How new requests are rejected varies by server and version:

- Tomcat, Jetty, and Reactor Netty may stop accepting requests at the network layer.
- Some servers/versions may accept connections and return a rejection status such as `503 Service Unavailable`.
- Persistent connections, HTTP/2 streams, WebSockets, and asynchronous requests have their own lifecycles that must be tested.

Do not assume every client always receives the exact same status code once a server starts stopping. Client contracts should handle connection resets, timeouts, and retryable responses during rollouts.

Long requests need reasonable bounds. If a request can run for several minutes while the Pod is only granted 30 seconds to stop, the server cannot guarantee completion.

## 9. Stop order of SmartLifecycle beans

`SmartLifecycle` allows components to participate in the Spring lifecycle with ordering and stop callbacks.

Phase rules:

- Lower phases start first.
- On shutdown, higher phases stop first.
- Beans in the same phase may stop concurrently.
- `depends-on` relationships also affect order: dependent beans stop before the dependencies they require.

Spring Boot performs graceful shutdown of the web server in the earliest phase of the `SmartLifecycle` stop sequence. Subsequent phases then continue stopping via the lifecycle processor.

This is useful when a service has message consumers, workers, and datasources. For example, a consumer must stop receiving messages and finish active work before the connection pool it uses is closed.

Do not assign phases arbitrarily. Map dependencies clearly and identify which components must stay active while others are stopping.

## 10. Using SmartLifecycle for tasks requiring asynchronous stop

`SmartLifecycle.stop(Runnable callback)` allows a bean to perform asynchronous shutdown work. The bean must invoke the callback once stopping finishes; forgetting the callback forces the lifecycle processor to wait until the phase timeout expires.

Condensed example for a queue consumer:

~~~java
@Override
public void stop(Runnable callback) {
    running = false;
    consumer.pause();

    try {
        boolean drained = consumer.awaitInFlight(Duration.ofSeconds(10));
        if (!drained) {
            log.warn("Consumer drain timed out");
        }
    }
    finally {
        try {
            consumer.close();
        }
        finally {
            callback.run();
        }
    }
}
~~~

`consumer` here represents the broker adapter used by the application. A complete implementation must also provide `start()`, `stop()`, and `isRunning()` per the `SmartLifecycle` contract.

Invoke the callback only after the bean's shutdown work has finished or timed out cleanly. Never invoke the callback immediately upon starting shutdown while workers are still running, or Spring may proceed to close dependencies those workers still need.

## 11. Stopping executors and scheduled tasks

Application-created executors need an explicit shutdown policy. On stop, they must reject new tasks, wait for running tasks, and define how queued tasks are handled.

With `ThreadPoolTaskExecutor`, you can configure:

~~~java
@Bean
ThreadPoolTaskExecutor exportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);
    return executor;
}
~~~

`setWaitForTasksToCompleteOnShutdown(true)` tells the executor to wait for accepted tasks; `setAwaitTerminationSeconds` bounds the wait duration. Choose queue capacity and timeouts based on real workloads. If the queue can hold critical work, consider durable persistence instead of in-memory-only buffering.

For schedulers, prevent new schedules from firing during shutdown and wait for current tasks up to a limit. Never let an infinitely running scheduled task hold the process in a shutting-down state.

If using Spring Boot auto-configured executors, check the shutdown properties under `spring.task.execution` and `spring.task.scheduling` for your Boot version. Avoid creating manual executors without Spring bean lifecycle management.

## 12. Stopping message consumers without losing messages

With Kafka, RabbitMQ, JMS, or other brokers, shutdown must distinguish between received and unreceived messages.

A typical sequence:

1. Stop polling/consuming new messages.
2. Wait for in-flight messages to finish within the deadline.
3. Commit offsets or acknowledge successfully processed messages.
4. Let unfinished messages be redelivered according to broker mechanics.
5. Close consumers/channels/connections.

If the deadline expires, never acknowledge a message whose business work is incomplete. The broker can redeliver it; handlers must be idempotent so retries do not create duplicate side effects.

Do not rely solely on HTTP graceful shutdown. A service may have stopped accepting HTTP traffic while message consumers are still processing. Consumers must participate in the Spring lifecycle with their own drain budget.

## 13. Closing dependencies in a safe order

An application may need databases or HTTP clients kept open while final workers finish. Shutdown order must therefore reflect dependency relationships:

| Component | Required action |
|---|---|
| Web server | Stop accepting new requests, wait for in-flight requests |
| Message consumer | Stop receiving new messages, drain in-flight messages |
| Scheduler | Prevent scheduling new work |
| Executor | Wait for accepted tasks to finish or time out |
| Transaction manager | Let active transactions complete before closing datasource |
| Database connection pool | Close after workers/transactions no longer use it |
| HTTP client/broker connection | Close after requests/consumers finish |
| Telemetry/logging | Flush bounded buffers then close exporters/appenders |

Spring handles bean dependencies and destruction callbacks through the context lifecycle, but custom components must be registered and configured properly. If you manually manage a thread or native resource outside Spring, wrap it in a lifecycle bean to close it in order.

Never close a datasource inside an independent shutdown hook running in parallel with Spring. That can cause workers still writing data to fail because the connection pool was already closed.

## 14. Calculating the shutdown time budget

Container runtimes only wait a finite amount of time for a process. The total budget must account for all steps that actually occur:

\[
T_{\text{total}} =
T_{\text{preStop}} +
T_{\text{drain}} +
T_{\text{lifecycle}} +
T_{\text{cleanup}} +
T_{\text{margin}}
\]

Where:

- `T_preStop`: execution time of the `preStop` hook, if any.
- `T_drain`: time waiting for load balancers/routing to stop sending new traffic to the instance.
- `T_lifecycle`: time to stop Spring lifecycle phases; this covers the web server waiting for in-flight requests and stop callbacks for `SmartLifecycle`-managed workers/consumers.
- `T_cleanup`: closing connections, flushing buffers, and releasing resources in destruction callbacks such as `@PreDestroy`.
- `T_margin`: buffer for scheduling jitter, logging, and load variance.

The total time must be less than Kubernetes `terminationGracePeriodSeconds` or the container runtime stop timeout.

Note that `spring.lifecycle.timeout-per-shutdown-phase` is a timeout per phase, not a global shutdown total. Callbacks within the same phase may run concurrently; sequential phases can make total duration longer than a single timeout. In the formula, `T_drain`, `T_lifecycle`, and `T_cleanup` represent actual observed durations—do not double-count Spring's configured timeout on top of them. Measure wall-clock shutdown time and sum sequential steps plus margin.

For example, if one phase can take 20 seconds and the application still needs time to stop consumers, flush telemetry, and run `preStop`, do not set the entire Pod grace period to exactly 20 seconds.

## 15. How Docker sends stop signals to native executables

With Docker, `docker stop` sends a stop signal to the main process in the container. By default this is `SIGTERM`; after the specified wait time, the runtime sends `SIGKILL` if the process has not exited.

Example:

~~~bash
docker stop --time 45 orders-native
~~~

The container has up to 45 seconds to exit after receiving the stop signal.

Dockerfiles should use exec form:

~~~dockerfile
ENTRYPOINT ["/app/application"]
~~~

Exec form makes the native executable the main process so it receives signals directly. Using shell form like `ENTRYPOINT /app/application` can put a shell in the middle, making signal forwarding dependent on the shell/script.

If a startup script is unavoidable, end the script with `exec /app/application` to replace the shell with the application process. There is no need to add an init process if the container runs a single process without child-process management needs; if wrappers or child processes exist, pick an appropriate init and test signal forwarding.

## 16. How does Kubernetes Pod termination work?

When a Pod is deleted or replaced during a rollout, Kubernetes initiates the termination flow:

1. The Pod is marked `Terminating` and the grace-period countdown begins.
2. If configured, kubelet executes the `preStop` hook before sending the signal.
3. Once `preStop` finishes, the container runtime sends `SIGTERM` to the main process.
4. The application gets the remaining time for graceful shutdown.
5. When `terminationGracePeriodSeconds` expires, any process still running receives `SIGKILL`.

The default `terminationGracePeriodSeconds` is 30 seconds if unspecified. **`preStop` execution time counts inside the same grace period**—it is not added on top of it. If `preStop` takes 10 seconds out of a 30-second budget, the application only has roughly 20 seconds left after receiving `SIGTERM`.

During termination, Kubernetes also updates `EndpointSlice` so the terminating endpoint is no longer treated as ready for normal traffic. Propagating this change to load balancers and clients still takes time; the application must handle late-arriving requests during this transition window.

## 17. Kubernetes configuration for Spring Boot Native Image

Example Deployment with a 60-second grace period and readiness probe:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-native
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-native
  template:
    metadata:
      labels:
        app: orders-native
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: orders
          image: example/orders:native
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_SHUTDOWN
              value: graceful
            - name: SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE
              value: 20s
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Spring Boot environment variables use relaxed binding; the names in the example correspond to `server.shutdown` and `spring.lifecycle.timeout-per-shutdown-phase`. Ensure Actuator readiness/liveness endpoints are enabled and exposed per the application's security policy.

The values 60 seconds and 20 seconds are examples only. Calculate yours from the longest supported request, lifecycle phases, background tasks, and infrastructure propagation delays.

Do not add `preStop: sleep 10` merely to pad time without purpose. If an external load balancer needs draining, use an intentional hook and include its duration in the termination budget.

## 18. When to use the preStop option

`preStop` runs before the container receives `SIGTERM`. It is useful when notifying an external system outside Kubernetes or instructing a custom load balancer to stop sending traffic before the application closes.

A `preStop` hook can be an HTTP hook or an exec hook. Keep in mind:

- The termination grace period countdown already started before the hook runs.
- The hook must finish before `SIGTERM` is sent.
- If the hook hangs, the application has less time left to shut down.
- Distroless/tiny runtime images may lack a shell or `curl` for exec hooks.
- If the hook fails, termination can still end in a forced kill.

For most HTTP services, Kubernetes readiness probes and endpoint termination already form the foundation for traffic draining. Add `preStop` only when genuinely required by a load balancer, service mesh, or business workflow.

## 19. Checking signal handlers in GraalVM builds

For a native executable, check the GraalVM version and exit handler status before debugging Spring lifecycle behavior.

From GraalVM 25 onward, exit handlers are enabled by default for executables. For older versions, if the builder supports and requires explicit signal handling, you can add `--install-exit-handlers` to native build arguments.

Gradle Native Build Tools, example for older toolchains needing it enabled:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--install-exit-handlers")
        }
    }
}
~~~

Maven Native Build Tools:

~~~xml
<configuration>
    <buildArgs>
        <buildArg>--install-exit-handlers</buildArg>
    </buildArgs>
</configuration>
~~~

Use these snippets only when your project's GraalVM version requires the flag. On GraalVM 25+, the option is deprecated and exit handlers for executables are enabled by default; omitting the old argument avoids unnecessary warnings. Check the documentation/release notes and native build logs of your exact distribution.

If building with Cloud Native Buildpacks, verify the GraalVM version used by the buildpack and the native build arguments actually passed to the builder. Do not infer this from the JDK on a developer machine if the builder image uses a different toolchain.

## 20. Testing graceful shutdown with in-flight requests

A good test must prove a request actually started before the stop signal was sent.

You can create a test-environment-only endpoint, such as `GET /test/slow?seconds=15`, which waits in a controlled manner before returning a response.

Procedure:

1. Start the native container.
2. Send a request to the slow endpoint in the background.
3. Wait for logs confirming the request was received and started processing.
4. Run `docker stop --time 45`.
5. Confirm the in-flight request receives a complete response.
6. Confirm the container exits before the deadline.
7. Check logs showing graceful shutdown and cleanup callbacks ran.

Example commands:

~~~bash
curl --fail --silent \
  http://127.0.0.1:8080/test/slow?seconds=15 \
  > slow-response.txt &
REQUEST_PID=$!

# Wait for log/test signal confirming the request has started.
docker stop --time 45 orders-native

wait "$REQUEST_PID"
cat slow-response.txt
~~~

This snippet is a skeleton; synchronize the wait step with a log line or test barrier to guarantee the request entered the server before stopping. Do not rely on a short `sleep` and assume the request started.

Expected observations:

- The in-flight request completes before timeout.
- New requests are no longer accepted as normal traffic once the server begins draining.
- Shutdown logs appear in a logical order.
- Executors, consumers, and datasources close according to lifecycle order.
- The process exits before the runtime is forced to send `SIGKILL`.

## 21. Testing timeout exceedance scenarios

You must also test cases where requests or background tasks exceed the shutdown budget.

Examples:

- A test request runs for 60 seconds while the Spring lifecycle phase waits only 20 seconds.
- A consumer is processing a large message and cannot drain within the deadline.
- A shutdown callback hangs or forgets to invoke its callback.
- `preStop` consumes almost the entire grace period.

Confirm the system behaves predictably:

- In-flight requests may be severed when the deadline expires.
- Clients enforce timeouts and retry per policy.
- Unacknowledged messages are redelivered by the broker.
- Open transactions roll back when the connection/process closes.
- No assumptions are made that `@PreDestroy` will run if the process receives `SIGKILL`.

Never increase timeouts indefinitely to mask a hung task. Bound processing durations, persist work state durably, and design for retries/idempotency.

## 22. Testing shutdown on Kubernetes

In a Kubernetes environment:

1. Deploy at least two replicas so traffic has somewhere to shift.
2. Send a long request and confirm it has started.
3. Perform a controlled rollout or delete one Pod.
4. Watch the Pod transition to `Terminating`.
5. Observe readiness/`EndpointSlice` and application logs.
6. Confirm the in-flight request finishes within the grace period.
7. Confirm the Pod terminates without hitting forced timeout.

Useful observation commands:

~~~bash
kubectl get pods -w
kubectl describe pod orders-native-xxxxx
kubectl logs orders-native-xxxxx
kubectl get endpointslices
~~~

If the Pod belongs to a Deployment, the controller will spin up a replacement replica. During testing, distinguish logs of the terminating old Pod from the newly created Pod.

Test both rolling updates and scale-downs, since traffic rerouting timing and remaining replica counts differ. Never run these tests against production workloads without a controlled impact plan.

## 23. Observing and diagnosing shutdown

Logs are the first piece of evidence showing when shutdown started and where it stopped. Spring Boot may log messages like:

~~~text
Commencing graceful shutdown. Waiting for active requests to complete
Graceful shutdown complete
~~~

Exact logger names and wording depend on the web server and Spring Boot version.

Record:

- Timestamp when `SIGTERM` was received and context closure began.
- Timestamp when the web server stopped accepting new requests.
- In-flight request count and drain duration.
- Messages being processed by consumers and acknowledgment outcomes.
- Remaining executor tasks and wait duration.
- Time taken to close datasources, brokers, HTTP clients, and telemetry.
- Timeout reasons or cleanup errors.
- Exit code and process exit timestamp.

You can add metrics such as in-flight requests, pending tasks, active consumer messages, and shutdown duration. Never log tokens, sensitive payloads, or credentials inside shutdown callbacks.

If a container exits via `SIGKILL`, final cleanup logs are usually absent. Cross-check Pod events, container exit reasons, grace period, and the timestamp of the last log line.

## 24. Common issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Native process exits immediately on `SIGTERM` | Exit handler/signal handling incompatible with GraalVM version | Check release, build output, and exit handlers |
| `@PreDestroy` does not run | Context never closed or process received `SIGKILL` | Check signals, `SpringApplication` shutdown hook, and container deadline |
| In-flight request gets cut off | Grace period shorter than request duration or server shutdown timeout | Measure request duration and increase budget appropriately |
| Pod gets `SIGKILL` after `preStop` | `preStop` consumed most of the grace period | Account for `preStop` inside `terminationGracePeriodSeconds` |
| Message processed twice | Process stopped before ack/commit or client retried | Use idempotency and ack after successful processing |
| Executor fails to finish | Task is blocked or executor does not await with a bound | Configure await termination and task timeouts |
| Shutdown callback never finishes | `SmartLifecycle.stop(Runnable)` forgot to invoke callback | Call callback along all controlled exit paths |
| Database closes while workers still run | Incorrect lifecycle/dependency order | Order phases and bean dependencies |
| Container never receives `SIGTERM` | Shell is PID 1 or does not forward signals | Use exec-form `ENTRYPOINT` or `exec` in scripts |
| Application takes too long to stop | Many lifecycle phases, hooks, or unbounded task waits | Measure each phase and set explicit deadlines |
| Missing final logs | `SIGKILL`, crash, or log exporter closed too early | Check runtime events, stdout/stderr, and exit reason |

## 25. Principles for safe shutdown design

- Use Spring Boot's default shutdown hook to close the context.
- Verify exit handlers/signal handling for your GraalVM version.
- Prefer `@PreDestroy` for synchronous, short, bounded cleanup.
- Use `SmartLifecycle` for consumers/workers requiring asynchronous or ordered shutdown.
- Stop accepting new work before draining active work.
- Close dependencies after the components using them have stopped.
- Set timeouts for requests, executors, consumers, and each lifecycle phase.
- Include `preStop` inside the Kubernetes grace period.
- Use an exec-form entrypoint so the native executable receives signals directly.
- Test both in-flight requests and tasks exceeding the timeout.
- Use idempotency, retries, and durable queues to handle interrupted work.
- Never rely on shutdown hooks to guarantee data safety against `SIGKILL` or power loss.

## 26. Takeaways

Graceful shutdown is a coordinated workflow across OS signals, the Native Image runtime, Spring Boot's shutdown hook, the web server, lifecycle beans, and the container orchestrator. Native executables can still run shutdown hooks and the Spring lifecycle, provided signals are handled and the process has enough time before forced termination.

Spring Boot closes the `ApplicationContext` when the shutdown hook runs. The web server can stop accepting new requests and wait for in-flight requests during the grace period; `SmartLifecycle`, `@PreDestroy`, and executor lifecycles stop workers and release dependencies in order. Kubernetes sends `SIGTERM` after `preStop` and sends `SIGKILL` when `terminationGracePeriodSeconds` expires.

Design your shutdown budget around the longest supported request, background tasks, lifecycle phases, orchestrator hooks, and safety margin. Test on the actual native executable/container, not just callbacks on the JVM. **A safe shutdown must finish before the platform deadline and have a retry/idempotency strategy for work that cannot complete.**

### References

- Spring Boot — Graceful Shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Spring Boot — SpringApplication, Application Exit: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework — SmartLifecycle Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- GraalVM — Native Image Compatibility Guide: https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/
- GraalVM — JDK 25 Release Notes: https://www.graalvm.org/release-notes/JDK_25/
- Java SE — Runtime and Shutdown Hooks: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html
- Kubernetes — Termination of Pods: https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/
- Kubernetes — Container Lifecycle Hooks: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

Graceful shutdown, signal handling, and lifecycle timeouts depend on Spring Boot, Spring Framework, GraalVM, and container runtime versions. Pin your toolchain and test the exact binary and deployment environment your project ships.
