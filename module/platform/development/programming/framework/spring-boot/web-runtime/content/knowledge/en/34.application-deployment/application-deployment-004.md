# Configuring Ports, Listen Addresses, and Resources in Containers

## 1. Context of the Lesson

This lesson belongs to **Application Deployment** in the Spring Boot web runtime module. An application runs fine on a developer machine, yet when packaged into Docker, deployed to Kubernetes, or moved to a PaaS, it runs into errors:

- Spring Boot logs `Tomcat started on port 8080`, yet calling `localhost:18080` from the host fails.
- The Dockerfile declares `EXPOSE 8080`, yet no port opens on the host machine.
- A Pod shows status `Running`, yet the Service has no ready endpoints, or clients receive connection refused.
- The container gets `OOMKilled` even though the Java heap never reached `-Xmx`.
- CPU quota is one core, yet increasing Tomcat worker threads does not improve throughput.
- A health probe checks a different management port and reports healthy while the main HTTP connector is not accepting requests.
- Rolling updates abruptly cut long-lived connections because the Java process did not receive `SIGTERM` properly.

To fix these, you must separate **the application layer, the network namespace layer, and the resource management layer**. `server.port` is a Java process decision; Docker `-p` and Kubernetes `Service.targetPort` are routing outside the process; memory/CPU cgroups are runtime budgets that the JVM must respect.

Learning goals after this lesson:
1. Explain `server.port`, `server.address`, `PORT`/`SERVER_PORT`, and Spring Boot 3.5 externalized configuration.
2. Distinguish `127.0.0.1`, `0.0.0.0`, container IP, Pod IP, and host/Pod network namespaces.
3. Configure Dockerfile, `EXPOSE`, `docker run -p`, Compose, Kubernetes `containerPort`, Service `port`/`targetPort`, and Ingress.
4. Set sensible CPU, RAM, JVM heap/direct/native memory, file descriptor, and temp storage limits.
5. Implement liveness/readiness/startup probes on the right port while preserving graceful shutdown behavior in containers.
6. Build a runnable Java 17 application, package a non-root multi-stage image, and verify the actual port over HTTP.
7. Diagnose wrong ports, wrong bind addresses, CPU throttling, memory pressure, and probe errors before wrongly editing controllers.

> **Practice versions:** Spring Boot **3.5.x**, Java **17+**, Gradle Groovy, Spring MVC/Tomcat, Docker, and basic Kubernetes. In Boot 3.5, the embedded server listens on port **8080** by default unless overridden. Some container/JVM/probe behaviors vary by kernel, JDK patch version, and platform; always inspect runtime data rather than assuming demo numbers are universal defaults.

## 2. Distinguishing the Three Ports in an HTTP Request

A Docker example:

~~~text
Browser/host
    |
    | http://localhost:18080/api/hello
    v
Host port 18080
    |
    | docker -p 18080:8080
    v
Container port 8080
    |
    | Spring server.port=8080
    v
Embedded Tomcat -> Controller
~~~

A Kubernetes example:

~~~text
Client in cluster -> runtime-demo:80
                            |
                            v
                   Service.port = 80
                            |
                            v
                   Service.targetPort = http
                            |
                            v
                   Pod containerPort name=http = 8080
                            |
                            v
                   Spring Boot listens :8080
~~~

Having different port numbers is **completely normal**. Each routing hop simply needs to match:

| Property | Managed layer | Example | Actually starts a listener? |
|---|---|---|---|
| `server.port` | Spring Boot JVM | 8080 | **Yes**: embedded server binds port |
| `server.address` | Spring Boot JVM | `0.0.0.0` | Selects IP/interface to bind |
| `EXPOSE 8080` | Dockerfile image metadata | 8080 | **No** |
| Docker `-p 18080:8080` | Docker host NAT/publish | Host 18080 → container 8080 | Publishes host port, does not change Spring |
| Compose `ports` | Docker networking | `127.0.0.1:18080:8080` | Host mapping |
| Kubernetes `containerPort` | Pod spec | 8080 | **No**: port documentation |
| Kubernetes `Service.port` | Service | 80 | Client-facing port of the Service |
| Kubernetes `Service.targetPort` | Service → Pod | 8080 or `http` | Selects destination port on the Pod |
| Ingress/Gateway | Edge | HTTPS 443 | Routes to Service, does not change Java port |
| `management.server.port` | Spring Actuator | 9090 | Can start a separate management listener |

**Rule:** Spring must listen on the exact port that `-p`/`targetPort` points to; do not force Java to listen on public ports 80/443 when TLS terminates at an Ingress or reverse proxy.

## 3. server.port: Default, Overrides, and Random Port

Spring Boot 3.5 defaults the main HTTP port to **8080**. You can declare:

~~~yaml
server:
  port: 8080
~~~

Or:

~~~properties
server.port=8080
~~~

Or override at launch:

~~~bash
java -jar app.jar --server.port=9090
~~~

Or OS env:

~~~bash
SERVER_PORT=9090 java -jar app.jar
~~~

Or Java system property:

~~~bash
java -Dserver.port=9090 -jar app.jar
~~~

`SERVER_PORT` is mapped to `server.port` by Spring Boot relaxed binding. Boot has multiple property sources with precedence rules; command-line arguments generally override config files and env vars take precedence over values in `application.yml`. When the actual port differs from expectations, check all env vars, CLI args, system properties, profile-specific configs, and startup logs instead of guessing Docker changed it.

### The PORT Variable Provided by PaaS Platforms

Some PaaS platforms provide `PORT`, but **`PORT` is not a standard Boot property name that maps automatically to `server.port`**. Write it explicitly:

~~~yaml
server:
  port: ${PORT:8080}
~~~

Placeholder explanation:
- When `PORT=9090`: Spring uses 9090.
- When `PORT` is unset: uses 8080.
- If `SERVER_PORT` or `--server.port` with higher precedence is set, it can override this YAML.

**Pick one contract:** either use `SERVER_PORT` directly from the environment, or use `PORT` in YAML. Do not set two conflicting sources and assume which one wins.

### server.port=0 and =-1

- `server.port=0`: lets the OS pick an available ephemeral port; useful for integration tests/`@LocalServerPort`.
- `server.port=-1`: per Boot docs, disables HTTP endpoints while still allowing a `WebApplicationContext` to be created.
- `spring.main.web-application-type=none`: disables the web application type entirely, not identical to `server.port=-1`.

