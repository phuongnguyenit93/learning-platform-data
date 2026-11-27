# Serving and Eventing Models in Knative

Knative is an open-source platform built on Kubernetes for deploying workloads under a serverless model. Knative provides two commonly used capability sets: **Serving** to run request-driven applications and autoscale with traffic, and **Eventing** to connect event sources with event-consuming services.

With Java, you can package an application as a container image and deploy it as a Knative Service. For asynchronous processing, an event source can emit a CloudEvent to a Broker; a Trigger filters events and routes them to the appropriate Java service. This approach decouples compute lifecycles from data lifecycles and enables scaling on demand.

This lesson covers the Serving and Eventing models, how they work together, how to package Java containers, and considerations around autoscaling, cold starts, traffic splitting, delivery, retries, and idempotency.

## 1. Serving and Eventing Solve Two Different Problems

| Component | Primary problem | Input | Output |
|---|---|---|---|
| Knative Serving | Run request-receiving applications | HTTP requests or gRPC depending on configuration | HTTP/gRPC responses |
| Knative Eventing | Route and deliver events between components | CloudEvents from sources or producers | Events delivered to subscribers/sinks |
| Kubernetes | Manage underlying container infrastructure | Pods, Services, Deployments, and cluster resources | Scheduling, networking, storage, and lifecycle |

Serving suits APIs, webhook receivers, web backends, or HTTP services. Eventing suits asynchronous processing, event source integration, fan-out, and event-driven pipelines.

The two components can work together. For example, a Java API running on Knative Serving receives an order creation request, writes the order to a database, and emits a CloudEvent into a Broker. A Trigger forwards the event to another Java worker. The worker processes business logic and emits a subsequent event. The API does not need to call individual workers directly or hold connections open throughout processing.

~~~mermaid
flowchart LR
    C["HTTP client"] --> S["Knative Serving: Java API"]
    S --> D["Database"]
    S --> B["Knative Eventing Broker"]
    B --> T["Trigger filtering CloudEvent"]
    T --> W["Knative Serving: Java worker"]
    W --> O["Database / external services"]
    W --> B
~~~

Serving and Eventing do not replace Kubernetes. They add serverless abstractions on top of Kubernetes, while the cluster remains responsible for nodes, networking, storage, policies, and resource capacity.

## 2. Knative Serving Architecture

Knative Serving provides an API for deploying and managing containerized applications. Its primary resource is the Knative Service. When configuration or the image changes, Serving creates a new Revision and manages a Route to send traffic to the selected revision.

Four concepts to distinguish:

- **Service:** high-level resource representing the deployed application.
- **Configuration:** describes the desired state of the pod template and runtime configuration.
- **Revision:** an immutable snapshot of a deployment configuration. Changing the image, env vars, or configuration creates a new revision.
- **Route:** maps requests to one or more revisions, optionally splitting traffic by percentage.

A Knative Service is not a Kubernetes Service. A Knative Service is a custom resource provided by Knative Serving; a Kubernetes Service is a networking resource with a different purpose.

~~~mermaid
flowchart TD
    K["Knative Service"] --> C["Configuration"]
    K --> R["Route"]
    C --> V1["Revision 1"]
    C --> V2["Revision 2"]
    R --> V1
    R --> V2
    V1 --> P1["Pod / container"]
    V2 --> P2["Pod / container"]
~~~

Immutable revisions make it possible to deploy a new version, test with a small slice of traffic, observe behavior, and gradually ramp traffic up. If errors occur, the Route can be shifted back to the prior revision, provided that revision is retained and remains compatible with external data.

### 2.1. HTTP Request Path

A request to a Knative Service typically enters through the cluster's ingress/gateway and is routed to the matching revision and pod. Knative manages pod counts based on demand. Internal components such as the Activator and `queue-proxy` support scale-to-zero, routing, concurrency enforcement, and metrics collection.

At a high level:

1. A client sends an HTTP request to the Knative Service domain.
2. The ingress or gateway routes the request to a revision.
3. If the revision already has ready pods, the request goes to a pod.
4. If the service has scaled to zero, the Activator can intercept the request, trigger scale-up, and hold the request while the pod starts.
5. The container processes the request and returns a response.
6. The autoscaler observes traffic and adjusts replica counts.

Exact ingress, gateway, TLS, and network path details depend on how Knative is installed and how the cluster is configured. Do not assume every cluster uses the same ingress controller.

## 3. Deploying a Java Service on Knative Serving

A Java web application must run inside a container and listen on the interface and port supplied by the platform. Knative Serving typically passes the `PORT` environment variable to the container. The application should bind to `0.0.0.0` rather than only `localhost` so the in-pod ingress proxy can connect.

Example Knative Service manifest:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
  namespace: apps
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "20"
    spec:
      containerConcurrency: 20
      containers:
        - image: registry.example.com/orders-api:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: APP_MODE
              value: "production"
~~~

This is an illustrative manifest. The image registry, namespace, port, and autoscaling annotations must fit your cluster. Not every annotation or autoscaling feature behaves identically across all Knative versions; check the API and autoscaler settings of the target platform.

With Spring Boot, you can configure the server port using the `PORT` environment variable. For example, in application properties:

~~~properties
server.port=${PORT:8080}
~~~

In production configurations, set the port from the runtime-provided `PORT` variable or read it in application config. The container image can use a JRE matching your Java version:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar /app/app.jar
ENV PORT=8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]
~~~

Knative requires the container to become ready within the configured startup timeout. The application must start quickly, close connections cleanly, and handle shutdown signals. If the application initializes a database or loads large models before becoming ready, factor that time into startup probes and cold starts.

### 3.1. Container Contract

A Java application on Knative Serving should follow several principles:

- Listen on the port supplied via the `PORT` environment variable or the matching configured port.
- Bind to an address reachable by the in-pod ingress proxy.
- Do not assume the container has a fixed IP or long-lived existence.
- Log to stdout/stderr for platform collection.
- Handle `SIGTERM` and close resources within the graceful shutdown window.
- Never store authoritative business state solely on the container filesystem.
- Implement readiness/startup behavior that accurately reflects ability to serve.

If the application spawns background threads, those threads must not be treated as durable job storage. When a pod scales down or is replaced, the process may terminate. Work that must finish should complete within bounded request handling or be handed off to a durable queue, event, or workflow.

## 4. Autoscaling and Scale-to-Zero

A defining feature of Knative Serving is load-based autoscaling. As requests rise, the autoscaler adds pods; as load drops, pod counts decrease. With scale-to-zero, a revision can keep zero pods when no requests arrive for a period of time.

Key concepts:

- **Target concurrency:** target concurrent requests used by the autoscaler to adjust replica counts.
- **Container concurrency:** hard limit on how many concurrent requests a single container receives.
- **Minimum scale:** minimum number of replicas to retain.
- **Maximum scale:** upper cap on replica count.
- **Scale-to-zero:** allows scaling down to zero when idle.
- **Scale-up/down behavior:** timing and mechanics of adding/removing replicas based on metrics.

Autoscaling does not mean every request spins up a brand-new container. One pod can serve multiple concurrent requests if container concurrency permits. Replica counts adjust based on autoscaler metrics and configuration.

### 4.1. KPA and HPA

Knative Serving typically uses the Knative Pod Autoscaler (KPA) to adjust pods from request/concurrency metrics. Depending on the environment, you can configure the Horizontal Pod Autoscaler (HPA) to scale on CPU or Kubernetes metrics.

| Criterion | KPA | HPA |
|---|---|---|
| Common metrics | Request concurrency or request rate depending on config | CPU, memory, or custom/external metrics per config |
| Integration with Knative request path | Aware of Knative traffic | Relies on configured Kubernetes metrics |
| Scale-to-zero | Supported in appropriate Knative setups | Traditional Kubernetes HPA does not scale to zero natively |
| Best suited for | Variable HTTP workloads scaling on requests | Workloads scaling on CPU or resource metrics |

