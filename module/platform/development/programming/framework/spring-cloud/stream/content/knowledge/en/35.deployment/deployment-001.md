# Packaging Spring Boot Applications and Container Images

A Spring Cloud Stream application typically runs continuously to receive, transform, and emit events via Kafka, RabbitMQ, or a binder corresponding to the message broker system. After writing `Supplier`, `Function`, and `Consumer` beans, the deployment step is to package the application into a reproducible runnable artifact and place that artifact into a container image. The image should carry the same source code and dependencies across all environments; broker addresses, groups, credentials, and resource limits are provided at runtime.

This lesson builds the workflow from a Spring Boot executable JAR to an OCI image, compares Cloud Native Buildpacks with a Dockerfile, configures the binder inside a container, and prepares the minimal elements for deploying on Docker or Kubernetes. The examples use Java 21, Gradle, and the Kafka binder; the same principles apply to RabbitMQ, Kafka Streams, and the Pulsar binders suited to your project.

## 1. Overview of the Deployment Workflow

~~~mermaid
flowchart LR
    A[Java code and config] --> B[Gradle bootJar]
    B --> C[Executable JAR]
    C --> D{Image build approach}
    D --> E[Cloud Native Buildpacks]
    D --> F[Dockerfile]
    E --> G[OCI container image]
    F --> G
    G --> H[Container registry]
    H --> I[Docker or Kubernetes]
    I --> J[Kafka / RabbitMQ / Pulsar]
~~~

There are three layers to distinguish:

| Component | What does it contain? | When does it change? |
|---|---|---|
| Executable JAR | Application bytecode, Spring Boot and Spring Cloud Stream libraries, default configuration | When building source code |
| Container image | JAR or extracted layers, Java runtime, metadata, entrypoint | When building/publishing the image |
| Running container | Image plus environment variables, secrets, volumes, network, CPU/memory limits | When deploying or restarting |

Do not create a separate image just to change a dev Kafka address into a staging Kafka address. A better approach is to release an immutable image, then pass different configurations for each environment. Do not put passwords or tokens directly into the JAR, Dockerfile, or image layers.

## 2. Preparing the Spring Cloud Stream Application

A function-based message-consuming application can have a bean like this:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status) {}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder() {
        return event -> System.out.printf(
                "orderId=%s status=%s%n",
                event.orderId(),
                event.status());
    }
}
~~~

This example illustrates the logic; in a real application, processing requires idempotency, error configuration, and structured logging. Once packaged, the function bean is still discovered just as when running in an IDE. The binder creates a default input binding named `processOrder-in-0`.

Required dependencies in a Kafka binder application may look like this:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-stream")
    implementation("org.springframework.cloud:spring-cloud-stream-binder-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Only needed when exposing HTTP health/metrics.
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Assume the project has already configured the Spring Boot Gradle plugin and imported a compatible Spring Cloud BOM. Do not arbitrarily mix Spring Boot, Spring Cloud, and binder versions from different release trains: you must select versions supported together. If you only use RabbitMQ, replace the Kafka binder with the corresponding Rabbit binder dependency; if you use the Kafka Streams DSL, use the Kafka Streams binder and configure its own application ID/state store.

## 3. Configuring Bindings via application.yml

Minimal configuration example:

~~~yaml
spring:
  application:
    name: order-event-consumer
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
~~~

`destination` is the topic receiving messages; `group` is a stable consumer group so Kafka persists reading progress. With a group that already has offsets, the application usually resumes from the committed offset upon restart. If a random group is used each time a container is created, recovery behavior and consumer scaling capabilities will change.

`KAFKA_BROKERS` is an environment variable supplied at runtime; `localhost:9092` is only a fallback value for local development on the host machine. Inside a container, `localhost` points to the container itself, not the Kafka broker running on the host machine or another container. Docker Compose and Kubernetes should use the DNS/broker address that the container can actually reach.

Environment-specific details such as SASL/TLS, schema registry, and credentials must also be provided via config/secrets at runtime. Only put harmless default configuration in the packaged `application.yml`.

## 4. Building an Executable Spring Boot JAR

The Spring Boot Gradle plugin provides the `bootJar` task. The produced artifact is an executable JAR containing dependencies and the Spring Boot launcher; the application can be run with `java -jar`.

In `build.gradle.kts`, you can set a stable JAR name:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
}
~~~

Build the JAR using the wrapper:

~~~bash
./gradlew clean bootJar
~~~

On Windows PowerShell, use `.\gradlew.bat clean bootJar`. After building, the artifact is located at `build/libs/app.jar`.

Test running it directly:

~~~bash
KAFKA_BROKERS=localhost:9092 java -jar build/libs/app.jar
~~~

Inline variable assignment on the same line is POSIX-style shell syntax; in PowerShell, use `$env:KAFKA_BROKERS = "localhost:9092"` before running `java -jar build/libs/app.jar`.

Verify that the JAR starts successfully, the function is registered, the input binding connects to the topic, and the health endpoint returns the expected status. If the application also has the `jar` task generating a `*-plain.jar` file, do not use an ambiguous wildcard `build/libs/*.jar` in the Dockerfile: the wildcard could match the non-executable JAR as well. Set an explicit name `app.jar` to avoid copying the wrong file.

If using Maven, the equivalent command is typically `./mvnw -DskipTests package`, and the Spring Boot Maven plugin packages the executable JAR. Skipping tests in the example is only for iterative local builds when tests already run in CI; a real release pipeline must still execute mandatory tests before publishing an image.

## 5. Approach 1: Building an OCI Image with Cloud Native Buildpacks

The Spring Boot Gradle plugin supports the `bootBuildImage` task based on Cloud Native Buildpacks. This task combines the JAR with a builder and a Java runtime chosen by the buildpack to produce an OCI-compliant image. There is no need to write a Dockerfile manually.

Example:

~~~bash
./gradlew bootBuildImage --imageName=registry.example.com/events/order-consumer:1.0.0
~~~

Prerequisites: the build machine or CI runner has a Docker daemon/OCI image service compatible with the task and can pull the builder/run images. The task creates a local image with the chosen name and tag.

You can configure it in Gradle:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("registry.example.com/events/order-consumer:1.0.0")
}
~~~

In a pipeline, derive the tag from the build version or commit ID rather than hard-coding it. When publishing the image, configure registry access permissions in the build system; do not put registry passwords in source control. The Spring Boot plugin supports publishing images via the task, or you can use `docker push` after building.

Advantages of Buildpacks:

- Automatically selects appropriate buildpacks for Java and Spring Boot.
- Provides caching mechanisms to reuse layers and reduce build times.
- Allows configuring the runtime and build options via the builder/buildpack.
- Reduces the need to maintain Dockerfiles and JAR extraction logic manually.

You still need to manage builder/run image versions, scan for CVEs, generate SBOMs, and rebuild when platform patches are released. Buildpacks do not replace logic testing or broker connectivity testing.

## 6. Approach 2: Simple Dockerfile from a Built JAR

When you need control over the runtime image and entrypoint, you can use the following Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy

WORKDIR /opt/app
RUN chown 10001:10001 /opt/app

COPY --chown=10001:10001 build/libs/app.jar /opt/app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Building the JAR is done beforehand with Gradle; the Dockerfile only packages the artifact. Choose a Java runtime image matching the compiled bytecode version. For example, use a Java 21 JRE for an application compiled with Java 21. Pin tags and verify digests according to organizational policy when releasing.

Command to build the image:

~~~bash
./gradlew clean bootJar
docker build --tag order-consumer:1.0.0 .
~~~

Key decisions:

- `WORKDIR` creates a consistent working directory.
- `COPY` places the exact executable JAR into the runtime image.
- `USER 10001:10001` runs with a non-root UID/GID, reducing process privileges.
- `ENTRYPOINT` in exec form allows the Java process to receive termination signals like SIGTERM directly, without an intermediate shell swallowing the signal.
- `EXPOSE 8080` is metadata about the intended port; it does not automatically publish the port to the host.

The container image needs a writable location for temporary files. If the Kafka Streams binder needs to store a RocksDB state store, a writable state path must be provided; you should not assume the entire container filesystem is writable. Since the container runs under UID 10001, all volume mounts must have appropriate permissions.

A `.dockerignore` file should exclude unrelated directories to reduce the build context:

~~~text
.git
.gradle
.idea
**/*.log
**/test-results
~~~

Do not exclude `build/libs/app.jar` if the Dockerfile is copying that artifact. Other `.dockerignore` rules may apply depending on the project, but verify that the JAR remains inside the Docker build context.

## 7. Multi-Layer Dockerfile to Optimize Image Updates