**Do not use port 0 arbitrarily when Kubernetes `Service.targetPort` is fixed**: the Pod may listen on an ephemeral port other than 8080, while the Service still sends traffic to 8080 and fails to connect.

### Port Conflicts Are Scoped to a Network Namespace

Two normal Docker containers have separate network namespaces and can both listen on **internal port 8080**. So can two Kubernetes Pods. However, **two containers inside the same Kubernetes Pod share a network namespace**, so they will conflict if both bind the same IP:port. A Docker host will also conflict if two containers both publish **host port 18080**.

## 4. server.address and Bind Address

~~~yaml
server:
  address: "0.0.0.0"
  port: 8080
~~~

Meaning of values:

| Bind address | Meaning | Receives requests via Pod/container IP? |
|---|---|---|
| `0.0.0.0` | All IPv4 interfaces in the **process's namespace** | Usually yes if network/port allow |
| `127.0.0.1` | IPv4 loopback of **that namespace** | Usually **no** when requests hit Pod IP |
| A specific IP | The interface with that address | Only if the IP exists in the namespace and routes there |
| `::` | IPv6 wildcard | IPv4 dual-stack depends on JVM/OS socket configuration |
| Hostname | Resolves then binds IP | Can fail if hostname does not resolve to a local IP |

### 0.0.0.0 Does Not Automatically Mean Public Internet

`0.0.0.0` only means the process accepts connections on all IPv4 interfaces of its network namespace. Public exposure depends on host port publishing, firewalls, Kubernetes Service/Ingress, NetworkPolicies, cloud security groups, and authentication.

### 127.0.0.1 Inside a Container Is Not the Host's localhost

~~~text
Host namespace:       localhost -> host loopback
Container A:          localhost -> A loopback
Container B:          localhost -> B loopback
Pod X:                localhost -> shared loopback of containers in the same Pod
Pod Y:                localhost -> loopback of Pod Y, not Pod X
~~~

If Spring listens on `127.0.0.1:8080` inside a Docker container, Docker port publishing `-p 18080:8080` typically forwards to the container's network IP:8080, **not reaching a loopback-only socket**; host requests fail even though Boot logs port 8080. Change to `server.address=0.0.0.0` for the main container listener.

Conversely, binding a management listener to loopback can be useful for internal tasks in the same namespace, but **does not replace auth/security** and makes remote scrapers/probes unable to reach it.

### What Are the Risks of Binding a Hostname or Pod IP Directly?

Pod IPs change on restarts and rolling deploys. Hardcoding a Pod IP in `server.address` or an HTTP client URL can cause the new version to fail to bind or clients to miss the right Pod. Use `0.0.0.0` for the listener and **Service DNS** when connecting to another service. Do not assume `localhost` resolves to a different Kubernetes service.

## 5. Environment Variables, Profiles, and Precedence Order

Configuration sources:

| Source | Example | Used for |
|---|---|---|
| `application.yml` | `server.port: 8080` | Defaults in source |
| OS environment | `SERVER_PORT=9090` | Runtime override |
| Custom env placeholder | `server.port: ${PORT:8080}` | PaaS providing `PORT` |
| CLI arg | `--server.port=9090` | Test/launcher override |
| JVM option | `-Dserver.port=9090` | Java process flag |
| ConfigMap | `PORT=8080` | Non-sensitive config in K8s |
| Secret/external vault | Password/token/cert | Data requiring protection |

A clean, controllable configuration for the practice lab:

~~~yaml
server:
  port: ${PORT:8080}
  address: ${SERVER_ADDRESS:0.0.0.0}
  shutdown: graceful
~~~

When running Docker, set `PORT=8080` and avoid also setting `SERVER_PORT` to compete in precedence. `SERVER_ADDRESS=127.0.0.1` can be used to reproduce an external bind failure, while normal deployments should keep `0.0.0.0`.

If `application-prod.yml`, `spring.profiles.active`, `spring.config.additional-location`, or `SPRING_APPLICATION_JSON` exist, they can override values. Do not guess “Docker changed the port” when a profile file is actually the source of the override. To investigate, inspect startup logs, **secured** actuator `configprops`/`env`, or a Java runtime endpoint that does not expose secrets.

## 6. Dockerfile EXPOSE Does Not Publish a Host Port

In a Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

merely documents that the image expects to use port 8080. It **does not create a host-published socket**. To reach the app from the host, use:

~~~bash
docker run --rm -p 18080:8080 runtime-demo:1.0
~~~

- 18080 on the host.
- 8080 inside the container.
- Boot still listens on 8080.
- The host accesses `http://localhost:18080`.

### Publish Only on Host Loopback for Safe Learning

~~~bash
docker run --rm \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

`127.0.0.1` in Docker `-p` is on **the host side**, not Spring's `server.address`. With standard Docker daemons, omitting the host IP may expose the published port across all host interfaces; do not expose debug/Actuator ports on shared machines for convenience.

### -p vs -P

- `-p 18080:8080`: explicit mapping.
- `-P`/`--publish-all`: Docker assigns random host ports for `EXPOSE`d ports; view the mapping with `docker port`.
- `--expose`: adds port metadata, does not publish.
- `--network host` (where supported by the runtime) makes the container share the host network, changing isolation and typically bypassing port publishing; do not use it as a “quick fix” for wrong port mappings.

### Common Scenarios

| Spring listener | Docker mapping | Outcome |
|---|---|---|
| `0.0.0.0:8080` | `-p 18080:8080` | Host reaches 18080 |
| `0.0.0.0:9090` | `-p 18080:8080` | Wrong target 8080, request fails |
| `127.0.0.1:8080` | `-p 18080:8080` | Loopback-only, external forwarding usually fails |
| `0.0.0.0:8080` | `EXPOSE 8080` without `-p` | Not accessible from host localhost |
| `0.0.0.0:8080` | `-p 127.0.0.1:19090:8080` | Host uses 19090, listener stays 8080 |

## 7. Runnable Spring Boot Java 17 Demo

The demo provides:
- `GET /api/hello` returning fixed JSON.
- `GET /api/runtime` reading the **actual port** embedded Tomcat is listening on, JVM processor count, and max heap size.
- Actuator health, liveness, and readiness paths.
- Never returning env vars, tokens, or JVM secret options over HTTP endpoints.

