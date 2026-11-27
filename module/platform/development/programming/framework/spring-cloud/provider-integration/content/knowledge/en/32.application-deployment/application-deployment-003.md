# Packaging JARs or Containers and Verifying Runtime Environment Conditions

A Spring Boot application that runs well on a developer's machine is not guaranteed to start properly in staging or production. The JAR may have been built with a different JDK than the JRE on the server; a container may lack CA certificates, target the wrong CPU architecture, lack environment variables, lack write permissions to a temporary directory, or have a memory limit lower than the JVM configuration. Therefore, packaging the application must go hand-in-hand with defining the runtime contract clearly and verifying real conditions before admitting traffic.

Spring Boot can be packaged as an executable JAR or an OCI container image. A JAR is suitable when the platform already provides a Java runtime; a container image is suitable when you want to bundle the runtime with the application and deploy consistently on Kubernetes, ECS, Cloud Run, or other container platforms. Regardless of the approach, the artifact needs a clear version, environment-provided configuration, a properly attached workload identity, and health check/shutdown behavior compatible with the platform.

This lesson belongs to the **Application Deployment** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module provides hands-on practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on packaging executable JARs/containers and verifying Java runtime, configuration, networking, identity, resource limits, probes, and shutdown before the application serves business traffic.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between an executable JAR and an OCI container image and choose the right format.
- Configure Maven or Gradle to build a Spring Boot executable JAR.
- Inspect the manifest, dependencies, and archive contents before release.
- Build container images using Cloud Native Buildpacks or Docker multi-stage builds.
- Optimize Spring Boot JAR layers to leverage build caching.
- Choose a JRE, CPU architecture, and OS compatible with the artifact.
- Configure non-root users, filesystems, and network ports inside containers.
- Pass profiles, endpoints, secret references, and workload identities from the runtime environment.
- Tune JVM memory/CPU according to container limits.
- Configure startup, liveness, and readiness probes using Spring Boot Actuator.
- Enable graceful shutdown when the platform sends `SIGTERM`.
- Perform smoke tests and verify runtime conditions before admitting traffic.

## 2. How Do JARs and Container Images Differ?

An **executable JAR** contains application bytecode, dependencies, and the Spring Boot launcher. The host machine must have a compatible Java runtime installed. A JAR does not include an entire operating system or JRE; the same JAR can run across multiple environments if the runtime and configuration match.

An **OCI container image** packages the application together with the required runtime and filesystem. The host still supplies the kernel and container runtime, but does not need a separate Java installation on the host. The image can run under Docker, containerd, or any OCI-compliant container platform.

| Criterion | Executable JAR | Container image |
|---|---|---|
| Java runtime | Target machine must have a compatible JRE/JDK installed | Typically packaged inside the image |
| Release size | Primarily the JAR and dependencies | Includes base image, runtime, and application |
| Configuration | Files, environment, system properties | Environment, mounted files/secrets, platform config |
| Runtime isolation | Depends on host machine configuration | Has filesystem/process/network namespaces |
| Distribution | Artifact repository, VMs, services | OCI registry, orchestrator, container platform |
| OS control | Managed by server operations | Managed by image builder/base image and platform |
| Health checks | Service manager or platform | Container runtime/orchestrator probes |
| Best fit | VMs, bare metal, PaaS accepting JARs | Kubernetes, ECS, Cloud Run, container apps |

Containers do not automatically make an application secure or portable. An image can still contain secrets, run as root, use an outdated base image, or miss CA certificates. A JAR can also be deployed securely if the Java runtime, OS, file permissions, and configuration are well managed.

## 3. Preparing a Spring Boot Project for Packaging

A typical Spring Boot project includes:

- A main application class annotated with `@SpringBootApplication`.
- Starter dependencies for web, database, messaging, or cloud SDKs.
- Spring Boot Maven or Gradle build plugin configuration.
- Tests and required profile configurations.
- A consistently declared target Java version.

Example Maven project structure:

~~~text
orders-service/
  pom.xml
  src/
    main/
      java/
      resources/
        application.yml
    test/
      java/
  Dockerfile
  .dockerignore
