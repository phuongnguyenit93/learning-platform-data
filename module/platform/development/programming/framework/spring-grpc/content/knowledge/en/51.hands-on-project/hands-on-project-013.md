# Containerizing a Spring gRPC Service and Graceful Shutdown

A gRPC service that runs reliably on a developer machine can still drop requests once packaged and deployed. Containers receive termination signals from Docker or Kubernetes; if the Java process never receives that signal, or if the server drops connections immediately, in-flight RPCs can fail midway.

In this project, you will package a Spring gRPC service into a multi-stage Docker image, run it as a non-root user, configure the gRPC Health service, and implement graceful shutdown. You will directly test an in-flight RPC while the container receives `SIGTERM`, and then deploy the same service to Kubernetes with appropriate probes and Pod termination budgets.

## Project Goals

Upon completion, the service must satisfy the following conditions:

- Can be built as an executable JAR and Docker image usable across target environments.
- The runtime image contains only the JRE and required artifacts; the process runs as a non-root user.
- Java is the process receiving `SIGTERM` directly from the container runtime.
- The gRPC server stops accepting new RPCs, gives in-flight RPCs time to finish, and forces shutdown when the grace period expires.
- The Health service provides separate statuses for startup/readiness and liveness.
- Docker Compose and Kubernetes wait longer than the gRPC graceful shutdown duration.

## Prerequisites

- A Spring Boot/Spring gRPC application already running locally with a Gradle Wrapper.
- Java 21, Docker Engine, and the Docker Compose plugin.
- `grpcurl` for invoking test RPCs from the host machine.
- `kubectl` and a Kubernetes cluster supporting native gRPC probes (Kubernetes 1.27 or newer).

## 1. Context and Architecture

Assume you have a Spring Boot application using Spring gRPC, listening on port 9090, with at least one service extending a generated `ImplBase`. The examples below use Java 21, Gradle Wrapper, Spring Boot 4.1.x, and Spring gRPC 1.1.x. If your project uses different versions, verify property names and lifecycle APIs in the documentation for your exact versions before applying.

Deployment flow:

~~~mermaid
flowchart LR
    C[gRPC Client] --> S[Kubernetes Service]
    S --> P[Pod: Spring gRPC]
    P --> G[Native gRPC server]
    T[Docker / kubelet sends SIGTERM] --> J[Java process]
    J --> L[Spring gRPC lifecycle]
    L --> D[Stop accepting new RPCs]
    D --> I[Drain in-flight RPCs]
    I --> X[Process exits]
~~~

When the container stops, Java receives `SIGTERM`. Spring gRPC manages the server lifecycle and triggers the gRPC shutdown sequence. The server rejects new RPCs while in-flight RPCs continue within the configured time limit; if the timeout expires, the server falls back to forceful shutdown. The container runtime waits for its own grace window before sending `SIGKILL`.

## 2. Preparing the Application and gRPC Health Service

### 2.1. Checking Dependencies

Spring gRPC can automatically register the gRPC Health service when the application includes the `grpc-services` dependency. This dependency also provides `HealthStatusManager` for updating serving statuses.

With Gradle, add the following dependency if not already present:

~~~groovy
dependencies {
    implementation("io.grpc:grpc-services")
}
~~~

Let Spring Boot/Spring gRPC dependency management control the `grpc-java` version; never manually select a `grpc-services` version different from the rest of the `grpc-java` libraries.

### 2.2. Declaring an RPC to Test Shutdown

You can use an existing service. If you need an RPC to simulate an in-flight task, add a `Wait` method to your proto file:

~~~proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "com.example.catalog.grpc";

service CatalogService {
  rpc Wait(WaitRequest) returns (WaitReply);
}

message WaitRequest {
  int32 delay_ms = 1;
}

message WaitReply {
  bool completed = 1;
}
~~~

Implement this method in a Spring-managed service. The following example only simulates an in-flight synchronous RPC; never use `Thread.sleep` for real workload processing:

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

