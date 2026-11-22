# Testing the Initialization Phase with `spring.context.exit=onRefresh`

When preparing a Spring Boot application for CRaC, you need to know exactly which tasks have completed at the moment the checkpoint is taken. An important question is: can beans be initialized without running lifecycle components yet? Spring Framework provides a test mode for this: setting the JVM system property `spring.context.exit=onRefresh`.

When the property is enabled, Spring runs ApplicationContext initialization up to the `LifecycleProcessor.onRefresh` phase, then terminates the JVM right at that point. Non-lazy singletons have been created and initialization callbacks such as `InitializingBean.afterPropertiesSet()` have executed; lifecycle beans have not yet been automatically started and `ContextRefreshedEvent` has not yet been published. This mode lets you observe whether bean creation inadvertently connects to a database, calls an HTTP service, or requires remote dependencies before the application starts running.

This is an initialization phase test. It does not create a checkpoint, does not restore a process, and does not require a CRaC-enabled JDK, the `org.crac:crac` library, or Linux. When you need to test an actual checkpoint at the same phase, Spring Framework has a separate property: `spring.context.checkpoint=onRefresh`.

## 1. What Is `spring.context.exit=onRefresh`?

`spring.context.exit` is a Spring Framework property read by `DefaultLifecycleProcessor` during initialization. The recognized value is `onRefresh` (case-insensitive). When `LifecycleProcessor.onRefresh()` is invoked during ApplicationContext refresh, the default implementation checks this property and terminates the JVM at that phase.

This feature was added in Spring Framework 6.1. With Spring Boot, check the actual Spring Framework version in the dependency graph; Spring Boot releases using Spring Framework 6.1 or later can use this feature while still using the default `DefaultLifecycleProcessor`. Do not look only at the Spring Boot name and overlook the resolved Framework version or whether the application replaced the lifecycle processor.

This property is designed to test the initialization process before lifecycle beans begin running. For example, a bean might construct an HTTP client in its constructor or `@PostConstruct`, while opening actual connections only needs to happen when the worker starts. Running the application with `spring.context.exit=onRefresh` helps detect such premature connections.

## 2. Where Does Spring Stop in the Startup Lifecycle?

Spring refreshes the ApplicationContext through multiple phases. For this test, it is important to distinguish bean initialization from starting lifecycle beans.

```mermaid
flowchart TD
    A[Spring Boot starts up] --> B[Read configuration and create ApplicationContext]
    B --> C[Register bean definitions and create non-lazy singletons]
    C --> D[Run constructors, dependency injection, and init callbacks]
    D --> E[LifecycleProcessor.onRefresh]
    E --> F{spring.context.exit=onRefresh?}
    F -->|Yes| G[Runtime.halt(0): terminate JVM]
    F -->|No| H[Start Lifecycle / SmartLifecycle beans]
    H --> I[Publish ContextRefreshedEvent]
    I --> J[Spring Boot continues with runners and ready event]
```

When `spring.context.exit=onRefresh` is enabled, the JVM exits inside `LifecycleProcessor.onRefresh`. Tasks completed before this point include:

- The ApplicationContext has been created and refreshed up to the lifecycle processor phase.
- Non-lazy singletons have been initialized.
- Constructors, dependency injection, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and corresponding init callbacks have run for created beans.
- Synchronous dependencies invoked during bean initialization have had a chance to execute.

Tasks that have not yet occurred include:

- `Lifecycle`/`SmartLifecycle` beans have not yet been automatically started by `DefaultLifecycleProcessor`.
- `ContextRefreshedEvent` has not yet been published.
- Post-refresh Spring Boot steps such as running `ApplicationRunner` and `CommandLineRunner` have not yet occurred.
- `ApplicationReadyEvent` has not yet been published.
- The web server lifecycle has not yet started to accept requests. Some server objects may have been created during refresh, yet the lifecycle start phase has not run.

A lazy-init bean is only initialized if another dependency requests it. Therefore, the test result reflects the beans actually initialized at this phase, and does not prove that every bean in the application has been created.

## 3. How to Enable the Property

Pass the property as a JVM system property right when launching the application:

```bash
java -Dspring.context.exit=onRefresh -jar application.jar
```

On Windows PowerShell, the equivalent invocation is:

```powershell
java "-Dspring.context.exit=onRefresh" -jar .\application.jar
```

If running with Docker, place the JVM argument before `-jar`:

```dockerfile
ENTRYPOINT ["java", "-Dspring.context.exit=onRefresh", "-jar", "/app/application.jar"]
```

If the application is launched through a build plugin such as `bootRun` or `spring-boot:run`, configure the JVM arguments of the application process. Do not confuse JVM arguments with parameters passed to the `main` method or with program arguments.

### 3.1. Why use `-D` instead of `application.properties`?

`DefaultLifecycleProcessor` reads the value via `SpringProperties.getProperty(...)`. `SpringProperties` looks for the property in a `spring.properties` file at the classpath root, then uses JVM system properties as a fallback. This is a low-level Spring Framework property mechanism, not a lookup from Spring's `Environment`.

Therefore, the following configuration in `application.properties` or `application.yml` is not the documented Spring approach for this property and is normally not visible to `SpringProperties`:

```properties
spring.context.exit=onRefresh
```

Prefer `-Dspring.context.exit=onRefresh` so the value is present from JVM startup. It can also be configured via `spring.properties` at the classpath root, though that file is a Spring Framework properties file, distinct from Spring Boot's `application.properties`.

The value is read during initialization of `DefaultLifecycleProcessor`, so do not wait until after the ApplicationContext has refreshed to set the system property. Setting the property before the JVM runs is the clearest and most reproducible method.

## 4. What Happens When the Property Is Enabled?

Inside `DefaultLifecycleProcessor.onRefresh()`, Spring checks the `spring.context.exit` property. If the value is `onRefresh`, the implementation calls `Runtime.getRuntime().halt(0)` at that lifecycle phase.

This has an important consequence: it is an immediate JVM termination, not closing the ApplicationContext via the normal shutdown sequence. `Runtime.halt(0)` does not trigger shutdown hooks. Because Spring does not go through `ApplicationContext.close()`, do not expect cleanup callbacks such as `@PreDestroy`, `DisposableBean.destroy()`, `ContextClosedEvent`, or Spring-managed resource closing operations to run.

The exit code is normally `0`, so a shell or CI may consider the process successful. However, this exit code only indicates the JVM reached the configured exit point; it does not prove the application finished starting up, the web server accepts requests, or all dependencies are ready.

That is why this mode should be used as an intentional diagnostic run, with an appropriate test environment and test data. Do not enable this property in normal production configuration.

## 5. Using the Test to Detect Premature Remote Connections

A primary benefit of `spring.context.exit=onRefresh` is identifying which beans require external services right during the initialization phase.

For example, an application may have the following components:

| Component | Work during initialization | Work during lifecycle start |
|---|---|---|
| `DataSource` | Creates configuration and connection pool object. | May open actual connections when acquiring a connection or when the pool starts. |
| HTTP client | Creates client and TLS/proxy configuration. | May start workers, health polling, or persistent connections. |
| Message consumer | Creates bean and reads subscription configuration. | Connects to broker, registers consumer, and starts receiving messages. |
| Scheduled worker | Creates scheduler or stores schedule configuration. | Registers periodic tasks and starts executing. |
| Cache loader | Creates cache object and eviction policy. | Loads data from database or service. |

If during the test run the application still needs a database or HTTP service right in the `onRefresh` phase, inspect which bean makes that call. A dependency might be connecting synchronously in a constructor, `@PostConstruct`, `afterPropertiesSet()`, or a factory method.

Not every early connection is wrong. Some applications need to verify credentials, schema, or remote configuration before proceeding. The goal is determining which connections are truly required before checkpoint and which connections can be deferred to lifecycle start or post-restore recovery.

### 5.1. Example of an initialization bean and a lifecycle bean

```java
import jakarta.annotation.PostConstruct;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class RemoteWorker implements SmartLifecycle {

    private volatile boolean running;

    public RemoteWorker() {
        // Constructor should keep initialization at a structural level.
    }

    @PostConstruct
    void initialize() {
        // If placing a synchronous remote call here, it will run before the onRefresh exit.
        System.out.println("RemoteWorker initialized");
    }

    @Override
    public void start() {
        // With spring.context.exit=onRefresh, this method has not been called yet.
        // Can connect to the broker or start the worker here if appropriate for lifecycle.
        running = true;
        System.out.println("RemoteWorker started");
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
```

When running with `-Dspring.context.exit=onRefresh`, the log `RemoteWorker initialized` may appear, yet `RemoteWorker started` will not appear because lifecycle start has not occurred. If the broker call were placed in `initialize()`, the test would reveal the connection happening too early. If moving the operation to `start()`, confirm that design fits the application's requirements and the CRaC checkpoint timing.

