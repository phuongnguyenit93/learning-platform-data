# Bootstrapping a Java Application and Exposing Health Endpoints

## Lesson Objectives

After this lesson, you will be able to:

- Initialize a Java application using Spring Boot and package it as a JAR.
- Create a simple business endpoint to verify that the application can accept requests.
- Integrate Spring Boot Actuator and expose the health endpoint over HTTP.
- Distinguish between liveness, readiness, and startup states to configure appropriate checks.
- Package the application into a container, configuring ports and environment variables.
- Connect the health endpoint to Kubernetes probes or container platform health checks.
- Verify application behavior during startup, readiness, failure, and shutdown.

## 1. Bootstrapping a Java Application in a Cloud Environment

Bootstrapping is the step of creating the application structure, choosing the runtime and dependencies, setting up startup configuration, and confirming that the application can run in the target environment. For cloud workloads, the application needs to start consistently, accept configuration from the deployment environment, write logs to stdout/stderr, and provide health signals so the orchestration platform knows when to route traffic to it.

This lab uses Java 21 and Spring Boot. Spring Boot auto-configures most web components, manages dependencies, and provides the Actuator mechanism for health endpoints. You can use any supported Spring Boot version compatible with your organization's JDK; let Spring Initializr or the project's parent/BOM manage dependency versions consistently.

A minimal application can be generated with Spring Initializr using the following choices:

| Attribute | Suggested value |
|---|---|
| Project | Maven |
| Language | Java |
| Java | 21 |
| Packaging | Jar |
| Dependencies | Spring Web, Spring Boot Actuator |
| Group | **com.example** |
| Artifact | **cloud-api** |
| Package | **com.example.cloudapi** |

If your organization has a project template or dependency catalog, prioritize that standard configuration to align Java version, Spring Boot version, plugins, and security rules.

### 1.1. Directory Structure

A minimal Maven structure:

    cloud-api/
    ├── mvnw
    ├── mvnw.cmd
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/com/example/cloudapi/
        │   │   ├── CloudApiApplication.java
        │   │   └── HealthDemoController.java
        │   └── resources/
        │       └── application.yml
        └── test/
            └── java/com/example/cloudapi/

The Maven Wrapper (mvnw or mvnw.cmd) ensures the development team and CI pipelines use the same Maven version without depending on a locally pre-installed Maven. Commit the wrapper and project configuration files according to repository conventions.

### 1.2. Required Dependencies

In **pom.xml**, the application needs the Spring Boot web starter and Actuator. Example dependencies section:

    <dependencies>
      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
      </dependency>

      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
      </dependency>

      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
      </dependency>
    </dependencies>

The parent or dependency management section must use a Spring Boot BOM compatible with the chosen Java version. Spring Initializr generates this configuration automatically. Do not manually pin individual versions for starters belonging to the same Spring Boot release train, as this can cause dependency mismatches.

## 2. Creating the Entry Point and Business Endpoint

The entry-point class marks the root package so Spring scans components, configurations, and controllers.

    package com.example.cloudapi;

    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;

    @SpringBootApplication
    public class CloudApiApplication {
        public static void main(String[] args) {
            SpringApplication.run(CloudApiApplication.class, args);
        }
    }

**@SpringBootApplication** combines auto-configuration, component scanning, and bean configuration. Place this class in the root package so controllers, services, and sub-configurations fall within the scan scope.

Create a simple business endpoint to distinguish between the application accepting requests and the health endpoint:

    package com.example.cloudapi;

    import java.util.Map;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    public class HealthDemoController {
        @GetMapping("/api/hello")
        public Map<String, String> hello() {
            return Map.of(
                "service", "cloud-api",
                "message", "Application is running"
            );
        }
    }

The **/api/hello** endpoint verifies that the HTTP flow and controller work. It does not replace the health endpoint: a business request can fail due to data or permissions while the process is still alive; conversely, a responding endpoint does not guarantee that all critical dependencies are ready.

## 3. Configuring the Application and HTTP Port

