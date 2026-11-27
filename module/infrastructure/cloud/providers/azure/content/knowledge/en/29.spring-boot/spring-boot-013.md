# Packaging, Health Probes, and Graceful Shutdown on Azure

A **Spring Boot** application that runs reliably on a developer workstation is not automatically safe when Azure starts new replicas, rolls out a new version, shifts traffic, replaces nodes, or sends a termination signal. If packaging is misconfigured, the app may miss dependencies or listen on the wrong port. If health probes are misconfigured, the platform may route requests to an unready instance or repeatedly restart a healthy one. Without **graceful shutdown**, a rolling deployment can drop in-flight requests, sever database connections mid-flight, or process an order twice.

This lesson belongs to the **Spring Boot on Azure** chapter in the **CLOUD_PROVIDERS_AZURE** module. Across the Azure curriculum—from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, data, security, observability, and cost control—this lesson focuses on three tightly coupled operational contracts: a **launchable artifact**, **honest health signals**, and **controlled application termination**. We examine Azure App Service, Azure Container Apps (ACA), Azure Kubernetes Service (AKS), and Azure Virtual Machines, and highlight how Azure Functions differs.

**Scope:** examples target Java 17/21, Spring Boot 3.x, and Linux/container environments; verify supported JDK, Spring Boot, base image, runtime/SKU, and platform capabilities at deployment time. Seconds, CPU, RAM, replica counts, and ports shown below are **illustrative learning assumptions**, not universal defaults for every workload. Never run destructive experiments against production.

## 1. Learning Objectives

After this lesson, you will be able to:

- Package Spring Boot into an **executable JAR** and distinguish JAR, WAR, and **OCI container images**.
- Author a secure Dockerfile covering JDK/JRE choice, non-root users, HTTP ports, and JVM memory sizing.
- Explain **liveness, readiness, and startup** and differentiate process checks from business dependency checks.
- Configure Spring Boot Actuator health probes served on the application port without leaking sensitive details.
- Define appropriate **startup, readiness, and liveness probes** for AKS and Container Apps.
- Understand App Service Health Check, startup warm-up, and Java hosting health paths.
- Explain **SIGTERM**, Spring's shutdown lifecycle, connection draining, and termination deadlines.
- Coordinate **`terminationGracePeriodSeconds`**, `preStop`, readiness, and rolling deployments in Kubernetes.
- Design shutdown behavior for REST APIs, HTTP streaming, and Service Bus/Kafka/background workers.
- Mitigate race conditions: requests arriving during pod termination, connection pools, active tasks, and duplicate messages.
- Build CI/CD gates verifying artifacts, probe behavior, image security, rolling rollouts, and rollbacks.
- Measure downtime, startup duration, 5xx errors, request interruptions, and the cost of high-availability configurations.

## 2. Three Operational Contracts

~~~mermaid
flowchart LR
    A[Git + build] --> B[Executable JAR or OCI image]
    B --> C[Azure host starts JVM]
    C --> D[Startup probe / warm-up]
    D --> E[Readiness allows traffic]
    E --> F[HTTP requests + background work]
    F --> G[SIGTERM / scale-in / deployment]
    G --> H[Stop accepting new work]
    H --> I[Drain + commit/checkpoint]
    I --> J[Exit within deadline]
~~~

The three contracts:

1. **Artifact contract:** the build contains the right bytecode and dependencies, runs on the intended Java version and configuration, is reproducible, and carries provenance.
2. **Health contract:** the platform receives accurate signals indicating whether the process is alive, finished starting, and ready to accept traffic.
3. **Shutdown contract:** when asked to stop, the process stops accepting new work, finishes or hands off active work before the deadline, and exits predictably.

These three contracts interact directly. Declaring the wrong port in a Dockerfile breaks readiness probes even while the app runs normally. Putting a database check inside liveness probes can restart every pod when Azure SQL slows down. Enabling graceful shutdown with only a 5-second termination deadline still truncates transactions mid-flight.

## 3. Comparing Azure Deployment Targets

| Platform | Typical artifact | Health inspection | Key shutdown mechanics |
|---|---|---|---|
| **Azure App Service (Java SE)** | Executable JAR | App Service Health Check, app logs, Actuator | App restart/slot swap/scale-in, runtime termination, warm-up |
| **App Service custom container** | OCI image | Health Check HTTP path; container startup | Container signal/lifecycle per hosting plan |
| **Azure Container Apps** | OCI image | Configurable HTTP/TCP startup/readiness/liveness probes | Revision/replica termination, draining/scale-in |
| **AKS** | OCI image via Kubernetes Deployment | `startupProbe`, `readinessProbe`, `livenessProbe` | Pod termination, `SIGTERM`, `preStop`, grace period |
| **Azure Virtual Machines / VMSS** | JAR or OCI image | Process/systemd, Load Balancer/App Gateway probes | systemd stop signals, timeouts, rolling VM upgrades |
| **Azure Functions Java** | Function package or supported format | Function host/runtime health and trigger behavior | Host lifecycle and trigger checkpoint/retry (differs from Spring MVC servers) |

**Never copy one generic probe YAML blindly across all platforms.** Spring Boot can expose consistent HTTP endpoints, while control-plane settings, termination deadlines, and health semantics vary by host.

## 4. Running Example Application

Assume **orders-api** is a REST API:

- **`GET /api/orders/{id}`** reads an order from Azure Database for PostgreSQL.
- **`POST /api/orders`** writes an order and creates an outbox event.
- **`/actuator/health/liveness`** serves liveness checks.
- **`/actuator/health/readiness`** serves readiness checks.
- Database credentials come from managed identity or an approved secret store.
- At least two replicas run; sessions and order state are **never kept exclusively in RAM**.

~~~text
Client -> Azure ingress -> orders-api instances
                           |
                           +-- PostgreSQL
                           +-- Service Bus (via outbox worker)
                           +-- Azure Monitor / Application Insights
~~~

Goal: during a new deployment, **old instances stop accepting new work**, in-flight requests finish within bounds, and new instances receive traffic only after genuinely passing readiness. Note that this alone does not provide **exactly-once** database/queue semantics—business operations still require transactions and idempotency.

## 5. Choosing JAR, WAR, or Container Image

| Format | Execution model | Best fit | Risks |
|---|---|---|---|
| **Executable JAR** | JVM runs Spring Boot's embedded server | App Service Java SE, VMs, or container base layer | Host JDK/runtime must match artifact version |
| **WAR** | External servlet container supporting WARs | Legacy apps or dedicated servlet hosts | Container compatibility and context path quirks |
| **OCI image** | Container runtime starts the Java process | Container Apps, AKS, App Service containers | Base image patching, user permissions, signal/PID 1 |
| **Native executable** (if adopted) | Compatible native image/runtime | Fast startup / low memory footprint needs | Different build, library support, debugging, and observability |

A **Spring Boot executable JAR** runs with `java -jar` and bundles runtime dependencies. A **plain JAR** lacks runtime dependencies and Boot's `Main-Class` launcher, so it will not boot as an executable Spring Boot app.

### Pre-Build Checklist

- Pin the JDK version via Maven/Gradle toolchains and CI build images.
- Pin the Spring Boot parent/BOM and audit dependencies.
- Run unit/integration tests and schema compatibility checks.
- Keep environment config and secrets outside the artifact.
- Enable Actuator judiciously without exposing every endpoint to the internet.
- Fix the **artifact filename/entrypoint** before writing the Dockerfile.
- Design bounded shutdown timeouts into code from day one rather than retrofitting in production.

## 6. Building an Executable Spring Boot JAR with Maven

An illustrative Maven setup:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>SPRING_BOOT_SUPPORTED_VERSION</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>orders-api</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
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
  <build>
    <finalName>orders-api</finalName>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`SPRING_BOOT_SUPPORTED_VERSION` is a placeholder: substitute a supported Spring Boot release compatible with Java 21 before running Maven. This POM is a skeleton and omits PostgreSQL, Security, test dependencies, migration plugins, and production profiles.

Build:

~~~bash
./mvnw -B clean verify
java -jar target/orders-api.jar
~~~

This expects the Maven Wrapper to be present (`mvn` works if CI pins Maven). Confirm the artifact actually starts and serves HTTP endpoints rather than trusting a zero build exit code alone.

## 7. Gradle `bootJar` and Artifact Consistency

With Gradle and the Spring Boot Gradle plugin:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/orders-api-1.0.0.jar
~~~

The output filename depends on project version, Gradle settings, and plugin configuration. Distinguish **`bootJar`** from the plain **`jar`** task if both run so pipelines deploy the executable archive rather than the plain JAR.

### Reproducibility

~~~text
Commit SHA  -> Maven/Gradle lock/BOM -> Built artifact
                                        |
                                        +-- Artifact checksum
                                        +-- SBOM/dependency scan
                                        +-- Image digest (if container)
~~~

Reliable releases record the commit SHA, artifact checksum, build tool/JDK versions, and deployment target. Avoid rebuilding from the moving `main` branch per environment, because builds can diverge even under the same version tag.

## 8. Writing a Safe Dockerfile for Spring Boot

For ACA or AKS, package the executable JAR into an OCI image. Assume CI already built `target/orders-api.jar`.

~~~dockerfile
# Runtime JRE 21 example; replace tag/digest per update policy.
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --chown=10001:10001 target/orders-api.jar /app/orders-api.jar

USER 10001:10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

### Rationale Behind Each Line

- **JRE instead of JDK** when only runtime execution is required; still check whether the app depends on JDK tools or native tooling.
- **`COPY --chown`** ensures the non-root user owns/reads the artifact; verify builder runtime support.
- **`USER 10001`** narrows the attack surface; verify temp directory write permissions if the app uses `/tmp`.
- **`EXPOSE 8080`** records container metadata and **does not open a public Azure port** by itself.
- **JSON-array `ENTRYPOINT`** keeps Java as PID 1 so termination signals reach the JVM directly without a shell swallowing them.
- **`MaxRAMPercentage=65`** is illustrative—measure heap, non-heap, and RSS against actual container memory limits.

