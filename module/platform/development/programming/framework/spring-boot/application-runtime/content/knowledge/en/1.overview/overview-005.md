# Distinguishing One-Shot Applications from Long-Running Services in Spring Boot

## 1. Nature of the two execution models

A **one-shot application** is launched to perform a task with a clear completion point: read input, process it, write output, release resources, and exit the process. Examples: importing a data file, generating an end-of-day report, running an administrative command, or processing a batch of data triggered on an external schedule.

A **long-running service** is launched to remain available to serve multiple requests or events throughout its deployment lifetime. Examples: a REST API, an application receiving messages from a queue, an event-consuming service, or a process coordinating periodic tasks. The service stops only when it receives a stop request, needs redeployment, or encounters a failure.

The distinguishing criterion is the **process lifecycle contract**, not runtime duration measured in minutes or hours. A job that runs for three hours can still be one-shot if it finishes its work and exits; a REST API stopped two minutes after startup is still a long-running service by design.

## 2. Comparison across practical dimensions

| Criterion | One-shot application | Long-running service |
| --- | --- | --- |
| Goal | Complete a defined unit of work | Remain ready to accept new requests or events |
| Completion condition | All work for that run has succeeded or failed | No "entire service finished" point during normal operation |
| Triggering mechanism | CLI command, operator, external scheduler, Job/CronJob, pipeline | Deployment, orchestrator, process manager service |
| Input | Command arguments, files, records to process, job parameters | HTTP, messages, events, tasks arriving at runtime |
| Output | Processing results, new files/records, logs, exit code | Per-request/event responses, state changes, metrics |
| Normal state after startup | Process the work and exit | Continue waiting for and processing subsequent requests |
| How success/failure is reported | Business outcome and exit code of each run | Per-request/event outcome, health, metrics, and process state |
| Resource management | Opened during execution, closed upon completion or error | Resources live alongside the service, closed on shutdown |
| Common deployment approach | Kubernetes Job/CronJob, CI task, operational command | Kubernetes Deployment, service manager, continuously running container |
| On failure | Determine whether to retry the whole job or failed step, prevent duplicate writes | Isolate errors per request/event; the service usually keeps accepting work |

Do not equate **one-shot** with "single-threaded" or **long-running** with "multi-threaded": both can process work in parallel. Likewise, do not equate "no HTTP" with "one-shot": a message broker consumer can run continuously without opening an HTTP port.

## 3. Spring Boot starts the same way, then the lifecycle diverges

Both models can use the same Spring Boot initialization mechanism:

1. The main method invokes SpringApplication.run(...), directly or through a configured SpringApplication.
2. Spring Boot prepares the Environment, creates and refreshes the ApplicationContext, and initializes beans and configured infrastructure.
3. For web applications, the embedded server may be initialized and begin listening on a port.
4. After the context is refreshed, Spring Boot invokes ApplicationRunner and CommandLineRunner beans; once runners complete, the application publishes ApplicationReadyEvent.
5. **Lifecycle fork point:** a one-shot app actively finishes and terminates; a service keeps serving via its web server, listeners, or appropriate long-lived processing mechanism.

**ApplicationReadyEvent does not mean "the job succeeded" or "all requests have been handled".** It signals that Spring Boot's startup phase has completed, including startup runners. A service can become ready and run indefinitely; a one-shot app can become ready right before closing its context.

Spring Boot determines the web type from the classpath and configuration. With spring-boot-starter-web, the application typically runs a servlet web server; for pure CLI apps, explicitly set WebApplicationType.NONE to avoid unintentionally starting a web server. However, **WebApplicationType.NONE does not itself define that a job has finished**: if the application still has listeners, executors with non-daemon threads, or other background activity, the process may remain alive.

## 4. One-shot example: process once and exit

The following example is for a **separate Spring Boot 3.x project**, Java 17+, with spring-boot-starter. Save the class in src/main/java/demo/OneShotApplication.java.

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class OneShotApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(OneShotApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Override
    public void run(String... args) {
        System.out.println("Processing complete.");
    }
}
~~~

If the project already has the Spring Boot Gradle plugin configured, you can run it with:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, use:

~~~powershell
.\gradlew.bat bootRun
~~~

The line printed by the example code itself (ignoring Spring Boot startup logs) is:

~~~text
Processing complete.
~~~

**Step-by-step explanation:**

- ApplicationContext is initialized; WebApplicationType.NONE requests non-web mode without a web server.
- Because the application class is a Spring bean implementing CommandLineRunner, Spring Boot calls run(...) once on each successful startup.
- When run(...) returns, SpringApplication.run(...) finishes and returns the context.
- SpringApplication.exit(context) closes the context and retrieves the exit code from registered ExitCodeGenerator beans (if any); by default with no error code it returns 0.
- System.exit(exitCode) passes this code as the JVM process exit code. This is appropriate behavior for a one-shot executable whose caller needs the outcome.

**Important note:** CommandLineRunner is only a startup hook. It **does not automatically turn the whole application into a one-shot app**. If the same application also has a web server or long-lived components, a runner finishing does not mean the process should exit. Place System.exit(...) in the top-level orchestration flow of a one-shot program; do not call it from shared business logic, controllers, or listeners.

