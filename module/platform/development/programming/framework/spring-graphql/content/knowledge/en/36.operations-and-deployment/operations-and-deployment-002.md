# GraphQL endpoint readiness

A Spring for GraphQL application should only accept traffic once the HTTP server has started, the GraphQL schema has been loaded, and the required components for serving requests are ready. In container environments, Kubernetes needs to know when to route requests to a pod, when to restart the process, and when to wait for the application to finish starting up.

These three states are related but not identical. Liveness indicates that the process is still running and not stuck to the point of needing a restart. Readiness indicates whether the instance can accept traffic at the current moment. The startup probe tells Kubernetes whether the application has passed its initial startup phase.

Spring Boot Actuator provides health endpoints and health groups for readiness/liveness. Spring for GraphQL provides the GraphQL endpoint and schema execution runtime. Combining the two helps deploy a GraphQL service with clear health checks, avoid adding unready pods to a load balancer, and handle orderly shutdowns.

## 1. Distinguishing the GraphQL endpoint and health endpoints

The GraphQL endpoint is where clients send GraphQL operations, typically at the `/graphql` path. Health endpoints are where the operations platform checks application status, typically provided by Spring Boot Actuator.

Examples:

| Endpoint | Purpose | Typical callers |
| --- | --- | --- |
| `/graphql` | Execute queries, mutations, or subscription transport | Web/mobile clients, other services |
| `/actuator/health` | Overall health status | Operators, monitoring |
| `/actuator/health/liveness` | Check whether the process is still alive | Kubernetes liveness probe |
| `/actuator/health/readiness` | Check whether the instance can accept traffic | Kubernetes readiness probe |
| `/livez` | Liveness probe on the application port | Kubernetes |
| `/readyz` | Readiness probe on the application port | Kubernetes |

Do not configure Kubernetes to call `/graphql` directly to check readiness. GraphQL HTTP transport is typically invoked with POST and may also support GET for queries depending on configuration; however, kubelet only sends an HTTP GET to the path without a valid GraphQL document and variables. That request may be rejected or return a transport error even when the application is healthy.

Even when sending a valid query, HTTP status does not always reflect business outcomes. GraphQL can return HTTP 200 alongside an `errors` field when a field resolver fails during execution. Therefore, health probes should call dedicated health endpoints; verifying actual GraphQL functionality should be a separate synthetic test.

## 2. The three states: startup, liveness, and readiness

**Startup** answers the question: has the application completed its initial startup phase? While startup has not completed, Kubernetes does not yet need to evaluate liveness/readiness on the regular cycle. Startup probes are useful for applications that take time to load large schemas, initialize caches, or run warm-up tasks.

**Liveness** answers the question: is the process still capable of running? If liveness fails repeatedly, Kubernetes may restart the container. Do not include databases or external services in liveness because a transient dependency outage could cause all pods to restart at the same time.

**Readiness** answers the question: can the instance accept new requests? If readiness fails, Kubernetes removes the pod from traffic-serving endpoints. The container keeps running so the application has a chance to recover.

You can visualize the lifecycle as follows:

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Startup completed
    Ready --> NotReady: Required dependency unavailable
    NotReady --> Ready: Dependency recovered
    Ready --> Stopping: Termination begins
    NotReady --> Stopping: Termination begins
    Stopping --> [*]
~~~

A `NotReady` pod does not necessarily need a restart. For example, if a database briefly loses connectivity: readiness can transition to DOWN to stop receiving requests, while liveness remains UP so the process waits for the connection to recover.

## 3. When does GraphQL schema readiness take shape?

With the Spring Boot GraphQL starter, Spring Boot creates `GraphQlSource` from the schema SDL and runtime wiring. Application initialization includes reading the schema, parsing, validating, and building the corresponding runtime.

An invalid schema, incorrect type reference, or uninitializable runtime wiring configuration typically causes application context startup to fail. In that case, the web server should not be considered ready to receive GraphQL traffic.

High-level steps:

~~~mermaid
flowchart TD
    A[Load application configuration] --> B[Create GraphQlSource]
    B --> C[Load SDL resources]
    C --> D[Parse and validate schema]
    D --> E[Apply RuntimeWiringConfigurer]
    E --> F[Create GraphQL runtime]
    F --> G[Start web server]
    G --> H[ApplicationReadyEvent]
    H --> I[Readiness becomes accepting traffic]
~~~

Spring Boot's readiness health group uses the application availability state. Only when the application has completed startup and transitioned to accepting traffic does the readiness health indicator reflect a ready state.

