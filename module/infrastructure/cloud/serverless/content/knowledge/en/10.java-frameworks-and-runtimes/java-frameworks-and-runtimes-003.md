# Bringing Spring Boot Applications to Serverless Environments

## 1. Spring Boot and the Serverless Execution Model

Spring Boot is typically deployed as a continuously running application: the JVM starts, Spring creates the application context, the embedded server opens an HTTP port, and the application handles many requests over the lifetime of the process. In the serverless function-as-a-service (FaaS) model, the platform receives a trigger and invokes a handler; the handler performs its work within one invocation and returns a result. The platform may spin up multiple parallel execution environments, reuse an environment for subsequent invocations, or tear down an environment when no longer needed.

That does not mean you have to rewrite all your Spring Boot business logic. Most services, repositories, validation, and domain logic can be preserved. The main work is choosing the right adapter, defining the application lifecycle, eliminating assumptions about local state, and configuring resources according to how the serverless platform operates.

Within the scope of CLOUD_SERVERLESS, the goal is to deploy Java functions triggered by HTTP, messages, or events. Learners need to handle triggers, state, access control, retries, idempotency, cold starts, scaling, and cost. Therefore, moving Spring Boot is not just packaging a JAR and uploading it to the platform; you must review how requests enter the application and how the application consumes resources in each invocation.

A Spring Boot application can be brought to a serverless environment in several ways:

| Deployment approach | How it works | Suitable when |
|---|---|---|
| Keep Spring MVC with a FaaS adapter | API Gateway converts HTTP events into servlet requests; the adapter invokes Spring MVC and translates the response back to the platform format | You already have a Spring Boot REST API and want to keep controllers/filters/interceptors |
| Spring Cloud Function | Declare business logic as `Function`, `Consumer`, or `Supplier`; the adapter translates triggers into function calls | The application is message/event-oriented or you want to decouple business logic from HTTP |
| Serverless container | Run the Spring Boot application as a container that can scale to zero or scale per request | You need to keep a web server model, native libraries, or long-lived protocols that FaaS does not fit |

Serverless containers have a different operational model from pure FaaS: the application still has a process and web server, even though the platform manages infrastructure and autoscaling. You must choose the right model based on runtime duration, protocols, and the platform's billing model.

## 2. Auditing the Application Before Migration

Before changing configurations, identify the assumptions of your current application:

- Does the application depend on a fixed HTTP port or a continuously running embedded server?
- Does it store sessions, caches, uploaded files, or business state in local memory?
- Does it use `@Scheduled`, background threads, executors, or infinite consumer loops?
- Does it open database connections, broker connections, or HTTP clients right at startup?
- Does it require WebSockets, streaming responses, long polling, or long-running requests?
- Does it depend on the local filesystem, working directory, or data persisting across multiple calls?
- Does it need to initialize many beans, scan the classpath, or fetch remote configuration during startup?
- Are there tasks requiring retries, checkpoints, idempotency, or compensation?

Plain Java business components are usually easy to reuse. Components that require careful review include the web server, session store, schedulers, thread pools, connection pools, file storage, and libraries assuming a long-lived process.

A safe approach is to separate the application layer from the adapter:

```text
HTTP / Queue / Stream Trigger
            |
            v
  API Gateway or FaaS Adapter
            |
            v
      Spring Application
            |
     +------+------+
     |             |
     v             v
 Domain Service  Application Service
     |             |
     +------+------+
            |
            v
 Repository / HTTP Client / Event Publisher
            |
            v
 Database / Object Storage / Queue / Event Bus
```

A controller or function adapter should only coordinate the protocol, validate input, and invoke the application service. Business rules should reside in services so they can be tested independently and reused across HTTP, queues, or streams.

## 3. Choosing an Adapter: Spring MVC or Spring Cloud Function?

### Keeping Spring MVC with a Serverless Adapter

If the application already has many `@RestController`s, Spring Security filters, validation, and exception handlers, you can use an adapter that emulates servlet requests/responses. For AWS Lambda and API Gateway, AWS Serverless Java Container is an option. The adapter converts the proxy event into a request Spring MVC understands, then converts the servlet response back into the API Gateway format.