**Never bake DB passwords, Azure connection strings, SAS tokens, or private keys** into Dockerfile `ENV` or `ARG` instructions—they persist in image layers, build logs, and metadata.

### Why Avoid Shell Entrypoints?

~~~dockerfile
# Discouraged when shell does not forward signals properly:
ENTRYPOINT java -jar /app/orders-api.jar
~~~

An intervening shell often runs as PID 1, fails to forward `SIGTERM` cleanly, or alters exit codes. Whenever an init wrapper script is unavoidable:

~~~sh
#!/bin/sh
set -eu
# Verify environment contains no secrets in logs.
exec java -jar /app/orders-api.jar
~~~

`exec` replaces the shell process with the JVM so signals reach Java directly. Ensure executable permissions, LF line endings, and compatible user permissions; note that distroless images may omit `/bin/sh` altogether.

## 9. Building and Running the Image Locally

~~~bash
./mvnw -B clean verify
docker build -t orders-api:lab .
docker run --rm --name orders-api \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local \
  orders-api:lab
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
~~~

These health routes require **Actuator + Spring Boot probe config**. Without a main class, controllers, or required DB configuration, the skeleton POM from Section 6 alone will not run completely.

### What to Verify

- Does the container process run under a non-root UID?
- Did Java pick up environment variables and the expected port?
- Does readiness transition from not-ready to ready once startup completes?
- Does liveness return HTTP 200 during normal operation?
- Is the container spared from **`OOMKilled`** under memory limits?
- When sent `SIGTERM`, does the app finish active requests and exit before the deadline?

## 10. JVM Inside Containers: Memory, CPU, and Exit Codes

Inside a container, Spring Boot allocates **heap, metaspace, direct buffers, thread stacks, native memory, JIT code cache, and native libraries**. Modern JVMs inspect cgroup limits automatically, yet still require measurement and tuning.

~~~text
Container memory limit: 1024 MiB (illustrative)
  |
  +-- JVM maximum heap: ~650 MiB
  +-- Metaspace / native / threads
  +-- Direct memory / TLS / network buffers
  +-- OS/container overhead
  +-- Safety headroom
~~~

**Never set `-Xmx` equal to the full container memory limit** assuming non-heap needs nothing. Under tight limits, GC thrashing or native OOMs can stall liveness probes and trigger restart loops.

### Exit Codes and Root Causes

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Exit code `0` | Normal completion or clean shutdown | Scale-in schedule, logs, lifecycle hooks |
| Exit code `137` | Killed via `SIGKILL` (OOM or grace deadline exceeded) | Check `OOMKilled`, memory metrics, termination grace |
| Exit code `143` | Typically corresponds to `SIGTERM` in shells/runtimes (not guaranteed everywhere) | Deployment/scale-in timestamps and signal handling |
| Liveness failure / restart | Probe timed out or process hung | Verify HTTP path/port, startup lag, CPU throttling, GC |
| JVM exception | Startup, configuration, or dependency error | Inspect redacted stack traces, secrets, DB reachability |

Exit codes **cannot pinpoint root cause in isolation**—correlate pod events, platform logs, `OOMKilled` flags, and deployment timelines.

## 11. How Liveness, Readiness, and Startup Probes Differ

A **health probe** lets the orchestrator periodically test instances to decide whether to route traffic or restart containers.

| Probe | Question asked | On failure | Should NOT depend on |
|---|---|---|---|
| **Startup** | Has the app finished initializing enough for normal probing? | Platform may restart after failure threshold | Normal slow JVM boot treated as crash |
| **Liveness** | Is the process alive and un-wedged? | Restarts instance/container after threshold | External SQL/Redis reachability |
| **Readiness** | Can this instance serve **new traffic** right now? | Pulled from traffic/Endpoints list | Non-critical optional features failing |

**Liveness failures should signal unrecoverable in-process faults**, such as a deadlocked process where a restart actually helps. By contrast, database maintenance is external—restarting 50 pods together makes recovery worse.

**Readiness failures should not automatically force restarts.** Pulling an unready instance out of rotation prevents HTTP 5xxs while healthy peers handle traffic.

## 12. Spring Boot Instance Lifecycle State Diagram

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> AliveNotReady: JVM, context, startup complete
    AliveNotReady --> Ready: readiness checks pass
    Ready --> NotReady: drain / local dependency unavailable
    NotReady --> Ready: recovered, not terminating
    Ready --> Terminating: SIGTERM / scale-in
    NotReady --> Terminating: SIGTERM
    Terminating --> Stopped: outstanding work completed or deadline
    Stopped --> [*]
~~~

Spring Boot tracks **`ApplicationAvailability`** via **`LivenessState`** and **`ReadinessState`**. After boot succeeds, lifecycle events flip these states accordingly; during shutdown, readiness can shift to **`REFUSING_TRAFFIC`** before beans and servers close, depending on Boot/runtime setup.

**Framework state does not eliminate platform propagation delays:** ingress routing caches and control-plane updates take finite time. Keep graceful draining and client-side safe retries in place.

## 13. Spring Boot Actuator: Dependencies and Configuration

Add Actuator to your Spring Boot project:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Illustrative **`application.yml`** for Spring Boot 3.x:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Standard Actuator probe endpoints:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

With `management.endpoint.health.probes.add-additional-paths=true`, supported Spring Boot releases also register:

~~~text
GET /livez
GET /readyz
~~~

on the **main application port**. Confirm exact paths and exposure against your Boot version and Spring Security setup—never assume additional paths exist or bypass security unconfigured.

### Why Set `show-details: never`?

Health responses exposing hostnames, database errors, connection details, or stack traces leak operational topology. Public health checks should return only **UP/DOWN or minimal status**, reserving rich diagnostics for authenticated observability tools.

### Health Output and HTTP Status Codes

Illustrative response:

~~~json
{"status":"UP"}
~~~

When readiness becomes **`REFUSING_TRAFFIC`**, the readiness group returns an error status mapped to an unhealthy HTTP code—typically **503**. If you customize status mappings, verify that Azure probes interpret those codes properly.

## 14. Which Port Should Health Endpoints Use?

Actuator can share the **main application port** or run separately on **`management.server.port`**. This choice directly affects probe fidelity.

~~~text
Client traffic -> port 8080 -> Spring MVC/Tomcat
Health probe   -> port 8080 -> same connector/process
~~~

When probes run on a **separate management port**:

~~~text
Client traffic -> port 8080 -> main server connector
Health probe   -> port 9090 -> management connector
~~~

A 200 OK on **management port 9090** does not prove main connector **8080** is accepting user traffic cleanly—if the main servlet thread pool is deadlocked or ingress mapping breaks, port 9090 can keep returning 200.

### Recommendations

- On Kubernetes and ACA, prefer **main-port readiness/liveness paths** where permitted by security policy.
- If a separate management port is required for access control, add synthetic checks exercising the live serving port.
- Never expose the full Actuator suite over public internet ingress.
- Keep health paths synchronized with container `targetPort`, Service ports, ingress rules, and path rewrites.

**Never treat port separation as authentication**: apply network policies and access controls to management ports too.

## 15. Spring Security and Health Probes

When **Spring Security** is active, authentication filters may return 401/403 or redirect probes to `/login`, since platform probes do not authenticate like end users.

Skeleton Spring Boot 3 / Spring Security 6 configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/actuator/health",
                "/actuator/health/liveness",
                "/actuator/health/readiness",
                "/livez",
                "/readyz")
            .permitAll()
            .anyRequest().authenticated());
        // This is only an authorization skeleton, lacking full JWT/CSRF.
        return http.build();
    }
}
~~~

**Do not copy this skeleton as complete production security.** Production REST APIs require JWT/OIDC resource server setup, issuer/audience validation, appropriate CSRF policies, exception handling, and method-level authorization. Permit only minimal health paths returning non-sensitive payloads, and pair them with App Service/AKS network access restrictions.

### Verification

~~~bash
curl --silent --show-error -i \
  http://localhost:8080/actuator/health/liveness
curl --silent --show-error -i \
  http://localhost:8080/actuator/health/readiness
~~~

If curl returns a **302 login redirect**, **401**, or **403**, fix security routing before expecting Azure probes to see 200 OK.

## 16. Readiness: Should It Check the Database?

A common option includes the **`db`** health indicator inside the readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

**This is a conditional customization**, not a blanket default. If an app cannot serve any meaningful request without the database, checking `db` avoids routing traffic to an isolated instance with broken local DB access. However, during a **shared DB outage across all replicas**, every pod flips unready simultaneously and load balancers return blanket 503s—even for endpoints that did not need the database.

### Comparing Two Designs

| Approach | Benefit | Risk |
|---|---|---|
| **Readiness via `readinessState` only** | Keeps pods in rotation during shared DB blips | DB-backed routes still fail; must enforce crisp timeouts/errors |
| **Readiness includes `db`** | Removes a pod suffering local DB failure | Shared DB outage marks every pod unready, obscuring root cause |

### Practical Guidelines

1. **Never include `db` in liveness** to avoid restart storms.
2. Assess which dependencies are truly mandatory for every incoming request.
3. Combine circuit breakers, bounded timeouts, and degraded responses for transient faults.
4. For mixed workloads, separate services or run lightweight domain-specific synthetic checks.
5. Keep any readiness DB check lightweight with strict timeouts and bounded pool usage.
6. Test full-database outages alongside single-pod network blackholes.

**Readiness should reflect an instance's ability to handle traffic**, not trigger fleet-wide blackouts whenever an external dependency blips.

## 17. Startup Probes: Handling Slow-Starting Applications

Spring Boot can take tens of seconds to boot due to classpath scanning, Flyway/Liquibase migrations, JIT warm-up, remote config loading, or cache hydration.

Kubernetes **`startupProbe`** holds off liveness and readiness checks until startup succeeds. Example:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
  timeoutSeconds: 2
~~~

That gives a **theoretical budget around `5 × 24 = 120` seconds** before startup is declared failed (excluding minor scheduling/check overhead). Never pick 120 blindly—measure p95/p99 startup time under realistic load, DB state, and environment settings.

