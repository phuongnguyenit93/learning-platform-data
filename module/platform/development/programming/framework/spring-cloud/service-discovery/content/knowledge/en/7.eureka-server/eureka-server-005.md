# Reading the Dashboard and Inspecting Applications and Instances

Eureka Server provides a Dashboard for operators to observe registered applications and the instances currently stored in the registry. When a service does not appear, has an unexpected status, or a consumer cannot reach an instance, the Dashboard is a useful starting point for inspection.

The Dashboard reflects the data Eureka Server knows at the time it is rendered. A row showing an instance with status `UP` is not a guarantee that the next request will succeed: data may lag due to heartbeats, caching, network issues, or the self-preservation mechanism. Therefore, combine Dashboard information with instance addresses, health endpoints, application logs, and Eureka's REST API.

This lesson belongs to the `SPRING_CLOUD_SERVICE_DISCOVERY` module, focusing on finding instances by service name via `DiscoveryClient`, `ServiceRegistry`, Eureka, or Consul, while understanding registration lifecycle, health checks, load balancing, security, and handling registry divergence. This content guides you through reading the main sections of the Eureka Dashboard and inspecting an application from the service level down to each individual instance.

## 1. Opening the Eureka Dashboard

In a common development configuration, Eureka Server runs on port `8761`. Unless the context path or endpoint configuration has been changed, open:

```text
http://localhost:8761/
```

The Dashboard is a web UI provided by Eureka Server. The actual access URL depends on `server.port`, `server.servlet.context-path`, reverse proxy settings, and how the server is deployed. If running in a container or on a remote host, replace `localhost` with a hostname or address reachable from the operator's machine.

A minimal Eureka Server application typically has the following configuration:

```yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
```

And enable Eureka Server in the Spring Boot application:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
```

The two properties `register-with-eureka: false` and `fetch-registry: false` are typically used for a standalone server so it does not register itself or query itself as a Eureka client. In a peer-aware cluster, client settings and the peer list will differ; do not copy the standalone configuration verbatim for all topologies.

## 2. Identifying Sections on the Dashboard

Label names and layout may vary across Eureka versions, but the Dashboard typically has the following main areas:

| Section | Contents | Inspection purpose |
|---|---|---|
| System Status | Status details of Eureka Server such as environment, datacenter, uptime, or relevant operational info. | Confirm you are viewing the right server and that it has started. |
| DS Replicas | Eureka peers/replicas known to the server. | Verify peer configuration and connectivity between servers. |
| Instances currently registered with Eureka | List of registered applications and instances. | Inspect service IDs, instance counts, and each instance's status. |
| General Info or additional details | Information about the registry, leases, renewals, or configuration depending on the version. | Assist with investigating heartbeats, eviction, and self-preservation. |

<text color="secondary" size="sm">The actual Dashboard depends on the Spring Cloud Netflix Eureka version, Eureka Server version, and UI configuration. Labels in the table are functional identifiers, not a guarantee that every version shares the exact same layout.</text>

## 3. Reading the Registered Applications List

The `Instances currently registered with Eureka` section is the most important area when inspecting providers. Eureka typically groups instances by application/service name. For example, `ORDER-SERVICE` may have three instances:

| Application | Illustrative Instance ID | Host/Port | Status |
|---|---|---|---|
| `ORDER-SERVICE` | `order-01` | `10.0.1.21:8080` | `UP` |
| `ORDER-SERVICE` | `order-02` | `10.0.1.22:8080` | `UP` |
| `ORDER-SERVICE` | `order-03` | `10.0.2.15:8080` | `OUT_OF_SERVICE` |

Application names are usually displayed in uppercase in the Eureka UI, even though `spring.application.name` in configuration may be written in lowercase. Match the service ID that the consumer looks up against the registered application name; do not rely on UI capitalization to infer an instance ID.

When reviewing an application group, check in order:

1. **Application name:** does it match the service ID used by the consumer?
2. **Instance count:** does the count shown on the Dashboard match the expected number of replicas?
3. **Instance ID:** does each running instance have a distinct identifier with no unintended collisions?
4. **Host and port:** is the address reachable from the consumer's network?
5. **Status:** is the instance in a state eligible to serve traffic?
6. **Links and metadata:** do the status page, home page, health URL, or metadata point to appropriate addresses?

The instance count on the Dashboard is the number of records Eureka currently holds, not necessarily the number of processes running at every instant. A process may not have registered yet; conversely, a stale record may still remain after a process has stopped.

## 4. Understanding Instance Statuses

Eureka represents instance states with values such as `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, and `UNKNOWN`. Their actual meaning should be interpreted alongside the client's health configuration and lifecycle.

