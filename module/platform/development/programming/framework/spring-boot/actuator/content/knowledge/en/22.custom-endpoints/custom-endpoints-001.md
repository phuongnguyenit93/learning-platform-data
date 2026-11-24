# When to Create an Actuator Endpoint Instead of a Business Controller

## 1. Two Types of Endpoints Answer Two Different Questions

A data import application might need to answer:

- “Has customer A's data import completed?”
- “Is this application instance's data import processor paused or running?”

The first question belongs to product functionality: the data is tied to a customer, an import job, and business access permissions. The second question serves operations: an on-call operator needs to know the state of a component running inside the application.

A **custom Actuator endpoint** is an application monitoring or management capability integrated into the Actuator mechanism. It is appropriate when you need to observe or control an operational aspect that is not already covered by built-in endpoints.

A **business controller** is the layer that handles requests for a use case belonging to the product or business domain: placing an order, looking up an order, submitting an application, viewing data import results, approving a refund. It remains a business API even when only internal staff or administrators can call it.

Both can return JSON over HTTP. Therefore, “having a URL”, “using GET”, “returning a status”, or “restricting access to admins only” does not by itself determine the endpoint type.

In Spring Boot, Actuator provides endpoints for monitoring and interacting with the application; see the [Spring Boot 3.3 endpoints overview](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. Understanding the Conceptual Layers Correctly

| Concept | Meaning |
| --- | --- |
| Endpoint in the ordinary HTTP sense | An access point defined by a combination of URL, method, and request/response contract |
| `@RestController` | A Spring MVC component that handles web requests using controller mapping mechanisms |
| `@Endpoint` | Defines an endpoint in the Actuator system, with an ID and operations |
| `@ReadOperation` | An Actuator read operation; when exposed over the web, mapped to GET |
| `@WriteOperation` | An Actuator write operation; when exposed over the web, mapped to POST |
| Exposure | Configuration that exposes an endpoint over a technology such as HTTP or JMX |
| Authorization | Decides which user or system is allowed to invoke an operation |

A class annotated with `@RestController` and `@GetMapping("/actuator/importworker")` is still an ordinary web controller. Giving it an Actuator-like path does not automatically place it into Actuator's endpoint discovery, exposure configuration, or management port.

According to the [Endpoint annotation contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html), Actuator endpoints are designed to be adaptable to multiple exposure technologies, including HTTP and JMX. `@Endpoint` also does not automatically turn an unregistered object into a Spring bean.

For controllers, [Spring MVC's annotated controller model](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html) provides request mapping, input handling, and exception handling tailored to web needs. It is the natural choice for business HTTP contracts.

## 3. Decision Criteria: Purpose, Data, and Lifecycle

The following table is a design guide, not a checklist that the framework checks automatically:

| Criterion | Leans Toward Custom Actuator | Leans Toward Business Controller |
| --- | --- | --- |
| Primary question | How is the application operating? | What does the user want to perform or look up? |
| Described subject | Processors, internal resources, worker/thread states | Orders, applications, import runs, customers |
| Consumer | Operations tools, on-call operators, diagnostic tools | Product UI, partners, services using business use cases |
| Data scope | One application instance or a well-defined technical component | Data scoped by customer, account, organization, or ownership |
| Contract lifecycle | Tied to operational capabilities and incident runbooks | Tied to product features, API versioning, and consumer commitments |
| Input | Small operational actions, parameters with clear meaning | Business requests, validation, domain rules, and domain errors |
| Implementation style | Reads state or invokes a management capability via a service | Calls a use-case service and applies business policies |

You should not rely on a single indicator to classify an endpoint. For example, another service calling an internal API to create an invoice is still using business functionality. An internal admin page for staff to approve orders also belongs to the product.

Conversely, an operations tool checking whether a message consumer is paused due to maintenance or an error is a suitable case to consider Actuator.

### 3.1. Three Questions Before Choosing

1. **If you remove the operations team from the problem, is this capability still needed by users or business flows?** If yes, it is very likely a business controller or business admin API.
2. **Does the data describe a business entity or the operational state of the application?** An “order status” and an “order processor status” are two different contracts.
3. **Does Actuator already have an appropriate extension point for this need?** If it does, extend that capability before creating another endpoint.

If a requirement mixes both purposes, split it into two clearly scoped contracts. Do not return both a list of customer data and processor thread status in the same endpoint just because they share an underlying service.

## 4. Before Creating a New One: Use the Right Built-In Capability

An operational requirement does not necessarily require a new endpoint.

| Need | Option to Consider First |
| --- | --- |
| Is the application or a dependency ready to serve traffic? | Health and an appropriate `HealthIndicator` |
| Version, build, and deployment description information | Info and an appropriate `InfoContributor` |
| Pending job count, throughput, processing duration, error rate | Metrics via Micrometer and the monitoring system |
| Adjusting log levels during diagnostics | Built-in `loggers` endpoint |
| Viewing or managing supported caches | Built-in `caches` endpoint |
| A specialized operational state snapshot without an existing suitable contract | Custom Actuator endpoint |
| Looking up details of a customer's order or import result | Business controller |

Health answers questions about application health and has status aggregation rules; an endpoint returning arbitrary JSON with a `status` field does not automatically participate in that mechanism. You can extend it with a `HealthIndicator` instead of creating `/actuator/myhealth` with similar content.

For time-series measurements, such as pending jobs per minute or processing duration percentiles, measure them with metrics. Having a monitoring tool repeatedly poll a custom JSON endpoint often leads to rebuilding collection and aggregation capabilities that already exist in the metrics system. See [Spring Boot 3.3 metrics integration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

A diagnostic endpoint can still return a snapshot of current state to help an on-call operator investigate. It serves a different purpose from metric charts, alerts, and historical analysis.

## 5. Commonly Misclassified Scenarios

### 5.1. Looking Up the Status of a Data Import Run

Requirement: “A customer logs in, sees how many rows succeeded in their import run, and downloads the failed rows.”

This is a business controller, such as a contract under `/api/imports/{importId}`. It needs ownership checks, pagination or result downloading, business statuses, and appropriate error handling. It does not become operational data just because the work executes asynchronously.

### 5.2. Inspecting the Data Import Processor

Requirement: “An on-call operator wants to know whether this application instance is paused, how many workers are active, and how many jobs are still pending.”

You can consider an Actuator endpoint if a diagnostic snapshot is needed and built-in capabilities are not sufficient. If you only need to track the pending job count over time, prefer metrics.

Make sure to state “this application instance” clearly. When the system runs multiple instances, in-memory data from one instance does not automatically become the total across the entire cluster.

### 5.3. Administrator Approving a Refund

Even if only administrators are allowed to call it, this is still a business operation: it involves refund rules, limits, approval authority, and decision history. Use a business admin API with the appropriate service.

Calling this API from a command-line tool instead of a UI does not change the nature of the use case either.

### 5.4. Pausing a Consumer for Maintenance

This can be an operational action suitable for Actuator, if the control scope is clear and the service supports it safely. You need to determine whether pausing affects one instance, a group, or the whole cluster; whether in-flight jobs are allowed to finish; and whether repeated calls produce different side effects.

If the operation is actually “cancel all orders for customer X”, it has crossed into business logic. Do not hide such an action behind a technical name like `repair` or `maintenance`.

### 5.5. A Customer Support Screen

This screen might need two sources:

- Customer import run details fetched from the business API.
- Processor operational state fetched from a management source, only when the viewer has permission.

Do not let the browser call a sensitive management endpoint directly just because it is convenient to fetch the data. Access architecture and permissions must match each source.

## 6. What Mechanism Does Actuator Provide for This Choice?

A custom Actuator endpoint is declared with an identifier and operations. A technology-neutral definition can be adapted to HTTP or JMX when configured accordingly. When only HTTP is needed, specialized options like `@WebEndpoint` exist.

Web operations follow Actuator conventions: `@ReadOperation` maps to GET, `@WriteOperation` maps to POST, and `@DeleteOperation` maps to DELETE. This is not a replacement for all capabilities of a REST controller.

Input parameters of a technology-neutral endpoint must adhere to supported data type contracts; you cannot take a controller method using `@RequestBody` with a complex object, simply swap the annotation, and expect it to work. Returning a result object can still be supported, such as the record in the example below. Distinguish **input types** from **return objects** when reading the [custom endpoint creation guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

If an API needs a rich HTTP contract, use-case-specific validation, response control, and business errors, a controller usually expresses it more clearly. For an operational need that requires web-specific capabilities, consider a web-specific extension point instead of forcing everything into `@Endpoint`.

Both endpoints and controllers should be thin reception layers:

```text
Operations tool -> Actuator Endpoint -> State/Control Service
User            -> API Controller    -> Business Use-Case Service
```

They may share an underlying data-reading component when sensible, but the two contracts do not need to return the same DTO or have the same access permissions.

## 7. Runnable Example: Processor State Snapshot

The example uses Java 21, Maven, and Spring Boot 3.3.0. It only provides simulated operational information and does not implement actual data import business logic. The goal is to see how an endpoint is registered, exposed, and invoked.

Directory structure:

```text
endpoint-choice-demo/
├── pom.xml
└── src/main/
    ├── java/example/endpointchoice/OperationsDemoApplication.java
    └── resources/application.properties
```

### 7.1. Declaring Dependencies

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>endpoint-choice-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

This is a standalone example project. In an application that already has a build configuration, add only the appropriate components to the existing structure rather than replacing the entire build with this template.

### 7.2. Separating the State Source from the Endpoint Class

File `src/main/java/example/endpointchoice/OperationsDemoApplication.java`:

```java
package example.endpointchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OperationsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OperationsDemoApplication.class, args);
    }

    @Bean
    WorkerState workerState() {
        return new WorkerState();
    }

    @Bean
    ImportWorkerEndpoint importWorkerEndpoint(WorkerState state) {
        return new ImportWorkerEndpoint(state);
    }

    public record WorkerSnapshot(
            boolean paused, int activeWorkers, int pendingJobs) {
    }

    public static class WorkerState {
        public WorkerSnapshot snapshot() {
            return new WorkerSnapshot(false, 2, 7);
        }
    }

    @Endpoint(id = "importworker")
    public static class ImportWorkerEndpoint {
        private final WorkerState state;

        public ImportWorkerEndpoint(WorkerState state) {
            this.state = state;
        }

        @ReadOperation
        public WorkerSnapshot snapshot() {
            return state.snapshot();
        }
    }
}
```

How to read the example:

- `WorkerState` is the state source. The numbers 2 and 7 are fixed simulated data.
- `WorkerSnapshot` contains only the operational information needed for the example; there is no customer data or individual job payload.
- `ImportWorkerEndpoint` adapts the ability to read state into an Actuator operation.
- `@Bean` registers the endpoint with Spring; `@Endpoint(id = "importworker")` declares its identifier.
- `@ReadOperation` reads state without dequeuing jobs, restarting workers, or mutating data.

A real application needs to replace `WorkerState.snapshot()` with a consistent state snapshot at an appropriate cost. Do not scan entire business tables or call multiple slow dependencies every time the monitoring system reads the endpoint.

### 7.3. Exposing the Endpoint Properly

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoint.importworker.enabled=true
management.endpoints.web.exposure.include=health,importworker
```

This configuration uses Spring Boot 3.3.x's enablement and exposure mechanisms. It only exposes `health` and `importworker` over the web. The example has no Spring Security library and listens only on loopback for local practice.

**Enabling an endpoint, exposing an endpoint, and authorizing a principal to access it are three distinct decisions.** Setting `enabled=true` does not substitute for exposure. Adding an ID to exposure is not an authentication or authorization rule either.

### 7.4. Running and Observing

From the directory containing `pom.xml`, using JDK 21:

```shell
mvn spring-boot:run
```

In PowerShell in another window:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/importworker
```

Response JSON body:

```json
{"paused":false,"activeWorkers":2,"pendingJobs":7}
```

This is data from the example's state source. It does not mean Spring Boot automatically counts workers or finds your application's queues.

Try sending POST to the read-only endpoint:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" -X POST http://127.0.0.1:8080/actuator/importworker
```

With the example configuration, the resulting status code is `405`, because there is no corresponding POST operation. Do not use this POST to conclude that the endpoint already has the ability to pause workers.

Next, change exposure to:

```properties
management.endpoints.web.exposure.include=health
```

Restart the application and call the URL above again. In the example without a security layer or another mapping, the result is `404` because the endpoint is not exposed over the web. The annotation is still in the code, but that is not enough for the URL to be available.

If you apply this experiment to an application with Spring Security, the security filter may return 401 or 403 before the request reaches the mapping layer. Therefore, do not infer the cause solely from an error code while ignoring the configuration of the actual application.

## 8. Exposure Boundaries and Access Protection

An operational endpoint can reveal how the application works or allow changing technical behavior. Therefore, choosing Actuator must go hand in hand with appropriate access design, not just picking an annotation.

Practical questions to answer:

- Is the endpoint read-only or can it mutate state?
- Which on-call operators or automated tools are allowed to call it? Should read permissions and control permissions be separated?
- Does the returned data contain job payloads, customer information, internal paths, or secrets?
- Is the operation scoped to one instance or the entire system? Can the caller tell that scope?
- Does a state-changing command need to record who performed it and the outcome?

In Spring Boot 3.3, if Spring Security is present and no custom `SecurityFilterChain` is declared, auto-configuration protects actuators other than health. When an application defines its own security filter chain, you must re-verify the rules for management endpoints; do not assume the previous protection mechanism is still retained. See [Actuator security in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

You can separate the management port, for example by adding to the configuration:

```properties
management.server.port=8081
management.server.address=127.0.0.1
```

Then the example's endpoint URL moves to `http://127.0.0.1:8081/actuator/importworker`. Configuring a separate management address is supported when the management port differs from the application port. These options are described in [monitoring and management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Separating the port helps organize operational access paths. It does not grant permissions on its own, nor does it guarantee the port is blocked in every deployment environment. Ordinary business controllers do not automatically move to the management port just because their URL starts with `/actuator`.

## 9. Design Pitfalls to Avoid

| Common Practice | Problem | Adjustment Direction |
| --- | --- | --- |
| Putting staff APIs into Actuator because “only admins use them” | Confuses user permissions with business nature | Classify by use case and data |
| Creating a custom health endpoint returning a `status` field | Does not participate in health aggregation and probes automatically | Consider `HealthIndicator` and health configuration |
| Creating a JSON endpoint to replace all metrics | Must build collection, aggregation, and history yourself | Use metrics for time-series numerical data |
| Reading an endpoint mutates queues or reruns jobs | Read operation has unexpected side effects | Separate queries from control operations |
| Returning lists of business objects via a diagnostic endpoint | Hard to control data exposure and ownership | Return the minimal operational information needed |
| Using in-memory state of one instance as cluster-wide metrics | Wrong conclusions when running multiple application instances | State the scope clearly or build a dedicated aggregation source |
| Adding `@Endpoint` and assuming the URL already exists | Missing bean registration, enablement, or exposure | Check each condition in the actual application |
| Changing a controller path to `/actuator/...` | Does not gain Actuator management mechanisms as expected | Use the right endpoint type and verify mappings |
| Putting every technical action into one “admin” endpoint | Contract and permissions are overly broad and hard to understand | Split by meaningful operational capabilities |

A long-running management operation also needs clear boundaries. If it must create a background job, it needs an appropriate intake, result-tracking, and retry-handling contract. Actuator annotations do not automatically provide a job orchestrator or guarantee at-most-once execution.

## 10. Decision and Verification Exercises

For each requirement below, choose a built-in capability, a custom Actuator endpoint, or a business controller. Explain the purpose, data scope, and who is allowed to call it.

1. A user views the data import results for their own account.
2. An on-call operator checks the paused status and number of active workers of an application instance.
3. An alerting system needs to track pending job counts and processing duration over 24 hours.
4. A support agent approves a refund within their assigned limit.
5. A maintenance tool wants to pause accepting new jobs while letting in-flight jobs finish.
6. The deployment system needs to know whether the application is ready to receive traffic.

Reference hints:

- Requirements 1 and 4 belong to business use cases.
- Requirement 2 may fit a custom diagnostic endpoint if a specialized snapshot is needed.
- Requirement 3 fits metrics and a time-series storage/visualization system.
- Requirement 5 can be an operational capability; scope, transitional states, and control permissions must be clarified before implementation.
- Requirement 6 should consider health/readiness rather than creating an unintegrated custom status endpoint.

Then verify the example in section 7 under three cases: GET returns the right snapshot when exposed; POST does not produce a write operation; removing the ID from exposure makes the URL unavailable in the sample configuration.

A design decision needs concrete reasons: what this capability describes or controls, who uses it, what scope the data belongs to, and why the chosen capability fits that contract.