Create **src/main/resources/application.yml**:

    spring:
      application:
        name: cloud-api
      lifecycle:
        timeout-per-shutdown-phase: 20s

    server:
      port: 8080
      shutdown: graceful

    management:
      endpoints:
        web:
          exposure:
            include: health
      endpoint:
        health:
          show-details: never
          probes:
            enabled: true

Key configurations:

- **spring.application.name** sets the service name so logs, metrics, and observability systems can identify the application.
- **server.port** sets the default port to 8080. Spring Boot can accept an override via the **SERVER_PORT** environment variable.
- **server.shutdown: graceful** allows Spring Boot to stop accepting new requests and wait for in-flight requests within the configured timeout.
- **timeout-per-shutdown-phase** sets the limit for each shutdown phase.
- **management.endpoints.web.exposure.include: health** exposes only the health endpoint over the web.
- **management.endpoint.health.show-details: never** prevents returning internal details to unauthorized requests.
- **management.endpoint.health.probes.enabled: true** enables health groups for liveness and readiness.

Expose only the endpoints that are actually needed. Do not use **include: "*"** in production without evaluating access permissions, because Actuator can expose environment information and administrative operations. Never include secrets, tokens, connection strings, or personal data in health responses.

A separate management port can be configured using **management.server.port**, but you must consider network paths and probes. If the health endpoint runs on a separate port, probes might succeed even while the main application port is not receiving traffic. For simple container workloads, using the same port typically helps verify the application's actual ability to serve traffic.

## 4. Exposing the Health Endpoint with Spring Boot Actuator

Spring Boot Actuator provides the **/actuator/health** endpoint. When the application starts, Actuator aggregates configured health contributors and returns an overall status.

After running the application, call:

    curl -i http://localhost:8080/actuator/health

A successful response typically looks like:

    HTTP/1.1 200
    Content-Type: application/vnd.spring-boot.actuator.v3+json

    {
      "status": "UP"
    }

Common statuses:

| Status | Meaning |
|---|---|
| **UP** | The checked component is operating normally |
| **DOWN** | The component is not operating or fails conditions |
| **OUT_OF_SERVICE** | The component is temporarily out of service |
| **UNKNOWN** | Status cannot be determined |

Typically, **UP** returns HTTP 200; **DOWN** or **OUT_OF_SERVICE** returns HTTP 503. Clients and orchestration platforms should rely on both the HTTP status code and the status payload, rather than only checking whether the server returns JSON.

A health endpoint is an operational signal, not a business endpoint. It should be fast, time-bounded, and avoid executing heavy queries on every call. A slow health check can cause the platform to mistakenly conclude that the application is unhealthy.

## 5. Distinguishing Liveness, Readiness, and Startup

The three check types answer three different questions:

| Type | Question | When it fails |
|---|---|---|
| Startup | Has the application finished starting up? | Platform keeps waiting within limits; restarts if the limit is exceeded |
| Liveness | Is the process still alive and able to continue running? | Platform may restart the instance/container |
| Readiness | Is the instance ready to receive traffic? | Platform stops routing traffic to that instance |

### 5.1. Liveness

Liveness indicates whether the process is still capable of operating or has entered an unrecoverable state, such as a deadlock or a loop preventing the application from making progress. If liveness fails repeatedly, Kubernetes may restart the container.

Do not include databases, message brokers, or external APIs in liveness checks. When a database is temporarily down, restarting all Pods will not fix the database; it can overload the system further when Pods restart and reopen connections simultaneously. Liveness should focus on the internal state of the application.

Spring Boot provides **/actuator/health/liveness** when probes are enabled. This endpoint typically reflects **livenessState**.

### 5.2. Readiness

Readiness indicates whether the instance can accept new requests. An application might be running but not ready because it is warming up caches, loading configuration, completing required migrations, or missing a mandatory dependency.

Spring Boot provides **/actuator/health/readiness**. This endpoint reflects **readinessState** and can be extended with appropriate health contributors.

Only add a dependency to readiness when that dependency is genuinely required for core functionality. If every secondary dependency such as email or analytics is placed in readiness, a minor outage could stop the entire API from receiving traffic even though core business operations can still be served.

### 5.3. Startup Probe

