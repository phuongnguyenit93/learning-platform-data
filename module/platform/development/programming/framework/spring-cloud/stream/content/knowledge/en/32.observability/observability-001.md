# Enabling Actuator and Checking Binder Health

Spring Boot Actuator provides endpoints for monitoring the state of a running application. Spring Cloud Stream adds a health indicator for binders under the name **`binders`**, making it possible to observe the state of the binders used in the application. When Actuator is enabled and the health endpoint is configured appropriately, operations teams can check the overall application status, inspect binder details, and detect certain connection failures or middleware processing states.

In the `SPRING_CLOUD_STREAM` module, applications typically run `Supplier`, `Function`, or `Consumer` functions through bindings connected to Kafka, RabbitMQ, or Pulsar. The health indicator provides an additional operational signal for the binder layer. However, the health indicator depends on each binder; not every binder provides the same level of detail or determines status the same way. An `UP` endpoint also does not prove that every message is delivered and received properly, that there is no backlog, or that all business logic is succeeding.

## 1. Actuator and the binder health indicator

Actuator is the management component of Spring Boot. The `health` endpoint aggregates status from the `HealthIndicator` and `HealthContributor` beans registered in the ApplicationContext. Spring Cloud Stream registers a composite health indicator for binders under the name `binders`.

```text
HTTP request
    |
    v
/actuator/health
    |
    v
Spring Boot HealthEndpoint
    |
    +---- diskSpace / db / custom indicators
    |
    +---- binders
             |
             +---- Kafka binder (if a health indicator is available)
             +---- Rabbit binder (if a health indicator is available)
             +---- Pulsar binder (if a health indicator is available)
    |
    v
Overall application status: UP / DOWN / OUT_OF_SERVICE / UNKNOWN
```

The binder health indicator helps answer a question at the integration layer: are the binders used by the application in a healthy state according to the binder implementation? It complements Spring Boot's default health indicators, such as `diskSpace` or `db`.

The binder health indicator is registered under the name `binders`. The `management.health.binders.enabled` property controls enabling/disabling this group. If not configured explicitly, Spring Cloud Stream currently falls back to `management.health.defaults.enabled`, whose default value is typically `true`. It is good practice to declare it explicitly in the application configuration so operators do not have to rely on release train defaults.

## 2. Adding the Actuator dependency

Actuator must be added to the application via the `spring-boot-starter-actuator` dependency. If the application does not yet have a web server, add an appropriate web dependency to expose endpoints over HTTP. MVC applications typically use `spring-boot-starter-web`; reactive applications can use `spring-boot-starter-webflux`.

### Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Only add if the application does not already have a web starter -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Only add if the application does not already have a web starter
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

### Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Only add if the application does not already have a web starter
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

There is no need to specify separate versions when the Spring Boot parent or dependency management/BOM manages versions. Keep Spring Boot, the Spring Cloud release train, and the Spring Cloud Stream binders at compatible versions.

If the application already uses a web starter to serve business APIs, you only need to add Actuator. If you only want to expose endpoints over JMX, a web server may not be required; this lesson focuses on the HTTP health endpoint so it can be used with monitoring and container probes.

## 3. Enabling the binder health indicator

Spring Cloud Stream provides the property:

```text
management.health.binders.enabled
```

Set it to `true` to enable the health indicator for binders. This is a property of Spring Boot's health infrastructure and does not sit under `spring.cloud.stream`.

```yaml
management:
  health:
    binders:
      enabled: true
```

If you want to disable the binder health indicator group across the entire application:

```yaml
management:
  health:
    binders:
      enabled: false
```

When the default indicator is disabled, custom `HealthIndicator` beans provided by the application can still be discovered by Spring Boot and included in the health endpoint. Only disable binder health when there is a clear operational reason or an alternative check mechanism in place.

Some binder implementations do not provide a health indicator. In that case, enabling `management.health.binders.enabled` does not automatically create uniform connection checks for every middleware. Check the documentation for the binder in use and verify actual status with appropriate integration/monitoring checks.

## 4. Exposing the `/actuator/health` endpoint

Spring Boot exposes the `health` endpoint over HTTP by default. Other endpoints such as `info`, `metrics`, `env`, or `beans` should not be exposed indiscriminately because they can reveal internal details.

Minimal configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

If you also want to expose `info`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

The default endpoint is:

```text
GET http://localhost:8080/actuator/health
```

If the application changes the base path via `management.endpoints.web.base-path`, the actual URL path changes as well. If a separate management port is used, the endpoint will be served on that port instead of the business HTTP port.

## 5. Showing binder details

