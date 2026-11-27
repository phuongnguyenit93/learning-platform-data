# Diagnosing Incidents Using env, conditions, health, and Log Evidence

When a Spring Cloud service starts returning errors after deploying new configuration, the first question is usually: does the fault lie in configuration, auto-configuration, an external dependency, or request-handling code? Each type of evidence answers a different piece of the puzzle. Actuator exposes `Environment`, bean creation conditions, health status, and log levels; application logs reveal what actually happened during a specific request.

This hands-on lab simulates an incident in **orders-service**. After a production configuration revision is rolled out, order creation requests begin failing when calling Inventory. Readiness transitions to DOWN, while liveness stays UP. Learners must gather evidence from **/actuator/env**, **/actuator/configprops**, **/actuator/conditions**, **/actuator/health**, **/actuator/loggers**, and centralized logs to pinpoint the cause.

The investigation uncovers a misspelled hostname in configuration fetched from Spring Cloud Config. **conditions** confirms the Inventory Client bean was still created; **configprops** shows the bound value; **health** reports the dependency is unreachable; logs confirm a DNS failure. From there, operations corrects the true configuration source, performs a controlled rollout, and verifies each replica.

This lesson belongs to the **Hands-on Project** chapter of the **SPRING_CLOUD_CORE** module. The focus is combining Spring Cloud abstractions with Spring Boot Actuator observability to reach evidence-based conclusions while protecting operational data and avoiding further disruption during diagnosis.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Construct an incident timeline and define blast radius by service, instance, profile, and config revision.
2. Distinguish the roles of **env**, **configprops**, **conditions**, **health**, and **loggers**.
3. Trace an effective property value back to the `PropertySource` or origin that supplied it.
4. Cross-check values in `Environment` against values bound into **@ConfigurationProperties**.
5. Read auto-configuration conditions to confirm whether a bean was created or excluded.
6. Read health components and readiness/liveness to separate application failures from dependency failures.
7. Use logs, exception chains, and correlation IDs to validate hypotheses.
8. Temporarily raise log levels for a targeted package and restore them after investigation.
9. Distinguish DNS failures, connection refused, timeouts, TLS errors, and HTTP authentication failures.
10. Handle discrepancies across replicas and configuration revisions.
11. Fix the true configuration owner and perform a controlled rollout.
12. Keep Actuator, logs, and configuration data within secured access boundaries.

## 2. Lab Architecture

### 2.1. Services and Dependencies

The lab involves three components:

- **orders-service**: receives order creation requests and calls Inventory to check stock.
- **inventory-service**: provides the stock lookup API and a health endpoint.
- **Spring Cloud Config Server**: distributes configuration by application, profile, and label.

**orders-service** runs three replicas with the **prod** profile. Each replica pulls configuration using the same config label during the rollout.

~~~mermaid
flowchart LR
    U[Client] --> O[Orders Service]
    O --> I[Inventory Service]
    O --> C[Spring Cloud Config Server]
    O --> A[Actuator]
    A --> E[env and configprops]
    A --> D[conditions]
    A --> H[health]
    A --> L[loggers]
    O --> G[Centralized Logs]
    G --> T[Incident Timeline]
~~~

### 2.2. Configuration Flow

**orders-service** carries safe defaults inside its artifact. Config Server provides production-profile overrides. Spring Boot merges `PropertySource` entries into `Environment`; **@ConfigurationProperties** then binds the required values into typed objects.

~~~mermaid
flowchart TD
    A[application.yml in artifact] --> E[Spring Environment]
    B[Config Server prod label] --> E
    C[Environment variables] --> E
    E --> D[PropertySource precedence]
    D --> P[InventoryProperties binding]
    P --> I[Inventory Client bean]
    I --> H[Inventory health check]
~~~

Seeing a property in `Environment` does not prove the bean received that value. Conversely, a bean might retain an old value if configuration changed after bean instantiation and the bean's lifecycle does not support refresh. Therefore, you must cross-check both **env** and **configprops**.

### 2.3. Endpoints Used

| Endpoint | Primary Evidence | Question Answered |
| --- | --- | --- |
| **/actuator/env** | PropertySources and effective values in Environment | Where did the value come from? |
| **/actuator/configprops** | Objects bound via @ConfigurationProperties | What value does the config bean hold? |
| **/actuator/conditions** | Auto-configuration conditions and match/non-match reasons | Was the bean registered? |
| **/actuator/health** | Application status and components | Which component is DOWN? |
| **/actuator/health/readiness** | Ability to receive traffic | Should the instance accept requests? |
| **/actuator/health/liveness** | Internal process/context state | Does the process need restarting? |
| **/actuator/loggers** | Configured/effective log levels | Are logs detailed enough to inspect? |
| Centralized logs | Requests, exceptions, and timeline | What actually occurred at runtime? |

Endpoints are accessible only when dependencies, access policies, and exposure are configured appropriately. Spring Boot exposes only `health` over HTTP by default; never open every endpoint just for diagnostic convenience.

## 3. Incident Scenario

### 3.1. Monitoring Alerts

At 14:05 UTC, the deployment team updated config label **orders-prod-2026.11.18-42** and rolled out **orders-service** version **2.8.1**.

After the rollout:

- Order creation error rate jumped from under 0.2% to 18%.
- Readiness on all three replicas transitioned to DOWN.
- Liveness on all replicas remained UP.
- Database health remained UP.
- Inventory health transitioned to DOWN.
- Logs showed **UnknownHostException** when calling Inventory.
- **inventory-service** still returned health UP when checked directly.

### 3.2. Initial Timeline

| UTC Time | Event |
| --- | --- |
| 13:55 | Release orders-service:2.8.1 tested in staging |
| 14:05 | New production config label promoted |
| 14:06 | First replica begins receiving traffic with new config revision |
| 14:07 | First replica readiness transitions to DOWN |
| 14:08 | Remaining two replicas complete rollout and also transition to DOWN |
| 14:09 | Alert fires for elevated Inventory call failures |
| 14:12 | Operations team starts collecting evidence |
| 14:24 | Endpoint property identified as having a misspelled hostname |
| 14:31 | Fix config revision created and reviewed |
| 14:38 | Rollout of corrected configuration begins |
| 14:43 | Replicas return to readiness UP |

Timestamps in this lesson are simulated data. During real incidents, use timestamps from deployment systems, log collectors, and individual instances; check timezones and clock skew before correlating events.

### 3.3. Initial Hypotheses

The on-call operations team logged four hypotheses:

1. Inventory service is down.
2. Discovery or load balancer cannot find Inventory instances.
3. Inventory Client was not auto-configured after the rollout.
4. Orders' configured endpoint is wrong.

Do not pick a hypothesis from alerts alone. Each hypothesis needs evidence capable of confirming or refuting it.

## 4. Preparing Sample Configuration and Application

### 4.1. Default Configuration

In **application.yml**, place environment-agnostic defaults:

~~~yaml
spring:
  application:
    name: orders-service

app:
  inventory:
    enabled: true
    base-url: https://inventory.default.internal
    timeout: 1s

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Default configuration gives local or test runs predictable values. Production can override the endpoint via Config Server.

### 4.2. Production Configuration Before the Incident

Suppose Config Server returns:

~~~yaml
app:
  inventory:
    enabled: true
    base-url: https://inventroy.internal
    timeout: 800ms
~~~

The hostname **inventroy.internal** swaps the letters **o** and **r**. The right hostname must be **inventory.internal**.

In this lab, Config Server owns production configuration. Local **application.yml** holds only defaults. Diagnosis must identify the effective property and the source that supplied it.

### 4.3. ConfigurationProperties

Example typed configuration:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.inventory")
@Validated
public record InventoryProperties(
        boolean enabled,
        @NotBlank String baseUrl,
        @NotNull Duration timeout
) {
}
~~~

Register it with **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties**. When reading **/actuator/configprops**, look up the bean with prefix **app.inventory** and inspect the bound values.

A constructor-bound record fits when configuration is loaded at startup. If configuration changes after startup, do not assume a record is automatically recreated or rebound. Choose refresh or restart according to the client's actual lifecycle.

### 4.4. Conditional Bean

Suppose Inventory Client is created only when enabled by property:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.inventory",
        name = "enabled",
        havingValue = "true"
)
class InventoryClientConfiguration {

    @Bean
    InventoryClient inventoryClient(
            InventoryProperties properties,
            RestClient.Builder builder
    ) {
        return new InventoryClient(
                builder,
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
~~~

In the project code, **InventoryClient** is an application-defined class with a **checkHealth()** method using the configured endpoint. The key point in this example is that bean creation depends on **app.inventory.enabled**.

If the property is **false**, **InventoryClientConfiguration** does not match and the bean may not be registered. In that case, **conditions** is the evidence to inspect.

### 4.5. Custom Health Indicator for Inventory

To include an **inventory** component on the health endpoint, the application registers a `HealthIndicator`. The example below uses Spring Boot 4.x API packages; for Spring Boot 3.x, the Actuator health API package differs—follow your project's dependency BOM.

~~~java
package com.example.orders.health;

import com.example.orders.inventory.InventoryClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventory")
public class InventoryHealthIndicator implements HealthIndicator {

    private final ObjectProvider<InventoryClient> inventoryClientProvider;

    public InventoryHealthIndicator(
            ObjectProvider<InventoryClient> inventoryClientProvider) {
        this.inventoryClientProvider = inventoryClientProvider;
    }

    @Override
    public Health health() {
        InventoryClient inventoryClient =
                inventoryClientProvider.getIfAvailable();

        if (inventoryClient == null) {
            return Health.unknown()
                    .withDetail("reason", "inventory-client-not-configured")
                    .build();
        }

        try {
            inventoryClient.checkHealth();

            return Health.up()
                    .withDetail("dependency", "inventory")
                    .build();
        }
        catch (Exception exception) {
            return Health.down()
                    .withDetail(
                            "cause",
                            exception.getClass().getSimpleName()
                    )
                    .build();
        }
    }
}
~~~

Do not include URLs containing credentials, bearer tokens, or full exception messages inside health details. Health details can be scraped by monitoring systems and retained longer than short-term logs.

### 4.6. Selecting the Readiness Group

If Orders cannot create valid orders when Inventory is unreachable, the **inventory** indicator can be added to the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
~~~

Add only truly essential dependencies. If the application has a circuit breaker, fallback, or can serve partial functionality while Inventory is down, consider omitting Inventory from readiness.

Never add external dependency health checks to liveness. If an Inventory outage causes liveness to turn DOWN, the platform may restart replicas en masse and worsen the outage.

## 5. Ensuring Safe Evidence Collection

### 5.1. Actuator Dependency and Exposure

The application requires the Actuator dependency, typically **spring-boot-starter-actuator**. Check the dependency tree and configuration for your Spring Boot release train if endpoints are missing.

In a controlled investigation environment, exposure configuration may allow the needed endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
          - conditions
          - loggers
~~~

This configuration illustrates the endpoint list for the lab. In production, expose only truly required endpoints over a management network/firewall with authentication and authorization.

### 5.2. Opt-In Access Permissions

You can apply an opt-in access policy:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    env:
      access: read-only
    configprops:
      access: read-only
    conditions:
      access: read-only
    loggers:
      access: read-only
~~~

When changing log levels via POST is necessary, temporarily grant write access to **loggers** per operational policy and restrict it to authorized roles. After investigation, return the endpoint to read-only or its baseline access policy.

Access and exposure are two separate conditions. An endpoint is reachable over HTTP only when both access is permitted and web exposure is enabled.

### 5.3. Sanitization of env and configprops

Values returned by **env** and **configprops** may contain passwords, tokens, secrets, or private keys. Spring Boot sanitizes sensitive values by default.

Authorized operational roles may be permitted to view non-sensitive values:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: OPS
    configprops:
      show-values: when-authorized
      roles: OPS
~~~

Never set **show-values: always** in production. The example above grants authorized `OPS` roles visibility during an investigation window; use a custom **SanitizingFunction** to continue masking passwords, tokens, private keys, and sensitive sources. If reliable sanitization rules are not yet in place, keep **configprops.show-values: never** and verify non-sensitive properties through another administrative channel.

### 5.4. Health Details

Health components and details may be hidden by configuration. For example:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      show-components: when-authorized
~~~

If details are restricted, you still see overall status. In that case, rely on logs and dependency checks from the runtime environment to verify the cause.

### 5.5. Do Not Expose All of Actuator

Never use:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

just for quick debugging. Endpoints such as **beans**, **env**, **configprops**, **mappings**, **heapdump**, or **logfile** can leak sensitive operational information. Select endpoints based on the specific questions you need to answer.

## 6. Starting the Investigation: Identifying the Exact Instance

### 6.1. Recording Scope

Before querying endpoints, record:

- Service name and application version.
- Spring Boot version and Spring Cloud release train.
- Active profiles.
- Config Server label or revision.
- Pod/instance ID.
- Namespace and cluster.
- Deployment timestamp.
- Timestamp of first error.
- Sample request/trace ID.
- Number of affected replicas.

### 6.2. Listing Replicas

In Kubernetes:

~~~bash
kubectl get pods -l app=orders-service -o wide
~~~

Record pod names, IPs, nodes, and statuses. Never merge Actuator outputs from multiple pods into one record without instance labels.

### 6.3. Collecting Logs per Pod

~~~bash
kubectl logs pod/orders-service-abc123 -c app --since=30m
~~~

Repeat for each affected pod. If using centralized logging, filter by service, pod, container, time window, and trace ID.

### 6.4. Checking Configuration Revision

If the application publishes its config revision in **/actuator/info** or startup logs, record each replica's revision. Never add a custom debug endpoint that dumps the entire `Environment`. A non-sensitive revision ID is enough to correlate against Config Server or deployment records.

## 7. Reading /actuator/env: Where Did the Value Come From?

### 7.1. Questions Answered by the Endpoint

**env** shows `PropertySource` entries in Spring `Environment` and resolved property values. During investigation, check:

- Does the property exist?
- Which `PropertySource` supplies it?
- Does a higher-precedence source override it?
- Which profiles are active?
- Does the origin point to the expected file or config revision?

Example query for a single property:

~~~bash
curl -sS \
  -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/env/app.inventory.base-url"
~~~

The **ACTUATOR** variable should hold the management URL of the specific instance, not a shared load balancer, when comparing replicas.

### 7.2. Evidence in the Incident

Abbreviated output from replica **orders-service-abc123**:

~~~json
{
  "property": {
    "source": "configserver:orders-service-prod.yml",
    "value": "https://inventroy.internal",
    "origin": "orders-service-prod.yml:18"
  },
  "activeProfiles": ["prod"]
}
~~~

This JSON layout illustrates the key fields to inspect. Actual Actuator responses may nest entries under **propertySources** and include version-specific metadata.

This evidence shows `Environment` holds the misspelled hostname and the source is production configuration from Config Server. It does not yet prove the Inventory Client bean bound this value; the next step is **configprops**.

### 7.3. PropertySource Precedence

A key can appear in multiple sources:

| Source | Example Value |
| --- | --- |
| Command-line argument | https://inventory-cli.internal |
| Environment variable | https://inventory-env.internal |
| Config Server | https://inventroy.internal |
| application.yml | https://inventory.default.internal |

The final effective value depends on actual `PropertySource` order, not on whichever filename sounds more "production." Always check the origin and source in `Environment`.

If one pod has the right value and another has the wrong value, compare active profiles, environment variables, config revisions, and rollout timestamps before drawing conclusions.

### 7.4. When env Hides Values

If a value appears as `**********`, this may be intentional policy sanitization. Never disable sanitization globally just to view one property.

You can continue using:

- Source name and origin if returned.
- Non-sensitive bound values.
- Config revision in deployment records.
- Redacted logs.
- Direct verification inside Config Server using approved access.

## 8. Reading /actuator/configprops: What Did the Bean Bind?

### 8.1. Role of configprops

**configprops** displays **@ConfigurationProperties** beans and the values bound onto those objects. It helps catch issues such as:

- `Environment` is right, yet the bean receives a different value.
- Wrong prefix or property name.
- Unexpected type conversion.
- Bean holding a stale value.
- Bean not registered or not created.

This endpoint can contain sensitive data and is sanitized. Never attach raw output to public tickets.

### 8.2. Checking InventoryProperties

Abbreviated output:

~~~json
{
  "bean": "app.inventory-com.example.orders.InventoryProperties",
  "prefix": "app.inventory",
  "properties": {
    "enabled": true,
    "baseUrl": "https://inventroy.internal",
    "timeout": "PT0.8S"
  }
}
~~~

Both `Environment` and the bean show the exact same misspelled hostname. That makes the hypothesis "bean failed to bind new config" unlikely. Current evidence points to the contents of the config source.

### 8.3. When env Is Right but configprops Is Wrong

If **env** shows the new value while **configprops** still holds an old value, check:

1. Does the bean use constructor binding or a record?
2. Was the bean instantiated before the new configuration source loaded?
3. Is the bean inside **@RefreshScope**?
4. Was a refresh or rebinding event actually triggered?
5. Is the property bound under a different prefix?
6. Does another bean or custom binder hold a separate snapshot?

Do not assume every bean updates automatically when `Environment` changes. For immutable beans or resources built from configuration, a rolling restart is usually easier to verify.

### 8.4. Checking Data Types

For instance, **timeout: 800ms** may bind as **Duration PT0.8S**. If the bound value is **PT8S**, the config source may specify **8000ms** or another value. Always compare typed values against source values and units.

## 9. Reading /actuator/conditions: Was the Bean Created?

### 9.1. Auto-Configuration Conditions

**conditions** lists conditions evaluated on configuration and auto-configuration classes, along with match or non-match reasons.

This endpoint answers questions such as:

- Did **@ConditionalOnClass** find the required class?
- Did **@ConditionalOnProperty** see the expected value?
- Did another bean cause **@ConditionalOnMissingBean** not to match?
- Was an auto-configuration excluded due to missing dependencies or properties?

It does not replace **env** or **configprops**: `conditions` reports conditional decisions, while the other two endpoints report configuration values.

### 9.2. Evidence in the Incident

Abbreviated output:

~~~text
InventoryClientConfiguration
  matched:
    @ConditionalOnProperty
    app.inventory.enabled=true
    matched expected value true

RestClientAutoConfiguration
  matched:
    RestClient.Builder class present
~~~

The evidence confirms Inventory Client was registered. Therefore, the failure is not caused by **app.inventory.enabled=false** or missing required auto-configuration.

### 9.3. When a Condition Does Not Match

For example:

~~~text
InventoryClientConfiguration
  did not match:
    @ConditionalOnProperty
    app.inventory.enabled did not find property
~~~

In that case, inspect **env** to see whether the key is missing, the profile is wrong, or the `PropertySource` was not loaded. Inspect **configprops** and the bean registry as needed.

If a bean definition was not created at startup, `POST` **/actuator/refresh** does not automatically rerun all auto-configuration to add the missing bean. Fix the source and restart or roll out the context as designed.

### 9.4. A Non-Matching Condition Is Not Always an Error

An unmatched auto-configuration can be intentional. For example, an optional module may be disabled, a class may not be on the classpath, or a user-supplied bean may have replaced the default auto-configuration.

Treat a condition as a root cause only when it contradicts business requirements and corroborating evidence.

### 9.5. When the Application Fails to Start

If the context fails to start and **/actuator/conditions** cannot be queried, use the startup condition report:

~~~bash
java -jar orders-service.jar --debug
~~~

Or enable scoped `DEBUG` for **ConditionEvaluationReportLoggingListener** during a controlled diagnostic run. Never leave application-wide `DEBUG` enabled long-term in production.

## 10. Reading /actuator/health: Which Component Is Failing?

### 10.1. Overall Health and Components

**health** returns an overall status and optionally nested components. Detail visibility depends on **management.endpoint.health.show-details**, **show-components**, and access permissions.

In the incident, abbreviated response:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "UP"
    },
    "inventory": {
      "status": "DOWN",
      "details": {
        "cause": "UnknownHostException"
      }
    },
    "discoveryComposite": {
      "status": "UP"
    }
  }
}
~~~

Database and discovery are UP; the Inventory component is DOWN. This makes hypotheses like a database outage or total discovery failure unlikely.

### 10.2. Health Alone Does Not Give the Full Root Cause

**DOWN** is a status, not a root-cause conclusion. A health indicator may return only an exception type or redacted details. Use logs to inspect the exception chain and exact timing.

A health check might test DNS, TCP connect, HTTP status, or a business operation. Read the indicator's implementation to understand what it actually verifies.

### 10.3. Readiness and Liveness

- Liveness answers whether the process/context remains in a valid state to keep running.
- Readiness answers whether the instance should receive traffic.

In this incident, Inventory is an essential dependency of order creation, so the team included **inventory** in the readiness group. Thus readiness going DOWN while liveness stays UP is expected.

~~~bash
curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/health/readiness"

curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/health/liveness"
~~~

If Inventory were an optional dependency with a fallback, you should not place it in readiness merely because its health indicator reports DOWN. Putting a shared dependency in readiness can pull every replica out of the load balancer simultaneously.

### 10.4. Health Groups Are a Business Decision

Spring Boot does not automatically add every external health indicator to the readiness group. The application selects required indicators:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
~~~

If the service can handle requests while Inventory is unavailable, adjust the readiness group or apply circuit breakers/fallbacks appropriately. Never use liveness to check external dependencies.

### 10.5. Checking HTTP Status Codes

Under default status mapping, **DOWN** and **OUT_OF_SERVICE** typically map to HTTP 503; **UP** returns HTTP 200. If your project uses a custom **HttpCodeStatusMapper** or custom status mapping, check the actual configuration before interpreting status codes.

## 11. Using /actuator/loggers: Scoped Log Elevation

### 11.1. Reading Configured and Effective Levels

The **loggers** endpoint shows the explicitly configured log level and the effective level inherited from the logging framework.

~~~bash
curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Example:

~~~json
{
  "configuredLevel": "INFO",
  "effectiveLevel": "INFO"
}
~~~

### 11.2. Raising DEBUG for a Targeted Package

When additional evidence is needed, raise the log level for a specific package rather than the root logger:

~~~bash
curl -sS -X POST \
  -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}' \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Enable it only briefly, monitor log volume, and verify code does not log secrets at DEBUG level. If POST returns 403, check security rules and CSRF policies; never disable CSRF broadly just to bypass the error.

### 11.3. Restoring the Log Level

You can reset the level back:

~~~bash
curl -sS -X POST \
  -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}' \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Setting **null** removes the logger-specific override so it falls back to the inherited level in the logging framework. If the logger originally had an explicit level configured in a file, restore that original level instead of clearing the override.

Runtime log level changes are not persistent configuration. They may be lost on restart and must be reverted immediately after investigation.

## 12. Reading Logs by Timeline and Exception Chain

### 12.1. Sample Log from the Incident

~~~text
2026-11-18T14:07:12.221Z ERROR
service=orders-service
pod=orders-service-abc123
traceId=4f8c2d9a
logger=com.example.orders.inventory.InventoryClient
message="Inventory health request failed"

java.net.UnknownHostException: inventroy.internal
    at java.net.InetAddress.getAllByName(...)
    at ...
~~~

This log shows the client failed to resolve the hostname. Contrast it with other failures:

| Exception or Result | Investigation Direction |
| --- | --- |
| **UnknownHostException** | Hostname, DNS records, search domains, resolver |
| **ConnectException: Connection refused** | Host resolved, but port has no listener or connection rejected |
| **SocketTimeoutException** | Network path, latency, overloaded server, timeout too short |
| **SSLHandshakeException** | Certificate, truststore, hostname verification, TLS protocol |
| HTTP 401/403 | Credentials, token scope, service authorization |
| HTTP 404 | Path, API version, route, or resource |
| HTTP 5xx | Dependency received request but failed processing it |
| No instances available | Service discovery, registration, service ID, zone/metadata |

### 12.2. Correlating the Same Request

Prefer trace IDs or correlation IDs to connect logs across Orders and Inventory. If trace IDs are unavailable, correlate by timestamp, request path, pod, and gateway-assigned request ID.

Do not search solely for **ERROR**. Read the full exception chain, preceding log lines, and subsequent retry logs to distinguish the root error from downstream cascading errors.

### 12.3. Synchronizing Timestamps

Check timestamps across:

- Container logs.
- Nodes.
- Centralized log collectors.
- Config Server.
- Inventory service.
- Deployment controller.

With significant clock skew, a request can appear to occur before the config rollout. Use UTC in incident timelines whenever possible.

### 12.4. Never Log Full Requests or Environment

Avoid logging Authorization headers, cookies, passwords, tokens, request bodies containing personal data, or the entire **Environment**. Diagnostic logs should keep correlation IDs, dependency names, sanitized hosts, timestamps, and exception types.

## 13. Correlating Evidence and Ruling Out Hypotheses

### 13.1. Evidence Matrix

| Hypothesis | Evidence Required | Simulated Finding | Conclusion |
| --- | --- | --- | --- |
| Inventory service down | Direct Inventory health, Inventory-side logs | Inventory health UP | Not supported |
| Discovery failure | conditions, Discovery health, service instance list | Discovery health UP; client uses direct URL | Unlikely |
| Inventory Client not created | conditions, bean/configprops | Condition matched; configprops lists bean | Refuted |
| Misconfigured endpoint | env, configprops, DNS logs | Hostname inventroy.internal | Confirmed |
| Network policy blocking | TCP test from affected pod/namespace, timeout/refused | DNS lookup fails before opening connection | Not primary hypothesis |
| Invalid credentials | HTTP 401/403 and auth logs | No HTTP response received | Refuted |

### 13.2. Root Cause

The production config revision recorded a misspelled hostname in **app.inventory.base-url**. `Environment` picked up the value from Config Server; **InventoryProperties** bound the misspelled value accurately; the Inventory Client creation condition still matched; the health check could not resolve the hostname; logs confirmed **UnknownHostException**.

The root cause is a production configuration content error, not Spring Cloud Discovery or a bean initialization failure.

### 13.3. Why Are All Four Endpoint Types Needed?

- Viewing only `health` tells you Inventory is DOWN, not which setting is wrong.
- Viewing only `env` reveals the hostname, not whether the bean actually bound it.
- Viewing only `configprops` shows the bean's value, not whether auto-configuration matched.
- Viewing only `conditions` shows the bean was created, not whether the dependency is reachable.
- Logs confirm the runtime failure and tie events to specific requests.

Strong conclusions emerge when independent pieces of evidence point to the same cause.

## 14. Step-by-Step Incident Response Procedure

### Step 1 — Determine Blast Radius

Record replica count, profile, version, config revision, region/cluster, and error rate. Determine whether the outage affects the entire service or a subset.

### Step 2 — Stabilize Traffic

If readiness is designed properly, failing instances can be pulled out of traffic. Check whether healthy replicas remain. If all replicas are unready, evaluate fallbacks or configuration rollback before taking actions that reduce capacity further.

### Step 3 — Collect Health

Query global health, readiness, and liveness from each replica. Compare DOWN components, status codes, and transition timestamps.

### Step 4 — Inspect conditions

Confirm critical beans were created. If an auto-configuration did not match, read the reason and trace back to properties, classpath, or overriding beans.

### Step 5 — Inspect env

Locate the suspect property, active profiles, `PropertySource`, and origin. Cross-check the config revision. If values are sanitized, do not widen secret permissions merely for convenience.

### Step 6 — Inspect configprops

Confirm the bean bound the expected value and type. If `env` and `configprops` disagree, check binding timing, constructor binding, refresh scope, and custom binders.

### Step 7 — Read Logs and Apply Scoped Elevation

Locate trace IDs and exception chains. If necessary, raise `DEBUG` on a narrow package and restore it afterward. Never turn on `DEBUG` for the root logger or the entire Spring framework without clear justification.

### Step 8 — Verify Dependency from the Running Location

For DNS errors, check hostname resolution from the affected pod/namespace. For TCP errors, check ports and network policies. For TLS errors, check certificate chains and hostnames. For HTTP errors, check statuses and authentication.

### Step 9 — Fix the Configuration Source

Fix the Config Server repository/label or true property owner. Review the change and verify profiles and property precedence. Never patch `Environment` temporarily on a single replica alone.

### Step 10 — Controlled Rollout

Promote the corrected config revision. Restart or roll out instance groups if clients or resources read properties at startup. Use Spring Cloud refresh only when beans and resources are explicitly designed for it.

### Step 11 — Post-Recovery Verification

On every replica, verify:

- New config revision.
- `env` and property origin.
- `configprops` bound accurately.
- `conditions` still match as expected.
- Inventory health UP.
- Readiness `ACCEPTING_TRAFFIC`.
- Logs free of DNS errors.
- Order error rate returned to baseline.

### Step 12 — Close the Diagnostic Window

Restore log levels. Revoke temporary access grants. Close any extra exposure opened during investigation. Archive the timeline and redacted evidence in the incident record.

## 15. Refresh vs. Restart When Fixing Configuration?

### 15.1. When Might Refresh Be Appropriate?

Spring Cloud Context can support updating `Environment`, rebinding certain mutable **@ConfigurationProperties**, and refreshing **@RefreshScope** beans. This is suitable only when every affected dependency and resource has a lifecycle designed to accept changes.

For example, a bean holding a URL inside a **@RefreshScope** target can be recreated on refresh. However, an HTTP client or connection pool created outside that scope may continue using old settings.

### 15.2. When Should You Restart?

Choose a rolling restart when:

- Beans use constructor binding or records.
- **@ConditionalOnProperty** governs whether a bean exists.
- The bean graph or auto-configuration must change.
- Clients/resources do not support safe refreshing.
- You need to guarantee all replicas run the exact same config revision.
- The refresh lifecycle cannot be verified with certainty.

### 15.3. Refresh Does Not Recreate Conditionally Excluded Beans

If **app.inventory.enabled=false** prevented Inventory Client from registering at startup, changing the property to `true` and calling refresh does not automatically rerun auto-configuration to create the missing bean.

Bean creation conditions are evaluated during context initialization. In this situation, fixing configuration and performing a restart/rollout is the verifiable path.

### 15.4. Do Not Use POST /actuator/env as a Source of Truth

Spring Cloud can enable `POST` **/actuator/env** to modify `Environment`, rebind **@ConfigurationProperties**, and adjust log levels. This is a runtime mutation and does not persist back to Config Server or Git repositories.

If you edit values directly on one instance, other replicas may keep old values and a restart wipes out the override. For Config Server-managed configuration, update the source of truth and promote a new revision.

## 16. Checking Dependencies from the Pod

### 16.1. DNS

From the affected pod or a debug container sharing its network namespace, check the hostname:

~~~bash
getent hosts inventory.internal
~~~

During the incident, check the hostname actually configured:

~~~bash
getent hosts inventroy.internal
~~~

If **getent** is missing from the image, use an organization-approved debug container or a DNS command available in that runtime. Never install packages into a production container just to investigate.

### 16.2. TCP and TLS

Once DNS resolves, verify TCP connectivity to the target port. For HTTPS, verify the certificate chain and hostname verification. Never disable TLS verification as a workaround.

### 16.3. HTTP

Call Inventory's health endpoint from the Orders environment with a short timeout. Use test credentials or a properly scoped workload identity. Never print tokens into terminal history or logs.

### 16.4. Comparing with Service Discovery

If the client uses `DiscoveryClient`/load balancer instead of a direct URL, inspect:

- Service ID.
- `DiscoveryClient` bean and conditions.
- Returned instance list.
- Health/status metadata.
- Zone/region and load-balancer filters.
- Inventory registration and heartbeats.

Do not conclude discovery is broken merely because an HTTP call failed. If the client uses a direct URL, discovery may not even be on the request path.

## 17. Regression Testing After the Fix

### 17.1. Testing Property Binding

Write a test confirming production-style configuration binds to the right URI and `Duration`. For example:

~~~java
@SpringBootTest
class InventoryPropertiesTest {

    @Autowired
    InventoryProperties properties;

    @Test
    void bindsExpectedInventoryConfiguration() {
        assertThat(properties.enabled()).isTrue();
        assertThat(properties.baseUrl().toString())
                .isEqualTo("https://inventory.internal");
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofMillis(800));
    }
}
~~~

This test should run against a dedicated test config fixture rather than reading live credentials or real production configuration.

### 17.2. Testing Condition Matching

Use **ApplicationContextRunner** or integration tests suited to your auto-configuration to confirm:

- When **app.inventory.enabled=true**, Inventory Client is created.
- When **false**, the bean is absent.
- When the property is omitted, behavior matches the designed policy.

Do not assert only `Environment`; assert actual bean presence.

### 17.3. Testing the Health Indicator

Mock Inventory Client to cover both cases:

- **checkHealth()** succeeds: the **inventory** component returns UP.
- **checkHealth()** throws an error: the component returns DOWN without exposing secrets or full URLs in details.

### 17.4. Testing Readiness Policy

If Inventory is a mandatory dependency, confirm the readiness group includes the indicator. If a fallback exists, confirm readiness is not dropped merely because Inventory experiences a transient failure.

Never lump liveness checks and dependency health into the same group.

### 17.5. Testing Config Revisions Through Rollout

In staging:

1. Deploy the tested artifact digest.
2. Promote the matching config revision.
3. Start at least two replicas.
4. Check revision and origin on every replica.
5. Exercise the order creation flow.
6. Verify health/readiness and logs.
7. Run a rollback rehearsal to ensure the prior config revision can be restored cleanly.

## 18. Investigation Exercises

### Exercise 1 — Finding the Wrong Property

Given:

~~~text
env:
  app.inventory.base-url = https://inventroy.internal
  source = configserver:orders-service-prod.yml

configprops:
  baseUrl = https://inventroy.internal

health:
  inventory = DOWN

log:
  UnknownHostException: inventroy.internal
~~~

Write the root cause in two sentences, citing the decisive evidence and the source that must be fixed.

### Exercise 2 — Bean Not Created

Given:

~~~text
env:
  app.inventory.enabled = false

conditions:
  InventoryClientConfiguration did not match
  reason: expected true but property was false

configprops:
  InventoryProperties exists; InventoryClient bean is absent
~~~

Explain why `InventoryProperties` still appears in `configprops` while `InventoryClient` was not created. With a `HealthIndicator` using `ObjectProvider` as in the example, the `inventory` health component returns `UNKNOWN` because the client is not configured. Explain why calling refresh alone does not guarantee bean recreation.

### Exercise 3 — New Environment, Old Bean

Given:

~~~text
env:
  app.inventory.base-url = https://inventory-v2.internal

configprops:
  baseUrl = https://inventory-v1.internal

log:
  request still targets inventory-v1.internal
~~~

List at least three possible causes and how to distinguish constructor binding, **@Value** singletons, **@RefreshScope**, and resources instantiated from configuration.

### Exercise 4 — Network Policy

Given:

~~~text
env:
  app.inventory.base-url = https://inventory.internal

configprops:
  baseUrl = https://inventory.internal

conditions:
  InventoryClientConfiguration matched

health:
  inventory = DOWN
  cause = SocketTimeoutException
~~~

Outline a plan to check DNS, TCP, TLS, NetworkPolicy, and response latency from the affected pod.

### Exercise 5 — Invalid Credentials

Given:

~~~text
health:
  inventory = DOWN
  cause = HttpClientErrorException$Unauthorized

log:
  HTTP 401 from inventory
~~~

Explain why the endpoint and DNS can be valid while requests still fail. Propose how to inspect token scopes and rotation without logging secrets.

### Exercise 6 — Inconsistent Replicas

Replica A has config revision 42 and the right endpoint. Replica B has revision 41 and the old endpoint. Identify the steps to inspect rollout state, Config Server labels, active profiles, and restart timing.

### Exercise 7 — Conditions Not Matching

An auto-configuration fails to match because a dependency class is absent from the classpath. Distinguish a dependency/build error from an `Environment` property error. Recommend checks for dependency management and the condition report.

### Exercise 8 — Health DOWN While Liveness UP

Explain why this can be the desired state when a business dependency fails. State the criteria for including Inventory in readiness and cases where circuit breakers/fallbacks should handle the failure instead.

### Exercise 9 — Temporary Log Level Elevation

Raise `DEBUG` for package **com.example.orders.inventory**, capture a failing request, and reset to the previous level. Write a checklist ensuring root `DEBUG` is never left on and no runtime configuration lingers.

### Exercise 10 — Writing an Incident Report

Produce an incident report covering:

- Impact.
- Timeline.
- Root cause.
- Evidence from env/configprops/conditions/health/logs.
- Remediation steps.
- Post-recovery verification.
- Preventive action items.
- Owners and deadlines.

## 19. Abbreviated Runbook

| Step | Action | Evidence to Save |
| --- | --- | --- |
| 1 | Identify service, pod, profile, version, config revision | Incident metadata |
| 2 | Collect readiness/liveness from each replica | Health JSON and timestamps |
| 3 | Inspect DOWN components | Health component details |
| 4 | Inspect bean/auto-config state | Conditions report |
| 5 | Inspect property source and origin | Redacted env property output |
| 6 | Inspect typed binding | Redacted configprops output |
| 7 | Locate requests and exceptions | Trace IDs, log lines |
| 8 | Apply scoped log elevation if needed | Logger levels before/after |
| 9 | Verify DNS/TCP/TLS/HTTP from affected pod | Probe outputs |
| 10 | Fix source of truth | Config commit/revision |
| 11 | Roll out and verify every replica | Revision, health, smoke tests |
| 12 | Restore log/security policies | Logger levels and endpoint access |

### 19.1. Evidence Recording Template

~~~text
Incident ID:
Service:
Application version:
Spring Boot version:
Spring Cloud release train:
Cluster / namespace:
Pod:
Active profiles:
Config revision:
Timestamp UTC:
Trace ID:

ENV:
Property:
Effective value (redacted if needed):
PropertySource:
Origin:

CONFIGPROPS:
Bean:
Prefix:
Bound value:
Type:

CONDITIONS:
Configuration class:
Matched / did not match:
Reason:

HEALTH:
Global status:
Readiness:
Liveness:
Failed component:
Details (sanitized):

LOG:
Logger:
Exception:
Root cause:
First seen:
Last seen:

CONCLUSION:
Confirmed cause:
Evidence:
Remediation:
Verification:
Rollback plan:
~~~

## 20. Pre-Closure Incident Checklist

### Scope and Evidence

- [ ] Exact pod/instance and config revision identified.
- [ ] Active profiles and application version recorded.
- [ ] Health/readiness/liveness collected from every replica.
- [ ] `env` cross-checked against `configprops`.
- [ ] `conditions` inspected to confirm bean/auto-configuration state.
- [ ] Logs correlated via trace ID or correlation ID.
- [ ] Dependency verified from the exact network namespace.

### Conclusion and Recovery

- [ ] Root cause supported by multiple independent evidence sources.
- [ ] Fixed in the true configuration source owning the property.
- [ ] Config revision reviewed and recorded.
- [ ] Rollout/restart aligned with bean and resource lifecycles.
- [ ] Every replica running the expected revision.
- [ ] Business smoke tests pass.
- [ ] Health and readiness returned to expected state.
- [ ] Logs free of the original error.

### Security and Operations

- [ ] No tokens, passwords, or private keys saved in incident attachments.
- [ ] `env`/`configprops` outputs redacted.
- [ ] Health details contain no sensitive data.
- [ ] `DEBUG` enabled only on targeted packages and reset afterward.
- [ ] Actuator exposure/access restored to baseline policy.
- [ ] No unintended `POST /actuator/env` or write access to `loggers` left active.
- [ ] Readiness does not check optional external dependencies.
- [ ] Liveness does not depend on external services.
- [ ] Action items and owners assigned for the root cause.

## 21. Key Takeaways and Reference Sources

- **env** shows properties in `Environment` and `PropertySource`; use `origin` to locate the owning source.
- **configprops** shows values bound into typed objects; it reveals mismatches between `Environment` and beans.
- **conditions** shows auto-configuration or configuration class match/non-match outcomes and reasons.
- **health** shows component statuses; `DOWN` is an investigative signal, not the root cause itself.
- **readiness** governs whether an instance should receive traffic; **liveness** governs whether the process retains a valid internal state.
- Never place external dependencies into liveness; place them in readiness only when business operations truly cannot proceed if that dependency fails.
- **loggers** displays configured/effective levels and allows runtime updates; enable `DEBUG` only on narrow packages for short durations.
- Spring Boot exposes only `health` over HTTP by default. Exposing extra endpoints must be paired with network isolation, authentication, authorization, and sanitization.
- `env`/`configprops` values are sanitized by default; never enable `show-values=always` in production.
- If a bean condition did not match at startup, refreshing `Environment` does not guarantee recreating the bean definition. Choose restart/rollout when the bean graph must change.
- When fixing Config Server-managed configuration, update the source of truth and promote a revision; avoid temporary overrides on a single replica.
- Every conclusion must be tied to a specific instance, profile, version, config revision, and timestamp.

Official sources:

1. [Spring Boot 4.1 – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
2. [Spring Boot 4.1 – Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
3. [Spring Boot 4.1 – Loggers Endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)
4. [Spring Boot 4.1 – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Boot 4.1 – SpringApplication and Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
6. [Spring Boot 4.1 – Health REST API](https://docs.spring.io/spring-boot/api/rest/actuator/health.html)
7. [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
8. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
9. [Spring Cloud – Release Train and Spring Boot Compatibility](https://spring.io/projects/spring-cloud/)