A startup probe is useful for slow-starting applications. While the startup probe has not yet succeeded, Kubernetes holds off on running liveness and readiness probes. This avoids restarting an application merely because its startup time exceeds the liveness probe's **initialDelaySeconds**.

The startup probe should have a threshold sufficient for the p95/p99 startup time plus a buffer. Do not set the threshold too high, as a genuinely hung application will take much longer to be detected.

### 5.4. Health Groups and Probe Paths

With **management.endpoint.health.probes.enabled=true**, Spring Boot exposes:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

These endpoints allow the platform to check each purpose separately. Do not use the overall **/actuator/health** for both liveness and readiness if the health group includes external dependencies; a dependency failure could trigger unnecessary restarts.

If you want probes to go through the main application port when using a separate management port, consider **management.endpoint.health.probes.add-additional-paths=true** on supported Spring Boot versions. Check your exact version and verify the actual endpoints before configuring probes.

## 6. Adding a Health Indicator for Critical Dependencies

Actuator can aggregate health contributors from supported integrations. For custom dependencies, you can implement a **HealthIndicator**. Only include a dependency in readiness if the service cannot perform its core function when that dependency is unavailable.

Illustrative example:

    package com.example.cloudapi;

    import org.springframework.boot.actuate.health.Health;
    import org.springframework.boot.actuate.health.HealthIndicator;
    import org.springframework.stereotype.Component;

    @Component("storage")
    public class StorageHealthIndicator implements HealthIndicator {
        private final StorageClient storageClient;

        public StorageHealthIndicator(StorageClient storageClient) {
            this.storageClient = storageClient;
        }

        @Override
        public Health health() {
            try {
                storageClient.pingWithTimeout();
                return Health.up().build();
            } catch (Exception ex) {
                return Health.down()
                    .withDetail("dependency", "storage_unavailable")
                    .build();
            }
        }
    }

**StorageClient** is an application-provided client; the ping method must have a short timeout, limited retries, and avoid fetching large payloads. Do not expose exception messages, internal hostnames, credentials, or configuration details in public responses.

You can add the **storage** contributor to the readiness group:

    management:
      endpoint:
        health:
          group:
            readiness:
              include: readinessState,storage

The contributor name depends on the bean name and Actuator configuration. Verify the actual response after startup. If storage only supports an optional feature, do not put it into overall readiness; instead, monitor it separately and degrade the related feature gracefully.

## 7. Securing the Health Endpoint

The health endpoint may be called by load balancers or kubelet, but it should not inadvertently become a channel leaking internal information.

Principles:

- Only expose **health** over the web unless there is a clear need for other endpoints.
- Keep **show-details** and **show-components** non-public; display them only to authorized users if truly needed.
- Never return secrets, internal hostnames, connection strings, exception stacks, or customer data.
- Use network policies, firewalls, or management networks to restrict access sources if supported by the platform.
- If using Spring Security, configure access for health endpoints to match the deployment model: internal probes are allowed, while details are restricted to authenticated operators.
- Do not use the health endpoint as a substitute for authentication or authorization on business APIs.

Security configurations must preserve access for the platform's probes. If the endpoint requires login but kubelet or the load balancer lacks credentials, all probes will fail even when the application is healthy. You can allow internal access to health paths while restricting network access and hiding details.

## 8. Packaging the Application as a Container

After verifying that the JAR runs, create a multi-stage Dockerfile or build the JAR in a pipeline. Example runtime image:

    FROM eclipse-temurin:21-jre
    WORKDIR /app
    COPY target/cloud-api-*.jar app.jar
    USER 10001:10001
    EXPOSE 8080
    ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]

Points to note:

- Use a JRE runtime if a compiler is not needed in the final image.
- Pin images by tag/version or digest according to your organization's supply chain policy.
- Run under a non-root UID.
- Do not copy configuration files containing secrets into the image.
- Use **.dockerignore** to exclude old **target** directories, **.git**, IDE metadata, and unnecessary files from the build context.
- Write logs to stdout/stderr for platform collection.
- Set memory requests/limits aligned with JVM heap and overhead.

