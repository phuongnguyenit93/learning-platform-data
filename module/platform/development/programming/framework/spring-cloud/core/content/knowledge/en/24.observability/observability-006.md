# Distinguishing Healthy Registry Connectivity from an Instance Able to Handle Requests

In a Spring Cloud system, a service can appear in the registry and be marked **UP**, yet actual requests still fail. Conversely, the registry can become temporarily unreachable while running instances keep handling requests routed from local caches.

To accurately assess system health, distinguish four layers:

1. **Registry availability:** whether the client can connect to and invoke the service registry API.
2. **Registration freshness:** whether the registry is still receiving valid heartbeats or health updates from the instance.
3. **Instance readiness:** whether the instance is ready to accept new requests with required dependencies and resources.
4. **Request success:** whether the consumer can actually complete the service call flow across DNS, network, TLS, authentication, application code, and business dependencies.

These layers are related, but they do not replace one another. An HTTP 200 from the registry only proves a registry endpoint responded. A successful heartbeat only proves the client is still communicating with the registry. A successful readiness probe indicates the instance is ready according to defined criteria. Only real requests or synthetic transactions test the full path used by consumers.

This lesson belongs to the **Observability** chapter of the **SPRING_CLOUD_CORE** module. It focuses on accurately reading health signals in Eureka, Consul, Kubernetes, and Spring Cloud LoadBalancer; designing Actuator health groups; monitoring metrics/traces; and diagnosing cases where the registry is healthy yet the service still cannot process requests.

## 1. Four Status Layers in a Distributed System

| Layer | What to Verify | Example Signal | What the Signal Does Not Prove |
| --- | --- | --- | --- |
| Registry availability | Is the registry API or agent responding? | HTTP probe to Eureka/Consul, registry health endpoint | Registered instances are alive or able to handle requests |
| Registration freshness | Is the registry still receiving updates from the instance? | Eureka heartbeat/lease, Consul check, registration metadata | The instance's thread pool, database, broker, or business flows are healthy |
| Instance readiness | Can the application accept new traffic? | Actuator readiness, Kubernetes Ready, registry health check | All business requests succeed |
| Request success | Can the consumer call and receive a valid result? | HTTP/gRPC response, synthetic transaction, error rate | Other instances or all functional flows are healthy |

Some examples:

- Eureka Server returns HTTP 200, yet an instance in the registry has stopped processing requests.
- Eureka receives regular heartbeats from a running JVM, yet the application's database pool is exhausted.
- Consul marks the HTTP check passing because the health endpoint returns 200, yet a business endpoint returns 500 due to data or permissions.
- A Kubernetes Pod is Ready, yet a specific business flow fails because its dependency was not included in the readiness check.
- The registry is temporarily unreachable, yet consumers continue using cached instance lists and requests succeed for a period of time.

Do not use a single **UP** word to conclude that all four layers are healthy.

## 2. Control Plane and Data Plane

The registry belongs to the control plane: it stores and distributes instance information. Requests between services belong to the data plane: they travel through DNS, routes, load balancers, network policies, TLS, server sockets, and request-handling code.

~~~mermaid
flowchart TD
    subgraph CP["Control plane"]
        REG["Service Registry"]
        CLIENT["Discovery Client"]
        HB["Heartbeat / Health update"]
        REG <--> CLIENT
        CLIENT --> HB
        HB --> REG
    end

    subgraph DP["Data plane"]
        CALLER["Consumer"]
        LB["Spring Cloud LoadBalancer"]
        INSTANCE["Service instance"]
        DEP["Database / Broker / External API"]
        CALLER --> LB
        LB --> INSTANCE
        INSTANCE --> DEP
    end

    REG -->|"Instance metadata / status"| LB
    INSTANCE -->|"Readiness / health signal"| CLIENT
~~~

The diagram shows that the registry supplies data to select an instance, while requests still travel over a separate network path. The registry does not sit inline on every request; after receiving the instance list, the client can cache and reuse that list for many calls.

Therefore, two questions must be monitored separately:

- **Control plane:** is the consumer obtaining an up-to-date and accurate instance list?
- **Data plane:** can the consumer connect to and complete requests against the selected instance?

