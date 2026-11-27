# Syncing Actuator Status with Eureka Health Check

A Spring Boot application can keep sending regular heartbeats to Eureka even when a critical dependency has failed. If Eureka relies solely on heartbeats, the registry may continue publishing the instance as UP and consumers will keep selecting that instance for requests.

Spring Cloud Netflix Eureka Client can synchronize the application's health status with its instance status in Eureka. When this integration is enabled, Eureka Client uses Spring Boot Actuator's health handler to aggregate the health contributors in the application context, maps the result to a status Eureka understands, and sends that status along with instance updates.

This mechanism helps the registry reflect the application's actual ability to serve requests. To configure it correctly, you need to distinguish heartbeats from health checks, understand how Actuator aggregates status, place the property in the right configuration file, control which HealthIndicators participate, and verify the result from the consumer's perspective.

## 1. Why Sync Actuator with Eureka?

Eureka uses heartbeats to tell whether a client is still maintaining its registration. A successful heartbeat proves the client can still reach Eureka Server; it does not prove that the application's APIs can execute business logic.

For example, `order-service` might be running and sending steady heartbeats while its database connection is broken. If Eureka continues publishing the instance as UP, `payment-service` or other consumers may keep routing requests to an instance that cannot complete work.

Spring Boot Actuator provides health indicators to evaluate the application and its dependencies. Spring Cloud Netflix can use that result to update the instance status in Eureka.

| Mechanism | What Does It Check? | How Is the Result Used? |
|---|---|---|
| Eureka heartbeat | Whether the client is still sending lease-renewal signals | Keeps or expires the registration |
| Actuator HealthIndicator | Whether the application and checked components are healthy | Computes the overall health status |
| Eureka health handler | Maps Actuator status to Eureka instance status | Updates the status published in the registry |
| Consumer discovery client | Which instances are published and eligible for use | Supplies the instance list for service calls |

Heartbeats and health checks complement each other. An application can send heartbeats successfully while its health status is DOWN. Conversely, a local health indicator might report UP while the client cannot reach Eureka; in that case, the registry can still let the lease expire after a period of time.

## 2. Distinguishing the Health Endpoint from the Eureka Health Handler

Two concepts are easy to confuse:

The **Actuator health endpoint** is an HTTP endpoint, commonly accessed at `/actuator/health` in current default Spring Boot configurations. This endpoint lets operators, monitoring systems, or authorized probes inspect the application's health status.

**EurekaHealthCheckHandler** is a Eureka Client component that reads health contributors from the application context, aggregates their status, and converts it into a Eureka instance status. Eureka Client invokes this handler while refreshing instance information.

This means:

- Eureka Server does not call HTTP `/actuator/health` on each instance by default to check health.
- Eureka Client aggregates health on the application side and sends the status alongside registration/heartbeat updates.
- Exposing the `/actuator/health` endpoint is useful for observability and probes, but exposing the endpoint alone does not enable status syncing with Eureka.
- The `eureka.instance.healthCheckUrlPath` field publishes the health URL in instance metadata. That metadata URL field is separate from the property that enables the client-side health handler.

~~~mermaid
flowchart TD
    subgraph APP["Spring Boot Application"]
        H1["Database HealthIndicator"]
        H2["Custom HealthIndicator"]
        H3["Other HealthContributors"]
        AGG["StatusAggregator"]
        EH["EurekaHealthCheckHandler"]
        EP["HTTP /actuator/health"]
        H1 --> AGG
        H2 --> AGG
        H3 --> AGG
        AGG --> EH
        H1 --> EP
        H2 --> EP
        H3 --> EP
    end

    EH -->|"InstanceStatus"| EC["Eureka Client"]
    EC -->|"Heartbeat / instance update"| ES[("Eureka Server")]
    ES -->|"Registry data"| CON["Consumer"]
~~~

The diagram shows that the HTTP endpoint and the health handler both draw from health contributors, yet serve different roles. Do not assume Eureka Server has to call the HTTP endpoint for status to synchronize.

## 3. Required Dependencies

The provider application needs Eureka Client and Spring Boot Actuator. Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud dependency versions should be managed by a Spring Cloud BOM compatible with your project's Spring Boot version. Do not pin an individual Eureka Client version if the BOM already manages that artifact.

With only Eureka Client added, the application can register and send heartbeats. To leverage Spring Boot's health indicators, you need Actuator and the indicators appropriate for your checks.

## 4. Enabling Health Status Sync in application.yml

Basic configuration example:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8082

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
    healthcheck:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

The key property is:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

This property enables Eureka Client's integrated health check handler. Across release trains, the default value of this property may vary; Spring Cloud Netflix 4.3.3 configuration documentation lists the default as `true`. Declaring it explicitly makes the configuration intent clear and avoids relying on version-specific defaults.