### What Startup Probes Should Verify

- Succeeds only once the JVM and Spring context are sufficiently initialized.
- Does not execute slow or flaky SQL queries.
- Does not report ready before the main HTTP connector opens if subsequent probes use HTTP.

**Never inflate `readinessProbe` thresholds to mask slow startup** while omitting `startupProbe`. In Kubernetes, `startupProbe` cleanly separates initialization budget from runtime liveness sensitivity.

## 18. Liveness Probes: Diagnosing Process Health

Illustrative HTTP liveness probe:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

The orchestrator polls periodically and restarts the container after consecutive failures per policy. Actual timings vary with kubelet scheduling—this is not a strict guarantee of "restart at 30.0 seconds."

### Pitfalls to Avoid

- Pointing liveness at default `/actuator/health` when it bundles DB/Redis checks, triggering restarts on external outages.
- Routing liveness through a public WAF or rate-limited gateway instead of internal pod/host checks.
- Setting `timeoutSeconds` shorter than normal GC pauses or CPU throttling windows.
- Setting `failureThreshold: 1` on processes with occasional brief pauses.
- Confusing a 302/401 auth redirect on the liveness URL with a dead JVM.

Design liveness strictly to catch **unrecoverable process states**, never as an integration test of downstream services.

## 19. Readiness Probes: Protecting Traffic During Rollouts

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 1
~~~

While readiness fails, Kubernetes Services remove the pod from ready endpoints so new traffic avoids it, assuming controllers and proxies honor readiness. Because **propagation lags slightly**, readiness never replaces graceful draining or client retries.

### Should Readiness Monitor the Java Thread Pool?

If request threads stay saturated long term, temporarily shedding load helps. However, if readiness flaps during brief traffic spikes, remaining replicas absorb extra load and cascade into failure. Address short spikes with **backpressure, timeouts, load shedding, and autoscaling** instead of flapping readiness on every CPU burst.

### Does Readiness Only Matter During New Deploys?

No. Readiness governs deployments, scale-ins, transient local disruptions, and recovery. Test the **entire lifecycle**, not just one `curl 200` right after startup.

## 20. How Misconfigured Health Probes Cause Outages

Classic anti-pattern:

~~~text
10 Spring Boot replicas
  -> liveness calls /actuator/health
  -> indicator 'db' queries shared PostgreSQL

PostgreSQL hits a 2-minute blip
  -> all liveness checks fail
  -> all replicas restart simultaneously
  -> JVM warm-up + connection pool storm
  -> database recovery slows down further
~~~

The **root fault** was a brief DB outage, while the **multiplier** was wiring DB health into liveness. Better design:

- Keep liveness strictly scoped to JVM/process health.
- Prevent DB hangs via connection/query timeouts and circuit breakers.
- Choose readiness semantics deliberately.
- Ensure autoscalers/HPAs do not amplify DB reconnect storms.
- Separate **`DB_DOWN`** from **`JVM_DEADLOCK`** in dashboards and alerts.

The goal is never "keep green checkboxes always," but ensuring each signal **accurately diagnoses the fault and drives the right response**.

## 21. AKS: Deployment with Full Probes and Graceful Deadlines

Illustrative manifest for Spring Boot on AKS:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 50
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: orders-api
          image: myregistry.azurecr.io/orders-api:1.0.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "768Mi"
            limits:
              cpu: "1500m"
              memory: "1536Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
            timeoutSeconds: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
            timeoutSeconds: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

This is a **learning manifest**, not a production-complete deployment package. Production requires ACR pull credentials/permissions, Workload Identity, app config, NetworkPolicies, ingress, HPA, PDB, security baselines, observability, and image scanning.

### Explaining the Timing Budget

~~~text
terminationGracePeriodSeconds = 50 s
preStop delay                  = 5 s
Spring Boot shutdown phase    = 30 s
Illustrative headroom          = 15 s
~~~

The **50 s** grace period covers `preStop` execution plus JVM `SIGTERM` shutdown plus headroom—it is **not** `50 s + preStop`. If `preStop` burns 40 seconds, the JVM gets barely any time before Kubernetes sends `SIGKILL`.

### `preStop` Command Caveat

`/bin/sh -c "sleep 5"` assumes `/bin/sh` and `sleep` exist in the container image. On **distroless images**, exec hooks calling `/bin/sh` fail—use image-compatible lifecycle mechanisms or supported container entrypoints, and avoid replacing real readiness/draining with huge sleeps.

### `maxUnavailable: 0` Does Not Guarantee Absolute Zero Downtime

This setting guides the Deployment controller to keep minimum ready replicas during **controlled rolling updates**. It cannot prevent node failures, AZ outages, DB downtime, HPA races, endpoint propagation lag, or breaking database schema migrations.

## 22. AKS: Verifying Rollouts and Pod Health

When authorized to test inside a **lab cluster**:

~~~bash
NAMESPACE="spring-lab"

kubectl get deployment orders-api -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -l app=orders-api -o wide
kubectl describe deployment orders-api -n "$NAMESPACE"
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp
kubectl rollout status deployment/orders-api -n "$NAMESPACE"
~~~

Inspect individual pods:

~~~bash
kubectl describe pod <POD_NAME> -n "$NAMESPACE"
kubectl logs <POD_NAME> -n "$NAMESPACE" --tail=100
kubectl get endpointslice -n "$NAMESPACE" \
  -l kubernetes.io/service-name=orders-api
~~~

### Signals to Check

- How long until a new Pod transitions to **`Ready`**?
- Did any `Startup probe failed`, `Readiness probe failed`, or `Liveness probe failed` events occur?
- Did restart counts climb, or did `OOMKilled` appear?
- Do Service `EndpointSlice` objects list only genuinely ready endpoints?
- During rollout, did old and new pods serve concurrently cleanly?
- Did ingress logs record 502/503 or connection resets during pod swaps?

Never stop at seeing **`Running`** in `kubectl get pods`. **`Running` does not mean `Ready`**, and `Ready` alone does not prove business transactions succeed.

## 23. AKS: Rollouts, PodDisruptionBudgets, and Node Drains

In Kubernetes:

- **Deployment `RollingUpdate`** orchestrates pod replacement during releases.
- **`readinessProbe`** determines traffic eligibility.
- **`PodDisruptionBudget` (PDB)** limits **voluntary** disruptions handled through Kubernetes' eviction API.
- **`terminationGracePeriodSeconds`** gives processes bounded time to stop.
- **Ingress/gateways** may hold keep-alive connections or lag slightly when updating upstreams.

Example PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

**PDBs do not stop involuntary outages** (node crashes, OOMs, forced deletions) and do not replace sufficient replicas or zone spread. Note also that running 2 replicas with `minAvailable: 2` can block voluntary node drains during cluster maintenance—balance availability against operational agility.

### Terminating Pods and Endpoint Propagation

When Kubernetes marks a pod terminating, `EndpointSlice` updates and ingress controllers need time to converge. Already-open sockets or racing requests can still hit the exiting pod. A brief **`preStop` delay** often lets load balancers drain before the JVM closes listeners, though you should measure actual convergence rather than treating 5 seconds as magic.

## 24. Container Apps: Container-Level Probes

With **Azure Container Apps**, apps deploy as OCI images with HTTP ingress matching `targetPort`, supporting configurable startup, readiness, and liveness probes.

**Conceptual** layout (not directly deployable verbatim):

~~~yaml
containerApp:
  image: myregistry.azurecr.io/orders-api:1.0.0
  ingress:
    external: true
    targetPort: 8080
  scale:
    minReplicas: 2
    maxReplicas: 10
  probes:
    startup:
      httpGet: /actuator/health/liveness
      port: 8080
    readiness:
      httpGet: /actuator/health/readiness
      port: 8080
    liveness:
      httpGet: /actuator/health/liveness
      port: 8080
~~~

**Never paste this pseudo-YAML into `az containerapp create/update`.** The real ACA resource schema nests probes under **`properties.template.containers[].probes`** with API-version-specific HTTP/TCP fields, thresholds, and intervals—create real configs via Portal, Bicep, ARM, or supported CLI schemas.

### Checks to Run

1. Container ingress **`targetPort`** matches Spring's `server.port`.
2. Container boots with the right JVM flags and environment variables.
3. Probe endpoints exist and return the expected HTTP codes.
4. New revisions receive traffic only once ready per platform semantics.
5. With **`scale-to-zero`**, initial requests incur cold starts—tune probe thresholds accordingly.
6. During scale-in or revision deactivation, confirm the app catches termination signals and shuts down within bounds.
7. Separate startup failures from liveness failures in scale/restart logs.

**Never assume ACA's exact signal timing and termination grace match AKS Kubernetes Deployments identically.** Consult ACA documentation and test on a real revision.

## 25. Container Apps: Revisions, Traffic Splitting, and Graceful Scale-In

ACA supports **revisions** and weighted traffic splitting across active revisions:

~~~text
External client
       |
       v
ACA ingress / traffic weights
       |
       +-- Revision v1: 90%, ready replicas
       |
       +-- Revision v2: 10%, ready replicas
                 |
                 v
             Spring Boot API
~~~

### Before Shifting Traffic to v2

- Do probe paths exist in the new image?
- Does v2 alter database schemas, and can v1 run safely alongside v2?
- Did startup time or memory footprint grow?
- Do JWT issuers/audiences, database DNS, and Key Vault references resolve cleanly?
- If v2 fails, can traffic safely route back to v1 despite any data written by v2?

### Scale-In Is a Mini Rollout

When `minReplicas` or scale rules shrink replica counts, each exiting replica still needs to:

- Stop accepting new work as termination begins.
- Finish in-flight HTTP requests or ensure queue jobs retry safely.
- Close JDBC pools and HTTP clients cleanly before the deadline.
- Record signal/termination telemetry for troubleshooting.

**Observing one clean deployment does not prove autoscale-in is safe.** Explicitly test scale-down while requests are actively executing.

## 26. App Service: Health Check for Spring Boot

