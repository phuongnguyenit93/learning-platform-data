# Packaging, Load Testing, Monitoring, and Recovery Drills for the Gateway

## 1. Practice Objectives

In the **SPRING_CLOUD_GATEWAY** module, the Gateway is the entry point for microservices. A route may work fine on a developer's machine and still not be production-ready if the image is hard to reproduce, the container runs with excessive privileges, maximum capacity is unknown, slow upstreams go undetected, or the system fails to recover after an instance fails.

In the **Comprehensive Practice** chapter, this lab connects route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, and TLS into a measurable deployment/observability/recovery workflow.

This lab walks a WebFlux Gateway through a complete operational lifecycle:

1. **Packaging:** build a reproducible executable JAR and OCI container image running non-root, with resource configuration and shutdown handling.
2. **Deployment:** run locally with Docker Compose, then move to Kubernetes with probes, rolling updates, and a PodDisruptionBudget.
3. **Load testing:** generate workloads with Grafana k6, measuring throughput, p95/p99 latency, errors, and behavior under increasing load.
4. **Observability:** export metrics via Micrometer/Prometheus, inspect Grafana dashboards, correlate traces via OpenTelemetry, and structure per-request logs.
5. **Recovery drills:** deliberately slow down/stop upstreams, restart the Gateway, or disrupt Redis or the telemetry backend; observe retries, circuit breakers, alerts, and rollbacks.

After this lab, you can hand over an image and a deployment backed by operational evidence: dependency/build versions, load test results, dashboards, alert thresholds, recovery drill outcomes, and rollback instructions.

> **Example scope:** Spring Boot 4.x, Spring Cloud Gateway Server WebFlux 5.x, Java 17+, Docker/OCI, Kubernetes, Prometheus/Grafana, and k6. For Gateway 4.x, check the older property prefixes and matching Spring Cloud Release Train versions. Examples in this article use the new **spring.cloud.gateway.server.webflux.*** prefix.

## 2. Lab Architecture and Data Flow

