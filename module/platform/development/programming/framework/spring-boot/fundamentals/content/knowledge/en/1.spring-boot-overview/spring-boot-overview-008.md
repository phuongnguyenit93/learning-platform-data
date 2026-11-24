# Command-Line Apps, Web Apps, and Background Workers Can All Use Spring Boot

When hearing **Spring Boot**, many people immediately picture a REST API running on port 8080. That is a popular use case, but it is not the definition of Spring Boot. The exact same platform can build:

- **Command-line applications (CLI):** accept arguments, perform a job, and exit.
- **Web applications:** start an HTTP server, accept requests, and return responses.
- **Background worker applications:** wait on a schedule, event, or message to execute work without a user directly calling HTTP.

The commonality does not lie in the interface or how work is triggered. What they share is that all three can use the **Spring ApplicationContext**, bean management, dependency injection, configuration, logging, integration libraries, and Spring Boot's startup mechanism.

## 1. Distinguishing Spring Boot from a Web Server

**Spring Framework** provides foundational pieces such as the IoC container, dependency injection, bean lifecycle management, transactions, and integrations with many technologies. **Spring Boot** makes initializing, configuring, and packaging Spring applications more convenient via starters, auto-configuration, externalized configuration, and a consistent launch mechanism.

Spring Boot **does not require** an application to have endpoints, controllers, or an HTTP server. When running a Boot application, you can picture the general flow:

~~~text
main() method
    │
    ▼
SpringApplication.run(...)
    │
    ├── Read configuration and environment
    ├── Create ApplicationContext
    ├── Instantiate and wire beans
    ├── Apply matching auto-configurations
    │
    ▼
Application ready
    │
    ├── CLI: run CommandLineRunner / ApplicationRunner → exit
    ├── Web: open HTTP server → serve requests continuously
    └── Worker: register schedule / listener → process background work
~~~

The difference mainly comes from **chosen libraries, application type configuration, and business trigger mechanisms**. For example, adding Spring MVC with an embedded server fits a web application; a program importing data from a file might only need core Spring Boot and a file-reading library.

### Concepts to Keep Separate

| Concept | Meaning |
|---|---|
| Spring Boot | Mechanism for bootstrapping, configuring, and operating Spring-based applications |
| ApplicationContext | Container managing the application's beans and dependencies |
| Bean / Service | Object managed by Spring, usable by CLI, web, or worker |
| HTTP server | Component serving network requests; needed for web apps, not a prerequisite for Spring Boot |
| Runner | Execution hook running code after Spring finishes initializing the context |
| Scheduler / Message listener | Mechanism triggering work periodically or when a message arrives |

In the examples below, treat **each type as an independent application** with its own package and bootstrap class. When needed, a real system can share business classes or combine multiple roles in the same process.

## 2. Comparison Across the Three Application Types

| Criterion | Command-Line App | Web App | Background Worker |
|---|---|---|---|
| Who triggers it? | User, terminal, script, CI, or external scheduler | Client sending an HTTP request | Periodic schedule, queue, event, or work source |
| Business entry point | `ApplicationRunner` / `CommandLineRunner`, specific command | Controller / HTTP handler | Method with `@Scheduled`, listener, or job handler |
| Needs an HTTP server? | No | Yes, if serving HTTP | Usually no; can be enabled for management or APIs |
| Typical lifecycle | Start → do work → exit | Start → serve requests → stop on signal | Start → wait & process work → stop on signal |
| Examples | CSV import, data migration, one-off report generation | Order REST API, admin portal, web backend | Sending emails from a queue, scheduled cleanup, event processing |
| Primary concerns | Arguments, output, exit codes, error handling | API contract, security, timeouts, throughput | Retries, idempotency, overlapping schedules, monitoring, shutdown |

**"No web interface" does not mean "no Spring."** A one-off program still benefits from dependency injection and configuration; a 24/7 worker can also use repositories, transactions, and services just like a web backend.

## 3. Type One: Command-Line Application (CLI)

