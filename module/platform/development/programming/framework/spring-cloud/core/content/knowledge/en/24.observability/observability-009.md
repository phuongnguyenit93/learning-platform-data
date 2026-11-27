# Monitoring Startup Failures, Refresh Failures, and Config Fetch Time

In a Spring Cloud application, three phases commonly cause operational disruptions: application startup, fetching configuration from an external source, and refreshing configuration while the application is running. They are related, yet they occur at different times. Looking at a single log line or health status makes it easy to confuse a Config Server connection failure with a bean creation failure, or to confuse a successful refresh with every bean already using the new configuration.

Effective observability combines lifecycle logs, startup steps, metrics, health indicators, and HTTP traces. Each signal answers a distinct question: at which stage did the application stop, how long did remote configuration take to respond, which properties changed, which beans failed to re-initialize, and which instances have not received the refresh.

This lesson belongs to the **Observability** chapter of the **SPRING_CLOUD_CORE** module. It guides you through collecting evidence for startup failures, refresh failures, and Config Client latency; using Spring Boot Actuator, Micrometer, and Spring Cloud Context; and establishing an investigation workflow suitable for containerized or multi-replica environments.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Distinguish when an application starts, finishes starting, and becomes ready to accept requests.
- Use **ApplicationStartup** and Actuator **startup** to inspect startup steps.
- Capture logs even when the ApplicationContext fails to be created.
- Identify the Config Client configuration-fetching phase and explain why multiple requests occur.
- Measure Config Server request handling duration using HTTP server metrics.
- Distinguish **application.started.time**, **application.ready.time**, **http.server.requests**, and **http.client.requests**.
- Monitor **EnvironmentChangeEvent**, **RefreshScope**, and target bean re-initialization failures.
- Use Config Client Health Indicator and RefreshScope Health Indicator for their intended purposes.
- Create custom metrics to measure application-driven refresh operations.
- Secure Actuator endpoints and avoid exposing sensitive configuration values.

## 2. Three Phases to Observe Separately

| Phase | What You Need to Know | Appropriate Signals |
| --- | --- | --- |
| Startup | Which step did the application stop at? How long until ready? | ApplicationFailedEvent, startup steps, application.started.time, application.ready.time |
| Fetching config | Which requests did the client send, how long did the server take, were there retries or discovery lookups? | Config Client logs, Config Server http.server.requests, access logs/proxy logs, Config Client Health Indicator |
| Refresh | Which properties changed? Which beans were rebound or recreated? Did refresh fail on any replica? | EnvironmentChangeEvent, /actuator/refresh, configprops, RefreshScope Health Indicator, refresh logs and metrics |

No single endpoint answers all three questions. For example, **GET /actuator/health** can report Config Server status, yet it does not tell you how long the last startup took to fetch configuration. Similarly, the startup endpoint only records the startup sequence; it is not a history of subsequent refreshes.

To use management endpoints, the application needs **spring-boot-starter-actuator**. If loading remote properties via Spring Cloud Config, it needs the corresponding Config Client, typically **spring-cloud-starter-config**. To export metrics to Prometheus, add the Micrometer Prometheus registry; only expose the **prometheus** endpoint once the registry is configured.

## 3. Understanding the Spring Boot Startup Lifecycle

A Spring Boot application moves through these key event milestones:

```text
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
ApplicationContextInitializedEvent
        |
ApplicationPreparedEvent
        |
ApplicationStartedEvent
        |
ApplicationReadyEvent

If startup fails:
ApplicationFailedEvent
```

Practical meaning:

- **ApplicationStartingEvent**: SpringApplication has just started; ApplicationContext is not ready yet.
- **ApplicationEnvironmentPreparedEvent**: Environment is prepared; configuration sources and profiles are being set up.
- **ApplicationContextInitializedEvent**: context is initialized but not yet refreshed.
- **ApplicationPreparedEvent**: bean definitions are loaded; context is about to refresh.
- **ApplicationStartedEvent**: context has refreshed; ApplicationRunners and CommandLineRunners are about to run.
- **ApplicationReadyEvent**: application is ready to accept requests.
- **ApplicationFailedEvent**: startup encountered an error.

Spring Boot's Config Data import happens during the Environment preparation phase, before most application beans are created. Therefore, a slow Config Server can prolong startup before Actuator HTTP endpoints even exist.