**Place this property in `application.yml` or equivalent application configuration. Do not place it in `bootstrap.yml`.** Spring Cloud Netflix documentation warns that placing this property in bootstrap configuration can cause side effects where the instance registers with status UNKNOWN.

If using profiles, you can place the property in the corresponding application profile file, such as `application-prod.yml`, as long as it is loaded during application configuration at the right phase.

## 5. How Does Actuator Aggregate Status?

Spring Boot represents the outcome of each health contributor as a `Status`. Common statuses include:

| Actuator Status | Meaning |
|---|---|
| `UP` | Checked component is operating normally |
| `DOWN` | Component is unresponsive |
| `OUT_OF_SERVICE` | Component is intentionally out of service |
| `UNKNOWN` | Condition could not be determined |

An application can have multiple HealthIndicators: database, disk space, broker, custom dependencies, or business components. `StatusAggregator` combines these outcomes into a single overall status.

For example:

| Database | Message broker | Possible Aggregated Status |
|---|---|---|
| UP | UP | UP |
| DOWN | UP | DOWN |
| UP | DOWN | DOWN |
| UP | OUT_OF_SERVICE | Depends on status ordering and aggregator configuration |

StatusAggregator uses a precedence order to determine the overall status when multiple results exist. If the application introduces custom statuses, you must configure the precedence order and appropriate mapping; do not assume every custom status is automatically understood by Eureka.

### 5.1. What Does EurekaHealthCheckHandler Do?

When enabled, Spring Cloud Netflix creates `EurekaHealthCheckHandler`. The handler collects `HealthContributor` and `ReactiveHealthContributor` beans in the application context, aggregates their status, and maps it to Eureka's `InstanceInfo.InstanceStatus`.

Conceptually:

1. Reads the registered health contributors.
2. Runs each contributor's health check.
3. Collects the returned statuses.
4. Uses StatusAggregator to compute the overall status.
5. Maps the overall status to a Eureka instance status.
6. Supplies the status to Eureka Client when the client refreshes instance information.

The implementation also avoids pulling discovery's own Eureka health indicator into the aggregation loop in a way that causes a health feedback loop. If Eureka's health check depended on the Eureka status it itself publishes, the application could fall into a self-referential cycle.

### 5.2. Mapping to Eureka Status

Eureka has its own instance status vocabulary such as `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE`, and `UNKNOWN`.

Default mapping depends on the Spring Cloud Netflix version and release train mapping rules. For instance, common implementations map `UP` to `UP`, `DOWN` to `DOWN`, and `UNKNOWN` to `UNKNOWN`; `OUT_OF_SERVICE` may be translated into a non-traffic-receiving status such as `DOWN` depending on the implementation. Unmapped custom statuses may become `UNKNOWN`.

Therefore, check the implementation and documentation for the exact version you are using before relying on a specific mapping. Never assume Actuator's `OUT_OF_SERVICE` is always preserved verbatim as `OUT_OF_SERVICE` in Eureka.

## 6. Creating a HealthIndicator for a Critical Dependency

Actuator includes several built-in health indicators when corresponding dependencies appear on the classpath. An application can also implement a custom `HealthIndicator` to check a specific business condition or dependency.

Example:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class InventoryDependencyHealthIndicator
        implements HealthIndicator {

    @Override
    public Health health() {
        boolean available = checkInventoryDependency();

        if (available) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("dependency", "inventory")
                .build();
    }

    private boolean checkInventoryDependency() {
        // Replace with a real check using an appropriate timeout.
        return true;
    }
}
~~~

This is a structural example. In a real application, the check method must probe the actual dependency, enforce a clear timeout, and avoid generating excessive load. Do not return a hardcoded `UP` like the placeholder above in production.

When the health indicator reports DOWN, the handler can aggregate it into a non-ready status and Eureka Client publishes that status. Consumers using Eureka will avoid selecting instances not in UP status when UP-only filtering is enabled.

### 6.1. Choosing Which Dependencies Count Toward Overall Health

Not every dependency should dictate whether an instance can accept traffic. Categorize them:

- Mandatory dependencies required for primary requests, such as a database without which the business capability cannot function.
- Dependencies whose degradation still allows the service to serve partial functionality.
- Dependencies used only for monitoring, analytics, or background tasks that do not affect primary requests.

If an optional dependency returns DOWN while the service can still handle business requests, including that indicator in aggregate health can cause Eureka to pull the instance prematurely. Conversely, omitting an essential dependency allows Eureka to keep advertising an instance that cannot process requests.

A HealthIndicator should reflect the serving capability consumers require, not merely every technical error that occurs in the process.

## 7. Distinguishing Liveness and Readiness

These two concepts are useful when applications run in containers or Kubernetes:

- **Liveness:** is the process still alive and able to keep running?
- **Readiness:** is the application ready to receive business requests?