| Status | General meaning | Next check |
|---|---|---|
| `UP` | The instance is recorded by Eureka as active. | Check the actual endpoint and connectivity from the consumer. |
| `DOWN` | The instance is marked inactive/unavailable. | Inspect health, client logs, heartbeat errors, or status updates. |
| `STARTING` | The instance is in its startup phase. | Check readiness and when the application starts registering. |
| `OUT_OF_SERVICE` | The instance is marked not to serve traffic. | Check maintenance actions, application state, or shutdown procedures. |
| `UNKNOWN` | Eureka does not yet have a clearly determined status. | Check the registration process, status updates, and health configuration. |

Do not treat row status colors as a stable contract across Dashboard versions. Read the actual status value and cross-check with the API or logs when confirmation is needed.

### 4.1. `UP` Does Not Mean Endpoints Are Guaranteed Healthy

A Eureka client typically maintains registration via heartbeats/leases. Depending on configuration, the client may integrate application health state. If health checks are not integrated, a process still sending heartbeats may continue to be considered `UP` by the registry even when business endpoints are failing.

For the client to use Spring Boot Actuator's health status, expose the appropriate endpoints and enable health check integration according to your version's configuration. For example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

eureka:
  client:
    healthcheck:
      enabled: true
  instance:
    status-page-url-path: ${management.endpoints.web.base-path}/info
    health-check-url-path: ${management.endpoints.web.base-path}/health
```

With Spring Boot Actuator's default configuration, the base path is normally `/actuator`; if `management.endpoints.web.base-path` has been customized, the URLs must match the actual value. Ensure the health endpoint is properly exposed and secured. Do not open management endpoints to public networks just so the Dashboard can display clickable links.

## 5. Inspecting a Specific Instance

Once you find the application on the Dashboard, select the instance to investigate and note the following details:

- **Instance ID:** identifier of the running instance to inspect.
- **Host name / IP address:** address published to consumers.
- **Port:** port registered by the application.
- **Status:** current status stored by Eureka.
- **Home page URL:** root URL declared for the instance, if any.
- **Status page URL:** application status info page, if declared.
- **Health check URL:** integrated or published health endpoint, depending on configuration and UI.
- **Metadata:** additional info such as zone, version, instance group, or application-published data.

These URLs are typically constructed from registration metadata. The fact that the Dashboard renders a link does not mean Eureka successfully called that endpoint every time the page was opened. Open or curl the endpoint from a machine sharing the consumer's network perspective to verify DNS, routing, firewalls, and TLS.

### 5.1. Checking the Endpoint from a Consumer Machine

For example, an instance registers `10.0.1.21:8080` and exposes Actuator health at `/actuator/health`. You can test it with `curl`:

```bash
curl -i http://10.0.1.21:8080/actuator/health
```

If the service uses HTTPS or requires authentication, use the scheme and credentials appropriate for the environment. Do not put real tokens or passwords into commands saved in documentation, shell history, or shared logs.

When the endpoint is unreachable, break down the checks:

1. Does the host resolve properly via DNS?
2. Is the port open from the consumer's network?
3. Is the application bound to a network interface reachable by consumers?
4. Are container ports, service ports, or reverse proxies mapped correctly?
5. Do the TLS certificate and hostname match?
6. Does the endpoint require authentication or specific access permissions?

If testing from the provider machine succeeds while testing from the consumer fails, the issue likely lies in network routing, firewall rules, DNS, or the registered address rather than discovery logic.

## 6. Checking Whether an Application Registers Correctly with Eureka

A Eureka client needs the appropriate dependency, a service ID, and a reachable Eureka Server URL. Illustrative client configuration:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
  instance:
    prefer-ip-address: true
```

In multi-host or container environments, `localhost` only points to the container/host running the client itself. Replace it with a Eureka Server address that the client can actually reach. `prefer-ip-address: true` makes the client advertise its IP instead of its hostname in certain configurations; enable it only when that IP is routable from the relevant consumers.

When the application does not appear on the Dashboard, check in order:

1. Did the application finish starting and is the Eureka client starter on the classpath?
2. Does `spring.application.name` match the expected service ID?
3. Does `eureka.client.service-url.defaultZone` have the right URL and include `/eureka/` matching the server configuration?
4. Can the client connect to Eureka Server? Check DNS, port, TLS, proxies, and authentication.
5. Is auto-registration disabled or deactivated by conditional configuration?
6. Do client logs show registration errors, heartbeat renewal errors, or metadata serialization errors?
7. Is the server receiving registrations in the expected profile, namespace, or cluster?

The Dashboard not showing an application immediately after the process starts is not necessarily an error. Check client logs and wait for the registration/sync interval matching your configuration rather than concluding from a single refresh.

## 7. Inspecting via the Eureka REST API

The Dashboard is convenient for visual inspection; the REST API is useful when you need structured data, monitoring scripts, or comparisons across servers. With common default settings, the Eureka API lives under the `/eureka` context.

| Request | Purpose |
|---|---|
| `GET /eureka/apps` | Retrieve the list of applications and registrations. |
| `GET /eureka/apps/{appName}` | Retrieve information for a single application by name. |
| `GET /eureka/apps/{appName}/{instanceId}` | Retrieve information for a specific instance. |

Example fetching the application list in JSON format:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps
```

Fetching a single application:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/ORDER-SERVICE
```