## 4. Recording Startup Steps with BufferingApplicationStartup

Spring Boot provides **BufferingApplicationStartup** to store **StartupStep** records in memory. Actuator **startup** can return a timeline of these steps, including start time, end time, duration, and tags.

Configure in the main class:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(OrdersApplication.class);

        application.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
```

The number **2048** is an example buffer capacity. Increase capacity if the application has many startup steps; avoid setting it unnecessarily huge since the data stays in memory.

Expose the endpoint in diagnostic environments:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,startup
  endpoint:
    health:
      show-details: when-authorized
```

Once the application has started, fetch a snapshot:

```bash
curl -sS http://localhost:8080/actuator/startup
```

**GET /actuator/startup** returns a snapshot of the buffer. **POST /actuator/startup** returns the data and drains the buffer, clearing recorded steps. Use GET when you want to read without losing data; only use POST when intentionally draining.

### 4.1. Reading the Timeline to Find Bottlenecks

Each event can contain:

- **startupStep.name**: startup step name.
- **startupStep.id** and **parentId**: parent-child step relationships.
- **startupStep.tags**: extra metadata such as bean name.
- **startTime**, **endTime**, **duration**: execution timing.

Look for steps with unusually large durations, then inspect child steps and tags. For example:

- A slow-initializing bean might be calling a database or external API inside its constructor.
- A bean-creation step with many child steps may indicate a deep dependency chain.
- Prolonged Environment preparation may relate to Config Data, profile activation, DNS, or Config Server access.

The startup timeline does not guarantee every Config Client HTTP request appears as its own step. Use it to pinpoint the slow phase, then cross-reference Config Client logs and Config Server logs/metrics to measure specific network requests.

## 5. Tracking Started and Ready Times

Spring Boot automatically registers two application startup metrics:

| Metric | Meaning |
| --- | --- |
| **application.started.time** | Time from startup start until the application is started |
| **application.ready.time** | Time from startup start until the application is ready to accept requests |

Read the metrics via Actuator:

```bash
curl -sS http://localhost:8080/actuator/metrics/application.started.time
curl -sS http://localhost:8080/actuator/metrics/application.ready.time
```

These two metrics only exist after startup reaches their respective milestones. They do not replace logs from a failed startup process.

Comparing across deployments:

- **application.started.time** spikes: check Config Data, bean initialization, classpath scanning, and eagerly initialized dependencies.
- **application.ready.time** increases while started time barely changes: check ApplicationRunners, CommandLineRunners, post-context-refresh tasks, or readiness steps.
- Both increase: check CPU/memory resources, DNS, TLS, Config Server, and external dependencies.

Do not compare numbers across releases while ignoring JDK upgrades, bean count changes, retry settings, or remote configuration call counts.

## 6. Catching Failures Before ApplicationContext Is Created

If an application fails before the web server starts listening, **/actuator/health** and **/actuator/startup** may be unreachable. In that case, observe via process/container logs and listeners registered before calling **SpringApplication.run()**.

Example capturing **ApplicationFailedEvent** early:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class OrdersApplicationLauncher {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersApplicationLauncher.class);

    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(OrdersApplicationLauncher.class);

        application.addListeners(
            (ApplicationListener<ApplicationFailedEvent>) event ->
                log.error(
                    "Application startup failed",
                    event.getException()
                )
        );

        application.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
```

The listener is registered before **run()**, so it can catch errors at stages where **@Component** or **@EventListener** beans inside ApplicationContext do not yet exist.

When reading errors, work from the outermost exception down to the root cause. Classify the cause before fixing:

- **ConfigDataLocationNotFoundException** or import error: check **spring.config.import**.
- **ConfigClientFailFastException** or connection error: check Config Server, DNS, TLS, authentication, and timeouts.
- **BindException**/validation failure: check property names, data types, and required values.
- **BeanCreationException**: check the bean being created in the context and its dependency chain.
- Port binding failure: check whether the application port is already in use by another process.

Spring Boot often provides a Failure Analyzer to print a description and action for common errors. Keep both the analysis and the full stack trace in diagnostic logs.

## 7. Enabling Logs on the Right Packages When Investigating Startup

There is no need to turn on TRACE for the entire application. Temporarily raise log levels on relevant packages:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
    org.springframework.cloud.config.client: DEBUG
    org.springframework.cloud.context.refresh: DEBUG
    org.springframework.cloud.context.scope.refresh: DEBUG
```