### 7.1. Create the Project

In Spring Initializr:
- Spring Boot **3.5.x**.
- Java **17+**.
- Gradle **Groovy**.
- Group: `demo`; Artifact: `runtime-demo`.
- Dependencies: **Spring Web**, **Spring Boot Actuator**, **Spring Boot Starter Test**.

In the Initializr `build.gradle`, dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Add after the dependencies block to produce an executable JAR with a fixed name:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'app.jar'
}
~~~

These are **Gradle fragments** inside a project that already has the Spring Boot plugin/repositories/Gradle wrapper; not a standalone complete `build.gradle`.

### 7.2. Complete Java Source File

Create `src/main/java/demo/runtime/ContainerRuntimeApplication.java`:

~~~java
package demo.runtime;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ContainerRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerRuntimeApplication.class, args);
    }
}

@RestController
class RuntimeController {

    private final ServletWebServerApplicationContext context;

    RuntimeController(ServletWebServerApplicationContext context) {
        this.context = context;
    }

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }

    @GetMapping("/api/runtime")
    public Map<String, Object> runtime() {
        Runtime jvm = Runtime.getRuntime();

        return Map.of(
            "message", "running",
            "listenPort", context.getWebServer().getPort(),
            "availableProcessors", jvm.availableProcessors(),
            "maxHeapMiB", jvm.maxMemory() / (1024 * 1024)
        );
    }
}
~~~

**Source structure QA:**
- `ContainerRuntimeApplication.java` has one public class matching its filename plus a package-private `RuntimeController`; Java 17 allows this layout.
- `@SpringBootApplication` scans `demo.runtime`, registering the controller.
- `ServletWebServerApplicationContext.getWebServer().getPort()` returns the actual bound port, including when `port=0` in tests.
- `Runtime.availableProcessors()` reflects JVM processor count heuristics/flags, **not a guarantee of host physical cores or CPU requests**.
- `Runtime.maxMemory()` is the JVM's max Java heap, **not process RSS or the cgroup memory limit**.
- `Map.of` JSON does not guarantee field ordering, so tests should assert by key rather than raw string matching.

If using Spring WebFlux/Reactor Netty instead of MVC/Tomcat, the corresponding context interface is reactive; do not copy `ServletWebServerApplicationContext` expecting it to work with a reactive-only starter.

### 7.3. application.yml

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: ${PORT:8080}
  address: ${SERVER_ADDRESS:0.0.0.0}
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Meaning:
- `PORT` defaults to `8080` when unset.
- `SERVER_ADDRESS` defaults to `0.0.0.0` when unset.
- `server.shutdown: graceful` is explicitly declared; Boot 3.5 enables graceful shutdown by default for supported embedded web servers.
- `timeout-per-shutdown-phase=25s` is **the wait budget per `SmartLifecycle` phase**, not a hard timeout for the whole process/container.
- Health probes are enabled locally and in clusters.
- `add-additional-paths=true` exposes `/livez` and `/readyz` on the **main server port**, allowing probes to verify the exact HTTP connector serving traffic.

### 7.4. Run Locally

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal:

~~~bash
curl -sS -i http://localhost:8080/api/hello
curl -sS http://localhost:8080/api/runtime
curl -sS -i http://localhost:8080/readyz
~~~

`/api/hello` returns HTTP 200 and JSON:

~~~json
{"message":"hello"}
~~~

`/api/runtime` may return:

~~~json
{
  "message": "running",
  "listenPort": 8080,
  "availableProcessors": 2,
  "maxHeapMiB": 384
}
~~~

**The numbers `2` and `384` are purely illustrative, not fixed outputs.** They depend on the JVM, cgroups/host, and flags. `listenPort` is `8080` unless overridden. `/readyz` returns success once the app is accepting traffic.

### 7.5. Testing Port Changes

Build the executable JAR:

~~~bash
./gradlew bootJar
~~~

Windows:

~~~powershell
.\gradlew.bat bootJar
~~~

Run:

~~~bash
java -jar build/libs/app.jar --server.port=9090
~~~

Verify:

~~~bash
curl -sS http://localhost:9090/api/runtime
~~~

Expected JSON has `"listenPort":9090`. If the JAR was named differently in another build, adjust to the actual output; the demo Gradle config sets `app.jar`.

Try a random port:

~~~bash
java -jar build/libs/app.jar --server.port=0
~~~

The OS chooses an available port; check startup logs or use `@LocalServerPort` in tests to inspect it. Do not hardcode clients to 8080 in that case.

## 8. Multi-Stage Dockerfile for Java 17

Create `Dockerfile` at the project root:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS builder

WORKDIR /workspace

COPY gradlew ./gradlew
COPY gradle/ ./gradle/
COPY settings.gradle build.gradle ./
COPY src/ ./src/

RUN chmod +x ./gradlew && ./gradlew --no-daemon bootJar

FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --from=builder --chown=10001:10001 \
    /workspace/build/libs/app.jar /app/app.jar

USER 10001:10001

# EXPOSE documents the port, does not publish on host.
EXPOSE 8080

# Exec form so JVM receives SIGTERM directly.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is a complete Dockerfile for a **Gradle Groovy project from Initializr** with `bootJar.archiveFileName='app.jar'` added. If using `build.gradle.kts` or multi-module, adjust the `COPY` and Gradle output paths accordingly. Do not put a demo Dockerfile into production without scanning base images and pinning versions/digests per security policy.

Benefits:
- The builder image uses a JDK to compile.
- The runtime image only needs a JRE + `app.jar`, no Gradle in production.
- The Java process runs as UID/GID 10001, avoiding root unnecessarily.
- `EXPOSE 8080` is metadata.
- Exec-form `ENTRYPOINT` lets the platform send signals directly to the JVM, supporting graceful shutdown.
- Files are copied separately between builder and runtime; no source code or build tools enter the runtime image.

Create `.dockerignore`:

~~~text
.git
.gradle
build
out
*.log
.env
.env.*
.idea
.vscode
~~~

Do not ignore `gradlew` or `gradle/wrapper`, as the Docker build needs them.

### Build and Run

~~~bash
docker build -t runtime-demo:1.0 .
~~~