Suppose we need a command that greets a user to clearly see how Spring Boot handles arguments. The application should accept a value from the terminal, use a bean created by Spring, print the result, and exit.

For a new application, a core dependency like **spring-boot-starter** is enough for this example. There is no need to add **spring-boot-starter-web** just to get dependency injection.

### Example Using ApplicationRunner

~~~java
package com.example.cli;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        // Do not start a web server, even if a web library happens to be on the classpath.
        try (var context = new SpringApplicationBuilder(CliApplication.class)
                .web(WebApplicationType.NONE)
                .run(args)) {
            // Spring already ran all ApplicationRunners before run(args) returned.
            // Close the context after synchronous work completes.
        }
    }

    @Bean
    ApplicationRunner greetingCommand(GreetingService greetingService) {
        return arguments -> {
            List<String> names = arguments.getOptionValues("name");
            String name = (names == null || names.isEmpty())
                    ? "friend"
                    : names.get(0);

            System.out.println(greetingService.greet(name));
        };
    }
}

@Service
class GreetingService {
    String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Run the packaged JAR:

~~~bash
java -jar cli-demo.jar --name=Lan
~~~

Business output looks like:

~~~text
Hello, Lan!
~~~

Spring Boot may also print startup logs; the line above is the output produced by the command.

In this example:

1. **main()** creates a Spring application of type **NONE**, meaning no web context is created.
2. Spring creates the **GreetingService** bean and passes it into the **ApplicationRunner** bean factory method.
3. Once the context is initialized, Boot invokes **ApplicationRunner.run(ApplicationArguments)**.
4. The runner reads the **--name=Lan** option and invokes business logic via the service.
5. After the synchronous runner finishes, the **try-with-resources** block closes the context; the process can exit.

**ApplicationRunner** provides an **ApplicationArguments** object for reading named options and non-option arguments. **CommandLineRunner** runs at the same point in startup, but receives the raw **String... args** array. Choose whichever matches how you want to parse arguments; both are Spring-managed beans.

### When a CLI Becomes a Real-World Tool

A real-world application might follow these steps:

~~~text
Command: java -jar import-tool.jar --file=/data/orders.csv
                 │
                 ▼
        Validate file argument
                 │
                 ▼
    ImportService → Validator → Repository
                 │
                 ▼
     Print output / logs / exit code
~~~

Useful principles in that case:

- **Separate business logic from the Runner:** The runner only parses input and orchestrates; services handle importing, validation, and data access.
- **Distinguish failure from success:** Scripts and orchestrators rely on **exit codes**. You can use **ExitCodeGenerator** and **SpringApplication.exit(...)** to emit an appropriate exit code; never just print "error" and return a success code.
- **Manage resources:** Stream large files when appropriate, close connections and the context, and handle transactions at business boundaries.
- **Do not spin up unnecessary web resources:** A one-off job does not need an HTTP server running throughout data ingestion.

If a task should terminate after a single run, a **CLI invoked by cron or a Kubernetes CronJob** may fit better than an always-on process waking itself up repeatedly. That is an operational choice, not a limitation of Spring Boot.

## 4. Type Two: Web Application

A web application has a different lifecycle: after Spring initializes, **the HTTP server stays up listening for requests**. Each incoming request to an endpoint travels through the web layer and calls the appropriate service.

With Spring MVC, you typically add **spring-boot-starter-web**. On Spring Boot 3.x, this starter provides the components needed for REST controllers and the default embedded Servlet server. If choosing WebFlux, use the corresponding reactive stack; you do not need both stacks for a basic example.

### Small REST API Example

~~~java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}

@RestController
class GreetingController {

    @GetMapping("/hello")
    GreetingResponse hello(@RequestParam(defaultValue = "friend") String name) {
        return new GreetingResponse("Hello, " + name + "!");
    }
}

record GreetingResponse(String message) {}
~~~

When the app runs on the default port, you can send a request:

~~~bash
curl "http://localhost:8080/hello?name=Lan"
~~~

Illustrative JSON response:

~~~json
{"message":"Hello, Lan!"}
~~~

