# Packaging the Application and Distinguishing Runtime Requirements Across Spring Cloud Gateway Variants

Packaging a **Spring Cloud Gateway** application is not simply creating a JAR and placing it into Docker. A Gateway may build successfully yet fail to find routes, accidentally run on a Servlet runtime instead of Reactor Netty, fail to connect to Redis or a service registry, or be repeatedly restarted by Kubernetes due to misconfigured health probes. These errors often surface only after deploying the application into an environment with real ingress, TLS, multiple replicas, and security policies.

This lesson belongs to the **Deployment** chapter of the **SPRING_CLOUD_GATEWAY** module, focusing on **packaging the application and distinguishing runtime requirements for each variant**. We will choose accurately among **Gateway Server WebFlux**, **Gateway Server Web MVC**, **ProxyExchange WebFlux**, and **ProxyExchange MVC**, then build an executable JAR/OCI image, configure the Java runtime, container resources, secrets, service discovery, route predicates/filters, authentication, rate limiting, circuit breaker, retry, TLS, and observability.

After studying this lesson, you will be able to:

1. Distinguish **web stack/runtime** from **distribution artifact type**.
2. Choose the right dependencies, Spring Boot–Spring Cloud BOM, and Java runtime per variant.
3. Package an executable JAR, container image, and verify the application runs the right HTTP server.
4. Configure routes, profiles, service discovery, Redis, TLS/JWT, and secrets without depending on developer machine paths.
5. Design startup/readiness/liveness, shutdown, rolling updates, and long-lived connection recovery in Kubernetes.
6. Set up smoke/integration tests before considering an image production-ready.

> **Version Scope:** Spring Cloud Gateway has renamed several starters and configuration prefixes across release trains. Examples below use common names in modern Gateway lines; verify the **documentation and BOM for your target deployment version**. Java 21 in the Dockerfile is an **illustrative choice** and must match the Spring Boot/Gateway baseline; it is not mandatory for all versions. This lesson does not claim that any sample Kubernetes configuration or image meets production security standards without testing.

## 1. Two Decisions: Application Variant and Artifact Format

Two axes must be separated:

- **Variant:** Gateway Server WebFlux, Gateway Server Web MVC, ProxyExchange WebFlux, or ProxyExchange MVC.
- **Artifact:** executable **JAR**, **OCI container image**, or within version support scope, **native executable/AOT**.

An executable JAR can start Reactor Netty **or** a Servlet container depending on classpath/config. A Docker image merely holds files, a runtime, and a run command; **Docker does not automatically turn a Servlet app into a reactive app**.

| Variant | Primary stack/runtime | Extension points | Best suited for |
|---|---|---|---|
| **Gateway Server WebFlux** | Spring WebFlux + Project Reactor, typically **Reactor Netty** | Reactive route predicates, `GatewayFilter`, `GlobalFilter` | Centralized API Gateway, many routes/filters and concurrent I/O traffic |
| **Gateway Server Web MVC** | Spring MVC / **Servlet container** | WebMvc.fn `RouterFunction`, handler filter functions | Gateway integrated with Servlet/MVC ecosystem |
| **ProxyExchange WebFlux** | WebFlux runtime | Controller accepting `ProxyExchange<T>`, returning `Mono<ResponseEntity<?>>` | BFF/proxying a few endpoints via reactive controller |
| **ProxyExchange MVC** | Spring MVC / Servlet | Controller accepting `ProxyExchange<T>`, returning `ResponseEntity<?>` | Simple BFF/proxy on MVC |

**Gateway Server** provides a route engine, predicates, filter factories, and features such as RequestRateLimiter/Retry depending on the variant. **ProxyExchange** is a proxying tool inside controllers; adding its dependency **does not automatically activate** the Gateway Server route/filter chain.

### Variant Selection Diagram

~~~mermaid
flowchart TD
    A["Application needs to call/proxy microservices"] --> B{"Need centralized route engine & filter policies?"}
    B -->|Yes| C{"Intended web stack?"}
    C -->|"Reactive WebFlux"| W["Gateway Server WebFlux"]
    C -->|"Servlet / Spring MVC"| M["Gateway Server Web MVC"]
    B -->|No, a few controller endpoints| D{"Controller stack?"}
    D -->|WebFlux| PW["ProxyExchange WebFlux"]
    D -->|MVC| PM["ProxyExchange MVC"]
    W --> J["Choose JAR / OCI image + Java runtime"]
    M --> J
    PW --> J
    PM --> J
~~~

**Do not choose based solely on small GET request RPS benchmarks.** Real performance depends on blocking operations, security filters, payload, concurrency, backend latency, retries, connection pools, TLS, and memory.

## 2. Gateway Server WebFlux: Netty and Reactive Pipeline

In Gateway Server WebFlux, Spring WebFlux and Project Reactor orchestrate the asynchronous request/response processing pipeline. The Gateway Server WebFlux model typically uses **Reactor Netty HTTP server and HTTP client**.

### Critical Runtime Requirements

- The **Server WebFlux** starter matching the Spring Cloud Gateway line.
- WebFlux/reactive application context with compatible Reactor Netty server/client.
- Custom `GatewayFilter`/`GlobalFilter` implementations use `Mono`/`Flux` and **do not block the event loop** with `Thread.sleep`, blocking JDBC, or `block()`.
- HTTP client connection pool, DNS, connect/response timeouts, and Netty direct memory are observed.
- Body filters like `CacheRequestBody` or `ModifyRequestBody` can aggregate the entire body, sharply increasing memory on large uploads.
- If using `lb://`, Spring Cloud LoadBalancer and an appropriate service discovery/resolver are required.
- If using Redis-based `RequestRateLimiter`, a compatible Redis client/config and tested fail-open/fail-closed policy are required.
- WebSocket/SSE/streaming must be tested across ingress, TLS termination, and rollouts.

### Do Not Deploy as a Traditional Servlet WAR

**Gateway Server WebFlux is not a Gateway written for an external Servlet container.** Prefer a **Boot executable JAR or OCI image running with a supported Netty runtime**. Do not rely on Spring WebFlux generally having some Servlet integration capabilities to assume that **any Gateway Server WebFlux can be dropped into Tomcat as a WAR**.

