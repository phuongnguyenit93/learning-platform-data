# Boundaries Between Runtime Requirements, Packaging Tools, and Deployment Platforms

> **Module:** Spring Boot - web-runtime · **Group:** Application Deployment. This lesson separates responsibilities across **application code/JVM/Spring Boot at runtime**, **Maven/Gradle during compilation and packaging**, **Dockerfile/Cloud Native Buildpacks when building OCI images**, and **Docker/Kubernetes/PaaS when running processes, networking, secrets, health checks, and resources**. Clear boundaries are essential to pinpoint the real cause when “the build is green yet production fails.” Examples target **Java 17+, Spring Boot 4.1.2, Spring MVC, Actuator, Maven, Docker, and Kubernetes**.

## 1. Learning Objectives

After this lesson, learners can:

1. Describe the five stages: **source/dependency resolution → compile/test → JAR/WAR packaging → image build → deploy/runtime**, and state what each stage does not guarantee.
2. State the **runtime contract** of Spring Boot 4.1.2: Java 17 minimum; dependencies/classpath; ports, configuration, secrets, file permissions, CPU/RAM, external connectivity, health, and shutdown.
3. Distinguish `mvn package`, `spring-boot:repackage`, `java -jar`, Gradle `bootJar`, Boot `build-image`, `docker build`, `docker run`, image push, and Kubernetes `Deployment`.
4. Explain `BOOT-INF/classes`, `BOOT-INF/lib`, `Main-Class`/`Start-Class`, executable JARs, and differences from WARs/embedded servers/native binaries.
5. Identify the responsibilities of `Dockerfile`, JRE/base images, Cloud Native Buildpacks, image architecture, OCI digests, registries, and supply-chain checks.
6. Design the mapping `server.port` ↔ `containerPort` ↔ Service `targetPort` ↔ Ingress/LB without mistaking `EXPOSE` for publishing a port.
7. Supply `SPRING_PROFILES_ACTIVE`, environment variables, `JAVA_TOOL_OPTIONS`, and mounted Secrets/`configtree:` **at runtime**, without baking secrets into artifacts.
8. Distinguish startup/liveness/readiness probes, `server.shutdown=graceful`, `SIGTERM`, `preStop`, and the `terminationGracePeriodSeconds` limit.
9. Run the Maven Spring Boot project, test via JUnit real random port, build a Docker image, author reference Deployment/Service manifests, and verify API/health across environments.
10. Follow an investigation checklist for `UnsupportedClassVersionError`, `no main manifest attribute`, `ImagePullBackOff`, `CrashLoopBackOff`, `OOMKilled`, readiness failures, proxy 502s, and graceful termination failures.

## 2. Responsibility Map from Source Code to HTTP Response

~~~text
Git commit / source code
       |
       v
[1] MAVEN / GRADLE
    resolve deps -> compile -> test -> package
       |
       v
Executable JAR/WAR (application + Boot loader + libraries)
       |
       v
[2] IMAGE BUILDER: Dockerfile or Cloud Native Buildpacks
    JRE/OS libraries + artifact + image entrypoint + layers
       |
       v
OCI image: registry/repository@sha256:digest
       |
       v
[3] DEPLOYMENT PLATFORM: Docker/Kubernetes/PaaS
    pull image, schedule instances, inject config/secrets,
    mount storage, set networking/probes, resources/limits,
    route traffic, restart/scale/rollout
       |
       v
[4] RUNTIME: JVM + Spring Boot + embedded server
    start, bind config, listen on port, handle HTTP,
    check health, send logs, receive SIGTERM, shut down
       |
       v
HTTP client / downstream services
~~~

A deployment is not a single atomic step. Maven finishing a build does not guarantee Kubernetes pulled the image; building a Docker image does not guarantee healthy startup; a Pod showing `RUNNING` does not prove users can call the API; HTTP 200 on localhost does not prove public TLS, DNS, proxy headers, or security are right.

### 2.1. “Who Owns This Failure?” Matrix

| Behavior/configuration | Primary owner layer | Coordinating layer |
| --- | --- | --- |
| Java compiler target, annotation processors | Maven/Gradle + build JDK | Developer/CI |
| Dependency versions/upgrades | Build configuration | Security/SBOM tooling |
| Nested libraries, executable manifest | Boot Maven/Gradle plugin | Runtime classpath/launcher |
| JRE version, CA store, Linux packages | Base/runtime image, PaaS runtime | JVM/application |
| JVM heap, GC, native memory | JVM flags/runtime | Container resource limits |
| HTTP listen port | `server.port` and embedded web server | Docker port publishing, Kubernetes Service |
| Public domain/TLS certificate | Ingress/LB/proxy | Application forwarded-header handling |
| Database URL and secret mount | Platform configuration | Application binding/connection |
| Liveness/readiness semantics | Application/Actuator | Kubelet and Service routing |
| Replica count, rollout strategy | Kubernetes controller | App statelessness/compatibility |
| `SIGTERM` and grace deadline | Container/orchestrator | Boot graceful shutdown |
| Event durability/replay | Application + database/message broker | Restart and rollout policies |
| Image digest/signature/pull | CI/registry/cluster policy | Builder and deploy pipeline |

A single incident can span multiple layers. For example, a public 502 might come from an ingress picking the wrong `targetPort`, an unready Pod, Tomcat not listening yet, or an OOM crash. Trace client → edge → Service → Pod → JVM instead of immediately editing the business controller.

### 2.2. Five Concepts That Do Not Substitute for Each Other

- **Build artifact**: compiled classes, resources, and dependency metadata/JAR.
- **Executable Boot archive**: repackaged artifact containing the Boot loader and dependencies for `java -jar`.
- **OCI image**: filesystem layers, runtime/JRE, entrypoint, and image metadata used by container runtimes.
- **Container/Pod**: running instance constrained by OS, namespaces, cgroups, env, mounts, and networking.
- **Deployment/Service/Ingress**: desired state and traffic routing; they are neither Java artifacts nor source code modifiers.

## 3. Spring Boot Runtime Requirements Differ from Build Requirements

Per Spring Boot **4.1.2** documentation, runtime requires at least **Java 17**; build support covers Maven **3.6.3+** and Gradle **8.14+ (8.x line)** or **9.x**. Spring Boot also specifies matching Spring Framework/Servlet container requirements; on the Servlet stack, Tomcat 11 and Jetty 12.1 are supported embedded containers per system requirements.

