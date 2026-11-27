# Choosing an Azure Platform to Run Spring Boot Applications

A **Spring Boot** application can run on a personal computer with just the **java -jar** command. However, when deploying to Microsoft Azure, the development team needs to answer many questions: should we use **Azure App Service**, **Azure Container Apps**, **Azure Kubernetes Service (AKS)**, **Azure Functions**, or **Azure Virtual Machines**? How many replicas does the application need to scale to, can it stop when there is no traffic, does it need to access the database over a private network, and who is responsible for OS patching, autoscaling configuration, backups, observability, and incident response?

Choosing a platform is not simply about finding a service that supports Java. **The same Spring Boot JAR** may fit App Service for an enterprise web application, Container Apps for a containerized microservice, AKS for a Kubernetes system with complex operational requirements, or VMs when OS-level control is required. Each option distributes responsibility, cost, and automation levels differently.

This lesson belongs to the **Spring Boot on Azure** chapter of the **CLOUD_PROVIDERS_AZURE** module. Within the context of learning Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, data, monitoring, protection, and cost, we will build a **method for choosing a Spring Boot platform based on real requirements**, rather than picking a service simply because the name is familiar. The content includes comparisons, decision diagrams, configuration patterns, deployment strategies, scenarios, and hands-on exercises.

**Scope:** this is an architecture selection and design lesson, not a guide to arbitrarily creating production resources. Features, SKU names, JDK runtimes, scale limits, pricing, and lifecycles of Azure services change over time, by region, and by subscription. Verify official documentation and availability before finalizing an option. The numbers in the examples are explicitly marked as **hypothetical**, not actual SLA/pricing commitments or real benchmarks.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish between **PaaS, container PaaS, managed Kubernetes, serverless functions, and IaaS** operating models when hosting Spring Boot.
- Evaluate the five primary options: **App Service, Container Apps, AKS, Functions, and Virtual Machines**.
- Explain why **Azure Spring Apps** must be evaluated against lifecycle/retirement announcements before choosing it for new systems.
- Select a platform based on **workload type**, HTTP/background job requirements, scaling, cold start, OS requirements, and infrastructure autonomy.
- Compare **JAR/WAR artifacts** and **OCI container images**, along with their consequences for CI/CD.
- Analyze ingress/egress networking, VNet, private endpoints, managed identity, TLS, and secrets.
- Design health checks, graceful shutdown, resource limits, scaling, and connection pooling for Java.
- Build deployment workflows and rolling/blue-green/canary and rollback strategies suitable for each platform.
- Estimate **total cost of ownership (TCO)** rather than comparing only listed compute prices.
- Use a **weighted decision matrix** to justify choices for real-world cases.
- Write tests and runbooks that reduce risk when bringing Spring Boot to Azure.

## 2. Start from the Application, Not from the Service Name

Before looking for a **Create** button in the Portal, build an application profile:

| Question | Example answer | Impact on choice |
|---|---|---|
| What does the app serve? | REST API receiving 100 req/s | PaaS/container PaaS is an easy fit |
| Is traffic steady? | High during the day, near 0 at night | Autoscale/scale-to-zero is valuable |
| Are there long requests? | Uploads, reports taking several minutes | Timeouts, async processing |
| Is there in-process state? | HTTP session in RAM | Needs externalized session or sticky session with limits |
| Need native libs/OS control? | ffmpeg, specialized libraries | Container or VM depending on control level |
| How many microservices? | 2, 10, or 100 services | Complexity/Kubernetes trade-off |
| Already have a K8s ops team? | No | AKS may create high organizational overhead |
| Private data? | SQL/Redis via Private Endpoint | VNet ingress/egress and DNS |
| Latency requirements? | P95 under 300 ms | Cold start, CPU/RAM, region, DB |
| Cost constraints? | Fixed budget for lab environment | Must calculate fixed and variable costs |
| SLO/DR? | 99.9% with specific RTO/RPO | Multi-zone/region, runbooks, backups |
| Release cadence? | Small Java team, daily deploys | Managed platform and simple CI/CD |

**Business complexity does not automatically mean you must use Kubernetes.** A large monolith can still operate well on App Service. Conversely, a small microservice with batch/trigger characteristics may fit Azure Functions better than both App Service and AKS.

## 3. Azure Compute Models for Spring Boot

~~~mermaid
flowchart TD
    A[Spring Boot Application] --> B{Workload Pattern?}
    B -->|HTTP API/web, low ops| C[Azure App Service]
    B -->|Container services, event-driven autoscale| D[Azure Container Apps]
    B -->|K8s platform, deep control| E[Azure Kubernetes Service]
    B -->|Short event-driven tasks| F[Azure Functions Java]
    B -->|Specialized OS/kernel/native dependencies| G[Azure Virtual Machines]
    C --> H[Azure SQL/PostgreSQL/Cosmos, Key Vault, Monitor]
    D --> H
    E --> H
    F --> H
    G --> H
~~~

### Responsibility Breakdown

| Model | More managed by Azure | Still handled by the app team |
|---|---|---|
| **App Service (PaaS)** | Web hosting infrastructure, configured runtime platform, plan scaling | Java code, dependencies, config, health, scale policy, app security |
| **Container Apps (managed container app)** | Container infrastructure, ingress, revisions, various autoscaling capabilities | Docker image, CPU/RAM, secrets/identity, scaling rules, service communication |
| **AKS (managed Kubernetes)** | Kubernetes control plane and configured managed features | Worker nodes/node pools, manifests, ingress, cluster security, upgrades, observability |
| **Functions (FaaS)** | Function triggers/hosting runtime per plan | Function contract, bindings, dependency/cold start, retries, state |
| **VMs (IaaS)** | Underlying Azure compute host/hypervisor | OS patches, Java runtime, load balancer, deployment, HA, security, and autoscale |

Managed does not mean **zero operations**. The development team still owns application correctness, data management, dependency failure handling, endpoint exposure, and cost.

## 4. Quick Comparison of the Five Options

| Criterion | App Service | Container Apps | AKS | Functions | VMs |
|---|---|---|---|---|---|
| Typical artifact | JAR/WAR or container | Container image | Container image | Function package/container when supported | JAR/container as desired |
| Infrastructure self-management | Low | Low–moderate | Moderate–high | Low for function workloads | High |
| Long-running HTTP API | Very suitable | Very suitable | Very suitable | Suitable for endpoints/functions within hosting limits | Possible |
| Event/background workers | Possible, requires considering hosting/lifecycle | Good with jobs/queue scaling | Good if orchestration already exists | Very well suited to triggers | Possible |
| Scale-to-zero | Not default for dedicated plans | Supported depending on config/scale type and plan | Architecture-dependent, not equivalent to app-level zero | Available on appropriate plans | Not built-in |
| Kubernetes-level control | No | Abstracted | Yes | No | Self-managed if desired |
| Blue-green/canary | Slots/traffic routing per plan/feature | Revisions/traffic weights | Deployments/Ingress/service mesh | Slots/versions depending on hosting | Self-built |
| Private network/identity | Supported per plan/config | Supported per environment/network config | Supports VNet/workload identity | Supported per hosting plan | Full configuration control |
| Operational burden | Low | Low–moderate | Higher | Low–moderate | Highest |
| Fit for Java team with minimal DevOps | High | High if familiar with Docker | Requires consideration | High for event code | Usually low |

Cells describe **general tendencies**; they do not replace SKU/region support matrices. For example, deployment slots, private endpoints, autoscale types, or workload profiles may require paid plans or specific configurations.

## 5. Azure App Service: A Starting Point for Spring Boot HTTP APIs

**Azure App Service** is a PaaS web platform that can run Java applications on supported runtimes, including Spring Boot executable JARs on **Java SE** and Java/web application hosting options provided by the service.

~~~text
Client HTTPS
      |
      v
Azure App Service frontend / managed hosting
      |
      v
Spring Boot Java process
      |
      +-- Azure SQL / PostgreSQL
      +-- Key Vault / managed identity
      +-- Application Insights / Azure Monitor
~~~

### When to Choose

- The team has **a few REST APIs** or a Spring Boot monolith.
- You want to deploy a **JAR directly** without being forced to build containers yourself.
- You do not want to manage a Kubernetes cluster and node upgrades.
- You need CI/CD, app settings, custom domains, TLS, and health/diagnostics.
- Traffic is relatively predictable, with the ability to scale the plan when needed.

### Things to Remember About App Service Plan

An App Service app is hosted on an **App Service Plan** with an associated SKU, compute capacity, and resource limits. **Scale up** increases resources per instance, while **scale out** increases the number of instances; multiple apps sharing one plan can share compute and affect each other.

~~~text
App Service Plan: plan-enterprise
    |
    +-- app-support-api
    +-- app-admin-web
    +-- app-reporting

Shared plan compute:
  apps can contend with each other for CPU/RAM
~~~

**Creating three Web Apps on the same plan is not equivalent to three independent servers**. When sizing, consider total load and required isolation.

### Limitations to Evaluate

- An App Service Plan has a **baseline cost** depending on the SKU even when the app receives few requests.
- It does not automatically turn every long-running endpoint into a reliable background job.
- If special native libraries are needed, check runtime support or use a **custom container**.
- Networking, deployment slots, autoscale, and SLA depend on the plan/features.
- JVM heap configuration, connection pooling, file storage, and health checks are still managed by the application.

## 6. App Service: JAR, WAR, or Custom Container?

| Packaging format | Use when | Things to watch out for |
|---|---|---|
| **Executable Spring Boot JAR** | Spring Boot starts an embedded server | Choose a compatible Java SE runtime and JDK |
| **WAR deployment** | Application requires servlet container hosting | Verify Tomcat/runtime/version |
| **Custom container** | Need custom native dependencies or a packaged runtime | Manage Dockerfile, base image patches, registry |

### Executable JAR

~~~bash
# Illustrative run on a development machine
./mvnw -B clean verify
java -jar target/support-api.jar
~~~

This command assumes the Maven project already has **finalName=support-api** or the build produces that exact JAR name. With Gradle, the artifact name and commands differ; you cannot change the path without inspecting the actual project.

### Custom Container

Using App Service does not prohibit containerization. If the team already has an OCI image pipeline, **App Service for Containers** can be a middle ground between a PaaS experience and custom image requirements. However, this does not automatically provide Container Apps-style revisions or scale-to-zero.

### JVM Configuration

The application must select a JDK supported by the Azure hosting plan, configure resource settings, and provide **secrets via configuration/identity**, not hard-coded inside the JAR. When an app hits OOM, the cause may involve heap, metaspace, direct memory, threads, libraries, or data load; do not simply raise **-Xmx** past the plan's RAM.