A Spring Boot executable JAR typically has multiple content groups: stable dependencies, snapshot dependencies, the launcher, and application code. If you copy the entire JAR into a single Docker layer, a small code change invalidates the layer containing the whole JAR. Extracting a layered JAR allows reusing less frequently changing layers.

With Spring Boot versions supporting `jarmode=tools`, you can use a two-stage Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy AS extract
WORKDIR /workspace
COPY build/libs/app.jar app.jar
RUN java -Djarmode=tools -jar app.jar extract --layers --destination extracted

FROM eclipse-temurin:21-jre-jammy
WORKDIR /opt/app
RUN chown 10001:10001 /opt/app

COPY --from=extract --chown=10001:10001 /workspace/extracted/dependencies/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/spring-boot-loader/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/application/ ./

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

In the current `extract --layers` layout, `application.jar` in the final stage is the launcher referencing the extracted layers; this is not the original JAR copied into the extract stage. This mechanism requires an executable JAR with a layer index and support for tools jar mode. Older Spring Boot versions may use `jarmode=layertools` with a different extraction syntax; do not mix the two approaches without checking the version.

If the application uses an embedded launch script to create a fully executable archive, check the limitations of tools jar mode. For Docker, the exec form entrypoint is generally better suited than an embedded launch script.

Order `COPY` instructions from least frequently changing layers to most frequently changing layers. Docker/OCI registries can reuse dependency layers when only business code changes. Actual benefits depend on how the build generates content and builder caching.

## 8. Buildpack or Dockerfile?

| Criterion | Buildpacks (`bootBuildImage`) | Dockerfile |
|---|---|---|
| Image configuration authoring | Minimal, mainly via Gradle/plugin | Explicitly write each instruction |
| Java runtime | Determined by builder/buildpack | Choose a specific base image |
| Layer caching | Supported by buildpack lifecycle | Depends on Docker layer design |
| Runtime user | Configured by buildpack run image | Must explicitly set `USER` |
| OS package customization | Depends on builder/buildpack | More flexible |
| Base image updates | Must manage builder/run images | Must manage `FROM` |
| Best suited for | Standard Boot applications | Images with custom OS or runtime constraints |

For a standard Spring Cloud Stream application, starting with `bootBuildImage` can reduce maintenance effort. If you need to customize the certificate store, platform tools, or specialized runtime utilities, a Dockerfile may be more suitable. Both approaches require image scanning and testing before release.

## 9. Running the Container and Passing Broker Configuration

With the built image, you can run:

~~~bash
docker run --rm \
  --name order-consumer \
  --publish 8080:8080 \
  --env KAFKA_BROKERS=kafka.internal:9092 \
  order-consumer:1.0.0
~~~

This command assumes `kafka.internal:9092` is resolvable and reachable from inside the container. If Kafka runs in the same Docker Compose setup, typically use the service name on the Compose network, such as `kafka:9092`.

If Kafka runs on a development machine, `host.docker.internal` may be supported depending on the Docker platform; this is a local environment convenience, not a production address. Kafka must also advertise `advertised.listeners` that clients inside containers can reach: connecting to the bootstrap server is not enough if the returned metadata contains an unresolvable internal hostname.

For the RabbitMQ binder, the address can be passed via `spring.rabbitmq.host`, `spring.rabbitmq.port`, or binder-specific environment properties when configuring multiple binders. For Pulsar, configure the service URL and certificates according to the binder/client in use. Do not reuse Kafka environment variable names for RabbitMQ or Pulsar; each integration has its own connection configuration.

## 10. Do Not Embed Secrets in the Image

Do not put SASL passwords, RabbitMQ passwords, TLS private keys, or schema registry tokens in a Dockerfile, an `application.yml` committed to Git, or build arguments.

Instead, inject secrets when the container runs:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_SASL_JAAS}
~~~

The `KAFKA_SASL_JAAS` variable should be supplied from a secret manager or Kubernetes Secret and made available only to authorized workloads. Ensure the variable actually exists; a configuration missing a secret must fail deployment in an observable way, rather than falling back to insecure default credentials.

Environment variables can be exposed through process configuration read permissions or runtime management tools. For stricter requirements, mount secrets as files with restricted read permissions or use a CSI Secret Store and specify the appropriate path for the Kafka client. Do not print secret values on application startup or expose them via Actuator `env`, `configprops`, or `bindings`.