**Azure App Service Health Check** periodically calls a configured HTTP path across instances where supported by plan, removing unhealthy instances from routing per service rules.

### Setup

1. Open your **App Service** and target environment/slot in the Azure Portal.
2. Navigate to **Health check**.
3. Specify a minimal path such as **`/actuator/health/readiness`**.
4. Confirm the path returns a healthy HTTP status directly from the **deployed app** without auth redirects.
5. Monitor platform health logs and metrics.
6. Test changes on staging before applying to production.

### Choosing a Health Check Path

| Path | Advantage | Limitation |
|---|---|---|
| **`/actuator/health/liveness`** | Confirms process responsiveness | Can return UP even when instance is not traffic-ready |
| **`/actuator/health/readiness`** | Reflects traffic readiness | If tied to a shared DB, all instances may turn unhealthy together |
| Custom minimal **`/healthz`** | Easy alignment with platform rules | Must stay synchronized with Spring availability without hiding faults |

**Never return hardcoded 200 OK** to force Health Check green if the Spring server is unready, and never execute heavy SQL queries inside the health path.

### App Service Specifics

- Health Check is **not identical to Kubernetes readiness/liveness/startup probes**; remediation mechanics differ.
- Required instance counts before route-away behavior triggers and replacement thresholds vary by plan/policy.
- For **custom containers**, confirm startup commands, `WEBSITES_PORT` / port bindings match.
- Enabling **Always On** (where supported) reduces idle unload, though it does not replace health paths or eliminate deployment cold starts.
- With only one instance, App Service has nowhere else to route traffic—plan scaling/HA accordingly.

## 27. App Service: Warm-Up, Startup Commands, and Slots

**App Service Java SE** executes Spring Boot executable JARs via the managed Java runtime. **App Service custom containers** launch your image/entrypoint with platform port settings.

### Verification Checklist

- Java runtime/JDK matches compiled bytecode.
- JAR filename matches startup command and includes `Main-Class`/Boot loader.
- Spring Boot binds to the port and interface expected by the runtime host.
- App Settings and Key Vault references resolve cleanly.
- `/actuator/health/readiness` returns healthy after boot.
- Cold starts and slot warm-ups do not time out initial user requests.

### Deployment Slots

~~~text
Staging slot: candidate JAR/image
     |
     +-- Warm-up + health check + DB/network check
     |
     v
Swap / traffic promotion per feature
     |
     v
Production slot: candidate version
~~~

**Deployment slot swaps follow slot-sticky setting and identity rules.** Verify database endpoints, secrets, managed identities, event publishers, and downstream integrations prior to swapping—never let staging credentials write to the production DB or vice versa.

### Health Paths Are Not Login-Protected Pages

If your health URL returns `302` to `/login` or serves an HTML "error" page with HTTP 200, fix Spring Security and routing so health checks return true status codes with minimal non-sensitive payloads.

## 28. Virtual Machines and VM Scale Sets: `systemd` Lifecycle

On Linux VMs, **`systemd`** typically manages the Spring Boot service:

~~~ini
[Unit]
Description=Spring Boot orders API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=orders
WorkingDirectory=/opt/orders
Environment=SPRING_PROFILES_ACTIVE=prod
ExecStart=/usr/bin/java -jar /opt/orders/orders-api.jar
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=45
SuccessExitStatus=143

[Install]
WantedBy=multi-user.target
~~~

This is a **template**: create the service user, lock down file permissions, confirm Java/JAR paths, and inject secrets securely. **Never put DB passwords directly in the unit file**, where local permissions or `systemd` inspection could expose them. Managing `systemd` requires authorized sudo/root privileges—never practice on production VMs.

### During `systemd` Stop

1. `systemd` sends **`SIGTERM`** per the unit configuration.
2. Spring Boot initiates its graceful shutdown lifecycle.
3. The HTTP server stops taking new requests and finishes active ones within bounds.
4. Beans, pools, and worker resources close.
5. Exceeding **`TimeoutStopSec`** triggers forced termination.

Align **`TimeoutStopSec`** with Spring's `timeout-per-shutdown-phase`, load balancer pre-drain delays, and overhead. On VM Scale Sets (VMSS), coordinate backend pool health probes and rolling upgrade settings to drain traffic smoothly.

## 29. Azure Functions Does Not Follow Web Server Probe Rules

**Azure Functions Java** runs inside a **Functions host** with platform triggers, scaling, and lifecycles tied to the hosting plan. A Service Bus or Timer function does not inherently run **embedded Tomcat** or Actuator endpoints like a Spring Boot MVC web service.

| Aspect | Spring Boot web app | Azure Functions Java |
|---|---|---|
| Orchestrating process | JVM / embedded server | Azure Functions host + Java worker |
| App health | Actuator liveness/readiness | Host/trigger health and plan telemetry |
| Work intake | HTTP/gateway or app consumer | Triggers and bindings |
| Shutdown | Spring context / server lifecycle | Host/trigger lifecycle and binding in-flight handling |
| Retry / checkpoint | App / queue consumer | Host/binding semantics plus business idempotency |

Never assume adding `server.shutdown=graceful` to a Function project automatically coordinates Functions host Service Bus trigger checkpoints. Use Functions-native host/SDK mechanisms and business idempotency.

## 30. `SIGTERM` Is the Starting Signal, Not the Finish Line

When shutting down a container or host, **`SIGTERM`** asks the JVM to shut down cleanly. If the JVM hangs or misses the host deadline, the platform escalates to **`SIGKILL`** or equivalent forced termination.

~~~mermaid
sequenceDiagram
    participant P as Platform / Orchestrator
    participant A as Spring Boot
    participant I as Ingress / Service
    participant D as Database / downstream
    P->>I: Mark endpoint terminating (propagation)
    P->>A: preStop hook if present
    P->>A: SIGTERM (after hook)
    A->>A: Readiness REFUSING_TRAFFIC / shutdown
    A->>I: Stop accepting new connections per server behavior
    A->>D: Complete or roll back transaction
    A->>A: Close pools, listeners, background tasks
    A-->>P: Process exit
    Note over P,A: Grace deadline expired: may force-kill
~~~

Exact sequencing of ingress deregistration, `SIGTERM`, and availability events varies across Kubernetes, ACA, App Service, and host runtimes. **This sequence diagram shows the actors involved**, not a strict guarantee of millisecond ordering on every host.

### Graceful Shutdown Cannot Prevent Every Failure Mode

- A VM or node can lose power before sending `SIGTERM`.
- A pod can be `OOMKilled` / `SIGKILL`ed instantaneously.
- Clients can drop connections mid-response.
- A DB transaction can commit right before the JVM crashes.
- Queue brokers can redeliver unacknowledged messages after failover.

Therefore, graceful shutdown **reduces avoidable disruptions**, while durability, idempotency, retries, and DR remain mandatory.

## 31. Configuring Graceful Shutdown in Spring Boot

Example **`application.yml`**:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

### Meaning

- **`server.shutdown=graceful`**: directs the embedded server to stop accepting new requests and drain active ones per server capabilities.
- **`spring.lifecycle.timeout-per-shutdown-phase=30s`**: caps duration **per Spring shutdown phase**—it **does not guarantee the entire process exits in exactly 30 seconds**.
- Health probes report availability to guide platform routing.

### Why Distinguish Total Deadline from Phase Timeout?

If multiple lifecycle phases run or components ignore deadlines, total shutdown duration can exceed any single number. The orchestrator's grace period acts as the hard ceiling:

~~~text
Host termination grace:        50 s
  - preStop:                    5 s
  - Spring lifecycle phases:   needs real measurement
  - network/cleanup overhead:  remaining
If still running after host deadline:
  -> process may be force-killed
~~~

**Never rely on naive math** like "Spring timeout = 30s, so Kubernetes grace = 31s is fine." Measure actual termination p95 across lifecycle listeners, I/O, worker draining, and overhead, and leave real headroom.

### Web Servers Differ in Shutdown Semantics

Tomcat, Jetty, Undertow, and Reactor Netty handle listener pausing and open requests differently. Keep-alive sockets, HTTP/2 streams, WebSockets, streaming responses, and client retries may demand application-level handling—**embedded server graceful shutdown never waits indefinitely for arbitrary background jobs**.

## 32. Never Call `System.exit` for a "Fast Shutdown"

Anti-pattern:

~~~java
@PreDestroy
public void stop() {
    System.exit(0); // Avoid: breaks context lifecycle and cleanup
}
~~~

Calling `System.exit` inside a lifecycle hook breaks ordered bean destruction and resource cleanup. Let `SpringApplication`/`ApplicationContext` and the embedded server coordinate `SIGTERM` shutdown normally; if administrative shutdown is ever needed, guard it strictly and avoid public endpoints calling `System.exit`.

### Shutdown Hooks and OS Signals

The JVM invokes shutdown hooks on normal exit paths, and Spring Boot registers a hook to close the `ApplicationContext`. However, **`SIGKILL`, kernel panics, power loss, and host OOM kills** skip hooks entirely—always back critical state with external transactions and checkpoints.

### Never Expose Public Actuator `/shutdown`

Some Spring Boot Actuator configurations include a `/shutdown` endpoint. Never expose it publicly "just to test graceful shutdown"—test `SIGTERM` using container or orchestrator stops in a sandbox.

## 33. `@PreDestroy`: Close Resources Without Long Business Work

For custom resources such as schedulers or unmanaged network clients, **`@PreDestroy`** cleans up locally:

~~~java
package com.example.orders;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import java.time.Instant;

@Component
public class LocalResourceOwner {
    private volatile boolean closing;

    public boolean isClosing() {
        return closing;
    }

    @PreDestroy
    public void closeResources() {
        closing = true;
        // Close custom clients/file handles with a reasonable deadline.
        // Never perform migrations or unbounded external API calls.
        System.out.println("Cleanup invoked at " + Instant.now());
    }
}
~~~

**This is a skeleton**; a boolean flag inside one bean does not redirect cluster traffic or replace Spring's `readinessState`. Framework-managed resources such as `DataSource`, JMS, and Kafka clients already participate in Spring lifecycles—avoid double-closing or closing out of order.

