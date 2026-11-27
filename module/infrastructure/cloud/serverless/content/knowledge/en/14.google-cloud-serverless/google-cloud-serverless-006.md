# On-demand container execution with Cloud Run services

Cloud Run services is Google Cloud's serverless platform for running containers that receive requests over HTTP or gRPC. The development team packages a Java application with its runtime and libraries into a container image, deploys the image to Cloud Run, and configures how the service receives traffic, scales instances, and bounds resources. Google Cloud manages the container-running infrastructure and automatically adjusts the number of instances according to load.

The key point is that Cloud Run runs **a container provided by the application**. The application still has to start a web server, listen on the right port, handle multiple concurrent requests, manage state, and close resources properly. The serverless model reduces server operations, but does not eliminate the responsibility of designing a secure and scalable HTTP service.

This lesson focuses on request-driven Cloud Run services, from the container contract and revision/instance lifecycle to concurrency, autoscaling, Java deployment, and production operations.

## Learning objectives

After this lesson, you will be able to:

- Explain how a Cloud Run service executes containers on demand per request.
- Distinguish service, revision, and instance.
- Package a Java application into a container image that satisfies the Cloud Run contract.
- Configure concurrency, min/max instances, timeouts, and resources.
- Understand scale-to-zero, cold starts, and the impact of CPU configuration.
- Design stateless applications, handle concurrent requests, and shut down gracefully.
- Deploy new revisions, split traffic, and roll back.
- Configure IAM invocation, service identity, and cost observability.

## 1. What are Cloud Run services?

A **Cloud Run service** is a service deployed from a container image that exposes an endpoint to receive requests. Cloud Run creates container instances when traffic arrives, routes requests to suitable instances, and scales the number of instances up or down according to demand and configured limits.

Typically suitable workloads:

- REST APIs or HTTP backends written in Java/Spring Boot.
- gRPC APIs between services.
- Webhook receivers from external systems.
- Backends for web or mobile applications.
- Services handling short or medium requests, calling databases, caches, object storage, and other APIs.
- HTTP endpoints receiving push events from Pub/Sub or Eventarc.

Cloud Run services fit applications that need to serve requests continuously whenever traffic arrives. If the work is batch processing or runs to completion without needing an endpoint waiting for requests, consider Cloud Run Jobs. If you want to deploy a function in an event-driven model without managing containers yourself, Cloud Run functions is another option in the Cloud Run ecosystem.

### What Cloud Run manages vs. what the application manages

| Component | Managed by Cloud Run | Managed by the development team |
|---|---|---|
| Infrastructure | Servers, scheduling, container runtime environment, and autoscaling | Selecting region, resources, and service configuration |
| Container | Creating instances from images, distributing requests | Building images, runtime, dependencies, and entrypoint |
| Networking | HTTPS endpoint, ingress, and configured connectivity | HTTP routing, TLS on downstream connections, application authentication |
| Scaling | Scaling instances up/down based on load and limits | Concurrency, min/max instances, downstream dependency capacity |
| Lifecycle | Starting and stopping instances on demand | Fast startup, handling SIGTERM, no reliance on instance memory |
| Data | Providing connectivity to cloud services | Durable state storage, transactions, backups, and idempotency |
| Security | IAM integration, service identity, and secret integration | Least-privilege permissions, request authentication, and data protection |

Cloud Run does not automatically turn an application with in-RAM state into a safely distributed application. If multiple instances handle requests simultaneously, business data must be persisted in a service with appropriate durability and semantics.

## 2. Service, revision, and instance

These three concepts appear frequently during deployment and operations.

- **Service:** the logical name and endpoint of the application, e.g., `orders-api`.
- **Revision:** an immutable snapshot of the service configuration and container image at deploy time. Each deployment of new configuration or a new image typically creates a new revision.
- **Instance:** a running container instantiated from a specific revision. One revision can have multiple instances as traffic increases.

~~~mermaid
flowchart TD
    A["Cloud Run service: orders-api"] --> B["Revision 00001"]
    A --> C["Revision 00002"]
    B --> D["Instance A"]
    B --> E["Instance B"]
    C --> F["Instance C"]
    G["HTTPS traffic"] --> H["Traffic routing"]
    H --> B
    H --> C