What each log group helps observe:

- **org.springframework.boot.context.config**: reading Config Data, profiles, and imports.
- **org.springframework.cloud.config.client**: configuration fetch requests to Config Server and processing results.
- **org.springframework.cloud.context.refresh**: Environment refresh process.
- **org.springframework.cloud.context.scope.refresh**: refresh scope and target bean activity.

If using logging settings to catch very early events, place log levels in a configuration source effective before the phase you want to observe, such as environment variables or JVM arguments. A logging setting fetched from Config Server cannot help log the initial request used to fetch that setting itself.

Only enable detailed logs during the investigation window. Never log secret values, passwords, tokens, private keys, or the entire Environment.

## 8. Monitoring Config Client Configuration Fetching

With Config Data import, for example:

```yaml
spring:
  application:
    name: orders
  config:
    import: "configserver:https://config.internal"
```

Spring Boot loads configuration in two stages:

1. Load configuration with the **default** profile to discover properties that may activate additional profiles.
2. Once active profiles are known, load configuration matching those profiles.

Therefore, a single startup can issue multiple requests to Config Server. This is normal behavior and does not automatically mean the client is retrying or looping.

If using discovery-first lookup to locate Config Server via **DiscoveryClient**, startup also incurs a network round trip to find Config Server's registration. When analyzing timing, separate server lookup time from property source fetch time.

### 8.1. Checking application, profile, and label

Config Server serves configuration along the path:

```text
/{application}/{profile}/{label}
```

By default, the client uses:

- **application**: value of **spring.application.name**.
- **profile**: active profiles.
- **label**: branch, tag, or configuration revision per backend.

When requests hit the wrong path, check application name, profiles, label, and **spring.cloud.config.name**, **spring.cloud.config.profile**, **spring.cloud.config.label** if overridden.

Record non-sensitive metadata in operational logs:

- application name.
- active profiles.
- config label or revision.
- Config Server host/service ID.
- request start time and completion time.
- attempt count and final outcome.

Do not log property source contents merely to confirm the client received a response.

## 9. Measuring Processing Time at Config Server

Spring Boot Actuator automatically creates the **http.server.requests** metric for requests handled by Spring MVC or WebFlux. On Config Server, this metric measures how long the HTTP server takes to process configuration fetch requests.

List available metrics:

```bash
curl -sS http://config-server:8888/actuator/metrics
```

Read the request metric:

```bash
curl -sS http://config-server:8888/actuator/metrics/http.server.requests
```

Common tags used for analysis include:

- **method**: HTTP method.
- **uri**: URI template if recognized by the framework.
- **status**: HTTP status.
- **outcome**: outcome group.
- **exception**: exception type if recorded.

When Config Server responds slowly, break down latency by URI, status, and request timestamp. If the server processes quickly yet the client is still slow, check DNS, TLS handshake, network routing, proxies, service discovery, and client-side retries.

### 9.1. Distinguishing HTTP Client Metrics from Config Data Import Time

Spring Boot provides the **http.client.requests** metric for **RestTemplate**, **WebClient**, and **RestClient** built from Boot-instrumented builders/customizers.

However, do not assume Config Client's internal bootstrap requests will appear as an **http.client.requests** metric in your application. Config Data is loaded before the main ApplicationContext completes, and the internal client does not necessarily use the HTTP builder the application creates later.

To measure configuration fetching reliably, combine:

1. Config Client DEBUG/TRACE logs to identify requests, profiles, and retries.
2. **http.server.requests** on Config Server to measure server processing time.
3. Reverse proxy/load balancer access logs if present.
4. Startup metrics to measure the overall impact on startup time.

Do not add server processing time and client-recorded time together if both measure the same interval. Clearly define the start/end points of each measurement.

## 10. Tracking Retries and Fail-Fast When Config Server Is Unavailable

If Config Server is a mandatory configuration source, omit the **optional:** prefix in Config Data import so the application fails when configuration cannot be loaded:

```yaml
spring:
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 6
        initial-interval: 1000
        multiplier: 1.1
```

Config Client retry requires **spring-retry** and **spring-boot-starter-aop** on the classpath. **spring.cloud.config.retry.*** properties adjust attempt counts and backoff. For imports declared in profile-specific files, retry settings may need to be passed as URL parameters on the import according to your version's documentation.