Registry credentials used for `docker push` are also pipeline secrets; do not place them inside the image. Use the runner's identity or an appropriate credential store.

## 11. CPU, Memory, and JVM in Containers

Do not set a fixed heap larger than the container's memory limit. Modern JVMs detect cgroup limits; you can adjust the heap ratio within the memory limit:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
~~~

This is an example configuration, not an optimal ratio for every application. The remaining memory must be sufficient for metaspace, direct buffers, thread stacks, Kafka client buffers, and native memory. Kafka Streams may use RocksDB, page cache, and state restore; these components must be accounted for outside the Java heap.

When choosing `resources.requests` and `resources.limits` on Kubernetes, measure heap, RSS, CPU throttling, GC pauses, consumer lag, and state restore speed under realistic load. If a container is OOMKilled, increasing the heap percentage without accounting for native memory can make things worse.

Do not package unnecessary debugging tools in the runtime image. When troubleshooting incidents, use debugging methods approved by your organization instead of granting root privileges to production images.

## 12. Health Endpoints and Readiness/Liveness

Applications with Actuator and an HTTP stack can expose `/actuator/health/liveness` and `/actuator/health/readiness`. Spring Boot integrates `LivenessState` and `ReadinessState`, which Kubernetes probes use to decide whether to restart or route traffic.

Example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Do not include brokers, databases, or external services in liveness in a way that causes all replicas to continuously restart when a shared dependency fails. Liveness should reflect the process's ability to self-recover; readiness should reflect its ability to serve traffic according to the application's contract.

For an application that only has a Kafka consumer and does not serve HTTP requests, web server readiness does not automatically pause the consumer or guarantee all bindings are connected. If you want readiness to reflect binder status or Kafka Streams state restoration, design an appropriate health indicator/readiness contributor and test it when the broker fails.

If management endpoints run on a separate port, probes might return UP even when the main HTTP API is not accepting requests. Spring Boot provides `management.endpoint.health.probes.add-additional-paths=true` to expose `/livez` and `/readyz` on the main port. Choose the probe port according to your actual runtime architecture.

## 13. Minimal Kubernetes Deployment

An example illustrating two replicas of a Kafka consumer, each using the same image and consumer group:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
    spec:
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/events/order-consumer:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: KAFKA_BROKERS
              value: "kafka-bootstrap.messaging.svc.cluster.local:9092"
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 18
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

This manifest assumes the application has web/Actuator on port 8080 and the health paths are reachable by kubelet. If Spring Security protects Actuator, configure appropriate rules for probes on the internal network without exposing sensitive management endpoints.

The values for `replicas`, CPU/memory, probe timing, and grace period are examples that should be validated under real load. In particular, `startupProbe` should allow enough time for application initialization; for Kafka Streams with large state restores, measure recovery time and adjust accordingly.

Creating a Kubernetes Service is not mandatory for an application that only consumes messages and receives no external requests. If you need to expose REST endpoints, metrics scraping, or Interactive Queries, declare a Service/network policy according to the specific purpose. Note that Service load balancing does not automatically route Interactive Queries to the instance owning a key.

## 14. Graceful Shutdown to Avoid Abrupt Termination

When Kubernetes replaces a pod, it sends SIGTERM before `terminationGracePeriodSeconds` expires and forces termination if the process has not exited. Java should be the main process of the container to receive this signal. Spring Boot handles closing the application context and stopping lifecycle components in order.

Example:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

On recent Spring Boot versions, graceful shutdown of the embedded web server is enabled by default; for projects on older versions, confirm or configure `server.shutdown: graceful`. The shutdown timeout must be less than the `terminationGracePeriodSeconds` budget, leaving buffer room for sidecars/proxies and other shutdown steps.

When a consumer is processing a message:

- Determine when the handler completes, ack/commit offsets occur, or transactions are closed.
- Do not assume every binder guarantees no reprocessing after SIGTERM.
- If the process receives SIGKILL or is OOMKilled, in-flight messages may be redelivered.
- Important side effects must be idempotent or use an appropriate inbox/outbox/transaction pattern.
- After deployment, check consumer lag, queue depth, and DLQ to detect improper stop/restart behavior.

Graceful shutdown reduces disruption, but does not replace crash testing. Producers using `Supplier` or `StreamBridge` also need to wait for in-flight messages to be sent according to the binder configuration.

## 15. Additional State Considerations for the Kafka Streams Binder