Exact capabilities depend on Knative version, autoscaler class, and cluster setup. If using HPA, verify whether scale-to-zero is supported via an add-on component; do not assume traditional HPA handles scale-to-zero automatically.

### 4.2. Choosing Appropriate Concurrency

If `containerConcurrency` is too high, a single pod may receive more requests than its CPU, heap, or connection pool can handle. This drives up latency and timeouts. If set too low, the system needs more pods, increasing startup overhead and cost.

Measure:

- p50/p95/p99 processing time.
- CPU and memory across concurrent request counts.
- Database connection counts.
- Timeout and downstream error rates.
- Steady-state throughput per pod.

For Java, concurrency limits must align with web server thread pools, connection pools, and resource limits. Do not set `containerConcurrency` higher than actual capacity merely to reduce pod count.

### 4.3. Min Scale and Max Scale

A min scale of zero minimizes compute when idle, though the first request after an idle period may hit a cold start. A min scale above zero keeps warm pods ready at the cost of baseline compute even during low traffic.

Max scale protects the cluster and dependencies from unbounded scale-out. However, once max scale is reached, requests may queue or be rejected depending on ingress and queueing behavior. Pair max scale with rate limiting, timeouts, and backpressure on dependent services.

Do not set max scale solely from cluster capacity. Account for database limits, message brokers, partner APIs, and cloud quotas.

## 5. Cold Starts and Optimizing Java on Knative

Cold starts happen when a revision needs to launch a new pod, including scheduling, pulling the image if uncached, starting the container, and initializing the Java application.

Factors that increase cold starts:

- Large images or many layers.
- Nodes without the image cached.
- JVM startup and loading many classes.
- Slow framework initialization.
- Heavy reflection or classpath scanning.
- Database connections, DNS lookups, or TLS handshakes.
- Startup logic reading configs/secrets or loading large datasets.

Ways to reduce cold starts:

1. Use multi-stage builds and slim runtime images.
2. Trim dependencies and avoid unnecessary classpath scanning.
3. Lazy-load components not required for the first request.
4. Pick frameworks with suitable startup times.
5. Measure and optimize external service connections.
6. Set min scale > 0 if SLAs demand low latency and cost permits.
7. Evaluate JVM CDS or native executables if benchmarks show net gains.
8. Optimize image layers to speed up pulling and unpacking.

Native executables can cut JVM startup time, but they do not eliminate scheduling, image pulls, network connections, or business initialization. Measure full request-to-response time rather than process startup alone.

## 6. Revisions and Traffic Management

Every deployment configuration change creates a new Revision. A Route can shift all traffic to the new revision or split traffic across multiple revisions.

Example Route configuration splitting 10% traffic to the latest revision and 90% to the older revision:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  traffic:
    - revisionName: orders-api-00001
      percent: 90
    - latestRevision: true
      percent: 10
~~~

Revision names are illustrative. In real deployments, verify existing revisions and how Knative names them. Tags can be used to create dedicated URLs for testing specific revisions.

Traffic splitting is useful for:

- Canary releases.
- A/B testing.
- Comparing latency and error rates between two builds.
- Gradually shifting traffic after verification.
- Fast rollback to a prior revision.

A safe rollout ramps traffic incrementally, monitors metrics, and sets explicit rollback conditions. Do not rely on HTTP 200 alone; track p95 latency, business errors, dependency errors, and resource saturation.

### 6.1. Schema and Data Compatibility

Old and new revisions may receive traffic concurrently for a time. If two versions require incompatible database schemas, a canary rollout can break. Apply schema changes using the expand-and-contract pattern:

1. Add new fields or tables while maintaining compatibility with the old version.
2. Deploy the new revision capable of reading/writing the transitional schema.
3. Shift traffic and verify.
4. Remove old structures only after no active revision or consumer needs them.