The code above only illustrates the difference between an init callback and `SmartLifecycle.start()`. A real `SmartLifecycle` needs to properly implement stop callbacks, timeouts, dependencies, and error handling according to application needs.

### 5.2. Inspecting logs and connection traces

When running the test, observe:

- Logs from constructors, `@PostConstruct`, `InitializingBean`, and factory methods.
- Logs or metrics from connection pools, HTTP clients, and drivers.
- Logs on the database, broker, or HTTP service side regarding new connections.
- Which beans invoke remote services during ApplicationContext creation.
- Which asynchronous tasks are launched from init callbacks.

If a bean launches a background thread and that thread connects to a remote service on its own, the outcome can be nondeterministic: `Runtime.halt(0)` may terminate the process before the asynchronous task completes. To test reliably, instrument where tasks are created or connections are opened, use test doubles/local services when appropriate, and avoid relying on waiting for logs to appear within a short window.

## 6. Practical Workflow with Spring Boot

The test can be carried out in the following sequence:

1. Confirm the application uses Spring Framework 6.1 or later and is using the default `DefaultLifecycleProcessor`.
2. Create a separate test configuration, avoiding unnecessary production secrets or data.
3. Launch the JAR with `-Dspring.context.exit=onRefresh`.
4. Collect bean initialization logs and monitor connection attempts to databases, brokers, caches, or HTTP services.
5. Identify which calls take place before `LifecycleProcessor.onRefresh`.
6. Classify which dependencies are needed before checkpoint and which are only needed when workers start running.
7. When appropriate, move opening connections or starting workers into `SmartLifecycle.start()` or an intentional lifecycle phase.
8. Rerun the test to verify that the initialization phase no longer makes unnecessary connections.
9. Run the application in normal mode to verify lifecycle start, the web server, and business functionality still work.

The expected test outcome is the process exiting at `onRefresh`, before lifecycle start. If the process terminates with exit code `0`, combine logs and connection traces to determine what ran; do not use the exit code alone as proof that full startup succeeded.

## 7. Comparing `spring.context.exit` and `spring.context.checkpoint`

These two properties use the same lifecycle phase yet serve two different goals.

| Criterion | `spring.context.exit=onRefresh` | `spring.context.checkpoint=onRefresh` |
|---|---|---|
| Purpose | Tests the initialization phase and then terminates the JVM. | Creates an automatic checkpoint at the initialization phase. |
| Creates a checkpoint image? | No. | Yes, if the runtime performs the checkpoint successfully. |
| Requires CRaC-enabled JVM? | No. | Yes. |
| Requires `org.crac:crac`? | No. | Yes. |
| Requires Linux/CRaC environment? | Not required for the exit test. | Requires a supported checkpoint/restore environment. |
| Has lifecycle start run? | Not yet. | Not yet when the checkpoint is created. After restore, startup continues. |
| Primary usage | Detecting work or connections occurring too early. | Fast-forwarding startup to the context-initialized phase to take a checkpoint. |

Both properties should not be enabled simultaneously in one test run. In the default implementation, `checkpoint` is processed first; when checkpoint/restore returns, `exit` may still be checked and terminate the JVM. Choose exactly one mode based on your test objective.

## 8. Limitations to Understand

`spring.context.exit=onRefresh` only simulates stopping the startup flow at the corresponding lifecycle phase. It does not replace real CRaC testing.

- Does not confirm the JVM can create a checkpoint image.
- Does not confirm CRIU or the kernel can restore the process.
- Does not execute `Resource.beforeCheckpoint(...)` or `Resource.afterRestore(...)` like a checkpoint/restore cycle.
- Does not test `SmartLifecycle.start()` callbacks since they have not been invoked yet.
- Does not test `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent`, or actual requests to the web server.
- Does not guarantee asynchronous tasks have completed before the JVM is halted.
- Does not run normal Spring cleanup callbacks upon termination.
- Does not prove that caches, connection pools, or resources will work after restore.

If you need to verify checkpoint/restore capability, run with `spring.context.checkpoint=onRefresh` in a compatible CRaC environment, then test dependencies and post-restore behavior. The exit test is an early diagnostic step to understand the initialization boundary, not proof of a successful restore.

## 9. Common Configuration Mistakes