### Ordering Matters

- Stop intake **before** closing downstream pools/resources still needed by active tasks.
- Wait up to a bound for tasks and handle interruption cleanly.
- Commit, roll back, or checkpoint per contract.
- Release thread pools, network sockets, and file handles last.

**Never call `Thread.sleep(60000)` inside `@PreDestroy`** to "wait for everything"—fixed sleeps waste grace budget without proving work actually finished.

## 34. `ThreadPoolTaskExecutor` and `@Async` Tasks

Spring Boot apps frequently run async work via **`@Async`** or custom executors. Without graceful executor shutdown, active tasks get severed on exit.

Example **`ThreadPoolTaskExecutor`** configuration:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {

    @Bean(name = "orderExecutor")
    public ThreadPoolTaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

### Key Limitations

- Waiting for queued/active tasks consumes shutdown grace budget.
- `queueCapacity(100)` lives **in process RAM** and vanishes on forced kills.
- Tasks ignoring thread interruption or making untimeouted downstream calls can still blow past deadlines.
- Rejection behavior during context close varies by Spring Framework version—verify experimentally rather than guessing from setter names.

**Never store must-not-lose business events solely in an in-memory `@Async` queue.** Persist durable work to a transactional outbox table or Service Bus before returning HTTP 2xx.

## 35. `@Scheduled` Across Multiple Replicas

A Spring Boot app might define:

~~~java
@Scheduled(fixedDelay = 60000)
public void refreshCache() {
    // Runs every minute while the application instance is alive.
}
~~~

Scaled to 5 replicas, **all 5 instances run `@Scheduled` independently**. During a rolling deployment, 5 old pods and 5 new pods can run simultaneously, amplifying duplicate executions.

### Choosing the Right Strategy

| Need | Suitable option |
|---|---|
| Per-instance local cache refresh | Local `@Scheduled` is appropriate |
| System-wide report dispatch | Durable scheduler/queue, distributed lock, or single leader election |
| Daily batch job | Container Apps Job, AKS CronJob, or Functions Timer as appropriate |
| Tasks needing durable retries | Service Bus / transactional outbox + idempotent worker |

**Graceful shutdown never turns `@Scheduled` into an exactly-once scheduler.** Even distributed locks require leases/fencing tokens and idempotency in case a lock holder crashes mid-work.

### Spring Scheduler Shutdown

Review shutdown policies for `TaskScheduler`, custom thread pools, cron tasks, and long-lived threads. Unmanaged custom executors need explicit Spring lifecycle shutdown—enabling `server.shutdown` alone will not stop unmanaged threads.

## 36. Queue Consumers: At-Least-Once Delivery and Shutdown

A Java worker consuming **Service Bus** messages:

~~~text
Queue message M42
    |
    v
Java consumer acquires message / lock
    |
    +-- Validate payload
    +-- Execute DB transaction
    +-- Commit business effect
    +-- Complete/acknowledge message
~~~

When the worker scales in:

1. Stop pulling new messages.
2. Allow in-flight handlers bounded time to finish.
3. Commit the database transaction **before** completing/settling the broker message.
4. If unfinished by the deadline, let the broker redeliver per lock expiration/abandon rules.
5. Re-processing must recognize `eventId` / idempotency keys to avoid duplicate side effects.

### Classic Race Condition

~~~text
T1: Worker writes order successfully.
T2: Database commit finishes.
T3: Host sends SIGTERM; process exits before completing the broker message.
T4: Broker redelivers the message.
T5: Next worker must detect the existing order and avoid duplicating it.
~~~

**Longer shutdown timeouts alone cannot prevent this race**, because nodes can crash suddenly. Build **unique constraints, idempotency keys, and transactional outbox/inbox patterns** wherever reliability matters.

### Never Mix API Liveness with Headless Queue Workers

A queue-only worker may have no HTTP server on port 8080. Attaching a Kubernetes HTTP probe to a container without an HTTP listener causes endless restarts even while the worker processes messages cleanly—use appropriate worker health checks or split APIs and workers into separate Deployments.

## 37. In-Flight HTTP Requests During Shutdown

Suppose **`POST /orders`** takes 8 seconds:

~~~text
00s Client sends POST /orders
02s Azure scale-in / rollout starts
03s Spring begins draining
08s DB transaction commits
09s Server returns 201 Created
12s JVM exits
~~~

That is the **happy path** when routing converges cleanly and shutdown budgets suffice. Yet failures still occur:

~~~text
00s POST /orders starts
02s SIGTERM
05s Container force-killed
06s Client retries after missing response
~~~

In the second timeline, the DB transaction may have either committed or rolled back, so a client retry risks creating a duplicate order. **The real defense is idempotency**, not merely a longer grace period.

### API Idempotency

Clients attach a header:

~~~http
POST /api/orders HTTP/1.1
Idempotency-Key: order-client-req-7c0e...
Content-Type: application/json

{"cartId":"cart-123"}
~~~

The backend binds the key durably to user/tenant, endpoint, request hash, and transaction outcome. If the same key arrives again after a timeout, return the stored confirmed outcome or status rather than creating a second order. **Never treat an idempotency key as an authentication token.**

## 38. HTTP Streaming, SSE, and WebSockets

Short request/response calls drain easily; **Server-Sent Events**, WebSockets, and long streaming downloads can stay open for minutes or hours.

### Challenges

- A stream may remain open past the termination grace limit.
- Rolling deployments inevitably close active WebSocket connections.
- Old clients might depend on session/subscription state held only in the old pod's RAM.
- In-memory subscription maps require client re-subscription on reconnect.

### Resilient Design

1. Clients implement **reconnect with exponential backoff and jitter**.
2. Protocols include a **cursor/sequence ID** to resume missed events cleanly.
3. Back shared subscription state with a durable broker or external state store where required.
4. Emit protocol-level close/drain frames when possible instead of abrupt TCP resets.
5. Test rolling deployments explicitly while streaming connections are active.
6. Never grant infinite grace periods trying to keep a WebSocket alive forever.

**Graceful shutdown does not keep WebSockets alive across pod replacement.** Seamless UX comes from clean client reconnect and resync.

## 39. DB Transactions, Connection Pools, and Cleanup

During `ApplicationContext` shutdown, Spring closes **`DataSource`/HikariCP** per bean lifecycle ordering. Closing the pool prematurely while a task is still writing breaks in-flight transactions.

### Rules

- Never close `DataSource` manually from a raw signal handler while services remain active.
- Never run schema migrations inside `@PreDestroy`.
- Configure explicit **transaction timeouts** on HTTP handlers and jobs.
- Commit outbox/checkpoints before settling broker messages.
- Size shutdown budgets to let normal active queries conclude.
- Account for DNS lookups, retries, and lock waits when sizing deadlines.

### Anti-Pattern

~~~java
@PreDestroy
void shutdown() throws InterruptedException {
    // Anti-pattern: wait indefinitely hoping the database always responds.
    while (hasPendingOrders()) {
        Thread.sleep(1000);
    }
}
~~~

During a database outage, this loop hangs until forced termination and triggers recovery storms. Use **bounded draining plus durable recovery** instead.

## 40. Calculating a Shutdown Deadline with Headroom

Illustrative budget:

| Component | Target max duration |
|---|---:|
| Ingress / `EndpointSlice` propagation + `preStop` | 5 seconds |
| Normal in-flight HTTP requests | 15 seconds |
| Worker / bean cleanup | 10 seconds |
| Log/metrics flush and safety headroom | 10 seconds |
| **Suggested test total grace period** | **40 seconds** |

If you set **`terminationGracePeriodSeconds: 45`**, validate under load—this table is a rough starting estimate. A 120-second synchronous request cannot safely rely on a 45-second termination window.

### What to Change for Long-Running Work

- Switch to **`202 Accepted` + durable `jobId`** processed asynchronously.
- Tighten downstream transaction and HTTP client timeouts.
- Support idempotent client retries.
- Checkpoint long-running jobs.
- Write large reports to Blob Storage and return a fetch URL/ID upon completion.

### Never Add Deadlines Naively

Spring executes multiple shutdown phases, some sequential and some parallel, while network propagation and `preStop` may overlap differently per platform. Always **measure wall-clock elapsed time from `SIGTERM`/scale-in to process exit** instead of merely adding YAML numbers.

## 41. Local Experiment: Slow Request and `docker stop`

To verify draining locally, add a controller active **only under a lab profile**:

~~~java
package com.example.orders.lab;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@Profile("local-lab")
@RestController
public class SlowLabController {

    @GetMapping("/lab/slow")
    public ResponseEntity<Map<String, String>> slow(
            @RequestParam(defaultValue = "8") int seconds)
            throws InterruptedException {
        int boundedSeconds = Math.min(Math.max(seconds, 0), 20);
        Thread.sleep(boundedSeconds * 1000L);
        return ResponseEntity.ok(Map.of(
            "result", "completed",
            "finishedAt", Instant.now().toString()
        ));
    }
}
~~~

**This lab endpoint merely sleeps without running business transactions.** Never enable `local-lab` in public or production environments.

### Docker Experiment

Terminal 1:

~~~bash
./mvnw -B clean verify
docker build -t orders-api:lab .
docker run -d --name orders-api \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local-lab \
  orders-api:lab
~~~

Terminal 2 (once readiness reports UP):

~~~bash
curl --silent --show-error -i \
  "http://localhost:8080/lab/slow?seconds=12"
~~~

Terminal 3 (while the request is in flight):

~~~bash
docker stop --time 45 orders-api
~~~

After container exit:

~~~bash
docker logs orders-api
docker inspect orders-api --format '{{.State.ExitCode}}'
docker rm orders-api
~~~

**Experiment limits:** `docker stop` validates signal delivery and JVM draining locally, but does not reproduce Kubernetes endpoint deregistration or Azure ingress lag. Zero-downtime verification across replicas requires an AKS/ACA lab with an active routing layer. Seeing 200 OK on one slow request proves draining worked for that case—**it does not prove every race condition is eliminated**.

## 42. Testing Forced Termination to Prove Durability

Do not stop at testing gentle shutdowns:

~~~text
Test A: SIGTERM with 45s grace
  -> Slow request can finish if time permits.

Test B: SIGKILL / kill -9 on lab container
  -> No @PreDestroy guarantee.
  -> Database and queues must recover via transactions and retries.
~~~

In a **sandbox you own**, run:

~~~bash
docker kill --signal=SIGKILL orders-api
~~~

Run this only on your test container using dummy data—never against production. When termination hooks never run:

- Uncommitted DB transactions must roll back cleanly.
- Committed DB transactions whose HTTP response dropped rely on idempotency.
- Unsettled queue messages get redelivered, so workers must deduplicate.
- Partially written local files are untrustworthy and never treated as source of truth.

**If a forced-kill test drops orders or sends duplicate emails, increasing graceful timeout will not fix the bug.** Fix transactions, persistence, message settlement, and replay safety.

## 43. Signal Handling in Java and Container Entrypoints

Quick check inside a running container:

~~~text
PID 1: java -jar /app/orders-api.jar  -> usually receives SIGTERM directly

PID 1: /bin/sh start.sh
 PID 7: java -jar /app/orders-api.jar
  -> shell may not forward signals properly
~~~

Whenever using a shell wrapper, use **`exec`** so the JVM replaces the shell:

~~~sh
#!/bin/sh
set -eu
exec java $JAVA_TOOL_OPTIONS -jar /app/orders-api.jar
~~~

**Warning:** unquoted `$JAVA_TOOL_OPTIONS` risks shell word-splitting and escaping bugs. Because the JVM reads `JAVA_TOOL_OPTIONS` from the environment automatically, the safer script is simply:

~~~sh
#!/bin/sh
set -eu
exec java -jar /app/orders-api.jar
~~~

`JAVA_TOOL_OPTIONS` still applies automatically. Even simpler, stick with a JSON-array `ENTRYPOINT` in your Dockerfile whenever no wrapper script is needed, and test signal delivery on your exact base image.

### Should You Write a Custom JVM Shutdown Hook?

Only for unmanaged resources that cannot participate in the Spring bean lifecycle. Avoid duplicating `@PreDestroy`/`DisposableBean`/`SmartLifecycle` logic, which introduces races, and enforce bounded timeouts, idempotency, and minimal logging on every cleanup step.

## 44. Observability for Probes and Shutdown

Track these signal groups to evaluate effectiveness:

| Group | Signals to observe | Meaning |
|---|---|---|
| **Startup** | JVM start → liveness UP → readiness UP | Warm-up duration and cold starts |
| **Readiness** | Probe success/failure, ready pod count | Traffic routing and rollback triggers |
| **Liveness** | Restart counts, failure reasons | Crashes, deadlocks, or misconfiguration |
| **HTTP** | 5xx, 429, connection resets, p95/p99 | User experience during rollouts |
| **Shutdown** | `SIGTERM` received, shutdown duration, force-kills | Actual grace budget consumption |
| **Async** | In-flight jobs, queue depth, retries, dead-letter | Work completion during scale-in |
| **DB** | Active/pending pool connections, tx rollbacks | Downstream saturation and cleanup |
| **JVM** | Heap, RSS, GC pauses, native memory | OOM kills and false-positive probe timeouts |
| **Cost** | Warm replicas, plan capacity, log ingestion | Cost impact of HA and probe frequency |

**Azure Monitor, Application Insights, Container Insights, Log Analytics, and Micrometer/OpenTelemetry** combine to capture these metrics, though not every item exists out of the box—several require **custom application instrumentation**.

### Structured Shutdown Event Log

~~~json
{
  "event": "application_shutdown_started",
  "appVersion": "orders-api-1.0.0",
  "replicaRef": "pod-hash-opaque",
  "reason": "SIGTERM",
  "inFlightRequests": 7,
  "inFlightJobs": 2,
  "timestamp": "2026-11-20T10:00:00Z"
}
~~~

This JSON is **illustrative**; Spring Boot does not emit this exact custom JSON automatically or always know the host reason behind `SIGTERM`. Emit sanitized lifecycle telemetry if helpful—never log secrets, request payloads, or PII.

### Separating Deployment Faults from Application Faults

A **readiness failure** caused by DB DNS can appear next to **image pull** or **entrypoint** failures, yet each has a different fix. Correlate `appVersion`/image digest, deployment windows, pod events, ingress errors, health transitions, and resource limits to triage accurately.

## 45. Cost vs. Availability Trade-Offs

Adding replicas and extending grace windows improves resilience, with clear trade-offs:

- **`minReplicas: 2`** over 0/1 carries steady baseline compute costs while cutting cold-start and single-point-of-failure risks.
- **`maxSurge: 1`** temporarily requires extra node or container capacity during rolling updates.
- Generous `startupProbe` budgets avoid premature restarts, though broken builds are detected slightly slower.
- Health Check with too few instances cannot failover if zero healthy spare capacity exists.
- Logging noisy probe hits every 5 seconds with bulky JSON inflates Log Analytics ingestion costs.
- Overly long drains slow scale-in and keep extra replicas running longer.

### Capacity Budget Example

~~~text
Assumed unit: each replica requires 1 CPU + 1.5 GiB RAM
  Production steady state: 3 replicas
  RollingUpdate maxSurge:  1 replica
  Peak during rollout:     4 replicas
~~~

Nodes or hosting plans must fit **4 replicas** during rollout; otherwise, the surge pod sits `Pending` and deployments stall. On AKS, extra capacity nodes increase compute bills; on Container Apps, scaling and consumption/workload profile pricing apply per plan. **Numbers above illustrate capacity planning, not Azure pricing.**

## 46. Scenario A: Deployment Stuck in `CrashLoopBackOff`

**Context:** after deploying a new AKS build, pods enter **`CrashLoopBackOff`** following liveness failures.

### Likely Causes

1. Spring Boot takes 80 seconds to start while liveness begins polling too early.
2. Probes hit port 80 while Java listens on 8080.
3. `/actuator/health/liveness` returns 401 or 302.
4. Containers get `OOMKilled` due to undersized memory limits.
5. Runtime JDK is older than the compiled class bytecode.
6. Startup crashes on missing environment variables or DB credentials.

### Runbook

~~~bash
kubectl describe pod <POD_NAME> -n <LAB_NAMESPACE>
kubectl logs <POD_NAME> -n <LAB_NAMESPACE> --previous
kubectl get deployment orders-api -n <LAB_NAMESPACE> -o yaml
~~~

Classify and fix:

- **Legitimate slow startup:** add a `startupProbe` sized to measured boot times.
- **Wrong port/path:** align probe port, container `targetPort`, and Spring config.
- **401/302:** permit minimal health paths in security routing while keeping business APIs protected.
- **`OOMKilled`:** profile heap/non-heap/RSS, adjust JVM flags or raise memory limits cleanly.
- **`NoClassDefFoundError`/`UnsupportedClassVersionError`:** align build and runtime JDKs.
- **Missing secret:** fix managed identity or vault references—never embed passwords in the image.

**Never crank `failureThreshold` arbitrarily high to hide crashing JVMs**; `startupProbe` only helps apps that are genuinely making startup progress.

## 47. Scenario B: App Service Health Check Returns 401

**Context:** Spring Boot uses Spring Security. Logged-in users work normally, yet App Service Health Check repeatedly marks instances unhealthy.

### Investigation

1. Check the configured **Health check path** in App Service.
2. Request the path from an appropriate network context, inspecting status codes and redirects.
3. Review `SecurityFilterChain` matchers and ordering.
4. Verify `management.endpoints.web.base-path` if customized.
5. Confirm probes hit the actual application port and hostname.
6. If routed through a proxy/gateway, check path rewrites and gateway auth policies.

### Fix

Allow unauthenticated access strictly to the minimal health path (returning non-sensitive status), reinforced by network/access restrictions where needed. Never permit all of `/actuator/**` (exposing `/heapdump`, `/env`, `/loggers`, `/shutdown`) just to satisfy health checks.

**Never let health URLs return HTTP 302 to `/login` or HTTP 200 HTML error pages**—the platform misinterprets application state.

## 48. Scenario C: Rolling Update Causes 5xxs Despite All Pods Ready

**Context:** while rolling out `orders-api` v2, clients see sporadic HTTP 502/503s or connection resets even though Kubernetes shows pods mostly `Ready`.

### Possible Causes

- `EndpointSlice` / ingress upstream removal lagged behind pod termination.
- The JVM handled `SIGTERM` and paused its listener before gateways stopped routing new requests.
- Readiness/liveness stayed green while servlet thread pools backed up.
- Long-lived keep-alive or HTTP/2 connections kept hitting terminating pods.
- v2 introduced DB schema changes incompatible with still-running v1 pods.
- Surge pods stalled `Pending` for lack of node capacity.

### Step-by-Step Runbook

1. Correlate timestamps: rollout start, pod `Terminating`, `SIGTERM`, and failed HTTP responses.
2. Compare ingress 5xx logs against Java logs/traces and connection resets.
3. Inspect readiness transitions, `EndpointSlice` states, and ingress controller logs.
4. Measure actual shutdown elapsed time to detect force-kills or timeouts.
5. Test a brief **`preStop` drain delay** in sandbox and re-measure—do not inflate endlessly.
6. Review **`maxUnavailable`, `maxSurge`, `minReadySeconds`, and `terminationGracePeriodSeconds`**.
7. Verify backward schema compatibility between v1 and v2.
8. Verify client-side retries and API idempotency for dropped connections.

**Never assume `maxUnavailable: 0` guarantees zero 5xxs.** Zero-downtime requires end-to-end verification across ingress, app, and database layers, not one Kubernetes field.

## 49. Scenario D: Worker Generates Duplicate Invoices During Scale-In

**Context:** a Spring Boot worker consumes Service Bus messages, creates an invoice row in the DB, and sends an email. ACA scales down from 4 replicas to 1, and an in-flight message is redelivered.

### Problem

The worker **committed the DB transaction** just before termination stopped it from settling the queue message; another replica picks up the redelivered message and issues a duplicate invoice.

### Proper Design

~~~text
Message eventId + tenantId
     |
     v
Database unique constraint (tenantId,eventId)
     |
     +-- Already processed -> safe replay / no duplicate
     |
     +-- New -> create invoice + outbox email event
                     |
                     v
                 Commit transaction
                     |
                     v
                Complete queue message
~~~

Because sending email is an external side effect outside the DB transaction, combine a **transactional outbox with sender idempotency/deduplication** instead of pretending email delivery and queue settlement share an atomic transaction.

### Verification

- Scale down mid-batch while messages execute.
- Force-kill between DB commit and broker completion in a **sandbox/mock**.
- Replay an identical `eventId`.
- Inspect DB unique constraints and outbound email counts.
- Ensure duplicates resolve cleanly without infinite poison-message retry loops.

**Graceful shutdown lowers interruption odds, but never replaces business idempotency.**

## 50. Scenario E: Health Endpoint Reports UP While App Cannot Serve Traffic

**Context:** `/actuator/health/liveness` returns 200 OK, yet business endpoints return 503 due to HikariCP pool exhaustion or slow queries.

### Why

Liveness checks only whether the process is alive. When readiness checks `readinessState` alone, it also stays UP despite local connection pool starvation.

### Resolution

1. Collect **Hikari active/idle/pending/timeout** metrics and p95 query latency.
2. Enforce connection/transaction timeouts and circuit breakers.
3. Determine whether the issue is a shared DB outage or a single degraded replica.
4. Consider a **very lightweight** custom readiness indicator only for instance-local failures impacting all traffic.
5. Never put the database inside liveness.
6. Run safe, low-frequency synthetic business transaction checks.
7. Alert on business error rates and latency independently of health endpoints.

**Technical health checks never prove full domain correctness**—an app can report `UP` while shipping broken authorization, schemas, or business rules.

## 51. Scenario F: JVM Exits Abruptly Despite Graceful Shutdown Config

**Context:** `server.shutdown=graceful` and a 30s timeout are set, yet Spring Boot containers vanish immediately on scale-in, snapping 10-second requests mid-flight.

### Checklist of Root Causes

- Shell entrypoint failed to forward `SIGTERM` or sent it to a wrapper parent instead of Java.
- Host termination grace was shorter than request duration.
- Deployment ran an unexpected Spring Boot or embedded server version.
- Container hit `OOMKilled` / `SIGKILL`, bypassing graceful handling.
- Embedded web server drained, while unmanaged `@Async`/background jobs stayed outside Spring lifecycle.
- Application code invoked `System.exit` inside a handler.
- A health-check restart fired rather than a controlled rollout.

### Diagnostic Path

~~~text
Container start command / PID 1
        |
        v
Signal received? SIGTERM or SIGKILL?
        |
        v
Did Spring Boot shutdown logs/lifecycle events run?
        |
        v
Elapsed time vs platform grace
        |
        v
In-flight request / worker state / DB commit outcome
~~~

**No Spring Boot property fixes `SIGKILL` or sudden host failure.** Whenever forced kills occur, rely on durable recovery and idempotency.

## 52. Automated Testing and CI/CD Release Gates

Pipelines should verify **both artifacts and runtime lifecycle**, not compilation alone:

~~~mermaid
flowchart TD
    A[Commit Java + config] --> B[Maven verify + security scan]
    B --> C[Build OCI image if needed]
    C --> D[Run container local + health probes]
    D --> E[Simulate SIGTERM during slow request]
    E --> F[Simulate forced kill + idempotency]
    F --> G[Deploy staging Azure]
    G --> H[Verify ingress/readiness/startup]
    H --> I[Rolling rollout / revision test under load]
    I --> J{SLO + errors + secrets checks pass?}
    J -- No --> K[Stop and investigate]
    J -- Yes --> L[Promote approved artifact]
    L --> M[Monitor + rollback plan]
~~~

### Automatable Checks

| Test | Pass criteria |
|---|---|
| **Artifact build** | Clean compile, passing tests, executable JAR starts |
| **Image execution** | Non-root user, right JDK/port, zero leaked secrets |
| **Startup** | Liveness/readiness flip cleanly within startup budget |
| **Readiness** | Unready instances receive zero routed test traffic |
| **Liveness** | Simulated external DB outage does not restart every instance |
| **Graceful `SIGTERM`** | Short in-flight requests inside the budget complete cleanly |
| **Forced termination** | Idempotent retries and durable state stay consistent |
| **Rolling update** | 5xx errors stay within canary thresholds |
| **Security** | Minimal unauthenticated health output; business APIs demand auth |
| **Regression** | Overlapping old/new builds maintain DB and event compatibility |
| **Observability** | Startup/shutdown events, traces, errors, and resource metrics emit |
| **Cost** | Replicas, surge, and warm capacity stay within budget |

### Clear Release Gates

- Traceable **commit SHA + immutable artifact/image digest**.
- p95 latency, 5xx rates, restarts, and shutdown duration within SLO.
- Zero leaked secrets or critical unmitigated CVEs per policy.
- Passing database and queue backward-compatibility tests.
- Health paths, ports, and grace periods reviewed as deployment code.
- Tested rollback path—not merely a paragraph in a wiki.

**Never run fault injection in production** without change approval and blast-radius controls; validate in staging/sandboxes using synthetic data.

## 53. End-to-End Lab: Zero-Disruption Spring Boot Deployments

### Context

You own **Orders API**. Requirements:

- Java 21, Spring Boot 3.x packaged as an **OCI image**.
- Exposes **`/actuator/health/liveness`** and **`/actuator/health/readiness`**.
- Configures **`server.shutdown=graceful`** and a measured `timeout-per-shutdown-phase`.
- Runs at least **two replicas** in a lab AKS or Container Apps setup.
- Ships a new build without dropping short in-flight requests beyond lab thresholds.
- Retrying `POST` after a forced kill creates zero duplicate business records.

If you lack Azure cluster access or budget, execute the **build/container/`SIGTERM` experiments locally** and document the Azure deployment manifest and test plan as an ADR—never provision a production-grade AKS cluster unnecessarily outside an approved sandbox.

### Part A — Prepare the Project

Create a minimal Spring Boot web app containing:

- Spring Web.
- Spring Boot Actuator.
- Spring Security (optional, to practice probe matcher rules).
- A `GET /api/ping` endpoint.
- A **`/lab/slow`** endpoint enabled solely under `local-lab`.
- Optional: a dummy `POST` endpoint honoring **`Idempotency-Key`**.

Minimal controller example:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok", "time", Instant.now().toString());
    }
}
~~~