The Maven version is not a requirement on the **machine running an executable JAR**. A compatible JRE/JVM is what `java -jar` needs. Conversely, a server with JDK 17 and no Maven still runs a pre-built JAR; a build agent with JDK 21 compiling for Java 17 still needs verification of dependencies and standard APIs.

### 3.1. Compiler vs Runtime JVM

~~~text
CI: JDK 21 + compiler --release 17
                |
                v
Java class file target 17 (major 61)
                |
        +-------+--------+
        |                |
JVM Java 17           JVM Java 21
can run               usually works
        |
JVM Java 11 -> CANNOT run Java 17 bytecode
~~~

`javac --release 17` locks language level, bytecode version, and Java standard APIs to release 17. Setting only `-source 17 -target 17` on a newer JDK can accidentally invoke Java 21 APIs and fail in production.

Create a standalone Java 17 program:

~~~java
public class RuntimeFeature {
    public static void main(String[] args) {
        System.out.println("Target feature: 17");
        System.out.println("Runtime feature: "
                + Runtime.version().feature());
    }
}
~~~

Run:

~~~bash
javac --release 17 RuntimeFeature.java
java RuntimeFeature
~~~

When genuinely running on JVM 17, stdout is:

~~~text
Target feature: 17
Runtime feature: 17
~~~

On JVM 21, the second line will read `Runtime feature: 21`. This checks the running JVM rather than replacing Maven's compiler target. When hitting `UnsupportedClassVersionError`, inspect **which class** has a bytecode version newer than the JVM: it may be a dependency rather than your main class.

### 3.2. Runtime Contract to Document Explicitly

| Field | Example for a service | How to verify |
| --- | --- | --- |
| Java feature | Java 17+ | `java -version` inside the image |
| OS/architecture | Linux AMD64/ARM64 per image support | Image manifest and node architecture |
| Entrypoint | `java -jar /app/application.jar` | Docker/OCI inspect |
| Inbound port | TCP 8080, listener on Pod interface | `server.port`, curl inside namespace |
| Required configuration | Release, region, DB URL, retry timeouts | Environment/config validation |
| Sensitive configuration | Credentials, private keys, trust config | Secret mount/RBAC/rotation |
| External services | DNS, TLS, DB/broker identity | Connectivity/credentials, app health |
| Resource assumptions | CPU, memory, threads, file descriptors, temp disk | cgroups/limits and load testing |
| Startup/health | What startup, live, and ready mean | Main-port probes |
| Shutdown | `SIGTERM`, deadline, and in-flight policy | Rolling restart/fault testing |
| Durable state | DB/object storage/queue, never ephemeral disk | Restart/failover testing |

**Portable Java bytecode does not mean an OCI image is unconditionally portable.** JNI/native libraries, TLS providers, fonts, OS/ABI, CPU architecture, and libc differ between AMD64/ARM64 and Linux distributions. GraalVM native binaries are even more tightly bound to OS/architecture.

### 3.3. Runtime CPU and Memory Are More Than the Java Heap

Suppose a Pod memory limit is 512Mi. Setting `-Xmx512m` can get the process `OOMKilled` because Metaspace, code cache, thread stacks, direct buffers, TLS/Netty buffers, native allocations, and GC metadata also consume memory. JVM 17 detects container limits, yet you must still measure RSS, allocation rates, and GC within real limits.

Illustrative setting:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+ExitOnOutOfMemoryError"
~~~

60% is a starting point for testing, **not** a universal preset for every app. `JAVA_TOOL_OPTIONS` affects the JVM at launch; it does not change the JDK binary, compiler target, or Kubernetes memory limit. With Buildpack images, the launcher may set its own `JAVA_TOOL_OPTIONS`; avoid overwriting it carelessly.

## 4. What Do Maven/Gradle Do in the Artifact Lifecycle?

Maven/Gradle resolve dependencies, compile, copy resources, run unit/integration tests, package JARs/WARs, and invoke the Boot plugin to repackage or build images. Inside the running production JVM process, Maven/Gradle **do not** run dynamically to fetch missing dependencies or inject secrets.

### 4.1. Spring Boot Executable JAR

Simplified layout:

~~~text
runtime-boundary-lab-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/
│   └── com/example/runtimeboundary/...
├── BOOT-INF/lib/
│   ├── spring-*.jar
│   └── ...
└── org/springframework/boot/loader/...
~~~

The Boot Maven plugin's `repackage` goal turns an archive into an executable JAR with nested dependencies. The manifest sets `Main-Class` to the Boot launcher and `Start-Class` to your app class. Do not merely set `Main-Class=com.example.App` in the Maven JAR plugin expecting a standard JVM to load nested JARs automatically.

~~~bash
mvn clean verify
jar tf target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

If you hit `no main manifest attribute` or `ClassNotFoundException`, verify Boot repackaged the archive and included nested libs; never install Maven inside the production image as a workaround.

### 4.2. What Each Maven Command Proves

| Command | What it verifies | What it **does not** verify |
| --- | --- | --- |
| `mvn compile` | Source compiles | HTTP listener/TLS, probes |
| `mvn test` | Tests pass under build config | Real image/Kubernetes |
| `mvn verify` | Lifecycle passes through verify | App will become Ready in prod |
| `mvn package` | Produces artifact | Image was pushed |
| `mvn spring-boot:run` | Dev runtime via classpath/plugin | Executable JAR layout |
| `mvn dependency:tree` | Dependency graph | Vulnerability policy passed |
| `mvn spring-boot:build-image` | Builds OCI image via buildpacks | Pod/Service/Ingress exist |

If a pipeline passes `-DskipTests`, never claim tests passed just because packaging succeeded; require CI evidence from an actual test step.

### 4.3. Gradle and Equivalent Boundaries

~~~bash
./gradlew test
./gradlew bootJar
./gradlew bootBuildImage
~~~

The Spring Boot Gradle plugin's `bootJar` creates the executable archive; the Java plugin's `jar` does not carry the same layout/launcher. `bootBuildImage` invokes Cloud Native Buildpacks. Gradle Wrapper/JDK compatibility is a **build-time** concern; do not assume `gradle` must be installed in the runtime image once an executable JAR exists.

### 4.4. WAR, External Servlet Container, and Native Image