Fetching a single instance:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/ORDER-SERVICE/order-01
```

`appName` and `instanceId` must match the registration data. Depending on the version, server context path, reverse proxy, and security settings, actual URLs or response formats may vary. The examples above only use GET to read data; POST/PUT/DELETE operations against the registry mutate system state and must be controlled separately.

When comparing the Dashboard and the API, inspect the same Eureka Server, at the same time, and for the same service ID. If the two results differ, check caching, replicas, and update timing.

## 8. Reading DS Replicas and Checking the Eureka Cluster

In a peer-aware deployment, the `DS Replicas` section displays the peer servers known to the current node. This section helps verify the peering configuration between Eureka Servers.

When operating a cluster, verify:

- Does the peer list contain the expected server hostnames and ports?
- Can the peers resolve DNS and connect over the network?
- Does `eureka.client.service-url.defaultZone` on each server point to the right peers?
- Are the servers using consistent naming and datacenter/region configuration according to the intended architecture?
- Are there replication, heartbeat, or peer connection error warnings in the logs?

Do not merely see peer names listed under `DS Replicas` and conclude replication is completely healthy. Check logs and the registration data observed from each peer. In a cluster with sync latency, two Dashboards may temporarily display different instance counts or statuses.

## 9. Heartbeats, Eviction, and Self-Preservation

Eureka clients periodically renew their leases via heartbeats. If the server does not receive renewals within the configured duration, the instance may be marked expired and evicted. Exact intervals and thresholds depend on client/server configuration.

Eureka has a self-preservation mechanism to limit mass instance removal when the number of received heartbeats drops abnormally. This mechanism prevents mistakenly deleting registrations during a widespread network outage, but it can cause some stale records to remain visible after a process has stopped.

When you see a stale instance on the Dashboard:

1. Verify whether the process or container is still running.
2. Check client logs to see whether heartbeats are being sent and received by the server.
3. Check server logs for lease expiration, eviction, and self-preservation messages.
4. Check peer status and replication if running a cluster.
5. Compare the registration in the Dashboard with the REST API and lookup results from consumers.
6. Check lease/eviction wait times against the actual configuration.

Do not disable self-preservation just to make the Dashboard look cleaner. First determine whether the drop in heartbeats is because instances actually died or because the network between clients and server is experiencing issues. Changing thresholds or disabling the safeguard can cause the registry to mistakenly delete large numbers of instances during a connectivity disruption.

## 10. Common Situations on the Dashboard

| Symptom | Possible cause | Initial action |
|---|---|---|
| Application not visible | Client has not registered, wrong server URL, wrong profile, or auto-registration disabled. | Check client logs, service ID, starter, and `defaultZone`. |
| Application exists, but expected instances are missing | Some replicas have not started yet or failed to register. | Compare actual replica count with registration count; check each instance's logs. |
| Instance is `DOWN` | Health/status was updated as unavailable or client encountered errors. | Check Actuator, application logs, and status update mechanism. |
| Instance is `OUT_OF_SERVICE` | Instance is under maintenance or intentionally drained from traffic. | Check deployment procedures, readiness, and administrative actions. |
| Instance is `UP`, but calls fail | Wrong registered address, stale data, network error, or unhealthy endpoint. | Call the URL from the consumer's network; verify host, port, DNS, TLS, and health. |
| Stopped instance still remains | Deregistration failed, lease has not expired yet, or self-preservation is retaining the record. | Check renewals, eviction, self-preservation, and peer logs. |
| Peers show different lists | Slow replication, lost peer connectivity, or queried at different times. | Compare logs, peer connectivity, REST API, and update timestamps. |
| Status/home page link cannot be opened | Wrong metadata URL or operator machine has no route to that host. | Check the registration URL and network access from the client machine. |

## 11. End-to-End Service Inspection Workflow

When there is a report such as "consumer cannot find `order-service`" or "calling instance fails," you can follow this workflow:

**Step 1 – Confirm the right Eureka Server.** Open the Dashboard and check the address, System Status, profile, and peers. Avoid looking at dev, staging, or another cluster node by mistake.

**Step 2 – Find the application name.** Confirm whether `ORDER-SERVICE` appears. Cross-check with the provider's `spring.application.name` and the service ID the consumer is looking up.

**Step 3 – Count instances.** Compare the record count against the expected number of replicas. If any are missing, inspect startup and registration logs of each provider.

**Step 4 – Inspect each status.** Note the instance ID, status, host, and port. For unexpected statuses, check health checks, heartbeats, and lifecycle events.

**Step 5 – Test connectivity from the consumer.** Use the host/port from the registration to check DNS, routing, firewalls, TLS, and the health endpoint. Do not test only from the provider host.

**Step 6 – Cross-check the REST API.** Query `/eureka/apps/ORDER-SERVICE` and the specific instance to confirm the registry payload being returned.

**Step 7 – Inspect cache and LoadBalancer.** If the Dashboard/API lists the instance yet the consumer cannot use it, inspect the discovery cache, supplier, filters, and LoadBalancer policy on the consumer.

**Step 8 – Check peers and self-preservation.** If data differs across nodes or stale instances persist, inspect replication, renewals, eviction, and server warnings.

**Step 9 – Record evidence.** Save timestamps, service ID, instance ID, status, host/port, relevant logs, and health/API outputs so operations teams can compare before and after changes.

## 12. Securing the Dashboard and Registry Data

The Dashboard can expose service names, internal addresses, ports, metadata, and system topology. Therefore, the Dashboard or Eureka REST API should not be exposed publicly to the Internet without a clear need and explicit protections.

Principles to apply:

- Place the Dashboard and REST API behind an appropriate authentication/authorization layer.
- Restrict access via management networks, VPNs, or network policies.
- Use TLS when accessing over untrusted networks.
- Never put tokens, passwords, or secrets into registration metadata.
- Restrict registry view and mutation permissions by operational role.
- Do not let health or info endpoints leak sensitive configuration.
- Record audit logs for administrative operations that alter status or registrations.

The Dashboard is primarily for observability; it does not replace monitoring, alerting, or auditing systems. In production, combine Eureka Server metrics and logs with application and network monitoring.

## 13. Dashboard Reading Checklist

| Category | Question |
|---|---|
| Server | Are you viewing the right Eureka Server and environment? |
| System Status | Has the server started stably and are there operational warnings? |
| DS Replicas | Do peers have the right addresses and are they reachable? |
| Application | Does the service ID match the name the consumer looks up? |
| Instance count | Does the registration count match the expected replica count? |
| Instance identity | Are instance IDs unique and matching the running deployments? |
| Status | Is the instance `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, or `UNKNOWN`? |
| Network address | Are the host/port reachable from the consumer? |
| Health | Are Actuator/health and health integration working? |
| Lease | Do heartbeats, eviction, and self-preservation explain any stale records? |
| API | Does the REST API return the same data as the Dashboard? |
| Consumer | Are the discovery cache and LoadBalancer using the right service ID and instances? |
| Security | Are the Dashboard, REST API, and management endpoints secured? |

## Conclusion

The Eureka Dashboard helps observe registered applications, instance counts, statuses, addresses, and Eureka Server peer information. When inspecting a service, start with the application name, count instances, read statuses, verify host/port, and test health endpoints from the consumer's network. Use the REST API to verify structured data and check `DS Replicas`, heartbeats, eviction, and self-preservation whenever registry discrepancies are suspected.

The Dashboard reflects the state currently stored by Eureka; it does not guarantee that endpoints are still healthy or reachable at request time. Reliable operations require combining Dashboard data with client/server logs, health checks, network connectivity, the discovery cache, and Spring Cloud LoadBalancer. Protecting the Dashboard and registry is also essential because they reveal the internal service structure of the system.