When a job fails, intentionally produce a non-zero exit code (for example via ExitCodeGenerator/ExitCodeExceptionMapper and the application's error-handling mechanism). Close the context in a finally block or use appropriate lifecycle management if orchestrating multiple steps yourself. Do not swallow exceptions and return 0 as if the job succeeded. For work with side effects, design retries and idempotency so reruns do not create duplicate data.

## 5. Long-running example: a REST API continuously accepting requests

The second standalone example uses Java 17+, Spring Boot 3.x, and spring-boot-starter-web. Save it in src/main/java/demo/ApiApplication.java of **a different project** from the one-shot example.

~~~java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

After running the project with Gradle, you can send requests repeatedly:

~~~bash
curl -s http://localhost:8080/ping
~~~

The JSON response under the default port configuration is:

~~~json
{"status":"ok"}
~~~

Key difference: main does not call SpringApplication.exit(...) or System.exit(...) right after startup. The embedded HTTP server continues listening and serving multiple requests until the system stops the application. Each finished request does not terminate the entire process. Port 8080 is only the default when server.port or another environment override is not configured.

A service does not necessarily have @RestController: an event-processing application or continuous consumer is also long-running when it must maintain a work-receiving lifecycle. For that type, configure listeners, thread/executor lifecycles, and shutdown properly; simply setting web-application-type=none is not enough to build an event-receiving process.

## 6. Stopping the application, exit codes, and resilience

**For one-shot apps:**

- Success typically corresponds to exit code 0; categorized failures need non-zero codes so a scheduler, CI/CD pipeline, or Kubernetes Job can detect them.
- Ensure connections, transactions, streams, executors, and remaining open resources are closed. Do not rely on the operating system reclaiming resources as a substitute for business cleanup.
- If stopped mid-run, define checkpoints, transaction boundaries, and resume or rerun mechanisms. "One-shot" describes a single launch, not a system-wide guarantee of at-most-once execution.
- Record processed record counts, error counts, duration, outcome, and run trace; track job completion rather than treating long uptime as success.

**For long-running services:**

- When receiving a controlled stop request (for example SIGTERM in the deployment environment), Spring Boot can close the ApplicationContext and invoke bean destruction mechanisms; active serving resources must be released.
- For web servers, graceful shutdown can be enabled to avoid abruptly cutting off in-flight requests. Example in application.yml:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

- Configured health/readiness/liveness checks (typically via Spring Boot Actuator and the deployment platform) help decide whether an instance is ready to accept traffic and whether it needs to be restarted. Readiness does not replace the success status of individual tasks.
- Handle timeouts, backpressure, connection pools, retries, and errors per request/event. A normal business error should not bring down the entire JVM.

Both models should manage resources through bean lifecycle management, try-with-resources where appropriate, and executor shutdown; **they differ primarily in when the context closes and what process termination signifies**.

## 7. Choose architecture by requirements, not by annotations

Answer these in order:

1. **Does the work have a completion condition per launch?** If yes and no new work needs to be accepted afterward, lean toward one-shot.
2. **After the initial task, must the process keep listening for new requests, queues, or triggers?** If yes, it is a long-running service, even if each request only takes a few milliseconds.
3. **Who decides when to launch again?** An external scheduler usually fits a Job/CronJob; a process continuously awaiting messages usually fits a Deployment or service manager.
4. **What outcomes must operations monitor?** For one-shot, per-run results and exit codes; for services, availability, performance, and outcomes across many requests.

Decision examples:

| Scenario | Reasonable choice | Reason |
| --- | --- | --- |
| Read a file nightly, export a report, and exit | One-shot, triggered by external schedule | Each run has a deterministic completion result |
| Serve a product lookup API | Long-running service | Must continuously accept independent requests |
| Kafka consumer receiving messages all day, without HTTP | Long-running service | Must keep listeners running even without a web server |
| Administrator runs a synchronous one-time command | One-shot | The command returns a result/exit code to the caller |
| A service with @Scheduled running cleanup every hour | Long-running service | The process keeps the scheduler alive waiting for the next trigger |
| Service loads configuration data once at startup, then serves an API | Long-running service | A one-time initialization step does not dictate the whole system's lifecycle |

## 8. Misconceptions that easily cause bugs

**Misconception 1: "Having CommandLineRunner makes it one-shot."** False. Runners execute during the startup phase for both web and non-web applications. Calling System.exit(...) after SpringApplication.run(...) in a service will cause the service to exit immediately, even if HTTP endpoints are registered.

**Misconception 2: "Setting WebApplicationType.NONE makes the JVM exit automatically."** Not necessarily. NONE only disables the web runtime; threads, schedulers, consumers, or background resources can keep the JVM alive. Conversely, a non-web app with no long-lived work can exit once only daemon threads remain without needing a web server.

**Misconception 3: "ApplicationReadyEvent means the job has finished."** This event only marks that startup and startup runners have completed; business outcomes, asynchronous processing, and future requests have their own lifecycles.

**Misconception 4: "A service only needs an infinite loop to stay alive."** Blind wait loops, infinite sleeps, or busy-waits hinder shutdown and monitoring. Use a web server, listener, or properly lifecycle-managed scheduler/executor suited to the actual purpose.

**Misconception 5: "A one-shot job does not need to care about retries."** A job can be rerun by a scheduler or operator after failure; writes outside a transaction or external API calls may have partially succeeded. Control reruns, idempotency, and outcome observability.

**Misconception 6: "Close the ApplicationContext after completing one request."** This only makes sense if the process itself is designed to serve exactly one task. For an API or consumer, closing the context cuts off the ability to receive subsequent requests/events.

## 9. Self-check

- A Spring Boot program reads 5 million records, takes two hours, then exports a file and exits: **one-shot**, because it has a clear completion condition.
- An application does not open HTTP but continuously consumes a queue: **long-running service**, because it must accept new events.
- A REST API uses CommandLineRunner to warm a cache at startup: **long-running service**, because the runner is only an initialization step.
- A Kubernetes CronJob creates a Pod, runs processing, and the Pod exits with exit code 0: **one-shot** per trigger.

**Takeaway:** The deciding question is *"After finishing the current task, does the process need to stay alive to accept new work?"* Answer that question first, then choose the runners, web server/listeners, shutdown configuration, exit codes, and deployment workload type accordingly.