When calling `/actuator/health`, by default clients usually only receive the overall status such as `UP` or `DOWN`. To inspect components and binder details, configure `show-details` and `show-components`.

In a development environment, you can use:

```yaml
management:
  endpoint:
    health:
      show-details: always
      show-components: always
```

In production, restrict details to authorized users:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

Commonly used values are `never`, `when-authorized`, and `always`. By default, Spring Boot does not show details. `always` makes detailed information visible to anyone who can reach the endpoint; only use it in protected internal environments or during local development.

Spring Cloud Stream describes setting `management.endpoint.health.show-details` to `ALWAYS` to view binder information. In newer Spring Boot versions, `show-components` also controls rendering the component structure; configuring both makes the output easier to inspect. Check the property metadata for your project's Spring Boot version if using an older release.

## 6. Complete combined configuration

Example of a Spring Cloud Stream application that has a binder and wants to expose the health endpoint:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
  health:
    binders:
      enabled: true
```

In this configuration:

- `server.port` is the application's web server port.
- `exposure.include` exposes only `health` and `info` over HTTP.
- `show-details` determines whether authorized callers can view detailed information.
- `show-components` determines whether the component structure is displayed.
- `management.health.binders.enabled` enables the binder health indicator group.

This is a general configuration. If the application has multiple binders or uses Kafka Streams, the detailed output also depends on the binder implementation and each binder's own configuration.

## 7. Checking the health endpoint over HTTP

After starting the application, call the health endpoint:

```bash
curl -i http://localhost:8080/actuator/health
```

When authorized to view details, the response may have a structure similar to:

```json
{
  "status": "UP",
  "components": {
    "binders": {
      "status": "UP",
      "components": {
        "kafka": {
          "status": "UP"
        }
      }
    },
    "diskSpace": {
      "status": "UP"
    }
  }
}
```

Sub-binder names and `details` fields depend on the binder, version, and configuration. The example above only illustrates the combined structure; not every binder returns these exact fields.

If you want to check the binder component directly, you can call:

```bash
curl -i http://localhost:8080/actuator/health/binders
```

With a nested contributor, the Spring Boot health endpoint also supports querying a sub-component by path, provided that contributor is exposed and the component name matches.

## 8. Understanding health status meanings

Common statuses:

| Status | General meaning | How to handle |
|---|---|---|
| `UP` | The indicator reports the component as healthy by its criteria | Continue monitoring metrics and message flow |
| `DOWN` | The indicator detected an unhealthy component | Check the broker, connections, bindings, threads, or configuration errors |
| `OUT_OF_SERVICE` | The component is marked out of service | Check maintenance, readiness, or operational state |
| `UNKNOWN` | The status could not be determined by the indicator/aggregator | Check the implementation, configuration, and logs |

The health endpoint aggregates statuses from multiple indicators. If a binder reports `DOWN`, overall health may become `DOWN` according to the status aggregator. The default HTTP status is typically `503` for `DOWN` and `OUT_OF_SERVICE`, while `UP` returns `200`.

Do not look solely at HTTP `200` and conclude that the entire event pipeline is functioning correctly. A health indicator only checks what its implementation is designed to check; it does not prove that consumers have cleared their backlog, that no messages are lost, or that there are no business errors.

## 9. Binder health indicators are binder-specific

Spring Cloud Stream registers the `binders` group, but each binder may implement its health indicator differently. Some binders provide checks for connection status or registered resources; some binders do not provide a dedicated health indicator.

| Binder | How to interpret the result |
|---|---|
| Kafka Binder | Depends on the implementation and registered destinations; do not infer that all consumer groups/partitions are fine solely from `UP` |
| Kafka Streams Binder | Has a dedicated health indicator tracking the state of stream threads and tasks |
| RabbitMQ Binder | Checks according to the binder version's health indicator capabilities; can be complemented with a separate Rabbit connection health indicator |
| Pulsar Binder | Checks according to the binder version's health indicator capabilities; also monitor brokers, topics, subscriptions, and backlog |

Do not assume that binders share the same set of `details` fields, timeouts, or `UP/DOWN` semantics. When running multiple middleware technologies, check the documentation for the exact binder version and add integration monitoring for important signals not covered by the health indicator.

## 10. Distinguishing binder health from broker health indicators

Spring Boot can auto-configure health indicators for certain technologies when the corresponding dependencies are on the classpath. For example, RabbitMQ may have an indicator named `rabbit` via the Spring AMQP connection factory. Spring Cloud Stream has its own `binders` group.

These two indicators are not synonymous:

| Indicator | Check scope |
|---|---|
| `binders` | Status reported by the binder implementation for binders in Spring Cloud Stream |
| `rabbit` | RabbitMQ connection status according to the Spring Boot/Spring AMQP health indicator when applicable |
| `db` | Ability to obtain a database connection according to the DataSource health indicator |
| `diskSpace` | Disk space against configured thresholds |

For example, `rabbit: UP` does not prove that the `orders-in-0` binding has the right queue, the right routing key, a consumer receiving messages, or a configured DLQ. Conversely, `binders: UP` does not replace checking backlog and queue state via the RabbitMQ Management API.

## 11. Inspecting the Kafka Streams Binder

The Kafka Streams Binder has a specialized health indicator for checking the state of stream threads. When details are shown, the output can include:

- Stream thread name.
- Thread state.
- Active tasks and assigned partitions.
- Standby tasks and corresponding partitions.
- Information grouped by application ID when there are multiple Kafka Streams processors.

Common thread states include:

| Thread state | Meaning |
|---|---|
| `CREATED` | The thread has been created but is not yet running normally |
| `RUNNING` | The thread is actively processing |
| `PARTITIONS_REVOKED` | The thread is revoking partitions during a rebalance |
| `PARTITIONS_ASSIGNED` | The thread is receiving newly assigned partitions |
| `PENDING_SHUTDOWN` | The thread is waiting to shut down |
| `DEAD` | The thread has stopped or is no longer active |

According to the Kafka Streams Binder documentation, the health indicator reports `UP` when all registered Kafka Streams threads are in the `RUNNING` state. During a rebalance, threads may temporarily enter other states; inspect the details and logs before concluding there is a persistent failure.

Example configuration:

```yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