Never assume rolling back a container image rolls back side effects or schema changes already written to the database.

## 7. Health Checks, Startup, and Graceful Shutdown

Knative Serving needs to know when a container has started and is ready to accept traffic. Java applications should expose health endpoints or configure appropriate probes.

- **Startup probe:** gives the application time to initialize; prevents readiness/liveness probes from firing too early.
- **Readiness probe:** signals whether the application can accept requests.
- **Liveness probe:** detects stuck processes needing restart, though overly aggressive thresholds can trigger restart loops.

Do not build a single health endpoint that checks every dependency in a way that causes cascading failures. If the database is briefly slow, repeated liveness probe failures can restart all pods and worsen the outage. Distinguish process liveness from readiness for specific request types.

When a pod scales down, the application must stop accepting new work and finish in-flight requests within the grace period. For long-running requests, set appropriate timeouts and use async jobs when processing exceeds a request lifecycle.

## 8. Knative Eventing Architecture

Knative Eventing connects event producers and event consumers using a common event protocol. CloudEvents is the standard format used to represent events interoperably across frameworks and services.

Core concepts:

- **Event source:** component generating events, such as `PingSource`, Kubernetes API sources, or messaging adapters.
- **Broker:** event hub that receives and distributes events, decoupling producers from consumers.
- **Trigger:** registers an event filter and a subscriber to receive matching events.
- **Sink:** destination receiving events, such as a Knative Service, Broker, or supported URI.
- **Channel/Subscription:** channel-based event delivery model; specific APIs and implementations depend on installed extensions/transports.

Broker/Trigger is a common abstraction for event routing. Channel/Subscription still appears in certain topologies or extensions. Do not assume every cluster running Knative Eventing installs the same broker, channel type, or source adapters.

~~~mermaid
flowchart LR
    S1["PingSource / API Source"] --> B["Broker"]
    S2["Producer / Adapter"] --> B
    B --> T1["Trigger: order.created"]
    B --> T2["Trigger: payment.failed"]
    T1 --> W1["Knative Service: order-worker"]
    T2 --> W2["Knative Service: alert-worker"]
~~~

A Broker frees producers from needing to know which services consume events. Triggers define subscribers and filters. Adding a new consumer only requires adding a Trigger without changing the producer, as long as the event contract stays compatible.

## 9. CloudEvents and Event Contracts

CloudEvents defines standard attributes describing an event. A CloudEvent typically includes:

| Attribute | Meaning |
|---|---|
| `specversion` | CloudEvents specification version |
| `id` | Event identifier unique within the source |
| `source` | Event origin |
| `type` | Event type |
| `subject` | Subject entity the event relates to, if any |
| `time` | Timestamp when the event occurred |
| `datacontenttype` | Content type of `data` |
| `data` | Business payload |

Example structured CloudEvent JSON:

~~~json
{
  "specversion": "1.0",
  "id": "evt-91f2",
  "source": "/orders/service",
  "type": "com.example.order.created",
  "subject": "orders/order-1042",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "order-1042",
    "customerId": "customer-42",
    "total": 125.50
  }
}
~~~

The `(source, id)` pair is a solid basis for uniquely identifying an event during deduplication. Do not rely on `id` alone if multiple sources can emit identical `id` values.

CloudEvents can be transmitted in structured mode or binary mode. In structured mode, metadata and data reside inside the JSON body. In binary mode, context attributes are usually passed in HTTP headers prefixed with `ce-`, while the body holds `data`. Producers and consumers must agree on the same binding and content type.

Event contracts should be versioned by `type` or schema version. Never change the semantics of a field used by consumers without a compatibility strategy. Events should describe facts that happened, such as `order.created`, rather than vague commands like `process-order` when consumers rely on business history.

## 10. Creating Brokers and Triggers

A Broker acts as an event ingress point within a namespace. Example Broker manifest:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Broker
metadata:
  name: default
  namespace: apps