If the control plane has issues, discovery data can become stale. If the data plane has issues, the registry may still operate normally and continue advertising the instance.

## 3. Healthy Registry API Does Not Mean Healthy Registration

A TCP/HTTP check against the registry typically verifies items such as:
- Registry DNS resolves.
- The registry port is open.
- The TLS handshake succeeds.
- The API endpoint responds.
- Credentials have read or write permissions if the test performs authenticated operations.

However, a simple check against the registry does not confirm:
- The registered instance has the right hostname/IP/port.
- The registration is fresh rather than expired.
- The instance's health check is passing.
- Consumers have received the update.
- Client-side caches have evicted unhealthy instances.
- Requests to the instance actually complete.

For example, the following command only checks the registry's own health endpoint:

~~~bash
curl -i https://registry.internal/actuator/health
~~~

If the response is **UP**, that reflects the health of the registry application itself according to its configured HealthContributors. It does not test every service instance managed by the registry.

Similarly, successfully calling an API to list services only proves the registry can return data. You must inspect individual instance records, timestamps/leases/check states, and request outcomes from consumers.

### 3.1. Reading Per-Instance Registrations

When inspecting a service, record at minimum:

- Service ID and instance ID.
- Advertised hostname/IP and port.
- Registration status.
- Last update/heartbeat or check timestamp if provided by the registry.
- Health check URL/path and check status.
- Necessary metadata such as zone, version, or management port.
- Which consumers are reading the record and how long they cache it.

A record with a good status yet the wrong port or wrong network zone is still unusable. A record with the right host yet no route from the consumer to that address also cannot serve requests.

### 3.2. Checking Both Read and Write Permissions

A client might be able to read from the registry without having permission to register, renew, or update status. In systems with ACLs, checking the health endpoint using read-only credentials does not prove the application's credentials have write permission.

When diagnosing, test separately:
- Reading the service list.
- Reading a specific registration.
- Registering/renewing using the service's identity.
- Updating status or deregistering if operational workflows require it.
- Connecting from the application's actual network namespace.

Do not run deregister or status-mutation operations in production just to test write permissions. Use dedicated test endpoints or a staging environment.

## 4. Heartbeats Only Prove the Client Is Still Communicating

Heartbeat/lease is a mechanism letting the registry know the client is still checking in periodically. It is useful for detecting lost processes or broken network paths, but it does not automatically test every application function.

### 4.1. Eureka Heartbeats

A Eureka client sends heartbeats to Eureka Server to renew its lease. Spring Cloud Netflix documentation describes common defaults where the client renews roughly every 30 seconds and the server evicts an instance from the registry after failing to receive heartbeats for the lease expiration period (typically 90 seconds). These values are configurable and must be evaluated for your actual version, load, and topology.

Crucially, heartbeats and application health are two separate signals. By default, Eureka relies on heartbeats to determine if a client is active; Actuator health status is not automatically propagated to Eureka unless health check integration is enabled.

You can enable it with `eureka.client.healthcheck.enabled=true` in `application.yml`:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Place this property in **application.yml** as guided by Spring Cloud Netflix. Documentation warns that placing it in **bootstrap.yml** can cause side effects, such as the instance registering with status **UNKNOWN**.

When health propagation is enabled, the application's health status can affect its Eureka status and whether consumers select the instance. Still, HealthIndicators/health groups must be configured properly for the intended purpose. If health only checks the process without checking essential readiness, Eureka may still mark an instance incapable of handling requests as UP.

### 4.2. Consul Health Checks

Spring Cloud Consul defaults to registering an HTTP health check that calls **/actuator/health** roughly every 10 seconds. If the check fails, the service instance is marked critical in Consul.

Configuration example:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health
        health-check-interval: 10s
~~~

Property names and default values should be verified against the Spring Cloud Consul version in your project's BOM. If the application uses a different context path or management path, update the health check path so Consul calls the right endpoint.

A passing health check means the endpoint returned a result Consul considers successful. If **/actuator/health** only checks the process or a small set of components, it does not prove business APIs are working.

### 4.3. Registries May Retain Stale Data for a Period

Heartbeats, lease expiration, health check intervals, registry replication, and client fetch/cache all operate on intervals. When an instance dies or stops being ready, a window of time can elapse before every consumer stops selecting that instance.