~~~

Example main class:

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

Having a main class alone is not enough to produce an executable JAR. The build must run the Spring Boot `repackage` goal or Gradle `bootJar` task to add the launcher and organize dependencies in the expected layout.

### 3.1. Choosing a Java Version

The Java version used for compilation and the Java version used at runtime must be compatible. If bytecode is compiled for Java 21, a Java 17 runtime cannot execute those classes. Choose a Java baseline supported across all deployment environments and declare it consistently in Maven/Gradle, CI images, Docker base images, and platform runtimes.

Maven example targeting Java 21:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Gradle example:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Toolchains ensure the build uses the chosen JDK. The runtime still requires a compatible Java version. Never infer the runtime version solely from the build machine.

## 4. Building an Executable JAR with Maven

The Spring Boot Maven Plugin runs `repackage` to produce an archive executable via `java -jar`. If the project uses `spring-boot-starter-parent`, the parent already configures execution for this goal. If you do not use the parent, declare the `repackage` goal in the plugin execution.

Example plugin configuration:

~~~xml
<build>
    <finalName>orders-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Build and verify:

~~~bash
./mvnw clean verify
~~~

The resulting executable JAR is located at:

~~~text
target/orders-service.jar
~~~

Run it locally:

~~~bash
java -jar target/orders-service.jar
~~~

In CI, run tests and verification before publishing artifacts. Do not use `skipTests` for release builds unless the pipeline has an equivalent standalone test stage.

### 4.1. Inspecting the Repackaged JAR

Check file existence and size:

~~~bash
ls -lh target/orders-service.jar
~~~

List archive contents:

~~~bash
jar tf target/orders-service.jar
~~~

A Spring Boot executable JAR typically contains:
- `META-INF/MANIFEST.MF`.
- `org/springframework/boot/loader` or the loader package corresponding to the version.
- `BOOT-INF/classes` containing application classes and resources.
- `BOOT-INF/lib` containing dependency JARs.

Read the manifest:

~~~bash
unzip -p target/orders-service.jar META-INF/MANIFEST.MF
~~~

The executable JAR manifest has `Main-Class` pointing to the Spring Boot launcher and `Start-Class` pointing to the main application class. The launcher package name changes across Spring Boot versions; do not hardcode old launcher names in verification scripts.

If the archive only contains classes and dependencies in a plain JAR layout, `java -jar` may report a missing `Main-Class` or fail to find the launcher. Inspect the `repackage` plugin configuration and build output instead of editing the manifest manually.

## 5. Building an Executable JAR with Gradle

The Spring Boot Gradle Plugin provides the `bootJar` task. When the plugin is applied, this task packages application classes, resources, dependencies, and the Spring Boot loader.

Example build:

~~~bash
./gradlew clean test bootJar
~~~

The output is typically located at:

~~~text
build/libs/orders-service.jar
~~~

You can configure a stable archive name:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-service.jar'
}
~~~

Run it locally:

~~~bash
java -jar build/libs/orders-service.jar
~~~

Distinguish `bootJar` from `jar`:
- `bootJar` creates the executable Spring Boot archive.
- `jar` creates a plain Java archive.
- A project may produce both if task configuration enables both.

If a pipeline mistakenly picks up the plain `jar` file for deployment, the application will not run with `java -jar`. Specify the exact artifact path and verify the manifest in the release job.

## 6. Verifying Artifact Contents and Metadata

Before releasing, verify:

- Artifact name and version match the release.
- The JAR is repackaged and includes the launcher.
- Required runtime dependencies are packaged.
- No `devtools` or test-only dependencies are present in production artifacts.
- Production profiles are not hardcoded into build files.
- No passwords, private keys, access keys, or `.env` files exist in the archive.
- Build metadata identifies commit, version, build time, and Java baseline.
- Artifact checksums are stored for verification at deployment time.

Do not embed secrets into `application.yml` inside the JAR. Artifacts are typically stored in repositories, CI caches, or registries accessible to far more people than a secret manager. If a secret is baked into the JAR, rotating it forces an artifact rebuild and the secret lingers in artifact history.