## 7. App Service: Deployment, Health Checks, and Deployment Slots

Typical workflow:

1. Build and test the artifact in CI.
2. Create an App Service Plan/Web App with the appropriate Java runtime or custom image.
3. Enable managed identity, configure app settings, and set up database connectivity.
4. Deploy to a staging/slot when supported by the plan.
5. Smoke test **health/readiness, auth, and database connectivity**.
6. Swap/route traffic to production according to your availability strategy.
7. Observe errors, p95 latency, memory, and logs.
8. Safely roll back code/config if errors occur.

**Deployment slots** help test and swap versions when supported. However, **slot setting stickiness, connection strings, and identities** must be verified; swapping with misconfigured settings can cause staging to touch the production database or vice versa.

### File System and App Instances

Do not store **sessions, in-progress uploads, job state, or transactional data** exclusively on the local file system of a single instance if the app will scale out or restart. Use Azure Blob Storage/database/cache appropriately and design for idempotency.

### The Long-Running Job Problem

An HTTP request executing a 30-minute report may run into timeouts or proxy lifecycle limits. A better option:

~~~text
POST /reports
     |
     v
Spring Boot API
     |
     +-- Create job record
     +-- Enqueue Service Bus message
     |
     v
202 Accepted + jobId
     |
     v
Background worker / Functions / Container Apps Job
     |
     v
Blob report + status API
~~~

**Using App Service for an HTTP API does not force you to run every task inside the same web process.** Separating workers usually improves recoverability and load control.

## 8. Azure Container Apps: Container PaaS for Spring Boot

**Azure Container Apps (ACA)** is a platform for running containerized applications with a managed environment, ingress/service networking, and rich autoscaling capabilities based on HTTP and events through supported mechanisms.

~~~text
Client / Queue
       |
       v
Azure Container Apps environment
       |
       +-- Container app: orders-api
       |       revision v1 / revision v2
       |
       +-- Container app: notifications-worker
       |
       +-- Container Apps Job: nightly-import
       |
       v
Azure SQL / Service Bus / Key Vault
~~~

### When to Choose

- The team is comfortable with Docker/OCI images but **does not want to manage a Kubernetes cluster**.
- The application has multiple small microservices or background workers.
- Traffic fluctuates and needs **autoscaling by HTTP/queue/event**.
- You want **revision-based releases**, traffic splitting, or revision rollback.
- There are scheduled/event-driven jobs (use **Container Apps Jobs** when appropriate).
- Environment-level network/identity/secret management is needed.

### Components You Must Understand

| Component | Purpose |
|---|---|
| **Container Apps environment** | Managed hosting/network boundary for container apps |
| **Container app** | Application definition: image, ingress, env, scale |
| **Revision** | Immutable configuration version following revision semantics |
| **Replica** | A running container app instance at a given point in time |
| **Scale rule** | Condition to increase/decrease replicas; HTTP and external triggers per support |
| **Job** | Finite task run on a schedule or event, distinct from a long-running API |
| **Workload profiles / consumption** | Resource/cost options per environment/plan |

**Container Apps is a managed platform, yet it still runs a container image maintained by you.** You remain responsible for base image CVEs, build provenance, resource requests, application security, liveness/readiness, and service-to-service auth.

## 9. Container Apps: Scale-to-Zero, Cold Start, and Revisions

**Scale-to-zero** can reduce an app's replica count to 0 when there is no demand and the configuration supports it. This is advantageous for sparse workloads, but restarting a Spring Boot JVM from 0 takes time.

~~~text
No requests/queue events
       |
       v
Replicas: 0
       |
       | Request or event trigger
       v
Provision container + start JVM
       |
       v
Spring context / DB connection pool ready
       |
       v
Serve requests
~~~

### When Not to Scale-to-Zero

- APIs requiring low p95 latency even after quiet periods.
- Large Spring apps with long cold start, migrations, or slow cache warm-up.
- Persistent connections/WebSockets or assumptions of an always-running process.
- Incompatible traffic/triggers or queue consumers governed by different policies.

The solution is **minReplicas greater than 0** or an appropriate platform/capacity configuration. You must account for the cost of keeping replicas warm and the accompanying environment/network infrastructure; do not assume scale-to-zero means a zero bill.

### Revision Releases

Container Apps supports a revision lifecycle and **traffic splitting** in supported modes. When releasing a new image:

1. Create a candidate revision.
2. Smoke test readiness and external dependencies.
3. Allocate a percentage of traffic if supported.
4. Monitor errors and latency.
5. Shift remaining traffic or revert to the old revision.

**Traffic splitting does not guarantee database schema compatibility**. If the new release includes a destructive migration, rolling back the image will not restore a dropped column.

## 10. Container Apps: Ingress, Target Port, and Internal Communication

Spring Boot typically listens for HTTP on port **8080** when self-configured. In Container Apps, ingress needs to know the corresponding **targetPort**, and the application must bind on an appropriate address inside the container.

~~~text
Container Apps HTTPS endpoint
           |
           | Managed ingress
           v
Container targetPort=8080
           |
           v
Spring Boot process (0.0.0.0:8080)
~~~

Example application configuration:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0

spring:
  application:
    name: orders-api

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

**Actual property names must match the Spring Boot version** and packaging method. When running on App Service, do not blindly copy port 8080 from Container Apps while ignoring Java hosting runtime conventions.

### Internal vs. External Ingress

A service dedicated to internal APIs should use **internal ingress/private networking** when the environment allows. A public app needs TLS/domain, authentication, rate limits, and related network protections. **Selecting internal ingress alone does not replace OAuth/JWT or business authorization checks.**

### Dapr, KEDA, and Add-on Components

Container Apps offers integrations/features supporting **Dapr** and event-based scaling. Do not enable every component just because it is available; each sidecar/trigger adds learning curve, latency, resource consumption, and configuration overhead.

## 11. Azure Kubernetes Service: When You Need a Kubernetes Platform

**AKS** is appropriate when requirements demand Kubernetes concepts and ecosystem capabilities: Deployments, Services, Ingress/Gateway, Horizontal Pod Autoscaler, node pools, storage classes, network policies, operators, and various platform engineering tools.

~~~mermaid
flowchart LR
    U[Client] --> I[Ingress / Gateway]
    I --> S[Kubernetes Service]
    S --> P1[Spring Boot Pod A]
    S --> P2[Spring Boot Pod B]
    P1 --> D[(Azure SQL / PostgreSQL)]
    P2 --> D
    K[HPA / KEDA] --> P1
    K --> P2
~~~

### When AKS Pays Off

- The organization **already has a capable platform/Kubernetes operations team**.
- There are dozens or hundreds of workloads requiring standardized policies/platforms.
- You need **network controls, scheduling, node pools, sidecars, operators**, or complex workloads.
- There are GPU/specialized compute requirements suited to specific nodes/tiers.
- You want to leverage manifests/Helm/GitOps and the deep K8s ecosystem.
- There is a multi-service operations setup with SREs and cluster upgrade runbooks.

### When AKS Is a Burden

For **a single simple REST API with two developers**, AKS can demand too much work:

- Upgrading clusters/node images and handling compatibility.
- Managing ingress controllers, certificates, cluster DNS, and network policies.
- Operating HPA/cluster autoscaler/KEDA, storage, and secrets.
- Monitoring nodes, pods, scheduling, resource pressure, and logging.
- RBAC/Kubernetes service accounts/workload identity and supply-chain security.

**A managed control plane does not mean all worker nodes/cluster operations are managed by Azure to the point where no SRE effort is needed.**

## 12. AKS: Pods, Resource Limits, and Spring Boot Scaling

A Spring Boot pod includes:

- CPU and memory **requests/limits**.
- **readiness/liveness/startup probes** suited to startup behavior.
- **graceful shutdown** and a termination grace period.
- **HPA** to scale pods, and **cluster autoscaler** to scale node pools if needed.
- **Pod disruption budgets**, spread/affinity when HA is required.
- **workload identity** when accessing Azure services.

~~~text
Spring Boot Deployment
  replicas: 3
    |
    +-- Pod 1: CPU request 250m, memory request 512Mi
    +-- Pod 2: CPU request 250m, memory request 512Mi
    +-- Pod 3: CPU request 250m, memory request 512Mi
    |
    v
Service -> Ingress -> Clients
~~~

These requests/limits are **illustrative assumptions**, not standard sizing for every Spring Boot application. You must measure JVM **heap, non-heap, thread stacks, native allocations**, and application peak before setting limits.

### JVM and Memory Limits

Do not set **-Xmx=1GiB** and then set the container limit to exactly **1GiB**, because the JVM also uses metaspace, JIT/code cache, direct buffers, GC, threads, and OS overhead. With a container-aware JVM, you can use an appropriate **-XX:MaxRAMPercentage** and leave headroom; choose values via load tests.

### HPA Does Not Automatically Solve Dependency Bottlenecks

If 10 pods simultaneously open **50 DB connections per pod**, the database may receive 500 connections. Scaling from 10 to 50 pods can exhaust the connection limit. Design **connection pooling, backpressure, and caching** before increasing replicas.

## 13. AKS: Example Deployment and Service for Spring Boot

A containerized application can be deployed to AKS using a **Deployment** and a **Service**. Below is an illustrative YAML example for an image already built and pushed to an authorized registry:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: myregistry.azurecr.io/orders-api:1.0.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1024Mi"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - port: 80
      targetPort: 8080
~~~

**This is a conceptual example**, not a complete production manifest. You must replace the registry/image with a real image and configure image pull/workload identity, securityContext, topology spread, startup probes, ingress, HPA, budgets, and database secrets appropriately.

### Why Are Readiness and Liveness Separate?

- **Readiness** indicates whether the pod can accept requests right now; if it has not yet connected to a critical dependency or is still starting up, avoid sending traffic to the pod.
- **Liveness** should only detect unrecoverable process states, not continuously restart every pod when an external database has an outage.
- A **startup probe** is useful for slow-starting Spring Boot apps to prevent premature liveness kills.

The paths **/actuator/health/liveness** and **/actuator/health/readiness** require Spring Boot Actuator and health probes enabled for the right version. Do not just copy YAML without enabling endpoints or verifying HTTP responses.

### The Manifest Does Not Create a Public Endpoint Yet

A **ClusterIP** Service only exposes routing internal to the cluster. Public HTTPS requires an ingress/gateway/controller, domain, certificate, network controls, and authentication. A common mistake is changing the Service type to LoadBalancer and accidentally exposing management APIs publicly.