If there are multiple Kafka Streams processors, details can be grouped by `applicationId`. This helps identify which topology has a failing thread.

## 12. Notes when multiple binders are on the classpath

An application may declare multiple binder dependencies on the classpath while only using some of them. Some implementations still register a health indicator even if that binder is unused. If the health indicator requires the binder to have registered destinations and the binder has no bindings, it may report `DOWN` and cause overall health to become `DOWN`.

For example, an application has both Kafka Binder and Kafka Streams Binder on the classpath but only declares Kafka Streams bindings. Kafka Binder may report `DOWN` because no destinations are registered for that binder. This is a case where the classpath configuration does not reflect the binder actually in use.

Resolution order:

1. Verify which binders are actually used in the application.
2. Remove unused binder dependencies if there is no reason to keep them.
3. If you need to keep a binder on the classpath for another purpose, look into disabling the health indicator in that binder's own environment.
4. Re-check `/actuator/health` after making the change.

Do not disable `management.health.binders.enabled` globally just to hide an unused binder if other binders still need to be monitored.

## 13. Disabling the health indicator for one binder in a multi-binder setup

When configuring multiple binders via `spring.cloud.stream.binders`, each binder can have its own environment. Spring Cloud Stream allows setting `management.health.binders.enabled=false` inside a specific binder's environment to exclude that binder's health indicator.

Illustrative example:

```yaml
spring:
  cloud:
    stream:
      binders:
        unusedKafka:
          type: kafka
          environment:
            management:
              health:
                binders:
                  enabled: false
```

Only use this approach when the `unusedKafka` binder does not need to be monitored via the binder health indicator. If a binder is serving production bindings, disabling its health indicator reduces observability. Confirm that the binder name and environment are applied properly in your actual multi-binder configuration.

If a binder is not used by any binding at all, removing the dependency is usually simpler. If a binder is used but its implementation does not provide a health indicator, add appropriate monitoring rather than assuming this property creates a new health check.

## 14. Liveness and readiness in deployment environments

Spring Boot can expose two health probe groups:

- **Liveness:** whether the application is alive and does not need to be restarted to recover.
- **Readiness:** whether the instance is ready to accept new traffic or work.

In Kubernetes, the commonly used endpoints are:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Spring Boot automatically enables probe groups when it detects a Kubernetes environment under suitable configurations. You can enable them explicitly in other environments with:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Liveness should not depend on an external broker's health check. If Kafka/RabbitMQ/Pulsar temporarily loses connectivity and liveness turns `DOWN`, Kubernetes may restart all instances simultaneously, creating a restart loop and making the situation worse.

Readiness can include binder health if the application cannot process work when the broker is unavailable. However, this is an operational decision: if a shared broker fails, all instances can become unready at the same time. If the application has retries, buffering, or fallbacks, including binders in readiness may not be appropriate.

## 15. Including binder health in the readiness group