You can inspect the dependency tree to catch unwanted dependencies:

~~~bash
./mvnw dependency:tree
~~~

Or with Gradle:

~~~bash
./gradlew dependencies
~~~

Inspecting dependencies does not replace vulnerability scanning. Use your pipeline's dependency scan/SCA tooling and remediate CVEs according to organizational policy.

## 7. Packaging Containers with Cloud Native Buildpacks

The Spring Boot Maven Plugin and Gradle Plugin can create OCI images from an executable JAR using Cloud Native Buildpacks (CNB). The buildpack detects the application, selects a runtime, and builds an image using the configured builder. This avoids having to write a `Dockerfile` for common cases.

Maven:

~~~bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/orders-service:1.0.0
~~~

Gradle:

~~~bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/orders-service:1.0.0
~~~

The buildpack builder requires access to a Docker daemon or compatible environment to build the image. Images produced by Spring Boot `build-image` run as a non-root user by default per buildpack configuration.

After building, inspect the image:

~~~bash
docker image inspect registry.example.com/orders-service:1.0.0
docker image ls registry.example.com/orders-service
~~~

Run a quick test:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  registry.example.com/orders-service:1.0.0
~~~

Buildpacks fit well when you want to reduce the number of Dockerfiles you maintain manually. However, you still must choose trusted builders/base images, keep builders updated, inspect images, configure runtime settings, and store images by immutable tag/digest.

## 8. Packaging Containers with Docker Multi-Stage Builds

A Docker multi-stage build separates building the JAR from running the application. Maven/JDK are needed only in the build stage; the runtime image contains only the JRE and JAR.

Example Dockerfile:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY src ./src

RUN mvn -B verify

FROM eclipse-temurin:21-jre-jammy AS runtime
WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=build --chown=10001:10001 \
    /workspace/target/orders-service.jar /app/app.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This `Dockerfile` assumes Maven `finalName` is set to `orders-service`. If the artifact name differs, update the `COPY` path. The build stage runs `verify`; if the project uses Maven Wrapper or needs custom Maven settings, copy those files into the build stage and invoke the wrapper.

Build the image:

~~~bash
docker build --pull \
  -t registry.example.com/orders-service:1.0.0 .
~~~

Run the container:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  registry.example.com/orders-service:1.0.0
~~~

### 8.1. Why Use Multi-Stage Builds?

- Build tools and source code stay out of the runtime image.
- The runtime image is smaller and has fewer packages.
- Build and runtime stages can choose separate base images.
- Dependency/build layers can be cached.
- Reduces attack surface compared to images containing a full JDK, Maven, and debugging tools.

Do not install shells, `curl`, package managers, or editors into the runtime image if the application does not need them. Even a minimal image still requires regular updates and scanning.

### 8.2. Using .dockerignore

Avoid sending unnecessary files into the Docker build context:

~~~text
.git
.gitignore
.idea
.vscode
target
build
.gradle
.mvn/wrapper/maven-wrapper.jar
.env
.env.*
*.log
secrets/
~~~

Adjust `.dockerignore` to fit your build process. If the build stage needs the Maven Wrapper, do not exclude `.mvn` or `mvnw`. Never copy `secrets/` directories or `.env` files into the build context.

## 9. Optimizing Spring Boot JAR Layers

A Spring Boot executable JAR can be split into layers. Infrequently changing dependencies go into dedicated layers; frequently changing application classes go into the final layer. When only code changes, Docker can reuse dependency layers from the build cache.

Default layers typically include:
- `dependencies`: non-SNAPSHOT dependencies.
- `spring-boot-loader`: Spring Boot loader.
- `snapshot-dependencies`: SNAPSHOT dependencies.
- `application`: module dependencies, application classes, and resources.

You can list layers:

~~~bash
java -Djarmode=tools -jar target/orders-service.jar list-layers
~~~

Extract layers:

~~~bash
java -Djarmode=tools -jar target/orders-service.jar \
  extract --layers --destination target/extracted
~~~