Example **.dockerignore**:

    .git
    .idea
    .vscode
    *.iml
    .env
    logs/
    target/

If the pipeline builds the JAR beforehand, ensure **target/cloud-api-*.jar** matches only a single artifact of the right version. For multi-module projects, use an explicit artifact path and name rather than a wildcard that might pick the wrong JAR.

Build and run:

    ./mvnw clean verify
    docker build -t cloud-api:local .
    docker run --rm -p 8080:8080 cloud-api:local

On Windows PowerShell, use **.\mvnw.cmd clean verify** if the Maven Wrapper is provided. Once the container is running, call **http://localhost:8080/actuator/health** and **/api/hello** from the host machine.

## 9. Configuring Kubernetes Probes

Kubernetes uses probes to decide when to send traffic, when to restart a container, and whether to wait for startup. Example Deployment:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: cloud-api
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: cloud-api
      template:
        metadata:
          labels:
            app: cloud-api
        spec:
          terminationGracePeriodSeconds: 30
          containers:
            - name: cloud-api
              image: registry.example.com/cloud-api:1.0.0
              ports:
                - name: http
                  containerPort: 8080
              env:
                - name: SERVER_PORT
                  value: "8080"
              resources:
                requests:
                  cpu: 250m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              startupProbe:
                httpGet:
                  path: /actuator/health/liveness
                  port: http
                periodSeconds: 10
                timeoutSeconds: 2
                failureThreshold: 30
              livenessProbe:
                httpGet:
                  path: /actuator/health/liveness
                  port: http
                periodSeconds: 10
                timeoutSeconds: 2
                failureThreshold: 3
              readinessProbe:
                httpGet:
                  path: /actuator/health/readiness
                  port: http
                periodSeconds: 5
                timeoutSeconds: 2
                failureThreshold: 3

In this example:

- The startup probe allows up to roughly 300 seconds for the application to start, calculated from period and failure threshold.
- The liveness probe checks the process after the startup probe succeeds.
- The readiness probe checks readiness to receive traffic more frequently.
- **timeoutSeconds** must be sufficient for the health handler to respond normally without being overly long.
- **terminationGracePeriodSeconds** must align with graceful shutdown and request draining time.

These numbers are only starting points. Measure startup duration and health endpoint latency in real environments. If probes are too sensitive, a GC pause or CPU spike can cause Pods to be removed from the Service or restarted repeatedly.

Kubernetes does not automatically create health endpoints for your application. The container must actually serve the configured paths, ports must match, and NetworkPolicies must not block probe traffic.

## 10. Verifying from Local to Cluster

### 10.1. Testing Local Build and Startup

Run:

    ./mvnw clean verify
    java -jar target/cloud-api-*.jar

Wait for logs indicating the application has started and the web server is listening. Then call:

    curl -i http://localhost:8080/api/hello
    curl -i http://localhost:8080/actuator/health
    curl -i http://localhost:8080/actuator/health/liveness
    curl -i http://localhost:8080/actuator/health/readiness

On Windows, use **curl.exe** to avoid the PowerShell alias. Confirm endpoints return HTTP 200 when the application is healthy and the health payload contains no sensitive information.

### 10.2. Testing Unready State

If you have a readiness contributor for a dependency, simulate dependency disconnection in a test environment. Verify that readiness returns an unhealthy state and the platform stops sending traffic to that instance. Also verify that liveness remains healthy if the process is still running and capable of recovering.

Do not simulate failure by making liveness depend on a database; doing so causes database outages to trigger restart loops.

### 10.3. Verifying in Kubernetes

After applying the manifest:

    kubectl apply -f deployment.yaml
    kubectl rollout status deployment/cloud-api
    kubectl get pods -l app=cloud-api
    kubectl describe pod <pod-name>
    kubectl logs <pod-name>

You can port-forward the Service to verify from an administrative machine:

    kubectl port-forward service/cloud-api 8080:80
    curl -i http://localhost:8080/actuator/health
    curl -i http://localhost:8080/actuator/health/readiness