### Common Mistakes

| Mistake | Consequence |
|---|---|
| Adding `spring-boot-starter-web` just to use an MVC utility | Classpath application type conflict |
| Calling blocking SDKs on the event loop | P95/P99 spikes, requests back up |
| Buffering entire files in a GatewayFilter | Direct/heap pressure, OOMKill |
| Using WebFlux `SecurityWebFilterChain` while the app actually runs as Servlet | Security config does not work as expected |
| Assuming all route filters are built-in | Startup fails due to missing Redis/CircuitBreaker or wrong config |

## 3. Gateway Server Web MVC: Servlet, WebMvc.fn, and Thread Model

**Gateway Server Web MVC** is built on **Spring MVC/Servlet**. Its extension points are **WebMvc.fn `RouterFunction` and handler filter functions**, not `ServerWebExchange` and reactive `GatewayFilter` as in WebFlux.

### Deployment Prerequisites

- **Gateway Server Web MVC** starter compatible with Boot/Cloud.
- A supported **Servlet runtime**, typically embedded Tomcat; another Servlet container can be configured if version and dependencies permit.
- Use `SecurityFilterChain` from Spring Security Servlet.
- If custom predicates/filter logic are needed, use MVC's **GatewayRequestPredicates** and **HandlerFilterFunctions** APIs.
- Monitor Servlet threads, HTTP client connection pools, blocking calls, and request queues.
- Verify WebSocket/SSE and timeouts against the **actual Servlet stack/proxy chain**, rather than applying Netty assumptions.

| Factor | WebFlux Server | Web MVC Server |
|---|---|---|
| Common HTTP server | Reactor Netty | Embedded Servlet container |
| Request API in extensions | `ServerWebExchange` | WebMvc.fn `ServerRequest`/Servlet request |
| Filter extension | Reactive `GatewayFilter`/`GlobalFilter` | MVC handler filters |
| Security | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Blocking behavior | Can stall event loop | Holds worker threads, can cause thread exhaustion |
| Streaming/long connections | Reactive publisher lifecycle | Servlet/web server lifecycle depending on app |

**MVC is not inherently "slow"; WebFlux is not inherently "fast."** Choose based on code and operational requirements, then measure under real workload, concurrency, TLS, and downstream behavior.

## 4. ProxyExchange WebFlux and MVC: Controller-Level Runtime

**ProxyExchange** uses Spring handler methods instead of requiring a full Gateway Server route engine declaration. Example in MVC:

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogBff {

    @GetMapping("/bff/catalog")
    ResponseEntity<?> get(ProxyExchange<byte[]> proxy)
            throws Exception {
        // Server-owned URI, never take a raw URL from the client.
        return proxy.uri("https://catalog.internal.example.test/items")
            .get();
    }
}
~~~

With WebFlux, the common import is `org.springframework.cloud.gateway.webflux.ProxyExchange`, and the controller returns `Mono<ResponseEntity<?>>`. Specific packages and APIs must still be verified against the version in use.

### Things to Remember When Packaging ProxyExchange

- ProxyExchange WebFlux requires a **WebFlux** web runtime; ProxyExchange MVC requires a **Servlet/MVC** web runtime.
- ProxyExchange does not automatically include Gateway Server's `RequestRateLimiter`, `Retry`, `CircuitBreaker`, or dynamic route locator.
- Authentication/authorization, rate limiting, retry, breaker, and observability must be integrated **at the controller/HTTP client layer**.
- `ProxyExchange<byte[]>` can materialize the body/response in RAM; it is not inherently suitable for multi-GiB file streaming.
- When using backend URIs, only allow **server-side allowlisted** destinations to prevent open proxy/SSRF.

### When to Choose ProxyExchange?

When the application only has a few custom-handled BFF endpoints and does not need hundreds of routes and unified filter policies. If you want to manage predicates, path/header rewrites, circuit breakers, and rate limits through a Gateway control plane, **Gateway Server** is usually a better fit.

## 5. Selecting Dependencies and Boot–Cloud BOM for One Web Stack

Common artifacts in modern lines:

| Choose one variant | Illustrative artifact |
|---|---|
| Gateway Server WebFlux | `spring-cloud-starter-gateway-server-webflux` |
| Gateway Server Web MVC | `spring-cloud-starter-gateway-server-webmvc` |
| ProxyExchange WebFlux | `spring-cloud-gateway-proxyexchange-webflux` |
| ProxyExchange MVC | `spring-cloud-gateway-proxyexchange-webmvc` |

Older lines may use `spring-cloud-starter-gateway`, `spring-cloud-starter-gateway-mvc`, `spring-cloud-gateway-webflux`, or `spring-cloud-gateway-mvc`. **Do not mix dependency names across multiple release trains** hoping Maven/Gradle will pick the right one automatically.

**Spring Boot BOM** manages Spring Framework, Reactor, Netty, Jackson, Micrometer, etc., and **Spring Cloud BOM** manages Gateway, LoadBalancer, CircuitBreaker, DiscoveryClient, etc. They must be chosen **from the compatibility matrix**, rather than picking the latest version of each individual artifact.

### Classpath Inspection

1. Confirm whether the app uses a **reactive** or **servlet** application type.
2. Check starters that transitively pull in Spring MVC and WebFlux.
3. Check the Java bytecode target and the JRE inside the image.
4. Verify Redis, Security, LoadBalancer, and CircuitBreaker dependencies are present when routes need them.
5. Check for conflicting/duplicate Reactor Netty or Boot autoconfiguration versions.
6. Execute startup and HTTP smoke tests; **successful compilation does not prove correct runtime behavior**.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Boot in common configurations prioritizes the **Servlet/MVC application type**. This is especially dangerous if you intend to run **Gateway Server WebFlux**.

## 6. Gradle: Dependency Templates for Four Different Applications

The snippets below assume the project has configured the Spring Boot plugin and a **compatible Boot/Cloud BOM**. **Pick exactly one** group per application; the code blocks are mutually exclusive alternatives, not meant to be combined in the same `build.gradle`.

### Gateway Server WebFlux

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