Spring Boot does not automatically add external health indicators to the readiness group. If you want readiness to also reflect binder health, you can configure:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,binders
```

Then check:

```bash
curl -i http://localhost:8080/actuator/health/readiness
```

Only add `binders` when the broker is a mandatory dependency for the instance to accept work. For stream processors, evaluate the exact semantics: an instance may require the broker to consume/publish, yet a shared broker outage could make all replicas unready. Depending on the architecture, that may be desirable or it may reduce system resilience.

Do not add `binders` to the liveness group. Liveness should reflect internal process failures that a restart can fix, not transient failures in external systems.

## 16. Managing the management port

Actuator can share the same port as the application or use a separate port:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,info
```

When configuring a separate management port, the health endpoint is available at `http://localhost:8081/actuator/health`. Monitoring agents and Kubernetes probes must target the correct port.

A separate management port helps isolate management traffic, though a health endpoint on a separate port can still succeed even when the main web server cannot accept connections. If using probes on the management port, consider exposing health groups on the main server port as supported by your Spring Boot version, or design probes to check the right application serving port.

## 17. Securing Actuator endpoints

The health endpoint can reveal broker names, binders, application IDs, threads, tasks, or error details. Do not expose all Actuator endpoints to the public Internet.

Guidelines:

- Expose only `health` and the endpoints that are genuinely needed.
- Use `show-details: when-authorized` in production.
- Restrict access through internal networks, firewalls, a service mesh, or Spring Security.
- If you have a custom `SecurityFilterChain`, configure protection rules for Actuator yourself; Spring Boot's security auto-configuration may back off when the application defines its own chain.
- Never include credentials, tokens, connection strings, or business payloads in health details.
- If using `show-details: always`, enable it only in protected environments.

Minimal exposure example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

The `health` endpoint is usually exposed over HTTP by default, but you should still verify the security policy and network path of the deployment environment.

## 18. Testing with curl and interpreting results

Basic verification workflow:

1. Start the application with Actuator and binder health enabled.
2. Confirm the management endpoint port and base path.
3. Call `/actuator/health`.
4. If authorized, inspect the `binders` component.
5. Call `/actuator/health/binders` to inspect the binder group.
6. Cross-check binder names and statuses against startup logs.
7. If `DOWN`, inspect sub-indicators and root errors in the logs.
8. Restore the broker or configuration and check again.

Example:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/binders
```

On Windows PowerShell, you can use `curl.exe` to invoke the real curl binary:

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/binders
```

If it returns `404`, check the Actuator dependency, web application setup, exposure includes, base path, and management port. If it returns `401` or `403`, check authentication/authorization. If it returns `503`, inspect the health JSON and logs to find which contributor reported `DOWN`.

## 19. Health indicators do not replace metrics and message-flow monitoring

The health endpoint is typically a point-in-time snapshot taken when called. To operate Spring Cloud Stream reliably, you also need to observe metrics and message flow state.

| Signal | Question to answer |
|---|---|
| Binder health | Does the binder report a healthy state? |
| Consumer lag/backlog | How many messages are waiting to be processed? |
| Processing rate | How many messages per second is the consumer processing? |
| Error rate | How many messages or processing attempts failed? |
| Retry/DLQ | How many messages had to be retried or routed to dead-letter? |
| Partition assignment | Has the consumer received all required partitions? |
| Connection/reconnect | Is the binder repeatedly disconnecting and reconnecting? |
| End-to-end latency | How long does it take from publishing to completed processing? |

Actuator `metrics` can expose Micrometer metrics recorded by the application and binder. If using Prometheus, add the appropriate registry and expose the `prometheus` endpoint after securing it. Do not assume all binders provide the same metric names or tags.

## 20. Testing binder health during broker failures

A health indicator is only useful once you know how it behaves under normal and failure conditions. Test it in an integration/staging environment:

| Scenario | Action | What to verify |
|---|---|---|
| Healthy broker | Start the broker and application | Binder health reflects healthy status per implementation |
| Broker unreachable at startup | Stop the broker before starting the application | Verify startup behavior, retries, and health result |
| Connection lost at runtime | Block the network or stop the broker | Observe health, reconnect logs, and recovery time |
| Broker recovery | Restart the broker | Verify the binder recovers and health returns to healthy |
| Binder without indicator | Use a binder implementation without a health check | Do not conclude `UP` means the broker was checked |
| Extra binder on classpath | Add an unused binder dependency | Check whether a contributor reports `DOWN` due to no destinations |
| Multi-binder | Run two binders with separate configs | Verify each binder is shown and its environment is applied properly |
| Details hidden | Use `show-details: never` | Endpoint returns only overall status |
| Insufficient privileges | Call endpoint with a user lacking the role | Details are hidden or request is rejected per security policy |
| Readiness when broker down | Include `binders` in readiness then stop the broker | Evaluate whether instances should be removed from traffic |