Then use a multi-stage Dockerfile to copy layer directories in a stable order. The exact approach depends on the Spring Boot version and `jarmode` tools packaged in the archive; consult the sample Dockerfile in the Spring Boot documentation matching your project's version.

Do not arbitrarily reorder layers. Placing infrequently changing dependencies first and the application layer last maximizes cache reuse. If your project does not need layer cache optimization, buildpacks or a Dockerfile copying a single JAR are simpler.

## 10. Configuring the Runtime Image and User

Containers should run as a non-root user. If a process is compromised, the attacker's privileges inside the container are far more restricted.

Example in a Dockerfile:

~~~dockerfile
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --chown=10001:10001 target/orders-service.jar /app/app.jar
USER 10001:10001
~~~

Some base images already define a non-root user. Read the base image documentation and use the proper UID/GID. If the orchestrator assigns an arbitrary UID, ensure writable directories have matching permissions.

Additional principles:
- Use official JRE base images or images from trusted publishers.
- Pin versioned tags, or even better, digests in production releases.
- Rebuild periodically to pick up OS/JRE patches.
- Never store secrets in Dockerfile `ARG`, `ENV`, or image layers.
- Never run processes in privileged mode.
- Drop Linux capabilities and use a read-only root filesystem when supported by the application.
- Expose only the ports the application actually needs.

## 11. Java Runtime and Operating System Conditions

A JAR is not tied directly to an OS like a native binary, yet the runtime still has conditions that must be verified:

| Condition | How to Verify | Common Failure |
|---|---|---|
| Java version | `java -version` | `UnsupportedClassVersionError` |
| Java vendor/distribution | `java -XshowSettings:properties -version` | Differences in CA bundle or native behavior |
| CPU architecture | `uname -m` or `docker image inspect` | `amd64` image running on `arm64` without emulation |
| OS libraries | `ldd --version`, package inventory | Missing native library or `libc` |
| Timezone | `date`, `TZ` configuration | Incorrect timestamp/cron timezone |
| Locale/encoding | `java -XshowSettings:properties -version` | Unexpected character encoding |
| CA certificates | Inspect trust store and TLS handshake | `SSLHandshakeException` |
| DNS/network | `nslookup`/`getent` and endpoint connectivity | `UnknownHostException`, timeout |
| File permissions | `id`, `ls -ld`, volume check | `AccessDeniedException` |
| Memory/CPU | Container limits and process metrics | `OOMKilled`, throttling, increased latency |

If you use JNI, native compression, Netty native transport, image processing, or libraries depending on `libc`, you must verify the OS and image architecture. Alpine uses `musl libc`, whereas many native dependencies are compiled for `glibc`; choosing Alpine solely for image size can introduce runtime failures.

### 11.1. Checking Java Version and JVM Flags

Commands:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

You can check class file target versions with `javap` or bytecode inspection tools if needed. Do not look only at the JDK version on the build machine; inspect the actual Java version inside the runtime container.

### 11.2. CA Certificates and TLS

Cloud SDKs typically connect over HTTPS to managed APIs. The runtime needs a trust store with the proper CAs and accurate system time. If using a private CA, mount the certificate via a platform-managed mechanism and configure a custom trust store.

Never disable hostname verification or trust all certificates to silence TLS errors. Check the certificate chain, hostname, DNS, system clock, and CA bundle first.

## 12. Spring Boot Environment Configuration

The same artifact should run in dev, staging, and production via externalized configuration. Values typically supplied at deployment include:

- Active profile.
- Server port and management endpoints.
- Resource endpoints, queue/topic/container names.
- Region, project ID, or resource identifiers.
- Feature flags and timeouts.
- Secret references or mounted secrets.
- JVM options and resource limits.

Example default `application.yml`:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    default: local

server:
  port: 8080
  shutdown: graceful

app:
  cloud:
    provider: local
    messaging:
      destination: orders-local
    storage:
      container: orders-local
~~~

Production can inject:

~~~bash
SPRING_PROFILES_ACTIVE=production
SERVER_PORT=8080
APP_CLOUD_PROVIDER=azure
APP_CLOUD_MESSAGING_DESTINATION=orders-prod-events
APP_CLOUD_STORAGE_CONTAINER=orders-prod-checkpoints
~~~