Run:

~~~bash
docker run --rm \
  --name runtime-demo \
  --memory=768m \
  --cpus=1 \
  -e PORT=8080 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=55.0" \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

On a host terminal:

~~~bash
curl -sS -i http://localhost:18080/api/hello
curl -sS http://localhost:18080/api/runtime
curl -sS -i http://localhost:18080/readyz
~~~

**What to observe:** `/api/runtime` JSON still reports `listenPort=8080`, not 18080. `JAVA_TOOL_OPTIONS` affects JVM heap sizing, not the HTTP port. `--memory`/`--cpus` create resource limits that the containerized JVM must operate within.

### Deliberately Testing a Mismatched Mapping to Understand the Error

~~~bash
docker run --rm \
  -e PORT=9090 \
  -p 127.0.0.1:19090:8080 \
  runtime-demo:1.0
~~~

Spring listens on **9090**, but Docker forwards host 19090 to container 8080, resulting in connection refused/reset. Fix:

~~~bash
docker run --rm \
  -e PORT=9090 \
  -p 127.0.0.1:19090:9090 \
  runtime-demo:1.0
~~~

Even if the Dockerfile says `EXPOSE 8080`, an explicit `-p ...:9090` works; however, update metadata/manifests when changing the actual port for production deployments.

### What If You Bind Loopback Inside?

~~~bash
docker run --rm \
  -e SERVER_ADDRESS=127.0.0.1 \
  -p 127.0.0.1:18080:8080 \
  runtime-demo:1.0
~~~

Spring's listener only sits on **container loopback**, so host-published traffic routed to the container IP cannot reach it. Revert to `0.0.0.0` after testing.

## 9. Docker Compose and Service DNS

Create `compose.yaml`:

~~~yaml
services:
  runtime:
    build: .
    image: runtime-demo:1.0
    environment:
      PORT: "8080"
      SERVER_ADDRESS: "0.0.0.0"
      JAVA_TOOL_OPTIONS: "-XX:MaxRAMPercentage=55.0"
    ports:
      - "127.0.0.1:18080:8080"
    restart: unless-stopped
~~~

Run:

~~~bash
docker compose up --build
~~~

The host accesses `http://localhost:18080/api/hello`. Another container **on the same Compose network** calls `http://runtime:8080/api/hello` using the **service name** and container port—not host-published 18080 or `localhost` of another container.

`restart: unless-stopped` does not fix wrong ports or memory leaks; it only restarts the process per Docker policy. Compose `mem_limit`/`cpus`/`deploy.resources` support and semantics depend on the Compose/runtime version, so verify actual enforcement with `docker inspect`/`docker stats` when used.

## 10. Kubernetes containerPort, Service.port, targetPort

Pod fragment:

~~~yaml
ports:
  - name: http
    containerPort: 8080
    protocol: TCP
~~~

This is metadata for routing/probes; it **does not automatically set** `server.port`. The app must listen on Pod interface `:8080` via Spring configuration.

Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: runtime-demo
spec:
  selector:
    app: runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

- `port: 80`: port that in-cluster clients use to call the Service.
- `targetPort: http`: looks up named port `http` in the Pod, here 8080.
- `selector app: runtime-demo` must match the Pod's labels.
- `type: ClusterIP` does not open a public Internet endpoint; for public access use Ingress/Gateway/LoadBalancer.
- If the Pod is not ready or the selector is wrong, the Service will have no usable endpoints.
- If Spring listens on `127.0.0.1:8080`, kube-proxy traffic sent to **Pod IP**:8080 will fail to find the listener.

Both named `targetPort: http` and numeric `targetPort: 8080` are valid; named ports clarify intent when port numbers change. `containerPort` is not `hostPort`; do not add `hostPort: 8080` just to work around a misconfigured Service route.

## 11. Kubernetes Deployment + Service Manifest

Example matching the Java demo and Dockerfile above:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-demo
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: runtime-demo
  template:
    metadata:
      labels:
        app: runtime-demo
    spec:
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: runtime
          image: registry.example.test/runtime-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: PORT
              value: "8080"
            - name: SERVER_ADDRESS
              value: "0.0.0.0"
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=55.0"
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "768Mi"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 3
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: runtime-demo
spec:
  selector:
    app: runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

**Mandatory note before deploying:** `registry.example.test/runtime-demo:1.0.0` is an illustrative image name, not a pre-existing registry for learners. Replace it with an image you built, tagged, pushed, and have pull permissions for in the cluster (or loaded via local cluster tools). Do not deploy a nonexistent image and blame Spring for `ImagePullBackOff`.

### Explaining Resources and Probes

- `resources.requests` drives scheduling, CPU shares/priority, and expected Pod memory.
- `resources.limits.cpu` triggers CPU quota/throttling under heavy load.
- `resources.limits.memory` is enforced by kernel cgroups and can trigger OOMKill if the process exceeds physical memory.
- `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=55.0` hints max heap at roughly 55% of the memory base detected by the JVM; it does not hard-cap the entire process.
- `readOnlyRootFilesystem:true` prevents writes to the image layer, requiring a `/tmp` volume since Java/HTTP frameworks can create temp files.
- `startupProbe` protects slow-starting apps from premature liveness kills.
- `readinessProbe` decides whether the Pod receives new Service traffic.
- `livenessProbe` detects process failure requiring a restart.
- `terminationGracePeriodSeconds:60` is the **total Pod termination budget**, including `preStop` if configured and shutdown phases; it is not added on top of Spring's timeout.

### Verify Once the Image Is Valid

~~~bash
kubectl apply -f k8s-runtime.yaml
kubectl get pods -l app=runtime-demo
kubectl get service runtime-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=runtime-demo
kubectl rollout status deployment/runtime-demo
~~~

In a ClusterIP-only environment, you can debug from a laptop:

~~~bash
kubectl port-forward service/runtime-demo 18080:80
~~~

Then in another terminal:

~~~bash
curl -sS -i http://localhost:18080/api/hello
curl -sS http://localhost:18080/api/runtime
curl -sS -i http://localhost:18080/readyz
~~~

With port-forward, the host uses 18080, the Service port is 80, and the Pod still listens on 8080. `kubectl port-forward` is a temporary debug tunnel, **not a public Ingress**.