@Override
public void wait(WaitRequest request, StreamObserver<WaitReply> responseObserver) {
    long remaining = Math.min(Math.max(request.getDelayMs(), 0), 60_000);
    Context rpcContext = Context.current();

    try {
        while (remaining > 0 && !rpcContext.isCancelled()) {
            long slice = Math.min(remaining, 100);
            Thread.sleep(slice);
            remaining -= slice;
        }
        if (rpcContext.isCancelled()) {
            return;
        }
        responseObserver.onNext(
                WaitReply.newBuilder().setCompleted(true).build());
        responseObserver.onCompleted();
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        responseObserver.onError(
                Status.CANCELLED
                        .withDescription("RPC interrupted")
                        .withCause(exception)
                        .asRuntimeException());
    }
}
~~~

Set the client deadline longer than the simulated duration. In a real service, every RPC needs an appropriate deadline, cancellation handling, and timeouts for calls to downstream dependencies.

### 2.3. Separating Liveness from Readiness

Liveness answers "is the process still alive and capable of serving?" Readiness answers "is the service ready to accept work?" Never tie liveness to database or external service status, because a downstream outage could cause Kubernetes to repeatedly restart an otherwise healthy process.

Spring gRPC provides `HealthStatusManager` when the gRPC Health service is configured. Create two distinct health service names for Kubernetes to probe:

~~~java
import static io.grpc.health.v1.HealthCheckResponse.ServingStatus.NOT_SERVING;
import static io.grpc.health.v1.HealthCheckResponse.ServingStatus.SERVING;

import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.grpc.server.lifecycle.GrpcServerShutdownEvent;
import org.springframework.stereotype.Component;

@Component
public class GrpcProbeHealth {

    private final HealthStatusManager health;