Spring Boot relaxed binding maps environment variables to properties. There is no need to build a separate JAR per environment. Do not put secret values into the image or configuration files committed to Git; use workload identity or a secret manager.

### 12.1. Profiles Do Not Replace Secret Management

Profiles only select environment-appropriate configuration sets. Never put production passwords inside an `application-prod.yml` committed to the repository. Profile files may contain non-sensitive endpoints/names; credentials come from Managed Identity, IAM roles, Workload Identity, or secret volumes.

### 12.2. Application Port and Management Port

`server.port` controls the primary HTTP port. If `management.server.port` is configured separately, Actuator listens on a different port. When configuring probes or load balancers, use the right port and ensure endpoints are exposed selectively.

`EXPOSE` in a Dockerfile is only metadata describing which port the container uses; it does not publish the port to the host. When running locally, map `-p hostPort:containerPort` or configure the corresponding port mapping on the platform.

## 13. JVM Memory and Container Limits

Containers can be constrained by memory and CPU limits. Modern JVMs are container-aware, but the application must still be sized appropriately for the total available memory.

Process memory is not just the Java heap. It also includes:
- Metaspace and class metadata.
- Thread stacks.
- Direct buffers/NIO.
- JIT code cache.
- Native memory used by TLS, compression, and native libraries.
- JVM overhead and memory-mapped files.

If you set `Xmx` close to the container memory limit, the process can be `OOMKilled` even before the heap reaches `Xmx` because native memory runs out.

You can set a maximum RAM percentage for the heap:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:InitialRAMPercentage=25"
~~~

These percentages are only starting examples; measure real load, thread counts, direct buffers, and memory usage before finalizing. Avoid setting conflicting fixed `-Xmx` and `MaxRAMPercentage` flags.

When a container is `OOMKilled`:
1. Inspect the memory limit and exit reason.
2. Check heap usage, GC logs, thread count, and direct buffers.
3. Check for memory leaks or oversized payloads/batches.
4. Raise the limit or adjust heap/native allocations based on measurements.
5. Do not simply raise `Xmx` right up to the limit.

## 14. CPU, Threads, and Concurrency

Low CPU limits can slow down GC, JIT, and request processing. When thread pools are oversized, the application wastes stack memory and incurs high context-switching overhead. Review:
- Container CPU requests/limits.
- Number of cores detected by the JVM.
- Tomcat/Jetty/Netty thread pools.
- Database connection pools.
- Kafka/Event Hubs/Service Bus consumer concurrency.
- Batch sizes and parallel message processing counts.

Do not size thread counts based on the CPU count of a developer laptop. A container may be allocated only a fraction of a node's CPU. Run load tests to determine appropriate throughput, latency, CPU throttling, and connection pool sizes.

## 15. Health Checks with Spring Boot Actuator

Add the Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot exposes health endpoints. For Kubernetes, Spring Boot provides dedicated health groups for liveness and readiness:

- `/actuator/health/liveness`: whether the process can continue running.
- `/actuator/health/readiness`: whether the instance is ready to accept traffic.
- `/actuator/health`: aggregate health, which may include additional indicators depending on configuration.

Configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      group:
        readiness:
          include: readinessState
~~~

Health endpoints may expose dependency or internal state details. Expose only needed endpoints and keep `show-details` at an appropriate level. Never expose `env`, `configprops`, or `heapdump` on a public ingress.

### 15.1. Liveness Should Not Depend on External Cloud Services

Liveness answers: is the process still alive and able to make progress? If a database or messaging service temporarily loses connectivity, restarting all pods will not fix a shared dependency outage and can trigger a cascading failure.

Readiness answers: can this instance accept traffic right now? You can add critical dependencies to the readiness group if you decide an instance should be removed from traffic when that dependency is unavailable. Evaluate carefully when dealing with shared dependencies or circuit breakers/fallbacks.

## 16. Startup, Liveness, and Readiness Probes on Kubernetes

The three probe types serve distinct purposes:

| Probe | Question | Action on Failure |
|---|---|---|
| Startup | Has the application finished starting? | After allowed failures, the container restarts |
| Liveness | Is the process deadlocked or unable to make progress? | Container restarts |
| Readiness | Can the instance accept requests? | Pod is removed from traffic-serving endpoints |

Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: orders-service
          image: registry.example.com/orders-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
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
~~~

The startup probe gives the application time to initialize before liveness/readiness probes begin. A readiness failure stops sending traffic to the pod; a liveness failure restarts the container. Values in the example must be tuned to your service's startup time, load, and SLA.

If the management server uses a separate port, update the probe port or configure an additional health group on the main server port. A health endpoint on the management port can report healthy even when the main HTTP server is unhealthy; verify the actual request path.

## 17. Graceful Shutdown and Handling SIGTERM

When Kubernetes or a container platform stops an instance, the runtime typically sends `SIGTERM` and waits for a grace period before killing the process. Spring Boot supports graceful shutdown for embedded web servers. Configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

During shutdown:
- Stop accepting new requests.
- Allow in-flight requests to finish within the allowed timeout.
- Stop listeners/workers according to lifecycle order.
- Close connection pools and SDK clients.
- Flush telemetry/logs if possible.
- Exit the process before the orchestrator's termination grace period expires.

The pod's `terminationGracePeriodSeconds` must exceed the shutdown timeout plus the time the platform needs to drain traffic. If there is a `preStop` hook, include hook duration in the total grace period.

For message consumers, shutdown must stop fetching new messages, finish or abandon in-flight messages per broker semantics, and ACK/commit at the proper time. Never ACK a message merely because the process is shutting down.

## 18. Filesystem, Writable Directories, and Container Security Context

Many container platforms allow a read-only root filesystem. If the application needs to write temporary files, specify a dedicated writable directory such as `/tmp` or a volume mount. Do not write logs to local files inside the container if the platform collects logs from `stdout`/`stderr`.

Example `docker run` with a read-only root filesystem and `tmpfs` for `/tmp`:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 \
  registry.example.com/orders-service:1.0.0
~~~

If the application needs to write uploads or business files, mount an appropriate volume or use object storage; do not rely on the container's writable layer because data is lost when the container is replaced.

On Kubernetes, you can configure:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
~~~

Ensure image and volume permissions match the UID/GID. If using writable volumes, configure `fsGroup` or ownership per storage driver guidelines and security policy.

## 19. Network, DNS, TLS, and Workload Identity

A running container does not automatically mean it can reach managed services. Before admitting traffic, verify:

- DNS resolves the target hostnames properly.
- Egress/network policies permit connections to endpoints.
- Private endpoints, route tables, firewalls, and security groups are configured properly.
- TLS certificate chains are trusted.
- Proxy variables are set if the environment requires a proxy.
- Managed Identity, IAM role, or Workload Identity is attached to the workload.
- The runtime principal holds the required data-plane roles.
- Token endpoints/metadata services are reachable per platform requirements.
- No static credentials are baked into the image.

Never test identity by printing access tokens or credentials into logs. Smoke tests should perform a minimal data-plane operation against a test resource or an appropriate read-only API.

### 19.1. Distinguishing Configuration Errors from Transient Errors

| Symptom | Where to Check |
|---|---|
| `UnknownHostException` | DNS, hostname, and private DNS zones |
| `Connect timed out` | Egress, firewall, routes, private endpoints |
| `SSLHandshakeException` | CA trust store, hostname, system clock |
| `401`/`403` | Workload identity, token audience/issuer, role assignments |
| `404` | Resource name, endpoint, environment outputs |
| Connection pool exhausted | Pool size, timeouts, request concurrency |
| Throttling/`429` | Service quotas, retry/backoff, concurrency |
| `OOMKilled` | Container memory limits and JVM heap/native memory |

Do not retry indefinitely on wrong endpoints or missing permissions. Use retries with backoff for transient errors; configuration errors should fail fast or mark readiness unhealthy.

## 20. Logs, Metrics, and Build Metadata

Containerized applications typically write logs to `stdout`/`stderr` for platform collection. Avoid relying on local log files on an ephemeral filesystem.