## 12. Ingress, TLS, and Reverse Proxy

A real traffic flow may look like:

~~~text
https://api.example.com:443
       |
       v
Ingress / Load Balancer, TLS termination
       |
       | Service runtime-demo:80
       v
Kubernetes Service
       |
       | targetPort http -> 8080
       v
Pod IP:8080
       |
       v
Spring Boot server.port=8080
~~~

TLS `443` at the edge does not mean Java must listen on port 443. Within a private cluster, internal HTTP or mTLS/end-to-end TLS may be used per security policy. If the app generates redirects, OAuth callback URLs, or `Secure` cookies, ensure scheme/host are restored accurately from **trusted proxies**.

Spring Boot provides `server.forward-headers-strategy` to control `Forwarded`/`X-Forwarded-*` handling. **Never blindly trust arbitrary forwarded headers sent by external clients**; control the proxy chain and strip/overwrite headers at the edge before the application uses them.

Do not use `0.0.0.0` as an automatic way to expose to the public Internet; it only binds interfaces. Public exposure is controlled by Service type, Ingress, firewalls/cloud security groups, and NetworkPolicies.

## 13. CPU Requests, CPU Limits, and Throttling

In Kubernetes:

~~~yaml
resources:
  requests:
    cpu: "200m"
  limits:
    cpu: "1000m"
~~~

- `200m` CPU is 0.2 CPU units considered by the scheduler when placing the Pod; it can influence CPU shares under node contention.
- `1000m` is a nominal 1 CPU unit limit; the kernel typically enforces it via quota/throttling.
- CPU request does not hard-cap actual CPU; when the node is idle, the process can burst above its request up to its limit.
- A 1-core CPU limit **does not give 8 worker threads the throughput of 8 cores**.
- Increasing `server.tomcat.threads.max` while CPU-throttled can increase context switches, queuing, and latency.
- If the app mostly waits on DB/HTTP clients, raising the CPU limit may not fix the bottleneck. Measure downstream latency/connection pools first.

Java 17's JVM uses `Runtime.availableProcessors()` for many heuristics (GC, `ForkJoinPool`, executor sizing); it can reflect cgroup constraints depending on JDK/OS. Do not assume it equals host physical cores.

You can override the JVM's active processor count:

~~~bash
JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=2"
~~~

However, this flag **does not increase the container's CPU quota**. Only use it when benchmarks show JVM heuristics need tuning.

## 14. Memory Requests/Limits and JVM Heap: Two Different Budgets

~~~yaml
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "768Mi"
~~~

- Memory request primarily guides scheduling and availability planning.
- Memory limit is the cgroup budget enforced by the kernel; exceeding it can OOMKill the process/container.
- Java `-Xmx` only caps the **heap**; the process also uses metaspace, code cache, direct/Netty buffers, thread stacks, TLS/native memory, mapped files, and other overhead.
- `-XX:MaxRAMPercentage` tunes **max heap sizing**, not total RSS.
- Without an appropriate memory limit, a container-aware JVM might size the heap from a large host memory base; design JVM and platform settings together.

A rough budget formula:

~~~text
Container memory limit
  >= Java heap live/committed
   + Direct/native buffers
   + Metaspace and code cache
   + GC/thread stack overhead
   + TLS/HTTP I/O buffers
   + Temporary/shared/accounted memory
   + Safety margin
~~~

You cannot measure every item precisely from a single snapshot; reserved, committed, RSS, and cgroup memory accounting differ.

Design example **for consideration, not a universal production default**:

| Item | Example |
|---|---:|
| Container memory limit | 768 MiB |
| JVM target max heap 55% | ~422 MiB |
| Remainder by subtraction | ~346 MiB |
| Used for | Native/direct, stacks, metaspace, TLS, GC, buffers, margin |

`422 MiB` is only an estimate—the JVM may not choose that exact figure due to flags, small-heap heuristics, rounding, and JDK implementation. Max heap is not heap used, and the remainder is not guaranteed free memory. Measure actual process/container memory under load.

### Java 17 Container Support

On supported Linux/HotSpot platforms, `UseContainerSupport` is enabled by default in Java 17; the JVM detects CPU/memory constraints via cgroups. Inspect:

~~~bash
java -Xlog:os+container=info -version
~~~

When JDK diagnostics are available:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

`-Xmx512m` normally overrides max heap computed from percentage. Do not set conflicting `-Xmx` and `MaxRAMPercentage` unless you understand precedence. Avoid `-XX:-UseContainerSupport`, because the JVM may size itself against the host instead of the container, raising OOMKilled risk.

### OOMKilled vs Java Heap OOM

- `java.lang.OutOfMemoryError: Java heap space`: Java heap is exhausted.
- `OutOfMemoryError: Cannot reserve ... direct buffer memory`: direct/native allocation pressure or related limits.
- Pod `OOMKilled`: kernel/cgroup termination; there may be no Java heap OOM log at all.
- High process RSS with low JVM heap: investigate native/direct memory, threads, and mapped memory, not just `-Xmx`.

Monitor `docker stats`, `kubectl top pod`, JVM Micrometer `jvm.memory.used`, `jvm.gc.pause`, NIO buffer pools, and Reactor Netty metrics as applicable, alongside OS/cgroup metrics. One high snapshot **is not proof of a memory leak**; inspect trends, active requests, and GC.

## 15. Threads, File Descriptors, and Network Connections

Containers are also bounded by:
- OS file descriptor/socket limits.
- Thread count and per-thread stack memory.
- Tomcat accept queue/worker pool; Reactor Netty event loops.
- Network receive/send buffers.
- Long-lived keep-alive, SSE, and WebSocket connections.
- Multipart temporary disk, heap/direct/serialization buffers.

A JVM holding 10,000 idle connections uses many sockets/buffers even with low active HTTP request rate; do not equate requests/sec with open connections. For large streaming workloads, combine backpressure/slow-client policies, outbound queue limits, and temporary file controls.

Check FD limits in a Linux shell if present:

~~~bash
ulimit -n
~~~

Docker runtime FD limit example when host policy permits:

~~~bash
docker run --ulimit nofile=65535:65535 \
  -p 127.0.0.1:18080:8080 runtime-demo:1.0
~~~

`65535` is only an **example**; raising FD limits does not fix connection leaks or memory exhaustion. If a minimal container lacks a shell/`ulimit`, use host metrics or authorized debug containers.