~~~

A service is the stable access point. A revision preserves deployment history and can receive a share of traffic. An instance is the container execution unit; the number of instances can fluctuate while the service retains the same URL.

A new deployment does not necessarily switch all requests immediately to the new revision if traffic splitting is configured. You can deploy a new revision for staging, route a small percentage of traffic to it, and gradually increase the share as metrics meet targets.

## 3. Cloud Run container contract

The container image must satisfy several requirements so Cloud Run can route requests to the application.

### Listening on the provided port

Cloud Run passes the `PORT` environment variable to the container. The application must listen on this port and bind to `0.0.0.0`, meaning all network interfaces inside the container.

Do not bind only to `127.0.0.1` or `localhost`, because requests from Cloud Run's proxy must reach the container's network interface. Do not hardcode a port that differs from the service configuration either.

With Spring Boot, you can configure:

~~~properties
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

`EXPOSE 8080` in a Dockerfile is merely metadata describing the image's port; it does not make the application listen on that port automatically. The web server inside the process must actually bind to `PORT`.

### Container must start up and accept requests

The application needs to complete startup within platform and probe limits. Avoid loading large datasets, calling many external APIs, or running long migrations during startup if unnecessary. Heavy initialization steps increase cold starts and can prevent the instance from becoming ready in time.

Cloud Run supports startup probes and liveness probes to check container health as configured. Health endpoints should reflect actual readiness to serve; do not return healthy when the service cannot yet accept requests or essential dependencies are not ready.

### Container must not rely on a durable local filesystem

The writable filesystem inside a container is ephemeral and its lifecycle is tied to the instance; local disk is not a place for long-term state storage. Temporary disk writes also consume memory resources according to Cloud Run's execution environment characteristics.

Use Cloud Storage, a database, or a durable storage service for files and data that must survive after an instance stops. Temporary files may be used within a single request if the application cleans them up and does not assume the next request will hit the same instance.

## 4. Java application example with Spring Boot

A simple Java service can expose a health check endpoint and an order-reading endpoint. The example uses Java 21 and Spring Boot 3.

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
@RequestMapping
class OrdersController {

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("ok");
    }

    @GetMapping("/orders/{orderId}")
    public OrderResponse getOrder(@PathVariable String orderId) {
        // Replace with a service/repository that enforces access control.
        return new OrderResponse(orderId, "PROCESSING");
    }
}

record HealthResponse(String status) {
}

record OrderResponse(String orderId, String status) {
}
~~~

The application needs the Spring Web dependency and Spring Boot Maven Plugin in `pom.xml`. Configure the port and bind address:

~~~properties
server.port=${PORT:8080}
server.address=0.0.0.0
~~~

The controller above only illustrates the HTTP structure. In a real application, business endpoints must authenticate callers, verify permissions on the order, and read data from a durable store. Never return a mocked status such as `PROCESSING` for production requests.

### Multi-stage Dockerfile

Example Dockerfile using Maven to build the JAR and a JRE image to run it:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/orders-api.jar app.jar
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec java -jar app.jar --server.port=${PORT:-8080} --server.address=0.0.0.0"]
~~~

The example assumes Maven produces `target/orders-api.jar`; configure `finalName` or the Spring Boot build output accordingly in your project. CI should run unit tests and integration tests before building a release image; `-DskipTests` in the example is solely to illustrate the image packaging step.

Use a base image with a JRE matching the application's Java version. You can optimize the image by picking a slim runtime image, omitting unnecessary build files, and running the process as a non-privileged user per your organization's security policy.

## 5. Building and deploying to Cloud Run

A common workflow is building the image, pushing it to Artifact Registry, and deploying the service.

First, you need a Docker repository in Artifact Registry in the selected region along with appropriate build/push permissions. Example using Cloud Build to build the image:

~~~bash
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
~~~

Then deploy:

~~~bash
gcloud run deploy orders-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1 \
  --region REGION \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --concurrency 40 \
  --min 0 \
  --max 20 \
  --timeout 300s \
  --no-allow-unauthenticated
~~~

Replace `REGION`, `PROJECT_ID`, and the service account with values for your environment. The `apps` repository must be created beforehand. The command above requires IAM authentication when invoking the service; if the endpoint must be public, you can configure unauthenticated invocation while still enforcing application-level authentication and authorization if the data requires it.

Illustrative flags:

| Flag | Meaning |
|---|---|
| `--region` | Region where the service is deployed |
| `--service-account` | Service identity the container uses when calling Google Cloud APIs |
| `--concurrency` | Maximum concurrent requests sent to one instance |
| `--min` | Minimum number of instances to maintain |
| `--max` | Maximum instance limit |
| `--timeout` | Maximum duration for a single request |
| `--no-allow-unauthenticated` | Do not grant public invocation permissions |

Cloud Run creates a new revision from the image and deployment configuration. After deploying, inspect the service URL, created revision, ready status, and startup logs before shifting production traffic.

## 6. Request lifecycle and autoscaling

A request typically goes through these steps:

1. The client sends an HTTPS request to the Cloud Run service URL.
2. The ingress and routing layer selects a revision according to traffic allocation.
3. Cloud Run selects a ready instance or spins up a new instance if load exceeds current capacity.
4. The container receives the request on port `PORT`.
5. The Java web server processes the request, calls dependencies, and produces a response.
6. The response is returned to the client; the instance may continue handling other requests or be stopped when no longer needed.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Cloud Run router
    participant I as Container instance
    participant D as Database / API
    C->>R: HTTPS request
    R->>I: Route to ready instance
    I->>D: Query or update
    D-->>I: Result
    I-->>R: HTTP response
    R-->>C: Response
~~~

The autoscaler adjusts instance count based on traffic and resource utilization, within configured limits and quotas. When load rises, Cloud Run can start more instances. When load drops, instances can be scaled down or stopped.

Do not assume instance count increases instantaneously in every situation. Startup time, max instance limits, regional quotas, and traffic ramp rate can introduce latency or cause rejected requests. If your system experiences large traffic bursts, run load tests and design client retries with backoff and jitter.

## 7. Scale-to-zero, cold starts, and minimum instances

When minimum instances is configured to 0, Cloud Run can scale the service down to zero after a period with no traffic. This avoids keeping instances running continuously for infrequently used services.

When the next request arrives, the platform must start a container before processing. This additional startup delay contributes to a **cold start**.

Cold starts are affected by:

- Image size and number of layers to pull.
- JVM and Spring application context startup time.
- Number of beans, libraries, and initialization tasks.
- Database, cache, or API connections opened during startup.
- Startup probe and time until the service is ready to receive requests.

### Reducing cold starts

- Use slim images and remove unnecessary dependencies.
- Avoid calling many external services inside constructors or static initializers.
- Initialize connections only when needed, yet avoid creating a new client on every request.
- Measure startup duration and p95/p99 request latency before optimizing.
- Use minimum instances when first-request latency matters more than the cost of keeping instances warm.
- Consider startup CPU boost if startup is CPU-bound and metrics show this setting helps.

Minimum instances can keep capacity ready to reduce cold starts, at increased cost. Distinguish service-level and revision-level min instances if both are used; verify which configuration applies to production traffic.

## 8. Concurrency: multiple requests on one instance

Cloud Run lets you configure the maximum concurrent requests per instance. A single instance can serve multiple requests simultaneously, depending on the concurrency setting and application capability.

High concurrency can improve CPU and memory utilization and reduce the number of instances required. However, it also increases contention inside the Java application and concurrent load on backend databases/APIs.

### Do not assume requests are processed sequentially

A Spring Boot server typically uses a thread pool to process requests. Concurrent requests can access the same singleton beans, static fields, local caches, or connection pools.

- Request data must stay in local variables or an isolated request context.
- Singleton beans must not hold per-request mutable state.
- Shared collections must be thread-safe if updated concurrently.
- Database transactions and conditional updates must protect business data.
- Connection pools must be bounded and aligned with concurrency.

For example, do not store the current request's `userId` in a field of a singleton service. Two concurrent requests could overwrite the value and access the wrong data. Pass user identity through method parameters or a properly managed security context.

### Choosing concurrency based on workload

| Concurrency per instance | Benefit | Risk to check |
|---|---|---|
| Low | Less request contention; fits CPU-heavy or memory-heavy tasks | Needs more instances as load grows |
| Medium | Balances resource utilization and instance count | Requires measuring thread pools and connection pools |
| High | Increases per-instance resource sharing | Can increase latency, heap pressure, and database load |

Start with a moderate value, then run load tests with realistic payloads. Measure throughput, p95/p99 latency, CPU, memory, connection counts, and 429/5xx errors. Do not choose concurrency based solely on average request rates.

### Bounding total load on the backend

Suppose a service can scale up to 20 instances and each instance allows 40 concurrent requests. Theoretically, the system could have up to 800 active requests at the same time. If every request opened its own database connection, the database could become overloaded.

Coordinate concurrency with:

- Per-instance connection pool size.
- Cloud Run max instances.
- Database connection limits.
- External API rate limits.
- Queues or Cloud Tasks when load smoothing is required.
- Timeouts and circuit breakers for dependencies.

Max instances is a backend protection tool, but if set too low, requests may wait or be rejected when traffic spikes. Test both sides: Cloud Run's serving capacity and the dependencies' load tolerance.

## 9. CPU, memory, and request timeout

Each revision has CPU and memory settings. Selecting too little CPU increases processing and startup time; selecting too little memory can cause `OutOfMemoryError` in the JVM or container termination.

For Java, measure heap alongside native memory, thread stacks, direct buffers, class metadata, and native libraries. Do not set `-Xmx` equal to the entire memory limit because the process also needs off-heap memory. Use a container-aware JVM and inspect memory metrics during load testing.

Cloud Run offers different CPU allocation options: request-based allocation fits services that mostly process work during active requests; instance-based allocation fits workloads needing CPU outside request handling. CPU allocation configuration affects background behavior and billing. Do not rely on background threads to perform business work after returning an HTTP response unless you select the appropriate CPU model and execution mechanism.

Request timeout is the wait limit for a single request. When a request exceeds the timeout, the client may receive an error even though the backend has already executed part or all of the side effects. Therefore:

- Choose timeouts based on SLAs and actual latency distributions.
- Set dependency timeouts lower than the overall request timeout.
- Use idempotency keys for operations that clients may retry.
- Do not use long HTTP requests as a mechanism for long-running batches if they can move to queues/jobs.
- Record task state if clients need to poll or receive a callback later.

Cloud Run services have product- and configuration-specific request timeout limits; check current region/runtime limits when choosing long values. High timeouts do not replace asynchronous processing design.

## 10. Stateless design and durable state storage

An instance may be stopped after a request completes or when the autoscaler scales down. The next request may land on a different instance. Therefore, the application must treat each request independently.

Do not use the following as the authoritative source of state:

- Static variables or singleton fields holding business state.
- Local files inside the container.
- Sessions stored solely in one instance's RAM.
- Local caches without a rebuild or invalidation mechanism.

Instead, you can use:

| Need | Suitable storage service |
|---|---|
| Relational data and transactions | Cloud SQL, AlloyDB, or an appropriate database |
| Document/key-value | Firestore or an appropriate datastore |
| Objects/files | Cloud Storage |
| Shared cache | Memorystore or an appropriate cache service |
| Queues and events | Pub/Sub or Cloud Tasks |
| Long-running workflow state | Database or a workflow/orchestration service |

Session affinity can increase the likelihood that a client is routed to the same instance, but it is not a durable session storage guarantee. Instances can still be stopped or replaced. If sessions are needed, persist session data in an external store and use local caching strictly as an optimization.

## 11. Background tasks and request retries

A Cloud Run service primarily serves requests. Do not spawn a background thread and return HTTP 200 before critical work is persisted or handed off to another system. The instance could be shut down and the work lost.

For asynchronous work:

- Enqueue the request to Pub/Sub or Cloud Tasks and return a job/accepted code.
- Use a Cloud Run service as a push endpoint for events when HTTP handling is needed.
- Use Cloud Run Jobs for batch or run-to-completion tasks.
- Use a workflow engine when the process involves multiple steps, retries, and long-lived state.

Clients may retry after timeouts or dropped connections, so write endpoints require idempotency. For example, `POST /orders` can accept an `Idempotency-Key`; the database stores the key and outcome so retries return the prior result instead of creating a duplicate order.

If a Cloud Run service receives push events from Pub/Sub, the handler must return a status code reflecting the processing result. An error response can cause the event to be redelivered per the retry policy. Therefore, payload validation, idempotency, and a dead-letter policy remain essential.

## 12. Graceful shutdown and resource management

Cloud Run can terminate an instance when scaling down or replacing revisions. The application should handle stop signals such as `SIGTERM`:

- Stop accepting or starting new work during shutdown.
- Allow in-flight requests to finish within the platform's grace period.
- Cleanly close connection pools, HTTP clients, and executors.
- Do not rely on shutdown hooks to persist critical business state; those operations must commit before returning the response.
- Do not let background threads keep writing data after requests or the instance have ended.

Spring Boot supports graceful shutdown via server shutdown configuration and lifecycle beans. Example:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

Cloud Run sends `SIGTERM` before terminating an instance and grants only a short grace period (10 seconds) before forcibly killing the process. Set Spring's timeout lower than that interval so time remains to close resources. A shutdown hook is an opportunity to close resources, not a mechanism to guarantee completion of a long job.

## 13. Security and service identity

A Cloud Run service can require IAM authentication or allow public access. For internal services, callers typically need `roles/run.invoker` on the service. For public endpoints, unauthenticated invocation can be allowed, while business operations still require appropriate authentication such as OAuth/JWT or sessions.

Separate two identities:

- **Caller identity:** the principal allowed to invoke the Cloud Run service.
- **Runtime service identity:** the service account the container uses when calling Google Cloud APIs.

The runtime service account should have least-privilege permissions, such as reading one specific bucket or accessing the exact secret needed. Do not use a default service account with overly broad permissions just to get the application running.

For service-to-service invocation, the caller can fetch a Google-signed ID token whose audience matches the target service URL and send it in the `Authorization` header. The target service validates the IAM Invoker permission. Do not arbitrarily use an access token in place of an ID token when the mechanism requires an ID token.

Secrets can be injected via Secret Manager integration as environment variables or mounted volumes. Choose the approach that matches update and rotation requirements; avoid baking secrets into images or committing them to repositories. Never log secret values or tokens.

## 14. Revisions, traffic splitting, and rollbacks

Every deployment creates a new revision. You can deploy a new revision without shifting all traffic yet, then split traffic between old and new revisions for a canary release.

For example, after deploying a new revision, run:

~~~bash
gcloud run services update-traffic orders-api \
  --region REGION \
  --to-revisions orders-api-00002-abc=10,orders-api-00001-def=90
~~~

This example sends 10% of traffic to the new revision and 90% to the old revision. Replace the revision names with actual values from your service. Once stability is verified, shift 100% of traffic to the new revision:

~~~bash
gcloud run services update-traffic orders-api \
  --region REGION \
  --to-revisions orders-api-00002-abc=100
~~~

If errors occur, shift traffic back to the old revision. Traffic routing rollback only affects new requests; it does not undo data or side effects already performed by the new revision. If two revisions access the same database simultaneously, the schema and API contract must remain backward-compatible during rollout.

### Recommended canary workflow

1. Build an immutable image tagged by commit or build ID.
2. Deploy the new revision and verify startup/health.
3. Run smoke tests via a revision tag or staging environment.
4. Route a small percentage of traffic to the new revision.
5. Compare latency, 5xx errors, CPU, memory, and business errors.
6. Increase traffic percentage if thresholds are met.
7. Shift 100% of traffic or roll back.
8. Keep the previous revision available during observation and verify dependencies.

Do not watch HTTP 2xx rates alone. A service can return 200 while writing corrupted data or processing duplicate events; monitor business metrics and validate data after release.

## 15. Observability and production operations

Cloud Run integrates with Cloud Logging and Cloud Monitoring. Applications should emit structured logs with correlation IDs to link request logs with business logs.

Key metrics to monitor:

| Metric | Meaning |
|---|---|
| Request count | Traffic by service/revision |
| Request latency p50/p95/p99 | User-observed latency |
| 4xx/5xx and timeouts | Client errors, server errors, and timed-out requests |
| Instance count | Active container instances |
| CPU and memory utilization | Resource usage and overload risk |
| Container startup latency | Time to start new instances |
| Concurrency | Concurrent requests per instance |
| Container restarts / startup probe failures | Startup or container health failures |
| Dependency latency/errors | Latency and errors for databases, caches, external APIs |
| Cost by revision/service | Cost by configuration and traffic |

Logs should not contain access tokens, secrets, passwords, personal data, or full request bodies unless necessary. Log request ID, route, status code, duration, and standardized error codes.

When latency spikes, break down startup time, in-application processing, and dependency wait time. Simply increasing concurrency or memory without finding the root cause may raise costs while the underlying failure persists.

## 16. Cost and configuration trade-offs

Cloud Run costs depend on CPU/memory resources, active duration or allocated capacity per billing mode, requests, network egress, and supporting services. Minimum instances, always-allocated CPU, and logging/monitoring can also affect total cost.

| Configuration | Typical impact |
|---|---|
| Min instances = 0 | Can scale to zero, saving idle costs, but incurs cold starts |
| Min instances > 0 | Reduces cold starts, increases cost of keeping capacity warm |
| High concurrency | Can reduce instance count, but increases contention and memory pressure |
| Low concurrency | Requires more instances, but isolates requests better |
| Low max instances | Protects dependencies and budget, but may cap throughput |
| Higher CPU/memory | Can shorten processing duration, while increasing billable resource rate |
| Always-allocated CPU | Supports background tasks within model limits, but can raise cost |

Do not optimize cost by lowering max instances without checking queueing, timeouts, and user latency. Nor should you raise min instances for every service if only certain endpoints need low latency. You can split services by load profile to tune configurations more effectively.

## 17. Checklist before taking a Cloud Run service to production

- [ ] Container listens on the `PORT` environment variable and binds `0.0.0.0`.
- [ ] Image uses a matching Java runtime and contains no secrets.
- [ ] Startup probe/health endpoint accurately reflects serving readiness.
- [ ] Service does not rely on container filesystem or instance RAM for durable state.
- [ ] Singleton beans, static fields, and local caches are concurrency-safe.
- [ ] Concurrency, CPU, memory, and min/max instances have been load tested.
- [ ] Connection pools and database/API load are bounded.
- [ ] Timeouts and retries use idempotency for write operations.
- [ ] Background work is handed off to queues/jobs rather than post-response threads.
- [ ] Service identity has least-privilege permissions; callers have appropriate IAM Invoker roles.
- [ ] Secrets are fetched from Secret Manager with a rotation policy.
- [ ] Graceful shutdown closes resources and does not depend on RAM state.
- [ ] New revisions are canaried, observed, and have a rollback plan.
- [ ] Dashboards exist for latency, errors, concurrency, instances, CPU/memory, and dependencies.
- [ ] Costs are estimated across Cloud Run, databases, caches, networking, and logging.

## Self-check

1. How does a Cloud Run service differ from a Cloud Run Job in workload type and execution lifecycle?
2. Why must the container bind to `0.0.0.0` and read the port from the `PORT` variable?
3. How do service, revision, and instance differ?
4. How does scale-to-zero save cost while potentially increasing first-request latency?
5. How does high concurrency affect thread safety and connection pools in a Java application?
6. Why should you avoid storing sessions or unique order state in one instance's RAM?
7. When a client retries a request after a timeout, how does idempotency protect business integrity?
8. How can max instances protect a database, and what is the trade-off?
9. Does rolling back traffic to an older revision undo side effects performed by the new revision?
10. Which metrics should you monitor to distinguish cold starts from dependency latency?

Cloud Run services lets you deploy containerized Java applications to Google Cloud and scale capacity only when requests arrive. To get the most out of this model, containers must comply with the port and startup contract, applications must be stateless and thread-safe, and concurrency plus max instances must align with backend dependencies. Revisions, traffic splitting, IAM, and observability help roll out services incrementally and operate them with controllable costs.