You should include:
- Application version and Git commit.
- Build time and Java version.
- Environment/service name.
- Request correlation/trace IDs.
- JVM heap, GC pause, thread, and CPU metrics.
- Startup duration and readiness transitions.
- Dependency latency/error rates.
- Container restart/OOM events.
- Image digest and release SBOM.

Never write secrets, access tokens, passwords, authorization headers, or the entire environment into logs. Health and info endpoints must have restricted access and expose only appropriate information.

## 21. Verifying Container Images and Artifacts Before Release

After building the image:

~~~bash
docker image inspect registry.example.com/orders-service:1.0.0
docker history registry.example.com/orders-service:1.0.0
docker run --rm registry.example.com/orders-service:1.0.0 --version
~~~

`--version` only works if the application supports that flag; otherwise, inspect image metadata and the health endpoint after startup.

Verification steps should include:
1. Build from an identified source commit.
2. Run unit and integration tests.
3. Scan dependencies and the base image.
4. Verify user, entrypoint, ports, and filesystem.
5. Verify no secrets exist in image layers.
6. Generate an SBOM and store it alongside release metadata.
7. Apply an immutable tag and record the digest.
8. Sign the image if required by supply-chain policy.
9. Deploy to staging using the exact tested image digest.
10. Run smoke tests before promoting to production.

Never use the `latest` tag as the sole identifier in production. A tag can point to a different digest after a new push; pinning by digest ensures deployments specify the exact image contents.

## 22. Testing Runtime Environment Conditions

| Scenario | How to Test | Expected Result |
|---|---|---|
| Executable JAR | Run `java -jar` in runtime JRE | Application context starts |
| Incompatible Java version | Run artifact on a JRE lower than target | Pipeline/runtime catches version mismatch |
| JAR missing dependency | Inspect archive and startup | Classpath error caught before release |
| Non-root container | Inspect user or run `id` in container | Process does not run as UID 0 |
| Image architecture | Inspect platform/manifest | Matches node architecture |
| Missing config | Omit required endpoint/profile variable | App fails fast or readiness fails |
| Missing secret | Omit secret reference mount in test | No secret logged; clear config error |
| DNS/network error | Run in restricted test network | Smoke test catches failure |
| Missing IAM/RBAC | Use workload identity without role | Data-plane operation is denied |
| Low memory limit | Constrain container memory in test | OOM and heap behavior observed |
| Slow startup | Configure startup probe with proper window | No premature restart during startup |
| Readiness false | Disable required dependency in test | Pod receives no traffic |
| Liveness false | Simulate hung/non-progressing process in test | Orchestrator restarts per policy |
| `SIGTERM` | Stop container while requests are in flight | In-flight requests drain within grace period |
| Read-only filesystem | Run container with read-only rootfs | App writes only to permitted paths |
| Missing TLS CA | Test against endpoint with untrusted CA | TLS failure clearly detected |
| Image rollback | Deploy previous digest | Previous version recovers cleanly |

Test environment failures in isolated test/staging environments. Never intentionally revoke roles, delete resources, or trigger OOMs on production workloads just to test.

## 23. Recommended Release Workflow

A release pipeline can follow this sequence:

~~~mermaid
flowchart TD
    SRC["Source commit"] --> BUILD["Build executable JAR"]
    BUILD --> TEST["Unit and integration tests"]
    TEST --> PACKAGE["Inspect JAR and metadata"]
    PACKAGE --> IMAGE["Build OCI image"]
    IMAGE --> SCAN["Scan image and dependencies"]
    SCAN --> PUBLISH["Publish image and digest"]
    PUBLISH --> DEPLOY["Deploy staging"]
    DEPLOY --> RUNTIME["Verify Java, config, identity, network"]
    RUNTIME --> HEALTH["Probe and smoke tests"]
    HEALTH --> APPROVE["Promote release"]
    APPROVE --> PROD["Deploy production"]
~~~

Build once and promote the same artifact/image digest across environments. Change only runtime configuration per environment; never rebuild the JAR with production endpoints or secrets.