With Eureka, clients fetch the registry and keep a local cache; registry updates do not necessarily appear simultaneously across all clients. With Consul, health checks also run on intervals and status changes appear after the next check. Account for detection and propagation delays in SLOs, alerts, and drain procedures.

Do not use a single timeout number to describe every delay. Separate:
- Time to detect an instance missed heartbeats.
- Time for the health checker to call the endpoint.
- Time for the registry to update/replicate status.
- Time for clients to fetch or refresh caches.
- Time for LoadBalancer to adopt the new list.
- Time for in-flight requests to finish or time out.

## 5. Application Health, Liveness, and Readiness

Spring Boot Actuator provides HealthEndpoint aggregating statuses from HealthContributors in the ApplicationContext. A HealthIndicator can check a database, broker, disk, LDAP, or another dependency.

Common endpoint:

~~~text
GET /actuator/health
~~~

The response may contain an overall status and components. Whether details are shown depends on **management.endpoint.health.show-details** and access permissions. By default, details are not exposed publicly.

However, overall health does not automatically mean the instance is ready to accept traffic. You must define the purpose of each health group.

| Signal | Question | Typical Action |
| --- | --- | --- |
| Liveness | Is the process/app stuck or broken enough to need a restart? | Restart container/process when probe fails past threshold |
| Readiness | Can the instance accept new requests? | Stop routing new traffic to the instance |
| Startup | Has the application finished its startup phase? | Hold off liveness/readiness checks until startup probe succeeds |
| Overall health | What status are aggregated HealthContributors reporting? | Observe and alert; action depends on policy |

### 5.1. Liveness Should Not Depend on External Systems

If a database or external API experiences a temporary error, it should not cause liveness to fail if the process is still healthy. Kubernetes could restart Pods en masse when a shared dependency fails, increasing load and triggering a cascading failure.

Liveness should focus on internal state that a restart can recover from, such as deadlocks or an unrecoverable stuck process state.

### 5.2. Readiness Should Reflect Traffic-Serving Capability

Readiness can verify prerequisites for handling new requests:
- Startup tasks have completed.
- Connection pools are ready.
- Required configuration is loaded.
- Mandatory dependencies for primary request flows are usable.
- The instance is not draining or under maintenance.
- Required resources have not breached thresholds preventing the service from accepting more traffic.

Not every dependency belongs in readiness. If a dependency only serves a secondary feature, placing it into service-wide readiness could remove all replicas even when most requests still work. Choose based on business contracts and fallback capabilities.

### 5.3. Startup Probes Protect Slow-Starting Applications

Startup probes are helpful when an application needs time to load configuration, warm caches, run migrations, or establish initial connections. When a startup probe is configured, Kubernetes waits for it to succeed before starting liveness and readiness probes.

This prevents the liveness probe from restarting an application merely because it has not finished starting up yet.

## 6. Configuring Health Groups in Spring Boot

Spring Boot can expose liveness and readiness health groups when running in Kubernetes or when appropriate probe settings are enabled.

Example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
      show-details: when-authorized
~~~

The configuration above includes **readinessState** and the **db** health contributor in the readiness group. Only include **db** if the database is genuinely mandatory for the service to accept traffic. Spring Boot does not automatically put all dependency health indicators into the readiness group.

Do not place databases, brokers, or external APIs into the liveness group merely because they appear in overall health.

### 6.1. Creating a HealthIndicator for Custom Readiness Conditions

Example of an internal check confirming initialization data is ready:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

interface CatalogBootstrapState {
    boolean isReady();
}

@Component("catalogBootstrap")
public class CatalogBootstrapHealthIndicator implements HealthIndicator {

    private final CatalogBootstrapState bootstrapState;

    public CatalogBootstrapHealthIndicator(
            CatalogBootstrapState bootstrapState) {
        this.bootstrapState = bootstrapState;
    }

    @Override
    public Health health() {
        if (bootstrapState.isReady()) {
            return Health.up().build();
        }

        return Health.outOfService()
                .withDetail("reason", "catalog data is still loading")
                .build();
    }
}
~~~

Include this indicator in the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,catalogBootstrap
~~~