### CPU Limits and HTTP Threading Models

| Stack | Common structure | Common mistake |
|---|---|---|
| Spring MVC/Tomcat | Blocking servlet worker threads | Raising max threads while DB pool/CPU remain bottlenecked |
| Spring WebFlux/Reactor Netty | Event-loop non-blocking I/O | Calling `block()`/`Thread.sleep()` on the event loop |
| Async executor | Worker pool + queue | Unbounded queue, shutdown without draining |
| SSE/WebSocket | Long-lived connections | Per-client buffers and reconnect storms |

Before tuning worker counts, measure CPU throttling, p95/p99 latency, JVM GC, DB pool waits, HTTP active/queued requests, and actual memory.

## 16. Writable /tmp, Ephemeral Storage, and Non-Root

The Kubernetes manifest uses:

~~~yaml
securityContext:
  readOnlyRootFilesystem: true

volumeMounts:
  - name: tmp
    mountPath: /tmp

volumes:
  - name: tmp
    emptyDir:
      sizeLimit: 128Mi
~~~

This is needed because Java/Servlet libraries can write temp files (multipart uploads, TLS/native scratch, `java.io.tmpdir`). With a read-only root filesystem and no writable temp mount, the app may fail with `Read-only file system` or failed uploads.

**Do not treat `emptyDir` as durable storage.** When the Pod is deleted, volume data is lost; use object storage/PVCs for durable files. With `emptyDir.medium: Memory`, `tmpfs` counts against the memory cgroup and can cause earlier OOMs; disk-backed `emptyDir` consumes ephemeral storage instead. For large uploads, enforce quotas, multipart limits, ephemeral storage monitoring, and cleanup.

Run as a non-root UID/GID:

~~~dockerfile
USER 10001:10001
~~~

and:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
~~~

Grant appropriate mount permissions rather than elevating the container to root just to write files. Pick an internal HTTP port like 8080/9090 instead of binding privileged ports 80/443 unnecessarily; the Ingress can expose 80/443 externally.

## 17. Health Probes: Readiness, Liveness, Startup

Spring Boot Actuator 3.5 provides Kubernetes probe support:
- `/actuator/health/liveness`.
- `/actuator/health/readiness`.
- With `management.endpoint.health.probes.add-additional-paths=true`, `/livez` and `/readyz` on the **main HTTP server port**.

In the demo:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

When `management.server.port` is separated, exposing `/livez`/`/readyz` on the main server checks the actual connector serving business traffic; a healthy management context does not guarantee the main connector is healthy.

| Probe | Purpose | On failure |
|---|---|---|
| Startup | Has startup progressed enough to begin liveness/readiness checks? | Waits, then restarts after failure budget |
| Readiness | Should new requests be routed to this Pod right now? | Marks Pod **NotReady**, removes from ready endpoints |
| Liveness | Is the process wedged and in need of restart? | Restarts container per thresholds |

**Do not tie database/Redis/partner outages to liveness failure** unless restarting the app genuinely fixes it; restarting every replica during a transient dependency outage triggers a cascading failure. Readiness may include checks reflecting ability to serve traffic, but must be designed to avoid flapping and excessive overhead.

Probes must target the **Pod/container port** (8080 or named `http`), not `Service.port` 80 when kubelet hits Pod IP. Test that the path actually exists; the Actuator starter must be included and probe groups enabled per environment.

### Separate Management Port

You can configure:

~~~yaml
management:
  server:
    port: 9090
    address: "127.0.0.1"
~~~

Per Spring Boot, `management.server.address` can only differ from the main listener when the management port is different. Binding to loopback inside a container means external scrapers/Pod-network probes to 9090 will **not reach it**. To scrape externally, design proper network/access controls rather than just opening a port in YAML. Protect metrics with auth/mTLS/NetworkPolicy/firewall; never publicly expose `/actuator/env`, `heapdump`, or all of Actuator.

## 18. Graceful Shutdown and Signal Handling

Spring Boot 3.5 enables HTTP graceful shutdown by default for supported embedded servers; explicitly configured in the demo:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

`timeout-per-shutdown-phase` is the wait time **per `SmartLifecycle` phase**, not a total JVM process deadline. In Kubernetes:

~~~yaml
terminationGracePeriodSeconds: 60
~~~

is the **total budget for Pod termination**, including `preStop` and Spring/other cleanup. If `preStop` takes 15s + multiple phases total 60s, the Pod can be force-killed before Java finishes. Measure shutdown timelines, request durations, and resource draining.

The Dockerfile uses exec form:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

so the JVM receives `SIGTERM` on container stop. Shell form `ENTRYPOINT java -jar /app/app.jar` can leave a shell as PID 1 that fails to forward signals, preventing Java's graceful shutdown hooks from running. If a wrapper script is needed, use `exec java -jar ...`.

SSE/WebSocket or streams outliving the grace period **do not automatically migrate to another Pod**. Use readiness false/draining, proactive close, client reconnect/backoff, and cursor/replay. For side-effecting POSTs, use idempotency keys/operation status because a dropped client response does not mean the server did not commit.

## 19. Logs and Metrics in Containers

Prefer logging to **stdout/stderr** for Docker/Kubernetes collection and rotation. Do not write unbounded log files into the container's writable overlay layer. Use centralized logging with retention and privacy controls for long-term logs.

Signals to monitor:

| Group | Metric/signal |
|---|---|
| Ports/HTTP | Startup port logs, ready endpoints, ingress 502/503, RPS and latency |
| JVM | `jvm.memory.used`, max heap, GC pauses, direct buffer metrics |
| Container | Memory working set/RSS/cgroup usage, CPU usage, CPU throttled time |
| Threads | Tomcat busy/current, executor active/queued, event loop lag |
| Connections | Active HTTP requests, TCP sockets, SSE/WebSocket sessions |
| Storage | Ephemeral bytes/inodes, temp file usage, volume quotas |
| Deploy | Readiness, liveness, `restartCount`, `lastState.terminated.reason` |
| Security | Bind addresses, NodePort/Ingress exposure, secrets, denied requests |

Do not put raw JWTs, cookies, usernames, personal IP addresses, or request IDs into high-cardinality Prometheus tags. `/api/runtime` in the demo returns minimal technical info; in production, protect or remove it if unneeded.