- An executable JAR usually embeds Tomcat/Jetty/Netty per dependencies.
- A WAR can deploy into an **external servlet container**, where the container controls servlet version, connectors, classloaders, TLS, JVM, and undeploys. Proper packaging, `SpringBootServletInitializer`, and dependency scopes are required—not just changing `jar` to `war`.
- A GraalVM native image is an AOT-compiled binary and **does not run via `java -jar`** like a JVM archive. It needs the GraalVM toolchain, reflection/resource/proxy metadata, and OS/arch-specific testing.
- Native images still require runtime config, secrets, probes, DB schemas, image signing, and graceful shutdown.

## 5. OCI Images: Dockerfiles and Buildpacks Are Not Deployments

An **OCI image** bundles filesystem layers, entrypoint/command, environment metadata, and platform support. Docker can run an image locally or Kubernetes can pull it from a registry. An image does not create a Service, public hostname, Secret, database, durable storage, or autoscaler.

### 5.1. What Does a Dockerfile Do?

- Selects the base image/JRE/OS userspace.
- Copies the JAR and needed resources, sets working directory.
- Configures entrypoint, default env, and user/permissions.
- Structures cacheable layers and build arguments.
- Supplies metadata such as `EXPOSE`.

Never store passwords or per-environment configuration variants inside a Dockerfile. Never rely on floating base tags in production without a rebuild/scan/patch policy.

### 5.2. What Do Cloud Native Buildpacks Do?

Cloud Native Buildpacks (CNB) take an app/JAR along with builder/buildpacks/run images and build an OCI image through a structured lifecycle. Spring Boot's Maven goal:

~~~bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=runtime-boundary-lab:0.0.1
~~~

This goal requires a container builder/daemon and pull access to builder/run images. `BP_JVM_VERSION` picks the Java version at **image build time** (as supported by the buildpack), whereas `JAVA_TOOL_OPTIONS` applies when the JVM runs. The buildpack-provided launcher may inject its own runtime flags/defaults.

| Aspect | Dockerfile | Buildpacks |
| --- | --- | --- |
| Base JRE | Chosen via `FROM` | Determined by builder/run image |
| Image layers | Designed via `COPY`/extract | Managed by Buildpacks |
| Non-root user | Configured by you | CNB images default non-root |
| Build | `docker build` | `spring-boot:build-image`/`bootBuildImage` |
| Image registry | Pushed separately or by CI | Needs publish/registry credentials |
| Deployment | Not created | Not created |
| TLS/DB/Secrets/Ingress | Not supplied | Not supplied |

Both approaches can package **the exact same application code**, yet the runtime JRE, CA store, OS libraries, architecture, and launch flags can differ. Always smoke test the **actual built image**, not just the JAR.

### 5.3. EXPOSE vs Port Publishing

~~~dockerfile
EXPOSE 8080
~~~

`EXPOSE` is primarily image metadata; it does not change `server.port`, open host ports, or create a Kubernetes Service. Local Docker requires explicit publishing:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 \
  runtime-boundary-lab:0.0.1
~~~

The left `127.0.0.1:8080` is the **host** bind; the right `8080` is the **container** port. Spring Boot must listen on port 8080 on a reachable container interface. If Boot binds only `127.0.0.1` **inside the container**, Docker NAT from the host to the container IP fails to connect.

### 5.4. Image Identity and Architecture

~~~text
registry.example.test/team/app:prod      # tag may be mutable
registry.example.test/team/app:1.0.3     # version tags also need an immutability policy
registry.example.test/team/app@sha256:... # digest identifies exact content
~~~

Pin digests/immutable tags and store commit IDs, SBOMs, provenance, signatures, and scan results per policy. When running on ARM64 nodes, the image must provide a compatible ARM64 manifest/platform; portable Java class files do not make an AMD64 base image run natively on ARM64.

## 6. Configuration Is a Runtime Contract, Not Build-Time Text Replacement

Spring Boot supports externalized configuration via `application.properties`, YAML, OS env vars, JVM system properties, CLI flags, `spring.config.import`, and config trees. The standard goal is **build once → deploy the same image many times** with environment-specific configs/secrets.

~~~text
One immutable JAR/image digest
   +-- test:    release=abc123, region=ci
   +-- staging: release=abc123, region=stage
   +-- prod:    release=abc123, region=ap-southeast
          |
          v
Same app version, different runtime settings
~~~

### 6.1. Environment and Profiles

~~~properties
spring.application.name=runtime-boundary-lab
app.runtime.release=${APP_RELEASE:local}
app.runtime.region=${APP_REGION:dev}
server.port=${PORT:8080}
~~~

Spring placeholder `${APP_RELEASE:local}` uses `APP_RELEASE` when set and falls back to `local`. Docker/Kubernetes can inject env vars **without modifying the JAR**.

An alternative is direct relaxed binding: `app.runtime.release` can normally be overridden via OS env `APP_RUNTIME_RELEASE`. Pick **one convention**; avoid competing mechanisms whose precedence causes confusion. Spring Boot applies an ordered PropertySource hierarchy (CLI/properties/env/config data/test overrides)—there is no rule that “ENV always beats everything”.

`SPRING_PROFILES_ACTIVE=prod` merely activates matching profile configs; it **does not** automatically provide TLS, authentication, credentials, connection pools, or network policies.

### 6.2. Secrets Must Not Be Baked into JARs or Images

Avoid putting passwords in:

- `pom.xml` or committed `application-prod.properties`.
- `Dockerfile` `ENV DB_PASSWORD=...`, build args, or image history.
- CI logs/artifact metadata, Maven CLI arguments, or screenshots.
- Public Kubernetes ConfigMaps or commands dumping entire Pod environments.

Spring Boot supports mounted `configtree`:

~~~properties
# Fragment for a real application with a DB dependency:
spring.config.import=configtree:/run/secrets/myapp/
spring.datasource.username=${db.username}
spring.datasource.password=${db.password}
~~~

The platform mounts `/run/secrets/myapp/db.username` and `db.password`, and Spring imports them as configuration properties. When secrets are mandatory, let startup fail fast if missing rather than using `optional:` or dummy defaults. Even Kubernetes Secrets require RBAC, encryption-at-rest/secret-store policies, and rotation—having `kind: Secret` alone does not guarantee total security.

The datasource fragment above is **not run in the demo** because the lab project has no database. Updating a mounted secret file does not automatically reload already-bound Spring beans; rolling restarts or explicit reload mechanisms are needed.

### 6.3. Build Config vs Runtime Config