In the web application:

1. **SpringApplication.run(...)** creates the context, auto-configures components matching classpath dependencies, and starts the embedded HTTP server.
2. **@RestController** declares a bean that handles HTTP requests.
3. **@GetMapping("/hello")** maps GET requests to the **hello(...)** method.
4. **@RequestParam** reads the **name** parameter from the query string; the response object is converted to JSON by an appropriate HTTP message conversion mechanism.
5. The application keeps serving requests until stopped or terminated.

Typical processing flow:

~~~text
Browser / Mobile / curl
          │ HTTP GET /hello
          ▼
Embedded HTTP server
          │
          ▼
Spring MVC → Controller → Service → Repository
          │
          ▼
HTTP status + JSON response
~~~

Unlike a CLI, **a single web application startup typically serves many requests**. Therefore, you must care about HTTP status codes, input validation, authentication/authorization, port configuration, timeouts, exception handling, and concurrency.

For example, the port can be configured in **application.yml**:

~~~yaml
server:
  port: 8081
~~~

Then the sample endpoint is reached at **http://localhost:8081/hello**. Changing the port only matters when the application actually runs an HTTP server.

## 5. Type Three: Background Worker

Workers serve jobs that **do not originate directly from an HTTP request at the time of execution**: nightly data cleanup, aggregating statistics, scheduled report generation, consuming messages from a queue, or syncing data with external systems.

A worker can run long-term **without opening an HTTP port**. Spring Boot still manages its services, configuration, dependencies, logging, and lifecycle.

### Example of a Periodic Task with @Scheduled

This is a standalone application using **spring-boot-starter** and Spring's scheduling support:

~~~java
package com.example.worker;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class WorkerApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(WorkerApplication.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}

@Component
class CleanupJob {

    private static final Logger log = LoggerFactory.getLogger(CleanupJob.class);

    @Scheduled(fixedDelay = 60_000)
    public void cleanup() {
        log.info("Starting cleanup check pass");

        // In a real application: call CleanupService to process data.

        log.info("Finished cleanup check pass");
    }
}
~~~

Notable points:

- **@EnableScheduling** turns on discovery and registration of **@Scheduled** methods.
- **@Scheduled(fixedDelay = 60_000)** schedules the next run 60,000 milliseconds after the previous run finishes.
- **WebApplicationType.NONE** disables the web layer; the worker has no **/cleanup** endpoint.
- **main()** does not close the context right away like a CLI, because the application must stay alive for the scheduler to trigger subsequent runs.

To run exactly at 2:00 AM daily in Vietnam time, you can use:

~~~java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void cleanupEveryNight() {
    // Call cleanup business logic.
}
~~~

Spring's cron expression in this example has **six fields**, where the first field is **seconds**. Choose one scheduling method for a given job; putting both examples in at the same time creates two independent scheduled triggers.

### Three Different Triggers for Background Work

Not every worker uses **@Scheduled**:

| Trigger Source | Organization | Example |
|---|---|---|
| Application-internal schedule | **@Scheduled** with fixed delay, fixed rate, or cron | Check and clean up data every night |
| External schedule | OS cron, Kubernetes CronJob launching a CLI/Job | Generate a report at 02:00 and exit |
| Message / event | RabbitMQ, Kafka, or similar queue listener | Receive an email-send request after an order is created |

For multi-step batch jobs requiring restarts or per-chunk progress tracking, **Spring Batch** may be appropriate. **@Scheduled** itself only handles **when to invoke a method**; it does not automatically provide durable retries, checkpoints, partitioning, or multi-instance deduplication.

### Issues a Worker Must Proactively Handle

**1. Duplicate execution across multiple instances.** If three replicas of an application each include `@Scheduled(cron=...)`, all three can run the job at the same time. When business logic must execute only once, design a coordination mechanism such as a distributed lock, a coordinating job scheduler, or queueing work with appropriate processing rules.

**2. Error handling and retries.** Logging an error does not give a job durable retries. Define which errors are retryable, retry counts, backoff intervals, state storage, and dead-letter/permanent-failure handling.