### 10.1. Setting Connection and Response Read Thresholds

Config Client has two separate timeouts: time spent waiting to connect to Config Server and time spent waiting to read the response. The example below uses milliseconds:

```yaml
spring:
  cloud:
    config:
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Connection timeout detects DNS/route/refused connections early; read timeout bounds how long to wait for server data after connecting. Choose values based on normal latency and the system's startup budget. Retry backoff adds onto per-request wait time, so total startup delay can exceed a single timeout.

When observing retries, distinguish:

- One request for **default** and one request for active profiles: likely the two normal Config Data stages.
- Repeated requests to the same path after connection errors: likely retries.
- A discovery lookup before the configuration request: likely discovery-first lookup.
- Multiple Config Server URLs: the client may try addresses sequentially to find an available server.

Record attempt counts, backoff intervals, and root exceptions. Never raise **max-attempts** to mask a Config Server that frequently fails or has latency exceeding your startup budget.

## 11. Using Config Client Health Indicator Appropriately

Spring Cloud Config Client provides a Health Indicator that attempts to fetch configuration from Config Server. This indicator is useful for checking whether Config Server is reachable.

By default, the health result is cached for 5 minutes. You can adjust the TTL with:

```yaml
health:
  config:
    time-to-live: 30000
```

The value above is 30 seconds in milliseconds. You can disable the indicator if not needed:

```properties
management.health.config.enabled=false
```

An **UP** status may come from a cached result and does not prove a configuration request just succeeded right now. The Health Indicator also does not prove remote properties were applied into the Environment of all replicas.

When you need to confirm configuration was loaded, also verify profiles, label/revision, property sources, and bound beans. Do not rely solely on a green light on the health dashboard.

## 12. Observing Environment Refresh and EnvironmentChangeEvent

When the Environment changes, Spring Cloud publishes **EnvironmentChangeEvent**. Standard components can:

- Rebind **@ConfigurationProperties** beans.
- Update logger levels from **logging.level.*** properties.
- When refresh runs via ContextRefresher, targets in RefreshScope can be invalidated to be recreated on the next call.

A listener can log the list of changed keys:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshAuditListener {

    private static final Logger log =
        LoggerFactory.getLogger(RefreshAuditListener.class);

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        log.info("Environment changed; keys={}", event.getKeys());
    }
}
```

Only log key names, not values. Some keys may reveal internal system names; restrict log access according to operational policy.

Config Client does not poll Config Server for changes by default. In multi-replica systems, you can use Spring Cloud Bus to broadcast refresh events to instances instead of having each instance poll on its own.

## 13. Tracking Refresh Operations via Actuator

Spring Cloud Context provides the Refresh endpoint. When exposed, you can call:

```bash
curl -i -X POST http://localhost:8080/actuator/refresh
```

The endpoint refreshes the Environment and returns the keys changed by the refresh mechanism. To expose the endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,refresh
```

In real environments, protect the endpoint with Spring Security, network policies, or a dedicated management interface. Never expose the refresh operation to public clients.

When refresh fails, cross-reference:

1. HTTP status and response from the endpoint.
2. Config Client logs to see if the remote source was fetched.
3. List of changed keys.
4. Whether a higher-precedence property source is overriding the new value.
5. Which beans were rebound or refreshed.
6. The refresh scope health indicator after the operation.

### 13.1. Refreshing Targets Is Not the Same as Reloading Configuration

**RefreshScope** manages target beans using a proxy/cache mechanism. When a target is invalidated, the next invocation creates a new target. However, invalidating a target does not by itself prove Config Server was just called or the Environment received new values.

Separate two questions:

- Was the remote property source fetched/updated?
- Did the bean using that property successfully rebind or recreate?

If you only check the second question, you may find the bean still has the old value because the Environment never changed. If you only check the first question, a bean outside refresh scope may continue holding stale state.

## 14. Tracking Bean Re-Initialization Failures After Refresh

Spring Cloud provides **RefreshScopeHealthIndicator**. If a bean fails to re-initialize or rebind after a context refresh, the indicator can transition to **DOWN** and include the corresponding exception in health details.

Check:

```bash
curl -sS http://localhost:8080/actuator/health
```

When authorized to view details, locate the refresh scope component and the corresponding exception. Distinguish errors during configuration loading from errors during target bean recreation.

Common causes include:

- The bean requires a new property that does not exist.
- The constructor or factory method throws an exception upon receiving the new value.
- An old database/client connection was not closed cleanly during lifecycle cleanup.
- The bean has a non-refreshed dependency yet the caller assumes the dependency changed.
- The bean is not actually inside **@RefreshScope**.
- The new configuration is type-valid yet business-invalid.

Note: constructor-bound **@ConfigurationProperties**, including Java records, cannot be refreshed via standard rebinding. If runtime configuration updates are needed, pick a bean and binding model compatible with refresh requirements.

## 15. Measuring Application-Controlled Refresh Duration

If the application has a dedicated service responsible for calling **ContextRefresher**, you can measure duration using a Micrometer **Timer**. Example:

```java
import java.util.Set;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Component;