## 14. AKS: Helm, GitOps, and Platform Engineering

AKS shines when the organization has standardized workflows:

~~~text
Git: Spring Boot source + Dockerfile
        |
        v
CI build, scan, test, sign image
        |
        v
Azure Container Registry (ACR)
        |
        v
GitOps/Helm manifests with image digest
        |
        v
AKS cluster, multiple namespaces
        |
        v
Monitoring, policy, rollout controller
~~~

### Organizational Questions Before Choosing AKS

- Who manages Kubernetes version/upgrades and node images?
- Are cluster/team isolation, resource quotas, and namespace policies in place?
- Who manages ingress controllers, private DNS, and TLS certificates?
- Are GitOps, image scanning, secret management, and shared observability established?
- Are SREs on call for alerts and handling scheduling/eviction/cluster outages?
- Is the cluster dedicated to one application or shared across many workloads?

If the organization already operates AKS as a shared platform, the **marginal cost** of adding a Spring Boot service may be lower than standing up a new platform. Conversely, creating a dedicated cluster for a small API can increase TCO, recovery time, and maintenance overhead.

## 15. Azure Functions: For Event-Driven Java Functions

**Azure Functions** is a suitable choice if a Spring Boot application has **event-driven** processing parts, such as when a new file arrives, a queue receives a message, a timer fires, or a lightweight HTTP endpoint needs to invoke Java code.

~~~text
Azure Service Bus queue
          |
          v
Azure Functions Java
          |
          +-- Validate message
          +-- Execute application function
          +-- Write result to database
          |
          v
Complete/retry/dead-letter according to binding/host settings
~~~

### Do Not Confuse a Spring Boot Web App with a Java Function

A Spring Boot application with embedded Tomcat and dozens of REST controllers **does not automatically become a Function App just by deploying its JAR**. Azure Functions has its own **programming model, triggers/bindings, host lifecycle**, and integration libraries. There are ways to integrate Java/Spring Cloud Function into Azure Functions per supported versions, but this usually requires an **adapter/refactor**.

### When to Choose Functions

- Workloads are **event-driven** with durations/characteristics suited to the hosting plan.
- Processing Service Bus, Event Hubs, timers, or specific HTTP endpoints.
- You want to separate background processing from the Spring Boot API.
- Cold start on the corresponding plan is acceptable, or you choose a hosting plan with always-warm capabilities.
- You do not need to keep a JVM web server running continuously for the entire application.

### When Not to Default to It

- Large, stateful Spring MVC monoliths requiring a long-lived web-server lifecycle.
- HTTP requests taking tens of minutes without wanting to switch to async.
- Long-lived connections or unmanaged background threads.
- Timeout/cold start/hosting plan constraints that conflict with the SLO.

**Functions does not mean always free or infinitely scalable automatically.** Costs and features vary across consumption-based plans, Flex Consumption/Premium, and dedicated hosting according to current capabilities.

## 16. Azure Functions: Java Event Handler Example

A Java function reading a Service Bus message can be expressed as:

~~~java
package com.example.orders;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger;

public class OrderEventsFunction {

    @FunctionName("processOrderEvent")
    public void handle(
        @ServiceBusQueueTrigger(
            name = "message",
            queueName = "order-events",
            connection = "SERVICE_BUS_CONNECTION"
        ) String message,
        ExecutionContext context) {

        // Parse, validate, authorize where required, process idempotently.
        // Do not log sensitive message contents.
        context.getLogger().info("Order event received");
    }
}
~~~

This is a **skeleton** based on the Java Azure Functions SDK/annotations. It requires a project/plugin, the **azure-functions-java-library** Maven dependency, compatible binding extensions, host settings, and appropriate credentials/identity. **SERVICE_BUS_CONNECTION** is the binding configuration name, not a connection string value in source code. Production must handle duplicates, retries, dead-lettering, error mapping, and shared resources.

### Combining with App Service or Container Apps

You often do not have to choose **a single platform**:

~~~text
Spring Boot API on App Service
         |
         v
Service Bus queue
         |
         v
Azure Functions Java
         |
         v
Database / external business integration
~~~

This flexible choice can be simpler than running the entire system on AKS when only a few functions truly need event triggers.

## 17. Azure Virtual Machines: OS-Level Control

**Azure Virtual Machines** are suitable if the application must control the operating system, agents, native libraries, network stack, specialized Java environment, or has lift-and-shift requirements that cannot yet be containerized.

~~~text
Azure Load Balancer / Application Gateway
                 |
                 v
         Virtual Machine Scale Set
                 |
            +----+----+
            |         |
          VM A      VM B
       Java/Spring Java/Spring
            |         |
            +----+----+
                 |
                 v
         Database / storage
~~~

### Who Manages What?

The operations team carries significant responsibility:

- OS images, patching, security baselines, and endpoint protection.
- Installing/updating the JDK, process supervisor, and startup scripts.
- Load balancers, certificates, network security groups, and routing.
- Scale sets, availability zones, backups, and disaster recovery.
- Log shipping, disk capacity, monitoring agents, and incident response.

### When VMs Make Sense

- Legacy software/native agents that cannot run on PaaS/containers yet.
- Need kernel/OS/custom drivers or a specialized filesystem model.
- Specific licensing/infrastructure constraints requiring IaaS.
- The team has strong automation/patch management and a clear view of TCO.

**VMs are a deliberate choice, not a default "guaranteed to work" fallback**. If you only need to run a standard JAR, there are usually options with much less operational overhead.

### A Single VM Is Not HA

If everything sits on **one VM** and that VM or zone fails, the application stops. For availability, you must design multiple instances, load balancing, health checks, and data-layer HA; do not simply take an OS disk snapshot and call it a fault-tolerant architecture.

## 18. Azure Spring Apps: Service Lifecycle Note

**Azure Spring Apps** (formerly Azure Spring Cloud) previously offered a PaaS experience dedicated to Spring applications. However, Microsoft has announced a **retirement roadmap** for the service. For new architectures, you must **check current retirement notices, support timelines, new-creation eligibility, and migration guidance** before considering it.

### How to Decide

| Situation | Course of action |
|---|---|
| Building a **new** Spring Boot service | Prioritize evaluating App Service, Container Apps, or AKS based on requirements |
| Currently running Spring Apps | Inventory dependencies, networking, config, service bindings, and build a migration plan |
| Wanting built-in Spring conveniences | Examine replacing them with app/platform config, config services, and observability |
| Contracts requiring long-term supported platforms | Review official lifecycle and roadmaps; do not choose based on outdated articles |

### Do Not "Lift-and-Shift" Blindly While Ignoring Features

An existing system may rely on Spring Apps' **config management, service discovery, JVM metrics, managed certificates, build/deploy conventions, and autoscale**. Migrating to App Service/Container Apps/AKS requires mapping each feature, running regression tests, and adopting a new operating model.

Do not put a specific retirement date into a migration plan without cross-checking Microsoft's latest official announcements and organizational contracts.

## 19. Supporting Services: What Runs Spring Boot and What Does Not?

Not every Azure service that interacts with Java code is a direct web hosting platform:

| Service | Is it a primary host for a Spring Boot API? | Role |
|---|---|---|
| **Azure Container Registry** | No | Stores OCI images, serves build artifacts |
| **Azure API Management** | No | Gateway, auth policies, quotas, and API exposure |
| **Azure Front Door** | No | Global entry, routing, CDN/WAF per configuration |
| **Azure Application Gateway** | No | Layer-7 routing/WAF in network architecture |
| **Azure Service Bus** | No | Queues/topics between microservices |
| **Azure Cache for Redis** | No | Caching/sessions/transient data per suitable model |
| **Azure SQL/PostgreSQL/Cosmos DB** | No | Data stores |
| **Azure Key Vault** | No | Manages secrets/certificates/keys |
| **Azure Monitor/Application Insights** | No | Metrics, logs, traces |
| **Azure Static Web Apps** | Not default for a full Spring Boot web server | Frontend hosting and limited API integration |
| **Azure Container Instances** | Can run containers, not default for complex production APIs | One-off jobs, isolated runs, simple containers |

**Do not choose API Management or Azure Front Door instead of compute**: they sit in front of the backend and do not run the Spring Boot process.

## 20. Synchronous HTTP Workloads and Background Jobs

Many Spring Boot systems contain both HTTP controllers and **@Scheduled** tasks, Kafka/Service Bus listeners, or batch jobs. Running everything in the same process makes scaling prone to unintended side effects.

### Scenario

~~~text
Spring Boot orders-api
  +-- GET /orders
  +-- POST /orders
  +-- @Scheduled sendDailyInvoice()
~~~

If you scale from 1 to 5 replicas, **@Scheduled** may run 5 times unless there is distributed locking/leader election or a scheduler ensuring exclusivity. Even with a lock, sharing CPU/RAM with the API can cause latency spikes.

### Workload Separation Design

~~~text
Orders API:
  App Service or Container App
  HTTP ingress + auth + database
          |
          v
  Service Bus / durable job record
          |
          v
Worker:
  Azure Function or Container Apps Job / service
          |
          v
Database / Blob Storage / email
~~~

**Scaling HTTP by requests does not mean scaling workers by backlog.** Choose triggers and scale metrics per workload.

### Choosing Functions vs. Container Apps Job

- **Functions:** rich trigger/binding features, relatively short handlers suited to the hosting model.
- **Container Apps Jobs:** need to run a finite container on a schedule/event/manual trigger, convenient when the job already has a Docker image and clear lifecycle.
- **AKS CronJob/Job:** sensible if the whole platform already runs on AKS with scheduling/quota/monitoring policies.

Do not assume multi-hour jobs can run in every Functions plan; check **timeouts, hosting plans, checkpointing**, and idempotency.

## 21. Choosing an Artifact: JAR, OCI Image, and Build Supply Chain

Platform choice drives packaging strategy:

~~~mermaid
flowchart LR
    S[Git repository] --> B[Build Maven/Gradle + tests]
    B --> J[Spring Boot executable JAR]
    J --> A[App Service Java SE]
    J --> I[OCI image build]
    I --> R[Azure Container Registry]
    R --> C[Container Apps]
    R --> K[AKS]
    R --> P[App Service custom container]
~~~

### Benefits of JAR Deployment

- Does not force the team to know Docker if choosing App Service Java SE.
- Managed runtime image/Java hosting per the service's support matrix.
- Simpler pipeline for standard web applications.

### Benefits of an OCI Image

- Packages the JDK/runtime, native libraries, and startup behavior with the build.
- Uses the same tested image across Container Apps, AKS, or container-enabled hosting.
- Well-suited for image scanning, signing, digest pinning, and reproducibility.