A Kafka Streams application has a topology, application ID, task assignment, and state stores. When running multiple replicas:

- Replicas participating in the same logical topology must use the same Kafka Streams `application.id`.
- If there are multiple independent processor functions in the same application, you may need to assign a separate application ID for each processor.
- Each instance has its own local state directory; do not mount the same RocksDB state directory across multiple pods.
- State can be rebuilt from changelog topics after losing the local directory, but restoration consumes time and network bandwidth.
- Persistent volumes can help reuse local state when tasks/pods are rescheduled appropriately, though they require an ownership and cleanup strategy; volumes alone do not eliminate rebalancing.

Configuration example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-aggregate-v1
            brokers: ${KAFKA_BROKERS:kafka:9092}
            configuration:
              state.dir: /var/lib/kafka-streams
~~~

If using `state.dir` as shown above, mount a writable volume at `/var/lib/kafka-streams` and ensure Java's UID/GID has permissions. Do not arbitrarily share a single hostPath/RWO volume across replicas. For multi-replica pods with distinct state, consider a StatefulSet or an operationally proven volume strategy.

For test scenarios using a temporary state directory per pod, you can add an `emptyDir` to the container in the Deployment manifest:

~~~yaml
spec:
  template:
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: app
          volumeMounts:
            - name: kafka-streams-state
              mountPath: /var/lib/kafka-streams
      volumes:
        - name: kafka-streams-state
          emptyDir: {}
~~~

This is an addition to an existing Deployment configuration, not a standalone Kubernetes manifest. `emptyDir` is lost when a pod is deleted; Kafka Streams must restore state from the changelog if state is properly stored on Kafka. Before production, verify restore duration and node disk capacity. If using persistent volumes, configure write permissions and volume lifecycle aligned with task assignment.

If Interactive Queries are needed, each Kafka Streams instance must advertise `application.server` with a host/port directly reachable at that instance. Do not set a shared load-balanced Service address across all replicas as `HostInfo` metadata, because key-based queries might be routed to a pod that does not own the partition.

## 16. Rolling Updates, Scaling, and Delivery Guarantees

New container images are typically deployed via rolling updates. With a Kafka consumer group, adding or removing replicas can trigger rebalancing; with Kafka Streams, tasks may move to another instance and restore state.

A deployment workflow should include:

1. Build and test the JAR, creating an image with an immutable tag.
2. Scan the image, publish it to the registry, and record the digest.
3. Deploy via canary or rolling update with an appropriate replica/partition count.
4. Observe startup, health, consumer group membership, lag, and binder errors.
5. Wait for business logic to process new messages and check the backlog.
6. If rollback is needed, redeploy the previous image digest along with compatible configuration.

With Kafka, the number of useful consumer replicas in the same group is bounded by the number of partitions for the corresponding topics/tasks; scaling pods beyond the partition count does not automatically increase message processing throughput. With Kafka Streams, you must also account for task assignment, RocksDB restoration, and standby replicas.

Rolling updates can cause messages to be redelivered. Even when the binder uses transactions or configured at-least-once processing, side effects on external systems must be evaluated separately. Do not claim end-to-end exactly-once semantics solely because the image deploys without downtime.

When changing message schemas, maintain compatibility between old and new producers/consumers during the rollout window. If a version that only reads the new schema is deployed before all producers switch over, consumers may fail deserialization and push messages to the DLQ.

## 17. Verifying the Image After Build

The commands below are example operations when running on a machine with Docker and a suitable broker:

~~~bash
docker image inspect order-consumer:1.0.0
docker run --rm --entrypoint java order-consumer:1.0.0 -version
docker run --rm --name order-consumer \
  --env KAFKA_BROKERS=kafka.internal:9092 \
  order-consumer:1.0.0
~~~

With a Dockerfile using `ENTRYPOINT ["java","-jar",...]`, arguments placed after the image name are passed to `java -jar`; to inspect the Java runtime, override the entrypoint with `--entrypoint java` as in the second command.

Verify:

- The image has a Java runtime matching the bytecode.
- The process runs under a non-root UID.
- `docker logs` does not expose secrets.
- The broker address resolves from inside the container.
- Function definitions and binding names match the configuration.
- Test messages flow through a real broker and produce business results.
- SIGTERM stops the application within the grace period.
- The image runs under production-like CPU/memory limits.