Component names in the group must match the registered HealthContributor names. Do not expose details containing credentials, connection strings, customer data, or sensitive infrastructure information.

A HealthIndicator should:
- Have explicit timeouts for I/O operations.
- Avoid running heavy queries on every probe.
- Produce no side effects.
- Return quickly and reliably.
- Distinguish transient errors from unrecoverable failures where appropriate.
- Never restart processes or mutate data inside a health check.

### 6.2. HTTP Status of Health Endpoints

Under Spring Boot's default configuration:
- **UP** maps to HTTP 200.
- **DOWN** and **OUT_OF_SERVICE** map to HTTP 503.
- **UNKNOWN** typically maps to HTTP 200 unless configured otherwise.

If an application defines custom status mappings, default mappings for DOWN and OUT_OF_SERVICE may be replaced and must be redeclared if you want to keep them. Therefore, check both the response body and the HTTP status code that probes actually receive.

### 6.3. Separate Management Ports Can Create False Positives

If Actuator runs on a separate management port, the health endpoint might return UP while the main HTTP server cannot accept connections. The two ports may use different web infrastructure and connection paths.

For applications needing probes on the main server port, you can enable additional paths:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Spring Boot provides default additional paths such as **/livez** and **/readyz** on the main server port for the corresponding health groups. Check the exact version and effective paths in the Boot documentation you use.

## 7. How Kubernetes Readiness Controls Traffic

Kubernetes separates container probes from Pod readiness conditions. When the readiness probe fails, the Pod may continue running while marked NotReady; the EndpointSlice controller updates endpoints so the Service stops sending regular traffic to that Pod.

Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: catalog
          image: example/catalog-service:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
~~~

These numbers are illustrative examples only. Choose periods, timeouts, success/failure thresholds, and startup allowances based on startup time, load, and availability requirements.

### 7.1. Liveness Failures and Readiness Failures Have Different Actions

| Probe | On Consecutive Failures | Impact |
| --- | --- | --- |
| Startup | Container has not completed startup | Kubelet may restart the container per restart policy |
| Liveness | Container is no longer healthy by liveness criteria | Kubelet restarts the container |
| Readiness | Container is not ready to accept traffic | Pod is marked NotReady; container keeps running |

Do not use readiness in place of liveness to restart an application. Also do not use liveness to temporarily remove an instance from traffic, because restarting can spread failures.

### 7.2. Readiness Is Not a Synthetic Transaction

A readiness probe usually checks a lightweight endpoint on each Pod. It does not necessarily traverse:
- Consumer service name DNS.
- Ingress or API gateway.
- Service mesh sidecars along the request path.
- Real client authentication/authorization.
- All business dependencies and transactions.

Therefore, readiness must be combined with request testing from consumers and monitoring at gateways/data planes.

## 8. Health Checks in Eureka and Consul

### 8.1. Eureka: Heartbeats and Health Propagation

Configuration:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

When health check integration is enabled, the application's health status can be propagated to Eureka. Consumers typically only select instances in UP status under default discovery settings.

Verify:
- Is Eureka Server still receiving heartbeats?
- Does InstanceInfo have the right status?
- Is the health check handler enabled in application.yml?
- Have client registry fetches picked up the new status?
- Does LoadBalancer filter instances by the desired status?
- Is the instance affected by a server-side override or stale cache?

If only heartbeats are checked, an instance can continue being treated as UP while business endpoints are failing. If health propagation is enabled yet the health group is configured too broadly or too narrowly, the status may still fail to reflect true readiness.

### 8.2. Consul: HTTP Checks and Critical State

Consul typically polls an instance's health check path periodically. When the endpoint fails to respond or returns a failure code, Consul can mark the check critical.

Example:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
~~~

Use the readiness endpoint when you want Consul to place only traffic-ready instances into the healthy list. However, verify that the path is exposed and reachable from the Consul agent.

If the Consul agent cannot reach the endpoint due to network policies, firewalls, TLS, or the wrong port, the check will fail even if the application handles consumer requests normally. In that case, the fault lies on the probe path from agent to instance, not necessarily in the consumer data plane.

### 8.3. Do Not Use One Health Endpoint for Every Purpose