@Component
public class TimedConfigRefresh {

    private final ContextRefresher contextRefresher;
    private final MeterRegistry meterRegistry;

    public TimedConfigRefresh(
            ContextRefresher contextRefresher,
            MeterRegistry meterRegistry) {
        this.contextRefresher = contextRefresher;
        this.meterRegistry = meterRegistry;
    }

    public Set<String> refresh() {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            return contextRefresher.refresh();
        }
        catch (RuntimeException exception) {
            outcome = "failure";
            throw exception;
        }
        finally {
            sample.stop(
                Timer.builder("app.config.refresh")
                    .tag("outcome", outcome)
                    .register(meterRegistry)
            );
        }
    }
}
```

The **app.config.refresh** metric shows the duration and outcome of refreshes passing through this service. It can be queried via **/actuator/metrics/app.config.refresh**.

If the Actuator Refresh endpoint is called directly, the wrapper above does not automatically measure that request. To measure the endpoint as well, instrument the refresh handling path or use observation support appropriate for your Spring Cloud version. Do not create a second refresh endpoint without unified authorization and audit policies.

Never add **changedKeys**, exception messages, user IDs, or property values as metric tags. Continuously varying data causes high cardinality and overloads metrics backends.

## 16. Designing Logs to Correlate Events

A useful log line needs enough fields to link events across phases without leaking configuration.

Fields to consider:

| Field | Purpose |
| --- | --- |
| service | Service name |
| environment | Deployment environment |
| instance | Pod/instance ID |
| profile | Active profiles |
| configLabel or configVersion | Configuration revision |
| operation | startup, config-fetch, refresh |
| outcome | success or failure |
| durationMs | Operation duration |
| changedKeys | List of changed keys, without values |
| traceId/spanId | Links logs to traces when tracing is configured |

Application log example:

```text
event=config-refresh
service=orders
instance=orders-7f9d
configVersion=release-2026-11-18
outcome=success
durationMs=184
changedKeys=[catalog.timeout,feature.checkout.enabled]
```

For startup failures, log the root cause, service, instance, profile, and config label if known. Never log access tokens, passwords, private keys, secret contents, or the entire Config Server response.

When using Micrometer Tracing, trace IDs and span IDs can be added to the logging context to correlate logs with traces. However, not every bootstrap activity has a request trace like regular HTTP traffic; retain timestamps and correlation metadata separately for the startup phase.

## 17. Securing Actuator Endpoints During Diagnostics

A minimal configuration for metrics and startup might look like:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,startup
  endpoint:
    health:
      show-details: when-authorized
```

If using Prometheus, add the corresponding registry dependency and expose **prometheus** once the scraper is configured.

Endpoints such as **env**, **configprops**, **loggers**, and **refresh** must be opened under strict control:

- **env** and **configprops** can expose internal configuration structures.
- **loggers** allows changing log levels at runtime.
- **refresh** alters the Environment and can trigger re-initialization of many beans.
- **startup** can expose bean names, classes, and internal structure.

Use a separate management port/interface where appropriate, require authentication, and restrict network access. Only open needed endpoints during investigation and revoke diagnostic settings afterward.

## 18. Symptom-Based Investigation Workflow

