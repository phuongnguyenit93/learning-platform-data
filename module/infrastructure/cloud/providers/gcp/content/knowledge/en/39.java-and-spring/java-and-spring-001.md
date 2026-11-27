# Choosing a JDK, Runtime, and Java Deployment Platform on GCP

A Java application that runs well on a development machine may not operate reliably when deployed to Google Cloud. The JDK used for compilation may differ from the runtime in the container; Spring libraries may not be compatible with a newer Java version; or the deployment platform may restrict the operating system, access permissions, or how the application receives requests. Choosing the right JDK, runtime, and platform reduces compatibility errors, simplifies operations, and preserves the ability to apply security updates.

Within the scope of **CLOUD_PROVIDERS_GCP**, this lesson places Java and Spring in the Google Cloud deployment picture—from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Learners will know how to choose a runtime based on the application lifecycle, package reproducible artifacts, select the right level of infrastructure control, and operate applications according to reliability, security, and cost requirements.

After this lesson, learners will be able to:

- Distinguish between JDK, JRE/runtime, JVM, Java distribution, and container base image.
- Choose a Java LTS version and JDK vendor based on support requirements, licensing, and patch cycles.
- Verify compatibility across JDK, Spring Boot, Maven/Gradle, libraries, and GCP platforms.
- Separate the build environment from the runtime environment and pin runtime versions.
- Choose Cloud Run, Cloud Run Jobs/functions, GKE, Compute Engine, or App Engine based on workload characteristics.
- Package Java/Spring Boot applications using Cloud Buildpacks or Docker.
- Configure the JVM, network ports, service accounts, secrets, logs, metrics, and traces to match the deployment environment.
- Plan JDK upgrades and platform migrations without causing service disruption.

## 1. Distinguishing JDK, Runtime, and JVM

Java terms are often used interchangeably in conversation, but they describe different components.

| Component | Role | Present in which stage? |
|---|---|---|
| JDK (Java Development Kit) | Development toolkit, including the **javac** compiler, debugger, packaging tools, and runtime | Build, test, and possibly runtime |
| JRE/runtime | Components required to run Java bytecode, including the JVM and runtime libraries | Runtime |
| JVM (Java Virtual Machine) | Executes bytecode, manages memory, garbage collection, JIT, and threads | Runtime |
| Java distribution | A JDK/runtime distribution from a specific vendor | Build/runtime depending on package |
| Container base image | Minimal operating system and runtime/libraries needed to run the application | Container runtime |

The JDK is typically used during the build stage because the compiler and testing tools are needed. Production containers may only need a JRE or a smaller runtime image. Separating the build image from the runtime image reduces image size, package count, and the container's attack surface.

Java bytecode is generated according to a class-file version. The runtime must understand the class-file version of both the application and its libraries. If compiled with a newer JDK without setting an appropriate target, the application may fail with **UnsupportedClassVersionError** when running on an older runtime. Conversely, setting a lower target does not automatically guarantee that newer libraries are compatible with an older runtime.

### 1.1. Choosing a Java LTS

Java releases feature versions on a six-month cadence; certain releases are designated Long-Term Support (LTS) by vendors with longer update and support schedules. As of November 2026, common LTS releases include Java 17, 21, and 25. Java 25 is a newer LTS; Java 21 remains a stable choice for many production systems; Java 17 is still supported on many platforms, though runtime support end dates for some GCP services arrive sooner.

| Version | Lifecycle position | Selection guidance |
|---|---|---|
| Java 25 | Current LTS, supported by many GCP runtimes | Suitable for new projects after confirming framework, library, and agent support |
| Java 21 | Widely deployed LTS | Suitable for production systems needing proven compatibility |
| Java 17 | Older LTS, still supported on many runtimes | For systems that cannot upgrade immediately; requires an upgrade plan |
| Java 11 and earlier | Many managed runtimes have ended deployment or are in legacy stage | Plan migration to a supported LTS version |

Do not choose a JDK based solely on the highest version number. Consider the Java versions supported by Spring Boot, frameworks, libraries, and agents; vendor patch schedules and support timelines; production licensing; CPU architecture, operating system, and native libraries; testing, observability, and rollback capabilities; and the runtimes supported by the target platform.

LTS is a lifecycle commitment made by a specific vendor or distribution under its own policy; it does not mean every vendor has the same support schedule. Read the roadmap of the exact JDK vendor chosen by your organization.

### 1.2. Choosing a JDK Vendor

Common OpenJDK distributions include Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, Red Hat OpenJDK, and Oracle JDK. They implement the same Java specification but may differ in installer packaging, update cadence, commercial support, certifications, licensing, and distribution format.

When evaluating a vendor, build a checklist:

1. **Support:** Are technical support, SLAs, and patch timelines suitable?
2. **License:** Do the terms of use and distribution fit your business model?
3. **Patch cadence:** How are security updates released and announced?
4. **Compatibility:** Are builds available for the Linux distribution, CPU architecture, and native dependencies in use?
5. **Supply chain:** Do images/packages provide signatures, checksums, SBOMs, and trustworthy distribution sources?
6. **Operations:** Does the operations team have standard procedures to update, test, and roll back?

Do not assume every package named OpenJDK carries the same support commitment. Record the exact vendor, version, and build number in your inventory, build metadata, or SBOM for traceability when vulnerabilities arise.

### 1.3. Checking Actual Versions

On a development machine or inside a container, run:

~~~bash
java -version
javac -version
./mvnw -version
./gradlew --version
~~~

The **java -version** command shows the runtime being invoked; **javac -version** shows the compiler if a JDK is present. Maven/Gradle may run on a different JDK than the one configured to compile source code. Check **JAVA_HOME**, toolchains, and build logs rather than relying on a single command.

## 2. JDK Compatibility with Spring Boot and Build Tools

The Java version must be chosen alongside Spring Boot, Spring Framework, Maven/Gradle, plugins, observability libraries, and dependencies with native components.

### 2.1. Spring Boot

Spring Boot defines minimum Java versions and compatibility ranges for each release line. As of November 2026, Spring Boot 4.0.x documentation specifies a minimum requirement of Java 17 and supports up to Java 27; Spring Boot 3.5.x requires at least Java 17 and supports up to Java 25. Check the exact patch release of the Spring Boot branch you are using, as build tool, Spring Framework, and container requirements can vary by version.

Points to review when upgrading the JDK:

- Do Spring Boot and Spring Framework support the target Java version?
- Are Maven/Gradle plugins and annotation processors compatible?
- Do logging, JDBC driver, ORM, serialization, and tracing libraries have compatible versions?
- Are any dependencies using deep reflection, internal APIs, or native libraries affected by the module system?
- Does the test suite depend on timezone, locale, charset, TLS, or GC behavior?
- Do the container image and GCP runtime support the required Java version?

Do not upgrade the JDK and Spring Boot simultaneously unless tests can isolate the root cause of failures. You can upgrade in two phases: keep the framework fixed to verify the JDK first, then upgrade the framework; or use a test matrix to evaluate both changes in a single controlled rollout.

### 2.2. Maven Configuration

With Maven, prefer the Maven Wrapper to pin the Maven version for the development team and CI. Use the **maven.compiler.release** property to set both API and bytecode targets:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

If the project uses the Spring Boot parent, check the Java properties used by the parent/plugins to avoid conflicting settings across **java.version**, **source**, **target**, and **release**. Do not just change JAVA_HOME and assume the compiler target changes accordingly.

Verify:

~~~bash
./mvnw -version
./mvnw -B clean verify
~~~

### 2.3. Gradle Configuration

With Gradle, use the Gradle Wrapper and Java toolchains to declare the JDK used for compiling and testing. For example:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}
~~~

Toolchains ensure the build picks the exact JDK rather than relying on the default JDK on the CI runner. Verify that the Gradle version and plugins are compatible with the selected Java version.

### 2.4. Upgrade Testing

A JDK upgrade test suite should include:

- Compilation and unit tests.
- Integration tests with databases, caches, message brokers, and external APIs.
- TLS, certificate, DNS, proxy, and JDBC tests.
- Startup, shutdown, graceful termination, and health check tests.
- Load/soak tests to observe GC, memory, threads, and latency.
- Verification of logs, metrics, traces, and security agents.
- Native image or JNI tests if used by the application.

Record a baseline before the upgrade: startup time, RSS memory, heap usage, GC pauses, throughput, p95/p99 latency, and error rate. Compare after the upgrade under the same workload.

## 3. Choosing a Java Runtime on Google Cloud

The runtime is the execution environment for the application. On GCP, you can use a Google-managed runtime or package Java yourself in a container or VM. Control increases from serverless platforms to Kubernetes and virtual machines, while operational responsibility shifts accordingly.

### 3.1. Current Managed Java Runtimes

According to Google Cloud's published runtime schedule as of November 2026, Java 25, 21, and 17 are available on the main managed runtimes below. Support schedules are subject to change; check the runtime support schedule before creating new systems or scheduling upgrades.

| Platform | Supported Java runtimes | Model |
|---|---|---|
| Cloud Run source deployments/buildpacks | Java 25, 21, 17 | Build source into a container and run as a service/job |
| Cloud Run functions | Java 25, 21, 17 | Functions Framework runtime for functions |
| App Engine standard gen2 | Java 25, 21, 17 | Managed runtime configured via app.yaml |
| App Engine flexible | Java 25, 21, 17 | Container on VMs managed by App Engine |
| GKE | Chosen by user in container image | Self-managed images, pods, and cluster mode |
| Compute Engine | Installed by user in VM or container | Self-managed OS, JDK, and processes |

Support dates for Java 25 and Java 21 on several GCP runtimes are published through October 2031 and September 2031, respectively; Java 17 on Cloud Run/buildpacks and App Engine standard has a published support date through October 2027. A support milestone does not mean the platform will automatically upgrade an application to a new major version. Application owners must plan version migrations before a runtime is deprecated or decommissioned.

### 3.2. Managed Runtime or Self-Managed Container?

**Managed runtimes** reduce the work of installing the JDK, patching the OS, and integrating with the platform. In return, the application must conform to the runtimes, buildpacks, configurations, and limits supported by the service.

**Self-managed containers** let you choose the JDK vendor, base image, native libraries, and startup command. In return, the team is responsible for rebuilding images, updating packages, scanning for vulnerabilities, managing registries, and testing the runtime.

Choose based on actual requirements:

- If the application is a standard HTTP, stateless Spring Boot service and does not need OS customization, Cloud Run is usually a straightforward starting point.
- If you need Kubernetes APIs, sidecars, a service mesh, network policies, or multiple coordinated container workloads, consider GKE.
- If you need OS admin privileges, specialized agents, custom filesystems, or long-running background processes, consider Compute Engine.
- If you want a code-centric application model tied to App Engine, check the limits of the standard or flexible environment.

## 4. Choosing a Deployment Platform

### 4.1. Cloud Run Services

Cloud Run runs containers in a managed model. It fits REST APIs, web services, Spring Boot backends, webhooks, and stateless HTTP applications.

Advantages:

- No cluster creation or VM management required.
- Scales with requests and can scale to zero when idle if configured.
- Built-in HTTPS endpoints, IAM, traffic splitting, revisions, and autoscaling.
- Deploy from source using buildpacks or deploy self-built container images.
- Configurable CPU, memory, concurrency, min/max instances, timeout, and ingress.

Design considerations:

- The application must listen on the port provided by Cloud Run via the PORT environment variable and bind to 0.0.0.0.
- Spring Boot can configure a default port of 8080 and map the environment variable when needed.
- Do not store sessions or critical files solely on the ephemeral instance filesystem.
- Do not assume a specific instance stays alive; requests may be routed to another instance or an instance may be stopped.
- Set concurrency according to the application's thread pool, connection pool, and memory capacity.
- Set maximum instances to protect databases and dependencies; set minimum instances when reducing cold starts is necessary.
- Design graceful shutdown, readiness, and SIGTERM handling.

Example application.yaml:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

If configuring a port other than 8080, read the value from the PORT environment variable. Do not expose all actuator endpoints to the Internet. Expose only necessary endpoints and restrict access appropriately. Connection pool sizes must be calculated across the total number of instances that may run concurrently.

Deploy from source:

~~~bash
gcloud run deploy orders-api --source . --region=asia-southeast1
~~~

This command uses Cloud Build and Google Cloud buildpacks to build a container image, store it in Artifact Registry, and deploy the service. This is a fast way to get started. If you need exact control over the base image, build arguments, SBOM, signing, or build stages, build the image separately with Cloud Build and then deploy the resulting image.

### 4.2. Cloud Run Jobs

Cloud Run Jobs are suited for workloads that run to completion rather than serving continuous requests:

- Batch imports/exports.
- Data reconciliation tasks.
- File processing or reporting jobs.
- Controlled migrations.
- Background jobs run on a schedule or triggered by a workflow.

A job runs a Java container and finishes with an exit code. You can configure task count, parallelism, timeout, retries, and task-specific environment variables. The application does not need to start an HTTP server if the job does not serve requests.

Do not use a Cloud Run service for long-running batch work if the workload is naturally a job with a clear start and end. Conversely, do not use a Job for an API that needs synchronous per-request responses.

### 4.3. Cloud Run Functions

Cloud Run functions fit a single function triggered by HTTP or events from other services such as Pub/Sub, Cloud Storage, or Eventarc. Java functions typically use the Functions Framework with a clear entry point.

Choose functions when the logic is narrow in scope, event-driven, and does not require a full Spring Boot web application. If you need multiple endpoints, filters, security chains, dependency injection, or large business workflows, a Spring Boot Cloud Run service may be easier to organize and test.

### 4.4. Google Kubernetes Engine

GKE fits when the organization already operates Kubernetes or the application needs high orchestration and customization capabilities:

- Multiple microservices and container workloads with independent lifecycles.
- Sidecars, service mesh, admission policies, or network policies.
- Stateful workloads or specialized operators.
- Control over node pools, accelerators, scheduling, and topology.
- Hybrid or multi-cluster setups per architectural requirements.

GKE Autopilot reduces node management and some infrastructure configuration responsibilities. GKE Standard offers deeper control over node pools, machine types, OS, and cluster configuration.

Java applications must be packaged into container images. A Deployment typically declares the image, resource requests/limits, probes, environment variables, service account, and autoscaling.

Simplified Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: app
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 500m
              memory: 768Mi
            limits:
              cpu: "2"
              memory: 1Gi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
~~~

This is a sample illustrating key fields. You must create an appropriate Service, Gateway/Ingress, or load balancer; configure probes accurately for the application; use immutable image tags or digests; and validate resource sizing via load testing. Do not set liveness probes too aggressively, which can cause the application to restart when simply handling high load.

When using GKE, account for CPU/memory requests, node capacity, pod IP ranges, cluster autoscaler, HPA, rollout surge, and Compute Engine quotas. Increasing pod replicas does not guarantee the cluster has node capacity available to schedule them.

### 4.5. Compute Engine

Compute Engine suits Java applications that require VM-level control:

- Legacy applications requiring OS-level agents or packages.
- Software requiring specific filesystem, process, or network configurations.
- Monolithic applications not yet ready for containerization.
- Long-running background workloads or licensing tied to VMs.

The operations team is responsible for installing the JDK, patching the OS, configuring systemd, firewalls, logging agents, monitoring, backups, and instance scaling. You can use Managed Instance Groups to deploy multiple VMs with autoscaling.

Avoid installing the JDK manually without a version management process. Use controlled image families or custom images, configure startup automation, and record the JDK vendor and build number. When updating, create a new image and deploy via rolling updates for easy rollback.

### 4.6. App Engine Standard and Flexible

App Engine has two environments for Java applications:

| Criterion | Standard environment | Flexible environment |
|---|---|---|
| Runtime | Google-managed Java runtime | Container on App Engine-managed VMs |
| OS control | Restricted to the runtime/stack | More flexible via Docker/buildpacks |
| Scaling | Optimized for fast scaling, can scale to 0 per config | Has minimum instances and scales per config |
| Best fit | Java web apps on supported runtimes | Apps needing custom runtimes/frameworks/libraries or containers |
| Responsibility | Less infrastructure management | More container and VM configuration |

With App Engine standard gen2, declare the runtime in app.yaml:

~~~yaml
runtime: java25

instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 20
~~~

Instance class and scaling values must be selected according to workload and current App Engine limits. The Java 25 runtime is a newer option on standard gen2; older Java 8/11 apps cannot always be migrated simply by changing the runtime field. Check APIs, libraries, and Jakarta/Java EE namespaces if the app uses servlets or legacy bundled services.

App Engine flexible is useful when you need custom containers and runtimes while keeping the App Engine deployment model. For new projects, compare it with Cloud Run and GKE, as container services can meet similar requirements with a different operational model.

## 5. Platform Decision Matrix

| Primary requirement | Platform to evaluate first | Reason |
|---|---|---|
| Stateless Spring Boot REST API | Cloud Run service | Managed containers, HTTPS, revisions, and autoscaling |
| Java batch job with a completion state | Cloud Run Jobs | Tasks, retries, timeouts, and parallelism |
| Event-driven function | Cloud Run functions | Function runtime and event integration |
| Microservices needing Kubernetes APIs, sidecars, or service mesh | GKE | Kubernetes orchestration and control |
| Legacy Java needing custom OS/agents | Compute Engine | Full VM and operating system control |
| Java web app wanting a managed code-centric runtime | App Engine standard | Managed runtime and fast scaling |
| Java needing custom containers within the App Engine model | App Engine flexible | Flexible runtime on VMs/containers |

There is no single best platform for every application. Choose based on workload, SLOs, network requirements, control level, operations team capabilities, platform cost, and time to release.

## 6. Packaging Java for GCP

### 6.1. Google Cloud Buildpacks

Buildpacks detect project structure, select the build process, and produce a container image. For Java, buildpacks support Maven and Gradle. Cloud Run source deployments can use buildpacks automatically without requiring developers to install Docker.

If the Java version is not specified, buildpacks may select the latest supported version. For reproducible builds, pin the JDK version in the repository.

Create project.toml:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "25"
~~~

The same configuration can be used when building with pack or Cloud Buildpacks. Check the runtime support schedule and builder stack before upgrading versions. Pinning the major version prevents new builds from unexpectedly switching to a different major version when the buildpack default updates.

### 6.2. Docker Multi-Stage Build

When you need control over the JDK vendor, OS packages, and runtime image, use a multi-stage Dockerfile. For example:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-25 AS build
WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN ./mvnw -B dependency:go-offline

COPY src/ src/
RUN ./mvnw -B clean package -DskipTests

FROM eclipse-temurin:25-jre
WORKDIR /app

RUN useradd --system --uid 10001 appuser
COPY --from=build /workspace/target/*.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is an illustrative template; verify that the specific image tag exists and is supported, pin digests in production pipelines, and adjust the JAR filename if the target directory contains multiple artifacts. In environments requiring tighter control, you can use a smaller JRE or distroless base image and run as a non-root user.

Principles:

- Use the JDK in the build stage and copy only necessary artifacts to the runtime stage.
- Do not copy .git, credentials, local config files, or secrets into the image.
- Update base images and rebuild when security patches arrive.
- Use .dockerignore to reduce the build context.
- Tag images with a version or commit SHA; do not rely on the latest tag.
- Scan images, store SBOMs and provenance, and sign images if required by your supply chain policy.
- Run as non-root and install only runtime packages that are genuinely needed.

### 6.3. Build Once, Deploy to Multiple Environments

Build the artifact once from a specific commit, then promote the exact same image digest through staging and production. Do not rebuild from source separately for each environment, as outputs may differ due to changed dependencies, buildpacks, or base images.

Runtime configuration such as project IDs, endpoints, feature flags, and resource names should be passed via environment/configuration systems. Fetch secrets from Secret Manager or an organization-approved secret mechanism; do not bake them into the image.

## 7. Configuring the JVM in Containers

The JVM must recognize container CPU and memory limits. A container with a 1 GiB memory limit does not mean all 1 GiB is available for the Java heap; the process also needs metaspace, thread stacks, direct buffers, JIT code cache, native libraries, and OS memory.

### 7.1. Heap and Memory Limits

You can configure the heap with -Xms/-Xmx or a RAM percentage such as -XX:MaxRAMPercentage. Do not set -Xmx equal to the container's memory limit, as the JVM and native components require additional off-heap memory.

Example:

~~~bash
java \
  -XX:MaxRAMPercentage=65 \
  -XX:InitialRAMPercentage=25 \
  -XX:+ExitOnOutOfMemoryError \
  -jar app.jar
~~~

These values are only starting points. Measure RSS, heap, metaspace, direct memory, thread counts, and GC in a production-like environment before finalizing. If a container is OOMKilled, examine both the memory limit and off-heap memory; simply increasing the heap can make the issue worse.

### 7.2. CPU, GC, and Startup

- Use profiling to determine whether the workload is CPU-bound or I/O-bound before changing the garbage collector.
- Monitor GC pauses, allocation rate, heap occupancy, and startup time.
- For scale-to-zero services, measure cold start and warm-up; consider min instances or startup CPU boost when appropriate.
- For applications with long JIT warm-up, compare latency on initial requests versus warmed-up requests.
- Verify shutdown hooks and request draining duration when the platform stops an instance.
- Avoid creating thread pools larger than the container's CPU and memory capacity.

Virtual threads introduced in Java 21 can be helpful for I/O-bound workloads with many blocking operations. They do not make CPU-bound code run faster and do not replace connection pool limits, backpressure, or timeouts. Test libraries and native calls before switching a Spring application to virtual threads.

### 7.3. Concurrency and Connection Pools

On Cloud Run, concurrency is the number of simultaneous requests a single instance can receive. A higher value can improve resource efficiency for I/O-bound applications, but increases memory, threads, connections, and latency when requests contend for resources.

With Spring Boot and HikariCP, calculate potential total connections:

\[
\text{Max DB connections} =
\text{Max instances} \times
\text{Pool size per instance}
\]

For example, 20 instances with a maximum pool size of 10 connections can open up to 200 connections. You must also add connections from jobs, migrations, admin tools, and other applications sharing the same database. Keep pools small enough and use timeouts/backpressure rather than allowing each instance to open too many connections.

## 8. Securing Identities and Application Configuration

### 8.1. Runtime Service Accounts

Java applications calling Google Cloud APIs should use the identity attached to the workload:

- Cloud Run: configure the service identity for the service.
- GKE: use Workload Identity Federation for GKE to map a Kubernetes ServiceAccount to Google Cloud permissions.
- Compute Engine: use the service account attached to the VM.
- App Engine: use the application's service account.

Do not embed service account JSON keys in JARs, Docker images, source code, or committed environment variables. Grant least-privilege roles on the exact project/resource—for example, read access to a single bucket or access to a specific secret.

### 8.2. Secrets and Configuration

Spring Boot supports multiple configuration sources including environment variables, config files, command-line arguments, and external configuration. Secrets must be managed separately:

- Store passwords, API tokens, and certificate private keys in Secret Manager.
- Grant Secret Accessor only on the secrets the service needs.
- Follow proper versioning and rotation procedures.
- Avoid logging secrets in logs, exceptions, trace attributes, or the actuator environment endpoint.
- Do not pass secrets in Docker build arguments or image layers.

With multiple environments, separate configuration by project and runtime identity. Ensure staging configuration cannot accidentally point to a production database.

### 8.3. Networking and Ingress

- Cloud Run: select internal, internal-and-cloud-load-balancing, or all ingress as needed; enable IAM authentication if the endpoint is not public.
- GKE: use appropriate Services, Gateways/Ingress, NetworkPolicies, and firewalls; restrict paths to the database.
- Compute Engine: place VMs in private subnets when appropriate, restrict firewall rules, and use IAP for administrative access.
- App Engine: check ingress, firewall rules, and connectivity paths to dependent services per environment.

Private IP alone does not protect a database if the service account or database credentials are overly permissive. Combine network controls with IAM, database authentication, and data-level authorization.

## 9. Observability for Java/Spring Applications

A production application needs logs, metrics, and traces so operations teams can detect and investigate incidents.

### 9.1. Logging

- Write structured JSON logs or a format compatible with Cloud Logging.
- Use appropriate severity levels; avoid logging every exception as INFO.
- Include a request ID or trace context to correlate logs with traces.
- Do not log passwords, tokens, personal data, or sensitive payloads.
- Write to stdout/stderr in containers if the platform collects logs that way; on VMs, configure an appropriate agent/collector.

### 9.2. Metrics and Health Checks

With Spring Boot Actuator and Micrometer, track:

- Request rate, error rate, and latency percentiles.
- JVM heap/non-heap, GC pauses, thread count, and process CPU.
- HikariCP active/idle/pending connections.
- Queue depth, cache hit ratio, and dependency latency.
- Container memory/CPU, instance/pod count, and restarts.

Expose health endpoints only to the extent needed. Readiness answers whether the application can accept traffic; liveness answers whether the process needs to be restarted. Do not use unstable external dependencies in liveness checks if doing so could trigger a restart storm.

### 9.3. Distributed Tracing

Use OpenTelemetry or compatible instrumentation to generate traces across services. Propagate W3C Trace Context over HTTP/RPC/message queues and include the trace ID in logs. When running on Cloud Run or GKE, ensure the exporter/collector has permission to write traces and can reach the endpoint.

### 9.4. SLOs and Alerting

Define SLIs/SLOs for latency, availability, and error rate. Alert on burn rate/error budget rather than alerting solely on a CPU threshold. Combine Cloud Monitoring dashboards with Logs Explorer and Cloud Trace to drill down from aggregate signals to individual requests.

## 10. Cost and Operational Models

Java costs on GCP depend on how the platform allocates resources, execution duration, networking, storage, logging, databases, and replica counts.

| Platform | Cost components to review | Considerations |
|---|---|---|
| Cloud Run | CPU/memory by usage, requests, minimum instances, network, and artifacts | Scale-to-zero saves money for intermittent traffic; min instances reduce cold starts but increase baseline cost |
| Cloud Run Jobs | CPU/memory per task and execution duration | Optimize parallelism and retries to avoid costly repeated runs |
| GKE Autopilot | Provisioned pod resources, network, storage, and supporting services | Easier to manage, but requires optimizing requests/limits and workload count |
| GKE Standard | Node VMs, cluster, disks, network, logging, and control plane per current pricing | Can optimize node utilization, but requires cluster management skills |
| Compute Engine | VM uptime, disks, network, licenses, and backups | Can be cost-effective for steady loads; team manages OS and patches |
| App Engine standard | Instance usage and resources per scaling/configuration | Fits code-centric apps; review min instances and scaling policies |
| App Engine flexible | VM/container capacity and minimum instances | Baseline cost can be higher during low traffic |

Do not choose a platform based solely on unit compute price. Factor in engineering operational time, HA costs, scale headroom, database connections, log retention, egress, and incident recovery time.

## 11. Decision and Deployment Roadmap

You can follow this sequence when bringing a Java/Spring application to GCP:

1. **Describe the workload:** HTTP service, event handler, batch job, or legacy app; define latency, throughput, state, and dependencies.
2. **Choose the JDK:** prefer an LTS with suitable remaining support; confirm vendor, license, security updates, and architecture.
3. **Check the framework:** verify Spring Boot, Spring Framework, Maven/Gradle, drivers, and agents against the JDK.
4. **Choose the platform:** Cloud Run for stateless HTTP; Jobs for batch; functions for event handlers; GKE for orchestration; Compute Engine for VM control; App Engine when a managed runtime model fits.
5. **Choose the build path:** buildpacks for simple source deployments; multi-stage Docker when image control is needed.
6. **Pin versions:** pin JDK major version, build tools, dependencies, and base images; record commit and image digest.
7. **Set up identity/network:** dedicated service account, least-privilege IAM, Secret Manager, and ingress/private networking.
8. **Configure runtime:** CPU/memory, JVM flags, concurrency, connection pools, startup, shutdown, and health checks.
9. **Test:** integration, load, failover, security scanning, and rollback.
10. **Operate:** dashboards, SLOs, logs/traces, patch cadence, and a JDK upgrade plan before runtime end-of-support.

### 11.1. Example: Spring Boot API on Cloud Run

Suppose an orders-api application uses Spring Boot, Maven, and Cloud SQL. The requirement is to serve an HTTPS API, scale with requests, and avoid managing Kubernetes.

Choices:

- Java 25 LTS after confirming Spring Boot/dependency support.
- Maven Wrapper and maven.compiler.release pinned in the repository.
- Google Cloud buildpacks with GOOGLE_RUNTIME_VERSION=25 or multi-stage Docker.
- Cloud Run service for the stateless API.
- Dedicated runtime service account with permission to connect to Cloud SQL and read the exact secret.
- Cloud SQL private IP/connector according to the chosen network architecture.
- Small HikariCP pool sized against the maximum instance count.
- Cloud Logging, Cloud Monitoring, and OpenTelemetry tracing.

Deploy from source to start:

~~~bash
gcloud run deploy orders-api \
  --source . \
  --region=asia-southeast1 \
  --service-account=orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=40 \
  --max=20
~~~

The CPU, memory, concurrency, and max instances values are only initial examples. Replace them using load test results, service limits, and Cloud SQL capacity. If using a self-built container image, replace --source . with --image IMAGE_URI and deploy the verified image digest.

### 11.2. Example: Spring Worker on GKE

If the application has multiple consumers, needs sidecars, network policies, and message processing schedules, GKE may fit better than a Cloud Run service. In that case:

- Package the Java runtime into a container image.
- Use a Kubernetes ServiceAccount and Workload Identity Federation.
- Set CPU/memory requests and limits based on profiling.
- Use HPA driven by CPU or custom metrics such as queue depth.
- Use PodDisruptionBudget and rolling updates to protect availability.
- Configure graceful shutdown so consumers stop accepting new messages and finish/ack messages currently in flight.
- Monitor nodes, pods, queue lag, database connections, and error rates.

## 12. Troubleshooting Common Issues

**UnsupportedClassVersionError.** The runtime is older than the class-file version of the application or a dependency. Check the build JDK, --release, java -version inside the container, and the runtime image.

**Application runs locally but fails to start on Cloud Run.** Check that the app binds to 0.0.0.0, listens on the PORT variable, completes startup within the limit, and does not rely on a local filesystem or separate daemon.

**Container is OOMKilled.** Check memory limit, heap, metaspace, direct buffers, thread stacks, and native memory. Do not simply increase -Xmx without measuring RSS.

**Cloud Run returns 503 errors under increased load.** Check startup/cold starts, max instances, concurrency, CPU allocation, readiness, and dependencies like the database. Scaling the app can exhaust downstream connection pools.

**GKE pod stuck Pending or restarting continuously.** Check resource requests/limits, node capacity, quotas, IP ranges, image pull, liveness/readiness probes, and container logs.

**Application cannot access Google Cloud APIs.** Verify the runtime service account, IAM roles, ADC, Workload Identity, and resource permissions. Do not work around this by embedding a JSON key in the image.

**TLS or JDBC errors after a JDK upgrade.** Check truststores, cipher/TLS policies, certificate chains, JDBC drivers, and native libraries. Run integration tests on the exact same runtime image.

**Build uses an unexpected JDK.** Check Maven/Gradle Wrappers, toolchains, JAVA_HOME, buildpack GOOGLE_RUNTIME_VERSION, and build stage logs.

**Spring Boot Actuator health reports DOWN even though the API works.** Check health groups, dependency checks, and readiness/liveness mappings. Do not let secondary dependencies cause liveness to fail repeatedly.

**Application runs fine but is missing logs/traces.** Check stdout/stderr, logging format, OpenTelemetry exporter, collector IAM permissions, and context propagation.

## 13. JDK and Platform Selection Checklist

### JDK and Framework

- [ ] Chosen a Java LTS version with suitable remaining support.
- [ ] Explicitly recorded JDK vendor, version, and build.
- [ ] Accepted the vendor's license/support policy.
- [ ] Confirmed Spring Boot/Spring Framework and dependencies are compatible with the JDK.
- [ ] Pinned Maven/Gradle Wrapper and toolchains.
- [ ] Ran compile, integration, load, and security tests after upgrade.

### Runtime and Platform

- [ ] Target GCP runtime remains supported for the required project lifetime.
- [ ] Selected Cloud Run, Jobs/functions, GKE, Compute Engine, or App Engine based on workload.
- [ ] Build runtime and production runtime are compatible.
- [ ] JDK/base image versions are pinned without relying on latest.
- [ ] Verified startup, port binding, health checks, and graceful shutdown.
- [ ] Sized CPU/memory, JVM heap, and connection pools based on load tests.

### Security and Operations

- [ ] Runtime uses a dedicated service account with least-privilege IAM.
- [ ] Secrets are retrieved from Secret Manager or an approved system.
- [ ] Image runs as non-root and is scanned for vulnerabilities.
- [ ] Logs, metrics, traces, and SLOs are in place.
- [ ] Periodic JDK/base image patching and rebuild process is established.
- [ ] Rollback and upgrade plan exists prior to runtime decommission date.

## 14. Official References

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Google Cloud Buildpacks Java](https://cloud.google.com/docs/buildpacks/java)
- [Google Cloud Buildpacks runtime support](https://cloud.google.com/docs/buildpacks/runtime-support)
- [Cloud Run runtime lifecycle](https://cloud.google.com/run/docs/runtime-support)
- [Deploy Java Spring Boot to Cloud Run](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Deploy source code to Cloud Run](https://cloud.google.com/run/docs/deploying-source-code)
- [Choose an App Engine environment](https://cloud.google.com/appengine/docs/the-appengine-environments)
- [App Engine standard Java runtime](https://cloud.google.com/appengine/docs/standard/java-gen2/runtime)
- [App Engine standard runtime support schedule](https://cloud.google.com/appengine/docs/standard/lifecycle/support-schedule)
- [App Engine flexible Java runtime](https://cloud.google.com/appengine/docs/flexible/java/runtime)
- [Compare GKE and Cloud Run](https://cloud.google.com/kubernetes-engine/docs/concepts/gke-and-cloud-run)
- [Google Cloud compute options](https://cloud.google.com/docs/compute-area/choose-compute-options)

Choosing a JDK and deployment platform is a decision tied to the application lifecycle. When the Java version, framework, build tools, container image, and runtime are pinned and tested together, teams can release Java/Spring applications on GCP consistently, apply security updates on time, and choose the level of infrastructure control that fits real needs.