You can use:
- Liveness for kubelet restart decisions.
- Readiness for Kubernetes/registry traffic-acceptance decisions.
- Lightweight health checks for LoadBalancer or registry.
- Synthetic endpoints/transactions for end-to-end monitoring.

Endpoints may share some HealthIndicators, yet each should have clear semantics. Never let a health check for a secondary dependency pull the entire instance out of traffic if the application still has a fallback.

## 9. Spring Cloud LoadBalancer Health Checks

Spring Cloud LoadBalancer provides **HealthCheckServiceInstanceListSupplier**. This supplier periodically checks instances returned by a delegate supplier and returns only healthy instances; if no instances are healthy, the current implementation returns the entire retrieved list again.

This point is crucial when designing fail-open/fail-closed behavior. If all probes fail, do not assume LoadBalancer is guaranteed to return an empty list and stop traffic.

This mechanism is especially helpful with **SimpleDiscoveryClient**, since SimpleDiscoveryClient only supplies a static list from properties and has no registry server performing health checks. With discovery clients retrieving status from a real registry, redundant probing is usually unnecessary because the registry already supplies health state.

### 9.1. Configuring the Health-Check Supplier

Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 2s
        interval: 20s
        path:
          default: /actuator/health/readiness
          catalog-service: /actuator/health/readiness
~~~

If no specific path is declared, the default path is usually **/actuator/health**. Ensure the Actuator dependency is present or the application provides a corresponding endpoint itself.

Properties can change across release trains; verify against Spring Cloud Commons configprops in your BOM. Current defaults are typically an initial delay of 0 and an interval of 25 seconds.

### 9.2. Refetching the Instance List

If the delegate does not emit continuous updates yet the instance list can change, you can enable refetch:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 25s
        repeat-health-check: false
~~~

Refetch instructs the supplier to reload the instance list periodically. It does not turn a static properties source into a dynamic registry by itself; a new list only appears if the configuration source/DiscoveryClient actually returns updated data.

### 9.3. Choosing the Right Port and Path

Health checks may use a separate port if management endpoints run on a different port. Ensure:
- The configured port is reachable by the probe.
- The path does not require sessions or tokens not granted to the probe.
- TLS certificates are trusted.
- Network policies permit the probe.
- The endpoint returns an HTTP code the supplier treats as successful.
- The path does not redirect to a login page or external URL.

If probes hit a separate management port, they might miss failures on the main HTTP connector. For services needing to confirm the main server can accept requests, expose a readiness path on the main port or add synthetic transactions from consumers.

### 9.4. Do Not Add Redundant Health Checks Unconditionally

A registry may already health-check instances and LoadBalancer may already receive healthy lists. Adding another health-check supplier can:
- Increase probe requests to every instance.
- Create unnecessary load.
- Introduce two different intervals and two status sources.
- Produce conflicting results when one probe passes and the other fails.
- Increase the time to remove an instance from traffic if two layers maintain separate caches.

Only enable LoadBalancer probing when needed, such as with SimpleDiscoveryClient or an instance source lacking reliable health state.

## 10. Health Checks Do Not Prove Business Requests Succeed

An **/actuator/health** endpoint is typically lightweight and aggregates component statuses. It may not test:
- Whether a specific API has the right mapping.
- Whether request serialization/deserialization fails.
- Whether consumer authentication/authorization is accepted.
- Whether business database queries have sufficient permissions.
- Whether a broker can publish/consume messages on the right topic/queue.
- Whether a multi-step transaction completes.
- Whether thread pools or connection pools retain capacity under real load.

For example, a database health indicator might execute a lightweight validation query successfully while a complex business query times out due to locks or missing indexes. Similarly, an open broker TCP connection does not prove consumer groups are processing messages properly.

### 10.1. Synthetic Transactions

A synthetic transaction is a test request generated periodically to verify a representative flow from the client's perspective.

Example of a catalog read transaction:

~~~text
monitor
  -> resolve catalog-service
  -> select instance via LoadBalancer
  -> call GET /internal/synthetic/catalog
  -> application queries test data
  -> verify response schema and expected data
~~~

A synthetic endpoint should:
- Have a clear purpose and be read-only or safely repeatable.
- Use dedicated test data.
- Enforce short timeouts and rate limits.
- Avoid creating real orders, payments, emails, or side-effecting messages.
- Not bypass authentication/TLS if you want to verify the real call path.
- Record outcomes, latency, and which instance served the request.