    public GrpcProbeHealth(HealthStatusManager health) {
        this.health = health;
        health.setStatus("liveness", SERVING);
        health.setStatus("readiness", NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void markReady() {
        health.setStatus("readiness", SERVING);
    }

    @EventListener(GrpcServerShutdownEvent.class)
    public void markStopping() {
        health.setStatus("readiness", NOT_SERVING);
    }
}
~~~

`ApplicationReadyEvent` marks the service ready once Spring finishes starting up. In a real application, mark readiness as `SERVING` only after mandatory dependencies are ready; if they can lose connectivity at runtime, update readiness accordingly. Liveness continues to reflect process health and should not depend on the database.

`GrpcServerShutdownEvent` is published by Spring gRPC before the server starts shutting down. Marking readiness as not serving signals the intent to stop receiving traffic; the server lifecycle still handles shutdown and draining in-flight RPCs.

## 3. Configuring Graceful Shutdown in Spring

In `application.yml`, configure the bind address, port, and grace period:

~~~yaml
spring:
  application:
    name: catalog-grpc
  grpc:
    server:
      address: 0.0.0.0
      port: 9090
      health:
        enabled: true
      servlet:
        enabled: false
      shutdown:
        grace-period: 25s
  lifecycle:
    timeout-per-shutdown-phase: 35s
~~~

The values in the example relate to each other as follows:

| Configuration | Value | Role |
| --- | ---: | --- |
| spring.grpc.server.shutdown.grace-period | 25 seconds | Time Spring gRPC waits for in-flight RPCs to complete |
| spring.lifecycle.timeout-per-shutdown-phase | 35 seconds | Time Spring waits for a lifecycle phase to finish stopping |
| Docker stop_grace_period or Kubernetes terminationGracePeriodSeconds | 45 seconds | External budget before the container is forcefully killed |

The Spring lifecycle timeout must be large enough for gRPC to finish its grace period. The Docker/Kubernetes timeout must exceed the application's shutdown duration, leaving headroom for closing connection pools, telemetry exporters, and other beans.

This lab selects the native gRPC server so the service listens directly on port 9090. If the application uses the servlet transport, gRPC runs through the embedded HTTP server and requires configuring ports, HTTP/2, and shutdown under the servlet model instead.

The property `spring.grpc.server.shutdown.grace-period` applies to Spring Boot 4.1.x and Spring gRPC 1.1.x. Spring gRPC 1.0.x used the older name `spring.grpc.server.shutdown-grace-period`; verify the application properties for your exact dependency version.

If the application also runs an embedded HTTP server for Actuator, HTTP graceful shutdown is a separate lifecycle. The gRPC configuration above does not replace HTTP server shutdown settings.

## 4. Packaging the Docker Image

### 4.1. Creating a Multi-Stage Dockerfile

Create `Dockerfile` in the application root directory:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY . .

RUN chmod +x ./gradlew \
    && ./gradlew --no-daemon clean bootJar \
    && mkdir -p /out \
    && APP_JAR="$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' | head -n 1)" \
    && test -n "$APP_JAR" \
    && cp "$APP_JAR" /out/app.jar

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build --chown=10001:10001 /out/app.jar /app/app.jar

USER 10001:10001
EXPOSE 9090
STOPSIGNAL SIGTERM

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-jar", "/app/app.jar"]
~~~

The build stage includes the JDK and Gradle Wrapper to produce the executable JAR. The runtime stage receives only the JAR and JRE, keeping the image small and omitting compilers and source code. Adjust the `build/libs` path if this is a multi-module Gradle build and the executable JAR resides in a sub-module.

`USER 10001:10001` runs Java under a non-root UID/GID. The exec-form `ENTRYPOINT` makes Java the main container process so it receives `SIGTERM` directly. Avoid wrapping the Java command in `sh -c` unless you explicitly forward signals.

`MaxRAMPercentage` tells the JVM to size the heap relative to container memory limits; `65%` is a starting point for the lab, not an optimal setting for every service. Measure heap, direct memory, thread stacks, and real memory footprint before finalizing production values.

In production, pin JDK/JRE base images to vetted patch versions or digests, scan images for vulnerabilities, and update them regularly.

### 4.2. Creating .dockerignore

~~~text
.git
.gradle
**/build
**/target
.idea
.run
*.iml
*.log
.env
.env.*
~~~

Do not exclude `gradlew`, `gradle/wrapper`, or sources required for the build. `.dockerignore` shrinks the build context and prevents environment files that may contain secrets from entering the image.

### 4.3. Building and Running the Image

~~~bash
docker build -t catalog-grpc:local .
docker run --rm --name catalog-grpc -p 9090:9090 catalog-grpc:local
~~~

Verify the RPC from the host machine using `grpcurl` and the proto file:

~~~bash
grpcurl -plaintext -proto src/main/proto/catalog.proto \
  -d '{"delayMs":100}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

The expected output is a response with `completed: true`. If the application uses TLS, replace `-plaintext` with the appropriate TLS flags and configure certificates/authorities accurately.

## 5. Running with Docker Compose

Create `compose.yaml`:

~~~yaml
services:
  catalog-grpc:
    build:
      context: .
      dockerfile: Dockerfile
    image: catalog-grpc:local
    ports:
      - "9090:9090"
    stop_grace_period: 45s
    restart: unless-stopped
~~~

`stop_grace_period` instructs Docker to wait up to 45 seconds after sending the stop signal before forcefully killing the container. This exceeds the gRPC server's 25-second grace period.

Start the application:

~~~bash
docker compose up --build -d
docker compose logs -f catalog-grpc
~~~

Test the RPC using `grpcurl`:

~~~bash
grpcurl -plaintext -proto src/main/proto/catalog.proto \
  -d '{"delayMs":100}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

## 6. Verifying Graceful Shutdown in Docker

This is the most critical part of the project. You must prove that an in-flight RPC can finish when the container receives `SIGTERM`.

1. Start the service with Docker Compose and confirm the `Wait` RPC works.
2. Open a first terminal and invoke an RPC taking 15 seconds:

   ~~~bash
   grpcurl -plaintext -max-time 30s \
     -proto src/main/proto/catalog.proto \
     -d '{"delayMs":15000}' \
     localhost:9090 catalog.v1.CatalogService/Wait
   ~~~

3. While the RPC is running, open a second terminal and stop the container:

   ~~~bash
   docker compose stop
   ~~~

4. Observe the client output and application logs.

Expected results:

- The RPC started before shutdown and completes within the 25-second grace period.
- The server stops accepting new RPCs once graceful shutdown begins.
- The container exits before `stop_grace_period` expires.
- Logs show the Spring context and gRPC server stopping cleanly.

Restart the service to test a timeout scenario:

~~~bash
docker compose up -d
~~~

Invoke a 40-second RPC and then stop the container. With a 25-second grace period, the RPC cannot be guaranteed to finish; the server forces shutdown once the timer expires. This tests the boundary of graceful shutdown rather than a successful completion.

In one terminal, start the RPC; in a second terminal, run `docker compose stop` before it finishes. Test command:

~~~bash
grpcurl -plaintext -max-time 50s \
  -proto src/main/proto/catalog.proto \
  -d '{"delayMs":40000}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

In the `Wait` example, the handler periodically checks cancellation status to halt simulated work when gRPC cancels the RPC. In real workloads, propagate cancellation to HTTP/database clients or background tasks; closing the transport alone does not automatically roll back side effects already executed.

If the 15-second RPC aborts immediately upon container stop, verify whether Java is PID 1, whether Docker sends `SIGTERM`, whether the grace period property is bound, and whether the runtime stop timeout is longer than the application's wait time.

## 7. Deploying to Kubernetes

### 7.1. Using gRPC Health Probes

Kubernetes supports native gRPC startup, readiness, and liveness probes. This requires the application to implement the gRPC Health Checking Protocol. `grpc-services` together with Spring gRPC's Health service provides the endpoint the probes call.

In the manifest below:

- The startup probe checks the `readiness` service during startup.
- The readiness probe allows the Pod to receive traffic only when the service is ready.
- The liveness probe uses the `liveness` service, independent of database or downstream system status.

### 7.2. Creating the Deployment and Service

Create `k8s/catalog-grpc.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-grpc
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: catalog-grpc
  template:
    metadata:
      labels:
        app: catalog-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: catalog-grpc
          image: catalog-grpc:local
          imagePullPolicy: IfNotPresent
          ports:
            - name: grpc
              containerPort: 9090
              protocol: TCP
          startupProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-grpc
spec:
  type: ClusterIP
  selector:
    app: catalog-grpc
  ports:
    - name: grpc
      port: 9090
      targetPort: grpc
      protocol: TCP
      appProtocol: kubernetes.io/h2c
~~~

Kubernetes gRPC probes take a numeric port, not a port name. The manifest above uses plaintext HTTP/2 (`h2c`) between Pods. If the gRPC server terminates TLS directly, check TLS probe support in your Kubernetes version/feature gates or use a probe compatible with your TLS setup. Never enable TLS probes assuming every cluster supports them.

`terminationGracePeriodSeconds: 45` sets the total budget for Pod termination. If you add a `preStop` hook, its execution time counts against these 45 seconds; never use a long sleeping hook that leaves insufficient time for gRPC draining.

### 7.3. Building and Deploying

Build the image:

~~~bash
docker build -t catalog-grpc:local .
~~~

If using a local cluster such as `kind`, load the image into the cluster using the cluster's tool, e.g.:

~~~bash
kind load docker-image catalog-grpc:local
~~~

Apply the manifest and monitor the rollout:

~~~bash
kubectl apply -f k8s/catalog-grpc.yaml
kubectl rollout status deployment/catalog-grpc
kubectl get pods -l app=catalog-grpc
kubectl get endpointslice -l kubernetes.io/service-name=catalog-grpc
~~~

You can test from the host machine via port-forwarding:

~~~bash
kubectl port-forward service/catalog-grpc 9090:9090
~~~

Then re-run the `grpcurl` command from the Docker section.

### 7.4. Testing Pod Termination

1. Ensure the Deployment has at least two replicas and both Pods are Ready.
2. Pick one Pod and follow its logs before deleting it:

   ~~~bash
   kubectl logs <pod-name> --follow
   ~~~

3. In a second terminal, open a direct port-forward to the chosen Pod:

   ~~~bash
   kubectl port-forward pod/<pod-name> 9091:9090
   ~~~

4. In a third terminal, start a `Wait` RPC targeting `localhost:9091`. While the RPC is running, delete the chosen Pod from a fourth terminal:

   ~~~bash
   grpcurl -plaintext -max-time 30s \
     -proto src/main/proto/catalog.proto \
     -d '{"delayMs":15000}' \
     localhost:9091 catalog.v1.CatalogService/Wait
   ~~~

   ~~~bash
   kubectl delete pod <pod-name>
   ~~~

5. Watch Pod status and EndpointSlice changes:

   ~~~bash
   kubectl get pods -l app=catalog-grpc -w
   kubectl get endpointslice -l kubernetes.io/service-name=catalog-grpc
   ~~~

The terminating Pod is removed from endpoints serving new traffic; kubelet runs `preStop` if configured, then sends the stop signal to the main process. Spring gRPC initiates server shutdown and waits for in-flight RPCs up to the grace period. If this exceeds the Pod's budget, kubelet forcefully kills the container.

## 8. Calculating the Shutdown Budget

Do not choose independent timeouts arbitrarily. They must form an ordered budget:

~~~text
gRPC shutdown grace period
        < Spring lifecycle phase timeout
        < container / Pod termination grace period
~~~

For this project's example:

| Layer | Duration |
| --- | ---: |
| gRPC server drain | 25 seconds |
| Spring lifecycle phase | 35 seconds |
| Docker stop / Kubernetes Pod termination | 45 seconds |

The gaps provide time for signal delivery, shutting down other beans, and process exit. If there is a `preStop` hook or sidecar that must stop sequentially, add its time to the total budget.

Graceful shutdown does not replace RPC deadlines. Clients still need finite deadlines and logic to handle `UNAVAILABLE` when connections drop. For RPCs with side effects, design idempotency or reconciliation mechanisms so clients can determine outcomes if a response is lost after the server completed processing.

## 9. Common Issues and Diagnostics

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Container stops almost immediately | Java did not receive `SIGTERM` or grace period is 0 | Check `ENTRYPOINT`, PID 1, stop signal, and Spring gRPC properties |
| In-flight RPC is cut off | Server forced shutdown before RPC finished | Compare RPC duration against gRPC grace period and container timeout |
| Docker waits and then sends `SIGKILL` | Application failed to exit within `stop_grace_period` | Inspect shutdown logs and adjust timeouts after identifying the blocking bean |
| Pod restarts repeatedly on DB outage | Liveness depends on the database | Separate liveness from readiness |
| Pod never becomes Ready | Health service not registered or readiness never set to `SERVING` | Check `grpc-services`, `HealthStatusManager`, and probe service name |
| Probe fails when TLS is enabled | Native probe connecting plaintext or cluster lacks TLS probe support | Verify feature gates and use a TLS-compatible probe |
| Image runs locally but fails in cluster | Image not loaded/pushed or wrong bind address/port | Check image, `0.0.0.0`, `containerPort`, and Service `targetPort` |

## 10. Acceptance Criteria

The project is complete when you can demonstrate:

- [ ] Docker image is built from a multi-stage Dockerfile.
- [ ] Runtime image runs Java under a non-root UID.
- [ ] Container listens for gRPC on `0.0.0.0:9090`.
- [ ] gRPC Health service returns `SERVING` for `liveness` after startup.
- [ ] `readiness` transitions to `SERVING` only once the application is ready.
- [ ] An in-flight RPC finishes when the container receives `SIGTERM` within the grace period.
- [ ] New RPCs are rejected once the server begins graceful shutdown.
- [ ] Docker Compose waits longer than the gRPC grace period.
- [ ] Kubernetes startup/readiness/liveness probes work.
- [ ] Pod `terminationGracePeriodSeconds` exceeds the application shutdown duration.
- [ ] Logs or observable evidence exist for both graceful completion and timeout/forced shutdown.

## References

- [Spring gRPC — gRPC Server](https://docs.spring.io/spring-grpc/reference/server.html): service registration, Health service, and `HealthStatusManager`.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.grpc.server.shutdown.grace-period` property.
- [Spring gRPC — Lifecycle API](https://docs.spring.io/spring-grpc/reference/api/java/org/springframework/grpc/server/lifecycle/package-summary.html): server lifecycle and shutdown events.
- [gRPC — Graceful Shutdown](https://grpc.io/docs/guides/server-graceful-stop/): stopping new RPCs and draining in-flight RPCs.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): configuring native gRPC probes.
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): `preStop` timing and calculating termination grace periods.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): Pod termination flow and signaling the main process.