A process can report liveness UP while readiness is not yet satisfied because it is warming caches or waiting for database connections. During that window, the instance should not receive traffic just because the JVM is alive.

Spring Boot supports health groups for liveness and readiness in compatible versions. You can enable probe endpoints with:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

This configuration is useful for deployment platform probes, but it does not guarantee Eureka uses only the readiness group. EurekaHealthCheckHandler aggregates health contributors in the application context according to its implementation. Verify which contributors and status aggregator participate so liveness, readiness, or an auxiliary indicator does not alter Eureka status unexpectedly.

A common policy:

- Instance not ready: do not publish as UP for traffic.
- Instance ready: overall health passes and Eureka publishes UP.
- Instance draining: transition to a non-traffic-receiving status via a supported mechanism, then finish in-flight requests.
- Instance failing: overall health switches to an unavailable status and consumers stop selecting the instance once data refreshes.

## 8. When Status Propagates to Eureka

Eureka Client continues sending heartbeats to renew its lease. When the health handler is registered, the client computes the application status during instance information refreshes and sends changes to Eureka Server via the registration/heartbeat update mechanism.

This means the status on the Eureka dashboard does not necessarily change at the exact instant `/actuator/health` changes its response.

Latency can arise from:

- Heartbeat and instance-information refresh intervals.
- Instance update/replication intervals.
- Network connectivity between Eureka Client and Eureka Server.
- Consumer-side registry cache and fetch intervals.
- Execution time of individual HealthIndicators.

Do not treat a single `/actuator/health` call as proof that every consumer has received the new status. Check the status on Eureka Server and the instance list seen from the consumer side.

## 9. Health URLs in Eureka Metadata

A Eureka instance has URL properties such as status page and health check URLs. These URLs are published in metadata so other systems or operational tools can reference them.

Example path configuration:

~~~yaml
eureka:
  instance:
    statusPageUrlPath: /actuator/info
    healthCheckUrlPath: /actuator/health
~~~

The actual paths must match the application's Actuator configuration. If you change the management base path, servlet path, context path, or run behind a proxy, update the published URLs so consumers and operational tools reach the right endpoints.

Remember:

- `eureka.client.healthcheck.enabled` turns on the client-side health handler mechanism.
- `eureka.instance.healthCheckUrlPath` configures the health URL published in instance metadata.
- The two properties serve different purposes.
- Having a health URL in metadata does not mean Eureka Server actively polls that endpoint by default.

If Actuator uses a separate management port, check both the published port and scheme. An incorrect metadata URL can break monitoring systems or consumers that rely on it, even while the internal health handler works fine.

## 10. Verifying Synchronization Results

After enabling the configuration, verify from three perspectives:

1. **Actuator:** what health status does the application return?
2. **Eureka Server:** what status is the instance published with?
3. **Consumer:** does the discovery client still include that instance in its usable list?

Example calling the Actuator endpoint:

~~~bash
curl http://localhost:8082/actuator/health
~~~

If the application enforces security, include appropriate credentials. Do not open detailed health endpoints to public networks merely for testing convenience.

You can inspect the Eureka dashboard at the server address, typically:

~~~text
http://localhost:8761/
~~~

Or query the registry via the Eureka API matching your server version.

### 10.1. Test Scenarios

| Scenario | Expected Actuator | Expected Eureka | Expected Consumer |
|---|---|---|---|
| All dependencies healthy | UP | UP | Can select instance |
| Mandatory dependency fails | DOWN or unavailable status | No longer UP | Does not select instance if filtering UP only |
| Dependency recovers | UP | Returns to UP after update | Instance reappears after refresh |
| Application draining | Status per drain policy | Status not accepting new traffic | Stops selecting instance after update |
| Eureka Server connection lost | Actuator can still be UP | Registry has not received new updates | Consumer may see stale data during transition |

Test both the transition to DOWN and recovery back to UP. Some configuration bugs only surface on the first health transition or during instance recovery.

## 11. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Actuator is DOWN but Eureka stays UP | Health handler not enabled or not registered | Check `eureka.client.healthcheck.enabled` and Actuator dependency |
| Eureka registers UNKNOWN at startup | Healthcheck property placed in bootstrap configuration or config not ready | Move property into application configuration |
| Eureka stays DOWN even though health endpoint is UP | Another HealthIndicator is still DOWN or aggregator picks a stricter status | Inspect every contributor and StatusAggregator |
| Eureka is DOWN yet an API still succeeds | Health policy includes non-essential dependencies | Reclassify indicators based on business serving capability |
| Consumer still calls failing instance | Consumer uses stale cache or does not filter UP-only instances | Check refresh, cache, and `eureka.client.filter-only-up-instances` |
| Consumer does not see instance after recovery | Status not replicated yet or client has not refreshed registry | Check heartbeat, update interval, and registry fetch |
| Health metadata URL returns 404 | Context path or Actuator base path mismatch | Update `healthCheckUrlPath` and check management port |
| Custom health status becomes UNKNOWN | Status lacks a mapping to Eureka InstanceStatus | Configure version-specific mapping or write a custom HealthCheckHandler |