Synthetic transactions should not be invoked too frequently or perform heavy operations. If every replica receives multiple complex probes, health checks themselves can generate failure-inducing load.

### 10.2. Checking from the Right Vantage Point

A check running on the instance itself via localhost does not test DNS, routing, or firewalls from consumers. Have checks across levels:
- Internal probe from the process or sidecar.
- Probe from the registry agent to the instance.
- Probe from a consumer in the same network zone.
- Probe from an external gateway/client.
- Synthetic transactions across critical business flows.

Differences across vantage points pinpoint whether a fault lies in the instance, registry path, or network path.

## 11. Observing with Metrics, Logs, and Traces

Do not rely on a single health endpoint. Combine:
- **Metrics:** request success/failure rates, latency, active instance counts, counts of failing to select an instance.
- **Logs:** heartbeat errors, timeouts, health check failures, registration updates, connection resets.
- **Traces:** requests through LoadBalancer to instances, time spent per hop, dependency calls, and returned errors.
- **Registry view:** registration status, lease/check state, host/port, and update timestamps.
- **Synthetic results:** transaction outcomes from consumer network zones.

### 11.1. Spring Cloud LoadBalancer Metrics

Spring Cloud Commons provides Micrometer statistics via **MicrometerStatsLoadBalancerLifecycle**. You can enable it:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

When a **MeterRegistry** is present, common meters include:

| Meter | Meaning |
| --- | --- |
| **loadbalancer.requests.active** | Gauge of active requests |
| **loadbalancer.requests.success** | Timer for requests ending with a response handed to the HTTP client |
| **loadbalancer.requests.failed** | Timer for requests ending with an exception |
| **loadbalancer.requests.discard** | Counter for requests that failed to obtain a ServiceInstance |

Meters may include tags for service instance, request, and response when data is available. **success** at the LoadBalancer layer does not necessarily mean an HTTP 2xx status or business success; track status/outcome in HTTP server/client instrumentation and business metrics separately.

### 11.2. Avoiding High-Cardinality Tags

Do not put user IDs, order IDs, session IDs, or URLs containing dynamic IDs into metric tags. With LoadBalancer, consider disabling the path in the URI tag if paths have high cardinality:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        include-path: false
~~~

Use traces or controlled logging for per-request details. Metrics should keep a small, stable set of tags to avoid inflating memory usage and backend costs.

### 11.3. Dashboards Should Offer Multiple Perspectives

An operational dashboard can be organized into:

| Panel | Data | Question |
| --- | --- | --- |
| Registry control plane | API latency/errors, leader/cluster status, client connections | Can we read/write the registry? |
| Registration | Instance count by service/status, heartbeat/check age | Are records fresh and complete? |
| Readiness | Ready/NotReady per replica, probe failures | Which instances can receive traffic? |
| LoadBalancer | active/success/failed/discard, selected instances | Which instances are consumers picking and how do requests fare? |
| HTTP server | request rate, status codes, latency | Are instances processing requests successfully? |
| Dependencies | DB pools, broker lag, connection errors | Which dependency is causing request failures? |
| Synthetic | transaction pass rate and latency by zone | Are end-to-end flows working? |

Alerts should be based on SLOs and sustained duration, avoiding paging on a single failed probe while real traffic remains normal.

## 12. Diagnosing Cases Where the Registry Is Healthy Yet the Service Fails

| Symptom | Likely Failing Layer | How to Check |
| --- | --- | --- |
| Registry API returns 200 yet no instances exist | Registration | Check service ID, auto-registration, write permissions, and status |
| Registry shows instance UP yet TCP times out | Advertised endpoint/network | Check host/port, routes, firewalls, security groups |
| Heartbeats steady yet requests return 500 | Application/dependency | Check readiness, logs, traces, and dependencies |
| Consul check critical yet consumer requests succeed | Probe path/agent network | Call health path from Consul agent and consumer separately |
| Eureka retains old instance after process death | Lease/cache propagation | Check heartbeat age, lease expiration, and client fetch |
| Pod Ready yet specific API fails | Readiness too broad | Check synthetic transactions and health groups |
| /actuator/health UP yet main port refuses connections | Separate management port | Probe readiness on main port or additional path |
| LoadBalancer selects an instance failing probes | Cache/supplier/fallback | Check supplier chain, cache, and behavior when all instances are unhealthy |
| One zone succeeds while another times out | Network zone/routing | Probe from each consumer zone and check advertised address |
| Registry and consumer display different statuses | Replication/client cache | Check update timestamps, fetch interval, and caches |
| Health check passes yet requests are slow | Capacity/saturation | Monitor thread pools, queues, connection pools, latency |
| Liveness continuously restarts multiple Pods | Misdesigned probe/cascading failure | Remove external dependencies from liveness and check thresholds |