~~~mermaid
flowchart LR
    K["k6 load generator"] -->|HTTP :8080| G["Gateway replicas"]
    G -->|route /api/orders/**| O["orders-service"]
    G -->|metrics :9001| P["Prometheus"]
    P --> D["Grafana dashboards"]
    G -->|OTLP traces| T["OpenTelemetry Collector"]
    T --> V["Trace backend"]
    G --> L["Central log collector"]
~~~

- Clients/k6 call only the Gateway's **public listener**.
- The Gateway forwards requests to `orders-service`.
- A separate management listener exposes health and metrics for operations systems.
- Prometheus scrapes each Gateway instance; Grafana queries Prometheus to render dashboards.
- Traces export to the OpenTelemetry Collector. Logs are collected from stdout or via an infrastructure agent.
- In Kubernetes, public Ingress/Service exposes only the application HTTP port; the management port is permitted only from probes and monitoring workloads.

### 2.1. Suggested Directory Layout

~~~text
gateway/
├── pom.xml
├── mvnw
├── .mvn/
├── .dockerignore
├── Dockerfile
├── compose.yaml
├── src/
│   └── main/
│       └── resources/
│           └── application.yml
└── ops/
    ├── prometheus/
    │   ├── prometheus.yml
    │   └── rules/
    │       └── gateway.yml
    ├── k6/
    │   └── gateway-load.js
    ├── grafana/
    │   └── dashboards/
    └── kubernetes/
        ├── gateway-deployment.yaml
        ├── gateway-service.yaml
        ├── gateway-pdb.yaml
        └── gateway-servicemonitor.yaml
~~~

This layout organizes the lab; if your existing project already has deployment/observability directories, use the existing structure and keep a single configuration source.

### 2.2. Prerequisites

- JDK 17 or higher, with Maven Wrapper or Gradle Wrapper per project.
- Docker Engine/BuildKit and the Docker Compose plugin.
- A WebFlux Gateway with a route to a backend.
- A test backend exposing a stable endpoint, e.g., `GET /orders/42`.
- Kubernetes cluster and `kubectl` for cluster deployment.
- Prometheus/Grafana or an equivalent stack.
- k6 CLI or k6 container.
- If using tracing: OpenTelemetry Collector and a trace backend such as Tempo/Jaeger/Zipkin.

**Never run stress tests against production or systems outside your control.** Start in local/staging, set load caps, and have an operator monitor the run.

## 3. Standardizing the Gateway App Before Packaging

### 3.1. Required Dependencies

With Maven and a matching Spring Cloud BOM release train, the core dependencies are typically:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

If routes use `lb://SERVICE-ID`, add `spring-cloud-starter-loadbalancer` and the appropriate Discovery Client. If using JWT Resource Server, Redis RateLimiter, CircuitBreaker, or tracing, add the exact starters for features actually configured. Never pin individual Spring Cloud artifact versions; let the BOM manage them.

### 3.2. Routes and the Management Listener

Example `application.yml` for Gateway Server WebFlux 5.x:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
          httpclient:
            pool:
              metrics: true
          routes:
            - id: orders-api
              uri: http://orders:80
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,prometheus,metrics
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  metrics:
    tags:
      application: spring-cloud-gateway
      environment: lab
    distribution:
      percentiles-histogram:
        http.server.requests: true
        http.client.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Explanation:

- `8080` receives application traffic; `9001` is reserved for management.
- `server.shutdown: graceful` and `spring.lifecycle.timeout-per-shutdown-phase` give Spring time to finish in-flight requests upon shutdown signal.
- `health`, `prometheus`, and `metrics` are the necessary endpoints in the lab. Never expose `env`, `configprops`, `heapdump`, `gateway`, or `loggers` on the public listener.
- `management.endpoint.health.probes.enabled` enables startup/readiness/liveness health groups.
- `spring.cloud.gateway.server.webflux.metrics.enabled` enables the Gateway metrics filter under the 5.x namespace; `httpclient.pool.metrics` collects connection pool metrics.
- `http.server.requests` and `http.client.requests` are metrics/observations to verify at runtime. Exact meter names can vary by version and registry; always inspect `/actuator/metrics` before writing PromQL.
- `management.tracing.sampling.probability: 0.1` samples 10% of traces. In short tests you can raise it temporarily for observation; never default to 100% across all production traffic.

For Gateway 4.x, properties usually live under `spring.cloud.gateway.*`; verify your release train's BOM and configuration properties before copying YAML.

### 3.3. Exporting Traces with OpenTelemetry

With Spring Boot 4, add `spring-boot-starter-opentelemetry` if choosing OTLP tracing. Example Collector endpoint configuration:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          transport: http
  tracing:
    sampling:
      probability: 0.1
~~~

This endpoint is an example for OTLP/HTTP. If your Collector uses gRPC, TLS, auth headers, or a different endpoint, configure transport/SSL/headers accordingly. Store credentials in a Secret or secret manager, never committed to `application.yml`.

Spring Boot creates traces and propagates context when using auto-configured clients. WebFlux Gateway also provides observations for outbound HTTP. Verify end-to-end traces from Gateway → backend; if the backend constructs an uninstrumented client or strips propagation headers, traces can break.

### 3.4. The Management Port Must Be Protected

Separating ports does not automatically make Actuator private. You must:

- Never publish `9001` to the Internet or public Ingress.
- Allow access only from Prometheus, Kubernetes probes, and operator networks.
- Apply Spring Security/network policies appropriate for your environment.
- Expose only strictly necessary endpoints.
- Ensure health responses never leak hostnames, credentials, or sensitive dependency details.

In Docker Compose, the management port only needs to be reachable on the internal Compose network. In Kubernetes, use a dedicated management Service and a NetworkPolicy restricting scrape sources.

## 4. Packaging an OCI Image

### 4.1. Multi-Stage Dockerfile

Example using Maven Wrapper and Java 17:

~~~dockerfile
# Pin base images by tag and digest in production pipelines.
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw
RUN ./mvnw -B dependency:go-offline

COPY src/ src/
RUN ./mvnw -B verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app

COPY --from=build --chown=10001:10001 /workspace/target/*.jar /app/app.jar

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0 -XX:+ExitOnOutOfMemoryError"

USER 10001:10001
EXPOSE 8080 9001

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Key points:

- The build stage holds Maven and the JDK; the runtime stage holds only the JRE and executable JAR.
- `./mvnw verify` runs tests/verification before building the image. If integration tests depend on external services, separate that test profile and run it in CI prior to image build.
- `USER 10001:10001` runs the app under a non-root UID/GID. The runtime image does not need chmod or write access to the app directory.
- `MaxRAMPercentage` lets the JVM size the heap relative to container memory limits; 75% is only a starting point—measure heap, direct memory, metaspace, and native overhead.
- `ExitOnOutOfMemoryError` terminates the process on OOM so the orchestrator can restart it; it does not replace resource sizing or memory monitoring.
- Exec-form `ENTRYPOINT` ensures the JVM receives `SIGTERM` directly so graceful shutdown works.

If using Gradle, replace the build stage with Gradle Wrapper and copy the artifact from `build/libs/`. Do not mix Maven examples into a Gradle project.

The Dockerfile above assumes a single-module Maven project producing one executable JAR in `target/`. For multi-module builds, copy the required module POMs before the dependency cache step and specify the exact Gateway artifact to copy into the runtime stage.

### 4.2. .dockerignore

~~~text
.git
.gitignore
.idea
.vscode
*.iml
target/
build/
.env
.env.*
secrets/
*.log
.DS_Store
~~~

Never include `.env`, private keys, local credentials, build caches, or repository metadata in the build context. If the build needs secrets to download private dependencies, use BuildKit secret mounts or a CI secret store; never use `ARG`/`ENV` to bake tokens into image layers.

### 4.3. Building and Inspecting the Image

~~~bash
docker build -t gateway-lab:local .
docker image inspect gateway-lab:local
docker history gateway-lab:local
~~~

In a pipeline:

1. Run unit/integration tests before building.
2. Pin base images by digest; use readable tags without relying on `latest`.
3. Generate an SBOM and scan image/dependencies for CVEs.
4. Sign images and verify signatures at deploy time if required by supply-chain policy.
5. Push images with immutable tags or digests; never overwrite published release tags.
6. Archive commit SHA, BOM versions, image digest, and test reports as release evidence.

Docker multi-stage builds strip build tools from the runtime image, but do not automatically ensure images are patched. Update base images and rebuild regularly.

## 5. Running Locally with Docker Compose

### 5.1. Prometheus Scrape Config

Create `ops/prometheus/prometheus.yml`:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules/gateway.yml

scrape_configs:
  - job_name: spring-cloud-gateway
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - gateway:9001
~~~

Prometheus scrapes the management listener over the internal network. In Kubernetes, do not scrape a load-balanced ClusterIP as a single target if you need per-replica metrics; use Pod discovery or ServiceMonitor/PodMonitor.

### 5.2. Compose Stack

Example `compose.yaml`:

~~~yaml
services:
  orders:
    image: traefik/whoami:v1.11
    expose:
      - "80"

  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    image: gateway-lab:local
    ports:
      - "127.0.0.1:8080:8080"
    expose:
      - "9001"
    depends_on:
      - orders
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true

  prometheus:
    image: prom/prometheus:PINNED_VERSION
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=7d
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./ops/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./ops/prometheus/rules:/etc/prometheus/rules:ro
      - prometheus-data:/prometheus
    depends_on:
      - gateway

  grafana:
    image: grafana/grafana:PINNED_VERSION
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: change-this-local-password
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
~~~

Replace `PINNED_VERSION` with tested tags/digests for Prometheus and Grafana; change the lab password and never use sample passwords in shared environments. Prometheus/Grafana ports are bound to loopback so they are not exposed to external networks. Named volumes preserve Prometheus/Grafana data across container recreations.

`traefik/whoami` is a demo backend echoing request details, not a real order service. In real projects, replace it with `orders-service` having its own contract and health endpoint. The `http://orders:80` route must match the Compose service hostname/port.

### 5.3. Keeping Route Config Consistent

The `orders-api` route is declared in `application.yml` in section 3.2. The URI `http://orders:80` uses the Compose service name; in Kubernetes, the same name works if the `orders` Service resides in the Gateway's namespace. Do not redeclare the same route in a separate profile. If a local profile is needed, override only properties that genuinely differ by environment and maintain one source for route declarations.

Compose `depends_on` orders container startup by default, without proving the backend is ready to serve requests. With real backends, add a proper healthcheck and use `depends_on` condition `service_healthy` if the image supports it; otherwise verify the Gateway/backend has appropriate retry/startup behavior.

Start up:

~~~bash
docker compose up -d --build
docker compose ps
docker compose logs -f gateway
~~~

Verify:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i http://localhost:9090/-/healthy
~~~

Management port `9001` is not published to the host in the Compose file above. Prometheus still scrapes via DNS `gateway:9001` inside the Compose network. If you need to inspect endpoints from the host, set up a controlled temporary port-forward/debug path rather than publishing the management port publicly.

Open Grafana at `http://localhost:3000`, add a Prometheus data source with URL `http://prometheus:9090`, and build the dashboard in section 8.

## 6. Deploying the Gateway on Kubernetes

### 6.1. Deployment With Resources and Health Probes

Example `gateway-deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  namespace: app
spec:
  replicas: 3
  revisionHistoryLimit: 5
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
      containers:
        - name: gateway
          image: registry.example.com/platform/gateway@sha256:REPLACE_WITH_DIGEST
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 9001
          volumeMounts:
            - name: tmp-dir
              mountPath: /tmp
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
      volumes:
        - name: tmp-dir
          emptyDir: {}
~~~

Replace the digest with a signed/scanned image from your organization's registry. CPU/memory requests and limits are lab starting points, **not production sizing**. Measure heap, direct buffers, native memory, GC, CPU throttling, and p95/p99 before finalizing.

Meaning of the probes:

- **Startup probe:** gives the app sufficient time to start. Until the startup probe succeeds, Kubernetes holds off running liveness/readiness probes.
- **Liveness probe:** detects hung or non-progressing processes and triggers restarts once failure thresholds are exceeded.
- **Readiness probe:** decides whether the Pod receives traffic from the Service. If readiness fails, the Pod is removed from ready endpoints.
- **Liveness must not depend on every backend:** if `orders-service` temporarily drops, restarting all Gateway replicas repeatedly can amplify the outage. Readiness should check only conditions truly required for the Pod to serve traffic; do not tie all downstream services into readiness if the Gateway can still serve other routes.

Startup/liveness/readiness in this example call management port `9001`. Confirm Spring Boot has health probes enabled and the management listener is actually listening on that port.

### 6.2. Separate Public and Management Services

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway
  namespace: app
  labels:
    app: gateway
spec:
  selector:
    app: gateway
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-management
  namespace: app
  labels:
    app: gateway
    monitoring: enabled
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: management
      port: 9001
      targetPort: management
~~~

Ingress points only to the `gateway` Service on port 80. The management Service is a separate ClusterIP with no public Ingress. A NetworkPolicy must restrict port `9001` to the monitoring namespace and authorized probe/operator sources; exact rules depend on your CNI and cluster networking.

### 6.3. PodDisruptionBudget and Autoscaling

For a Deployment with three replicas, you can use a PDB:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: gateway
  namespace: app
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: gateway
~~~

A PDB limits voluntary disruptions that would drop ready Pods below two. A PDB does not prevent simultaneous crashes, node failures, or all forms of Pod deletion; nor does it replace rolling update strategies and replica counts.

HPA is optional once metrics-server is installed and load tests establish scaling behavior:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway
  namespace: app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

70% CPU is an example, not an optimal threshold for every Gateway. HPA requires CPU requests to compute utilization. When testing autoscaling, allow enough time for metrics collection, scale-up stabilization, and Pod startup; do not evaluate after only a few seconds of load.

### 6.4. Prometheus Operator ServiceMonitor

If the cluster uses Prometheus Operator, a ServiceMonitor can scrape the management Service:

~~~yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: gateway
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames:
      - app
  selector:
    matchLabels:
      monitoring: enabled
  endpoints:
    - port: management
      path: /actuator/prometheus
      interval: 15s
      scrapeTimeout: 5s
~~~

The label selector must match your cluster's Prometheus Operator configuration. `ServiceMonitor` is a CRD; if Prometheus Operator is not installed, use Prometheus Kubernetes service discovery/Pod discovery equivalents. Confirm every replica is scraped rather than a single load-balanced Service address.

Apply the core manifests and inspect endpoints:

~~~bash
kubectl apply -f ops/kubernetes/gateway-deployment.yaml
kubectl apply -f ops/kubernetes/gateway-service.yaml
kubectl apply -f ops/kubernetes/gateway-pdb.yaml
kubectl rollout status deployment/gateway -n app
kubectl get pods,svc,endpointslices -n app
~~~

Apply `ServiceMonitor` only when the Prometheus Operator CRD is installed and the label selector matches your Prometheus instance:

~~~bash
kubectl apply -f ops/kubernetes/gateway-servicemonitor.yaml
~~~

To run k6 from a developer machine, open a port-forward in a separate terminal:

~~~bash
kubectl port-forward service/gateway 8080:80 -n app
~~~

### 6.5. Graceful Shutdown and Rolling Updates

During a rollout or node drain:

1. The Pod enters termination; Kubernetes updates endpoint status so new traffic gradually stops reaching the Pod.
2. The container receives `SIGTERM`.
3. Spring Boot graceful shutdown stops accepting new requests and waits for in-flight requests up to the configured limit.
4. After `terminationGracePeriodSeconds`, Kubernetes may forcibly kill any remaining process.

In the example, Spring has 30 seconds for the shutdown phase and the Pod has a 45-second termination grace period. Leave headroom for endpoint propagation and shutdown. Test with long/streaming requests; do not assume every client/proxy keeps connections open indefinitely.

## 7. Load Testing with Grafana k6

### 7.1. Define Objectives Before Running

A load test is meaningful only when you know the questions to answer:

- How many requests/second can the Gateway serve at the target latency?
- As concurrency rises, at what level do p95/p99 begin breaching the SLO?
- At what load level do 5xxs, timeouts, or 429s appear?
- How do CPU, heap, direct memory, and connection pools grow?
- Does the backend or the Gateway become the bottleneck first?
- When one backend instance drops, how do throughput and latency change?

Set initial illustrative lab SLOs:

| Metric | Illustrative lab threshold |
| --- | --- |
| p95 request latency | under 300 ms |
| p99 request latency | under 800 ms |
| Unexpected HTTP failures | under 1% |
| Response contract checks | at least 99% passing |
| Gateway replicas | no restarts/OOM during steady load |

These are starting thresholds to practice measuring, not SLA commitments. Replace them with your API's real SLOs, traffic mix, payload sizes, and backends.

### 7.2. k6 Script With Smoke/Load/Stress/Soak Profiles

Create `ops/k6/gateway-load.js`:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const baseURL = __ENV.BASE_URL || 'http://localhost:8080';
const profile = __ENV.PROFILE || 'smoke';

const profiles = {
  smoke: [
    { duration: '30s', target: 2 },
    { duration: '1m', target: 2 },
    { duration: '15s', target: 0 },
  ],
  load: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 10 },
    { duration: '2m', target: 0 },
  ],
  stress: [
    { duration: '2m', target: 20 },
    { duration: '2m', target: 40 },
    { duration: '2m', target: 80 },
    { duration: '1m', target: 0 },
  ],
  soak: [
    { duration: '5m', target: 20 },
    { duration: '30m', target: 20 },
    { duration: '5m', target: 0 },
  ],
};

export const options = {
  scenarios: {
    gateway_traffic: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: profiles[profile] || profiles.smoke,
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(baseURL + '/api/orders/42', {
    headers: {
      Accept: 'text/plain, application/json',
    },
    tags: {
      route: 'orders-api',
    },
  });

  check(response, {
    'Gateway returns HTTP 200': (r) => r.status === 200,
    'response body is not empty': (r) => r.body && r.body.length > 0,
  });

  sleep(1);
}
~~~

Explanation:

- **smoke:** confirms routes, auth, and backends work under minimal load.
- **load:** holds expected load for several minutes to observe latency and resource usage.
- **stress:** steps load up to find saturation points; fails the test when thresholds breach. If early abort is needed, configure `abortOnFail` on thresholds per k6 docs.
- **soak:** sustains load over an extended window to uncover memory growth, connection leaks, queue buildup, or gradual degradation.
- Thresholds cause k6 to exit with a failure code when breached. Checks only record assertions; to fail the run on failed checks, set a threshold on the `checks` metric as shown.
- The script uses `ramping-vus`, a closed workload model. When responses slow down, VUs take longer and request rate can drop. If you need to test a fixed arrival rate, use the `constant-arrival-rate` executor and watch `dropped_iterations`.

The p95/p99 thresholds in the script must match lab objectives. If the demo backend or local environment is slower, adjust only after documenting the reason; never relax thresholds merely to get green results.

### 7.3. Running the Profiles

From PowerShell:

~~~powershell
$env:BASE_URL = 'http://localhost:8080'
$env:PROFILE = 'smoke'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'load'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'stress'
k6 run .\ops\k6\gateway-load.js

$env:PROFILE = 'soak'
k6 run .\ops\k6\gateway-load.js
~~~

On Linux/macOS:

~~~bash
BASE_URL=http://localhost:8080 PROFILE=smoke k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=load k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=stress k6 run ops/k6/gateway-load.js
BASE_URL=http://localhost:8080 PROFILE=soak k6 run ops/k6/gateway-load.js
~~~

If running k6 in a container, mount the script into the container and attach it to the proper Compose/Kubernetes network. Never use `localhost` inside a container to reach another Gateway container; use service DNS or an appropriate port-forward address.

### 7.4. Measuring a Fixed Arrival Rate When Needed

If the requirement is "the Gateway must sustain 100 new requests per second", ramping VUs does not model that goal accurately. Use a separate scenario:

~~~javascript
export const options = {
  scenarios: {
    fixed_rate: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    dropped_iterations: ['count==0'],
  },
};
~~~

This replaces the `export const options` block in the main script; do not declare two `options` variables simultaneously. Allocate enough VUs so k6 can maintain the arrival rate; otherwise `dropped_iterations` rises and the test no longer generates the intended load. The load generator itself must also have enough CPU/network not to become the bottleneck.

### 7.5. Controlled Load Testing Procedure

1. Record image version, config, Gateway replica count, and backend replica count.
2. Run a smoke test first.
3. Warm up so JVM JIT, connection pools, and caches stabilize.
4. Run the load test with a fixed traffic mix.
5. Capture k6 results and Prometheus/Grafana snapshots over the same time window.
6. Repeat changing one variable at a time: replicas, CPU, pool, timeouts, or backend capacity.
7. Run stress tests with bounded duration/concurrency and active supervision.
8. Run soak tests once load tests stabilize.
9. Archive the test script, environment details, image digest, raw output, and conclusions.

When testing a rate limiter, `429` may be the **intended policy outcome** rather than a system failure. Create a dedicated scenario for quota behavior, define expected `429`/`Retry-After` responses, and configure expected-status/checks accordingly. Do not mix expected 429s into a baseline success test and conclude the system failed.

### 7.6. Interpreting Results

| Observation | Initial interpretation |
| --- | --- |
| Throughput rises, p95 stays flat | Headroom remains at that load level |
| p95 rises sharply before p99 | A substantial fraction of requests are queuing/slowing |
| p99 rises while p50 stays flat | Tail latency or a subset of backend instances has issues |
| 5xx rises alongside connect timeouts | Check network, backend listeners, pools, and timeouts |
| 429 rises right at quota threshold | Rate limiter is enforcing policy |
| High CPU throttling | Container CPU limit may be too low |
| Heap/direct memory climbs steadily | Check body buffering, pools, leaks, and workload |
| Pending connections rise | Check pool capacity, backend latency, and concurrency |
| Gateway is healthy while backend saturates | Scale backend capacity or rate-limit at the Gateway |

Never conclude a bottleneck from a single metric alone. Correlate k6, Gateway metrics, backend metrics, traces, and resource metrics within the same time window.

## 8. Monitoring with Prometheus, Grafana, Traces, and Logs

### 8.1. Confirming Metrics Are Actually Exported

Once the app is running, query the internal endpoints:

~~~bash
curl -s http://localhost:9001/actuator/health
curl -s http://localhost:9001/actuator/metrics
curl -s http://localhost:9001/actuator/metrics/http.server.requests
curl -s http://localhost:9001/actuator/metrics/http.client.requests
curl -s http://localhost:9001/actuator/prometheus
~~~

If a metric is missing:

1. Verify Actuator and Micrometer registry dependencies.
2. Check whether the endpoint is exposed.
3. Verify Gateway metrics/observability is enabled under the right version namespace.
4. Send a request through the Gateway and check again; some meters appear only after traffic arrives.
5. Use meter names from the Actuator metrics endpoint when building dashboards rather than guessing Prometheus normalized names.

Meters commonly tracked:

| Meter | Operational meaning |
| --- | --- |
| `http.server.requests` | Inbound requests to the Gateway, with status, method, route/URI tags depending on instrumentation |
| `http.client.requests` | Outbound requests from the Gateway to upstream |
| `spring.cloud.gateway.requests` | Gateway metrics filter in versions exporting this meter |
| `jvm.memory.used` / `jvm.gc.pause` | Heap/GC behavior |
| `process.cpu.usage` / `system.cpu.usage` | CPU pressure |
| `application.ready.time` | Time for the application to reach ready state |
| HTTP client pool metrics | Active/idle/pending connections and acquire pressure when pool metrics are enabled |

Not every version/runtime exports the exact same set of meters. Gateway 5.x provides the Gateway HTTP client observation named `http.client.requests`; other Gateway-specific metrics depend on filters and version. Inspect the endpoints before writing PromQL.

### 8.2. Sample PromQL

5-minute HTTP 5xx ratio, assuming Prometheus scrapes the `http.server.requests` histogram/counter:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="spring-cloud-gateway",
  status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    application="spring-cloud-gateway"
  }[5m])),
  1
)
~~~

Aggregated p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="spring-cloud-gateway"
    }[5m])
  )
)
~~~

Request rate:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="spring-cloud-gateway"
}[1m]))
~~~

Series/label names depend on Micrometer naming conventions and application common tags. If your metrics use different prefixes, adapt names to match actual data in Prometheus Explore. Never copy a query verbatim and conclude "no traffic" when `application`/`uri` labels differ.

### 8.3. Recommended Grafana Dashboard Panels

Organize dashboards around the questions they answer:

| Row/panel | Content | Question to answer |
| --- | --- | --- |
| Traffic | Requests/sec by route/method | On which route is traffic rising? |
| Status | 2xx/4xx/5xx/429 | Are errors from backends, quotas, or clients? |
| Latency | p50/p95/p99 | When did tail latency start degrading? |
| Upstream | `http.client.requests` by service/route | Is the Gateway or the backend slow? |
| Connection pool | Active/idle/pending/acquire timeouts | Is the Gateway starved for connections or are backends holding them too long? |
| JVM | Heap, non-heap, direct buffers, GC pauses | Is there memory pressure or GC pausing? |
| Kubernetes | Ready replicas, restarts, CPU/memory, HPA | Are Pods restarting, throttling, or scaling slowly? |
| Resilience | Circuit breaker state, retry attempts, fallbacks | Is the Gateway recovering or over-retrying? |
| Test annotations | Smoke/load/stress/soak start/end | Do metric shifts align with test windows? |

Maintain separate dashboards for backend services when you have visibility into them. Looking only at the Gateway may show rising outbound latency without revealing which backend or dependency is slow.

### 8.4. Cardinality and Sensitive Data

- Use route ID or URI template as dimensions; never attach raw paths containing order IDs/user IDs.
- Never put JWT subjects, emails, session IDs, request IDs, or raw queries into metric labels.
- Gateway path tags can explode cardinality quickly; enable only when paths are bounded to safe templates.
- Never log `Authorization`, `Cookie`, request/response bodies, or private forwarded headers.
- Management endpoints must never be public; allow scraping only from the monitoring network.

A metric label taking a new value per request can spawn hundreds of thousands of time series, inflating Prometheus memory and slowing queries. Trace IDs belong in trace/log correlation, not metric labels.

### 8.5. Per-Request Tracing

Spring Boot supports Micrometer Tracing with OpenTelemetry/OTLP. In the lab:

1. Add the OpenTelemetry starter matching your Boot version.
2. Configure the Collector endpoint and sampling probability.
3. Send a request carrying W3C trace context.
4. Open the trace backend and inspect spans across the Gateway to the backend.
5. Correlate span latency with Gateway/client metrics and backend logs.

In production, 10% sampling is a reasonable starting point, though the final rate depends on traffic volume, cost, and investigation needs. Increase to 100% only during short, bounded tests. Never record raw request bodies or tokens in span attributes.

### 8.6. Structured Logs and Correlation

An operational log event can include fields like:

~~~json
{
  "timestamp": "2026-11-24T10:15:30Z",
  "service": "spring-cloud-gateway",
  "environment": "staging",
  "routeId": "orders-api",
  "method": "GET",
  "status": 503,
  "durationMs": 420,
  "errorCategory": "UPSTREAM_UNAVAILABLE",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
~~~

This is an illustrative schema, not auto-generated default output. Log actionable events for investigation, adding route ID/status/latency/error category and trace context. Never echo credentials, payloads, or full headers into logs.

Metrics show continuous trends; traces follow individual requests; logs capture discrete events and redacted causes. The three signals complement rather than replace one another.

## 9. Setting Up Alerts and SLOs

### 9.1. Alerts Should Map to Actions

Create `ops/prometheus/rules/gateway.yml`. This example assumes Prometheus receives the `http.server.requests` histogram/counter and the `application` common tag:

~~~yaml
groups:
  - name: gateway-slo
    rules:
      - alert: GatewayHigh5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              application="spring-cloud-gateway",
              status=~"5.."
            }[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count{
              application="spring-cloud-gateway"
            }[5m])), 1)
          ) > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Gateway 5xx ratio is above 1 percent
          description: Check route, upstream status, LoadBalancer and connection pool.

      - alert: GatewayP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(http_server_requests_seconds_bucket{
                application="spring-cloud-gateway"
              }[5m])
            )
          ) > 0.3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Gateway p95 latency is above 300ms
          description: Compare inbound and outbound latency, CPU, GC and pool metrics.
~~~

The 1% and 300ms thresholds are lab examples only. If meter names/labels differ in your running version, update the rules to match real metrics before reloading Prometheus. Alert rules must be loaded and verified inside Prometheus; a file existing on disk does not prove alerts work.

Prometheus evaluates rules, while notifications require a configured Alertmanager; Grafana Alerting can be used instead if that is your organization's alerting platform.

| Alert | Suggested lab condition | First action |
| --- | --- | --- |
| Gateway 5xx ratio | Above 1% continuously for 5 minutes | Categorize upstream statuses, connect errors, and routes |
| p95 latency | Breaches SLO for 10 minutes | Inspect upstream latency, pool, CPU/GC, and traces |
| Low ready replicas | Fewer than 2 in a 3-replica Deployment | Check probes, rollout status, node/resource pressure |
| Restarts/OOM | Rising restart count or OOMKilled | Check memory limits, direct buffers, heap/GC |
| Pool acquire pressure | Rising pending/acquire timeouts | Check pool metrics, backend latency, and max connections |
| Circuit breaker open | Sustained open state | Check failure source, backend health, and fallback |
| Telemetry gap | Prometheus scrape down or trace export failing | Check collector/monitoring network without ignoring request paths |

Do not alert on every 429 when rate limiting is working as intended. Alert only when 429s exceed baseline or unexpectedly hit critical clients/tenants.

Define the SLO before computing an error budget: decide explicitly whether client 4xxs, expected quota 429s, and health endpoints belong in the request set. For instance, a 99.9% availability SLO allows a 0.1% error budget over the measurement window; do not mix synthetic, probe, and business traffic when the target measures user APIs.

### 9.2. Distinguishing Symptom From Cause

Example:

~~~text
Symptom:
  Gateway 5xx rising

Possible causes:
  - backend returns HTTP 503
  - no ServiceInstance from LoadBalancer
  - connection refused / DNS / TLS
  - connect/response timeout
  - Redis rate limiter or custom filter error
  - circuit breaker fallback
  - Gateway pod overloaded / pool acquire timeout
~~~

Alerts signal symptoms; runbooks must help operators pinpoint root causes. Include links to dashboards, trace searches, deployment revisions, and runbooks in alert annotations to shorten investigation time.

## 10. Failure Injection and Recovery Drills

Run failure injection only in local/staging or approved environments. Every drill needs an observer, abort criteria, a time limit, and a recovery plan.

### 10.1. Drill A — Losing One Backend Instance

**Action:** with a multi-replica backend, stop one replica or delete one Pod in staging. If the Gateway uses a Kubernetes Service, the Service shifts traffic to remaining Ready endpoints. If using `lb://SERVICE-ID`, verify LoadBalancer selects an active instance.

**Observe:**

- Upstream request successes/failures.
- Service/EndpointSlice and ServiceInstance lists.
- Retry attempts and circuit breaker state.
- p95/p99 latency while endpoints update.

**Pass when:** the Gateway keeps serving via remaining instances; errors stay bounded within the expected convergence window; no retry amplification or prolonged 5xx spike occurs.

The Compose demo with a single `orders` container cannot prove multi-instance failover. Use Kubernetes replicas or a discovery-backed route for this drill.

### 10.2. Drill B — Upstream Slower Than Response Timeout

Use Toxiproxy or a test backend capable of delaying responses. Inject latency exceeding the Gateway's configured response timeout.

Example Gateway WebFlux 5.x configuration:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 2s
~~~

Connect timeout in the example is in milliseconds; response timeout is a duration. Values are for lab use only.

**Observe:** latency, timeout/error statuses, retry counts, circuit breaker state, and whether the backend continues processing abandoned requests.

**Pass when:** requests exceeding the deadline fail per policy; the Gateway does not hold resources indefinitely; retries apply only to safe methods/idempotent operations; and the circuit breaker does not turn failures into fake business successes.

### 10.3. Drill C — Backend Returns 503

Configure a mock backend to return HTTP 503 for a window of time. Distinguish this case from connection refused or missing ServiceInstance:

- Upstream HTTP 503: the backend received the request and returned a response.
- Connect failure: the Gateway received no HTTP response from the backend.
- Empty ServiceInstance: LoadBalancer found no target.

**Pass when:** logs/metrics/traces accurately pinpoint the failure source; status/fallback matches the API contract; alerts and runbooks point to backend health/capacity rather than discovery when discovery is healthy.

### 10.4. Drill D — Redis Rate Limiter Unavailable

If a route uses `RedisRateLimiter`:

1. Record baseline quota behavior and Redis metrics.
2. In staging, stop Redis or block connections from the Gateway.
3. Send requests at a low rate, then increase.
4. Observe Gateway errors/statuses, logs, and Redis connection failures.
5. Restore Redis and check quota state.

Proactively decide on a **fail-open or fail-closed** policy when Redis is unavailable. Never assume the Gateway always returns 429 or always lets traffic through; behavior depends on filter/error handling and version. For sensitive APIs, fail-open bypasses quotas; fail-closed interrupts traffic. Document the decision and test it against the contract.

### 10.5. Drill E — Gateway Restart / Rollout

Perform a rolling update or delete a Pod via eviction/rollout in staging:

~~~bash
kubectl rollout restart deployment/gateway -n app
kubectl rollout status deployment/gateway -n app
kubectl get pods -n app -l app=gateway -w
kubectl get endpointslices -n app
~~~

**Observe:**

- Readiness transitions and endpoint updates.
- Ready replicas never drop below the PDB during properly managed voluntary disruptions.
- In-flight requests drain within termination grace.
- No 502/503 spike occurs while replacement Pods start.
- New replicas run the right image digest and config revision.

PDBs are enforced via the Eviction API during voluntary disruptions; direct Pod deletion can bypass PDBs. Never run destructive tests on a production cluster for practice.

### 10.6. Drill F — Monitoring/Collector Disruption

In staging, temporarily stop Prometheus or the OpenTelemetry Collector:

- Does the Gateway continue serving business requests?
- Does the Prometheus scrape gap trigger an alert?
- Do trace export queues/drops/failures rise?
- Does the exporter add noticeable latency or resource overhead?
- Once the Collector returns, does export resume or was data dropped?

Telemetry backends must never become a synchronous hard dependency for business requests. Monitor exporter errors/queues and verify actual retention/gap behavior.

### 10.7. Drill G — Rolling Back a Faulty Release

Before the drill, record the image digest and config revision of the stable release. Deploy an intentional canary change introducing a test fault, observe alerts, then roll back.

~~~bash
kubectl rollout undo deployment/gateway -n app
kubectl rollout status deployment/gateway -n app
kubectl get deployment gateway -n app -o wide
~~~

If configuration is managed via ConfigMap/Helm/GitOps, roll back the config revision as well; reverting the image while keeping new properties can prevent the older app from binding configuration. Verify route definitions, secret references, and schema/cache compatibility.

**Pass when:** both image and config return to the same release; replicas are Ready; smoke tests pass; error rates/latency return to baseline; and no data loss or duplicate side effects occur.

## 11. Runbook When the Gateway Degrades

### 11.1. Response Sequence

1. **Confirm impact:** which routes, which regions/zones, since when, and what statuses/latencies.
2. **Check rollout:** image digest, config revision, Ready replicas, restarts, and events.
3. **Classify errors:** route misses, 401/403/429, upstream HTTP 5xx, no ServiceInstance, connect/DNS/TLS/timeouts, or fallbacks.
4. **Correlate upstream:** backend request counts, health, latency, dependencies/databases.
5. **Check Gateway resources:** CPU throttling, heap/direct memory, GC pauses, pool pending acquires, event loop.
6. **Check resilience:** retry attempts, circuit breaker states, fallback behavior.
7. **Choose mitigation:** roll back, shed traffic, scale, disable a route in a controlled way, or restore a backend dependency.
8. **Verify recovery:** smoke tests, low load, error ratio, and p95/p99.
9. **Record timeline:** trigger, detection, mitigation, recovery, and follow-up actions.

### 11.2. Symptom → Investigation Table

| Symptom | First area to investigate |
| --- | --- |
| Sudden 404 spike | Route predicates, path rewrites, route config revision |
| Rising 401/403 | JWT issuer/JWK, scopes, identity provider |
| Rising 429 | Rate limiter, Redis, quota key, client traffic |
| Rising 502/503 | Upstream status, LoadBalancer instances, connect errors, circuit breaker |
| Rising 504 | Backend latency, response timeout, network path |
| p99 rises while p50 stays flat | Slow instance, queuing, connection pool, dependency tail latency |
| Gateway OOM/restarts | Heap/direct buffers, body caching, container limits |
| Missing metrics | Actuator exposure, Prometheus scrape, registry dependency |
| Missing traces | Sampling, OTLP endpoint, Collector connectivity, propagation |
| Traffic lost after rollout | Readiness, Service selectors, image/config mismatch, public ingress |

### 11.3. Evidence to Archive After Each Drill

- k6 summary and raw output.
- Image digest, config revision, and replica count.
- Prometheus dashboard/export covering the test window.
- Redacted sample trace IDs.
- Gateway/backend logs scrubbed of credentials/PII.
- Kubernetes events, rollout history, and EndpointSlice snapshots.
- Pass/fail results against agreed criteria.
- Time to detect, time to recover, and owner.

Never store raw bearer tokens, cookies, customer payloads, or private keys in an evidence pack.

## 12. Full-Lab Acceptance Criteria

| Area | Completion criterion |
| --- | --- |
| Build | CI verify passes, image has immutable tag/digest, SBOM/scan evidence |
| Container | Multi-stage, non-root, read-only filesystem if supported by app, resource limits |
| Deployment | 3 replicas, valid startup/liveness/readiness, rolling updates and graceful shutdown |
| Availability | Appropriate PDB and Service selectors; private management port |
| Load | Smoke/load/stress/soak profiles, k6 thresholds, and archived outputs |
| Performance | Throughput, p95/p99, error ratio, and resource usage compared against SLOs |
| Metrics | Prometheus scrapes every replica; Grafana shows traffic/errors/latency/JVM/pool |
| Tracing/logs | Traces span Gateway to backend; logs carry route/status/trace ID and are redacted |
| Recovery | Completed at least backend-down, backend-slow, Gateway rollout, and rollback drills |
| Runbook | Includes symptom mapping, mitigation, verification, and rollback instructions |

### 12.1. Pre-Completion Checklist

- [ ] Dockerfile builds cleanly using the project's Maven/Gradle Wrapper.
- [ ] Tests run before the image is published.
- [ ] Image contains no credentials, `.env` files, or private keys.
- [ ] Runtime executes non-root with least privilege.
- [ ] Management port is not publicly exposed.
- [ ] Health probes distinguish startup, liveness, and readiness.
- [ ] CPU/memory requests/limits are measured rather than copied verbatim from lab values.
- [ ] Prometheus scrapes every Gateway replica.
- [ ] Grafana displays request rate, statuses, p95/p99, JVM, and pool metrics.
- [ ] k6 smoke/load/stress/soak runs have clear outputs and thresholds.
- [ ] Load generator never becomes the bottleneck of the measurement.
- [ ] Expected 429s are separated from unexpected failures.
- [ ] Traces propagate across the Gateway and backend.
- [ ] Logs/traces/metrics contain no tokens, cookies, or PII.
- [ ] Backend-down and backend-slow drills match the contract.
- [ ] Redis/telemetry failure policies are tested if those dependencies exist in the architecture.
- [ ] Rolling updates and rollbacks are rehearsed in staging.
- [ ] Evidence pack and runbook are ready for on-call operators.

## 13. Summary and References

A Gateway is ready for operations only when you can **package it reproducibly, deploy it safely, measure its limits, observe requests, and recover with verification**. Good Docker images keep runtimes lean and least-privileged; Kubernetes probes/PDBs/graceful shutdown manage Pod lifecycles; k6 quantifies throughput and tail latency; Prometheus/Grafana/Tracing locate bottlenecks; and recovery drills prove the system responds properly when upstreams, Redis, the Gateway, or monitoring degrade.

Never declare production capacity from a single successful load test. Record configuration, image digest, workload profile, SLOs, resource limits, and runtime environment alongside results; repeat whenever changing Gateway versions, routes/filters, backends, JVM, or infrastructure.

### Official References

- [Spring Boot — Container Images and Dockerfiles](https://docs.spring.io/spring-boot/reference/packaging/container-images/).
- [Spring Boot — Actuator Metrics and Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Actuator Health Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Tracing and OpenTelemetry](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).
- [Spring Cloud Gateway — Configuration Properties and Observability](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Docker — Build best practices](https://docs.docker.com/build/building/best-practices/).
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/).
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
- [Kubernetes — Pod Disruptions and PodDisruptionBudget](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/).
- [Grafana k6 — Scenarios and Executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/).
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/).