## 20. Random-Port Integration Test

Create `src/test/java/demo/runtime/ContainerRuntimeApplicationTests.java`:

~~~java
package demo.runtime;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ContainerRuntimeApplicationTests {

    @LocalServerPort
    int port;

    @Test
    void runtimeReportsRealPort() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/api/runtime"))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"listenPort\":" + port));
        assertTrue(response.body().contains(
            "\"message\":\"running\""));
    }

    @Test
    void helloReturnsExpectedBody() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/api/hello"))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"message\":\"hello\""));
    }
}
~~~

The tests use Java 17's `HttpClient` + JUnit 5 from the test starter. `@LocalServerPort` verifies the real port assigned when Boot tests pick an ephemeral port. Do not assert fixed CPU/heap values since they depend on the runtime. Run:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

This is instructional code for learners to run; **do not claim tests passed** if you have not executed them. Host mock/server tests do not substitute for testing Docker port mappings or Kubernetes Service networking during deployment.

## 21. Quick Diagnostic Steps When Unreachable

1. **Client URL:** are host/scheme/port right?
2. **Host publish:** are Docker `-p`, Compose ports, or Ingress/LB configured properly?
3. **Service:** do selector, port, and `targetPort` match the Pod listener?
4. **Ready endpoints:** is the Pod ready, and does EndpointSlices list addresses?
5. **Container listener:** what are Spring's actual `server.port` and `server.address`?
6. **Security/firewall:** are NetworkPolicy, security groups, ingress whitelists, or TLS blocking traffic?
7. **Application:** does the controller actually map the route? 404 differs from connection refused.
8. **Resources:** OOMKilled, CPU throttling, file descriptor limits, or startup probe flapping?
9. **Shutdown:** is the container terminating and refusing new traffic?
10. **Logs/metrics:** correlate timestamps across host, proxy, Pod, and JVM.

### Docker Commands

~~~bash
docker ps
docker port runtime-demo
docker logs --tail 100 runtime-demo
docker stats runtime-demo
docker inspect runtime-demo
~~~

`docker inspect` can reveal env vars/secrets; never share raw output publicly.

### Kubernetes Commands

~~~bash
kubectl get pods -l app=runtime-demo -o wide
kubectl describe deployment runtime-demo
kubectl describe service runtime-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=runtime-demo
kubectl logs deployment/runtime-demo --tail=100
kubectl top pod -l app=runtime-demo
kubectl rollout status deployment/runtime-demo
~~~

`kubectl top` requires metrics-server; `kubectl get endpointslices` requires matching RBAC read permissions. If a Pod restarts, get the **actual Pod name** from `kubectl get pods` and run `kubectl logs POD_NAME --previous`. Minimal runtime images may lack `curl`, `ss`, or `netstat`; debug via port-forward, host curl, proxy metrics, or authorized ephemeral debug containers.

### Distinguishing Failure Modes

| Symptom | Likely cause | What to verify |
|---|---|---|
| Connection refused from Docker host | Missing publish/wrong target/bound localhost | `docker port` + Spring bind |
| Timeout via Service | NetworkPolicy/LB/Service targetPort | Endpoints, probes, network path |
| HTTP 404 | Reached HTTP server, route did not match | Context path/controller mappings |
| HTTP 502 | Proxy cannot reach upstream | Gateway/proxy logs, Pod readiness |
| HTTP 503 | Pod draining/unavailable or server response | Ingress/source status |
| Pod `ImagePullBackOff` | Wrong image registry/tag/credentials | `kubectl describe pod` |
| Pod `CrashLoopBackOff` | App startup error/bind/OOM/probes | Previous logs and Events |
| Pod `OOMKilled` | Cgroup RAM limit exceeded | RSS/heap/native metrics |
| High CPU, rising latency | Saturation/throttling/blocking | CPU quota, GC, traces, queues |
| Process started but probe fails | Wrong probe path/port/management context | `/livez`/`/readyz` on main port |
| Upload fails on read-only FS | No writable temp dir | `/tmp` mount/permissions/quota |
| Non-graceful stop | Signal not reaching JVM PID 1 | Docker ENTRYPOINT, stop deadline |

**Do not reflexively increase `-Xmx` or `server.tomcat.threads.max`** when the root cause is a wrong port, probe, or Service route.

## 22. Network, Container, and Configuration Security

- Only publish necessary ports; Docker host `-p 127.0.0.1:18080:8080` is safer for local demos than `-p 18080:8080` when LAN access is unneeded.
- Use `USER 10001:10001`/`runAsNonRoot` and a read-only root filesystem if compatible; provide quota-bounded writable mounts.
- Separate management endpoints from public APIs or protect them with auth/authz, network policies, and TLS/mTLS; never set `management.endpoints.web.exposure.include="*"`.
- When TLS terminates at a proxy, only trust `Forwarded`/`X-Forwarded-*` from trusted proxies to prevent host/scheme spoofing.
- Never bake secrets into Docker image layers or commit them to `application.yml`. Use a Secrets manager or Kubernetes Secrets with proper RBAC/encryption/rotation.
- Never log `System.getenv()` or expose `/actuator/env`/heapdump to the Internet.
- Cap HTTP body size, concurrent requests, slow-client timeouts, and outbound queues to prevent memory/FD exhaustion.
- Never pin a fixed Pod IP into `server.address` because Pods get replaced.
- Test readiness/termination during rolling deploys so Pods do not stay unready unnecessarily due to overly tight startup probes.

### Recommended Configurations by Environment

| Environment | Spring bind | Client port | Security/resource focus |
|---|---|---|---|
| Local jar | 8080/9090 as needed | Same bound port | Never hardcode env secrets |
| Local Docker | 0.0.0.0:8080 | Host 127.0.0.1:18080 | Non-root, Docker memory/CPU |
| Compose | 0.0.0.0:8080 | Host ports or service DNS:8080 | Service network, environment |
| Kubernetes | 0.0.0.0:8080 | Service 80 → Pod 8080 | Requests/limits/probes/securityContext |
| Ingress HTTPS | 0.0.0.0:8080 | Public 443 → Service 80 | TLS/proxy trusted headers |
| PaaS with PORT | `${PORT:8080}` | Platform URL | Platform quota and JVM heap |