~~~

A Trigger subscribes to events from a Broker using filters. For example, forwarding only events with `type` `com.example.order.created` to a Knative Service:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: order-created
  namespace: apps
spec:
  broker: default
  filter:
    attributes:
      type: com.example.order.created
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: order-worker
~~~

These manifests follow the Knative Eventing v1 API. A Broker implementation and proper namespace/permissions must be installed before creating resources. Default brokers, persistence guarantees, and delivery semantics depend on the implementation installed in the cluster.

You can attach multiple Triggers to the same Broker to fan out an event to multiple subscribers. When a Trigger filters by `type` or `subject`, ensure producers emit exact attributes and consumers validate schemas before processing.

## 11. Event Sources and Sinks

A Source is an adapter that translates signals from another system into CloudEvents and sends them to a sink. Sources can come from the Kubernetes API, cron schedules, or messaging systems. Specific sources are typically installed as extensions with their own APIs.

Example `PingSource` emitting periodic events to a Broker:

~~~yaml
apiVersion: sources.knative.dev/v1
kind: PingSource
metadata:
  name: periodic-cleanup
  namespace: apps
spec:
  schedule: "*/5 * * * *"
  contentType: application/json
  data: '{"task":"cleanup"}'
  sink:
    ref:
      apiVersion: eventing.knative.dev/v1
      kind: Broker
      name: default
~~~

The example above emits an event every five minutes per the source's schedule. Schedule syntax, timezones, and missed-schedule behavior depend on the source implementation; consult the extension docs. Do not use `PingSource` as a substitute for a scheduler with complex business semantics if you need catch-up control, timezone guarantees, or overlap prevention.

A Sink is an event destination. A sink can be a Knative Service, a Broker, or a URI depending on configuration and supported APIs. When sending events to a service, the producer does not need to know how many replicas are running. Serving scales the subscriber according to incoming traffic.

## 12. Handling CloudEvents in Java

A Java consumer can use the CloudEvents Java SDK or framework adapters to parse events from HTTP bindings. After receiving a `CloudEvent`, the application reads `source`, `id`, `type`, and `data`, validates the contract, and invokes business logic.

The example below illustrates processing after an adapter has parsed the HTTP request into a `CloudEvent`. The `EventInbox` interface represents an application-implemented idempotency store.

~~~java
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;

public final class OrderEventHandler {

    private final EventInbox inbox;
    private final OrderService orderService;

    public OrderEventHandler(EventInbox inbox, OrderService orderService) {
        this.inbox = inbox;
        this.orderService = orderService;
    }

    public void handle(CloudEvent event) throws Exception {
        if (!"com.example.order.created".equals(event.getType())) {
            throw new IllegalArgumentException("Unsupported event type");
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("Event data is required");
        }

        String eventKey = event.getSource() + ":" + event.getId();

        InboxClaim claim = inbox.claim(eventKey);
        if (claim == InboxClaim.ALREADY_PROCESSED) {
            return;
        }
        if (claim == InboxClaim.OWNED_BY_ACTIVE_WORKER) {
            throw new IllegalStateException("Event is already being processed");
        }

        try {
            String json = new String(
                    event.getData().toBytes(),
                    StandardCharsets.UTF_8);

            orderService.handleCreatedOrder(json);
            inbox.markProcessed(eventKey);
        } catch (Exception error) {
            inbox.markRetryableFailure(eventKey, error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

`EventInbox`, `InboxClaim`, and `OrderService` are domain interfaces you define. Claiming must be atomic, typically via a unique key on `source + id` and a lease/processing state. When a consumer hits a transient failure, the state must permit safe retries; never leave a record stuck in `PROCESSING` forever. Schema errors or unsupported event types are permanent errors and should be routed to dead-letter or marked rejected rather than retried indefinitely. If an event is already `PROCESSED`, return success so duplicate deliveries do not repeat side effects.

This snippet shows post-parse logic only. The HTTP adapter must handle CloudEvents binary/structured mode according to the binding in use. Do not manually parse headers via string manipulation when the CloudEvents library or framework supports standard bindings.

### 12.1. Ack Only After Durable Acceptance

When a consumer receives events over HTTP, a `2xx` response tells the dispatcher the event was accepted. If the application returns `2xx` before persisting the event or finishing required policy work, the event can be lost if the process crashes immediately afterward.

Two common patterns:

- Process synchronously and return `2xx` only after side effects commit.
- Persist the event to a durable inbox/queue, then return `2xx`; workers process asynchronously later.

The second pattern suits long workloads or independent retry handling. In both cases, duplicates can still occur and the consumer requires idempotency.

## 13. Delivery, Retries, and Dead-Lettering

Event delivery in distributed systems can repeat. Producers may retry on missing responses; Brokers or dispatchers may redeliver on subscriber failures or timeouts. Never design consumers assuming each event arrives exactly once.

Knative Eventing supports configuring delivery behavior on appropriate resources, including retries, backoff, and a dead-letter sink. Exact schema and placement of the delivery spec depend on the resource kind and Eventing version. Example delivery configuration on a Trigger:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: order-created
spec:
  broker: default
  filter:
    attributes:
      type: com.example.order.created
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: order-worker
  delivery:
    retry: 5
    backoffPolicy: exponential
    backoffDelay: PT1S
    deadLetterSink:
      ref:
        apiVersion: serving.knative.dev/v1
        kind: Service
        name: event-dead-letter
~~~

Values are illustrative. Verify the API schema for your installed Knative Eventing version and Broker implementation. The dead-letter sink must be deployed, authorized, and backed by operational procedures to inspect, fix, or replay failed events.

A retry policy must define:

- Which errors are retryable.
- Maximum retry count.
- Linear vs. exponential backoff.
- Maximum delay.
- Per-delivery timeout.
- Dead-letter destination.
- How operators handle events after they land in the DLQ.

Do not retry malformed schemas or permanent business errors forever. If a consumer does not support an event type, emit a structured error and route to the DLQ instead of looping endlessly.

### 13.1. At-Least-Once and Idempotency

Many event delivery configurations aim for at-least-once delivery: the system attempts delivery, though consumers may receive duplicates. Exact delivery guarantees also depend on the source, broker, channel implementation, and retry settings.

Do not claim the entire pipeline is exactly-once solely because the Broker or transport offers some deduplication. Side effects in databases, payment providers, or external APIs may not share a single transaction.

Use a stable idempotency key, typically derived from `source + event id`. Persist event state alongside business outcomes using transactions or the inbox/outbox pattern. When a consumer calls external APIs, pass the idempotency key to those APIs if supported.

## 14. Ordering, Fan-Out, and Backpressure

Not every broker or channel guarantees event ordering. Multiple subscribers can process concurrently and finish in an order different from emission. If business logic requires ordering, define partition keys, sequence numbers, or aggregate versions.

For example, `order.updated` version 8 may arrive before version 7. The consumer can ignore stale events if a newer version has already been processed, or hold events if sequential processing is mandatory. Do not use standalone timestamps for strict ordering when multiple producers have skewed clocks.

Fan-out lets multiple Triggers subscribe to the same event—for instance, one consumer updating a search index and another sending notifications. Subscribers must stay isolated: a notification failure should not block index updates if brokers and delivery are configured independently.

Backpressure must be handled at multiple layers:

- Cap concurrency on the Knative Service.
- Tune autoscaling targets and max scale.
- Limit in-flight events inside Java workers.
- Cap connection pools and request rates to dependencies.
- Leverage queue/broker buffering when supported by the implementation.
- Configure timeouts and retries with backoff.
- Monitor backlog depth, event age, and delivery failures.

If subscribers scale out faster than the database can sustain, the event backlog may shrink while the database collapses. Set limits based on whole-system capacity, not container speed alone.

## 15. Securing Serving and Eventing

A Knative Service can be exposed externally or restricted to internal cluster traffic. Never assume every service needs public ingress. Apply ingress policies, gateways, TLS, and network policies matching your cluster model.

For events:

- Authenticate producers or sources allowed to publish.
- Restrict creation of Brokers, Triggers, and Sources via Kubernetes RBAC.
- Protect sinks and callback endpoints with TLS and appropriate authentication.
- Exclude secrets from CloudEvent payloads when subscribers do not need them.
- Validate tenants/resources in payloads against authoritative data.
- Validate event schemas and payload sizes.
- Restrict sink URIs to prevent SSRF or forwarding data to untrusted destinations.
- Audit changes to routing, filters, and access permissions.

CloudEvents standardizes data structure, not sender authentication. An event claiming `source: /payments/provider` does not prove it actually came from the payment provider. Authenticate at the ingress/source adapter and verify integrity at the transport/protocol layer.

Kubernetes service accounts, RBAC, and network policies govern cluster permissions. When Java services call cloud APIs, use workload identity or the platform's identity mechanism instead of baking long-lived keys into images.

## 16. Observability and Troubleshooting

For Serving, monitor:

- Request count, concurrency, and p50/p95/p99 latency.
- Replica/pod count and scale-up time.
- Cold starts, startup probes, and readiness failures.
- Container CPU, memory, restarts, and OOMs.
- HTTP 4xx/5xx, timeouts, and dependency latency.
- Active revisions receiving traffic and traffic split percentages.

For Eventing, monitor:

- Published events and delivered events.
- Delivery latency and event age.
- Retries, timeouts, and dead-letter counts.
- Subscriber response codes.
- Duplicate events deduplicated by idempotency.
- Broker/dispatcher health and backlog if exposed by the implementation.
- Events unmatched by any Trigger filter.
- Event rates by type/source.

Include correlation IDs, CloudEvent `source`/`id`/`type`, request IDs, revisions, or task identifiers in logs. Never log sensitive payloads or secrets. When an event traverses multiple services, use event IDs or trace context to stitch producer and subscriber logs.

Common failure modes:

| Symptom | Possible cause | Where to check |
|---|---|---|
| Service receives no requests | Misconfigured Route/ingress, DNS, or TLS | Inspect Route, gateway, domain, and certificates |
| Pod fails to become ready | Wrong `PORT`, slow startup, or broken probe | Check container logs, port binding, and probe configs |
| Scale-to-zero fails to scale up | Autoscaler/Activator issue or min/max config | Check metrics and Serving configuration |
| Request timeout on cold start | Large image or slow Java init | Measure image pull, process startup, and dependencies |
| Events do not reach subscriber | Misconfigured Source/Broker/Trigger or filter | Check event attributes, namespace, and sink |
| Duplicate events | Retries or delivery semantics | Check `source`/`id`, inbox, and retry policy |
| Events land in DLQ | Persistent subscriber errors or invalid schema | Check subscriber responses, logs, and DLQ consumer |
| Database overload | Excessive concurrency or parallelism | Lower max scale/concurrency and cap connections |

## 17. Deployment and Testing

Knative is typically installed on Kubernetes alongside Serving/Eventing CRDs and controllers. Before deploying applications, verify:

- Knative Serving and Eventing are installed at compatible versions.
- Ingress/gateway and DNS are configured.
- Required Broker implementation and event source extensions are ready.
- Namespaces, service accounts, and RBAC are set properly.
- Registry credentials or workload identity allow pulling images.
- Observability stack collects logs and metrics.

Apply manifests with `kubectl`:

~~~bash
kubectl apply -f orders-api.yaml
kubectl get ksvc -n apps
kubectl get revisions -n apps
kubectl get routes -n apps
~~~

For Eventing:

~~~bash
kubectl apply -f broker.yaml
kubectl apply -f order-trigger.yaml
kubectl get brokers -n apps
kubectl get triggers -n apps
~~~

Resource names and CRDs may vary if the cluster runs different versions or extensions. Verify installed CRDs before applying manifests.

Scenarios to test:

1. Service handles requests with warm pods ready.
2. Service scales to zero and handles the first wake-up request.
3. Send bursts and high concurrency to verify autoscaling.
4. Deploy a new revision and split canary traffic.
5. Roll back traffic when the new revision errors.
6. Producer emits a CloudEvent with matching `type` and Trigger delivers it to the subscriber.
7. Events with non-matching `type` do not route to unrelated Triggers.
8. Subscriber returns errors and delivery retries per policy.
9. Events route to the dead-letter sink after exhausting retries.
10. Resend the same `source`/`id` and verify consumer idempotency.
11. Test out-of-order and duplicate event arrivals.
12. Verify RBAC and authentication block unauthorized producers/consumers.

## 18. Choosing Serving, Eventing, or Both

| Need | Suitable model |
|---|---|
| HTTP API scaling with requests | Knative Serving |
| Webhook receiver | Knative Serving; optionally emit CloudEvents to Eventing |
| Asynchronous event processing | Knative Eventing with subscribers on Serving |
| Single event with multiple consumers | Broker and multiple Triggers |
| Scheduled batch jobs | Suitable event source/scheduler or job runner; Serving is not the default fit |
| Stateful multi-step processes | Workflow engine paired with Serving/Eventing |
| Long-running consumers or persistent connections | Evaluate dedicated workers/services and appropriate autoscaling |

Serving focuses on the request lifecycle and container scaling. Eventing focuses on event contracts, routing, and delivery. Combining both lets a system serve synchronous APIs while handling resulting work asynchronously.

Not every workload needs both. A small HTTP-only service may need only Serving. An event pipeline with no public API may need only Eventing and subscribers. Choose abstractions based on request, event, state, and delivery requirements.

## 19. Designing a Java Application on Knative

1. **Classify workloads.** Separate HTTP-facing endpoints from event-driven reactions.
2. **Design the container.** Pick JDK/JRE, keep images slim, configure `PORT`, startup, and graceful shutdown.
3. **Create the Knative Service.** Configure revisions, concurrency, min/max scale, and ingress.
4. **Benchmark autoscaling.** Test request concurrency, cold starts, and dependency limits.
5. **Design event contracts.** Use CloudEvents with clear `source`, `id`, `type`, and schemas.
6. **Configure Brokers and Triggers.** Select a broker implementation, filters, and subscribers.
7. **Make consumers idempotent.** Use an inbox/unique key, retries, and DLQs.
8. **Secure the system.** Configure TLS, authentication, RBAC, service accounts, and network policies.
9. **Instrument observability.** Propagate correlation IDs; monitor revisions, delivery latency, and errors.
10. **Test failure modes.** Scale-to-zero, traffic bursts, duplicates, out-of-order events, retries, and rollbacks.

## 20. Self-Check Questions

- Which two problems do Knative Serving and Knative Eventing solve?
- What roles do Service, Configuration, Revision, and Route play?
- Why is a Knative Revision considered immutable?
- How does the Activator support scale-to-zero?
- How does container concurrency differ from autoscaler target concurrency?
- When should min scale stay above zero?
- How do Brokers and Triggers decouple producers from subscribers?
- What are CloudEvents `source`, `id`, and `type` used for?
- How does Channel/Subscription differ from Broker/Trigger conceptually?
- Why does event delivery still require idempotency even with retries?
- How do you control ordering and backpressure?
- Which metrics reveal cold starts or slow event delivery?

Knative Serving lets Java containers serve requests and scale with traffic; Knative Eventing lets components exchange CloudEvents without tight coupling. When combining both models, design revisions and autoscaling for the HTTP path alongside event contracts, retries, dead-lettering, and idempotency for the asynchronous path. Together, they form a flexible and operable foundation for running Java serverless workloads on Kubernetes.