When rolling back, deploy a previously tested digest. Ensure database schemas, event contracts, and resource endpoints remain compatible with the older version.

## 24. Common Issues and Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| `no main manifest attribute` | JAR was not repackaged | Check Spring Boot Maven/Gradle plugin |
| `UnsupportedClassVersionError` | Runtime Java is older than bytecode target | Align JDK/JRE versions |
| `ClassNotFoundException` | Dependency not packaged or excluded | Check dependency tree and `BOOT-INF/lib` |
| Container exits immediately | Wrong entrypoint/JAR path or config error | Check exit code and startup logs |
| Permission denied | UID lacks permission to read JAR or write directory | Check `COPY` ownership and volume permissions |
| Container cannot bind port | Port already in use or misconfigured | Check `server.port` and port mapping |
| `OOMKilled` | Heap/native memory exceeded container limit | Measure memory and adjust JVM/resource limits |
| Readiness probe fails | Wrong port/path or dependency not ready | Check Actuator, probe timings, and readiness policy |
| Liveness probe restarts continuously | Probe depends on shared external service or timeout too short | Decouple liveness from external dependencies |
| Shutdown drops messages | Listener ACKed/committed before finishing processing | Stop consumer and finish in-flight work per broker semantics |
| `SSLHandshakeException` | Wrong CA bundle or hostname | Check certificate chain and trust store |
| App runs locally but not in container | Differences in env, DNS, filesystem, architecture, or identity | Compare runtime contract and run smoke tests |
| Image too large | JDK/build tools included in runtime stage | Use buildpacks or multi-stage builds |
| Secrets appear in image | `.env` file copied or secret written in Dockerfile | Remove from build context, rotate secret, rebuild |

## 25. Pre-Production Checklist

- **Artifact:** JAR is repackaged, version/commit are clear, and checksum is stored.
- **Java:** JRE version is compatible with bytecode and framework.
- **Container:** OCI image is built from a trusted base image with an immutable digest.
- **Architecture:** Image platform matches node/runtime architecture.
- **Security:** Process runs non-root; not privileged; filesystem writable only where required.
- **Dependencies:** Dependencies/base image are scanned and up to date.
- **Configuration:** Profile, endpoints, ports, and resource names are provided by the environment.
- **Secrets:** No secrets exist in JAR, image layers, Dockerfile, or logs.
- **Identity:** Workload identity is attached with proper data-plane permissions.
- **Network:** DNS, egress, private endpoints, TLS, and CA trust work properly.
- **Resources:** JVM heap/native memory fit container limits; CPU/thread pools are benchmarked.
- **Health:** Startup, liveness, and readiness probes have appropriate paths, ports, and timeouts.
- **Shutdown:** Graceful shutdown timeout is shorter than termination grace period.
- **Observability:** Logs, metrics, traces, and build metadata are traceable.
- **Release:** Image digest is promoted across staging/production without rebuilding.
- **Recovery:** Rollback digest exists and schema/resource compatibility is verified.

## 26. Summary

Spring Boot can be packaged as an executable JAR or an OCI container image. The Spring Boot Maven Plugin and Gradle Plugin build executable archives; Cloud Native Buildpacks can build images directly; Docker multi-stage builds separate build tools from the runtime. Layered JARs help optimize caching when application code changes frequently.

Packaging is only part of deployment. The runtime environment needs a compatible Java version and architecture, externalized configuration, workload identity, network/TLS connectivity, filesystem permissions, and appropriate CPU/memory limits. On Kubernetes, startup/liveness/readiness probes must accurately reflect application state; graceful shutdown needs enough time to drain in-flight requests and messages. When pipelines verify artifacts, image digests, and runtime contracts before promotion, Spring Boot applications can run consistently on VMs, Kubernetes, and managed container platforms across AWS, Azure, and Google Cloud.

## References

- [Spring Boot Maven Plugin - Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin - Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Dockerfiles and layered archives](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot Maven Plugin - Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Spring Boot Gradle Plugin - Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html)
- [Spring Boot Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Docker Build Best Practices](https://docs.docker.com/build/building/best-practices/)
- [Kubernetes Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