**3. Idempotency.** If the same message is delivered twice, operations like "transfer funds" or "issue invoice" must not blindly execute twice. Rely on unique job IDs, database constraints, or idempotent handling designed into the business layer.

**4. Execution duration and shutdown.** Long-running jobs need graceful shutdown handling, transactions, timeouts, and progress tracking. If the app stops mid-run, know what it must do upon restart.

**5. Observability.** Log with job IDs, count successes/failures, track duration, and alert when periodic work fails to complete. A worker without an HTTP endpoint still needs monitoring.

## 6. Same Service, Multiple Ways to Invoke It

Imagine a system with an inventory report generation feature. We can put the logic into a Spring bean:

~~~java
package com.example.reports;

import org.springframework.stereotype.Service;

@Service
public class InventoryReportService {

    public String generate() {
        // Illustrative: in practice this may query a repository and export a report file.
        return "Inventory report has been generated";
    }
}
~~~

This bean does not need to know who invokes it. Three different adapters can use the exact same service:

~~~text
                         InventoryReportService
                         + generate()
                              ▲
             ┌────────────────┼────────────────┐
             │                │                │
     CLI ApplicationRunner    │        Worker @Scheduled
     runs on command          │        runs on schedule
                              │
                     Web @PostMapping
                     runs on HTTP request
~~~

Corresponding ways to wire them:

~~~java
// CLI: runs once when the application starts.
@Bean
ApplicationRunner reportCommand(InventoryReportService reports) {
    return args -> System.out.println(reports.generate());
}
~~~

~~~java
// Web: runs when a client sends POST /reports.
@RestController
class ReportController {
    private final InventoryReportService reports;

    ReportController(InventoryReportService reports) {
        this.reports = reports;
    }

    @PostMapping("/reports")
    String createReport() {
        return reports.generate();
    }
}
~~~

~~~java
// Worker: runs daily at 02:00 Vietnam time.
@Component
class NightlyReportJob {
    private final InventoryReportService reports;