| Symptom | First Evidence | Next Step |
| --- | --- | --- |
| Process exits before web server starts | Container/process logs, ApplicationFailedEvent | Inspect root cause, Config Data logs, bind/bean errors |
| Startup is slow yet eventually succeeds | application.started.time, application.ready.time, startup timeline | Find prolonged Environment preparation or bean initialization steps |
| Config Client times out | Client logs, Config Server http.server.requests, proxy access logs | Check DNS, TLS, auth, routing, server load, and retries |
| Config Client sends multiple requests | Request paths and profiles in logs | Identify default pass, active profile pass, discovery lookup, or retry |
| Config Server health is UP yet config is stale | Health indicator cache, property sources, and config version | Check TTL, refresh events, and actual Environment |
| POST refresh succeeds yet bean keeps old value | Changed keys, configprops, bean scope | Check property precedence and whether target was refreshed |
| Refresh endpoint errors | HTTP response, refresh logs, RefreshScope Health Indicator | Locate bean rebind/reinitialize exception |
| One replica receives new config, another does not | Instance ID, config version, and per-instance refresh events | Check Spring Cloud Bus broadcast and each replica's health |
| First request after refresh is slow | Lazy target initialization of RefreshScope | Observe bean recreation time and internal dependency initialization |
| HTTP client metrics lack Config Server requests | Bootstrap client instrumentation | Use server-side metrics, client logs, and proxy logs |

## 19. Practice Exercise

A system consists of **orders-service** and Config Server. After deploying a new release:

- orders-service takes 18 seconds to become ready.
- Config Server records multiple requests for the same service.
- **POST /actuator/refresh** returns a list of changed keys.
- One replica transitions its refresh scope health to **DOWN**.
- The remaining replica still responds with the old timeout.

Investigate in order:

1. Retrieve **application.started.time** and **application.ready.time** for before/after deployments.
2. Enable **BufferingApplicationStartup** and fetch **/actuator/startup**.
3. Cross-reference Environment preparation with Config Client logs.
4. Classify Config Server requests into **default**, active profiles, discovery lookup, and retries.
5. Read **http.server.requests** on Config Server to measure processing time.
6. Check Config Client Health Indicator and TTL to see if health status is stale.
7. Trigger refresh and record changed keys, config label, and processing time.
8. Inspect **configprops** and RefreshScope Health Indicator on each replica.
9. Find the exception preventing the first replica's target bean from re-initializing.
10. Verify the second replica received the event and its target bean actually uses the new timeout.
11. Propose how to broadcast refresh events and add per-instance logs/metrics.

**Completion criteria:** pinpoint how much time was spent in startup, Config Server requests, or bean initialization; explain the Config Client request count; identify the root cause of refresh failure on one replica; provide evidence that all replicas applied the expected config version.

## 20. Key Takeaways

- **application.started.time** and **application.ready.time** measure two distinct startup milestones.
- Actuator **startup** requires **BufferingApplicationStartup**; GET returns a snapshot, POST drains the buffer.
- If ApplicationContext fails to start, Actuator endpoints may not exist yet; use process logs and an **ApplicationFailedEvent** listener.
- Config Data import may load configuration for **default** then active profiles, so multiple requests are not necessarily retries.
- Discovery-first lookup adds a network round trip to locate Config Server.
- **http.server.requests** on Config Server measures server handling time; do not assume bootstrap Config Client calls always appear in **http.client.requests**.
- Config Client Health Indicator caches results for 5 minutes by default; UP does not prove the latest refresh succeeded.
- **EnvironmentChangeEvent** rebinds **@ConfigurationProperties** and updates logger levels; Config Client does not poll by default.
- **RefreshScopeHealthIndicator** helps detect rebind/reinitialize failures after context refresh.
- Measure refresh duration with a dedicated timer if the application needs to track refresh latency.
- Log keys and metadata, never secret values; bound the cardinality of metric tags.
- Secure Actuator endpoints, especially **env**, **configprops**, **loggers**, and **refresh**.

## 21. References

- [Spring Boot — Application Startup](https://docs.spring.io/spring-boot/reference/features/spring-application.html): **ApplicationStartup**, **BufferingApplicationStartup**, and startup events.
- [Spring Boot — Actuator Startup Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html): reading snapshots and draining startup steps.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): **application.started.time**, **application.ready.time**, **http.server.requests**, **http.client.requests**.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, endpoint access, and securing management endpoints.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, default/active profile requests, discovery-first lookup, retry, and Config Client Health Indicator.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): **EnvironmentChangeEvent**, **@RefreshScope**, refresh endpoint, and RefreshScope Health Indicator.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): measuring duration, count, and operation latency distributions.