Note: successful schema initialization does not prove that every resolver works properly with the database, remote services, or real data. Readiness should also verify essential dependencies; integration tests and synthetic GraphQL probes should verify operation behavior.

## 4. Adding Spring Boot Actuator

The application needs the GraphQL starter and Actuator. Gradle example:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")

    // Add the database driver and data-access starter used by the application.
}
~~~

The GraphQL starter provides the endpoint and execution runtime. Actuator provides the health infrastructure, health indicators, and health endpoints.

If the application uses JDBC or JPA, the `db` health indicator can be auto-configured when matching database components are on the classpath. If there is no datasource, do not add `db` to the readiness group. If the service uses other dependencies like Redis or a catalog service, decide whether that dependency is truly required to process requests before adding the corresponding health indicator.

## 5. Configuring GraphQL and health probes

Example configuration in `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  graphql:
    path: /graphql

management:
  endpoints:
    web:
      exposure:
        include: health,info

  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Key settings:

- `spring.graphql.path` sets the GraphQL HTTP endpoint path.
- `management.endpoints.web.exposure.include` exposes only selected Actuator endpoints over HTTP.
- `management.endpoint.health.probes.enabled` enables health groups for liveness and readiness.
- `management.endpoint.health.probes.add-additional-paths` adds `/livez` and `/readyz` on the application's main HTTP port.
- `liveness.include` contains only `livenessState`.
- `readiness.include` contains `readinessState` and `db` in this example with an essential database.
- `show-details: never` avoids exposing unnecessary health details.

If the application does not use a database, the readiness group can consist solely of `readinessState`. If there are other mandatory dependencies, add their corresponding health indicators after evaluating timeouts and behavior when the dependency loses connectivity.

The default health group names and paths are `/actuator/health/liveness` and `/actuator/health/readiness`. When additional paths are enabled, `/livez` and `/readyz` allow kubelet to call probes on the same application port serving GraphQL.

Do not put `db` in the liveness group. Temporary database unavailability does not mean the process needs to restart.

## 6. Should the database be included in readiness?

The answer depends on the ability to serve requests when the database loses connectivity.

If almost every query/mutation requires the database, the pod cannot process useful requests when the database is DOWN. Including `db` in readiness stops sending new traffic to that instance.

If the GraphQL service can continue serving most requests via cache or independent data, including the database in readiness can cause pods to be removed from traffic even though they can still serve some operations. In that case, you can use only `readinessState` for the basic probe and monitor the database with a separate alert; or design readiness indicators around truly mandatory dependencies.

Do not include all external services in readiness by default. A failing auxiliary dependency can take down the entire GraphQL API's availability even though operations that do not depend on it can still run.

Also control health check frequency. Health indicators should have short timeouts, avoid heavy queries, and avoid adding significant load to dependencies during an incident.

## 7. Health indicator for an essential dependency

If the application has a dependency not supported automatically by Actuator, you can create a custom `HealthIndicator`.

Example where a catalog service is required for search queries:

~~~java
package com.example.catalog.health;

import com.example.catalog.client.CatalogClient;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalog")
public class CatalogHealthIndicator implements HealthIndicator {

    private final CatalogClient catalogClient;

    public CatalogHealthIndicator(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @Override
    public Health health() {
        boolean available = catalogClient.isAvailable();

        if (available) {
            return Health.up().build();
        }

        return Health.down()
            .withDetail("dependency", "catalog")
            .build();
    }
}
~~~

Then add `catalog` to the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,catalog
~~~

This snippet only illustrates the structure. In practice, `isAvailable()` must have a bounded timeout and avoid prolonged retries. For reactive clients, use `ReactiveHealthIndicator` and bound the publisher duration instead of blocking the event loop.

Do not put internal URLs, credentials, stack traces, or sensitive connection details into health details. Health endpoints may be accessed by multiple monitoring systems; provide only enough information for operators to triage the incident.

## 8. Dedicated management port and additional probe paths

Some systems place Actuator on a separate port:

~~~yaml
management:
  server:
    port: 8081
~~~

If kubelet checks readiness on a separate management port, the probe can report UP while the main port serving GraphQL fails to bind or has issues in the main web server.

Spring Boot has an option for additional probe paths to expose `/livez` and `/readyz` on the main server port. This is a good choice when you want health probes to verify that the exact web server receiving GraphQL traffic is functioning.

If using a separate management port, consider:

- Which port internal probes need to call.
- Whether network policies allow kubelet to reach that port.
- Whether the main port needs additional paths.
- Whether health endpoints are appropriately protected and exposure-limited.

Do not expose all Actuator endpoints to the Internet just so Kubernetes can read health. Only expose `health` (and `info` if needed), then restrict access using network policies, firewalls, or Spring Security.

## 9. Configuring Kubernetes startup, liveness, and readiness probes

Example deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-graphql
spec:
  replicas: 3
  selector:
    matchLabels:
      app: spring-graphql
  template:
    metadata:
      labels:
        app: spring-graphql
    spec:
      containers:
        - name: spring-graphql
          image: example/spring-graphql:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Meaning:

- `startupProbe` allows the application up to roughly 150 seconds to pass the startup phase per this example configuration. During this window, Kubernetes does not yet use liveness/readiness to conclude that the container needs restarting or can receive traffic.
- `livenessProbe` checks the process periodically. If it fails consecutively up to the threshold, Kubernetes restarts the container.
- `readinessProbe` checks the ability to receive traffic. When it fails, the pod is removed from Service endpoints until it recovers.

The numbers are only examples. Choose `periodSeconds`, `timeoutSeconds`, and `failureThreshold` based on startup duration, health check latency, and system recovery characteristics. Too low a timeout can cause false negatives when a node is under heavy load.

## 10. Readiness does not replace synthetic GraphQL tests

Health endpoints verify application state and configured dependencies. They do not prove that a specific GraphQL operation returns correct data.

A synthetic test can send a read-only query to the GraphQL endpoint on a schedule:

~~~graphql
query ReadinessCheck {
    serviceStatus {
        status
    }
}
~~~

For example, the `serviceStatus` field must be specifically designed for functional checking, have stable semantics, and not mutate data. Do not add a dummy health field just to return the string `OK` without checking any critical component.

A synthetic test should verify:

- The HTTP endpoint accepts requests.
- Authentication or client credentials work.
- The GraphQL document is validated and executed.
- Key resolvers can reach required dependencies.
- The response has the expected shape and values.

Synthetic tests can run from a monitoring system or deployment smoke tests. Do not use queries with side effects as Kubernetes readiness probes because probes run repeatedly and can create unwanted data.

## 11. Verifying the GraphQL endpoint and health endpoints

You can verify manually after deployment:

~~~bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query { books { id title } }"}'
~~~

Both health endpoints typically return HTTP status 200 when UP and a non-success status when DOWN. The GraphQL endpoint requires a document and payload matching the application's schema.

If using `/actuator/health/readiness` instead of the additional path, call that exact Actuator path. Do not infer readiness solely from `/graphql` returning HTTP 200; inspect the body and GraphQL errors when running synthetic tests.

When authentication is enabled for GraphQL, synthetic tests must use appropriate credentials. Kubernetes health probes should generally not require user tokens; therefore, health endpoints need a separate, secure, and simple internal access policy.

## 12. Testing the readiness health group

Health endpoints can be verified with integration tests. Example using MockMvc:

~~~java
package com.example.graphql.health;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReadinessEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readinessEndpointIsAvailableAfterStartup() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
            .andExpect(status().isOk());
    }
}
~~~

This test assumes the application exposes the Actuator health endpoint and the readiness group is UP. If the configuration only exposes additional paths on the main server or a separate management server port, verify the corresponding endpoint in that integration setup.

Besides the health endpoint, add a GraphQL runtime test:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GraphQlRuntimeTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void schemaCanExecuteARepresentativeQuery() {
        GraphQlTester tester =
            ExecutionGraphQlServiceTester.create(graphQlService);

        tester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .verify();
    }
}
~~~

The second test confirms that the schema and resolvers can execute a representative operation. It does not replace runtime health probes, but catches wiring or schema contract errors before release.

## 13. Graceful shutdown and stopping traffic

Readiness is also important when pods are newly deployed or terminated. When the application begins shutting down, it needs to stop accepting new requests and give in-flight requests time to complete.

Spring Boot configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

With graceful shutdown, the web server stops accepting new connections and waits for in-flight requests during the configured timeout. Kubernetes also needs a `terminationGracePeriodSeconds` long enough for traffic draining and shutdown to complete.

Example:

~~~yaml
spec:
  terminationGracePeriodSeconds: 40
~~~

The value here is only illustrative; set it larger than the total time needed for the load balancer to update endpoints, in-flight requests to finish, and Spring to complete shutdown.

Subscriptions over WebSocket or long-lived streams have a different lifecycle from short HTTP requests. When deploying, you need a client reconnect policy, session duration limits, or a reconnect notification mechanism if the system requires zero interruption.

Do not rely on readiness to guarantee that all in-flight requests have finished. Readiness prevents new traffic from being routed to the pod; graceful shutdown manages completing existing requests.

## 14. Readiness during warm-up or unavailable dependencies

Some GraphQL services need to warm up caches, load metadata, or sync schemas from another system before accepting traffic. If this work runs synchronously during the startup lifecycle, the application only transitions to accepting traffic after startup finishes.

If warm-up runs asynchronously after the application is already ready, the availability state must be managed explicitly. Spring Boot provides `ApplicationAvailability` and `AvailabilityChangeEvent` to transition readiness states.

Example component actively refusing traffic during warm-up:

~~~java
package com.example.graphql.startup;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmup {

    private final ApplicationContext applicationContext;
    private final CatalogCache catalogCache;

    public CatalogWarmup(
            ApplicationContext applicationContext,
            CatalogCache catalogCache) {
        this.applicationContext = applicationContext;
        this.catalogCache = catalogCache;
    }

    public void refresh() {
        AvailabilityChangeEvent.publish(
            applicationContext,
            ReadinessState.REFUSING_TRAFFIC
        );

        try {
            catalogCache.loadRequiredEntries();

            AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC
            );
        } catch (RuntimeException exception) {
            // Keep the instance out of traffic and report the failure.
            throw exception;
        }
    }
}
~~~

This example illustrates the availability mechanism; where `refresh()` is called must be designed around the application's lifecycle. Do not transition to `ACCEPTING_TRAFFIC` if mandatory steps have not succeeded. If warm-up fails, readiness remains DOWN so operators can intervene.

Do not use the readiness state as an arbitrary toggle for individual queries. It is an instance-wide state. If only an auxiliary feature temporarily fails while the API can still serve other operations, consider returning controlled errors on the affected operation and keeping the instance ready.

## 15. Protecting health endpoints

Health endpoints can leak information about databases, dependencies, and internal structure if `show-details` is enabled too broadly.

Guidelines:

- Expose only the health endpoints needed for probes and monitoring.
- Keep `show-details: never` or only show details to authenticated operators.
- Do not return internal hostnames, connection strings, credentials, or exception messages.
- Use network policies or firewalls to restrict probe caller sources.
- If using Spring Security, configure access rules for health endpoints separately from the GraphQL endpoint.
- Do not expose all Actuator endpoints to the Internet.

When using a dedicated management port, protect that port as well and review network policies. The endpoint not being on the GraphQL port does not mean it is automatically secure.

## 16. Common readiness configuration pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Pod never becomes Ready | Readiness group contains a DOWN indicator | Inspect each indicator and dependency |
| Pod restarts continuously when the database fails | Database was placed in liveness | Move the dependency check to readiness |
| `/readyz` returns 404 | Additional paths or probes are not enabled | Check Actuator configuration and correct port |
| `/graphql` returns 405 on probe | Kubelet sends GET to the GraphQL endpoint | Use a dedicated health endpoint |
| Health is UP, yet GraphQL queries fail | Schema/runtime initializes, yet resolvers or dependencies fail | Add integration tests and synthetic queries |
| Health endpoint leaks internal details | `show-details`/exposure is too broad | Restrict exposure and access permissions |
| Pod is removed from traffic when an auxiliary dependency fails | Readiness includes too many dependencies | Include only truly essential dependencies |
| Deploy drops subscriptions | WebSocket sessions outlive the shutdown window | Design reconnect and drain policies |
| Probe times out under high load | Health indicator calls a slow dependency | Bound timeouts and optimize health checks |

## 17. Pre-deployment checklist

- Are the GraphQL endpoint path and transport clearly configured?
- Are schema SDL and runtime wiring verified during startup?
- Has Actuator been added and does it expose only necessary endpoints?
- Does liveness reflect only process survivability?
- Does readiness reflect accepting-traffic status and truly essential dependencies?
- Do databases or remote services have bounded timeouts when checked?
- Do Kubernetes startup, liveness, and readiness probes use the right paths and ports?
- Are additional probe paths enabled if the management server uses a separate port?
- Do health details avoid exposing sensitive information?
- Are there synthetic tests verifying critical GraphQL operations?
- Are graceful shutdown and termination grace period sufficient for in-flight requests?
- Do WebSocket subscriptions have a reconnect policy during deployments?
- Are there dashboards/alerts for readiness, liveness, GraphQL error rate, and latency?

A GraphQL endpoint is ready when the schema/runtime has initialized, the web server can receive requests, and the instance's mandatory dependencies are operating. Use Actuator readiness to route traffic, liveness to detect processes needing restart, and startup probes to protect the startup phase. Verify GraphQL operations with integration tests or separate synthetic probes; combine with graceful shutdown so deployments can stop accepting new requests while allowing current requests to complete.

## References

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — GraphQL Support](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