Do not take container status `running` as proof that messages are being processed. Send an event with an ID, monitor the consumer, and confirm the result in the output topic/queue or database.

## 18. Security and Image Supply Chain

Because the image packages both application code and dependencies, it is also a unit requiring vulnerability control:

- Prefer small runtime images and do not run Java as root.
- Pin base images to trusted tags/digests; rebuild periodically when patches are released.
- Use immutable version/tags or image digests when deploying, avoiding uncontrolled `latest` tags.
- Scan for CVEs in both JAR dependencies and the image OS.
- Generate and store an SBOM if the pipeline supports it.
- Sign images/attestations per organizational process if required.
- Restrict registry push/pull permissions; separate release and rollback privileges.
- Do not leave SSH keys, kubeconfig, tokens, build caches containing secrets, or unnecessary source code inside the runtime image.
- Use a read-only root filesystem if the application and binder have been granted appropriate writable volumes/tmp directories.

Especially with Kafka SSL and RocksDB, a read-only filesystem does not mean the application never writes files. Mount suitable paths for state, temp files, and certificates used by the client.

## 19. Common Packaging and Deployment Issues

| Symptom | Common Cause | How to Check or Resolve |
|---|---|---|
| `no main manifest attribute` on `java -jar` | Accidentally copied `*-plain.jar` | Use `bootJar` and an explicit filename |
| `UnsupportedClassVersionError` | JRE in the image is older than Java compile target | Align the Java toolchain and runtime |
| Container starts but cannot connect to Kafka | Used `localhost:9092` inside the container | Use a reachable broker DNS and check advertised listeners |
| Bootstrap connects but broker metadata fails | Kafka `advertised.listeners` returns a host unreachable by clients | Fix listener/advertised address on the broker |
| No messages received after restart | Consumer group or destination changed | Check bindings, group, and committed offsets |
| Pod `CrashLoopBackOff` | App config error, missing secret, OOM, or overly aggressive liveness probe | Check logs, events, memory, and probes |
| Pod `Running` but lag increases | Consumer not connected, paused, handler error, or missing partitions | Check binder health, group assignment, lag/DLQ |
| Large image and slow push | Single layer contains the entire fat JAR or large build context | Use layered JARs/Buildpacks and `.dockerignore` |
| `Permission denied` with RocksDB | State dir/volume is not writable by non-root UID | Set proper volume security context/permissions |
| Shutdown killed by SIGKILL | Grace period too short or handler fails to stop in time | Adjust graceful timeout and inspect in-flight work |
| Readiness stays UP while binder is not processing | Probe only reflects general Spring Boot status | Add a readiness indicator tailored to the binder |
| Rollback still fails deserialization | Incompatible schema between versions | Design schema evolution and test mixed-version setups |

## 20. Application Release Checklist

- Spring Boot, Spring Cloud, and binder dependencies are on compatible versions.
- `bootJar` produces a valid executable JAR and `java -jar` runs properly.
- The image uses the matching Java runtime and runs as a non-root user.
- Either `bootBuildImage` or a Dockerfile is chosen with a base image update strategy.
- Immutable tags/digests are used, recording the release version and commit.
- No secrets exist in the JAR, Dockerfile, image layers, or startup logs.
- Kafka/RabbitMQ/Pulsar addresses are passed accurately at runtime and are reachable from the container network.
- Binding names, destinations, groups, and binder configurations are verified.
- Actuator health endpoints exist, with liveness/readiness designed for actual operational effect.
- Memory/CPU limits are appropriate for the JVM and client/binder.
- Graceful shutdown and termination grace period have been tested.
- If using Kafka Streams, the state directory and application ID are correct; the state store is writable.
- Rollouts monitor lag/backlog, retries, DLQ, rebalancing, and state restoration.
- Post-deploy smoke test exists with a message ID and verified business outcome.
- Rollback strategy exists along with message schema compatibility checks.

Packaging a Spring Cloud Stream application is more than putting a JAR into a container. A reliable image must run the right Java runtime, package dependencies consistently, receive broker configuration from the environment, support proper shutdown and health checks, and ensure consumers/binders continue processing after pod replacements. Both Buildpacks and Dockerfiles can produce OCI images; either choice still requires testing against a real broker and controlled image release management.

## References

- [Spring Boot — Packaging OCI Images with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html)
- [Spring Boot — Dockerfiles and Layered JARs](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Kubernetes Probes and Health Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