### 11.1. Identifying the HealthIndicator Causing DOWN

Actuator often aggregates many indicators. Looking only at the overall status does not tell you which contributor is forcing the application DOWN.

In development, you can enable detailed health output in a controlled way to inspect each component. In production, expose details only to authenticated operators and avoid leaking hostnames, connection strings, database names, or sensitive data.

### 11.2. Checking Consumer-Side Filtering

In Eureka Client configuration, `eureka.client.filter-only-up-instances` controls filtering the instance list down to UP instances only. Documentation for current releases sets the default to true. If an application alters this property, consumers may receive instances in non-UP states; weigh the implications carefully before changing it.

Syncing status on the provider only matters if consumers actually honor that status during discovery and instance selection.

## 12. Customizing HealthCheckHandler

If you need logic more complex than Actuator's default aggregation, you can implement your own `com.netflix.appinfo.HealthCheckHandler`.

The handler receives the current status and returns the `InstanceInfo.InstanceStatus` that Eureka Client will publish. For example, an application can incorporate a business rule into the status decision or map custom statuses according to its own policy.

When customizing:

- Return only statuses valid in Eureka's vocabulary.
- Avoid long-running or unbounded network calls inside each health check.
- Avoid circular dependencies on the application's own Eureka health indicator or discovery client.
- Define clear status behavior during startup and shutdown phases.
- Test exception paths; an exception while computing health can cause the client to publish an unintended status.
- Emit logs and metrics whenever the handler returns an unexpected status.

If you only need to check a database or broker, an appropriate HealthIndicator is usually simpler than writing a custom handler. Only customize HealthCheckHandler when the default aggregation or mapping policy cannot satisfy your requirements.

## 13. Security and Performance

Health endpoints can reveal information about dependencies and internal topology. Expose only necessary endpoints, restrict access rights, and never set `show-details: always` for unauthenticated users.

Health checks also carry runtime cost:

- An indicator querying a database or broker can add load.
- A slow check can delay status computation.
- If too many indicators run concurrently, heartbeat/status updates can suffer.
- If the health policy is too sensitive, transient blips can pull instances out of traffic.
- If the health policy is too lenient, broken instances can stay advertised as UP.

Use timeouts on dependency checks, select only essential health indicators, and set appropriate thresholds. Health checks should reflect serving readiness without becoming heavier than business requests themselves.

## 14. Recommended Rollout Workflow

When applying Actuator-to-Eureka synchronization in a service:

1. Add compatible Eureka Client and Spring Boot Actuator dependencies.
2. Configure the service ID and Eureka Server address.
3. Enable `eureka.client.healthcheck.enabled` in application configuration.
4. Identify which health indicators truly govern serving capability.
5. Verify StatusAggregator and status mappings for your exact release train.
6. Configure Actuator endpoints and protect detailed health information.
7. Align the health metadata URL if consumers or operational tools consume that URL.
8. Test UP, DOWN, recovery, and graceful shutdown.
9. Verify status on Eureka Server and the instance list from the consumer side.
10. Monitor propagation latency, health check errors, and failed requests after rollout.

Do not stop at testing the Actuator endpoint alone. What you must confirm is that Eureka received the status and consumers route accordingly.

## 15. Key Takeaways

- Eureka heartbeats confirm the client is maintaining its lease; they do not by themselves prove the application is healthy for business traffic.
- `eureka.client.healthcheck.enabled` turns on Actuator status syncing via Eureka Client's health handler.
- Put the property in `application.yml`, not in `bootstrap.yml`.
- EurekaHealthCheckHandler aggregates HealthContributors/HealthIndicators in the application context and maps the result to InstanceStatus.
- Actuator `/actuator/health` is an HTTP endpoint; Eureka Server does not poll this endpoint by default to obtain status.
- `eureka.instance.healthCheckUrlPath` only configures the health URL in metadata and is separate from the property enabling the health handler.
- Status mappings can vary by version; custom statuses must be explicitly mapped.
- Verify status across Actuator, Eureka Server, and consumers; caches and heartbeats introduce propagation delay.
- Choose health indicators based on business serving capability, protect endpoints, and bound health-check overhead.

Syncing Actuator with Eureka helps the registry reflect each instance's actual ability to serve requests. When health policies, status mappings, and update timing are clearly designed, consumers can avoid sending requests to instances unfit to handle business work.

## References

- [Spring Cloud Netflix — Eureka's Health Checks](https://docs.spring.io/spring-cloud-netflix/reference/html/index.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [EurekaHealthCheckHandler source](https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaHealthCheckHandler.java)
