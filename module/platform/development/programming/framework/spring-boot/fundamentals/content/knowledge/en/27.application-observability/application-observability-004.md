# `health`, `info`, and the Meaning of Published Data

A Spring Boot application being able to run does not necessarily mean it is **ready to serve**, and an HTTP endpoint returning `200 OK` does not by itself prove the entire system is healthy. In practice, operations teams need to know two distinct groups of information:

- **What state is the application in?** Can it operate, should it receive new requests, or is it having trouble with a required dependency?
- **Which deployment is this application?** Which service does it belong to, what version is it running, what code revision was it built from, and where is its operational documentation?

Spring Boot Actuator provides two commonly mentioned endpoints to address those two needs:

- **`health`** — reports the health status of the application and the components configured to participate in the evaluation.
- **`info`** — publishes intentional metadata about the application, such as service name, build version, or operational support information.

This lesson belongs to **Spring Boot Fundamentals → Application Observability**, focusing not just on enabling endpoints, but on understanding **the meaning of published data**, how to interpret it in monitoring, the reliability bounds of each signal, and security boundaries when exposing information over HTTP.

## 1. `health` and `info` Answer Two Different Questions

Suppose an order processing service returns two responses:

~~~http
GET /actuator/health

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

And:

~~~http
GET /actuator/info

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{
  "app": {
    "name": "orders-api",
    "description": "Order processing service"
  },
  "build": {
    "version": "1.4.2"
  }
}
~~~

The two responses carry completely different meanings:

| Question | `health` | `info` |
|---|---|---|
| Is there an unavailability condition? | Can provide a signal | Not its primary purpose |
| Should new requests be routed to this instance? | Can use readiness health group | No |
| Does the process show severe failure needing a restart? | Can use suitable liveness probe | No |
| Which version is this? | Not primary info | Can return build metadata |
| Can it display service name or description? | Unnecessary | Yes |
| Can it contain sensitive internal info? | Yes, if details are opened uncontrollably | Yes, if metadata is published too broadly |
| Does HTTP 200 prove all business logic succeeds? | No | No |

A complete `info` response can still be returned while the database is down. Conversely, a `health` response of `UP` does not tell you which commit the application is running without corresponding metadata.

**Principle:** use `health` to evaluate serving status against clearly defined conditions; use `info` to **identify and describe the application**, not as a liveness/readiness check system.

## 2. What Is Spring Boot Actuator?

**Spring Boot Actuator** is a collection of capabilities supporting application operations and observability, including endpoints for health, info, metrics, loggers, and many other types of information depending on dependencies and configuration.

In a web application using HTTP, endpoints typically have paths starting with:

~~~text
/actuator
~~~

For example:

~~~text
/actuator/health
/actuator/info
/actuator/health/liveness
/actuator/health/readiness
~~~

Exact paths depend on version, whether endpoints are enabled, exposure configuration, health groups, and customized management paths. Do not infer that all endpoints above are always available after adding a single dependency.

A normal Spring Boot application can run completely without Actuator. However, when deploying via container orchestration, load balancers, or centralized observability systems, Actuator helps provide structured, consistent operational signals.

### Adding the Dependency with Maven

In `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

This example assumes the project already uses Spring Boot dependency management to select a compatible starter version.

### Adding the Dependency with Gradle

Groovy DSL in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Once the starter is present and the application is configured appropriately, Spring Boot auto-configuration registers the corresponding Actuator components.

**Actuator does not automatically turn all operational information into public data.** Whether an endpoint exists in the context is distinct from whether that endpoint is exposed over HTTP and whether callers have permission to access it.

## 3. Three Layers Determining Whether an Endpoint Is Accessible

When someone calls `GET /actuator/info` and receives 404 or 403, you cannot conclude Spring Boot does not support the endpoint. Three layers must be separated:

1. **Endpoint enabled:** is the endpoint activated by the application?
2. **Endpoint exposed:** is the endpoint exposed over the access technology in use, such as HTTP?
3. **Endpoint authorized:** does the request pass authentication/authorization mechanisms?

Diagram:

~~~text
Actuator endpoint
      |
      v
Enabled?
      | No -> Unavailable
      v
Exposed over HTTP?
      | No -> Not found over HTTP
      v
Authorized to access?
      | No -> 401/403 or security-defined behavior
      v
Endpoint processes request and returns data
~~~

Example explicit configuration:

~~~properties
management.endpoints.web.exposure.include=health,info
~~~

It specifies two endpoints exposed over HTTP per Actuator configuration. This line **does not configure authentication or authorization by itself**; when protecting `info` or other management endpoints is required, combine it with appropriate security configuration.

In many common Spring Boot configurations, only `health` is exposed over HTTP by default. Do not assume `info` or other endpoints are public without configuration. Defaults can vary by Spring Boot release; always check the version and configuration of the running project.

### Default Management Paths

A simple example:

~~~properties
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info
~~~

If the web server uses port 8080 and the context path is unchanged, you can try:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
~~~

If the application changes `management.server.port`, servlet context path, web base path, or security rules, the actual URLs will differ. Do not hardcode URLs in monitoring systems without verifying deployment configuration.

## 4. Basic Response of `health`

The `health` endpoint provides an aggregated status of the contributors participating in checks.

A minimal response typically looks like:

~~~json
{
  "status": "UP"
}
~~~

This status indicates that the signals **currently evaluated by the health endpoint** aggregate to `UP`. It **does not guarantee**:

- Every business HTTP endpoint works.
- All databases, caches, queues, or external APIs were checked.
- Data is freshly synchronized.
- The application will remain healthy in a few minutes.
- The instance is receiving traffic through the load balancer.
- There are no logic bugs in any Java method.

**`UP` is the result of a set of checks at the time of the request, under the current configuration.** Interpreting it accurately requires knowing which components are included in the aggregation.

### Common Statuses

Spring Boot supports common health statuses:

| Status | General Meaning |
|---|---|
| `UP` | The contributor is considered functioning according to its check |
| `DOWN` | The contributor or condition is considered non-functioning |
| `OUT_OF_SERVICE` | The component/application is determined unable or unwilling to serve |
| `UNKNOWN` | Insufficient information to reach a clear conclusion |

An application can define custom statuses, though adding a new status requires reviewing both aggregation ordering and HTTP status mapping so monitoring systems interpret it correctly.

Do not treat `UNKNOWN` as guaranteed failure or success; it is a signal that must be interpreted per application policy.

## 5. Health Status and HTTP Status Are Two Layers of Information

For example, when a required database is unreachable:

~~~http
GET /actuator/health

HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

In standard Spring Boot configuration:

- `UP` typically maps to HTTP `200 OK`.
- `DOWN` and `OUT_OF_SERVICE` typically map to HTTP `503 Service Unavailable`.
- Other statuses have default mappings unless customized by developers.

This is why a load balancer or orchestrator can read the HTTP signal of a health endpoint without parsing the entire JSON payload.

However, the status → HTTP code mapping can be **customized**. Therefore, when designing probes, do not rely on a single assumption without checking actual endpoint behavior.

### Why Is a 503 Response Useful?

In a readiness context, HTTP 503 can signal the orchestrator to temporarily stop sending new requests to an instance. This differs from the JVM having stopped; the process can remain running while waiting for a dependency to recover.

In a liveness context, sustained repeated failures can prompt the orchestrator to restart the process. Different purposes require different check policies.

**Not every health 503 means a restart is required.**

## 6. Health Contributors and `HealthIndicator`

Spring Boot Actuator can collect status from many **health contributors**. A simple contributor is commonly implemented via the `HealthIndicator` interface:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class SampleHealthIndicator implements HealthIndicator {

    @Override
    public Health health() {
        return Health.up().build();
    }
}
~~~

`health()` returns a `Health` object carrying a status and optionally details.

Example of a contributor checking readiness of a service:

~~~java
@Override
public Health health() {
    boolean available = checkRequiredResource();

    if (available) {
        return Health.up().build();
    }

    return Health.down()
            .withDetail("reason", "required-resource-unavailable")
            .build();
}
~~~

`checkRequiredResource()` is an illustrative application-defined method. The snippet demonstrates returning `Health`, not built-in ways to check networks, databases, or business state.

### Health Can Aggregate Multiple Components

If an application has contributors for disk space, database, and catalog, aggregated status might look like:

~~~text
Overall health
   |
   +-- diskSpace: UP
   |
   +-- db: UP
   |
   +-- catalog: DOWN
   |
   v
Overall status: DOWN
~~~

How aggregation works depends on the group, which contributors are included in the group, and the configured status aggregator. A single contributor must not be treated as “representing the entire application” if other critical conditions remain unevaluated.

## 7. Health Indicators Provided by Spring Boot

When suitable dependencies and configuration exist, Spring Boot can auto-register common health indicators:

| Group | Example Check Capability | What to Understand |
|---|---|---|
| `diskSpace` | Available disk space | Does not reflect whether data on disk is business-valid |
| `db` | Basic datasource connectivity/responsiveness | Does not guarantee all queries or migrations are right |
| `redis` | Whether Redis responds at the configured check level | Does not guarantee caches are sufficiently populated |
| `mongo` | MongoDB connection status | Does not prove all collections are consistent |
| `rabbit` | RabbitMQ check capability | Does not mean all queues are consuming normally |
| `ping` | A basic health component, if enabled | Does not check application business logic |
| `livenessState` | Liveness per `ApplicationAvailability` | Only reflects lifecycle state published by Spring Boot |
| `readinessState` | Readiness per `ApplicationAvailability` | Does not automatically know asynchronous prep tasks |

Not all of these indicators appear in every project. The actual list depends on starters, classpath libraries, beans, version, and configuration.

**Checking “can the database connect?” is different from “can the payment service complete transactions?”.** Each health indicator guarantees no more than the logic it actually executes.

### Do Not Put Every Dependency Into Every Health Group

If an API can still serve regular requests when an analytics tool or auxiliary email system disconnects, marking the entire service `DOWN` for an optional dependency can cause unnecessary outages.

Clearly identify which dependencies are **truly mandatory** for the published status, especially for readiness.

## 8. Readiness and Liveness Solve Two Different Operational Problems

One of the most important real-world uses of `health` is providing probes for orchestrators like Kubernetes.

Two core terms:

**Liveness:** is the application still in a state capable of continuing to run?

**Readiness:** should this instance receive new requests right now?

Example:

~~~text
Application instance
        |
        +-----------------------+
        |                       |
        v                       v
   Liveness probe          Readiness probe
        |                       |
        v                       v
Process still healthy?   Ready for traffic?
        |                       |
        v                       v
Used for restart         Used for routing
decisions                decisions
~~~

An instance can be **live yet not ready**:

- The web server just opened its port while preparation work is still running.
- A mandatory cache has not finished loading.
- An essential dependency has not recovered, though the app can retry without restarting.
- The instance is temporarily refusing traffic during a controlled shutdown phase.

Conversely, if the application enters an unrecoverable internal state, liveness can be the right signal for a restart under system policy.

### Why Shouldn't the Database Be in Liveness by Default?

Suppose the entire database loses connectivity for a few minutes. If every instance's liveness probe depends directly on the database, the orchestrator can repeatedly restart the entire fleet simply because the database is unavailable.

That widens the outage:

~~~text
Database outage
     |
     v
All app instances report liveness DOWN
     |
     v
Orchestrator restarts entire fleet
     |
     v
Restart storm and load spike when database recovers
~~~

In many architectures, the database should be a **readiness** condition if all requests require it, rather than a liveness condition. Even then, readiness must be designed carefully to avoid cascading effects or pulling all capacity unnecessarily.

## 9. Enabling Liveness and Readiness Health Groups

In Spring Boot, you can configure Actuator probes to access lifecycle-based health groups:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

When the groups are enabled and the web environment supports them, the paths are usually:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Example:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Responses typically look like:

~~~json
{"status":"UP"}
~~~

or:

~~~json
{"status":"DOWN"}
~~~

Whether you receive `UP` depends on startup/shutdown timing and published state, not a guarantee across every call.

Kubernetes environments can activate probe support automatically depending on version and environment. Setting `management.endpoint.health.probes.enabled=true` makes it explicit when testing outside Kubernetes.

### Is `readinessState` Alone Enough?

In a normal startup flow, Spring Boot publishes availability states like:

~~~text
Application starts
     |
     v
Readiness: REFUSING_TRAFFIC
     |
     v
Context refresh and runners execute
     |
     v
ApplicationReadyEvent
     |
     v
Readiness: ACCEPTING_TRAFFIC
~~~

However, if an `ApplicationRunner` merely **submits a cache-loading task to an executor and returns immediately**, Spring Boot can publish `ACCEPTING_TRAFFIC` while the task is still running.

Thus, a readiness group containing only `readinessState` may be insufficient for an application with asynchronous preparation conditions. A custom health contributor reflecting that exact condition is needed.

## 10. Configuring Health Groups for Application Needs

Actuator lets you define or adjust health groups. For example, adding a custom indicator named `catalog` to readiness:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

Logical condition to satisfy:

~~~text
Spring Boot readinessState
           AND
Catalog preparation complete
           |
           v
/actuator/health/readiness -> UP
~~~

If the catalog is not ready, the readiness group can return `DOWN` even though Boot already published `ReadinessState.ACCEPTING_TRAFFIC`.

A health group can also serve a specialized purpose, such as a group for an internal integration endpoint. Be sure to distinguish:

- **Overall health `/actuator/health`:** looks at the default contributors/group.
- **Liveness group:** checks internal viability.
- **Readiness group:** checks conditions for receiving traffic.
- **Custom group:** an application-defined set of health contributors.

Not every group has to have the same members or the same status.

### Independent Liveness Configuration

In many systems, the liveness group should rely primarily on `livenessState`:

~~~properties
management.endpoint.health.group.liveness.include=livenessState
~~~

Intentionally placing network dependencies in liveness should be carefully evaluated because external outages are not necessarily fixed by restarting the app.

## 11. Writing a `HealthIndicator` for Custom Preparation Conditions

Suppose an order API must load a catalog into memory before receiving traffic. We want readiness to report not ready while loading.

File `CatalogHealthIndicator.java`:

~~~java
package com.example.observation;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalogHealthIndicator")
public class CatalogHealthIndicator implements HealthIndicator {

    private final AtomicBoolean ready = new AtomicBoolean(false);

    public void markReady() {
        ready.set(true);
    }

    public void markNotReady() {
        ready.set(false);
    }

    @Override
    public Health health() {
        if (ready.get()) {
            return Health.up()
                    .withDetail("phase", "READY")
                    .build();
        }

        return Health.down()
                .withDetail("phase", "PREPARING")
                .build();
    }
}
~~~

Explanation:

- Initially `ready=false`, so the indicator returns `DOWN`.
- Once preparation work completes, call `markReady()`.
- If a condition arises where the service can no longer serve adequately, call `markNotReady()` per application policy.
- `AtomicBoolean` ensures state is updated safely between the worker thread and threads serving health requests.
- Bean name `catalogHealthIndicator` is typically mapped by Actuator to contributor name `catalog`.

This is a minimal model. In production you might need more states like `PREPARING`, `READY`, `FAILED`, and internal metadata for debugging. Do not expose sensitive data or raw exceptions directly in public health details.

### Combining with Synchronous Startup Tasks

A runner can mark ready only after mandatory work succeeds:

~~~java
package com.example.observation;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogPreparationConfiguration {

    @Bean
    ApplicationRunner prepareCatalog(
            CatalogHealthIndicator indicator
    ) {
        return args -> {
            // Simulate verifiable preparation work.
            // In a real app, replace with actual catalog loading.
            Thread.sleep(1500);

            indicator.markReady();
        };
    }
}
~~~

With a synchronous runner, Boot waits for `run(...)` to return before the ready milestone. `Thread.sleep` is only for lesson simulation, not a suggestion to load production data by sleeping.

If the runner throws an exception, startup can fail. If the work uses `@Async` or an executor and the runner returns immediately, **you must keep the indicator `DOWN` until the background work truly finishes**, not merely until the task is submitted.

### Adding the Indicator to Readiness

In `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

With this configuration, readiness can combine Boot's lifecycle state and catalog readiness.

**Note:** if the `catalog` contributor participates in default overall health, it can also affect `/actuator/health`. Decide clearly on each contributor's scope, which health groups need it, and the response policy of each endpoint.

## 12. When Should You Avoid Heavy Work in a `HealthIndicator`?

Every call to a health endpoint can trigger check logic. If an implementation runs a large query, downloads files, reads millions of records, or waits on a slow system without a timeout, the observability endpoint itself can become a source of resource exhaustion.

Example of what not to do:

~~~java
@Override
public Health health() {
    List<Order> allOrders = orderRepository.findAll();
    return allOrders.isEmpty() ? Health.down().build()
                               : Health.up().build();
}
~~~

Reading the entire database to answer “can the application process requests?” wastes resources and does not reliably reflect the right condition.

Instead:

- Prefer cheap, time-bounded checks.
- If external connections are needed, use timeouts and appropriate controls.
- Perform no side effects or data mutations inside probes.
- Consider health driven by state updated by main processes.
- Distinguish mandatory dependencies from optional components.
- Account for probe frequency across multiple orchestrators, load balancers, and monitoring services.

In reactive applications, if a health check must perform asynchronous I/O, use `ReactiveHealthIndicator` and constructs suited to the reactive web stack. Never block the event loop just to perform a health check.

## 13. What Is the `info` Endpoint Used For?

`info` is where **metadata not intended to describe instantaneous health** is published.

Appropriate examples:

- Service name: `orders-api`.
- Short description: service receiving and processing orders.
- Application version: `1.4.2`.
- Build info: group, artifact, version, build time.
- Git commit ID or branch when configured and permitted for disclosure.
- Responsible team name or internal runbook URL, if the endpoint has an appropriate access scope.
- Non-sensitive API contract version code.

Information inappropriate for public disclosure:

- Passwords, access tokens, API keys.
- Connection strings containing credentials.
- Full environment variables.
- Internal hostnames, infrastructure identifiers, or topology the organization does not wish to expose.
- Absolute file paths to secrets or private keys.
- Detailed security configurations.
- User data or undisclosed business data.

**`info` tells observers “which build is running,” not a dump of the entire `Environment`.**

## 14. Configuring `info.app` via `application.properties`

You can create explicit metadata:

~~~properties
spring.application.name=orders-api

management.endpoints.web.exposure.include=health,info
management.info.env.enabled=true

info.app.name=orders-api
info.app.description=Order processing service
info.app.version=1.4.2
~~~

In the example:

- `info.app.*` are application-defined properties.
- `management.info.env.enabled=true` lets the environment contributor include eligible `info.*` properties in the endpoint on Spring Boot configurations supporting this mechanism.
- `management.endpoints.web.exposure.include=health,info` makes the endpoint reachable over HTTP if enabled and permitted by security.

Illustrative response:

~~~json
{
  "app": {
    "name": "orders-api",
    "description": "Order processing service",
    "version": "1.4.2"
  }
}
~~~

**Do not deduce that merely adding `info.app.name` guarantees the value appears in every version.** Ensure the corresponding contributor is enabled and the endpoint is properly exposed.

### Why Might `info` Return `{}`?

If `/actuator/info` returns:

~~~json
{}
~~~

that usually does not mean the application is broken. Possible reasons:

- No `InfoContributor` is supplying metadata.
- The expected contributor is not enabled.
- Build info / git info resources were not generated.
- `info.*` config is not being read from an active source.

Inspect the actual configuration instead of treating an empty response as a health failure signal.

## 15. Build Information: Avoid Manual Versions When a Build Pipeline Exists

The application version should come from the **build process**, rather than being hardcoded across multiple files.

With Spring Boot, build-info metadata is commonly generated into the resource:

~~~text
META-INF/build-info.properties
~~~

Illustrative content:

~~~properties
build.artifact=orders-api
build.group=com.example
build.name=Orders API
build.version=1.4.2
build.time=2026-11-13T09:00:00Z
~~~

When the build info contributor is enabled and the resource exists, `/actuator/info` can display data under the `build` group:

~~~json
{
  "build": {
    "artifact": "orders-api",
    "group": "com.example",
    "name": "Orders API",
    "version": "1.4.2",
    "time": "2026-11-13T09:00:00Z"
  }
}
~~~

Values are illustrative; actual version, group, and timestamp are generated by the build.

### Generating `build-info` with Maven

With `spring-boot-maven-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>build-info</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

If the project already defines the plugin with another execution, add the `build-info` goal to the proper configuration rather than creating two conflicting plugin declarations.

### Generating `build-info` with Gradle

In a project using the Spring Boot Gradle plugin, you can configure:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Keep in mind: these snippets only show how to instruct the build tool to generate metadata; they do not replace running the right build task or verifying the resource exists inside the artifact.

### Meaning of `build.time`

Build time helps investigate:

- Was the artifact created during the expected release?
- Which instance is running an older build?
- Is there a mismatch between the newly built artifact and what was deployed to production?

However, a timestamp cannot replace commit ID, version, or checksums. Two artifacts can share a version yet differ in contents if the release process does not enforce immutability.

## 16. Git Information: Identifying the Running Commit

If the build generates a resource such as:

~~~text
git.properties
~~~

Spring Boot can use the corresponding contributor to place selected Git metadata into the `info` endpoint, depending on version and configuration.

Example information that may appear:

~~~json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "abc1234",
      "time": "2026-11-13T08:40:00Z"
    }
  }
}
~~~

This data helps answer a crucial question during an incident:

> Which commit's code is the instance running?

With multiple instances after a rolling deployment, comparing commits/versions helps spot an instance that was not updated or was rolled back.

### Git Metadata Is Not Automatically Present in Every Application

Spring Boot cannot deduce the exact source commit simply by running a built JAR without corresponding build data. The build process usually must use a plugin or task to generate `git.properties`.

For instance, Maven projects can use a Git properties plugin; Gradle can use an equivalent plugin. Plugin names, config, and behavior depend on the build system, so consult your specific project.

Do not declare a Git branch as the artifact's source merely because the production server sets a `BRANCH=main` variable. Code build metadata must be bound to the released artifact.

### Level of Information Published

Some Git info configurations allow fuller details. The more detailed it is, the more carefully you must consider:

- Does it leak internal branch names?
- Does it leak private repository URLs or committer details?
- Does it leak sensitive tags/metadata?
- Does it need to be visible to external clients, or only operations systems?

Publish only fields needed for observability, with matching authorization levels.

## 17. Creating a Custom `InfoContributor`

If metadata cannot be fully represented via `info.*` or build/git contributors, you can create a custom `InfoContributor`.

Example:

~~~java
package com.example.observation;

import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

@Component
public class ServiceInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail(
                "service",
                Map.of(
                        "name", "orders-api",
                        "domain", "orders",
                        "runbook", "https://docs.example.org/runbooks/orders"
                )
        );
    }
}
~~~

Illustrative response:

~~~json
{
  "service": {
    "name": "orders-api",
    "domain": "orders",
    "runbook": "https://docs.example.org/runbooks/orders"
  }
}
~~~

The URL in the example merely represents a hypothetical documentation link; learners are not expected to visit it or treat it as real documentation.

### Principles When Designing an `InfoContributor`

1. Publish only metadata useful to callers of the endpoint.
2. Do not dump the entire `Environment`, system properties, or objects containing secrets into `Info.Builder`.
3. Avoid heavy I/O operations when requests hit the endpoint.
4. Do not use `info` for rapidly changing data like database status.
5. Keep keys stable so dashboards or monitoring tools can parse them.
6. If metadata is internal-only, apply appropriate security or internal networking.

`InfoContributor` is a very useful extension mechanism, yet should not be treated as a place to write logs, update business state, or reload data on every request.

## 18. `health` and `info` Can Provide Data at Different Levels of Detail

The health endpoint typically has a mechanism to adjust the level of detail returned:

~~~properties
management.endpoint.health.show-details=never
~~~

Common options:

| Value | Meaning |
|---|---|
| `never` | Do not display health details to clients |
| `when_authorized` | Display when the request satisfies authorization conditions |
| `always` | Display details whenever the endpoint is reachable |

You can also configure component visibility:

~~~properties
management.endpoint.health.show-components=never
~~~

Or another option fitting operational needs. Distinguish **component names** from **details**: exposing contributor names alone can reveal application architecture or technologies, even when details are hidden.

### Minimal Response

~~~json
{
  "status": "UP"
}
~~~

### Detailed Response — Illustrative Only

~~~json
{
  "status": "UP",
  "components": {
    "db": {
      "status": "UP",
      "details": {
        "database": "PostgreSQL"
      }
    },
    "diskSpace": {
      "status": "UP",
      "details": {
        "threshold": 10485760,
        "exists": true
      }
    }
  }
}
~~~

Exact responses depend on contributors and Spring Boot version. If configured to show details only to authorized callers, unauthorized clients see the abbreviated output.

**Do not enable `show-details=always` on a public endpoint just for easy debugging.** Details such as database names, dependency structures, paths, or exceptions can reveal information that should not be shown to external users.

## 19. `when_authorized` Requires Real Access Control

Example configuration:

~~~properties
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=ACTUATOR_ADMIN
~~~

Intent of the configuration:

- Regular callers see only the overall status.
- Users with the matching role see details per the authorization mechanism.

However, verify actual Spring Security and authentication/authorization configuration. **Do not assume that adding `when_authorized` alone makes the endpoint secure**, especially in applications without security or with custom security chains.

In configurations lacking suitable Spring Security, evaluating whether a caller is “authorized” may not behave as expected. Therefore, if the endpoint is public on the Internet, the safer approach is usually publishing minimal status publicly while using an internal, role-restricted endpoint to view details.

### Should Public and Internal Health Endpoints Be Separated?

Many systems use:

~~~text
Public / routed health:
  Only UP/DOWN or minimal status

Internal diagnostics:
  Authorized access required to view components and details
~~~

This is a sensible separation of responsibilities. Load balancer health checks do not need to know datasource names, disk thresholds, or detailed exceptions.

## 20. Security of the `info` Endpoint

Unlike `health`, the `info` endpoint typically contains metadata unnecessary for regular clients. Even when the data is not a password, it can still expose:

- Specific framework or application versions.
- Commit, branch, build timestamp.
- Responsible team names and runbook URLs.
- Architecture or list of business modules.
- Repository paths or build tool info.

This data aids incident debugging, yet can also help attackers identify versions or targets.

**Ask: who needs to know?**

| Caller | Information Likely Needed |
|---|---|
| Load balancer | Basic health status |
| Kubernetes readiness probe | Readiness status |
| Release tracking system | Version, commit, build ID |
| Operations staff | Version, owner, runbook, and relevant metadata |
| External users | Usually do not need most build/internal metadata |

Therefore, consider restricting `info` to internal networks, requiring authentication/authorization, or exposing only non-sensitive fields. If certain metadata must be public, design a fixed set of allowed fields rather than dumping an entire configuration object.

## 21. Enabled, Exposed, and Protected: Protection Design Example

A web application configuration might start with:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.info.env.enabled=true
~~~

This is only **endpoint and data configuration**, not a complete security policy. When `/actuator/info` must only be reachable by operations staff, the application needs a corresponding security rule.

Example with Spring Security 6 and Spring Boot 3.x in a Servlet application:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.autoconfigure.security.servlet
        .EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders
        .HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This snippet illustrates **a `SecurityFilterChain` for Actuator**, not the full security configuration for the entire application. In a real project, add chains for business URLs and appropriate authentication policies. Do not use sample credentials or public Basic Auth outside managed HTTPS environments.

**Note:** `permitAll()` on `health` typically also permits health sub-endpoints/groups matched by that matcher; if you need only one probe public and other groups protected, write more specific rules by path and test the actual policy.

When an application declares its own `SecurityFilterChain`, do not assume Spring Boot's auto-configuration will continue protecting every endpoint as desired. The organization must explicitly decide which endpoints are public, which roles are required, and where they are exposed.

## 22. Separate Management Port and Differences Between Two Ports

Spring Boot supports configuring the management server on a port different from the application server in appropriate environments.

Example:

~~~properties
server.port=8080
management.server.port=9090
management.endpoints.web.exposure.include=health,info
~~~

Then, depending on configuration:

~~~text
Application API:
  http://localhost:8080/api/orders

Management:
  http://localhost:9090/actuator/health
  http://localhost:9090/actuator/info
~~~

A separate port can be convenient for restricting management access via network policies. However, it also creates a nuance:

**The management port returning health UP does not prove the application port is accepting requests normally.**

For example, the management server can keep working while the application connector or part of routing on the main port fails. If the orchestrator needs to check real traffic-serving capability, consider probes on the **main server port** or an appropriate end-to-end check.

### Additional Probe Paths

Spring Boot supports probe-related options:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

In supported configurations, probes can also be served on the main server port under paths such as `/livez` and `/readyz`. Verify the actual paths/ports for your version and web stack.

The goal is for probes to test a path closer to the port serving real requests, rather than only confirming the separate management context is alive.

## 23. Kubernetes Configuration Sample with Readiness/Liveness

Example pod/container manifest with web port 8080:

~~~yaml
containers:
  - name: orders-api
    image: example/orders-api:1.4.2
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
~~~

This example assumes Actuator probes are enabled and these two URLs are served on port 8080. If using a separate management port, the configuration would differ.

**Meaning of the two probes:**

- Readiness failing: the instance normally receives no new requests from routing paths that respect readiness.
- Liveness failing continuously beyond threshold: the orchestrator may restart the container.
- An HTTP 503 from readiness can happen during startup or when a mandatory dependency is unready without meaning the JVM died.

If the application starts slowly, use a `startupProbe` to allow extra startup time before liveness begins triggering restarts. A startup probe does not replace readiness: an app whose infrastructure finished starting may still lack business conditions to accept traffic.

### Do Not Copy Probe Parameters Mechanically

Values for `periodSeconds`, `timeoutSeconds`, and `failureThreshold` must be based on:

- Expected startup time.
- Health check latency.
- System load.
- Rollout policy.
- Time needed to detect and react to incidents.

Setting timeouts too short can cause false negatives under high load. Setting thresholds too high can delay pulling a genuinely unready instance.

## 24. Health Checks Must Not Become the Cause of an Outage

Suppose every health request executes a complex SQL query. With multiple monitoring layers, one instance can be probed tens or hundreds of times per minute.

~~~text
Load balancer probe
          |
Kubernetes probe
          |
Monitoring collector
          |
          v
  /actuator/health
          |
          v
  Expensive database query
          |
          v
     Increased DB load
~~~

In the worst case, the probes themselves overload the dependency and push health to DOWN, creating a negative feedback loop.

A proper health check should:

- Execute fast and have a timeout.
- Not mutate business state.
- Not hold long locks.
- Not spawn bursts of unnecessary new connections.
- Not depend on an overly broad list of services unnecessarily.
- Have caching or state-update policies suited to signal freshness needs.

Some critical components may require direct checks. Still, what is checked must be proportionate to health's meaning and probe frequency.

## 25. `info` Should Not Contain Second-by-Second Mutable Data

An example of misusing `InfoContributor`:

~~~java
@Override
public void contribute(Info.Builder builder) {
    builder.withDetail("activeOrders",
            orderRepository.countAllActiveOrders());
}
~~~

If every `/actuator/info` request queries the database for a count, this endpoint is doing the work of a metric or live dashboard rather than providing metadata.

Instead:

- Use **metrics** to track active order counts, latency, and error rates.
- Use **logs** for context on specific events.
- Use **tracing** to investigate cross-service call flows.
- Use **health** for clearly scoped operational conditions.
- Use **info** for version identification, service identity, and contact information.

These tools complement one another. Do not turn a single endpoint into a catch-all dumping ground for observability data merely because it renders nicely as JSON.

## 26. `health` Is Not a Business API

Suppose a service has order processing APIs:

~~~text
POST /api/orders
GET  /api/orders/{id}
~~~

A health indicator can confirm the database is reachable. However, that does not verify:

- Whether taxes and prices are calculated accurately.
- Whether duplicate orders are prevented.
- Whether the payment flow responds per business rules.
- Whether returned data respects access permissions.

That is the job of unit tests, integration tests, contract tests, end-to-end tests, and business monitoring.

**Health helps operations make quick decisions; it does not prove product correctness.**

Therefore, when a service reports `UP` while users still encounter errors, investigate requests/metrics/logs/tracing and business conditions rather than trusting the health response alone.

## 27. Small Project Example: `health` + `info` + `readiness`

Suppose an order management application contains:

~~~text
orders-api
  |
  +-- Spring Web
  |
  +-- Spring Boot Actuator
  |
  +-- CatalogHealthIndicator
  |
  +-- ServiceInfoContributor
  |
  +-- API /api/ping
~~~

### 27.1. Dependencies

Maven:

~~~xml
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
~~~

### 27.2. Main Class

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

### 27.3. Minimal API Endpoint

~~~java
package com.example.orders;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
~~~

### 27.4. Actuator Configuration

~~~properties
spring.application.name=orders-api

management.endpoints.web.exposure.include=health,info
management.endpoint.health.probes.enabled=true

management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

management.info.env.enabled=true
info.app.name=orders-api
info.app.description=Order processing service
info.app.version=1.4.2
~~~

If `CatalogHealthIndicator` from earlier is declared and you want it to participate in readiness:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

### 27.5. Observing From the Terminal

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

The `/api/ping` response shows the example route works, `/health` shows aggregated health status, `/info` shows configured metadata, and liveness/readiness provide lifecycle and group-checked condition signals.

A request returning HTTP 404 may mean the endpoint is not exposed or the URL mismatches. A 401/403 may mean security. A 503 on health can be a failing status signal, **not necessarily a disabled endpoint**.

## 28. Reading a Health Response with Components

In an environment with authorized access, a response may include contributors:

~~~json
{
  "status": "DOWN",
  "components": {
    "catalog": {
      "status": "DOWN",
      "details": {
        "phase": "PREPARING"
      }
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

Correct interpretation:

1. Overall status is `DOWN`.
2. The `catalog` component is reported as not ready.
3. DiskSpace and Ping report `UP` according to their own checks.
4. **Do not conclude CPU, database, queues, or every API are healthy** if they are not represented or checked.
5. This response should only be served to callers with appropriate permissions if components/details expose internal info.

A `DOWN` response needs additional context from logs and metrics to know **why** catalog is not ready, whether it will recover automatically, or whether intervention is required.

## 29. Aggregated Health Status Can Hide Differences Between Components

Suppose:

~~~text
diskSpace = UP
db        = DOWN
cache     = UP
~~~

Aggregated status can be `DOWN` because the database is included in the aggregation.

Yet another service might use the same database optionally for certain APIs. For that service, the readiness decision when the database is DOWN could be different.

Therefore:

- **Same status does not mean same cause.**
- **Same cause does not necessarily yield the same routing policy.**
- **A health group suitable for app A may not suit app B.**

Do not write orchestration policies based solely on contributor names without understanding their role in the service.

### Custom Statuses and Precedence Order

Spring Boot has a mechanism for aggregating contributor statuses and allows customizing their order, for example when an application adds a `DEGRADED` status.

When creating a custom status, ensure consistency:

- Which status is more severe?
- Which status constitutes a readiness failure?
- What is the corresponding HTTP status code?
- How does monitoring interpret the new status?
- Should liveness be affected by that status?

Without a clear need, using built-in statuses is usually simpler and easier to integrate.

## 30. Health in Reactive Applications

In Spring WebFlux or reactive environments, blocking I/O inside a health check can cause issues if executed on an inappropriate processing thread.

Spring Boot provides `ReactiveHealthIndicator` for asynchronous health representation:

~~~java
package com.example.observation;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveSampleHealthIndicator
        implements ReactiveHealthIndicator {

    @Override
    public Mono<Health> health() {
        return Mono.just(Health.up().build());
    }
}
~~~

The example only illustrates the interface; there is no real I/O.

When checking an external dependency, a reactive implementation should:

- Use a client suited to the reactive stack.
- Have an explicit timeout.
- Map errors into reasonable health statuses.
- Never block the event loop with uncontrolled blocking calls.
- Avoid overly heavy network operations on every probe.

Depending on the stack, Spring Boot adapts health contributors appropriately. The principles regarding health's meaning and scope remain unchanged: a check only states what it actually measures.

## 31. `InfoContributor` Must Also Have Stable, Reliable Data

Some metadata fields are very useful yet require careful management.

| Metadata | Meaningful Usage | Risk If Exposed Broadly |
|---|---|---|
| `app.name` | Identify the service | Usually low, though naming policy still matters |
| `app.version` | Know which release is deployed | May reveal vulnerable versions |
| `build.time` | Investigate stale/new artifacts | May reveal release schedules |
| `git.commit.id` | Trace back to release source code | May help infer repository info |
| `runbook` | Assist incident response | Internal doc links should usually not be public |
| `team` | Identify owner | Can expose internal org structure |
| `region` | Distinguish deployment locations | Can expose topology |
| `feature-flags` | Know feature configuration | Should not dump all flags or policies |
| `environment variables` | Useful when debugging certain values | Very likely to contain secrets and sensitive data |

An application with multiple replicas can share the same `app.version` or `git.commit.id`, while process start times and some environment parameters differ. If placing much runtime data in `info`, decide clearly whether it remains stable metadata worth publishing.

### Do Not Treat Client-Supplied Info as a Trusted Build Source

For instance, if an application takes a `version` value from an HTTP request and echoes it in `info`, that data does not prove which code version is running. Build metadata is far more trustworthy when generated by a pipeline and embedded in the artifact via a controlled release process.

## 32. Common Deployment Scenarios

### A. Load Balancer Only Needs to Know Whether the Instance Accepts Traffic

Use the readiness health group or a clearly scoped check endpoint. There is no need to expose `info` or health details to the load balancer.

### B. On-Call Needs to Know Which Deployment Is Failing

Use `info` with version/commit alongside logs/metrics. Set appropriate access permissions so only operators can view the required metadata.

### C. A Mandatory Dependency Is Down

If the application cannot serve core requests when this dependency disconnects, reflect it in readiness. Avoid putting this dependency in liveness if restarting the application cannot fix the outage.

### D. An Auxiliary Dependency Fails

If the application can still serve core functionality, use dedicated metrics and alerts instead of forcing all of readiness `DOWN`.

### E. Startup Has an Asynchronous Data-Loading Step

Use a dedicated preparation state combined with the readiness group; do not report ready solely because `ApplicationReadyEvent` fired.

### F. Need to Check an Instance Externally

If exposing health externally is required, prefer minimal status and control ports, paths, and network access. Do not automatically expose other Actuator endpoints just because you want health.

## 33. Common Configuration Errors and How to Investigate

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `/actuator/health` returns 404 | Actuator missing, wrong endpoint/path, or not exposed | Dependencies, base path, management port, config |
| `/actuator/info` returns 404 | Info not exposed or endpoint disabled | Exposure include, endpoint enablement |
| `/actuator/info` returns `{}` | No info contributor or not enabled | `management.info.env.enabled`, build/git resources |
| `/actuator/health` returns 503 | Aggregated status is DOWN/OUT_OF_SERVICE | Logs, internal contributors, mandatory dependencies |
| Health always UP while main API fails | Health checks only a limited set of conditions | Redesign checks/metrics and business validation |
| Readiness UP while cache not loaded | Async task not participating in readiness | Add indicator reflecting true completion |
| Liveness DOWN due to DB outage | DB placed in liveness | Separate readiness and liveness |
| Health times out | Slow indicator or distant dependency | Timeouts, measure latency, reduce probe work |
| Cannot view health details | `show-details=never` or insufficient permissions | Check display policy and authorization |
| Info exposes internal data | Overly broad exposure and contributor config | Restrict fields and enforce authorization |
| Management port health UP yet API port fails | Probe does not traverse same traffic path | Check additional probe paths or app smoke tests |
| Build info missing | `build-info.properties` not generated or packaged | Check build plugin, archive, and contributor |
| Git info wrong/missing | `git.properties` not generated or artifact version drift | Verify CI pipeline and artifact |

The table above offers investigation starting points. Specific failures must be confirmed from stack traces, configuration, and actual system responses.

## 34. Hands-On: Observing `health` and `info` Step by Step

In a safe local or staging environment, you can try the following steps.

### Experiment 1 — Minimal Health

Add the Actuator starter and configure:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Run the application and call:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Record the HTTP status and body. Do not infer anything about dependencies that were not checked.

### Experiment 2 — Info From Environment

Add:

~~~properties
management.info.env.enabled=true
info.app.name=learning-service
info.app.version=0.1.0
~~~

Call:

~~~bash
curl -i http://localhost:8080/actuator/info
~~~

Compare output before and after adding the configuration. If output is empty or the endpoint returns 404, identify the right cause category: missing metadata vs. unexposed endpoint.

### Experiment 3 — Custom `HealthIndicator`

Create `CatalogHealthIndicator` from Section 11. Before calling `markReady()`, the indicator returns `DOWN`. After calling `markReady()`, it returns `UP`.

Add:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalog
~~~

Check `/actuator/health/readiness` during the preparation phase and after completion.

### Experiment 4 — Testing Restriction of Published Data

Switch:

~~~properties
management.endpoint.health.show-details=never
~~~

to a policy restricted to authorized callers, such as `when_authorized` with an appropriate role. Test with two different identities if the project has real security configured.

Do not try enabling details and exposing the endpoint publicly on the Internet just for convenient viewing.

### Experiment 5 — Checking Build Metadata

Configure the build tool to generate `META-INF/build-info.properties`, package the application, and run that artifact. Call `/actuator/info` to see whether build info is present.

Some fields may vary by plugin and version; the key takeaway is that build metadata must be generated and present inside the runtime artifact.

## 35. Misconceptions to Avoid

**“Health UP means all APIs work.”** False. It only aggregates configured checks and may not cover business logic.

**“Info returning 200 means the system is healthy.”** False. Info primarily publishes metadata and is not designed as a readiness or liveness signal.

**“Just adding the starter makes every endpoint public.”** False. Enabled, exposure, and security are separate layers.

**“When health returns 503 every instance must be restarted.”** False. In readiness, it may indicate waiting for recovery; whether to restart depends on liveness and operational policy.

**“Might as well check every dependency in liveness to be safe.”** Can trigger restart storms when external dependencies experience outages.

**“`ApplicationReadyEvent` guarantees all data is loaded.”** Incorrect for asynchronous tasks launched and returned early.

**“Empty info is an error.”** Not necessarily; a contributor may not be configured yet.

**“`show-details=always` is the only way to monitor well.”** False. Probes usually need status only; details should require proper authorization and clear purpose.

**“Just enabling the info endpoint automatically exposes all `info.*` values.”** Still depends on contributors and configuration in the Boot version in use.

**“The more checks a `HealthIndicator` runs, the more reliable it is.”** Not necessarily. Slow, heavy, or over-dependent probes can destabilize the system.

**“Separating the management port is enough to keep endpoints safe.”** No. Proper network policies, authentication, and authorization are still required.

**“As long as no direct secrets are returned, all metadata can be public.”** Versions, commits, topology, or runbooks can also be valuable internal intelligence for attackers.

## 36. Design Checklist Before Taking `health`/`info` to Production

1. **Purpose:** does the endpoint serve a load balancer, Kubernetes, or operations staff?
2. **Scope:** which signals genuinely affect liveness or readiness?
3. **Freshness:** is the health check event-updated or evaluated on every call?
4. **Performance:** are health contributors fast, time-bounded, and side-effect-free?
5. **Output:** do status and HTTP codes align with probes/alerting?
6. **Security:** which endpoints are public, and which require authentication/authorization?
7. **Data:** do details leak credentials, topology, or internal info?
8. **Version:** does `info` reflect the actual artifact, not just manually typed values?
9. **Topology:** are probes hitting the management port or the application port?
10. **Deployment:** have startup, shutdown, and mandatory dependency failure behaviors been tested?
11. **Complementary observability:** are logs, metrics, and tracing sufficient to investigate when health goes DOWN?
12. **Recovery:** when readiness goes DOWN, is there a recovery mechanism or alert rather than leaving the system out of service indefinitely?

An initial configuration for an API with Actuator wanting minimal health and internal info could be:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.endpoint.health.probes.enabled=true

management.info.env.enabled=true
info.app.name=orders-api
info.app.description=Order processing service
~~~

**Security/network policies appropriate to the actual environment must be added** before considering this configuration production-ready. If only a load balancer needs `health` and nobody needs `info`, you can expose even less.

## Conclusion

Spring Boot Actuator provides two endpoints with distinct roles:

- **`health`** reports operational status according to configured health contributors and health groups. It can support readiness/liveness and respond with `UP`, `DOWN`, `OUT_OF_SERVICE`, or `UNKNOWN`, yet only speaks to the conditions evaluated at call time.
- **`info`** publishes intentional metadata, such as service name, build version, commit, or support details. It serves deployment identification and operational investigation, **not health measurement**.

When using them, keep **endpoint enabled**, **exposed over HTTP**, and **authorized for access** distinct. Do not open health details, build info, repository details, or environment info broadly merely for debugging convenience. For orchestrators, separate **liveness** from **readiness**, avoid putting unnecessary dependencies into liveness, and add business conditions when Spring Boot reports ready yet asynchronous preparation has not completed.

**The value of observability data lies not in publishing as much as possible, but in ensuring recipients understand accurately what a signal proves — and what it does not.**