Advantages:

- Retains the controller structure and most existing web libraries.
- Allows reusing filters, interceptors, validation, and Spring Security.
- Well-suited for request/response REST APIs.

Trade-offs:

- The Spring context and servlet stack increase artifact size and cold start time.
- Must map the exact API Gateway event format; REST API proxy v1 and HTTP API v2 have different structures.
- Features relying on long-lived connections or server push may not fit request/response FaaS.
- The adapter does not make every behavior of a long-lived web server completely identical to a traditional servlet environment.

### Using Spring Cloud Function

Spring Cloud Function lets you define business logic as Java functions. The platform adapter converts HTTP requests, messages, or events into function inputs. This approach works well when processing logic is protocol-independent.

Example:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    Function<CreateOrderCommand, OrderAccepted> createOrder(
            OrderApplicationService orderService) {
        return orderService::create;
    }
}
```

Here `CreateOrderCommand`, `OrderAccepted`, and `OrderApplicationService` are the application's data types/business classes. The serverless adapter selects the function to call and converts the payload according to the platform's contract. Handler names, dependencies, and packaging configuration must match the adapter/version in use; do not assume a single handler class works across all clouds.

Spring Cloud Function decouples business logic from HTTP or message transports, improving testability and reuse. However, if the application needs the full servlet stack, complex filters, or many REST endpoints, converting everything to functions can require significant changes.

### Choosing Based on Workload Characteristics

| Need | Approach to consider first |
|---|---|
| Existing REST API, want to keep controllers | Spring MVC + serverless adapter |
| Event/message processing, minimal servlet dependency | Spring Cloud Function |
| Long-running work, continuous background processes | Queue + long-lived worker or serverless container/workflow |
| WebSockets or persistent connections | Managed WebSocket service or suitable serverless container |
| Fast startup, small artifact, single simple task | Lean Java function, possibly without full Spring Boot |
| Need to keep existing web app with minimal changes | Serverless container or request-scaling container platform |

Do not move to FaaS just because an application uses Spring Boot. Compare cold starts, execution duration, request frequency, connections, cost, and operational effort against the container model.

## 4. Spring ApplicationContext Lifecycle in FaaS

Spring Boot creates the application context, initializes beans, and runs startup callbacks. With an appropriate adapter, the context is typically initialized when the execution environment starts and can be reused across multiple invocations on the same environment. The platform does not guarantee that an instance will live forever or that the next request will hit the same instance.

Therefore:

- Singleton beans can hold safely shared dependencies such as thread-safe HTTP clients or serializers.
- Do not place per-request or per-user data in fields of singleton beans.
- Do not use static maps to store sessions or business state.
- Do not assume `@PostConstruct` runs once for the entire application; it runs per execution environment context lifecycle.
- Do not rely on shutdown hooks to persist critical data; the environment may be terminated without sufficient shutdown time.
- Lazy bean initialization can reduce initial startup time but shifts initialization latency to the first invocation that uses that bean.

Unsafe example:

```java
@Service
public class CurrentUserCache {
    // Wrong: user data may be shared across invocations.
    private String currentUserId;

    public void setCurrentUser(String userId) {
        this.currentUserId = userId;
    }
}
```

Instead, pass user context via method parameters or a properly managed per-invocation request-scoped context. If state must persist across multiple requests, use a shared session store or database.

An execution environment may process invocations concurrently depending on the platform and adapter, or only sequentially per environment. Do not rely on that assumption to omit synchronization. Use thread-safe beans and avoid mutable shared state. If you have a local cache, treat it as a best-effort cache that can be lost or differ across instances.

## 5. Spring Boot MVC Example with AWS Serverless Java Container

This example illustrates Spring Boot 3 invoked via an API Gateway REST API proxy v1 event and AWS Lambda. The application still uses `@RestController`; the handler class acts as an adapter between the Lambda runtime and the servlet application.

Spring Boot application:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
class HealthController {
    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("UP");
    }
}

record HealthResponse(String status) {}
```

Lambda stream handler:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import com.amazonaws.serverless.exceptions.ContainerInitializationException;
import com.amazonaws.serverless.proxy.model.AwsProxyRequest;
import com.amazonaws.serverless.proxy.model.AwsProxyResponse;
import com.amazonaws.serverless.proxy.spring.SpringBootLambdaContainerHandler;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;

public class StreamLambdaHandler implements RequestStreamHandler {
    private static final SpringBootLambdaContainerHandler<AwsProxyRequest, AwsProxyResponse> HANDLER;

    static {
        try {
            HANDLER = SpringBootLambdaContainerHandler.getAwsProxyHandler(
                    OrdersApplication.class);
        } catch (ContainerInitializationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @Override
    public void handleRequest(
            InputStream input,
            OutputStream output,
            Context context) throws IOException {
        HANDLER.proxyStream(input, output, context);
    }
}
```

The handler above uses the API Gateway REST API v1 proxy event format. If using API Gateway HTTP API v2, you must choose a handler/adapter that supports v2 payloads and configure the corresponding integration; do not feed v2 events into a v1 parser. Class and method names may vary across versions of AWS Serverless Java Container, so align dependency versions with the examples and documentation for your chosen release.

Required dependencies typically include the Spring Boot 3 adapter of AWS Serverless Java Container and AWS Lambda Java Core. Use versions compatible with your project's Java/Spring Boot versions, declare them in Maven or Gradle, and package all required dependencies into the artifact. The handler configured in Lambda must point to the `StreamLambdaHandler` class in the format required by the runtime.

This code snippet illustrates the integration structure; a production project needs build configuration, API Gateway routes, IAM roles, environment variables, logging, security filters, and sample event tests. Do not start a standalone embedded HTTP server inside the Lambda handler when the adapter is already responsible for routing requests into the servlet stack.

## 6. Separating Business Logic from HTTP Controllers

A good controller only orchestrates the protocol. Business logic should live in application services so HTTP, messages, and workflows can invoke the same logic.

```java
public record CreateOrderCommand(
        String customerId,
        String sku,
        int quantity,
        String idempotencyKey) {}

public record OrderAccepted(String orderId, String status) {}

@Service
public class OrderApplicationService {
    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderAccepted create(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // In a real application, the repository uses transactions and idempotency keys.
        Order order = orders.createOnce(command);
        return new OrderAccepted(order.id(), order.status());
    }
}
```

The MVC controller can receive an HTTP DTO and convert it into a command. Spring Cloud Function can receive the same command from an event adapter. Separating these layers allows unit testing services without constructing API Gateway events or a Spring MVC context.

Do not let API Gateway or message broker DTOs become domain models. The adapter is responsible for converting transport types into internal commands and converting business results into HTTP responses or events.

## 7. Statelessness and Externalizing State

FaaS can scale from one instance to many instances. Each instance has its own memory and an unguaranteed lifetime. Data that must survive across invocations must be stored in durable systems:

| Data | Appropriate storage |
|---|---|
| Orders, payments, business state | Database or data store with appropriate transactions |
| User sessions | Shared session store or tokens with a revocation strategy |
| Uploaded files and output files | Object storage |
| Shared cache | Managed cache; cached data must be rebuildable |
| Pending messages | Queue or event stream |
| Long-running workflow progress | Workflow engine or durable state store |
| Idempotency keys and inbox | Database with appropriate unique constraints/TTL |

Temporary files in `/tmp` or a temp directory can be useful within a single invocation, but must not be treated as durable storage. If temp files remain when an environment is reused, old data could leak to another invocation. Use randomized filenames, restricted permissions, and delete sensitive data after use.

Do not use `@SessionAttributes`, in-memory HTTP sessions, or local caches as the source of truth in multi-instance environments. If sessions are needed, configure Spring Session with a shared store or use an appropriate authentication mechanism.

## 8. Database Connections and Scale-Out

A common issue when moving Spring Boot to FaaS is that each execution environment creates its own connection pool. If a function scales to 100 instances and each instance opens a pool of up to 10 connections, the database could face around 1,000 connections from that function alone, not counting other applications.

Estimate total connections with the approximate formula:

\[
Connections_{max} \approx Instances_{max} \times PoolSize_{perInstance}
\]

This is a theoretical configuration upper bound; actual connections depend on whether the pool allocates lazily or eagerly, concurrent invocations, and how long instances are kept warm. Nevertheless, this calculation prevents FaaS from opening more connections than the database can handle.

Recommendations:

- Set a small max pool size aligned with concurrency.
- Create datasources/clients at the context lifecycle level when safely reusable, without opening too many connections at startup.
- Use a connection proxy/pooling service if supported by the platform and database.
- Configure connect timeouts, socket timeouts, and query timeouts.
- Close transactions quickly; do not hold connections open while waiting on HTTP providers or unrelated tasks.
- Cap function concurrency according to database capacity.
- Monitor connection counts, pool wait times, timeouts, and pool exhaustion errors.

Do not simply increase pool size to handle more invocations. If the database is the bottleneck, increasing concurrency can cause wait times and errors to spike sharply. You can offload part of the work to a queue to smooth write rates.

## 9. Cold Starts and Spring Boot Startup Time

Cold start is the latency incurred when the platform must create a new execution environment before handling an invocation. For Spring Boot, startup time can include:

1. Preparing the runtime and downloading the artifact.
2. Starting the JVM or native runtime.
3. Loading classes and dependencies.
4. Component scanning, auto-configuration, and creating Spring beans.
5. Initializing logging, serializers, clients, and datasources.
6. Handling the first invocation.

Spring Boot has a rich ecosystem, but auto-configuration and reflection can increase startup time and artifact size. Not every bean needs to be initialized for a small function.

### Ways to Reduce Cold Starts

- Include only necessary dependencies in the artifact; avoid unused starters.
- Narrow component scanning and tune auto-configuration appropriately.
- Avoid calling remote services or running heavy queries in constructors/`@PostConstruct`.
- Reuse thread-safe HTTP clients, serializers, and SDK clients.
- Measure initialization time per bean group before optimizing.
- Use provisioned/pre-warmed capacity if SLAs require consistent latency and cost permits.
- Evaluate runtime snapshots or JVM optimizations if supported by the provider.
- Consider Spring AOT/GraalVM Native Image when the application is compatible and startup gains are substantial.

Do not optimize based solely on a single cold start measurement. Measure p50/p95/p99 latency, cold start rate, memory, CPU, and cost under realistic load. A solution that speeds up startup while increasing memory or build complexity may not yield a net benefit.

### Spring AOT and GraalVM Native Image

Spring AOT performs part of the application analysis at build time. GraalVM Native Image compiles the application into a native executable, often reducing startup time and footprint for certain workloads. In return, native builds can be more complex, and features relying on reflection, dynamic class loading, proxies, or resources require appropriate hints.

Before choosing native image:

- Verify all libraries and drivers support native image.
- Add runtime hints for reflection, serialization, proxies, and resources as needed.
- Run integration tests on the native artifact, not just JVM mode.
- Measure memory and throughput; native is not automatically faster for every workload.
- Evaluate build times, debugging experience, and production support.

JVM mode remains the right choice when broad library compatibility is needed, JIT optimizes long-running workloads, or native build pipelines are not yet worth the investment.

## 10. Packaging and Artifact Deployment

There are two common packaging approaches:

### ZIP/JAR for Managed Java Runtimes

The artifact must include the proper handler, required dependencies, and the structure supported by the runtime. With the Spring MVC adapter, package the Spring Boot application together with AWS Serverless Java Container and Lambda Java Core. You can use the Maven Shade Plugin or the packaging mechanism recommended by the adapter. Verify that resources, service loaders, and configuration files are not overwritten when building a fat JAR.

### Container Image

A container image packages both the runtime and the application. This approach is useful when you need control over OS packages, native libraries, or packaging layout. However, you must use a base image compatible with the serverless platform, configure the right entrypoint/handler, and keep the image lean. Container images do not eliminate cold starts; image size, JVM startup, and Spring context initialization still affect startup time.

The build pipeline should include these steps:

1. Run unit tests and check dependencies.
2. Build the JAR or image with the production profile.
3. Verify the artifact contains the required handler, resources, and dependencies.
4. Scan dependencies and images per your organization's security process.
5. Deploy to a test environment with real or representative sample events.
6. Run smoke tests and inspect logs/metrics.
7. Shift traffic using a rollback-capable strategy.

Do not embed secrets in JARs, image layers, or configuration files committed to source control. Use a secret manager, parameter store, or the platform's secret injection mechanism.

## 11. Environment-Specific Configuration

Spring Boot can read configuration from `application.yml`, profiles, and environment variables. In serverless, deployment configuration should be passed via environment variables or a secret manager, for example:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX:2}
      connection-timeout: ${DB_CONNECTION_TIMEOUT_MS:3000}

app:
  payment:
    base-url: ${PAYMENT_BASE_URL}
    timeout-ms: ${PAYMENT_TIMEOUT_MS:5000}
```

This example only illustrates configuration; default values must be tuned for the actual runtime and load. Database passwords should not be stored in plain environment variables if the platform provides a dedicated secret manager. Restrict the function's permissions so it can only read the secrets it needs.

Avoid calling the secret manager and config service repeatedly on every request if they can be safely cached for the environment lifecycle. However, when secrets rotate, you need a refresh strategy or cache TTL. Never keep secrets in logs or exception messages.

## 12. HTTP Triggers and Request/Response Limits

With HTTP triggers, API Gateway or an HTTP adapter typically handles TLS termination, routing, preliminary authentication, throttling, and converting requests into events. The Java function processes the request and returns a status code, headers, and body according to the integration protocol.

Pay attention to:

- API Gateway has its own timeout, payload size, and header limits.
- Function timeout does not necessarily equal the gateway timeout.
- Requests may be retried by clients when the client times out even if the function already completed.
- Idempotency keys are needed for creating orders, processing payments, or critical writes.
- CORS must be configured at the right layer, and error responses also need appropriate headers.
- Do not hold an HTTP request open for long periods waiting for background work; return an acceptance code and track status via API/events if business requirements permit.

If work takes longer than request/response limits, accept the request, persist durable state, send a message or start a workflow, and return `202 Accepted` with a tracking ID. The client polls status or receives a webhook/callback upon completion.

## 13. Message and Event Triggers

Spring Boot services can process messages using Spring Cloud Function or a platform-specific adapter. With queue/stream triggers, the function often receives a batch of events and must return results according to the trigger's acknowledgement/checkpoint semantics.

Design requirements:

- Parse and validate each record; invalid payloads should be quarantined or sent to a DLQ.
- Process idempotently because messages can be redelivered.
- Acknowledge/checkpoint only after side effects are durably persisted.
- With batches, understand partial batch failure so one bad record does not force unnecessary reprocessing of the entire batch.
- Preserve ordering within a partition/group if required by business logic.
- Limit concurrency and batch size according to database or downstream API capacity.
- Propagate `eventId`, `correlationId`, and tenant context per contract.

Do not run a `while(true)` loop to poll a queue inside a function when the event source mapping is already responsible for polling. In a long-lived worker container model, a consumer loop may make sense, but that is a different deployment model requiring shutdown, lease, rebalance, and checkpoint management.

## 14. Security and Access Control

Each function should run with its own service identity and least-privilege permissions. A function reading orders does not need permission to delete buckets; a function sending emails does not need permission to read the entire customer table. Separating roles by responsibility limits the blast radius if a dependency or function is compromised.

Required layers of defense:

- Authenticate callers at the API gateway or Spring Security; enforce authorization per resource.
- Validate tenant context and do not trust arbitrary tenant IDs from payloads.
- Use IAM/service accounts for the function to access queues, database proxies, object storage, and secrets.
- Encrypt data in transit and at rest; restrict access to logs and DLQs.
- Do not bundle secrets into artifacts or log full requests.
- Validate payloads and enforce size limits to mitigate malicious input risks.
- Keep dependencies and base images updated; scan for CVEs in the pipeline.

If using Spring Security, verify that the adapter forwards headers, methods, paths, and identity context accurately. With an API Gateway authorizer, determine which claims are trusted and how they map to a Spring Security principal. Never rely solely on a client-supplied header to grant access.

## 15. Retries, Timeouts, and Idempotency in Spring Boot FaaS

A function can be invoked again due to trigger retries, workflow retries, client retries, or network errors. If multiple layers retry without coordination, calls to dependencies can multiply. Define a retry owner and an overall retry budget.

In Spring Boot:

- Configure explicit connect/read/request timeouts for `RestClient`, `WebClient`, or whichever HTTP client is in use.
- Retry only transient errors such as connection timeouts, 429, or 503 according to dependency policies.
- Use backoff and jitter, capping attempts and total deadline.
- Do not retry validation errors, authorization failures, or business rejections.
- Tie a stable idempotency key to a single business action.
- Record processing markers in the same transaction as data updates whenever possible.
- If a timeout leaves the external outcome uncertain, query status before resending.

For example, `OrderApplicationService.create` should implement `createOnce` using a unique constraint on the idempotency key. If two invocations receive the same request due to a client retry, the database creates only one order and returns the existing result. Do not rely on a `synchronized` block in the JVM because separate function instances do not share locks.

## 16. Background Tasks and Schedulers

Traditional Spring Boot applications often use `@Scheduled` or `@Async`. In FaaS, you should not assume an instance stays alive continuously to run schedulers or finish background tasks after the request returns.

Replace them with:

- A managed scheduler emitting scheduled events to trigger functions.
- A queue for background work needing retries and load leveling.
- A workflow engine for multi-step or long-running processes.
- An event bus for independent consumers reacting to business changes.

`@Async` can be used within the scope of an invocation if the function waits for completion before returning a response. Do not spawn threads and return success while work is still running; the runtime may freeze or terminate the environment. If work must continue independently, enqueue a job or start a workflow before returning a response.

If using a managed scheduler, design idempotency around the schedule interval or business date to avoid triggering the same period twice. Handle timezones, daylight saving time, catch-up runs, and late-arriving triggers.

## 17. Observability: Logs, Metrics, and Traces

A request can travel through API Gateway, the Lambda adapter, Spring filters, services, the database, and an event bus. Logs should be structured and carry a correlation ID or trace context across all layers.

Useful information:

- Platform-assigned invocation/request ID.
- `correlationId`, `eventId`, `orderId`, or business keys.
- Function name/version, trigger type, and processing duration.
- Cold start indicator if provided by the runtime.
- Database pool wait time, dependency latency, and timeouts.
- Retry attempts, idempotency outcomes, and DLQ/partial batch failures.
- Business outcome and stable error codes.

Metrics to monitor include invocation count, error rate, p50/p95/p99 duration, timeouts, concurrency, throttling, cold starts, memory, queue age/lag, database connections, and cost per business unit. Do not log cookies, bearer tokens, secrets, or sensitive full payloads. Use trace sampling under high traffic while retaining enough data to investigate rare failures.

Spring Boot Actuator can expose health and metric endpoints, but you should not publicly expose all endpoints by default in FaaS. Enable only required metrics, protect endpoints, and integrate with the platform's observability mechanisms.

## 18. Testing Serverless Spring Boot Applications

Testing should be divided along boundaries:

| Test type | Objective | Example |
|---|---|---|
| Unit test | Verify business logic without framework dependencies | Test `OrderApplicationService` with fake/mock repositories |
| Spring slice test | Verify controllers, validation, security, or serialization | `@WebMvcTest` for controllers |
| Context test | Verify Spring bean graph and configuration | `@SpringBootTest` with mocked dependencies |
| Adapter contract test | Verify event/API Gateway payloads are converted properly | Sample v1/v2 events, headers, and responses |
| Integration test | Verify database, queue, secrets, and external APIs via test environment | Testcontainers or managed test resources |
| Deployment smoke test | Verify the real artifact after deployment | Call endpoints, send events, inspect logs and permissions |
| Failure test | Verify retries, timeouts, duplicates, and partial batches | Disconnect database, return 429/503, kill function mid-side-effect |

Unit tests do not prove the event adapter works. Integration tests must use the exact trigger payload format, especially distinguishing API Gateway REST v1 and HTTP API v2. Test both success and error responses, CORS, serialization, security context, and request IDs.

Test cold starts and warm invocations separately. If using native image, run tests on the native artifact; JVM tests do not catch all reflection or resource hint issues. If using provisioned capacity, test both initialization time and the cost of maintaining capacity.

## 19. Safe Deployment and Rollback

A deployment roadmap can include:

1. Separate business logic from controllers and runtime details.
2. Select an HTTP adapter or function adapter matching the trigger.
3. Move sessions, caches, and persistent state to shared services.
4. Cap connection pools, concurrency, timeouts, and batch sizes.
5. Package the artifact and configure the runtime/handler.
6. Grant least-privilege permissions, configure secrets, and set up network access.
7. Deploy to dev/staging; run contract tests and smoke tests.
8. Measure cold starts, warm latency, memory, throughput, and cost.
9. Shift traffic using canary or alias/version routing if supported by the platform.
10. Monitor error rates, timeouts, lag, and business state; roll back if thresholds are breached.

When changing event or database schemas, maintain compatibility between old and new versions while in-flight invocations or backlogged messages exist. Rolling back a function does not automatically roll back side effects that already occurred. You need backward-compatible migrations, idempotency, and compensation processes when necessary.

## 20. When Is Spring Boot Not a Good Fit for a Function?

Spring Boot is useful when an application needs dependency injection, rich configuration, validation, security, and the Spring ecosystem. However, a small function that only transforms payloads or handles a simple message may not need the entire Spring context.

Consider plain Java or a lighter-startup framework when:

- The function has only one handler and a few dependencies.
- Cold start latency is a strict requirement.
- Small artifact size and fast build/deploy times are critical.
- Servlets, auto-configuration, or most of the Spring ecosystem are not needed.

Consider serverless containers or long-lived workers when:

- Work is long-running or requires continuous background execution.
- Persistent WebSocket, streaming, or stateful protocol connections are required.
- The application needs long-term control over processes or threads.
- Steady workloads with continuous runtime make FaaS more expensive than containers.

Decisions should be based on measured workload metrics: invocation rate, execution duration, memory, cold starts, dependency latency, concurrency, data transfer, and cost. There is no single Java framework best suited for every function.

## 21. Checklist Before Moving Spring Boot to Serverless

- [ ] Clearly chosen between FaaS, Spring MVC adapter, Spring Cloud Function, or serverless container.
- [ ] Identified exact event formats for HTTP/queue/stream triggers.
- [ ] Business logic is decoupled from controllers and adapters.
- [ ] ApplicationContext and singleton beans do not retain per-request/per-user state.
- [ ] Sessions, critical caches, and business state reside in shared systems.
- [ ] Not relying on `@Scheduled`, background threads, or local files for long-running work.
- [ ] Connection pools and concurrency fit database limits.
- [ ] Dependency, function, gateway, and workflow timeouts are coordinated.
- [ ] Retries are bounded; side effects have idempotency and reconciliation.
- [ ] Cold starts have been measured; unnecessary dependencies and beans have been removed.
- [ ] Native/AOT is chosen only after verifying compatibility and running integration tests.
- [ ] Artifacts contain the required handler, dependencies, resources, and configuration.
- [ ] Secrets are managed outside the artifact; the function has least-privilege permissions.
- [ ] Logs/metrics/traces include correlation IDs without exposing credentials or sensitive data.
- [ ] Tested adapter contracts, duplicates, timeouts, cold starts, and real deployments.
- [ ] Canary/rollback strategy and schema compatibility are in place during version transitions.

## Conclusion

Bringing Spring Boot to serverless is a process of adapting the application's lifecycle and integration boundaries to the invocation model, not merely changing how it is packaged. The Spring MVC adapter helps preserve existing REST APIs; Spring Cloud Function fits event-driven logic; serverless containers are the right choice when long-lived web processes are needed. Whichever path you choose, the application must be stateless across invocations, store state in shared services, control connections and concurrency, optimize cold starts, protect access permissions, and design for retries and idempotency. Measuring latency, throughput, and cost under realistic workloads will determine whether Spring Boot is the right fit for each function.