Add this inside a proper Spring Boot project alongside your `@SpringBootApplication` main class and Maven/Gradle dependencies. If Spring Security is enabled, enforce your auth policy on `/api/ping` rather than leaving production business routes anonymous.

### Part B — Package JAR and Build Image

~~~bash
./mvnw -B clean verify
test -f target/orders-api.jar
docker build -t orders-api:lab .
~~~

`test -f` applies to Bash/Linux and assumes Maven `finalName=orders-api` (use `Test-Path target/orders-api.jar` in PowerShell). Start and verify probes:

~~~bash
docker run -d --name orders-api-lab \
  -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=local-lab \
  orders-api:lab

curl --fail --silent --show-error \
  http://localhost:8080/actuator/health/liveness

curl --fail --silent --show-error \
  http://localhost:8080/actuator/health/readiness
~~~

On 404, inspect Actuator dependencies, probe properties, and active profiles. On 401/403, review `SecurityFilterChain`. If connections fail, verify container ports, entrypoint, JDK, and logs.

### Part C — Measure Startup Timing

Record **four timestamps**:

~~~text
T0 = Container/pod start time
T1 = JVM start / first application log
T2 = Liveness first UP
T3 = Readiness first UP

startupDuration = T3 - T0
~~~

Collect timestamps from one synchronized clock/telemetry stream (accounting for clock skew and polling intervals if comparing systems). Average at least 5 runs in sandbox, or document small sample counts clearly.

### Part D — Test `SIGTERM` During an Active Request

1. Start a slow request via **`/lab/slow?seconds=12`**.
2. While it waits, run **`docker stop --time 45`**.
3. Record HTTP status code and response duration.
4. Inspect container exit code and shutdown logs.
5. If it failed, classify why: finished before stop, client timeout, immediate app exit, or host `SIGKILL`?
6. Repeat with a request exceeding the grace period and record expected vs. observed limits.

**Never claim zero-downtime for requests longer than the shutdown budget**—those require asynchronous jobs and idempotency.

### Part E — Test AKS or ACA in a Sandbox

On **AKS**:

- Apply the Deployment/Service from Section 21 tailored with your image, namespace, and permissions.
- Configure 2–3 replicas plus startup, readiness, and liveness probes.
- Set `maxUnavailable: 0` and an appropriate `maxSurge` matching cluster headroom.
- Watch `EndpointSlice` updates, pod events, and `kubectl rollout status`.
- Roll out a new image revision under bounded test load.
- Record 5xxs, connection resets, and shutdown durations.

On **Container Apps**:

- Deploy your image to a lab Container App with matching ingress/`targetPort`.
- Configure probes per the supported ACA schema.
- Roll out revisions and observe traffic shifting once ready.
- Set `minReplicas` appropriately if isolating scale-to-zero from rollout tests.
- Test scale-in during active requests where sandbox access permits.

**Never delete pods/nodes or alter shared ingress rules on shared/production clusters** to manufacture faults; if lacking cluster permissions, document expected vs. verified outcomes clearly.

### Part F — Test Degraded Dependency Handling

Simulate **database unavailable** using test config or a mock:

1. Liveness must **not** fail solely because the external DB drops.
2. Readiness may fail **only if your app policy deems the DB strictly mandatory**—explain your choice.
3. Business HTTP endpoints return bounded timeouts/errors instead of hanging forever.
4. Queue workers back off, retry, or dead-letter per broker policy.
5. When the DB recovers, the app avoids a reconnect storm.