| Setting | Stage | Owner |
| --- | --- | --- |
| `java.version=17` | Compile/build | Maven compiler |
| `BP_JVM_VERSION` | CNB image build | Buildpacks |
| `JAVA_TOOL_OPTIONS` | JVM startup | JVM/image launcher |
| `SPRING_PROFILES_ACTIVE` | Spring app startup | Spring config loader |
| `PORT`/`server.port` | Spring server runtime | Embedded server |
| `containerPort` | Pod manifest | Kubelet/Service reference |
| `targetPort` | Service routing | Kubernetes networking |
| `terminationGracePeriodSeconds` | Pod lifecycle | Kubelet |
| `EXPOSE` | Image metadata | Dockerfile/image |

Never set `PORT` expecting a Kubernetes Service to rewrite itself. Never set `BP_JVM_VERSION` in a Pod manifest expecting the JRE binary inside the image to swap at runtime. Never set `JAVA_TOOL_OPTIONS` expecting `maven.compiler.release` to change.

## 7. Networking: Aligning Port Mappings Across Multiple Layers

~~~text
Browser: https://shop.example.test:443
           |
           v
Ingress/LB: TLS termination, host/path routing
           |
           v
Kubernetes Service: port 80
           |
           v
Pod targetPort: named http -> 8080
           |
           v
Spring Boot: server.port=8080, listening 0.0.0.0
~~~

- **Ingress/TLS** is configured by the platform. Public edge TLS does not guarantee the internal backend hop is encrypted.
- **Service port** is the Service's logical port.
- **`targetPort`** determines which Pod port receives traffic.
- **`containerPort`** is metadata/named-port declaration; it **does not force** the JVM to listen.
- **`server.port`** is the application setting that configures the embedded web server.
- **`server.address=127.0.0.1`** inside a container binds only loopback; usually wrong when Service traffic arrives at Pod IP.
- **`server.address=0.0.0.0`** or default is appropriate for container listeners; restrict external exposure via policies/firewalls.

### 7.1. Forwarded Headers Are a Trust Boundary

When Ingress terminates HTTPS and proxies HTTP to Boot, `request.isSecure()`/scheme, absolute redirects, and `Secure` cookies rely on `Forwarded` or `X-Forwarded-*`. `server.forward-headers-strategy=framework`/`native` interprets forwarded metadata, yet **does not verify** whether headers came from a trusted proxy.

The edge must strip incoming client-sent forwarded headers, rewrite canonical values from the real connection, enforce a `Host` allowlist, and block direct Internet access to backend ports. Test spoofed `X-Forwarded-Host` and `Forwarded: host=...` through the public edge rather than only localhost `curl`.

### 7.2. Outbound Dependencies Cannot Arbitrarily Use localhost

Inside a Pod, `localhost:5432` refers to **the Pod's own** network namespace, not a database on your laptop or another Pod. Runtime config needs managed DB/Kubernetes Service DNS, credentials, CA trust, network policies, retries/backoff, and connection pool budgets. Image builders do not provision databases or schemas; migrations carry their own ownership and rollback policies.

## 8. Lifecycle: Startup, Readiness, Liveness, Shutdown

### 8.1. Three Probes Ask Three Distinct Questions

| Probe | Meaning | Usage |
| --- | --- | --- |
| Startup | Has the app progressed enough in startup? | Prevents premature liveness kills during slow warm-up |
| Liveness | Is the app wedged/broken internally and needing restart? | Kubelet restarts after prolonged failure |
| Readiness | Can the app accept new traffic? | Service endpoint selection |

With Spring Boot Actuator, `management.endpoint.health.probes.enabled=true` enables liveness/readiness groups, and `management.endpoint.health.probes.add-additional-paths=true` exposes `/livez` and `/readyz` on the **main application port**. This prevents a separate healthy management port from hiding a dead main connector.

**Never make “DB down” an unconditional liveness failure:** a shared DB outage can restart every Pod simultaneously and cause a cascading failure. Use readiness or circuit breakers per SLO instead.

### 8.2. Graceful Shutdown Sits at the JVM–Orchestrator Boundary

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot 4.1 supports graceful shutdown on embedded web servers. It does not replace Kubernetes deadlines, `SIGTERM` forwarding, or durable state persistence. On shutdown, the app must receive `SIGTERM`, drop readiness, finish bounded in-flight requests, and handle long-lived SSE/WebSocket/streaming connections.

Kubernetes `terminationGracePeriodSeconds` includes `preStop` and graceful processing. If `preStop` sleeps 40 seconds inside a 30-second grace period, Java may be killed before shutdown hooks run. `SIGKILL` runs no Java hooks.

### 8.3. Exec-Form Entrypoint

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Exec form allows the container runtime to deliver stop signals directly to the JVM process. Shell form can block signal forwarding unless the shell uses `exec`:

~~~dockerfile
# Not recommended unless signal forwarding is handled:
ENTRYPOINT java -jar /app/application.jar
~~~

Boot's phase timeout **does not** guarantee the process always exits within that duration: other hooks, blocked I/O, threads, orchestrator deadlines, and external shutdown tasks still apply. Measure under load and test both `SIGTERM` and forced-kill recovery.

## 9. Complete Maven Example: One App, Multiple Environments

The project uses no database or cloud account, isolating runtime config and packaging boundaries. Java code **has no Docker/Kubernetes awareness**; the same JAR returns different responses based on runtime env vars.

### 9.1. Structure

~~~text
runtime-boundary-lab/
  pom.xml
  Dockerfile
  .dockerignore
  src/main/java/com/example/runtimeboundary/
    RuntimeBoundaryApplication.java
    RuntimeContractController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/runtimeboundary/
    RuntimeContractIntegrationTest.java
  k8s/
    deployment.yaml
    service.yaml
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>runtime-boundary-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Boot parent manages versions; the WebMVC starter includes embedded Tomcat, Boot Actuator provides health/probes, and the WebMVC test starter supplies Boot 4-compatible JUnit/test integrations.

### 9.3. RuntimeBoundaryApplication.java

~~~java
package com.example.runtimeboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeBoundaryApplication.class, args);
    }
}
~~~

### 9.4. RuntimeContractController.java