Observe Pod conditions, restart counts, and Events. When readiness fails, the Pod may stay Running but is removed from the Service's serving endpoints. When liveness fails enough times to hit the threshold, kubelet restarts the container. The startup probe protects the initial startup phase.

### 10.4. Testing Shutdown

Send SIGTERM or perform a rollout in staging. Confirm that the application stops accepting new requests, finishes in-flight requests within the grace period, and exits cleanly. If the application is killed before finishing, check alignment between:

- **spring.lifecycle.timeout-per-shutdown-phase**
- **terminationGracePeriodSeconds**
- **preStop** hook if present
- load balancer or ingress drain time
- maximum request processing duration

## 11. Automated Testing for Health Endpoints

You can use Spring Boot Test and MockMvc to verify that the endpoint exists and returns a valid status.

Example:

    package com.example.cloudapi;

    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    import org.junit.jupiter.api.Test;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.test.web.servlet.MockMvc;

    @SpringBootTest
    @AutoConfigureMockMvc
    class HealthEndpointTest {
        @Autowired
        private MockMvc mockMvc;

        @Test
        void healthEndpointReportsUp() throws Exception {
            mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
        }
    }

If tests use profiles or mocked dependencies, adjust expectations accordingly. Do not make tests depend on a real database or cloud service if the goal is solely to verify the endpoint and Actuator configuration. Write separate tests for custom HealthIndicators to cover both UP and DOWN states, timeouts, and returned payloads.

## 12. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| **/actuator/health** returns 404 | Missing Actuator dependency or endpoint not exposed | Check starter, exposure include, and path |
| Health returns 503 immediately on startup | Dependency contributor not ready or readiness config too strict | Check component status and startup sequence |
| Kubernetes reports probe failed | Wrong port/path, application not yet bound, or probe timeout too short | Check `kubectl describe pod`, logs, and call endpoint inside container |
| Pod restarts continuously | Liveness check failing, startup probe insufficient time, or JVM OOM | Check restart reason, exit code, memory, and probe events |
| Pod Running but receives no traffic | Readiness failing or Service selector/port mismatch | Check Pod conditions, EndpointSlice, and Service |
| Dependency failure restarts entire Pod | Dependency placed in liveness | Move appropriate dependency to readiness or monitor separately |
| Health endpoint leaks internal info | `show-details` enabled or too many Actuator endpoints exposed | Restrict exposure, details, and network access |
| Runs locally but unreachable in container | Port, bind address, environment, or image differences | Check `SERVER_PORT`, logs, container port, and runtime config |
| Shutdown forcefully killed | Grace period shorter than drain time | Align Spring, Kubernetes, and load balancer timeouts |

## 13. Pre-Deployment Checklist

- [ ] Select a supported JDK and Spring Boot version compatible with project dependencies.
- [ ] Provide a Maven/Gradle wrapper with reproducible builds in CI.
- [ ] Application includes a main class and minimal business endpoint.
- [ ] Add Spring Boot Actuator and expose only required health endpoints.
- [ ] Configure the port via environment variable with an appropriate default.
- [ ] Enable liveness/readiness probes; design a startup probe for slow-starting apps.
- [ ] Liveness checks only process vitality; readiness reflects traffic-serving capability.
- [ ] Health checks have short timeouts and avoid heavy queries.
- [ ] Never return secrets or internal details in health responses.
- [ ] Run containers as a non-root user and never bake secrets into the image.
- [ ] Configure Kubernetes probes matching actual paths, ports, and timings.
- [ ] Align graceful shutdown, load balancer draining, and termination grace period.
- [ ] Test HTTP 200/503 responses, dependency failures, startup, restarts, and shutdown.
- [ ] Set up logs, metrics, and alerts for probe failures, restart counts, and readiness duration.

## Conclusion

Bootstrapping a Java application for the cloud requires producing a stable runnable artifact, reading configuration from the environment, and exposing meaningful health signals. Spring Boot Actuator provides the health endpoints: liveness indicates whether the process can keep running, readiness indicates whether the instance can accept traffic, and the startup probe protects the initialization phase. Configuring probes properly, limiting exposed health details, and testing both failure scenarios and shutdown enables the orchestration platform to operate the application safely in production.