### Added Responsibilities with an OCI Image

- Track base image and dependency CVEs.
- Do not embed secrets, SSH keys, or tenant data in image layers.
- Run as non-root when appropriate; use minimal runtime images.
- Record image digests, SBOMs, and provenance when required.
- Match CPU architecture/OS and JDK compatibility.

**Containerization does not automatically make an app cloud-native**. A Spring Boot container can still store local state, create unscalable sessions, hold static secrets, or crash on transient database errors.

## 22. Sample Dockerfile for Spring Boot

Assuming the Maven project produces **target/support-api.jar** after tests:

~~~dockerfile
# Example uses JDK 21; replace with a version supported by the app and platform.
FROM eclipse-temurin:21-jre
WORKDIR /app

# Assumes the artifact was built and tested in CI before image creation.
COPY target/support-api.jar /app/application.jar

# Use a non-root UID; file/volume permissions must be compatible.
USER 10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

### Build and Test Locally

~~~bash
./mvnw -B clean verify
docker build -t support-api:lab .
docker run --rm -p 8080:8080 support-api:lab
curl --fail http://localhost:8080/actuator/health
~~~

**This is a hands-on example**, not an assertion that an existing project already has a Maven wrapper, a JAR named support-api.jar, the Actuator dependency, or a health endpoint. You must configure **finalName**, build plugins, Actuator, and environment settings for the actual project.

### Operational Points to Check

1. Use an up-to-date base image and pin versions/digests according to policy.
2. Build the JAR in CI, run unit/integration tests, and scan before pushing the image.
3. Do not set database passwords, connection strings, or secrets via hard-coded **ENV** in the Dockerfile.
4. Verify **UID 10001** has permission to read the JAR and write to temporary directories if libraries require it.
5. Account for heap + non-heap RAM; **65% is an illustrative number**, not a universal optimum.
6. Exposing 8080 does not open it to the Internet: you still need Container Apps ingress or AKS Service/Ingress accordingly.
7. Add graceful shutdown and a readiness probe before routing traffic.

If using a distroless image or a different JDK major version, verify library/native compatibility and production debugging methods.

## 23. Runtime Versions and Compatibility Matrix

Spring Boot runs on the JVM, yet not every combination of **JDK + Spring Boot + Azure runtime + SDK** is supported. Before selecting a platform:

| Item | Must confirm |
|---|---|
| **Java major version** | Project needs Java 17, 21, or another supported release |
| **Spring Boot version** | Compatible with JDK, Spring Framework, and dependencies |
| **Container base image** | Architecture support, CA certificates, tzdata, native libs |
| **Azure hosting runtime** | Actual JDK/runtime stack available on App Service/Functions |
| **Azure SDK BOM** | Identity, storage, Service Bus libraries have consistent versions |
| **Startup commands** | JAR path, JVM flags, port, and graceful shutdown |
| **Build pipeline** | Maven/Gradle toolchain, reproducible builds, tests |
| **Security** | CVEs/runtime patches, SBOM, container scans, EOL policy |

### Upgrade Risks

An app built with Java 21 bytecode cannot run on a Java 17 runtime. A Spring Boot major upgrade can change packages (**javax → jakarta**), config keys, security behavior, or Actuator paths. The chosen platform must allow tested upgrades rather than trapping you on an out-of-support JDK for too long.

### Recommendation

For new applications, choose an **LTS JDK and Spring Boot version actively supported at deployment time**, checking the Azure support matrix and dependency requirements. Do not lock hard-coded runtime versions in architecture docs without a review schedule.

## 24. Pragmatic Decision Tree

~~~text
You have a Spring Boot application
  |
  +-- Primarily event handlers / short jobs?
  |      |
  |      +-- Yes: consider Azure Functions Java
  |             or Container Apps Jobs if the job is containerized
  |
  +-- Continuous HTTP API / web server?
         |
         +-- Want fast JAR deploy, low operations?
         |      -> App Service
         |
         +-- Already containerized, need revisions/event autoscale?
         |      -> Container Apps
         |
         +-- Need Kubernetes-level APIs, operators, node pools?
         |      -> AKS, if platform operations capability exists
         |
         +-- Must have full OS/native kernel/legacy runtime control?
                -> VM/VM Scale Sets
~~~

**This is not an automated algorithm replacing the architect.** For example, an organization with a standardized shared AKS cluster may choose AKS for a small API; a containerized app can also run well on App Service for Containers. Check all mandatory constraints before applying any priority order.

### What If Two Options Tie?

Prefer the option with **lower operational burden that still meets SLO/security/networking**, or the one aligned with the platform the team already operates proficiently. Avoid introducing a new platform solely for an appealing feature without an actual use case.

## 25. Weighted Scoring Matrix

A decision tree helps narrow options, but it **does not replace mandatory constraints**. Before scoring, immediately disqualify any platform that fails legal/compliance, data residency, network security, native dependency, or product support requirements.

For remaining candidates, score **1 = very poor fit, 5 = very strong fit** across weighted criteria.

### Example: 4-person team, one Spring Boot REST API, steady traffic

| Criterion | Weight | App Service | Container Apps | AKS | Functions | VM |
|---|---:|---:|---:|---:|---:|---:|
| Low operational burden | 30% | 5 | 4 | 2 | 3 | 1 |
| Fit for continuous HTTP API | 25% | 4 | 5 | 5 | 2 | 4 |
| Fit for expected budget | 20% | 4 | 4 | 2 | 5 | 2 |
| Required network/security support | 15% | 4 | 4 | 5 | 3 | 5 |
| Existing team skills | 10% | 5 | 4 | 2 | 4 | 2 |
| **Illustrative total / 5** | **100%** | **4.40** | **4.25** | **3.20** | **3.25** | **2.65** |

Calculation for App Service:

~~~text
0.30 × 5 + 0.25 × 4 + 0.20 × 4 + 0.15 × 4 + 0.10 × 5
= 1.50 + 1.00 + 0.80 + 0.60 + 0.50
= 4.40 / 5.00
~~~

**All scores are hypothetical self-assessments**, not objective Azure rankings. If an organization already has a shared AKS platform or requires native network policies, weights/skills and costs change; AKS could win.

### Proper Process for Using the Matrix

1. List **must-haves**: compliance, private access, latency SLO, workload type.
2. Eliminate options that fail any must-have.
3. Align weights with security, operations, product, and finance teams.
4. Score each item with evidence/PoC rather than gut feeling.
5. Run a **sensitivity analysis**: does the winner flip if cost or ops weight increases?
6. Pick the top two candidates for benchmarking and cost estimation.
7. Write an **Architecture Decision Record (ADR)** with revisit triggers.

**A high score does not override a mandatory violation.** A platform scoring 4.8/5 that fails data residency still cannot be selected.

## 26. Networking: Distinguish Inbound and Outbound

Spring Boot has at least three network flows:

~~~text
Client -> HTTPS -> Java application
                         |
                         +-- Azure SQL / PostgreSQL
                         +-- Azure Service Bus
                         +-- Key Vault
                         +-- Azure Storage
                         +-- External payment API
~~~

### Inbound

Who can call the application?

- Public Internet over HTTPS and gateway/WAF when needed.
- Internal network/VNet/Private Endpoint only.
- Another frontend within the same platform.
- An Azure service callback requiring an authenticated endpoint.

### Outbound

Which destinations must the application reach?

- Database private IP/Private Endpoint with proper DNS.
- Managed services using data-plane identity.
- External APIs via NAT/firewall/proxy if allowlisted.
- Identity provider to acquire tokens when needed.

| Platform | Key distinction |
|---|---|
| **App Service** | **VNet Integration** handles outbound to a VNet; **Private Endpoint** handles private inbound per feature support |
| **Container Apps** | Environment networking, internal/external ingress, VNet, and outbound controls |
| **AKS** | Cluster/node/pod networking, ingress controller, Network Policy, and egress |
| **Functions** | VNet/private access depends on hosting plan and trigger model |
| **VM** | VNet subnet, NSG, load balancer, firewall/NAT, and DNS |

**App Service VNet Integration does not automatically turn a public web app into a private app.** If public Internet inbound must be blocked, configure inbound access restrictions/private endpoints per the approved topology.

### DNS Is Critical for Private Link

An application may resolve **mydb.postgres.database.azure.com** or another database hostname to a public address even after creating a Private Endpoint. You must verify:

- Private DNS zone/link/forwarder.
- DNS resolution from **the actual app instance/pod**.
- Route/firewall/port reachability to the service.
- TLS hostname verification and certificate.
- Data-plane permissions.

**Never hard-code a private IP in Java** to bypass DNS issues. It undermines TLS and service agility.

## 27. Secrets and Managed Identity

Never store database passwords, Azure Storage connection strings, Service Bus keys, or secret tokens in committed **application.properties** files or Docker images.

### Architectural Pattern

~~~text
Spring Boot workload
       |
       | Managed identity / Workload identity
       v
Microsoft Entra ID
       |
       +-- Access to Key Vault (if secret needed)
       +-- Access to Storage/Service Bus data plane
       +-- Access to Azure SQL/PostgreSQL per capability
       |
       v
Authorized Azure resources
~~~

| Platform | Identity mechanism to evaluate |
|---|---|
| **App Service** | System-assigned or user-assigned managed identity |
| **Container Apps** | Managed identity attached to the container app per feature support |
| **AKS** | Microsoft Entra Workload ID for pod/service account; cluster identity differs from workload identity |
| **Functions** | Function App managed identity per hosting |
| **VM** | VM/VMSS managed identity |

### Two Common Mistakes

1. **Enabling managed identity without assigning a data-plane role:** requests still return 403.
2. **Granting Azure Contributor on the resource group and assuming the app can query data:** control-plane RBAC differs from data-plane authorization.

Assign the proper scope and **least privilege**, and test with the actual workload identity rather than masking issues with a developer's Owner credential.

### When a Secret Is Still Needed

Some third-party APIs, database providers, or legacy systems still require passwords/API keys. Use **Azure Key Vault**, secret references/app settings, and a rotation plan; restrict read access in Key Vault. Never expose raw secrets in error logs, application telemetry, or support tickets.

### Spring Cloud Azure

**Spring Cloud Azure** libraries can simplify integrating Azure identity, Service Bus, Storage, and Key Vault with compatible Spring Boot versions. Always pin the **Spring Boot–Spring Cloud Azure compatibility matrix** rather than assuming all latest versions combine cleanly.

## 28. Configuration: Environments and Feature Flags

Separate configuration from the artifact so the same JAR/image deploys to dev/staging/prod:

~~~yaml
# Illustrative configuration, containing no real credentials.
spring:
  application:
    name: orders-api
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Other values are injected via app settings/environment variables or secret references:

~~~text
SPRING_PROFILES_ACTIVE=staging
DATABASE_HOST=<STAGING_DATABASE_HOST>
SERVICE_BUS_NAMESPACE=<STAGING_NAMESPACE>
SPRING_DATASOURCE_PASSWORD=<INJECTED_SECRET_IF_REQUIRED>
APP_FEATURE_NEW_CHECKOUT=false
~~~

**Environment variables do not inherently guarantee end-to-end encryption or airtight access control**. Anyone permitted to inspect container/pod/process configuration can view some values; prefer identity over static secrets and enforce platform permissions.

### Do Not Confuse Environment with Spring Profile

**dev/staging/prod** are infrastructure environments that may differ in subscription, resource group, network, and database. A **Spring profile** is merely an in-app configuration selector. Setting profile=prod does not automatically point identity, database, or storage to production; you must verify deployment config and policies.

### Feature Flags

Using feature flags for per-tenant or canary releases helps avoid rolling back the entire JAR. However, design safe defaults and never guard data-risking features solely with a client-side flag.

## 29. Database: Do Not Let Compute Dictate Data Architecture

A Spring Boot application can use:

- **Azure SQL Database** when a relational model/T-SQL fits the app.
- **Azure Database for PostgreSQL – Flexible Server** for PostgreSQL/JPA/JDBC.
- **Azure Cosmos DB** for NoSQL document workloads with partitioning and the RU model.
- **Azure Blob Storage** for large files, images, and exports.
- **Azure Cache for Redis/appropriate Redis service** for cache/session/locks per support lifecycle.

Choose the database based on **data model, consistency, transactions, HA, and cost**, not because AKS or App Service requires a particular DB.

### Pooling and Autoscale

Suppose:

~~~text
One Spring Boot instance:
  HikariCP maximumPoolSize = 20

10 replicas:
  Up to 200 DB connections in a simple model

40 replicas:
  Up to 800 DB connections
~~~

This is a **hypothetical multiplication**, excluding admin connections, retries, maintenance, and pool behavior. Check database connection limits, saturation, and transaction durations. A CPU/request scale rule can spike connection demand, overloading the database before the app runs out of CPU.

### Session State and Cache

Avoid relying on **in-RAM-only HTTP sessions** when running multiple instances or rolling updates. Use stateless tokens where sensible, or a properly designed distributed session store. A cache does not replace the source database; configure TTLs, invalidation, stampede protection, and tenant isolation.

## 30. Health Checks, Probes, and JVM Startup

Spring Boot Actuator provides health endpoints when the dependency and configuration are added:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

### Verification Layers

| Check | Purpose | Avoid |
|---|---|---|
| **Startup** | Has the app started enough to evaluate liveness? | Restarting the JVM during valid warm-up |
| **Liveness** | Is the process stuck in an unrecoverable state? | Restarting when the database is temporarily down |
| **Readiness** | Is the instance ready to receive traffic? | Sending requests to a migrating/initializing pod |
| **Business synthetic check** | Do real transactions succeed? | Treating HTTP 200 on /health as proof of full functionality |

### Why Can Startup Be Slow?

- Large Spring context and dependency injection graph.
- JIT warm-up or cache initialization.
- Database migration/schema validation.
- Slow DNS/network/Key Vault fetch.
- Large classpath or native library loading.

Set **startupProbe/readiness thresholds** based on measured startup time. Do not make liveness probes call all downstream services; a SQL outage could cause every pod to restart continuously and prolong the incident.

### Graceful Shutdown

During a rolling deploy:

1. Stop accepting new requests.
2. Finish in-flight requests within the timeout.
3. Stop listeners/threads and close connections.
4. Ensure background jobs have checkpoint/retry state.

Spring Boot supports **server.shutdown=graceful** and phase timeouts depending on the version; the platform also needs an adequate termination grace period. Never promise all requests will finish if a VM/pod is force-killed, a node loses power, or the deadline expires.

## 31. Autoscaling: The Right Metric for the Right Workload

Not every service scales the same way:

| Workload | Metrics to consider |
|---|---|
| REST API | Request rate/concurrency, CPU, latency, memory |
| Service Bus worker | Queue depth, oldest message age, execution duration |
| Event Hubs processor | Consumer lag, partition utilization, time-to-process |
| Batch scheduler | Job queue/backlog and deadline |
| Memory-heavy analytics | Memory, GC pause, heap pressure |
| WebSocket/streaming | Connections/concurrency and network I/O |

### Example of Scaling Wrong

A Service Bus worker has low CPU because it is waiting on a slow database. CPU-based autoscale will not add replicas, or adding replicas might worsen DB contention. A better metric may be backlog/age, yet you still need a **max concurrency** cap to avoid overwhelming dependencies.

### Scale-Out Does Not Automatically Provide Data HA

Adding 10 Spring Boot instances on AKS/App Service does not make a single-instance PostgreSQL database multi-zone. Compute scaling and data-tier HA/DR are independent responsibilities.

### Cold Start and Min Instances

With Container Apps/Functions, scale-to-zero or serverless environments can exhibit cold starts. With App Service/AKS, processes still have startup time during deployments/replacements. Measure **time-to-readiness** and use pre-warming/min replicas when the SLO demands fast responses.

## 32. Observability and Performance Analysis

Layers to observe:

~~~text
User request / traceId
        |
        v
Gateway / WAF / API Management
        |
        v
Spring Boot HTTP controller
        |
        +-- DB query / connection pool
        +-- Service Bus publish
        +-- Redis cache
        +-- External API
        |
        v
HTTP response / business result
~~~

### Telemetry Recommendations

| Layer | Useful data |
|---|---|
| **Platform** | CPU, memory, restarts, replicas, cold starts/scale events |
| **JVM** | Heap, GC duration, threads, class loading, OOM |
| **HTTP** | Request rate, p50/p95 latency, 4xx/5xx, timeouts |
| **Database** | Pool utilization, query latency, retries/deadlocks |
| **Queue** | Publish/consume latency, backlog, DLQ |
| **Security** | Unauthorized attempts, denied identities, configuration changes |
| **Business** | Orders created, payment failures, processing lag |
| **Cost** | Spend per environment/service, log ingestion, egress |

Spring Boot commonly uses **Micrometer + Actuator** for metrics. **Application Insights/Azure Monitor/OpenTelemetry** can centralize traces, logs, and JVM telemetry depending on how instrumentation/agents/versions are configured.

### Correlation

Propagate a **traceId/requestId** from ingress through Spring Boot, the Azure SDK, and databases/queues where supported. Do not log full authorization headers, cookies, database passwords, raw PII, or file uploads. Set sampling/retention according to data sensitivity and cost.

### Do Not Watch CPU Alone

An app at 30% CPU with rising p95 latency may suffer from DNS, connection pool exhaustion, SQL locks, GC, networking, or downstream throttling. SREs should inspect **dependency traces** before deciding to scale.

## 33. High Availability and Disaster Recovery

### Distinct Objectives

- **Availability:** the app keeps serving when an instance fails.
- **RTO:** maximum acceptable time to recover after an incident.
- **RPO:** maximum acceptable data loss upon recovery.
- **SLO/SLA:** operational target versus conditional service commitment.

### Example of a Fault-Tolerant Architecture

~~~text
Users
  |
  v
Azure Front Door / Application Gateway as required
  |
  +--> Region A: >=2 healthy Spring Boot instances
  |         |
  |         +--> Database HA configuration
  |
  +--> Region B: standby/active per DR plan
            |
            +--> Replication / recovery mechanism
~~~

### Platform-Specific HA Checks

| Platform | HA points |
|---|---|
| **App Service** | Instance count, plan zone redundancy support, health/routing, and regional DR |
| **Container Apps** | Multiple replicas, zones per environment/plan, revision availability |
| **AKS** | Multi-node pools/zones, topology spread, PDB, resilient ingress |
| **Functions** | Hosting-plan availability and retry/durable processing |
| **VMs** | Availability zones/sets, VMSS, load balancer, and patch orchestration |

**A deployment with replicas=2 does not automatically guarantee multi-zone**; verify placement, platform support, DB HA, shared dependencies, and single points of failure.

### Backup Is Not HA

Backups enable data recovery, whereas HA keeps processing requests when an instance/component fails. Do not calculate RPO/RTO for Spring Boot purely from compute replica counts. Practice **failover** and test restores, secrets, networking, and DNS.

## 34. Security and Supply Chain per Platform

Shared responsibilities:

- Manage dependencies/CVEs, JDK, and Spring Boot versions.
- Keep secrets out of Git, images, shell history, and logs.
- Authentication/authorization using **Microsoft Entra ID/OIDC/JWT** or an appropriate mechanism.
- HTTPS/TLS, HSTS, and public endpoint policies as required.
- Validate requests, CORS/CSRF, input size, and upload security.
- Least-privilege data-plane access, NSG/network segmentation, and egress control.
- Configurations/role assignments governed via IaC and audited.

### Different Areas of Focus

| Platform | Extra considerations |
|---|---|
| **App Service** | App settings/slot settings, access restrictions, runtime upgrades |
| **Container Apps** | Image signing/scanning, secrets/ingress, revision exposure |
| **AKS** | Kubernetes RBAC, service accounts, network policies, admission, node security |
| **Functions** | Function keys vs. end-user auth, trigger identity, exposed HTTP functions |
| **VMs** | OS hardening, patch management, SSH/RDP, host firewall, agents |

**A function key is not equivalent to user authentication**, and **a Kubernetes namespace is not an absolute security boundary**. Design permissions from user identity down to the resource, not only at the transport layer.

### Secret Scanning and Rollout

If a secret is accidentally committed to an image/repository, deleting the commit is not enough; you must **rotate** the secret, audit access, and inspect logs. For ACR images, pin digests and scan to detect vulnerable libraries before rollout.

## 35. Cost: Compare TCO Rather Than Compute Price Alone

An estimate claiming "a 2 vCPU VM is cheaper than 2 vCPU App Service" is incomplete. **Total Cost of Ownership** includes compute, dependent services, and operational labor.

~~~text
TCO = Compute/hosting
    + Network ingress/egress/Private Link
    + Database/Storage/Cache
    + Monitoring/log retention
    + Registry/build/security
    + Backup/DR/capacity headroom
    + Human operations & incident risk
~~~

### Cost Categories to List