~~~java
package com.example.runtimeboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeContractController {
    private final String release;
    private final String region;

    public RuntimeContractController(
            @Value("${app.runtime.release}") String release,
            @Value("${app.runtime.region}") String region) {
        this.release = release;
        this.region = region;
    }

    public record RuntimeView(String service, String release, String region) {}

    @GetMapping("/api/runtime")
    public RuntimeView runtime() {
        return new RuntimeView(
                "runtime-boundary-lab", release, region);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Never dump all env/config into HTTP responses: they can leak tokens, secrets, and internal hostnames. The demo endpoint returns only harmless release/region strings. Production should restrict diagnostic endpoints and use Actuator `info` for allowlisted build metadata.

### 9.5. application.properties

~~~properties
spring.application.name=runtime-boundary-lab

server.port=${PORT:8080}
app.runtime.release=${APP_RELEASE:local}
app.runtime.region=${APP_REGION:dev}

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoints.web.exposure.include=health,info

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In containers, do not set `server.address=127.0.0.1`, because Kubernetes Service/Docker forwarding needs the app listening on the container interface. If both `PORT` and `SERVER_PORT` are set to different values, Spring PropertySources can produce unexpected results; stick to one convention.

### 9.6. RuntimeContractIntegrationTest.java

~~~java
package com.example.runtimeboundary;

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
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "app.runtime.release=ci-123",
        "app.runtime.region=ci",
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.probes.add-additional-paths=true"
    }
)
class RuntimeContractIntegrationTest {
    @LocalServerPort
    int port;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET().build();

        // Java 17 HttpClient does not implement AutoCloseable.
        HttpClient client = HttpClient.newHttpClient();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void environmentPropertiesReachRealHttpServer() throws Exception {
        HttpResponse<String> response = get("/api/runtime");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
                "\"release\":\"ci-123\""), response.body());
        assertTrue(response.body().contains(
                "\"region\":\"ci\""), response.body());
    }

    @Test
    void probesUseTheSameApplicationPort() throws Exception {
        assertEquals(200, get("/livez").statusCode());
        assertEquals(200, get("/readyz").statusCode());
    }

    @Test
    void businessEndpointWorks() throws Exception {
        HttpResponse<String> response = get("/api/ping");
        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

This is a **complete test class in Java 17**. `RANDOM_PORT` starts a real embedded server avoiding CI port collisions; `@LocalServerPort` captures the assigned port. The test verifies HTTP and config inside the test JVM, **not** Docker/Ingress/TLS. If the real app initializes external dependencies before becoming ready, add corresponding tests at the appropriate layers.

### 9.7. Build and Run the JAR

~~~bash
java -version
mvn -version
mvn clean verify
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Another terminal:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/livez
curl -i http://127.0.0.1:8080/readyz
~~~

The `/api/ping` response body is exactly:

~~~text
pong
~~~

With no env overrides, the `/api/runtime` data payload is:

~~~json
{"service":"runtime-boundary-lab","release":"local","region":"dev"}
~~~

JSON property ordering and headers may differ, yet all three field values are fixed by code. Health endpoints normally return 200 once ready; headers and health component details vary by config.

### 9.8. Run the Exact Same JAR with a Different Port and Config

Bash/POSIX:

~~~bash
APP_RELEASE=release-42 APP_REGION=staging PORT=8081 \
  java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Call:

~~~bash
curl -s http://127.0.0.1:8081/api/runtime
~~~

Expected body:

~~~json
{"service":"runtime-boundary-lab","release":"release-42","region":"staging"}
~~~

PowerShell:

~~~powershell
$env:APP_RELEASE = "release-42"
$env:APP_REGION = "staging"
$env:PORT = "8081"
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

No JAR rebuild is needed to change the port or region, though platform routing and probes must map to the new port as well. Do not launch two processes on 8080/8081 without stopping the first one.

## 10. Runtime-Only Dockerfile: Build Once, Run Anywhere

### 10.1. Dockerfile

~~~dockerfile
# Production should pin images by digest and apply controlled patches.
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --chown=10001:10001 \
  target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar \
  /app/application.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

This Dockerfile copies the already-built JAR without bringing Maven or compilers into the runtime container. It uses a numeric non-root UID; readable/writable paths must match permissions. Base image tags are mutable in practice; production pins digests, scans, and rebuilds on CVE/Java patches.

### 10.2. .dockerignore

~~~text
.git
.idea
.vscode
src
k8s
tls
secrets
.env
.env.*
target/*
!target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

These rules fit a Dockerfile copying only the pre-built artifact. If switching to a multi-stage Dockerfile compiling source, adjust `.dockerignore` so the builder can see `pom.xml` and `src`. Never send keys, `.env` files, or Git history into the build context unnecessarily.

### 10.3. Build the Image and Run

After `mvn clean verify`:

~~~bash
docker build -t runtime-boundary-lab:0.0.1 .

docker run --rm --name runtime-boundary-lab \
  -p 127.0.0.1:8080:8080 \
  -e PORT=8080 \
  -e APP_RELEASE=image-001 \
  -e APP_REGION=container-lab \
  --memory=512m --cpus=1 \
  runtime-boundary-lab:0.0.1
~~~

Another terminal:

~~~bash
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/readyz
docker logs runtime-boundary-lab
~~~

Expected body from `/api/runtime`:

~~~json
{"service":"runtime-boundary-lab","release":"image-001","region":"container-lab"}
~~~

If connections are refused, check whether Java is listening on 8080, `server.address` binds properly, `-p` matches, and the host port is free. Never infer from `EXPOSE 8080` that networking is automatically published.

### 10.4. Observability and Stop Signals in Containers

~~~bash
docker image inspect runtime-boundary-lab:0.0.1
docker inspect runtime-boundary-lab
docker logs runtime-boundary-lab
docker stats runtime-boundary-lab
docker stop --time 30 runtime-boundary-lab
~~~

`docker stop` sends a stop signal to PID 1, then kills after the timeout if still running. `--time 30` is Docker's command timeout, distinct from `spring.lifecycle.timeout-per-shutdown-phase=20s`. If APIs serve SSE/WebSocket/large requests, the app may need explicit drain logic prior to `SIGTERM`. Never claim the process always exits within 20 seconds.

### 10.5. Layered JARs and Image Optimization

Spring Boot provides layered archives and `tools` jarmode:

~~~bash
java -Djarmode=tools \
  -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar \
  list-layers
~~~

Boot metadata splits `dependencies`, `spring-boot-loader`, `snapshot-dependencies`, and `application`, optimizing Docker layer caching when source changes while dependencies stay stable. This optimizes **image builds/pulls**; it does not make runtime API logic any more accurate.

Modern Boot versions use `-Djarmode=tools` per current documentation; do not blindly copy legacy `layertools` commands from older guides.

## 11. Buildpacks: Different Image Builder, Same App Contract

~~~bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=runtime-boundary-lab:0.0.1
~~~

This goal uses a builder/run image and buildpacks to produce an OCI image without a Dockerfile. A Docker-compatible daemon and permissions are usually needed to run the plugin. The Spring Boot plugin infers the target Java version from compiler settings; `BP_JVM_VERSION` can override it intentionally on the builder.

Even with a buildpack image, **you must still test the runtime image**:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 \
  -e APP_RELEASE=buildpack-001 \
  -e APP_REGION=container-lab \
  runtime-boundary-lab:0.0.1
~~~

Different builder/runtime images may use different JVM flags, CAs, users/entrypoints, or layer layouts than your Dockerfile; inspect and health-check the real environment. Buildpacks **do not** create Kubernetes Services/Ingresses, registry credentials, signed digests, required secrets, or database migrations.

## 12. Kubernetes Implementing the Runtime Contract: Deployment and Service

The manifests below are a **reference structure**. `registry.example.test/team/runtime-boundary-lab:0.0.1` is an example name; build/push to a real registry and configure `imagePull` permissions before applying. No public Ingress/TLS is included because those depend on infrastructure and certificates.

### 12.1. k8s/deployment.yaml

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-boundary-lab
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: runtime-boundary-lab
  template:
    metadata:
      labels:
        app: runtime-boundary-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.test/team/runtime-boundary-lab:0.0.1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: PORT
              value: "8080"
            - name: APP_RELEASE
              value: "release-0.0.1"
            - name: APP_REGION
              value: "cluster-lab"
          startupProbe:
            httpGet:
              path: /livez
              port: http
            failureThreshold: 30
            periodSeconds: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: temp
              mountPath: /tmp
      volumes:
        - name: temp
          emptyDir: {}
~~~

Explanation:

- `replicas` and rolling strategy belong to the platform; the app must be stateless/backward-compatible enough to run multiple instances.
- `PORT=8080` → Spring placeholder → listens on 8080, matching named container port `http`.
- `startupProbe` prevents liveness kills during warm-up; `readinessProbe` controls traffic routing; `livenessProbe` triggers restarts.
- CPU/memory are cgroup/runtime constraints, not POM compiler settings.
- `runAsNonRoot`/read-only root filesystem harden the Pod; `emptyDir` at `/tmp` gives JVM/Tomcat temp space. Data in `emptyDir` does not survive Pod deletion.
- `terminationGracePeriodSeconds: 45` is the total deadline, including `preStop` if added; align it with actual app drain/hook timings.
- The image tag is for demo purposes; production should pin digests/immutability and enforce signature policies.

### 12.2. k8s/service.yaml

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: runtime-boundary-lab
spec:
  selector:
    app: runtime-boundary-lab
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

Service `port 80` routes to named container port `http=8080`. The Service does not provide public TLS or DNS. Add Ingress/Gateway/LoadBalancer and appropriate network/security policies for Internet traffic.

### 12.3. Deployment Commands Once Registry and Cluster Are Ready

~~~bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/runtime-boundary-lab
kubectl get pods -l app=runtime-boundary-lab
kubectl describe deployment runtime-boundary-lab
kubectl logs deployment/runtime-boundary-lab
~~~

To smoke test from an admin machine:

~~~bash
kubectl port-forward service/runtime-boundary-lab 8080:80
~~~

Another terminal:

~~~bash
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/readyz
~~~

`port-forward` does not prove public Ingress/TLS works; it simply tunnels through the API server to a Service-selected Pod for internal inspection. Likewise, `RUNNING` does not mean `READY`; check endpoints, probes, and events.

### 12.4. Common Platform Errors

- `ImagePullBackOff`: wrong image ref/digest, registry credentials/IAM, network unreachable, or mismatched architecture.
- `CrashLoopBackOff`: process exits repeatedly or liveness restarts; inspect previous logs/exit reason.
- `OOMKilled`: cgroup memory limit exceeded, including native off-heap memory.
- `Readiness probe failed`: wrong path/port, app still starting, DB/feature dependency, or resource pressure.
- `Connection refused` via Service: app bound `127.0.0.1` inside Pod, wrong listen port, or no ready endpoints.
- HTTP 502/503 from Ingress: unready backend pods, upstream routing/timeout/TLS errors, or bad ingress rules.
- Slow shutdown on `SIGTERM`: process misses signal, streams stay open, or insufficient grace period.
- Rolling deploy fails to shift traffic: wrong Service selector/labels, new Pods not ready, or external LB propagation lag.

## 13. Build Once, Deploy Many, and Supply Chain

Sample pipeline:

~~~text
Source commit/tag
  -> dependency resolution + compile/tests
  -> Maven executable JAR
  -> JAR smoke test
  -> OCI image build
  -> image smoke test + SBOM/CVE scans
  -> sign image / record immutable digest
  -> push into trusted registry
  -> stage deploy by SAME digest
  -> Service/Ingress/probe and business smoke tests
  -> promote SAME digest into production
  -> rolling/canary rollout, monitoring, rollback policy
~~~

**Build once** ensures the exact tested bytes promote across environments, changing only runtime config/secrets. If CI rebuilds separately for staging and production with baked-in passwords/URLs, each environment runs a distinct artifact lacking shared test evidence.

### 13.1. SBOM, Digest, and Provenance Are Distinct

- **SBOM:** inventory of components/dependencies/versions for license/CVE auditing.
- **Digest:** content-addressed image identity, preventing mutable-tag drift.
- **Signature/attestation:** binds the image to its publisher and build workflow.
- **Provenance:** records commit, builder, build parameters, and artifact origin.
- **Vulnerability scan:** flags library/JRE/OS CVEs per policy.

An image scanned clean today does not patch its JRE automatically tomorrow; rebuild, test, and roll out regularly. Signing an image does not prove business logic works—only distribution trust per policy.

### 13.2. Rollback Is More Than Swapping Tags

If a new release introduced an incompatible DB schema or event format, reverting to an older image can break data. Design expand–contract migrations, backward/forward compatible clients/consumers, idempotency/replay, and rollback rehearsals. Never treat local container ephemeral storage as a durable source of business truth.

## 14. Layer-by-Layer Troubleshooting

| Error | First layer to inspect | Action |
| --- | --- | --- |
| Maven dependency resolution fails | Build/repository | POM, repository credentials/network |
| Compiler JDK lacks API | Build/JDK target | `--release`, toolchains, dependencies |
| `UnsupportedClassVersionError` | Runtime JVM | Image Java version vs class bytecode version |
| `no main manifest attribute` | Packaging | Boot repackage, correct JAR |
| `ClassNotFoundException` | Archive/classpath | `BOOT-INF/lib`, exclusions |
| Docker `COPY` JAR fails | Build context | `mvn package`, `.dockerignore`, path |
| `exec format error` | Image architecture | `linux/amd64` vs `arm64`/native binary |
| `Permission denied` | Image user/FS | Numeric UID/GID, `COPY` permissions, volumes |
| `ImagePullBackOff` | Registry/cluster | Pull secrets, image digest/tag, network |
| `CrashLoopBackOff` | Runtime/health | `logs --previous`, exit code, liveness |
| `Address already in use` | Runtime connector | `server.port` and competing processes |
| Service returns connection refused | Networking | `targetPort`, app bind address, Pod endpoints |
| Pod `RUNNING` NotReady | Health/lifecycle | readiness, `startupProbe`, dependencies |
| `OOMKilled` | Runtime resources | Heap + off-heap RSS vs memory limits |
| Wrong redirect host/scheme | Edge/proxy | Forwarded headers/`Host` allowlist |
| Public TLS cert mismatch | Ingress/PKI | SNI, SAN, trust chain |
| 503 during deploy | Rolling/readiness/proxy | New Pod readiness, disruption budget, draining |
| Data lost on Pod restart | Stateful design | External durable DB/storage/replay |

### 14.1. Port Mismatch Scenario

CI packaging passes, image build passes, the Pod runs and logs “Started”. Yet Deployment has `PORT=9090`, `containerPort: 8080`, and Service `targetPort: http` pointing to 8080. Java listens on 9090 while the Service and probes hit 8080. **Fix the port contract**, not the controller or Maven plugin.

### 14.2. OOMKilled Even Though -Xmx Is Below the Limit

Heap is only part of RSS. Thread stacks, metaspace, direct buffers, native libraries, mmap, and GC add up. Inspect cgroup memory counters, JVM flags, GC/RSS, off-heap pools, Netty/Tomcat buffers, and in-flight requests; reduce queues/payloads or raise limits based on capacity instead of blindly tuning heap.

### 14.3. Liveness Restart Storm When DB Is Down

If liveness checks an external database, a DB outage restarts all Pods and floods the DB with reconnects during recovery. Base liveness on internal state, readiness on traffic readiness, and add circuit breakers/retries. Never “fix” it by deleting all probes.

### 14.4. Same Digest Yet Staging Passes and Production Fails

Compare config/secret references, DNS, CA/truststores, architecture, container limits, node policies, Ingress, DB migrations, clock/timezone, and outbound egress. Identical images guarantee artifact identity, **not** identical environments.

## 15. Release Contract Testing Matrix

| Test | Where? | Expected result |
| --- | --- | --- |
| Java 17 compile | CI | No newer APIs or bytecode |
| Executable manifest | CI | `java -jar` starts cleanly |
| Real HTTP port | JUnit `RANDOM_PORT` | `/api/runtime` and `/api/ping` pass |
| Env override | JAR runtime | `APP_RELEASE`/`APP_REGION` change responses |
| Port override | JAR runtime | `PORT=8081` listens on 8081 |
| Image smoke | Docker | Correct JRE, non-root, health passes |
| Image architecture | Registry/cluster | Image runs on target nodes |
| Image pull | Kubernetes | Pull succeeds with credentials/policy |
| Service routing | K8s | `/readyz` reachable via `targetPort` |
| Startup/liveness/readiness | K8s | Distinct semantics, no restart storm |
| Secrets | Staging | Missing required secret fails fast |
| TLS/Ingress | Staging | CA/SAN/SNI/redirects/headers valid |
| CPU/memory | Load test | No OOM, p99/GC within SLO |
| `SIGTERM` | Docker/K8s | Signal reaches JVM, bounded shutdown |
| Rollout/rollback | Staging | Capacity and schema compatibility preserved |
| Durable data | Chaos test | Restarts lose zero events/transactions |

**Crucial negative tests:** run on an older JVM, omit secrets, misalign ports, mount container rootfs read-only, use wrong image architecture, mismatch TLS hostnames, forge forwarded hosts, trigger CPU throttling, induce OOM, set readiness `REFUSING_TRAFFIC`, send `SIGKILL` mid-request, and briefly drop DB connectivity.

Not all of these fit inside `mvn test`: the JUnit lab only verifies Java/Spring against a real embedded server; platform tests require real images, registries, ingresses, DNS, TLS, and clusters.

## 16. Common Misconceptions

| Misconception | Correction |
| --- | --- |
| “Production must install Maven” | Runtime needs a JRE and packaged artifact/classpath |
| “`mvn package` passing means the Docker image is ready” | Building the artifact and building the image are separate steps |
| “Image build passing means the Service works” | Still requires image pull, Pods, probes, and routing |
| “`EXPOSE` opens a public port” | Metadata only; Docker `-p`/K8s Services route separately |
| “`containerPort` sets `server.port`” | No, both configs must be aligned |
| “Docker image = Deployment” | One is an artifact; the other is controller desired state |
| “Enabling the `prod` profile provides security” | Profiles do not replace auth, TLS, or secret policies |
| “Baking secrets into the JAR is convenient” | Never; inject at runtime and enforce access controls |
| “The `latest` tag is a fixed artifact identity” | Use immutable tags/digests |
| “Maven target Java 17 means JRE 17 image” | Build target and runtime JVM are separate contracts |
| “Java 17 bytecode runs on Java 11” | Older JVMs reject newer class file versions |
| “K8s Service auto-discovers the app port” | `targetPort`/`port` must still match |
| “Pod Running = Ready” | Health/availability have distinct semantics |
| “If DB is down, fail liveness” | Causes restart storms; consider readiness instead |
| “`-Xmx` equals a safe memory limit” | Off-heap/native memory also counts |
| “TLS at ingress encrypts the internal hop too” | Depends on backend TLS/network policies |
| “HTTP/2 in browser means Tomcat backend uses h2” | The edge may downgrade h2 → h1 |
| “`SIGTERM` always grants enough time” | Depends on entrypoint, grace period, hooks, and streams |
| “Native image is just converting JAR to exe” | Needs AOT/native build and compatibility testing |
| “Rolling back the old image completes the rollback” | DB/data/event/config compatibility still matters |

## 17. Production Deployment Checklist

### Artifact and Build

- [ ] Correct Java 17+ toolchain, managed dependency versions and CVEs.
- [ ] Tests execute before packaging; executable JAR manifest and nested deps verified.
- [ ] `java -jar` smoke tested on a runtime matching production's JVM.
- [ ] Buildpacks/Dockerfile use a verified base JRE, architecture, and provenance.
- [ ] No secrets or `.env` files baked into artifacts/images.

### Image and Supply Chain

- [ ] Non-root user, permissions, and writable temp clearly defined.
- [ ] JRE patches and base digest updates managed on a lifecycle.
- [ ] SBOM, CVE scans, signatures, and immutable image digests enforced.
- [ ] Image smoke tested before pushing/deploying.
- [ ] Exec-form entrypoint forwards `SIGTERM` cleanly.
- [ ] No reliance on `EXPOSE` to open firewalls or Services.

### Runtime Config and Networking

- [ ] `server.port` matches `containerPort`/`targetPort`/probes.
- [ ] Containerized app never binds loopback when Service inbound traffic is needed.
- [ ] Required config/secrets injected under exact names and fail fast if missing.
- [ ] Env/profile/ConfigMap/Secret precedence and reload behavior understood.
- [ ] Database DNS, TLS, credentials, and network permissions verified.
- [ ] Ingress TLS, forwarded headers, redirects, and `Host` allowlists tested.
- [ ] No sensitive Actuator endpoints exposed publicly; logs contain no secrets.

### Kubernetes / Lifecycle

- [ ] Startup/live/ready probes match their responsibilities on the main port.
- [ ] CPU/memory requests/limits load tested with heap/off-heap headroom.
- [ ] Rolling strategy maintains healthy capacity with `PodDisruptionBudget` where needed.
- [ ] `SIGTERM`, `preStop`, and shutdown grace deadlines are consistent.
- [ ] Durable state never relies on local container ephemeral filesystems.
- [ ] Image rollouts/rollbacks have smoke tests, schema compatibility, and metrics.
- [ ] Runbooks exist for `ImagePullBackOff`, `OOMKilled`, NotReady, and proxy 502s.

## 18. Self-Check Questions with Answers

**1.** Maven produces an executable JAR—does production need Maven installed?

**Answer:** No. With a compatible JRE and properly packaged archive, `java -jar` is sufficient to launch the application.

**2.** Do Buildpacks automatically create Kubernetes Services and databases?

**Answer:** No. Buildpacks produce an OCI image; platform/manifest/service owners handle routing, secrets, and external dependencies.

**3.** `server.port=9090` while Service `targetPort=8080`—where is the bug?

**Answer:** Mismatch between the runtime listener and platform routing contract. Fix config/Service, not the business controller.

**4.** Does Docker `EXPOSE 8080` make the app reachable from Internet browsers?

**Answer:** No. Port publishing, network access, and Ingress are required; `EXPOSE` is metadata only.

**5.** Why smoke test the image even when the exact same JAR already passed tests?

**Answer:** Runtime JRE, CAs, OS libraries, architecture, permissions, entrypoint, and JVM flags can differ from the build machine.

**6.** Why is `--release 17` safer than `-source`/`-target 17`?

**Answer:** It also restricts Java standard library APIs to Java 17, preventing accidental use of newer APIs when compiling on a newer JDK.

**7.** Does `SPRING_PROFILES_ACTIVE=prod` automatically secure secrets and TLS?

**Answer:** No. A profile selects defined configuration; security and secret management must be designed and provisioned separately.

**8.** Should database connectivity unconditionally fail liveness?

**Answer:** No. Shared DB outages would restart all Pods simultaneously; design readiness, health groups, and circuit breakers around recovery semantics.

**9.** Why can `-Xmx512m` trigger `OOMKilled` inside a 512Mi Pod memory limit?

**Answer:** The JVM also uses metaspace, native/direct memory, thread stacks, GC metadata, and buffers outside the heap; cgroups account for total memory.

**10.** When a Kubernetes Secret updates, does the app always pick up the new value immediately?

**Answer:** No. Process env vars never update dynamically; mounted files may update, yet already-bound beans do not necessarily reload. A lifecycle/rotation policy is needed.

**11.** Does a Pod in `RUNNING` yet not `READY` state mean compilation failed?

**Answer:** Not necessarily. Check probes, ports, startup, dependencies, CPU/RAM, config, and platform routing.

**12.** Does public HTTPS guarantee backend Pods terminate TLS?

**Answer:** No. Ingress may terminate HTTPS and proxy HTTP/1.1; protect internal hops according to your threat model.

**13.** How do digests and image tags differ?

**Answer:** A digest identifies exact content; a tag can be repointed to a different digest if the registry allows overwrites. Deploying by digest/immutable tags prevents drift.

**14.** Is rolling back to an older Docker image guaranteed safe?

**Answer:** No. DB schemas, event formats, and runtime configs may have changed. Migration/compatibility/rollback tests are essential.

**15.** What is the minimum Java version required by Spring Boot 4.1.2?

**Answer:** Java 17, though other dependencies in your app may raise the effective minimum.

## 19. Official References

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
- [Spring Boot — Installing and Running](https://docs.spring.io/spring-boot/installing.html).
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html).
- [Spring Boot Maven Plugin — Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html).
- [Spring Boot — OCI Images with Cloud Native Buildpacks](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).
- [Spring Boot — Dockerfiles and Layering](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html).
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html).
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- [Spring Boot — Deploying to the Cloud](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html).
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
- [Kubernetes — Services and Networking](https://kubernetes.io/docs/concepts/services-networking/service/).
- [Kubernetes — Liveness/Readiness/Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- [Kubernetes — Managing Container Resources](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [OCI Image Specification](https://github.com/opencontainers/image-spec).
- [Cloud Native Buildpacks — Concepts](https://buildpacks.io/docs/for-platform-operators/concepts/).
- [OWASP — Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html).

**Conclusion:** Maven/Gradle produce the **artifact**, Dockerfiles/Buildpacks produce the **runtime image**, the platform supplies the **environment, traffic routing, replicas, resources, and lifecycle**, and the JVM + Spring Boot execute the application. Deployment mastery starts with the **runtime contract**: Java 17+, classpath, settings/secrets, ports, probes, TLS/proxies, CPU/RAM, shutdown, and durable state. **Build once, test both the artifact and the image separately, promote by digest, and measure inside the real deployment environment** before concluding a release is production-ready.