Do not test only a stopped broker. Also test network timeouts, expired credentials, DNS failures, TLS certificate issues, missing ACLs, and a binder failing to register destinations to understand the limits of the health indicator.

## 21. Common issues

| Symptom | Possible cause | How to resolve |
|---|---|---|
| `/actuator/health` returns `404` | Missing Actuator/web dependency, wrong port/base path, or endpoint not exposed | Check dependencies and management configuration |
| Only `{"status":"UP"}` is shown | Component details are hidden | Configure `show-details` and `show-components` appropriately |
| `binders` is missing | Binder health disabled or binder has no indicator | Check `management.health.binders.enabled` and implementation |
| `binders` reports `DOWN` even though binder is running | Extra binder on classpath or indicator found no destinations | Identify binders actually in use, remove extra dependencies, or configure per-binder environment |
| Kafka Streams health is `DOWN` | A stream thread is not in `RUNNING` | Inspect thread states, tasks, rebalances, and logs |
| `rabbit` UP but binding fails | Rabbit connection indicator does not verify all bindings | Check `binders`, queues, exchanges, routing, and consumers |
| Health stays UP while backlog grows | Indicator does not measure throughput/backlog | Monitor consumer lag and processing metrics |
| Health endpoint leaks details | `show-details: always` or security not restricted | Use `when-authorized`, firewalls, and roles |
| Kubernetes restarts continuously during broker outage | Liveness depends on binder health | Do not include external binder health in liveness |
| All pods unready when shared broker fails | Readiness group includes `binders` | Re-evaluate dependencies and readiness policy |
| Health check times out | Indicator or broker request responds slowly | Check timeouts, network, and slow-indicator logs |

## 22. Production rollout checklist

1. Add `spring-boot-starter-actuator` and a web dependency if HTTP exposure is needed.
2. Enable `management.health.binders.enabled: true`.
3. Expose minimal endpoints, typically `health` and optionally `info`.
4. Configure `show-details`/`show-components` based on access permissions.
5. Confirm whether the binder implementation in use provides a health indicator.
6. Review the classpath to remove unused binder dependencies.
7. For multi-binder setups, check each binder's environment and health contributor.
8. Call `/actuator/health` and `/actuator/health/binders` in staging.
9. Test broker outages, network interruptions, credential/ACL failures, and recovery.
10. Decide whether to include binder health in readiness; do not include external dependencies in liveness.
11. Protect the management port and endpoints with network policies/Spring Security.
12. Combine health checks with metrics, consumer lag, retry/DLQ, and end-to-end monitoring.

## 23. Self-check

- [ ] Can add `spring-boot-starter-actuator` and an appropriate web dependency.
- [ ] Can explain the role of the Actuator `health` endpoint.
- [ ] Can enable `management.health.binders.enabled`.
- [ ] Can expose and call `/actuator/health`.
- [ ] Can configure `show-details` and `show-components` appropriately for the environment.
- [ ] Can explain why binder health indicators are implementation-dependent.
- [ ] Can distinguish `binders` from dedicated RabbitMQ or database indicators.
- [ ] Can recognize when an unused binder dependency causes health to report `DOWN`.
- [ ] Can read Kafka Streams thread/task health details.
- [ ] Can distinguish liveness from readiness and decide when to include binders in readiness.
- [ ] Can secure Actuator endpoints and the management port.
- [ ] Can combine the health endpoint with metrics, lag, retry, and DLQ monitoring.
- [ ] Can design tests for broker disconnects and broker recovery.

## Conclusion

To check Spring Cloud Stream binder health, add Actuator, enable the binder health indicator with `management.health.binders.enabled`, and access `/actuator/health`. The indicator group is registered under the name `binders`; to view detailed information, configure `show-details` and `show-components` alongside appropriate security. Results depend on the binder implementation, so Kafka, RabbitMQ, and Pulsar do not all provide the same check. In particular, watch for unused binders on the classpath, Kafka Streams thread states, readiness/liveness configuration, and the difference between binder health and broker connection health. Combining Actuator with metrics, backlog, retry/DLQ monitoring, and outage testing builds a complete operational picture.

## References

- Spring Cloud Stream 5.0.4 — Health Indicator: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html
- Spring Cloud Stream 4.1.6 — Kafka Streams Binder Health Indicator: https://docs.spring.io/spring-cloud-stream/reference/4.1/kafka/kafka-streams-binder/health-indicator.html
- Spring Boot — Actuator Endpoints and Health Information: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Kubernetes Probes: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes
