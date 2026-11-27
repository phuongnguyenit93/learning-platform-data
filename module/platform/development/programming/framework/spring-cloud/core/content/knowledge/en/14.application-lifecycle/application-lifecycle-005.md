# The Restart Endpoint and Default Enablement Status

Spring Boot Actuator and Spring Cloud Context provide several endpoints that can directly affect an application's lifecycle. Among them, `/actuator/restart` can close and restart the `ApplicationContext`; `/actuator/pause` and `/actuator/resume` control components supporting pause/resume; and `/actuator/shutdown` instructs the application to terminate.

These endpoints have different levels of impact and do not share a single mechanism. `restart`, `pause`, and `resume` belong to **Spring Cloud Context**; `shutdown` is a **Spring Boot Actuator** endpoint. Whether an endpoint has an implementation, is enabled, is exposed over HTTP, and is authorized to be called are separate conditions. Therefore, you cannot conclude an endpoint is reachable simply by seeing its name in documentation or adding an exposure line.

This lesson belongs to the **Application Lifecycle** chapter of the **SPRING_CLOUD_CORE** module. The scope focuses on shared Spring Cloud platforms, the `ApplicationContext` lifecycle, externalized configuration, service management, and limitations when operating multiple instances.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish between restart, pause, resume, shutdown, and refresh.
2. Describe the roles of Spring Cloud `RestartEndpoint` and its related endpoints.
3. Identify the default state of restart, pause/resume, and shutdown.
4. Distinguish between an endpoint being created, granted access, and exposed over HTTP/JMX.
5. Configure endpoints according to Spring Boot 3.x or 4.x.
6. Invoke endpoints with the appropriate HTTP method and verify outcomes.
7. Explain the effects of restart/shutdown on `ApplicationContext`, the JVM, and replicas.
8. Design appropriate administrative permissions, graceful shutdown, testing, and monitoring.

## 2. Four Distinct Lifecycle Operations

| Operation | Endpoint | Component | Primary impact |
| --- | --- | --- | --- |
| Context restart | `/actuator/restart` | Spring Cloud Context | Closes the current `ApplicationContext` and restarts the context |
| Pause | `/actuator/pause` | Spring Cloud Context | Invokes `pause()` on registered `PauseHandler` beans |
| Resume | `/actuator/resume` | Spring Cloud Context | Invokes `resume()` on registered `PauseHandler` beans |
| Shutdown | `/actuator/shutdown` | Spring Boot Actuator | Closes the context and terminates the application; supported only when running as an executable JAR |
| Configuration refresh | `/actuator/refresh` | Spring Cloud Context | Reloads configuration via the refresh mechanism and refreshes eligible beans |

**Restart is not refresh.** Refresh keeps the running context alive and updates configuration/beans via Spring Cloud's mechanism. Restart recreates the context, so many beans and resources go through initialization lifecycle from the beginning.

**Pause is not shutdown.** Pause controls only components with a `PauseHandler`; it does not inherently stop the entire HTTP server, close the context, or terminate the JVM.

**Shutdown does not automatically restart the application.** After the process exits, the deployment platform such as Kubernetes, systemd, or a process supervisor may restart the process according to its own policy.

~~~mermaid
flowchart TD
    A[Running application] --> B{Administrative action}
    B -->|restart| C[Close ApplicationContext]
    C --> D[Create and start new ApplicationContext]
    D --> A
    B -->|pause| E[Invoke PauseHandler.pause]
    E --> F[Supported components pause]
    F -->|resume| G[Invoke PauseHandler.resume]
    G --> A
    B -->|shutdown| H[Close ApplicationContext]
    H --> I[Application terminates]
    B -->|refresh| J[Update Environment and eligible beans]
    J --> A
~~~

The diagram illustrates high-level effects. Which components an operation actually controls still depends on endpoint availability, registered handlers, and how the application is configured.

## 3. Default Enablement Status

### 3.1. Overview Table

Current Spring Cloud Commons 5.0.4 documentation describes `/actuator/restart` as **disabled by default**. `/actuator/pause` and `/actuator/resume` are only created when `RestartEndpoint` is present, so they are also unavailable under default configuration when the restart endpoint is not enabled.

Spring Boot Actuator describes `/actuator/shutdown` as **disabled by default**. With Spring Boot 4.x, the default access level for the shutdown endpoint is `none`.

| Endpoint | Owner | Default per current docs | Key conditions |
| --- | --- | --- | --- |
| `restart` | Spring Cloud Context | Disabled | Must grant access/enable endpoint; requires Actuator and Spring Cloud Context |
| `pause` | Spring Cloud Context | Unavailable when `RestartEndpoint` is disabled | Requires `RestartEndpoint` and appropriate `PauseHandler` beans to take effect |
| `resume` | Spring Cloud Context | Unavailable when `RestartEndpoint` is disabled | Requires `RestartEndpoint` and appropriate `PauseHandler` beans to take effect |
| `shutdown` | Spring Boot Actuator | Disabled | Must enable endpoint, allow write access, and expose over protocol; works only with executable JAR |
| `refresh` | Spring Cloud Context | Depends on endpoint configuration of the active release | Does not restart the entire context |

**Version note:** endpoint defaults and configuration syntax have changed across Spring Boot/Spring Cloud generations. Some older docs or metadata may list `restart.enabled=true` as default. For your project, always check the documentation for the exact Spring Cloud release train and Spring Boot version. The table above reflects current Spring Cloud Commons 5.0.4 and Spring Boot 4.x documentation at the time of writing.

### 3.2. Why Must Multiple Conditions Be Checked?

For an endpoint to be callable over HTTP, check at least:

1. **Implementation exists:** the dependency providing the endpoint is on the runtime classpath and the relevant auto-configuration is active.
2. **Endpoint is available:** the endpoint is not disabled or restricted by access controls.
3. **Exposed:** the HTTP/JMX transport is configured to expose the endpoint.
4. **Authorized to call:** Spring Security, firewalls, management port, and network policies allow the request.
5. **Correct HTTP method:** state-changing operations typically use `POST`.

~~~mermaid
flowchart TD
    A[Endpoint has implementation?] -->|No| X[Endpoint does not exist]
    A -->|Yes| B[Endpoint enabled / access permitted?]
    B -->|No| Y[Endpoint unavailable]
    B -->|Yes| C[Exposed over HTTP or JMX?]
    C -->|No| Z[No matching route]
    C -->|Yes| D[Authentication and authorization allowed?]
    D -->|No| Q[401 / 403 or blocked]
    D -->|Yes| E[Endpoint can receive requests]
~~~

Do not rely on a single HTTP error code to diagnose the root cause. `404` can mean the endpoint does not exist or is not exposed; `401`/`403` usually relate to authentication/authorization; `405` can mean the wrong HTTP method was used.

## 4. `/actuator/restart` in Spring Cloud Context

### 4.1. Functionality

`RestartEndpoint` allows closing the current `ApplicationContext` and restarting the context within the same application. The endpoint is provided by Spring Cloud Context and integrates with Spring Boot Actuator.

A context restart typically sends the following components through a fresh lifecycle:

- Singleton beans are destroyed and recreated.
- Callbacks such as `@PreDestroy`, `DisposableBean`, or `destroyMethod` execute as beans/context close.
- Configuration and auto-configuration are reprocessed when the context starts.
- Connections, clients, schedulers, or listeners managed by the context may be reinitialized.
- Startup runners and listeners may be invoked again under the new startup lifecycle.

`restart` does not replace the JVM or the executable JAR. The process may continue existing under the same PID while the `ApplicationContext` is recreated. It also does not deploy a new artifact version; to change classpath or binaries, you must rebuild and redeploy the application.

### 4.2. When to Consider Restart?

Context restart can be useful when:

- A change only takes effect at bean initialization time and lacks a safe refresh mechanism.
- A component needs to be recreated with new configuration.
- Startup behavior needs to be tested in a controlled environment.
- The application has specific operational requirements permitting context recreation without terminating the JVM.

Do not treat restart as a cure-all for every failure. If a problem resides in the JVM, classpath, native libraries, non-Spring threads, process state, or resources that cannot be safely recreated, restart the process or redeploy via the process management platform.

### 4.3. Restart Affects Only the Context of the Instance Receiving the Request

If an application runs multiple replicas, calling the endpoint on one instance restarts only the context in that process. Other instances do not restart automatically.

Example:

~~~text
orders-service-1 -> JVM 1 -> ApplicationContext 1
orders-service-2 -> JVM 2 -> ApplicationContext 2
orders-service-3 -> JVM 3 -> ApplicationContext 3
~~~

Calling `POST /actuator/restart` on `orders-service-1` does not mean `orders-service-2` and `orders-service-3` also restart. Separate orchestration or a rollout procedure is required to affect multiple replicas.

## 5. Enabling the Restart Endpoint

### 5.1. Spring Boot 3.x: the `enabled` Property

For Spring Boot 3.x versions still using the `enabled` mechanism, enable the endpoint with:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,restart,pause,resume
~~~

`management.endpoint.restart.enabled=true` lets Spring Boot Actuator create the restart endpoint. `management.endpoints.web.exposure.include` exposes the selected endpoints over HTTP.

Starting in Spring Boot 3.4, a new access management model was introduced and the `enabled` property was deprecated in favor of `management.endpoint.<id>.access`. When using Boot 3.4/3.5, prefer the `access` syntax if supported by your project and dependencies; do not copy old `enabled` settings without checking deprecation warnings.

### 5.2. Spring Boot 4.x: Using `access`

In Spring Boot 4.x, configure endpoint access using `management.endpoint.<id>.access`:

~~~yaml
management:
  endpoint:
    restart:
      access: unrestricted
    pause:
      access: unrestricted
    resume:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,restart,pause,resume
~~~

Common access levels:

- `none`: the endpoint is inaccessible and may be excluded from the context.
- `read-only`: allows only read operations.
- `unrestricted`: allows all operations the endpoint provides, including write operations.

`restart`, `pause`, and `resume` are state-mutating operations and therefore require write access. `read-only` is insufficient to execute these commands.

If an application sets `management.endpoints.access.default=none`, access must be granted individually for each needed endpoint. Additionally, `management.endpoints.access.max-permitted` can cap the maximum allowed level; setting this cap to `none` prevents re-enabling an endpoint via per-endpoint configuration.

### 5.3. Expose Only Endpoints That Are Actually Needed

The example above exposes an explicit list. Avoid configuring:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

in production just for convenience. Management endpoints can reveal sensitive details or mutate application state. Limit exposure, configure a dedicated management port where appropriate, and protect with authentication/authorization.

### 5.4. Invoking Restart via HTTP POST

Default path:

~~~http
POST /actuator/restart
~~~

Example:

~~~bash
curl -X POST http://localhost:8080/actuator/restart
~~~

If the management base path or port is customized, adjust the URL accordingly. Never use `GET` for restart operations.

A successful call only confirms the request was accepted at the endpoint level. Afterward, observe startup logs, readiness, health, and dependency connections to verify the new context is ready.

## 6. `/actuator/pause` and `/actuator/resume`

### 6.1. Role of PauseHandler

Spring Cloud Context provides the `PauseHandler` abstraction so components can register pause and resume behavior. The two corresponding endpoints invoke `pause()` and `resume()` on handlers present in the context.

With Spring Integration, Spring Cloud can provide a built-in handler for components implementing `Pausable`. An application can also register custom `PauseHandler` beans to control schedulers, consumers, or internal components that support pausing/resuming.

Conceptual example:

~~~java
public interface PauseHandler {
    void pause();

    void resume();
}
~~~

This is an illustrative behavioral contract. When writing an implementation, use the exact package/API of the Spring Cloud Commons version your project uses.

### 6.2. Pause Does Not Automatically Stop the Entire Application

If an application has no matching `PauseHandler`, the pause/resume endpoints may produce no useful effect. The mere existence of the endpoints does not mean all HTTP requests, schedulers, Kafka consumers, or background workers stop automatically.

Identify explicitly which components need pausing:

- Message consumers.
- Scheduled tasks.
- Integration flows.
- Background jobs that can stop safely.
- Internal tasks requiring draining before maintenance.

Do not use pause as a substitute for readiness management or load balancer draining if those components are not integrated with corresponding handlers.

### 6.3. Dependency Relationship with RestartEndpoint

In current Spring Cloud Commons, `PauseEndpoint` and `ResumeEndpoint` are created when the `RestartEndpoint` bean is present. Consequently, when the restart endpoint is disabled, pause and resume are also disabled by this dependency relationship.

That explains why merely putting `pause,resume` in exposure settings is not enough. You must first satisfy the condition so `RestartEndpoint` is created.

### 6.4. Invoking Pause and Resume

~~~http
POST /actuator/pause
POST /actuator/resume
~~~

Example:

~~~bash
curl -X POST http://localhost:8080/actuator/pause
curl -X POST http://localhost:8080/actuator/resume
~~~

Both operations should be tested on each handler. After pausing, verify consumers or schedulers actually stop accepting new work; after resuming, verify they continue operating without duplicate or dropped messages.

### 6.5. Differences Across Release Trains

Some older Spring Cloud documentation describes pause/resume in terms of `Lifecycle.stop()` and `Lifecycle.start()` methods on `ApplicationContext`. Current Spring Cloud Commons 5.0.4 documentation describes the endpoints as invoking `pause()`/`resume()` on `PauseHandler` beans, including a handler for Spring Integration `Pausable`.

When upgrading, read the exact reference guide and Javadoc for your release train. Do not assume a handler or semantics from an older project behave identically in a newer version.

## 7. `/actuator/shutdown` in Spring Boot Actuator

### 7.1. This Endpoint Differs from Restart

`shutdown` belongs to Spring Boot Actuator. When enabled and validly invoked, the endpoint instructs the application to close the `ApplicationContext` and terminate.

Unlike restart:

- `shutdown` does not create a new context.
- The application terminates after the context closes.
- The JVM/process may exit once no components remain keeping the process alive.
- An external platform may restart the process according to its restart policy, which is the platform's responsibility.

Per Spring Boot documentation, this endpoint works only when the application is packaged/run as an executable JAR.

### 7.2. Defaults and Configuration

Spring Boot documents the shutdown endpoint as disabled by default.

In Spring Boot 3.x prior to the new access mechanism, it can be enabled with:

~~~yaml
management:
  endpoint:
    shutdown:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,shutdown
~~~

From Spring Boot 3.4 onward and in Boot 4.x, use the `access` property. Example:

~~~yaml
management:
  endpoint:
    shutdown:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,shutdown
~~~

In Boot 4.x, `management.endpoint.shutdown.access` defaults to `none`. Only change it to `unrestricted` once proper authentication, authorization, and network restrictions are in place.

### 7.3. Invoking Shutdown

~~~http
POST /actuator/shutdown
~~~

Example:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

After the request, the application begins closing the context. The HTTP connection may close while the server is stopping; do not rely on the client receiving a specific response as sole proof that the process has exited completely.

### 7.4. Graceful Shutdown

Spring Boot supports graceful shutdown for common embedded web servers. When the context closes, the server stops accepting new requests and grants in-flight requests a grace period to finish according to the configured timeout.

Example:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Graceful shutdown is a mechanism for handling requests while the application stops; it does not automatically expose `/actuator/shutdown`, nor does it enable that endpoint. Keep these two configurations distinct.

## 8. Distinguishing the Restart Endpoint from Spring Boot DevTools Restart

Spring Boot DevTools provides an automatic application restart feature in development environments when the classpath changes. This is a developer productivity feature, different from Spring Cloud Context's restart endpoint.

| Criterion | Spring Cloud `/actuator/restart` | Spring Boot DevTools restart |
| --- | --- | --- |
| Goal | Runtime context lifecycle management | Automatic restart when changes are detected during development |
| Trigger | HTTP/JMX write operation | Monitoring classpath changes or trigger files |
| Dependency | Spring Cloud Context and Actuator | `spring-boot-devtools` |
| Suitable environment | Usable in managed, secured environments | Primarily intended for development |
| Related configuration | `management.endpoint.restart.*` | `spring.devtools.restart.*` |
| Production binary changes | Does not deploy new artifacts | Not a production deployment mechanism |

Do not confuse `spring.devtools.restart.enabled=true` with `management.endpoint.restart.enabled=true`. The two properties control completely different features.

## 9. Dependencies and Runtime Conditions

### 9.1. Required Components

To use Spring Cloud Context endpoints:

- Spring Boot Actuator must be on the runtime classpath.
- Spring Cloud Context must be present through an appropriate dependency, usually pulled in by Spring Cloud starters.
- The Spring Cloud release train must be compatible with Spring Boot.
- Endpoint auto-configuration must be enabled and not excluded.
- For pause/resume, `RestartEndpoint` and appropriate handlers must be present.

Illustrative Maven dependencies example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

This snippet is a minimal illustrative example. In an application using other feature starters, Spring Cloud Context may already be in the dependency tree. Inspect `dependency:tree` and use a compatible Spring Cloud BOM instead of pinning individual module versions manually.

### 9.2. Verifying Endpoint Creation

You can use Actuator `beans` or `conditions` in a protected environment to verify auto-configuration and endpoint beans. The `mappings` endpoint can help verify whether HTTP paths have been mapped.

Do not expose `beans`, `conditions`, or `mappings` on public networks just for debugging. Use startup logs or test contexts if you do not want to open management endpoints.

## 10. Testing Lifecycle Endpoints

### 10.1. Testing Restart

An integration scenario should:

1. Start the application in a test environment with dedicated management endpoints.
2. Confirm the restart endpoint is unavailable under default settings.
3. Enable the endpoint in test configuration and expose it over HTTP.
4. Call `POST /actuator/restart`.
5. Observe context closing logs and fresh startup logs.
6. Verify readiness, recreated beans, and dependency connections.
7. Confirm PID/process is not mistakenly treated as restarted when only the context was recreated.

Do not invoke restart inside a shared test suite context that other tests still depend on. Run the test in an isolated process or manage lifecycle explicitly.

### 10.2. Testing Pause/Resume

Create a `PauseHandler` with a counter or an integration component whose state can be observed:

- After `POST /actuator/pause`, the handler receives one pause command.
- The controlled component stops accepting new work.
- After `POST /actuator/resume`, the handler resumes operation.
- Calling pause/resume multiple times does not produce invalid state or resource leaks.
- When no handler exists, tests should reflect that the endpoint does not control any business component.

### 10.3. Testing Shutdown

The shutdown endpoint should be tested in a standalone process:

1. Launch the executable JAR with the shutdown endpoint enabled and exposed.
2. Send `POST /actuator/shutdown`.
3. Verify the context closes, resource callbacks run, and the process terminates.
4. Verify graceful shutdown obeys the configured timeout.
5. Verify whether the process supervisor restarts or does not restart the process per policy.

Do not run shutdown tests inside the same JVM orchestrating the entire test suite.

### 10.4. Testing Unexposed Endpoints

If an endpoint exists but is not exposed over HTTP, HTTP requests cannot reach it. Tests should verify all three states:

- Endpoint disabled or access `none`.
- Endpoint available but omitted from `web.exposure.include`.
- Endpoint available, exposed, and authorized.

This prevents tests from merely asserting an HTTP response without knowing which condition produced it.

## 11. Securing Management Endpoints

Restart, pause, resume, and shutdown can disrupt business operations or alter system state. They must be treated as sensitive administrative APIs.

Recommendations:

- Expose only genuinely necessary endpoints.
- Use dedicated authentication and operator roles.
- Restrict the management port to the administrative network.
- Use TLS when accessing over a network.
- Do not grant restart/shutdown permissions to ordinary service accounts.
- Audit the caller, timestamp, endpoint, and target instance.
- Never expose all of Actuator with a wildcard.
- Separate dev, staging, and production networks and credentials.
- Test access controls in pipelines so production configurations do not accidentally leave endpoints open.

If Spring Security is present, inspect custom `SecurityFilterChain` beans. An application-defined security configuration can override default Actuator rules; ensure write operations are restricted to authorized administrative roles.

## 12. Impact in Multi-Instance Systems

### 12.1. Endpoints Affect Only the Receiving Instance

Each replica runs its own JVM and `ApplicationContext`. Calling restart or pause on one replica does not automatically apply to other replicas.

If multiple instances must be restarted, use orchestration rollouts or deployment management tools. If an instance must be shut down, coordinate with the load balancer to stop routing traffic before the process exits.

### 12.2. Restarting Multiple Replicas Simultaneously Can Cause Outages

Restarting all replicas at once can leave the service with zero available instances. A safer workflow is typically:

1. Select one instance or a small batch.
2. Drain traffic from that group.
3. Perform the planned restart/shutdown.
4. Wait for readiness and health checks to pass.
5. Proceed to the next batch.
6. Halt the rollout if error rates or latency exceed thresholds.

The restart endpoint does not replace rolling deployments and does not provide automatic orchestration.

### 12.3. Service Discovery and Registration State

If the application registers with Eureka, Consul, or another registry, inspect the registration/deregistration lifecycle when the context stops and restarts. Do not assume the registry always removes the old instance instantaneously or that all consumers update their lists immediately.

Observe:

- Is the instance deregistered or marked unavailable when stopping?
- Does the new instance re-register after restart?
- Do health checks and leases/heartbeats recover?
- Does the load balancer continue sending requests to the restarting instance?

These behaviors depend on the discovery provider, service registry, and health/lifecycle configuration.

## 13. Common Pitfalls

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| `404` on `/actuator/restart` | Endpoint not created or not exposed | Check Spring Cloud Context, enable/access settings, and exposure |
| Restart still unavailable despite exposure | Endpoint is disabled by default | Enable the endpoint using the property matching your Boot version |
| Pause/resume do not appear | `RestartEndpoint` not created or child endpoints unavailable | Check restart access and bean conditions |
| Pause returns success but worker keeps running | No `PauseHandler` controls that worker | Check handlers and integration components |
| Using `GET` returns `405` | Endpoint is a write operation | Use `POST` |
| Shutdown returns `404` | Shutdown endpoint disabled or missing at runtime | Check Actuator, access/enabled, and executable JAR |
| Shutdown unreachable despite exposure | Boot 4 defaults `shutdown.access=none` or security blocks it | Grant appropriate access and check authorization |
| Restart causes request failures | Bean reinitialization fails or dependencies not ready | Inspect startup logs, health, and lifecycle callbacks |
| Restarting one replica still causes service errors | Load balancer still routes traffic or remaining replicas lack capacity | Drain traffic and roll out in batches |
| Old endpoint configuration has no effect | Using `enabled` on a version that moved to the access model | Read property metadata for your Boot version |
| Shutdown endpoint does not terminate process as expected | Not running as executable JAR or external supervisor manages process | Check packaging and runtime environment |

## 14. Procedure for Verifying Endpoints in a Project

When a lifecycle endpoint does not work, check in order:

1. Confirm the active Spring Boot and Spring Cloud release train.
2. Confirm Actuator and Spring Cloud Context are on the runtime classpath.
3. Verify the endpoint is auto-configured and the corresponding bean exists.
4. Check enable/access properties matching the Boot generation.
5. Check `management.endpoints.web.exposure.include` and `exclude`.
6. Check the management port, base path, and network binding.
7. Check HTTP method (`POST`) and Spring Security rules.
8. Verify the endpoint has actual handlers/lifecycle components to control.
9. Inspect logs, health, and instance state after execution.

You can use dependency inspection commands:

~~~bash
# Maven: check whether Spring Cloud Context and Actuator are in the runtime tree
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-context,org.springframework.boot:spring-boot-actuator

# Gradle: inspect runtime dependencies
./gradlew dependencies --configuration runtimeClasspath
~~~

Cross-check results against the application's BOM and release train.

## 15. Practice Exercises

**Exercise 1 — Endpoint defaults.** Create an application with Actuator and Spring Cloud Context. Keep default settings and inspect `/actuator/restart`, `/actuator/pause`, `/actuator/resume`, and `/actuator/shutdown`. Note which endpoints are not created, which are unexposed, and why.

**Exercise 2 — Enabling restart.** For Spring Boot 3.x, configure `management.endpoint.restart.enabled=true`. For Boot 4.x, use `management.endpoint.restart.access=unrestricted`. Expose the endpoint and verify `POST /actuator/restart` restarts the context.

**Exercise 3 — PauseHandler.** Create a handler for a simulated worker. Call pause and resume, inspect worker state, and handle repeated invocations.

**Exercise 4 — Shutdown.** Enable the shutdown endpoint in a test executable JAR. Send POST, verify the context closes and the process terminates. Compare with stopping the process via SIGTERM.

**Exercise 5 — Graceful shutdown.** Configure a shutdown phase timeout. Send a long-running request, trigger shutdown, and observe the in-flight request, new requests, and process exit timing.

**Exercise 6 — Security.** Create an `OPS_ADMIN` role permitted solely to invoke lifecycle endpoints. Confirm users without the role receive `403` and the health endpoint continues working per policy.

**Exercise 7 — Multiple replicas.** Run two instances of the same service. Restart one instance and observe the other instance, service discovery, load balancer, and readiness. Design a rollout that avoids losing total capacity.

**Exercise 8 — Version comparison.** Run the same sample on Spring Boot 3.x and 4.x. Compare `enabled` versus `access`, default exposure, and shutdown endpoint handling.

## 16. Key Takeaways and References

- `/actuator/restart` belongs to Spring Cloud Context and is disabled by default in current Spring Cloud Commons documentation.
- `/actuator/pause` and `/actuator/resume` depend on `RestartEndpoint`; they invoke registered `PauseHandler` beans.
- Pause/resume do not automatically stop the entire web server or every worker in the application.
- `/actuator/shutdown` belongs to Spring Boot Actuator, is disabled by default, and supports only executable JARs.
- Older Boot 3.x uses `management.endpoint.<id>.enabled`; Boot 3.4+ and Boot 4.x transition to `management.endpoint.<id>.access`.
- Endpoint implementation, enable/access status, exposure, and invocation authorization are separate conditions.
- State-changing operations require HTTP `POST` and appropriate administrative privileges.
- Context restart does not restart the JVM, does not deploy new artifacts, and does not automatically affect other replicas.
- Graceful shutdown is a controlled request-draining mechanism; it does not automatically enable the Actuator shutdown endpoint.
- When operating multiple instances, drain traffic, verify discovery/readiness, and roll out in batches.

Official references to check against your version:

1. [Spring Cloud Commons – Application Context Services and Endpoints](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – RestartEndpointAutoConfiguration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshEndpointAutoConfiguration.java)
3. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
4. [Spring Boot Reference – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
5. [Spring Boot Reference – Developer Tools Restart](https://docs.spring.io/spring-boot/reference/using/devtools.html)
6. [Spring Boot API – Endpoint Access](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/PropertiesEndpointAccessResolver.html)
7. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