### 12.1. Investigation Sequence

1. Call the registry's health endpoint from the service client's exact network namespace.
2. Read the service's record and verify host, port, status, and metadata.
3. Check heartbeat/lease or health-check timestamps.
4. Call the readiness endpoint directly on the instance from the consumer network.
5. Check DNS, TCP, TLS, and HTTP against the advertised address.
6. Send requests through the exact Spring Cloud LoadBalancer client.
7. Read LoadBalancer and HTTP client/server metrics.
8. Follow traces to identify which hop times out or returns errors.
9. Check the instance's dependencies and capacity.
10. Only alter status/deregister/rollout after pinpointing the root cause and impact scope.

Preserve timestamps and instance IDs throughout these steps to correlate the same event. Do not compare two logs from different timestamps and conclude the registry is wrong.

## 13. Testing Health Layers Independently

A health endpoint test does not replace a registry test, and a registry test does not replace a request test. Organize tests by goal.

| Test Type | Setup | What to Prove |
| --- | --- | --- |
| Registry availability test | Call registry API/health endpoint | Registry endpoint is reachable and returns valid responses |
| Registration test | Start discovery client, read record | Instance registers the right host/port/status |
| Heartbeat/lease test | Wait for renewal or simulate client disconnect | Registry detects stale registrations per policy |
| Actuator health test | Mock dependencies and call health group | Health status accurately reflects components/groups |
| Readiness test | Transition app state/dependency to not ready | Readiness endpoint returns appropriate status and HTTP code |
| LoadBalancer health test | Two instances, one passing probe and one failing | Supplier filters per health policy |
| Consumer reachability test | Call from consumer container/Pod | DNS, routing, TLS, and ports work |
| Synthetic transaction test | Call non-side-effecting business flow | End-to-end request completes properly |
| Failure injection test | Controlled disconnect of registry or dependency | System degrades per policy without cascading failure |

### 13.1. Testing Actuator Readiness

Example with MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoint.health.probes.enabled=true"
})
@AutoConfigureMockMvc
class ReadinessEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readinessEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
    }
}
~~~

This is only an example for the default healthy state. Real tests should control readiness state or mock a HealthIndicator to verify both DOWN/OUT_OF_SERVICE and HTTP 503 cases.

### 13.2. Testing the LoadBalancer Health Supplier

Create two ServiceInstances:
- Instance A returns HTTP 200 on the readiness path.
- Instance B returns HTTP 503 or times out.
- Enable HealthCheckServiceInstanceListSupplier.
- Wait for the first health check to finish using polling with a timeout.
- Confirm the healthy list and request selection.

Do not use long fixed `Thread.sleep` calls without checking that the scheduler has run. Use Awaitility or observable conditions for stable tests.

If all instances are unhealthy, check the fallback behavior of your exact Spring Cloud Commons version. Current documentation describes the supplier returning the full retrieved list when no instance is healthy; if your application requires fail-closed behavior, test and explicitly configure/customize that policy.

### 13.3. Testing When the Registry Disconnects

A resilience test can:
1. Start a test registry server.
2. Register two instances.
3. Let the consumer fetch the registry list.
4. Disconnect the registry.
5. Send requests through the client holding the cache.
6. Observe whether requests are still routed.
7. Let the cache/lease expire or refresh discovery.
8. Verify behavior when no usable instances remain.

Results depend on the registry client, caches, retries, and timeouts. Do not write a blanket assertion that losing the registry causes every request to fail immediately or always keep succeeding.

## 14. Designing Alerts and SLOs