### Gateway Server Web MVC

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### ProxyExchange WebFlux

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

### ProxyExchange MVC

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

These are **dependency skeletons**, not production-ready builds. Security resource server/JWT, Redis, CircuitBreaker, DiscoveryClient, and tracing should only be added when required by features and backed by corresponding configuration/tests.

## 7. Maven Also Needs Boot Parent/Cloud BOM and Executable Packaging

With Maven, configure the Spring Boot parent or Boot dependency management alongside a compatible Spring Cloud dependency BOM. **Partial `pom.xml`** example, insufficient to build standalone:

~~~xml
<properties>
  <java.version>21</java.version>
  <spring-cloud.version>RELEASE_TRAIN_MATCHING_BOOT</spring-cloud.version>
</properties>

<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-dependencies</artifactId>
      <version>${spring-cloud.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
  </dependency>
</dependencies>
~~~

The value `RELEASE_TRAIN_MATCHING_BOOT` is only a placeholder: replace it with a Spring Cloud release train compatible with your Spring Boot baseline. In XML, `${spring-cloud.version}` references the declared property; do not leave the placeholder literal when building. You must configure **spring-boot-maven-plugin**/**repackage** properly if you want an executable Boot JAR. `mvn package` creating a plain JAR is insufficient if the plugin is missing.

## 8. Choosing the Java Runtime for the Executable JAR

Information to lock down before building:

| Parameter | Question |
|---|---|
| Compile JDK | Which version runs Gradle/Maven? |
| Java bytecode target | Which Java version is the JAR compiled for? |
| Runtime JRE in image | Does it support the class version and BOM in use? |
| Base image | Does it have security patches updated and the right architecture? |
| JVM flags | Are they appropriate for memory/cgroup and GC policy? |
| Truststore | Does the Java runtime trust the CA of backend/JWK/Redis TLS? |
| Native libraries | Are image architecture and runtime libraries sufficient? |

Classic mistake: a JAR built for Java 21 running on JRE 17 triggers `UnsupportedClassVersionError`. Conversely, **a newer JRE does not automatically guarantee vendor support for an older Spring Boot version**.

### Verification in CI

~~~bash
java -version
./gradlew clean test bootJar
ls -lh build/libs/
~~~

These commands are illustrative for hands-on practice; this article does not execute builds. **Do not use `-x test` or `-DskipTests` as the primary path of a production pipeline**.

## 9. Creating an Executable JAR: `bootJar` vs `jar`

With the Spring Boot Gradle plugin:

~~~groovy
// Fixed artifact name so the Dockerfile can easily COPY it.
tasks.named('bootJar') {
    archiveFileName = 'gateway-app.jar'
}
~~~

Build and test startup:

~~~bash
./gradlew clean test bootJar

java -jar build/libs/gateway-app.jar \
  --spring.profiles.active=lab
~~~

A Boot executable JAR is packaged with the launcher and runtime dependencies matching the Boot plugin. A plain `jar` only contains application classes and may **lack dependencies**, causing missing-class errors on `java -jar`.

With Maven and the corresponding Boot plugin/repackage:

~~~bash
./mvnw verify

# Pick the actual JAR name from target/.
java -jar target/gateway-app.jar
~~~

`target/gateway-app.jar` is an example name and will not exist if `artifactId`/`finalName` differs. Whether using Maven or Gradle, you must prove **the application context starts and backend routes run properly**.

## 10. OCI Image: Buildpacks and Dockerfile

A packaged Gateway can produce an OCI image via:

1. **Spring Boot Cloud Native Buildpacks** via `bootBuildImage`/`spring-boot:build-image`.
2. **Dockerfile** based on a compatible JRE runtime.

Neither method decides whether the app uses Netty or Tomcat; the web stack lives in dependencies/config.

### Buildpacks

~~~bash
# Gradle (when supported by the Spring Boot plugin):
./gradlew bootBuildImage \
  --imageName=registry.example.test/team/gateway-app:lab

# Maven:
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.test/team/gateway-app:lab
~~~

Buildpacks can leverage caching/layering, supporting better reproducible deployments when governed properly. However, image builder/runtime compatibility, registry credentials, and SBOM scanning still must be verified in CI.

### Why Avoid `latest`?

A mutable tag like `latest` can point to a different image between two rollouts. For rollback and auditing, prefer **immutable tags by commit SHA** or **image digests**, while recording the Boot/Cloud BOM, route config revision, and test results.

## 11. Running a Non-Root Dockerfile

Assuming `bootJar` creates `build/libs/gateway-app.jar`:

~~~dockerfile
# Java 21 is only an example; must be compatible with project runtime baseline.
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/libs/gateway-app.jar /app/app.jar

# Numeric UID/GID, do not run as root.
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Points to evaluate:

- The base image must be updated/digest-pinned, CVE-scanned, and matched to CPU architecture.
- `USER 10001:10001` may need write permissions to `/tmp`, logs/temp, and certificate locations used by the app.
- `EXPOSE 8080` is metadata only and does not publish the port to the Internet.
- Never copy credentials, keystore passwords, or private keys into the JAR/image.
- The JRE in the image must match bytecode/compiler; do not swap in a "lighter" but older runtime.
- If running with a **read-only root filesystem**, writable volumes must be mounted at the right paths; you cannot assume the container filesystem is always writable.

Build and run lab:

~~~bash
./gradlew clean test bootJar
docker build -t gateway-app:lab .
docker run --rm -p 8080:8080 gateway-app:lab
~~~

**Localhost trap:** `localhost` inside a container refers to **that container itself**, not the host machine or another backend container. A route `http://localhost:9090` may work in an IDE yet return 502 when deployed to Docker/Kubernetes.

## 12. Container Memory: Do Not Set Xmx Equal to Memory Limit

A WebFlux Gateway uses heap **and** Netty **direct memory**; MVC uses heap, thread stacks, buffer pools, metaspace, and various native allocations.

~~~text
Container memory limit: 1024 MiB (example)
Heap around 55-60%: 560-615 MiB (starting point)
Remainder: direct memory, metaspace, thread stacks, TLS, native/JVM
~~~

This is an **illustrative estimate**, not a standard ratio for every workload. In Netty, streaming and high connection counts can grow direct memory; in MVC, worker threads and blocking I/O create different pressures.

A common JVM flag:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
java -jar /app/app.jar
~~~

**Do not configure `-Xmx=1024m` when the container only has 1 GiB** and ignore other regions. Track RSS/container memory, heap, GC, direct memory, metaspace, file descriptors, threads, and connection pools under increasing load.

### Measuring by Variant

| Variant | Common bottlenecks |
|---|---|
| WebFlux Server | Event-loop blocking, Netty pending acquire, direct memory |
| Web MVC Server | Servlet threads waiting, HTTP client pool/DB pool saturation |
| ProxyExchange WebFlux | Controller blocking, body aggregation, reactive context |
| ProxyExchange MVC | Threads held by slow outbound calls and body buffering |

**Virtual threads** are a conditional option on supported Spring Boot/Servlet versions, but they do not make ProxyExchange MVC reactive and do not remove HTTP client/DB pool limits.

## 13. Externalizing Environment Configuration from the Image

A good image should be deployable to staging/production **without rebuilding to change a backend host or JWT issuer**. Configuration sources may include:

- Spring Boot profiles/property sources;
- Kubernetes **ConfigMap** for non-secret configuration;
- Kubernetes **Secret**/secret manager for credentials;
- Externalized route definitions/config repository with access control;
- Mounted files for CA truststores, TLS certificates, and client keys.

### Gateway Server WebFlux Route Example (Modern Line Namespace)

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  application:
    name: gateway-edge
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: http://catalog.default.svc.cluster.local:8080
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Some release trains use the prefix `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. MVC has a different namespace and route DSL. **Verify effective property binding and actual routes** for your exact version; do not declare both prefixes and assume the same routes are always loaded.

In the example, the URI uses **Kubernetes Service DNS** directly, not `lb://`. This target relies on Kubernetes Service DNS/networking and does not invoke the Gateway's LoadBalancer discovery filter.

### Precedence and Environment Variables

Spring Boot supports relaxed binding, but regexes, map keys, SpEL, and complex route filter args can be altered when mapped to environment variable names. For dynamic routes or complex filter chains, prefer reviewed/versioned configuration and verify binding via integration tests. **Never embed passwords in command lines or startup logs**.

## 14. `lb://` Is Not Kubernetes Service DNS

A route can resolve a backend in two distinct ways:

~~~mermaid
flowchart TD
    G["Gateway route URI"] --> S{"Target scheme"}
    S -->|"http://catalog.default.svc:8080"| D["Kubernetes DNS + Service routing"]
    S -->|"lb://catalog-service"| L["Spring Cloud LoadBalancer"]
    L --> DISC["DiscoveryClient / service registry"]
    D --> P["Ready backend instances"]
    DISC --> P
    P --> OUT["Egress network/TLS policy"]
~~~

| URI | Runtime needed | What to verify |
|---|---|---|
| `http://host:port` | HTTP client + DNS/route | Host, port, timeout |
| Kubernetes Service DNS | Cluster DNS, ready Service/Endpoints | Namespace, targetPort, routing |
| `lb://service-id` | LoadBalancer + compatible DiscoveryClient/resolver | Service ID and instance list |
| `https://service` | TLS trust, hostname, SNI | CA/cert SANs and renewals |
| `ws://`/`wss://` | WebSocket routing for the right variant | Upgrade, idle timeout, close/reconnect |

**`lb://` is a URI scheme understood by Gateway/LoadBalancer integration**, not a standard scheme natively supported by every HTTP client. When moving from local to cluster, confirm service IDs, discovery provider, and instance registration permissions.

**Network policies remain necessary even when services live in a registry**: a discoverable service does not mean any user should be allowed to expose it publicly through the Gateway.

## 15. Runtime Dependencies: Security, Redis, CircuitBreaker, and Retry

Features described in the module can introduce distinct runtime requirements:

| Feature | Dependencies and configuration to verify | Typical failure |
|---|---|---|
| **JWT authentication** | Spring Security matching WebFlux/MVC stack, decoder, issuer/JWK reachability, audience/scopes | Unexpected 401/403 |
| **Redis RequestRateLimiter** | Version-matched Redis client/integration, Redis DNS, TLS/auth, fail policy | Redis unavailable/429/5xx |
| **CircuitBreaker** | Compatible CircuitBreaker/Resilience4j module and filter factory, fallback URI | Missing factory, wrong fallback |
| **Retry** | Retry filter/client policy, attempts/backoff, body replay/idempotency | Duplicate POST, retry storm |
| **Service discovery** | LoadBalancer + provider, registry metadata, health | `lb://` selects no instances |
| **Local response cache** | Cache support, TTL, private/public policy | Stale data/tenant leak |
| **TLS/mTLS outbound** | Truststore and client identity when needed | `SSLHandshakeException` |
| **Observability** | Actuator/Micrometer/tracing exporter | Empty dashboards |
| **Dynamic routes** | Route source/persistence/refresh and per-node reconciliation | Gateway nodes route differently |

Do not assume every dependency in the table must be added manually: some starters pull them in transitively. **What matters is verifying the classpath, beans/factories, and actual runtime behavior**.

### Do Not Make Redis Part of Default Liveness

The Redis rate limiter can lose connectivity while the Gateway still has routes capable of serving traffic. If liveness requires Redis to be healthy, a Redis outage can cause **all Gateway Pods to restart simultaneously**, compounding the outage. Choose readiness/security failure policies according to business requirements and separate downstream monitoring from liveness.

## 16. TLS: Three Hops and Trust Boundaries

Common edge model:

~~~mermaid
flowchart LR
    C["Client HTTPS"] --> I["Ingress / CDN / LB TLS"]
    I -->|"HTTP or HTTPS"| G["Gateway"]
    G -->|"HTTPS/mTLS or private HTTP"| B["Backend"]
~~~

Three hops require separate decisions:

1. Client → ingress: public certificate, Host/SNI, HTTP/2/ALPN per support.
2. Ingress → Gateway: mTLS/TLS or private link with network isolation.
3. Gateway → backend: TLS verification, hostname/cert SAN, outbound truststore, and client certificate when using mTLS.

**Never fix TLS errors by trusting all certificates or disabling hostname verification.** Container truststores can differ from developer machines; use approved CAs and test certificate rotation.

### Forwarded Headers

After TLS termination, the Gateway may receive internal HTTP traffic while the public URL is HTTPS. `Forwarded` and `X-Forwarded-Proto`/`Host`/`For` can affect redirects, CORS, or client IP.

- Only trust forwarded headers from **trusted proxies**.
- Ingress must strip/overwrite client-supplied headers if they are used as trusted signals.
- Verify `server.forward-headers-strategy` per Boot/runtime variant.
- Do not use raw `X-Forwarded-For` for authorization or IP KeyResolvers without verifying the trust chain.
- Do not forward `Authorization`/`Cookie` to services outside the audience/trust boundary.

## 17. Startup, Readiness, and Liveness: Three Different States

In Kubernetes:

| Probe | What does it ask? | Result on failure |
|---|---|---|
| **startupProbe** | Has the application finished starting up? | Allows slow startup before liveness checks begin |
| **readinessProbe** | Should the Pod receive new traffic? | Removed from ready endpoints |
| **livenessProbe** | Does the process need to be restarted? | Container restarted |

Spring Boot Actuator supports Kubernetes probes. In supported versions, configuring:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

can expose health groups on the **main port** at `/livez` and `/readyz`. **Verify the actual paths on your version**, especially when management port and HTTP application port are separate.

### Why Can Probing Only the Management Port Mislead?

The management server can keep returning health 200 while the **main application port** has stopped serving properly. Probing on the main port checks connectivity closer to the traffic path. However, `/readyz` alone does not prove every route/backend is healthy.

**Do not put all backend health checks into liveness.** Liveness must avoid transient external dependencies that push the cluster into a restart loop. Readiness can include conditions genuinely required to serve safely, with a clearly defined failure policy.

## 18. Illustrative Kubernetes Deployment/Service

The manifest below configures a Gateway with three replicas, rolling updates, and probes on the application HTTP port:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway-edge
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: gateway-edge
  template:
    metadata:
      labels:
        app: gateway-edge
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: gateway
          image: registry.example.test/edge/gateway:sha-EXAMPLE
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=60.0"
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: temp
              mountPath: /tmp
      volumes:
        - name: temp
          emptyDir:
            sizeLimit: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-edge
spec:
  selector:
    app: gateway-edge
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### Must Be Adjusted Before Production Use

- `image` is a placeholder; replace with a signed/governed image digest.
- Resource sizing and probe intervals must be measured against startup, traffic, and SLOs.
- `/livez` and `/readyz` do not exist without proper Actuator configuration.
- `readOnlyRootFilesystem` requires mounting every writable path, not just `/tmp` if code writes elsewhere.
- Missing NetworkPolicy, Ingress/TLS, Secret/ConfigMap, HPA, PodDisruptionBudget, and RBAC.
- `maxUnavailable: 0` avoids proactively reducing ready pod count per rollout strategy, but **does not guarantee zero dropped requests**.
- If using a separate management port, ensure health on the main port still reflects the required state.

## 19. Graceful Shutdown, Drain, and Rolling Update

In Spring Boot versions supporting graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When deleting a Pod, Kubernetes stops routing new traffic after endpoint readiness changes, but endpoint propagation and load balancer state updates **are not instantaneous**.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant I as Ingress/Service
    participant G as Gateway Pod
    participant C as Client
    K->>G: SIGTERM / termination
    G->>G: Start graceful shutdown
    K->>I: Update endpoints per Pod state
    I-->>G: In-flight/new requests may arrive during propagation
    G-->>C: Complete active requests if within time
    G->>G: Cleanup and close connections
    K-->>G: SIGKILL when termination grace expires
~~~

### Do Not Assume

- `server.shutdown=graceful` does not guarantee multi-hour WebSockets will finish.
- `terminationGracePeriodSeconds=45` does not mean every 2 GiB upload will finish in 45 seconds.
- A successful rolling update does not guarantee zero client retries or connection resets.
- `preStop: sleep` can help with certain ingresses, but it also consumes the grace budget; do not add it blindly.
- A committed backend POST can create side effects even if the client receives a connection reset; idempotency is required.

### Recovery for Long-Lived Connections

| Traffic | Required contract |
|---|---|
| WebSocket | Reconnect/backoff, session recovery, and message dedup if needed |
| SSE | Heartbeat, reconnect, `Last-Event-ID` when backend supports it |
| File upload | Resumable parts/offset/checksum, partial cleanup |
| File download | HTTP Range/ETag/checksum where appropriate |
| Business POST | Idempotency key and backend-enforced deduplication |

## 20. Ingress and Gateway Can Form Two Consecutive Proxy Layers

A real deployment:

~~~text
Client
  -> CDN/WAF
  -> Ingress / L7 load balancer
  -> Spring Cloud Gateway
  -> Kubernetes Service or DiscoveryClient
  -> Backend
~~~

Each layer has its own **timeouts, retries, request-size limits, hop-by-hop headers, TLS**, and sometimes body buffering.

| Request type | Verify before going public |
|---|---|
| JSON GET/POST | Host/path rewrite, CORS, auth, deadlines, 401/403/429/5xx |
| Multipart upload | Ingress body-size, buffering, Content-Type boundary, cancel |
| Large download | 206/Range/ETag, length, streaming, checksum |
| SSE | Per-event flush, heartbeat, idle timeout, proxy buffering |
| WebSocket | Upgrade handshake, ws/wss, idle timeout, reconnect/drain |
| gRPC/HTTP/2 | ALPN, backend protocol, end-to-end variant support |
| Retry | Total attempts across ingress + Gateway + HTTP client |
| TLS | Public/inner certs, SNI, truststore, renewal |

**A `curl GET` returning 200 does not prove SSE/WebSocket/multipart work properly**, because an upstream reverse proxy might buffer bodies or strip Upgrade headers.

## 21. Securing the Image, Runtime, and Control Plane

Essential checklist:

1. Run containers non-root, drop capabilities, and use a read-only filesystem when possible.
2. Image scanning, dependency vulnerability auditing, SBOM/provenance, and immutable tags/digests.
3. Secrets outside the image/JAR, strict RBAC, and rotation policies.
4. TLS/mTLS matching trust boundaries; never disable certificate validation.
5. Network ingress/egress allowlists; prevent SSRF from dynamic route URIs.
6. Protect Actuator/Prometheus; never expose Gateway route mutation endpoints publicly.
7. Spring Security matching the variant: reactive `SecurityWebFilterChain` or servlet `SecurityFilterChain`.
8. Forward auth/session/tenant headers strictly per trust contract; do not trust user-supplied headers.
9. Enforce limits on request bodies, concurrency, retry attempts, and connection timeouts.
10. Audit route/security policy changes, without logging JWTs, cookies, API keys, or sensitive raw payloads.

**Route predicates select routes; they do not grant access.** A route `Host=admin.example.test` or `Path=/api/admin/**` does not replace authentication/authorization.

## 22. Metrics and Tracing Must Be Enabled per Actual Web Stack

Post-deployment minimum observability:

| Question | Metric |
|---|---|
| Is the Gateway receiving traffic? | Inbound HTTP RPS and Gateway routed RPS |
| Which route is failing? | 401/403/429/5xx by route, status |
| Where is user latency spent? | Client TTFB/TTLB, Gateway P95/P99, backend tracing |
| Are JVM/Netty/Servlet saturated? | Heap/direct memory, GC, threads/event-loop, pools |
| Are retries multiplying load? | Outbound attempts vs routed requests |
| Are breakers/limiters working? | Open/fallback rate, quota decisions, Redis health |
| Are Pods being scraped? | Prometheus `up` per instance, deployment revision |
| Are routes consistent across replicas? | Route config revision/health, per-node effective routes |

Do not assume identical meter names across Gateway Server WebFlux, Server Web MVC, and ProxyExchange. In some WebFlux versions, `spring.cloud.gateway.requests` is the route-level timer while `http.server.requests` is the inbound server metric. Requests rejected by security before routing **may not appear in the route-level timer**.

**Never attach raw URLs, user IDs, JWTs, cookies, or trace IDs as metric labels** due to cardinality explosion and sensitive data exposure.

## 23. Native Image/AOT: Optional Execution Format

Spring Boot provides AOT/native image workflows for supported versions and dependencies. **A native executable is not a fifth Gateway variant**.

When considering native:

- Compatible GraalVM/toolchain/plugin matching the Boot release is required.
- Verify whether the chosen Spring Cloud Gateway variant has a **supported native surface**.
- Dynamic route loading, reflection, SpEL, SSL, DNS, Redis, CircuitBreaker, and custom filters may need adjustments/hints or lack full support.
- Measure startup, RSS, latency, and correctness on the **actual native binary**, not extrapolated from JVM JAR tests.
- Keep a fallback/rollback path to the JVM image if the application relies on unverified dynamic features.

A safe baseline for learning and deployment is usually an **executable JVM JAR/OCI image**; try native when there is a specific requirement and a clear compatibility matrix.

## 24. Smoke Test Matrix by Variant

| Check | Server WebFlux | Server Web MVC | ProxyExchange WebFlux | ProxyExchange MVC |
|---|---|---|---|---|
| Boot starts with correct classpath | Yes | Yes | Yes | Yes |
| Correct HTTP runtime | Reactor Netty | Servlet | WebFlux runtime | Servlet |
| Routes/handlers registered | Gateway route engine | MVC routing | Controller | Controller |
| Predicate/HTTP mapping | Reactive predicates | MVC predicates | `@GetMapping`... | `@GetMapping`... |
| Path/header transforms | Reactive filters | MVC handler filters | Controller/client | Controller/client |
| Correct Security API | Reactive chain | Servlet chain | Reactive chain | Servlet chain |
| CircuitBreaker/Redis | Per Gateway support/deps | Per MVC support/deps | Custom integration | Custom integration |
| `lb://` | Check LoadBalancer/discovery | Check LoadBalancer/discovery | Do not assume | Do not assume |
| Health probes/readiness | Test | Test | Test | Test |
| HTTP 401/403/429/5xx | Test | Test | Test | Test |
| TLS, WebSocket, SSE | Test end-to-end | Test end-to-end | Per app capabilities | Per app capabilities |
| Graceful shutdown | Test | Test | Test | Test |

**`MockMvc` unit tests in Server MVC do not prove Netty routes of WebFlux Server work.** Use `WebTestClient` for WebFlux and Servlet test tools for MVC, adding end-to-end HTTP tests against a test backend when DNS/TLS/filter routing need verification.

## 25. CI/CD and Release Metadata

~~~mermaid
flowchart TD
    S["Source + BOM + config revision"] --> U["Unit tests + security checks"]
    U --> I["HTTP integration tests"]
    I --> B["Build executable JAR / OCI image"]
    B --> V["SBOM/scan/signature/provenance"]
    V --> ST["Deploy staging + smoke tests"]
    ST --> CA["Canary / rolling update"]
    CA --> M["Monitor errors, latency, traffic"]
    M --> D{"SLO & security invariants PASS?"}
    D -->|Yes| P["Promote image digest"]
    D -->|No| R["Rollback + incident review"]
~~~

Recommended release records:

- Git SHA/image digest;
- Spring Boot, Spring Cloud release train, and Gateway variant;
- Java build/runtime version;
- Route configuration revision;
- TLS/Redis/Discovery dependency schema (without secrets);
- Deployment environment/namespace/replica count;
- Test reports, pre/post-canary SLOs;
- Rollback image and approver.

**Image revision and route config revision can change independently.** A dynamic route using a new filter unsupported by an older image will fail even if that image was previously healthy; compatibility checks are required for both.

## 26. Lab: JAR → Image → Smoke Tests

Assume an echo backend has `GET /catalog/items/42`; the Gateway receives `GET /api/catalog/items/42` and strips the `/api` prefix before forwarding.

### Step 1 — Choose Two Independent Lab Projects

- Project A: **Server WebFlux** with reactive routes.
- Project B: **Server Web MVC** with MVC routes.

Do not combine both starters just to "compare." Keep the same backend/HTTP contract, and the same TLS/CPU/memory limits when benchmarking.

### Step 2 — Build and Run on a Compatible JVM

~~~bash
java -version
./gradlew clean test bootJar
java -jar build/libs/gateway-app.jar \
  --spring.profiles.active=lab
~~~

### Step 3 — Verify Gateway and Probes

~~~bash
curl -i 'http://localhost:8080/api/catalog/items/42'
curl -i 'http://localhost:8080/livez'
curl -i 'http://localhost:8080/readyz'
~~~

If `/livez`/`/readyz` return 404, check your Spring Boot version's probe/path mapping properties before concluding the app is unhealthy.

### Step 4 — Test Disallowed Methods/Paths

~~~bash
curl -i -X DELETE \
  'http://localhost:8080/api/catalog/items/42'
curl -i 'http://localhost:8080/no-route-here'
~~~

Status codes may be 404/405/401/403 depending on routes, Spring Security, and handler mappings. What must be proven: invalid requests **are not mistakenly forwarded to the backend**.

### Step 5 — Package the Image

~~~bash
docker build -t gateway-app:lab .
docker run --rm -p 8080:8080 gateway-app:lab
~~~

Verify DNS/network when the backend is another container. **`localhost` inside a container does not automatically reach the host machine**.

### Step 6 — Test Production-Like Dependencies

If using a Redis limiter, test exceeding quota and a Redis outage in **lab**; if using `lb://`, verify instance selection; if using TLS, test valid and invalid certificates; if using JWT, test missing tokens and wrong scopes/audiences.

### Step 7 — Test on a Kubernetes Test Cluster

~~~bash
kubectl apply -f gateway-deployment.yaml
kubectl rollout status deployment/gateway-edge
kubectl get pods -l app=gateway-edge
kubectl get endpointslice \
  -l kubernetes.io/service-name=gateway-edge
~~~

Manifest names, cluster RBAC, and Service labels must match your actual setup. These commands are lab exercises only; do not run on production without authorization.

### Step 8 — Verify Rollout/Drain

1. Send continuous GET requests at low load.
2. Roll out a canary image; record deployment revision.
3. Observe readiness transitions, 5xx responses, dropped connections, and P99.
4. If using SSE/WebSocket, verify reconnect/resume.
5. Check SIGTERM/grace budget and lost request count.
6. Roll back if SLO or security tests fail.

### Step 9 — Report Results by Variant

| Result | Server WebFlux | Server Web MVC |
|---|---|---|
| Java/runtime version | Measure | Measure |
| Startup + ready time | Measure | Measure |
| RSS, heap/direct, thread/event-loop | Measure | Measure |
| Successful RPS | Measure | Measure |
| P95/P99, 401/403/429/5xx | Measure | Measure |
| TLS/SSE/WebSocket/rollout | PASS/FAIL | PASS/FAIL |

**Do not fill in fabricated numbers as real benchmarks.** Results allow fair comparison only when backend, request mix, TLS, caching, resource limits, and load generator are controlled.

## 27. Troubleshooting by Deployment Symptom

| Symptom | Likely cause to check | Action |
|---|---|---|
| `UnsupportedClassVersionError` | JRE lower than bytecode | Match compile JDK and runtime |
| `NoSuchMethodError` or `ClassNotFoundException` | Boot/Cloud/Reactor version mismatch | Check BOM/dependency tree |
| Server WebFlux startup fails after adding MVC starter | Web stack/classpath conflict | Choose exactly one server variant |
| Server MVC custom filter fails to compile | Using reactive `GatewayFilter` API | Switch to MVC handler filter |
| ProxyExchange cannot be injected | Wrong MVC/WebFlux module | Verify dependency and controller stack |
| Health 200 but routes 404 | Wrong route config namespace, route not loaded | Inspect effective routes/handler mappings |
| `lb://` 503 | Missing LoadBalancer/discovery/instances | Verify service IDs and registry |
| Container calling localhost backend → 502 | Localhost targets container | Use proper Service DNS/target |
| Backend HTTPS handshake fails | Wrong CA trust/SNI/hostname | Fix truststore/certificate, never trust-all |
| JWT returns 401 on all requests | JWK/issuer/audience/security config | Check auth integration/egress |
| Redis limiter not running | Wrong DNS/TLS/password/module | Check Redis health/failure policy |
| CircuitBreaker filter missing | Missing factory/dependency | Check supported variant/version |
| Pod OOMKilled | Heap + direct/native exceed limit | Measure RSS, reduce buffering/adjust memory reasonably |
| P99 spikes under load | Blocking event loop or Servlet pool saturation | Profile the right stack |
| Readiness fails though app started | Wrong probe path/port or startup timing | Verify endpoints/startupProbe |
| Management health green but main port unresponsive | Probe only hits management port | Probe main port/readiness |
| WebSocket disconnects during deploy | No reconnect/drain strategy | Design client resume |
| SSE buffered | Ingress proxy buffering/body transform | Inspect every hop |
| 413 upload | Ingress/Gateway/backend size limit | Set limits per policy |
| Deployed wrong image version | Mutable tag or registry cache | Pin digest/immutable tag |
| Secrets leaked via env/config/logs | Misconfigured logging or RBAC | Redact/rotate/restrict |
| Canary routes differ across nodes | Config revisions/refresh drift | Reconcile/rollback |
| Route-level metrics empty | Wrong meter, route unmatched, different variant | Inspect Actuator/runtime |

### Six Isolation Questions

1. Does the **Artifact** have the right Java runtime, BOM, and image digest?
2. Does the **Variant** match WebFlux/Netty, MVC/Servlet, or ProxyExchange?
3. Are the **app main port** and readiness/liveness actually working?
4. Are **routes** loaded and matching the expected predicate/filter order?
5. Can **outbound** traffic traverse DNS/discovery/TLS/Redis/JWK?
6. Do **policies and outcomes** match expected 401/403/429/5xx/retry/fallback/tracing?

**Never "quick-fix" by enabling global `permitAll`, disabling TLS verification, exposing all Actuator endpoints, or setting infinite timeouts.**

## 28. Pre-Release Checklist

### Variant and Build

- [ ] Explicitly selected **Server WebFlux**, **Server Web MVC**, **ProxyExchange WebFlux**, or **ProxyExchange MVC**.
- [ ] Starter matches release train; Boot and Cloud BOMs are compatible.
- [ ] Not mixing Servlet/Reactive Gateway Server outside supported models.
- [ ] Not confusing WebFlux `GatewayFilter` with MVC handler filter.
- [ ] Not confusing ProxyExchange with Gateway Server filters/route locators.
- [ ] Java runtime compatible with compile JDK/Boot baseline.
- [ ] Built a true executable JAR, not just a plain JAR.
- [ ] CI runs unit/integration/security tests before publishing the image.
- [ ] Image digest, release metadata, scan/SBOM, and rollback target ready.

### Container, Config, and TLS

- [ ] Non-root container, minimal capabilities, proper write paths.
- [ ] Container CPU/memory limits based on measurement; Xmx not set equal to total memory limit.
- [ ] Heap, direct memory, RSS, threads, and connection pools monitored per stack.
- [ ] Secrets externalized from image; ConfigMap/Secret/profiles match environment.
- [ ] Routes bound under the correct prefix for the Gateway version.
- [ ] No leftover `localhost` URIs misused in container deployment.
- [ ] Clear when to use Kubernetes DNS vs `lb://`.
- [ ] Egress/SSRF allowlist, JWT, TLS/mTLS truststore, and certificate rotation verified.
- [ ] No raw tokens/cookies/API keys or sensitive payloads logged.

### Kubernetes and Operations

- [ ] Startup/readiness/liveness probes use the right paths and main/management ports.
- [ ] Liveness does not depend on all backends/Redis.
- [ ] Replica count/headroom aligned with SLO, rolling update, and rollback strategy.
- [ ] SIGTERM/graceful shutdown/endpoint propagation tested.
- [ ] SSE/WebSocket reconnect and long upload/download recovery strategies exist.
- [ ] Ingress properly supports CORS, headers, HTTP/2/TLS, WebSocket/SSE, body sizes, and timeouts.
- [ ] Authentication uses the right SecurityFilterChain per stack, with independent backend authorization.
- [ ] Retry, breaker, Redis limiter, cache, and discovery failure policies tested.
- [ ] Actuator/Prometheus not exposed outside administrative scope.
- [ ] Metrics, tracing, route IDs, and deployment versions suffice for incident investigation.
- [ ] Smoke tests cover GET/POST/401/403/429/5xx, route misses, TLS, and shutdown.
- [ ] Green build/startup/health is not treated as proof the system is secure enough.

## 29. Applied Exercises

**Exercise 1 — Choosing a Variant.** A team has a Spring MVC BFF with 5 controllers that only need to forward GET/POST to backends without needing a Gateway route engine. Compare ProxyExchange MVC with Gateway Server WebFlux across functionality, operations, and dependencies.

**Exercise 2 — Fixing Classpath.** A Server WebFlux application fails to boot after adding `spring-boot-starter-web`. Write a procedure to inspect the dependency graph, Boot application type, and actual embedded HTTP server.

**Exercise 3 — JAR/JRE.** Build targeting Java 21 then run on JRE 17 inside a Docker image. Predict the failure and design CI controls.

**Exercise 4 — Readiness.** The management port returns health UP while main port 8080 is failing. Design probes reflecting traffic-serving capability and explain why Redis should not be in default liveness.

**Exercise 5 — Service Discovery.** Route `lb://catalog-service` finds no instances while Kubernetes Service DNS works. Compare the two resolution approaches without conflating the two URI types.

**Exercise 6 — Redis Outage.** One sensitive route requires a fail-closed limiter, while another public route has a different policy. Test startup, readiness, 429/503, and recovery when Redis is unavailable.

**Exercise 7 — WebSocket Rollout.** The Gateway holds many WebSocket sessions, and rolling updates drop connections. Design reconnect, state recovery, grace budget, and appropriate k6/WebSocket client tests.

**Exercise 8 — Hardening.** An image runs as root, stores a Redis password in `application-prod.yml`, and exposes `/actuator/**` publicly. List mandatory changes and how to verify them.

**Exercise 9 — Comparing Runtimes.** Measure WebFlux Server and MVC Server under identical request mix, backend, TLS, and resources. Explain why you cannot compare solely by a single RPS number or startup time alone.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Server WebFlux, Server Web MVC, Proxy Exchange, GatewayFilter, and deployment/Actuator sections by version.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — variants and release trains.
- [Spring Cloud Project](https://spring.io/projects/spring-cloud) — compatibility between Spring Boot and Spring Cloud BOMs.
- [Spring Boot — Packaging](https://docs.spring.io/spring-boot/reference/packaging/index.html) — executable archives, build plugins, and distribution.
- [Spring Boot — Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html) — Buildpacks and Dockerfiles.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — graceful shutdown and in-flight requests.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Kubernetes probes, health groups, security, and endpoint exposure.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — profiles, env, and config import.
- [Spring Boot — Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html) — AOT/native constraints.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — reactive `SecurityWebFilterChain`.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — servlet `SecurityFilterChain`.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — replicas and rolling updates.
- [Kubernetes — Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — startup/readiness/liveness.
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) — SIGTERM and termination grace.
- [Kubernetes — Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) — non-root/capabilities.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — outbound URI allowlists and network controls.

**Key Takeaway:** In Spring Cloud Gateway, **the variant determines the web stack and route/filter APIs**, whereas **a JAR/OCI image is merely the distribution format**. **Server WebFlux** uses a reactive Netty pipeline; **Server Web MVC** uses Servlet/WebMvc.fn; **ProxyExchange WebFlux/MVC** are controller-style proxies that do not automatically include Gateway Server's filter policies. To deploy safely, lock the Boot–Cloud BOM, use an appropriate Java runtime, build an executable JAR, run non-root containers, externalize secrets/config, verify DNS/`lb://`/TLS, design probes and graceful rollouts, and **test the right variant with requests, auth, limiters, retries, TLS, and long-lived connections in a real deployment environment**. A successfully built image **does not prove the Gateway is ready or safe to expose publicly**.