## 23. Self-Check Questions

**1.** With `server.port=8080` and `docker run -p 18080:8080`, which port does the host call?

**Answer:** Host **18080**; Spring inside the container stays **8080**.

**2.** If a Dockerfile has `EXPOSE 8080` without `-p`, can the host access port 8080 automatically?

**Answer:** No. `EXPOSE` is metadata and does not publish host ports.

**3.** Why can `server.address=127.0.0.1` prevent Docker/K8s Services from connecting?

**Answer:** The app binds only loopback in its network namespace; external routing typically targets the container/Pod IP, not the loopback socket.

**4.** Does `0.0.0.0` automatically expose the app to the public Internet?

**Answer:** No. It is a wildcard bind within the namespace; public exposure depends on Docker publishing, Ingress/LB, firewalls, and network policies.

**5.** Does `containerPort: 8080` automatically set Boot's `server.port`?

**Answer:** No. It is Pod documentation, not what starts the Java listener.

**6.** Does `Service port:80, targetPort:8080` mean the JVM must listen on port 80?

**Answer:** No. The JVM listens on 8080; the Service accepts 80 and routes to Pod port 8080.

**7.** Why can two Pods both listen on 8080, while two containers in the same Pod conflict?

**Answer:** Two Pods normally have separate network namespaces; containers in the same Pod share one namespace.

**8.** Does `PORT=9090` always change Spring Boot's port automatically?

**Answer:** No, unless mapped in config like `server.port: ${PORT:8080}` or via platform integration. Boot natively recognizes `SERVER_PORT`.

**9.** Is `server.port=0` suitable for a Kubernetes manifest with fixed `targetPort: 8080`?

**Answer:** No, unless special dynamic discovery/routing exists; the ephemeral port may differ from 8080.

**10.** Given a 768Mi container memory limit, is `-Xmx768m` guaranteed safe?

**Answer:** No. The JVM also uses native/direct memory, metaspace, thread stacks, and cgroup overhead outside the heap.

**11.** Does `MaxRAMPercentage=55` mean the process never exceeds 55% of RAM?

**Answer:** No. It is a percentage for sizing max Java heap; RSS/process native memory can still exceed it.

**12.** Does `ActiveProcessorCount=8` grant 8 CPUs to a container with a 1-core CPU limit?

**Answer:** No. JVM heuristics change while the kernel quota stays 1 core, which can trigger throttling.

**13.** Do exceeding the CPU limit and exceeding the memory limit produce the same outcome?

**Answer:** No. CPU overages cause throttling; memory pressure can trigger OOMKill.

**14.** Why shouldn't liveness depend completely on database status?

**Answer:** An external DB outage can cause all Pods to restart repeatedly, creating a cascading failure.

**15.** Why put `/readyz` on the main port when management runs on a separate port?

**Answer:** So the probe checks the actual HTTP connector serving business traffic.

**16.** Does `terminationGracePeriodSeconds=60` give each Spring lifecycle phase its own 60 seconds?

**Answer:** No. It is Kubernetes's total termination budget, covering `preStop` and app cleanup combined.

**17.** What does exec-form Docker `ENTRYPOINT` help with?

**Answer:** It allows Java to receive the stop signal directly and run shutdown hooks/graceful shutdown within budget.

**18.** If a non-root/read-only filesystem Java upload fails writing `/tmp`, how should you fix it?

**Answer:** Provide a writable temp volume/directory with proper permissions/quota; do not run as root.

**19.** If Spring's JVM heap metric is low yet the container is `OOMKilled`, what should you investigate?

**Answer:** Native/direct memory, thread stacks, RSS, cgroup temp/cache, concurrency, and JVM flags.

**20.** When a Service is unreachable, what should you check before raising Tomcat threads?

**Answer:** Port/address bind, Service selector/`targetPort`, Pod readiness, network policies, and proxy routes.

### Extended Exercises

1. Run the JAR on 8080 then 9090, checking `/api/runtime` reporting actual `listenPort`.
2. Build the Docker image, publish `18080:8080`, and verify host port differs from container port.
3. Change `PORT=9090` while intentionally keeping Docker mapped to 8080, observe the error, and fix it.
4. Bind `127.0.0.1` inside the container and try host publishing; explain network namespaces.
5. Use `--memory=768m`/`--cpus=1` and `MaxRAMPercentage=55`, comparing JVM `maxHeap` with `docker stats` under light load.
6. With Compose, call `http://runtime:8080` from another container instead of `localhost:18080`.
7. Deploy the test image to Kubernetes; use `kubectl port-forward service/runtime-demo 18080:80` and verify `/readyz`.
8. Intentionally misconfigure `targetPort` in a test cluster and diagnose EndpointSlices and logs.
9. Experiment with CPU throttling in a test environment and observe latency, queues, and GC; never stress-test production.
10. Enable `readOnlyRootFilesystem` with writable `/tmp`, observing temp files and quotas.
11. During a rolling deployment, measure readiness transitions, SIGTERM, HTTP graceful drain, and Pod termination budget.
12. Write a random-port test using `@LocalServerPort` without hardcoding 8080.

## 24. Official Documentation

- [Spring Boot 3.5 — Embedded Web Servers / Change HTTP Port](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Docker Docs — Running Containers and Publishing Ports](https://docs.docker.com/engine/containers/run/)
- [Docker Docs — Dockerfile Reference: EXPOSE/ENTRYPOINT](https://docs.docker.com/reference/dockerfile/)
- [Docker Docs — Compose Services](https://docs.docker.com/compose/compose-file/05-services/)
- [Kubernetes — Service port and targetPort](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes — Resource Management for Pods/Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes — Startup, Liveness, Readiness Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [Oracle Java 17 — java launcher and Container Support](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)

**Conclusion:** Spring Boot determines **the port and listener interface inside the JVM**; Docker/Kubernetes determine **the route from outside to that listener**. `EXPOSE` and `containerPort` do not start listeners, whereas `-p` and `Service.targetPort` must point accurately. CPU/memory limits encompass more than JVM heap, readiness must inspect the right main port, and containers need non-root permissions, writable temp paths, logs/metrics, and graceful signal handling. When troubleshooting deployment issues, trace **bind → network namespace → publish/Service → readiness → resources → handler**, instead of changing every setting at once.