Alerts should tie to user impact or serving capacity. Signals that can be combined include:

- Sustained high registry API error rate.
- Healthy instance count dropping below the required threshold.
- Heartbeat/check age exceeding threshold.
- Readiness failures increasing across multiple replicas.
- Increasing LoadBalancer discards.
- Increasing HTTP 5xx or timeouts.
- Synthetic transactions failing from one or more zones.
- p95/p99 latency breaching SLO.
- Exhausted dependency pools or rising queue/consumer lag.

Do not alert merely because the registry is unreachable for a few seconds if consumers still have valid caches and request success has not degraded. Conversely, a completely healthy registry paired with continuously failing synthetic transactions is a priority data plane incident signal.

Severity levels can be divided into:
- **Warning:** registry or health probes have errors, yet request success/SLO has not degraded.
- **Critical:** request success drops, latency breaches SLO, or not enough instances remain to serve traffic.
- **Capacity risk:** healthy instance count is low, yet current requests still succeed.

Thresholds should be based on SLOs, load, minimum replica count, and acceptable recovery time.

## 15. Operational Principles

- Measure registry availability, registration freshness, readiness, and request success separately.
- Do not treat heartbeats as business health checks.
- Do not treat HTTP 200 from the registry as proof an instance can handle requests.
- Design liveness for internal failures recoverable via restart.
- Design readiness around traffic-handling ability and genuinely mandatory dependencies.
- Use startup probes for slow-starting applications.
- Do not include external dependencies in liveness if their failure could cause mass restarts.
- Ensure the registry agent hits the right health path/port/TLS.
- Avoid duplicate probing if the registry already supplies reliable health state.
- Understand HealthCheckServiceInstanceListSupplier's fallback when all instances are unhealthy.
- Check consumer caches and propagation delays before concluding a status failed to update.
- Use synthetic transactions to check critical flows from the client's viewpoint.
- Correlate metrics, logs, traces, and registry records on a single timeline.
- Never expose health details, topology, or credentials to unauthorized parties.

## 16. Checklist When a Service Reports UP Yet Requests Fail

- [ ] Registry API is reachable from the service client.
- [ ] Registration has the right service ID, instance ID, host, and port.
- [ ] Heartbeat/lease or registry health check is fresh.
- [ ] Eureka enables health propagation if Actuator status is needed.
- [ ] Consul agent calls the right health-check path and port.
- [ ] Actuator readiness accurately reflects conditions for accepting traffic.
- [ ] Liveness does not depend on external databases/brokers/APIs.
- [ ] Kubernetes readiness and EndpointSlice reflect Pod readiness.
- [ ] Separate management port does not produce false positives.
- [ ] LoadBalancer supplier and cache are configured appropriately.
- [ ] Fallback when no healthy instances remain is understood and tested.
- [ ] Consumer has DNS resolution and routing to the advertised endpoint.
- [ ] TLS, authentication, authorization, and NetworkPolicy do not block requests.
- [ ] LoadBalancer and HTTP server/client metrics have data.
- [ ] Synthetic transaction verifies critical business flows.
- [ ] Alerts rely on request success/SLO rather than registry pings alone.

## Key Takeaways

A healthy registry only tells you the control plane can respond; fresh heartbeats only tell you the client keeps checking in; readiness tells you the instance is ready per configured criteria; request success is what confirms consumers complete the real call path. Eureka relies on heartbeats by default and needs health propagation enabled to sync Actuator status; Consul can poll an HTTP health endpoint periodically; Kubernetes uses readiness to control Service endpoints; Spring Cloud LoadBalancer has its own health-check supplier, especially useful with SimpleDiscoveryClient. Observe all four layers and verify from the consumer's network zone before concluding a service is healthy.

## References

- Spring Cloud Netflix – Eureka Health Checks: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Netflix – Configuration Properties: https://docs.spring.io/spring-cloud-netflix/reference/configprops.html
- Spring Cloud Consul – Service Discovery and Health Checks: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Commons – LoadBalancer Health Check and Statistics: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Boot – Actuator Endpoints and Health Groups: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot – Health Endpoint API: https://docs.spring.io/spring-boot/api/rest/actuator/health.html
- Kubernetes – Liveness, Readiness, and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