| Item | App Service | Container Apps | AKS | Functions | VMs |
|---|---|---|---|---|---|
| Primary compute | App Service Plan | Consumption/dedicated workload profiles per plan | Node VMs/node pools and cluster-tier features | Executions/resources/hosting plan | VM hours/disk |
| Idle load | Plan may still incur charges | Scale-to-zero per app/plan, may have environment cost | Nodes/platform still run depending on setup | Depends on plan, min instances/capacity | VM keeps running |
| Burst scaling | Plan scale-out | Replica autoscaling | HPA + cluster autoscaler | Trigger-based scale | VMSS/autoscale |
| Network | VNet/Private Endpoint/NAT as needed | Environment VNet/ingress/egress | Load balancer, ingress, NAT/VNet | VNet per plan/feature | Load balancer, NSG, Public IP/NAT |
| Security tooling | App/identity policy | Image scanning/secrets | Cluster policy/node/image security | Trigger/identity security | OS patching/hardening |
| Observability | App Insights/logs | Container/platform logs | K8s/container insights | Function telemetry | VM agents/logs |
| Ops/TCO | Usually low | Usually low–moderate | High without a platform team | Depends on code/trigger model | High |

Rows show **cost drivers**, not direct price comparisons. Prices/plans/regions vary over time and configuration; to quantify, use the **Azure Pricing Calculator + real benchmarks + Cost Management**.

### Simple Instance-Hours Example

An API needs **two continuous instances** during a hypothetical 730-hour month:

~~~text
2 instances × 730 hours = 1,460 instance-hours/month
~~~

A worker running only **20 hours of CPU/billing-eligible time per month** may suit an execution-based model better if the runtime and workflow fit. However, **you cannot compare 20 hours directly against 1,460 hours and conclude Functions is cheaper**: compute units, memory, billing granularity, startup, idle charges, downstream traffic, and platform capacity all differ.

### Staffing and Operational Cost

Suppose using AKS for an API saves some monthly compute spend, but the team must spend an extra 15 hours/month on patching, policies, and cluster incidents. In TCO terms, that labor can outweigh the compute savings. Conversely, if a shared AKS platform team already exists, the marginal cost may be reasonable.

## 36. Rough Sizing Formulas for Spring Boot

Before picking a SKU, measure a representative application under expected load:

| Metric | Meaning |
|---|---|
| Peak concurrent HTTP requests | Requests processed simultaneously |
| RPS/QPS | Application throughput |
| P50/P95/P99 latency | Actual tail latency, not just averages |
| CPU per instance | Compute consumption |
| Heap and non-heap RSS | Actual RAM needed by the JVM |
| GC pause/time | Signs of memory pressure |
| DB pool utilization | Effective connection usage |
| Startup/readiness time | Impact on autoscale/deployments |
| Downstream latency | SQL/queue/external API bottlenecks |

### Estimating Concurrency with Little's Law

Under steady-state conditions and suitable assumptions:

~~~text
Concurrent requests ≈ throughput (requests/second)
                      × average latency (seconds)

Example:
  120 requests/second × 0.20 seconds = 24 average concurrent requests
~~~

**This is not a CPU quota or exact pod count formula**. Requests may wait on I/O, latency distributions are skewed, WebSockets are long-lived, and peaks differ from averages. Use load-test results to choose instance counts, headroom, and autoscale thresholds.

### Memory Sizing

Assume one measured instance shows:

~~~text
Heap maximum:          700 MiB
Non-heap/native/stack: 200 MiB
OS/process overhead:   100 MiB
Desired headroom:      300 MiB
------------------------------
Capacity to consider: 1,300 MiB
~~~

These numbers only illustrate summation, excluding CPU limits, classloading, file buffers, TLS, code paths, and traffic. Do not always choose a 1GiB replica simply because -Xmx is below 1GiB.

### Sizing Database Connections for Scale-Out

~~~text
maxDBConnectionsNeeded ≈ maxReplicas × maxPoolSizePerReplica
                         + worker/admin overhead

Example:
  12 replicas × 15 connections = 180
  + 30 for services/ops        = 210 reference connections
~~~

This is a **theoretical ceiling** based on config; actual connection usage depends on pool/lifecycle behavior. The database must be sized for bursts and other clients; the app also needs timeouts/backpressure when the pool is exhausted.

## 37. Deployment and Rollback Strategies per Platform

| Platform | Common strategy | Things to check |
|---|---|---|
| **App Service** | Deployment slots, swap, traffic routing per plan/feature | Sticky settings, health, warm-up |
| **Container Apps** | Revision rollout/traffic weights, revert to previous revision | Revision modes, secrets/ingress, readiness |
| **AKS** | RollingUpdate/blue-green/canary with Deployment/Ingress/mesh/GitOps | Probes, PDB, capacity, HPA, image digest |
| **Functions** | Slot/version deployments per hosting support or staged release | Trigger activation, retries, old event bindings |
| **VM/VMSS** | Image rollout/blue-green scale set, rolling upgrades | OS/image compatibility, load balancer health |

### Do Not Roll Back Only the Image

A release often changes:

~~~text
Java app version
Database schema migration
Event JSON schema
Feature flags
Authorization roles
Container/host settings
Endpoint/network configuration
~~~

**Code rollback can fail if the database changed incompatibly.** Use **expand-and-contract schema migrations**, backward-compatible events, feature flags, and testing with multiple app versions running concurrently.

### A Controlled Deployment Workflow

1. Build the same artifact/JAR/image once from a tested commit.
2. Run security scans, SBOM generation, and dependency checks.
3. Deploy to staging with equivalent data/network/config as needed.
4. Run smoke/integration tests and verify readiness.
5. Perform canary/blue-green or rolling release per platform capabilities.
6. Monitor p95/5xx, DB metrics, queue lag, and business KPIs.
7. Promote or roll back routes/artifacts per the runbook.
8. Clean up old revisions/slots only after a reasonable observation window.

Do not use a mutable **latest** image tag as proof that the right version was deployed. Record the image digest/commit SHA and configuration revision.

## 38. Azure CLI: Inventory Existing Platforms

Before creating additional compute services, inventory what already exists in the subscription:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"

# App Service Web Apps
az webapp list --resource-group "$RG" \
  --query "[].{name:name,location:location,kind:kind}" \
  --output table

# Azure Container Apps (requires the right CLI extension/version)
az containerapp list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# AKS clusters
az aks list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# Azure Functions
az functionapp list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table

# Azure VMs
az vm list --resource-group "$RG" \
  --query "[].{name:name,location:location}" \
  --output table
~~~

These commands **only read metadata** within your existing permissions. Running **az containerapp** may require installing/updating the CLI extension; output properties and command flags vary by version. A resource not appearing in this resource group does not mean the subscription lacks similar services in another resource group.

### Do Not Use a Production Subscription for Random Create Tests

Every command creating an App Service Plan, Container Apps environment, AKS cluster, or VM can incur **different costs, public endpoints, and network policies**. For a platform selection exercise, you can complete the decision matrix and mock deployment **without creating real resources**.

## 39. Architecture Decision Record (ADR): Verifiable Decisions

A concise ADR prevents choices driven by personal preference:

~~~text
ADR-007: Platform for Spring Boot orders-api

Context:
  1 Spring Boot REST API, 5 developers
  HTTP traffic daytime, staging/prod environments
  Azure SQL private access, Entra auth, p95 SLO

Must-have:
  Private database egress, managed identity,
  deployment rollback, JVM 21 support, regional availability

Considered:
  App Service, Container Apps, AKS, Functions, VM

Decision:
  <SELECTED_PLATFORM_AFTER_TEST>

Why:
  <EVIDENCE_FROM_COST_AND_LOAD_TEST>

Trade-offs:
  <OPERATIONS, IDLE COST, SCALE, DEPLOYMENT LIMITS>

Revisit if:
  >10 microservices, need Kubernetes operators,
  traffic shape or compliance changes
~~~

### The ADR Must Record Reasons for Rejecting Options

For example:

- **AKS rejected** because there is no cluster operations team and no need for K8s-specific features.
- **Functions rejected** because the app is a long-running Spring MVC web app with no plan to refactor into handlers.
- **VM rejected** because there are no native OS constraints.
- **App Service and Container Apps advance to PoC** because both satisfy all mandatory conditions.

If the conclusion is simply "chose AKS because it's trending," the ADR lacks architectural evidence.

## 40. Scenario A: Small Team Operating One REST API

**Context:** A team of four Java developers builds an order management portal using Spring Boot/Java 21 and Azure Database for PostgreSQL, with around 50–150 requests/s at peak. No K8s operators are needed and there is no platform team.

### Evaluation

1. Can deploy an **executable JAR** with an appropriate App Service configuration.
2. If a Docker pipeline already exists or revision-based releases are needed, consider Container Apps.
3. Private database networking and managed identity are needed per the support matrix.
4. Must measure RAM, JVM startup, p95 latency, and connection pooling.
5. If traffic is steady throughout the day, **scale-to-zero is not a top priority**.

### Conclusion for This Scenario

**App Service** is a sensible default for the first PoC; **Container Apps** is an equivalent candidate if the team prefers OCI images and event-driven scaling. **AKS/VMs do not inherently add value** in this model unless a new constraint appears.

### Common Mistake

Choosing AKS right away for "future scalability" when there is no Kubernetes requirement, then spending weeks building networking, ingress, and patching pipelines. Scalability should be justified by workload data, not by the number of service names.

## 41. Scenario B: Microservices Scaling by Queue

**Context:** An e-commerce system consists of orders, inventory, payment integration APIs, and a notification worker. The Orders API serves HTTP, while the worker processes a Service Bus queue that sees 20x volume in the evening.

~~~text
HTTP Orders API
     |
     +--> Database
     |
     v
Service Bus queue
     |
     v
Notification worker
     |
     v
Email / external system
~~~

### Options

- **Container Apps** for containerized APIs/workers with supported HTTP/queue scale rules.
- Or **App Service for the REST API + Azure Functions/Container Apps Job** for the worker.
- **AKS** if the organization needs Kubernetes, has a platform team, and other services already run on K8s.

### Why Not Put the Worker in the Same Web App?

When scaling up API replicas, worker listeners may multiply unintentionally; when worker backlog grows, HTTP scaling does not necessarily help. Separating services allows **independent resource limits, autoscale, deployments, credentials, and SLOs**.

### Items to Verify

- Queue retry/dead-letter handling and idempotency.
- Do not send emails or charge twice on worker restart.
- HPA/KEDA or external scaling respects database/external API caps.
- Monitor oldest message age and backlog instead of CPU alone.

## 42. Scenario C: 20-Minute Batch, Once per Night

**Context:** A Java application reads a CSV file from Blob Storage at 02:00, processes for 20 minutes, and stops. There is no HTTP API and no need for an always-on JVM.

### Candidates

| Option | Assessment |
|---|---|
| **Container Apps Job** | Sensible if the job is containerized and needs scheduled execution and resource limits |
| **Azure Functions** | Sensible when the function programming model, trigger, and hosting plan fit the duration |
| **AKS CronJob** | Sensible if an AKS cluster and operational policies already exist |
| **VM cron** | Possible, but high cost/ops overhead for a single job |
| **App Service scheduled logic** | Must weigh web lifecycle, scale-out, and duplicate scheduling |

### Suggested Decision

If the team already has a Dockerfile and no AKS, **Container Apps Job** is worth a PoC. If the logic fits Azure Functions triggers and hosting limits, **Functions** is also worth testing.

### Easily Overlooked Parts

- Does rerunning the job after a failure create duplicate data?
- Is there a stable input blob version/event ID?
- Should the 20-minute work be split into chunks with checkpoints?
- Are input files and outputs persisted outside the container?
- Are timeouts, retries, and max parallel jobs clearly defined?

**A job with no HTTP traffic does not need a continuously hosted web server** just to have somewhere to run a Java main method.

## 43. Scenario D: Banking System Requiring Private Networking and Auditing

**Context:** A Spring Boot API processes sensitive data. Requirements:

- Inbound only from a private network or controlled gateway.
- Database over Private Endpoint/Private DNS.
- Managed identity and least-privilege RBAC.
- WAF, audit logs, and policy-governed log retention.
- Clear RTO/RPO and multi-zone capability.
- No manual deployments from developer laptops.

### How to Choose

You cannot conclude that **only AKS** meets these requirements. **App Service, Container Apps, and AKS** can all provide mechanisms to satisfy them depending on **SKU/region/topology/actual features**. Check each mandatory criterion:

1. Private inbound/egress and network inspection.
2. Managed identity/data-plane RBAC.
3. Data residency policies and zone availability.
4. Secrets, container/JDK patching, and audit logging.
5. CI/CD approvals and image/artifact provenance.
6. DR capability and failover testing.

### When AKS Truly Adds Value

If the organization requires **Kubernetes Network Policies**, admission policies, operators, specialized scheduling configurations, and already has a platform team, AKS can provide the right toolset. If the API is simple and PaaS fully supports the required networking/identity/compliance, picking AKS solely for the "enterprise" label is insufficient justification.

### Mistake to Avoid

Enabling App Service VNet Integration and claiming the API is private. VNet Integration mainly addresses **outbound** traffic; you must independently configure **inbound restrictions/private endpoints** and gateway paths. Similarly, AKS inside a VNet does not protect any service exposed via a public LoadBalancer.

## 44. Scenario E: Legacy App Depending on Native OS Agent

**Context:** Spring Boot 2.x on an older JDK, using a native library installed via an OS script, requiring a proprietary security agent running as root and writing to the local filesystem.

### Evaluation

- Check whether the library can be packaged into a **custom container** running as non-root.
- Verify whether the current JDK/Spring Boot version is still supported/secure.
- Check whether the agent requirement can move to managed telemetry/a sidecar.
- If OS/kernel control unavailable on PaaS is mandatory, **VM/VMSS** can serve as a transitional option.
- If using VMs, design HA, OS patching, managed disks, backups, and monitoring.

### Two-Phase Plan

~~~text
Phase 1: ensure the app runs securely with HA
  VM/VMSS or container if feasible
          |
          v
Phase 2: remove native dependencies / upgrade JDK
          |
          v
  Evaluate migration to App Service/ACA/AKS
~~~

**Do not force legacy apps into AKS just to "modernize"** if the container still requires privileged root and excessive host filesystem access. Platform selection must be accompanied by real architectural and permission-model changes.

## 45. Scenario F: Container Apps Cold Start Raises p95 Latency

**Context:** A low-traffic API at night is configured on Container Apps with **minReplicas=0**. After 20 quiet minutes, the first request takes several seconds; the API's SLO demands fast responses even after idle periods.

### Diagnosis

1. Measure time from request arrival to replica provisioning.
2. Measure JVM startup and Spring context initialization.
3. Measure database connection, Key Vault access, and cache warm-up time.
4. Check whether the request actually reached the container or hit network/gateway delays.
5. Review scaling rules and minReplicas/maxReplicas.

### Options

- Set **minReplicas=1** or higher to reduce cold starts within plan capabilities.
- Optimize startup and remove unnecessary blocking initialization.
- Consider **App Service** with warm capacity if traffic/SLO fits.
- If the app only handles async jobs, allow queue buffering instead of demanding immediate HTTP responses.

**Scale-to-zero is an economic and technical choice**, not a feature to turn on for every app. Changing min replicas alters cost; calculate based on real traffic.

## 46. Scenario G: AKS Scales Many Pods but PostgreSQL Gets Slower

**Context:** An API receives 429/5xx responses under traffic spikes. The team raises HPA from 5 to 30 pods. Per-pod CPU drops, yet the database returns "too many connections" and p95 latency rises.

### Analysis

~~~text
Before:
   5 pods × poolSize 20 = up to 100 DB connections

After:
  30 pods × poolSize 20 = up to 600 DB connections

Hypothetical database connection budget: 250
~~~

HPA multiplied connection pools past the database's capacity. This is a **dependency design problem**, not necessarily a Kubernetes bug.

### Remediation

1. Reduce per-pod pool max according to the total connection budget.
2. Cap max replicas and API concurrency while stabilizing the service.
3. Optimize queries, transaction durations, and caching.
4. Evaluate a **connection pooler/proxy** compatible with the database and workload.
5. If needed, scale the database based on measurements and HA policies.
6. Set metrics/alerts for HikariCP active/pending counts, DB connections, and latency.

Do not simply raise database max_connections indefinitely if memory/CPU/lock contention remain the real bottlenecks.

## 47. Scenario H: App Service Slot Swap Sends Traffic to the Wrong Database

**Context:** Staging App Service uses a test database and production uses the real database. After a slot swap, the production app starts with a few environment variables from staging and operates on test data.

### Root Cause

- Slot settings and swap behavior were not fully understood.
- The app used a misnamed environment variable or a shared secret reference.
- There was no smoke test confirming environment/data source identity.
- Some resources were shared between staging and prod without app-level distinction.

### Runbook

1. Stop impact-causing write operations if a wrong target is detected.
2. Verify **effective configuration** without printing passwords/secrets.
3. Inspect slot-specific settings, identities, and Key Vault references.
4. Restore traffic/config following a controlled runbook.
5. Audit incorrectly created data and assess remediation.
6. Add a startup guard or post-deploy test verifying resource/environment IDs.

### Prevention

Tag resources, separate identities/RBAC per environment, and restrict database permissions so the **staging identity cannot write to production data**. Even if deployment config is wrong, least privilege can still block the damage.

## 48. Hands-On Exercise: Choosing a Platform for a Spring Boot Project

### Context

An enterprise wants to move its **Commerce API** system to Azure. The system includes:

- A Spring Boot REST API running **Java 21**, using Maven and PostgreSQL.
- A worker processing Service Bus messages to send emails.
- Invoice file storage on Azure Blob Storage.
- Initially **4 Java developers**, with no Kubernetes platform team yet.
- **Development, staging, and production** environments requiring permission separation.
- Hypothetical peak of **120 requests/second**, target p95 latency under **500 ms**.
- Dev can shut down outside working hours; production needs 2 instances or an appropriate HA setup.
- The database requires a private network, centralized secrets, and alerting.

**The data and values above are learning assumptions.** Do not use real production resources for experimentation; if you lack a subscription or creation permissions, complete the exercise with an ADR, manifests, and local/mock tests.

### Part A: Build a Requirements Table

| Requirement | Mandatory or desired? | Required evidence |
|---|---|---|
| Run JDK 21 and compatible Spring Boot version | Mandatory | Runtime/support matrix |
| HTTPS REST API | Mandatory | Ingress test |
| Private database access | Mandatory | DNS/network path proof |
| Identity without static Azure keys | High priority | Managed identity + RBAC test |
| p95 under 500 ms | Mandatory per hypothetical SLO | Load test |
| Tested release/rollback | Mandatory | Staging/canary evidence |
| Scale by HTTP | Desired | Load/scale metrics |
| Worker scales by Service Bus queue | Desired | Queue backlog metrics |
| Dev scale-to-zero | Desired | Cost vs. cold start test |
| No K8s operations required | Highly desired | Ops effort estimate |

Learners must explain **which features are hard constraints**. If an option cannot guarantee private networking in the chosen region/SKU, do not score it high just for low price.

### Part B: Select Up to Two Architectures to Test

**Architecture 1 — App Service + Functions**

~~~text
Browser / frontend
       |
       v
App Service: Spring Boot Commerce API
       |
       +-- PostgreSQL Flexible Server via private networking
       +-- Azure Blob Storage
       +-- Azure Service Bus queue
                       |
                       v
               Azure Functions Java worker
~~~

**Architecture 2 — Azure Container Apps**

~~~text
Browser / frontend
       |
       v
Container App: commerce-api
       |
       +-- PostgreSQL Flexible Server via private networking
       +-- Blob Storage
       +-- Service Bus queue
                       |
                       v
               Container App: mail-worker
               (scales by queue when supported)
~~~

**Architecture 3 — AKS** is an optional comparison if the organization already has a cluster/shared platform. Deploying all three is not required as it may incur high cost.

### Part C: Prepare the Local Spring Boot App

Create a simple REST controller:

~~~java
package com.example.commerce;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.time.Instant;
import java.util.Map;

@RestController
public class DemoController {
    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of(
            "service", "commerce-api",
            "timeUtc", Instant.now().toString()
        );
    }
}
~~~

This is **one class** inside an initialized Spring Boot project, not a complete Java project. It needs a main application class, Maven/Gradle, the Spring Web dependency, and Actuator. Do not use the ping endpoint as proof that the whole system connects to the database or meets security requirements.

Configure the health endpoint via Spring Boot Actuator:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true

server:
  port: 8080
  shutdown: graceful
~~~

**Set port 8080 for local/container builds**; when deploying to App Service Java SE, check the hosting runtime's port convention. If the database is not configured yet, the health check only confirms the application process is running, not complete business functionality.

### Part D: Local Testing

~~~bash
# Command requires a valid Maven project
./mvnw -B clean verify
./mvnw spring-boot:run

# Run from another terminal
curl --fail http://localhost:8080/api/ping
curl --fail http://localhost:8080/actuator/health
~~~

Do not run an integration test suite against a real database without test configuration, as the app might accidentally connect to production. Use a local container/test database or an approved mock.

### Part E: Two Ways to Package

**JAR for App Service:**

~~~text
Git -> Maven verify -> executable JAR
                     |
                     v
              App Service Java SE
~~~

**OCI image for Container Apps:**

~~~text
Git -> Maven verify -> Dockerfile -> ACR
                                  |
                                  v
                           Container Apps
~~~

If using the Dockerfile from section 22, ensure the artifact is named **target/support-api.jar** or adjust the COPY instruction to match the project's actual output. Verify the container runs as non-root, has a health endpoint, and exposes port 8080.

### Part F: Sandbox Deployment Trial (If Approved)

1. Choose a lab subscription and resource group; attach **environment, owner, costCenter, deleteAfter** tags.
2. Use organization-approved IaC or Portal guides to create just one trial platform.
3. Set up a staging data source, managed identity, and secret references.
4. Verify the private DNS/network path from the actual app instance.
5. Deploy the tested artifact; record the commit SHA/image digest.
6. Smoke test **/api/ping**, **/actuator/health**, and actual API authentication.
7. Test 2 instances/replicas and perform a rolling/revision deployment.
8. Verify graceful shutdown, logs/traces, and rollback.
9. Run a bounded load test; measure CPU/RAM, p95, and DB connections.
10. Collect cost/limit data and clean up lab resources when finished.

**You do not need to create an AKS cluster just to finish this exercise** if you lack permissions or budget. An ADR backed by a benchmark plan and architecture evidence still achieves the learning objective.

### Part G: Benchmark Matrix to Complete

| Metric | App Service + Functions | Container Apps | Conclusion |
|---|---|---|---|
| Time-to-first-response when warm | Measure in practice | Measure in practice | Per SLO |
| Cold-start after idle | If applicable to model | Measure if minReplicas=0 | UX trade-off |
| P95 latency at 120 req/s | Measure in practice | Measure in practice | Pick meeting target |
| JVM resident memory | Measure in practice | Measure in practice | Sizing |
| Database peak connections | Measure in practice | Measure in practice | Must stay below capacity |
| Verified max scale | Per plan/test | Per plan/test | Do not guess quotas |
| CI/CD rollback | Slot/process test | Revision test | Time to recovery |
| Private network + identity | PASS/FAIL | PASS/FAIL | Must-have |
| Worker queue backlog | Per trigger/worker | Per scale rule | Per SLO |
| Monthly total cost estimate | Based on SKU/usage | Based on SKU/usage | Include downstream |
| Operational effort | Estimate hours/month | Estimate hours/month | TCO |

Do not fill in imagined latency/cost figures and present them as benchmark results. If no live lab is run, record **not measured**, along with assumptions and a measurement plan.

### Part H: Write a One-Page ADR

The exercise deliverable should cover:

1. **Context/requirements**: app type, SLO, team, workloads, compliance.
2. **Options considered**: at least App Service and Container Apps; explain why Functions/AKS/VM were excluded if unsuitable.
3. **Must-have evaluation**: network, JDK, identity, DR, release.
4. **Weighted matrix**, with assumptions/sensitivity analysis.
5. **PoC evidence/cost estimates**, clearly marking unmeasured items.
6. **Decision and trade-offs**, with approving owner.
7. **Deployment/rollback plan**, and future conditions for revisiting the decision.

### Part I: Cleanup

- Delete or stop only the **lab resources you created/own** per policy; do not delete shared resource groups.
- Clean up test images/secrets per retention rules; do not delete production registries or Key Vaults.
- Verify no unexpected plan, environment, node, log ingestion, disk, or NAT charges remain.
- Never commit keys/connection strings; if exposed, rotate them.

## 49. Checklist Before Finalizing the Platform

- [ ] Identified HTTP APIs, workers, schedulers, and distinct workloads.
- [ ] Defined SLO targets, peak load, idle periods, and RTO/RPO.
- [ ] Mapped JDK/Spring Boot/native library/OS dependencies.
- [ ] Checked Azure runtime/JDK support and service lifecycle notices.
- [ ] Avoided defaulting to Azure Spring Apps for new architectures without checking retirement notices.
- [ ] Compared App Service, Container Apps, AKS, Functions, and VMs against the use case.
- [ ] Established must-have security/compliance/region/identity criteria before scoring.
- [ ] Accounted for operational burden and team capabilities.
- [ ] Decided whether the artifact is a JAR/WAR or OCI image and how to scan/sign it.
- [ ] Separated HTTP APIs and background jobs when scaling/lifecycles differ.
- [ ] Tested health checks, readiness/liveness/startup probes, and graceful shutdown.
- [ ] Sized memory/CPU with JVM non-heap headroom.
- [ ] Verified app port/ingress configuration for the chosen platform.
- [ ] Checked inbound vs. outbound private networking and DNS from the workload.
- [ ] Used managed identity/data-plane RBAC and Key Vault where appropriate.
- [ ] Kept secrets out of Git, JARs, container images, and logs.
- [ ] Avoided using ephemeral local disk as source-of-truth or session store.
- [ ] Calculated database connection pools based on max replicas.
- [ ] Configured appropriate autoscale metrics for HTTP/queues/streams and concurrency caps.
- [ ] Defined cold-start budgets and min instances if required by the SLO.
- [ ] Selected deployment/rollback strategies and verified schema compatibility.
- [ ] Established JVM/HTTP/downstream/trace telemetry, alerts, and runbooks.
- [ ] Evaluated zone/region HA, backup/restore, and DR.
- [ ] Calculated TCO including compute, network, database, logs, CI/CD, and staffing.
- [ ] Documented an ADR with conditions to revisit the decision.
- [ ] Created real resources only with approval/budget; cleaned up labs afterward.

## 50. Self-Check Questions

1. Why can you not choose an Azure platform based solely on Java support?
2. How do App Service, Container Apps, AKS, Functions, and VMs differ in self-management level?
3. When is App Service Java SE simpler than containerization?
4. How does sharing an App Service Plan across multiple Web Apps affect sizing?
5. Can you deploy a custom container to App Service?
6. How do a Container Apps environment, app, revision, and replica differ?
7. When is scale-to-zero beneficial, and when does it break a latency SLO?
8. How does KEDA/event-based scaling differ in objective from HTTP/CPU autoscaling?
9. Why is running a Spring Boot web monolith on Azure Functions not as simple as uploading a JAR?
10. When is Functions a good fit for a Java event handler?
11. What requirements genuinely justify AKS?
12. Does a managed Kubernetes control plane eliminate the operations team's patching/node responsibilities?
13. What roles do a Kubernetes Deployment, Service, and Ingress play?
14. How do readiness, liveness, and startup probes differ?
15. Why should a liveness probe not depend too tightly on SQL availability?
16. Why does setting a container memory limit equal to JVM max heap easily cause OOM?
17. When is VM/VMSS still the right choice?
18. What lifecycle factor of Azure Spring Apps must be checked before making a new decision?
19. Can Azure Front Door and API Management replace Spring Boot compute?
20. Why can @Scheduled run multiple times when scaling replicas?
21. How do JARs and OCI images differ in supply chain and patching?
22. Does running a Spring Boot container in Docker automatically make it a stateless app?
23. How does App Service VNet Integration differ from an inbound Private Endpoint?
24. Does enabling managed identity automatically grant data-plane permissions?
25. What problem do Key Vault secret references solve, and what risks remain?
26. Why must database connection pools be calculated against maximum replicas?
27. Why can adding more pods make PostgreSQL slower?
28. How do RTO, RPO, SLO, and SLA differ?
29. Do two replicas automatically guarantee multi-zone HA?
30. How can blue-green/canary/rollback fail due to schema migrations?
31. Why should log ingestion/egress/network costs be included in TCO?
32. Can a weighted decision matrix be used before the compliance screening step?
33. How can a small REST API benefit from AKS if a platform team already exists?
34. If a workload runs only once per night, why is an always-on VM unnecessary?
35. Must a system requiring a private network use AKS?
36. What must be tested when using Container Apps minReplicas=0?
37. Why can a slot swap cause an outage even when the code is completely bug-free?
38. Which metrics should be measured to compare App Service and Container Apps?
39. When a deployment returns HTTP 200, does that prove business functionality works correctly?
40. What situations would trigger revisiting an ADR after six months?

## 51. References

- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview) — PaaS web service.
- [Configure a Java app for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java) — Java runtime, hosting, and configuration.
- [App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — staging, swap, and rollback.
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview) — container apps, environments, scaling.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — versioning and traffic management.
- [Azure Container Apps scale](https://learn.microsoft.com/azure/container-apps/scale-app) — HTTP/event-driven scaling.
- [Azure Container Apps jobs](https://learn.microsoft.com/azure/container-apps/jobs) — scheduled/event-driven jobs.
- [Azure Kubernetes Service overview](https://learn.microsoft.com/azure/aks/intro-kubernetes) — AKS and managed Kubernetes architecture.
- [Kubernetes workload identity on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — service accounts and Entra identity.
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview) — FaaS triggers/hosting models.
- [Java developer guide for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-java) — Java programming model.
- [Azure Virtual Machines overview](https://learn.microsoft.com/azure/virtual-machines/overview) — IaaS and VM operations.
- [Azure Spring Apps documentation and lifecycle information](https://learn.microsoft.com/azure/azure-spring-apps/) — review current retirement/migration notices.
- [Azure Container Registry documentation](https://learn.microsoft.com/azure/container-registry/) — OCI images and artifact security.
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — workload authentication.
- [Azure Private Link documentation](https://learn.microsoft.com/azure/private-link/private-link-overview) — private connectivity and DNS.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html) — health/metrics/production-ready features.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, distributed traces, and alerts.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — cost estimation by region/SKU.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, security, operational excellence, performance, and cost.

**Conclusion:** For Spring Boot on Azure, choose the platform based on **workload and operational responsibilities**, not the "most powerful" label. **App Service** is often practical for REST APIs/JARs needing minimal infrastructure; **Container Apps** suits containerized microservices, background jobs, and flexible scaling; **AKS** belongs where Kubernetes is needed and platform engineering capability exists; **Functions** fits event processing; and **VMs** address specialized OS/legacy requirements. Whichever option you choose, production quality still depends on **identity, private networking, data, JVM resource sizing, health probes, deployment/rollback, observability, and TCO**. Use must-have criteria, a weighted evaluation matrix, PoCs, and ADRs to make evidence-based decisions while checking Azure lifecycles and capabilities at deployment time.