    NightlyReportJob(InventoryReportService reports) {
        this.reports = reports;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    void createReport() {
        reports.generate();
    }
}
~~~

The snippets above show **three alternative adapters**; they must be placed in an application with matching configuration, dependencies, and imports. Do not copy all three into one project and assume only one will run: if you register the controller, runner, and scheduler together, all three mechanisms can execute.

The architectural meaning is that **services hold business logic, while adapters decide when and how to invoke that logic**. This lets you test business logic independently of HTTP or the terminal and reduces code duplication as the system grows.

## 7. Can One Application Combine Multiple Roles?

**Yes.** A web application can serve APIs while also running `@Scheduled` tasks to clean caches. A worker can expose an HTTP endpoint for administrative commands. A CLI can also use repositories and transactions just like a long-lived server.

However, combining roles must be an **intentional deployment decision**:

- When a short task runs once, a CLI is usually simpler to operate.
- When needing to respond to client requests, a web app is the natural fit.
- When waiting on queues or running periodically, a worker fits background cadence.
- When background work is resource-intensive, running it inside the web process can hurt API latency; splitting out a worker enables independent resource allocation and scaling.
- When deploying multiple replicas of a web app, `@Scheduled` schedules inside each replica may fire multiple times; define a deduplication strategy before going to production.

In particular, **@Async** is not a default substitute for a durable job. It supports running work asynchronously inside the application, but it does not automatically turn a task into a persistent queue with retries and crash recovery.

## 8. Choosing the Application Type from Real Requirements

Start with the question: **What initiates the work and when is it considered complete?**

~~~text
How does the work start?
        │
        ├── Triggered by a command or external schedule
        │      └── CLI / batch runs once and exits
        │
        ├── Client needs HTTP request/response
        │      └── Web application + controller/handler
        │
        └── App proactively waits on a schedule or messages
               └── Background worker + scheduler/listener
~~~

Only then choose dependencies, configuration, packaging, and deployment. Examples:

| Requirement | Sensible Initial Choice | Reason |
|---|---|---|
| Run a one-off legacy data migration command | CLI | Clear start/end point, easy to emit exit codes |
| Provide a product lookup API | Web | Clients send requests and receive responses |
| Poll a queue every minute and process items | Worker/listener | Work arrives from an asynchronous source |
| Generate a nightly report and exit | CLI triggered by CronJob or batch job | Schedule can be orchestrated by infrastructure |
| Send confirmation email after checkout | Worker consuming messages | Decouples slow work from the HTTP response path |
| Admin clicks a button to start a heavy job | Web enqueues request + worker processes | Fast HTTP response, independent job execution |

### Combined Scenario: "Generating a Report" Doesn't Have to Happen Inside the Request

Suppose an API receives a request to generate a massive report file. If the controller runs everything inside the request, the client may time out and the server holds connections open too long. A usually better organization is:

~~~text
Client ── POST /reports ──► Web API
                               │
                               ├── Validate request
                               ├── Save job with status PENDING
                               └── Push message to queue
                                            │
                                            ▼
                                     Background worker
                                            │
                                            ├── Read data
                                            ├── Generate report
                                            └── Update status DONE/FAILED

Client ── GET /reports/{id} ──► Web API returns status/result
~~~

In this design, **both web and worker can be written with Spring Boot**, yet their roles and operational cadences differ. The queue, job persistence, and retry mechanisms must be implemented or chosen using suitable technologies; Spring Boot does not create a durable queue from annotations alone.

## 9. Common Misconceptions

**"Using Spring Boot requires Tomcat and port 8080."** Incorrect. Embedded Tomcat is an option for standard Servlet web applications. CLIs and workers can run with **WebApplicationType.NONE** without opening any HTTP port.

**"Without a controller, you cannot use dependency injection."** Incorrect. Dependency injection belongs to the ApplicationContext and works with services, runners, schedulers, listeners, and many other components.

**"ApplicationRunner is a scheduler."** Incorrect. A runner is invoked once at application startup; it does not re-run periodically on its own.

**"Using @Scheduled guarantees a job runs only once across the entire system."** Incorrect. Each instance has its own scheduler if it registers the job. Coordination across instances is required when uniqueness is needed.

**"Put every heavy task in a controller since everything is Spring Boot anyway."** Do not reason that way. Sharing a framework does not erase differences in HTTP timeouts, load pressure, retry semantics, and job lifecycles.

**"A worker must be a separate microservice."** Not mandatory. That is a deployment and scaling decision, not a Spring Boot constraint. You can start in the same process and split later when operational needs demand it.

## 10. Observing the Differences Yourself at Runtime

You can create three small projects following the examples above, run each one, and observe their behavior:

| Experiment | What to Observe |
|---|---|
| Run the CLI with **--name=Lan** | Runner executes once, prints the greeting, and the process exits |
| Run the web app and call **GET /hello?name=Lan** repeatedly | Each request receives JSON; the app keeps running between requests |
| Run the worker with a **fixedDelay** schedule | Logs appear repeatedly on schedule without any HTTP call |
| Run the worker and try calling **localhost:8080** | No web server responds because the worker intentionally uses **WebApplicationType.NONE** |
| Run two worker instances with the same schedule | You can see each instance trigger the job independently; this is why coordination must be designed when needed |

When observing, focus on three questions: **Who starts the work? Which beans does Spring manage? When does the process terminate?** These three questions classify an application more accurately than whether a controller is present.

## Conclusion

Spring Boot is a platform for building **many kinds of Java applications**, not just REST APIs. CLIs, web applications, and background workers can all share dependency injection, configuration, services, repositories, and familiar Spring integrations. What changes are **business trigger points, HTTP server requirements, and operational lifecycles**.

When designing a system, choose the application type based on how work arrives and is processed: **one-off command execution, continuous HTTP serving, or scheduled/event-driven background processing**. Understanding that distinction helps you select the right starters, organize reusable code, and avoid operational pitfalls such as duplicate job runs or overly long-lived HTTP requests.