The aim is validating probe policies cleanly, never breaking real databases.

### Part G — Test Forced Kill and Retry

Using a local mock or durable test DB:

1. Send `POST /orders` with an `Idempotency-Key`.
2. Force-kill the container mid-workflow at simulated checkpoints.
3. Replay the identical request and key.
4. Inspect order row counts, outbox rows, and returned payloads.
5. Verify replaying the same key with a **different payload** triggers rejection/conflict per policy.

**Never generate real monetary transactions or live customer orders during testing**—use sample data and sandboxes exclusively.

### Part H — Evidence Report

| Evidence item | Value to record |
|---|---|
| Commit SHA / artifact checksum / image digest | Verified build identifiers |
| JDK / Spring Boot versions | Exact runtime versions |
| Azure platform + SKU/region | App Service / ACA / AKS / VM per lab |
| Replica count / resource limits | Deployed sizing |
| Startup probe thresholds | `periodSeconds`, `failureThreshold`, `timeoutSeconds` |
| Readiness / liveness paths | HTTP codes and timings |
| Graceful config | `server.shutdown`, Spring phase timeout |
| Host termination deadline | Configured grace value |
| Slow request outcome | HTTP status, latency, logs |
| Forced kill outcome | DB/queue idempotency proof |
| Rolling release outcome | 5xx counts, restarts, time-to-ready |
| Security | Zero secret exposure; minimal health output |
| Cost | Compute/replica, log ingestion, cleanup status |

### Part I — Safe Cleanup

- Delete only **lab containers** and resources you own.
- Remove test instances, staging revisions, or temporary nodes per policy.
- Retain redacted logs/samples for learning evidence if permitted.
- Review Azure Cost Management because App Service plans, ACA environments, AKS nodes, ACRs, and Log Analytics workspaces may continue billing.
- Never delete shared clusters, registries, or namespaces belonging to other teams.

## 54. Production-Readiness Checklist

- [ ] **Executable JAR** or OCI image built and tested from an immutable commit SHA.
- [ ] Supported JDK and Spring Boot versions match between CI and Azure runtime.
- [ ] Container image scanned, secret-free, and running non-root where feasible.
- [ ] Container entrypoint forwards `SIGTERM` directly to the JVM rather than trapping it in a shell.
- [ ] Ports, ingress `targetPort`, Service ports, and Health Check paths verified aligned.
- [ ] Actuator health probes enabled with minimal responses exposing zero stack traces or secrets.
- [ ] `SecurityFilterChain` permits strictly required health paths while enforcing auth on business routes.
- [ ] Liveness tracks process health only—never shared databases or external APIs.
- [ ] Readiness reflects true traffic readiness under reviewed dependency policies.
- [ ] Startup probe budget derived from measured p95/p99 startup time in a matching environment.
- [ ] Probes run on the main application port, or separate management ports are paired with live synthetic checks.
- [ ] `server.shutdown=graceful`, phase timeouts, and host termination deadlines are configured and coordinated.
- [ ] Total shutdown budget accounts for `preStop`, in-flight requests, cleanup, and headroom, verified by measurement.
- [ ] No infinite sleeps in `@PreDestroy`, no `System.exit`, and no public Actuator `/shutdown`.
- [ ] Custom threads, schedulers, and clients implement bounded shutdown lifecycles.
- [ ] Long-running business jobs rely on durable queues/checkpoints instead of RAM alone.
- [ ] Service Bus/Kafka consumers stop intake first, commit/checkpoint, and settle messages cleanly.
- [ ] Idempotency protects `POST` endpoints and broker redeliveries across forced kills.
- [ ] HTTP streaming and WebSocket clients handle reconnect and state resync cleanly.
- [ ] Database connection pools fit DB capacity limits across autoscale and `maxSurge` peaks.
- [ ] AKS Deployments define update strategy, probes, termination grace, and resource requests/limits.
- [ ] AKS PDBs, zone spread, and ingress convergence validated where HA applies.
- [ ] ACA probes, revisions, ingress, and scale-in behavior tested under traffic.
- [ ] App Service Health Check, slot settings, and warm-up smoke-tested.
- [ ] VM `systemd` stop timeouts and Load Balancer probes align with Spring shutdown lifecycle.
- [ ] Azure Functions triggers rely on Functions host lifecycle semantics rather than assuming Actuator.
- [ ] CI/CD runs `SIGTERM`, forced-kill, and rolling deployment tests in sandbox environments.
- [ ] Metrics and alerts watch 5xxs, restarts, readiness, startup lag, active jobs, and shutdown duration.
- [ ] Documented rollback runbooks and cross-version DB schema compatibility verified.
- [ ] Compute sizing accounts for `maxSurge`, warm capacity, and log ingestion costs.
- [ ] Zero unapproved fault injection on production resources or live data.

## 55. Self-Check Questions

1. How does an executable Spring Boot JAR differ from a plain JAR and a WAR?
2. Why does `EXPOSE 8080` in an OCI image not open a public port automatically?
3. How does a JSON-array `ENTRYPOINT` help `SIGTERM` delivery?
4. Why must non-root containers check file ownership and temp directory permissions?
5. What error typically signals a build vs. runtime JDK version mismatch?
6. What happens if you set JVM heap equal to the entire container memory limit?
7. What distinct goals do readiness, liveness, and startup probes serve?
8. Should a pod that is `Running` yet unready receive Service traffic?
9. Why should liveness never query a shared PostgreSQL instance?
10. When might checking the DB inside readiness be appropriate?
11. What failure mode can a separate `management.server.port` hide on the main app port?
12. Should health endpoints ever expose full Actuator `/env` or `/heapdump` publicly?
13. Why is an HTTP 302 redirect to `/login` problematic for App Service Health Check?
14. What does `startupProbe`'s `failureThreshold × periodSeconds` buy you?
15. Why measure real Spring Boot startup duration instead of guessing thresholds?
16. Does `readinessProbe` returning false restart a pod? How does it differ from liveness?
17. Does `maxUnavailable: 0` guarantee zero downtime unconditionally?
18. Does `preStop` consume time inside `terminationGracePeriodSeconds` or add extra time on top?
19. What happens if a `preStop` hook invokes `/bin/sh` on a distroless image?
20. Do readiness transitions propagate instantaneously to every ingress and gateway?
21. Which Spring Boot properties enable graceful shutdown?
22. Is `timeout-per-shutdown-phase` equal to the total process shutdown deadline?
23. Why should you never call `System.exit` inside `@PreDestroy`?
24. Are shutdown hooks guaranteed to run during `SIGKILL`, OOM kills, or sudden node power loss?
25. When is `ThreadPoolTaskExecutor` `waitForTasksToCompleteOnShutdown` helpful vs. risky?
26. What problem arises when running `@Scheduled` across multiple replicas?
27. What happens if a worker commits to the database and crashes before completing the queue message?
28. Why must an `Idempotency-Key` be scoped to user, tenant, and request payload?
29. Can a WebSocket connection survive pod replacement indefinitely?
30. When should a long HTTP call become a durable asynchronous job?
31. Is it contradictory for an API to report liveness UP while returning business 503s?
32. How does App Service Health Check differ from Kubernetes readiness probes?
33. How do Container Apps revisions help canary releases and rollbacks?
34. Can an AKS `PodDisruptionBudget` block forced OOM kills?
35. Why inspect effective App Settings and DB credentials before an App Service slot swap?
36. How should VM `systemd` `TimeoutStopSec` align with Spring's shutdown phase timeout?
37. Does an Azure Functions Service Bus trigger require a Tomcat Actuator endpoint?
38. Which metrics help evaluate graceful shutdown during a rollout?
39. If a new container image changes the DB schema, is rolling back code alone enough?
40. What does a local `docker stop` experiment prove, and what does it leave unproven?

## 56. References

- [Spring Boot production-ready features](https://docs.spring.io/spring-boot/reference/actuator/index.html) — Actuator, health, metrics, and probes.
- [Spring Boot Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) — `ApplicationAvailability`, liveness/readiness.
- [Spring Boot graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — server shutdown and lifecycle timeouts.
- [Spring Framework TaskExecutor and scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — async tasks, scheduling, executor lifecycle.
- [Azure App Service for Java](https://learn.microsoft.com/azure/app-service/configure-language-java) — Java hosting, startup, and application settings.
- [Azure App Service Health Check](https://learn.microsoft.com/azure/app-service/monitor-instances-health-check) — health probe integration.
- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — warm-up, swaps, and sticky settings.
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview) — environments, replicas, and revisions.
- [Azure Container Apps health probes](https://learn.microsoft.com/azure/container-apps/health-probes) — container-level readiness, liveness, and startup.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — staged releases and traffic splitting.
- [AKS introduction](https://learn.microsoft.com/azure/aks/intro-kubernetes) — managed Kubernetes.
- [Kubernetes liveness, readiness and startup probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — probe semantics.
- [Kubernetes Pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) — `SIGTERM`, hooks, grace periods, forced termination.
- [Kubernetes Deployment rolling updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — rollout strategies and availability.
- [Kubernetes PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/) — voluntary disruptions.
- [Azure Functions Java developer guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java Functions hosting and lifecycle.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, and alerts.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — plan, node, and replica cost estimation.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, security, operations, performance, and cost.

**Conclusion:** Packaging Spring Boot into a JAR or OCI image is only step one. An Azure-ready release requires **meaningful health probes, accurate application readiness, `SIGTERM` reaching the JVM, graceful shutdown backed by realistic deadlines, checkpointed/idempotent workers, and rollouts validated under load**. App Service, Container Apps, AKS, VMs, and Functions each follow distinct lifecycles, so never copy-paste one host's probe config blindly onto another. Test **normal startup, failed readiness, shared dependency outages, `SIGTERM` with active requests, and forced termination** in a sandbox—then review metrics, security, and costs before promoting to production. The goal is never an artificially green dashboard, but an application that **accepts traffic when genuinely ready, drains orderly when signaled, and recovers domain state cleanly whenever forced to stop**.