**Setting the property in `application.yml` while the application still runs normally.** The property is read via `SpringProperties`, not Spring Boot's `Environment`. Pass `-Dspring.context.exit=onRefresh` when launching the JVM or use `spring.properties` per Spring Framework's mechanism.

**Using the wrong property name.** `spring.context.exit` is the property that exits the JVM. `spring.context.checkpoint` is the property requesting a CRaC checkpoint. The two names are not interchangeable.

**Using an incorrect value.** The recognized value is `onRefresh`; other values do not trigger this behavior. Comparison is case-insensitive.

**Using Spring Framework older than 6.1.** This property did not exist in earlier versions. Check actual dependencies rather than only checking the application's source code.

**Replacing `DefaultLifecycleProcessor` with a custom implementation.** The property is handled by the default implementation. If the application supplies a different `LifecycleProcessor`, do not expect a custom processor to automatically understand this property.

**Assuming this is a graceful shutdown.** The implementation calls `Runtime.halt(0)`. Do not rely on `@PreDestroy`, `ContextClosedEvent`, or shutdown hooks to release resources during this test run.

**Assuming exit code 0 means the application is ready.** The JVM terminates before lifecycle start, runners, and readiness. Interpret the exit code in line with the goal of the test.

## 10. Checklist When Testing the Initialization Phase

- [ ] Confirm Spring Framework 6.1+ in the dependency graph.
- [ ] Confirm the default `DefaultLifecycleProcessor` is being used.
- [ ] Pass `-Dspring.context.exit=onRefresh` before the JVM starts.
- [ ] Use a safe test configuration and avoid production side effects.
- [ ] Record constructors, `@PostConstruct`, and `afterPropertiesSet()` of non-lazy singletons.
- [ ] Check at which phase database, broker, HTTP, and remote configuration connections are opened.
- [ ] Distinguish bean initialization from `Lifecycle`/`SmartLifecycle.start()`.
- [ ] Do not expect `ContextRefreshedEvent`, runners, or `ApplicationReadyEvent` to be published.
- [ ] Do not rely on shutdown callbacks for cleanup since the JVM is halted immediately.
- [ ] Identify and instrument asynchronous tasks launched inside init callbacks.
- [ ] Do not use exit code 0 alone as proof of complete startup.
- [ ] Rerun the application normally to confirm lifecycle and web server operation.
- [ ] Use `spring.context.checkpoint=onRefresh` in a separate CRaC environment when actual checkpoint verification is needed.

## 11. Key Terms to Remember

- **`spring.context.exit`:** Spring Framework property controlling JVM termination at a specified lifecycle phase.
- **`onRefresh`:** value requesting the behavior to execute at `LifecycleProcessor.onRefresh()`.
- **`DefaultLifecycleProcessor`:** default implementation coordinating `Lifecycle` and `SmartLifecycle` beans during start/stop.
- **Bean initialization:** the phase of instantiating beans, injecting dependencies, and running init callbacks.
- **Lifecycle start:** the phase where Spring invokes `start()` on eligible lifecycle beans.
- **`SmartLifecycle`:** lifecycle contract adding phase ordering, auto-start, and asynchronous stop callbacks.
- **`ContextRefreshedEvent`:** event published after the refresh/lifecycle processor phase.
- **`Runtime.halt(0)`:** terminates the JVM immediately with exit code 0 without running shutdown hooks.
- **`SpringProperties`:** Spring Framework's low-level property mechanism, reading `spring.properties` and JVM system properties.
- **`spring.context.checkpoint`:** another property used to request an automatic checkpoint at `onRefresh` when a CRaC environment is supported.

`spring.context.exit=onRefresh` is a quick way to observe the boundary between ApplicationContext initialization and starting lifecycle beans in Spring Boot. Use it to find connections or remote tasks occurring too early, understand which callbacks have run, and see which phases have not been reached yet. Since the JVM terminates immediately at this point, read the results as evidence about the initialization phase, then use normal run mode and an actual CRaC checkpoint to verify subsequent phases.

## References

- [Spring Framework — JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html): official description of `spring.context.exit=onRefresh`, its position in `LifecycleProcessor.onRefresh`, and the purpose of checking remote connections before beans start.
- [Spring Framework — `DefaultLifecycleProcessor` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): property `EXIT_PROPERTY_NAME`, value `ON_REFRESH_VALUE`, and lifecycle processor.
- [Spring Framework — `SpringProperties` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/SpringProperties.html): how Spring reads the `spring.properties` file and JVM system properties.