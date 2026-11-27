# Deploying a Java Application with Deployment and Service

A Java application may run smoothly with **`java -jar`** on a laptop, yet cannot serve users simply by putting a JAR file onto Azure Kubernetes Service (AKS). Kubernetes needs to know **which image to run, how many replicas are needed, which port the process listens on, when the app is ready, and how traffic reaches Pods**. The two foundational resources solving most of this problem are **Deployment** and **Service**.

In this lesson, we build a simple Spring Boot API, package it as a container image, store the image in Azure Container Registry (ACR), deploy it via a Kubernetes Deployment, and create a **ClusterIP** Service for stable access. Next, we test the app, practice rolling updates/rollbacks, and troubleshoot common failures such as ImagePullBackOff, CrashLoopBackOff, and NotReady Pods. Actions that can incur charges or expose public endpoints are cleanly separated from the core hands-on workflow.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, data, deployment, monitoring, protection, and cost control. Here, AKS provides orchestration; ACR manages artifacts; Deployment manages the Pod lifecycle; Service provides a stable endpoint; and identity, networking, and observability policies make Java deployments secure.

After completing this lesson, you can:

- Explain the relationship **Java app → image → registry → Pod → Deployment → Service**.
- Write a minimal Spring Boot application and a Dockerfile to package it into an image.
- Distinguish Deployment, ReplicaSet, Pod, Service, and EndpointSlice.
- Author Deployment/Service manifests with proper labels, selectors, ports, requests/limits, and health probes.
- Configure ACR image-pull permissions using the right identity, without hardcoding registry passwords.
- Deploy and verify the application with **`az`**, **`kubectl`**, **`curl`**, rolling updates, and rollbacks.
- Distinguish a ClusterIP Service from LoadBalancer/Ingress to avoid accidentally exposing apps to the Internet.
- Troubleshoot scheduling, image pull, Java startup, and connectivity issues.

## 1. Overview of Java deployment architecture on AKS

AKS is a managed Kubernetes service on Azure. Azure manages control plane components under the shared responsibility model; operators remain responsible for configuring node pools, access permissions, networking, images, workloads, and security/monitoring controls.

~~~text
Developer / CI pipeline
      |
      | Build + test + package
      v
Java application (JAR)
      |
      | Docker build
      v
Container image: java-api:1.0.0
      |
      | Push
      v
Azure Container Registry (ACR)
      |
      | Kubelet/image pull identity
      v
AKS cluster
  |
  +-- Deployment/java-api
  |     |
  |     +-- ReplicaSet
  |           +-- Pod A --> Java container :8080
  |           +-- Pod B --> Java container :8080
  |
  +-- Service/java-api (ClusterIP :80)
        |
        +-- Selects Pods with label app=java-api
        +-- Forwards traffic to targetPort 8080
~~~

The **image pull** path is separate from the **HTTP request** path. ACR supplies container images when Pods are created/recreated; Service receives requests from in-cluster clients and forwards them to ready Pods. **ACR is not an HTTP load balancer**, and Service does not store JAR files.

### Terms to distinguish

| Concept | Role | Do not confuse with |
|---|---|---|
| **AKS cluster** | Azure-managed Kubernetes environment | Not a single VM |
| **Node** | Machine running Pods, typically in a node pool | Not a container |
| **Pod** | Smallest deployable/schedulable unit, containing one or more containers | Pod IPs/names are ephemeral |
| **Deployment** | Declares desired state for replaceable Pods, supporting rollouts | Does not itself create a fixed client endpoint |
| **ReplicaSet** | Maintains Pod count per template, typically managed by a Deployment | Usually not edited directly when managed by Deployment |
| **Service** | Stable address/endpoint to a set of Pods via selector | Does not build images or guarantee app health |
| **EndpointSlice** | Backend endpoint metadata maintained by controllers | Not where application code deploys |
| **Namespace** | Groups Kubernetes resources for organization/management | Not an absolute security isolation boundary |

## 2. Deployment and Service solve two different problems

### Deployment: maintaining desired state

When you declare **replicas: 2**, the Deployment tries to maintain two Pods matching the template. If one Pod is deleted or a node fails, the controller attempts to create a replacement Pod based on available resources and scheduling constraints.

~~~text
Deployment replicas=2
   |
   +-- Pod 1 Ready
   +-- Pod 2 Ready

Pod 1 lost
   |
   v
Controller creates replacement Pod 3
   |
   +-- Pod 2 Ready
   +-- Pod 3 Pending/Starting -> Ready
~~~

Deployment cannot guarantee two Pods are always running if the cluster runs out of CPU/RAM, cannot pull images, hits quotas, or loses nodes. It provides **reconciliation**, while actual availability depends on capacity and surrounding dependencies.

### Service: stable endpoint for clients

Pods can be recreated with new IPs. If clients hardcode Pod IPs, every rolling update or reschedule breaks connections. A Service provides a **stable DNS name inside the namespace**, routing traffic to Pods matching its selector that are in Ready state per Kubernetes rules.

Example:

~~~text
java-api.java-demo.svc.cluster.local:80
            |
            v
       Service/java-api
        /           \
       v             v
  Pod A:8080     Pod B:8080
~~~

Within the same namespace, clients usually call the short name **java-api:80**. From another namespace, clients can use **java-api.java-demo:80** or the full FQDN.

**A Service is not necessarily public.** This lesson uses **ClusterIP**, which routes only within the cluster network and designed internal paths; to access it from a learner's workstation, we use **`kubectl port-forward`** instead of creating a public load balancer.

## 3. Request flow, labels, and selectors

A Service **does not bind to a Deployment by resource name**. It discovers Pods using declared **labels**.

~~~yaml
template:
  metadata:
    labels:
      app: java-api
~~~

The Service declares:

~~~yaml
spec:
  selector:
    app: java-api
~~~

Only when Pods carry matching labels does the Service find backends. If the Deployment sets **app: order-api** while the Service selects **app: java-api**, the Service exists and gets a ClusterIP, yet has **zero endpoints**, causing requests to fail.

### Three common port fields

| Field | Where it lives | Meaning |
|---|---|---|
| **containerPort: 8080** | Pod/Container spec | Documents the port the app expects to listen on inside the container; declaring it alone does not open a listener |
| **port: 80** | Service spec | Port clients connect to on the Service |
| **targetPort: http** | Service spec | Destination container port; can be a number or a **port name** declared on the Pod |

Example: **Service port 80 → targetPort http → containerPort 8080**. The Java application must actually bind to **0.0.0.0:8080** (or an appropriate interface); writing `containerPort` in YAML alone will not make Java listen on that port.

## 4. Preparing a safe environment

To practice on real Azure resources, you need:

- An authorized **lab subscription** with budget/cost rules.
- An **existing AKS cluster** with a node pool sized for at least two sample Pods.
- An **existing ACR** with a repository for the demo image, or an approved dedicated lab registry.
- Appropriate permissions to view AKS, fetch kubeconfig, create Deployments/Services in the lab namespace, and push images to ACR.
- Azure CLI (**`az`**), **`kubectl`**, Java/Maven, and Docker or a compatible OCI builder if building locally.
- Network reachability to the AKS control plane, ACR login/data endpoints, and the lab namespace.

**Creating a brand-new AKS cluster is not mandatory to learn Deployment and Service.** Clusters, node pools, public IPs, storage, ACR, and Azure Monitor incur costs. Without a sandbox, you can still study the Java/YAML code and complete the analytical sections without touching cloud resources.

### Distinguishing three permission groups

1. **Azure management plane:** permissions to view/edit clusters, registries, and Azure resources.
2. **Kubernetes authorization:** permissions to create/view/edit Deployments, Services, and Pods in a namespace; usually Kubernetes RBAC or Azure RBAC for Kubernetes.
3. **ACR data plane:** permissions to push/pull images; not automatically granted just because a user administers AKS.

An account with cluster **Reader** may not be able to create Deployments. Someone allowed to push images may not be able to edit Kubernetes Services.

## 5. Building a sample Spring Boot Java application

To keep the lesson self-contained, we use a Spring Boot API with endpoint **`/api/hello`**, while **Spring Boot Actuator** exposes health endpoints for Kubernetes probes. The example uses Java 21 and Maven; real applications may use other organization-approved Java/Spring Boot versions.

### Project structure

~~~text
aks-java-demo/
├── pom.xml
├── Dockerfile
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/aksdemo/
│       │       └── AksDemoApplication.java
│       └── resources/
│           └── application.properties
└── k8s/
    └── java-api.yaml
~~~

These files are **examples for learners to create in a practice environment**, not files generated by this Markdown guide.

### Maven configuration (`pom.xml`)

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aks-java-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
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
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot **3.5.7** is simply a pinned reproducible version at authoring time; for real deployments, verify a **currently supported, security-patched** release and keep the pipeline aligned. Never copy tutorial tags or dependency versions verbatim as permanent production policies.

### Java source code

Save as **`src/main/java/com/example/aksdemo/AksDemoApplication.java`**:

~~~java
package com.example.aksdemo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AksDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AksDemoApplication.class, args);
    }
}

@RestController
class HelloController {
    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        String message = System.getenv()
            .getOrDefault("APP_MESSAGE", "Hello from AKS");
        return Map.of("message", message);
    }
}
~~~

This API reads a non-sensitive environment variable **`APP_MESSAGE`**, illustrating environment-specific configuration without rebuilding an image per message.

### Spring Boot configuration

Save as **`src/main/resources/application.properties`**:

~~~properties
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

With **`spring-boot-starter-actuator`** and probes enabled, Spring Boot exposes:

- **GET `/actuator/health/liveness`**: is the application process healthy at application level?
- **GET `/actuator/health/readiness`**: is the application ready to serve requests per Spring Boot state?
- **GET `/api/hello`**: sample business endpoint.

Supported health endpoints and exact paths depend on the Spring Boot version and Actuator config. Do not configure these paths in manifests if your app lacks Actuator or changes the management base path.

### Testing Java locally before containerizing

In the project folder:

~~~bash
mvn -B test
mvn -B package
java -jar target/aks-java-demo-1.0.0.jar
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/liveness
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

Expect `/api/hello` to return JSON containing **`message`**, and both health endpoints to return healthy status once the app boots. In real systems, add comprehensive unit and integration tests for business logic rather than checking hello alone.

## 6. Creating a Dockerfile for the Java application

Kubernetes does not deploy raw JAR files directly: it runs containers from declared images. A multi-stage Dockerfile separates the Maven build environment from a lean JRE runtime image.

~~~dockerfile
# Stage 1: build JAR
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml ./
COPY src ./src
RUN mvn -B -DskipTests package

# Stage 2: lean runtime
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 /build/target/*.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

### Key points to understand

1. **Build stage:** uses JDK/Maven to compile and package the JAR. Skipping tests inside the Docker build avoids duplicating work after CI runs **`mvn test`**; production pipelines must still block builds on test failures.
2. **Runtime stage:** uses a Java 21 JRE without shipping Maven or build tools into the final image.
3. **Non-root user:** runs under UID/GID **10001** to limit impact if a container is compromised.
4. **EXPOSE 8080:** documents the expected port; **does not create a listener**. Spring Boot is already configured to listen on 8080.
5. **ENTRYPOINT:** starts the Java process as the primary container process; Kubernetes tracks container lifecycle through it.
6. **Pin base images:** production should use trusted, vulnerability-scanned base images pinned by digest/internal policy; example tags do not guarantee freshness or safety.
7. **File permissions:** if the app writes temporary files, provide writable directories/volumes matching the non-root user instead of reverting to root to bypass permission errors.

Maven's parent POM produces an executable Spring Boot JAR via the configured plugin. If your project outputs multiple **`.jar`** files or uses Gradle, adjust **`COPY`** to select the exact artifact rather than relying on wildcards.

### Testing the container locally before AKS

~~~bash
docker build -t aks-java-demo:1.0.0 .
docker run --rm -p 8080:8080 \
  -e APP_MESSAGE="Hello from local container" \
  aks-java-demo:1.0.0
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

If the container fails locally, **do not push it to AKS hoping for luck**. Verify Java version, main class, artifact path, ports, and container logs first.

## 7. Pushing the image to Azure Container Registry

ACR provides a private registry for AKS to pull images using an authorized identity. Assuming a lab registry named **`acrjavalab`** (illustrative only), the full image reference looks like:

~~~text
acrjavalab.azurecr.io/java-api:1.0.0
~~~

**The registry name must exist and be valid**; never create resources using placeholder names verbatim. A registry holds the **`java-api` repository**, tag **`1.0.0`**, and its manifest digest.

### Sign in to Azure and inspect the registry

These commands use Bash in Azure Cloud Shell or a terminal with Azure CLI and Docker:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"
az account show --output table

ACR="<EXISTING_ACR_NAME>"
LOGIN_SERVER=$(az acr show \
  --name "$ACR" \
  --query loginServer \
  --output tsv)

echo "$LOGIN_SERVER"
~~~

Target an authorized registry and verify its login server. **Do not create registries or enable the admin account** unless needed and approved.

### Build, tag, and push

~~~bash
az acr login --name "$ACR"

docker build \
  -t "$LOGIN_SERVER/java-api:1.0.0" \
  .

docker push "$LOGIN_SERVER/java-api:1.0.0"
~~~

This requires a running Docker daemon, push permissions, and network connectivity to ACR. If Docker is unavailable locally, consider **`az acr build`** in an authorized environment; note ACR Tasks has constraints when registries disable public networking.

Verify the repository:

~~~bash
az acr repository show-tags \
  --name "$ACR" \
  --repository java-api \
  --output table
~~~

### Tags and digests

**Tags** are human-friendly yet can point to different contents if overwritten. **Digests** immutably identify manifests for consistent releases:

~~~text
<ACR_LOGIN_SERVER>/java-api:1.0.0
<ACR_LOGIN_SERVER>/java-api@sha256:<MANIFEST_DIGEST>
~~~

In production, use immutable release tags and/or pin by digest. Record digests alongside source commits, SBOMs, and security scan results. An image appearing in a registry does not prove it is vulnerability-free or built for your node pool's CPU architecture.

## 8. Which permissions let AKS pull images from ACR?

A common pitfall: **the user running `kubectl apply` is not the identity that pulls container images**.

In AKS, image pulls for Pods are typically performed by the **kubelet/node identity** per cluster configuration. The application identity used to call Azure Key Vault, Storage, or databases is a **separate concern** from the identity pulling images from ACR.

### With ACR using standard registry-level RBAC

In the **RBAC Registry Permissions** model, the kubelet identity or matching service principal needs the **`AcrPull`** role at the registry scope. Eligible AKS setups can attach ACR via:

~~~bash
az aks update \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --attach-acr "<ACR_NAME_OR_RESOURCE_ID>"
~~~

**Do not run this blindly**: it alters cluster integration/permissions and requires Azure permissions plus AKS/ACR owner approval. Also, if ACR uses **RBAC Registry + ABAC Repository Permissions**, registry-wide **`--attach-acr`** has limitations and must not replace assigning repository roles under the new mode.

### With ACR repository-level permissions

Registries using **ABAC Repository Permissions** require repository-scoped roles and conditions, such as **Container Registry Repository Reader** for repository **`java-api`** where supported. Catalog/list permissions may also be needed for certain operations. Never assign **`AcrPull`** and assume it works across every mode.

### Avoid registry admin passwords

Never enable the ACR admin user just to clear **`ImagePullBackOff`**. Over-broad registry credentials can leak through manifests, logs, or secrets and are difficult to audit per workload. If an `imagePullSecret` is strictly required where managed identity is unsupported, narrow its scope/lifetime, store it securely, and plan rotation.

### Networking must also work

Valid pull permissions fail if AKS nodes cannot reach the registry:

- Does ACR use a public endpoint with firewall rules? Are node egress IPs allowed?
- Does ACR use a **Private Endpoint**? Do login and data endpoints resolve properly via DNS from the VNet/nodes?
- Do NSGs, routes, proxies, and egress firewalls allow traffic to the registry?
- Does the image exist with the exact tag/digest and matching CPU architecture?

If ACR uses geo-replication, test pull connectivity from each workload region rather than merely checking replica status.

## 9. Connecting kubectl to an existing AKS cluster

In your lab environment:

~~~bash
RG="<AKS_RESOURCE_GROUP>"
AKS="<EXISTING_AKS_CLUSTER>"

az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl config current-context
kubectl cluster-info
kubectl get nodes
~~~

**`az aks get-credentials`** updates your local kubeconfig/context and may switch the default context. **Always verify `current-context` before running `kubectl apply` or `delete`** so you do not touch production.

If the cluster uses a private API server, the machine running kubectl must have a valid network path (VPN, bastion, jump host, or in-VNet runner). If authorization fails, check **Azure auth / Kubernetes RBAC** instead of reflexively requesting `cluster-admin`.

### Use a dedicated lab namespace

~~~bash
kubectl create namespace java-demo
kubectl get namespace java-demo
~~~

If the namespace already exists, do not recreate it; check who owns it before deploying. Namespaces organize resources and quotas, but **do not isolate networking or permissions automatically** without NetworkPolicies and RBAC.

## 10. Writing a ConfigMap for non-sensitive configuration

The Java app reads **`APP_MESSAGE`** from an environment variable. A Kubernetes **ConfigMap** fits non-sensitive values:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: java-api-config
  namespace: java-demo
data:
  APP_MESSAGE: "Hello from AKS Deployment"
~~~

ConfigMaps are mounted as files or injected as environment variables per Pod spec. In the next section, we use **`envFrom.configMapRef`** to map its keys.

**Never store database passwords, API keys, certificate private keys, or tokens in a ConfigMap.** Even Kubernetes Secrets are not automatically end-to-end protected from every threat; govern encryption at rest, RBAC, and Azure Key Vault / Workload Identity integration where appropriate.

When ConfigMap keys are injected as **environment variables**, editing the ConfigMap later **does not automatically update environment variables inside running Pods**. Perform a controlled rollout/restart so new Pods pick up updated values.

## 11. Writing a complete Deployment

This Deployment runs **two replicas** of the API using the ACR image, health probes, and illustrative CPU/RAM allocations.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-api
  namespace: java-demo
  labels:
    app: java-api
spec:
  replicas: 2
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: java-api
  template:
    metadata:
      labels:
        app: java-api
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: java-api
          image: <ACR_LOGIN_SERVER>/java-api:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          envFrom:
            - configMapRef:
                name: java-api-config
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
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 10001
            capabilities:
              drop:
                - ALL
~~~

**Before running:** replace **`<ACR_LOGIN_SERVER>`** with the real login server, e.g., **`myregistry.azurecr.io`**. Kubernetes does not resolve placeholders. Never copy this manifest straight to production without tuning image digests, requests/limits, probes, security policies, and real requirements.

### Explaining key fields

| Field | Meaning |
|---|---|
| **`apiVersion: apps/v1`** | Kubernetes API version for Deployment |
| **`replicas: 2`** | Desired Pod count; not a guarantee two Pods are always Ready |
| **`selector.matchLabels`** | Rule identifying Pods owned by the Deployment; must match template labels |
| **`template.spec.containers.image`** | Container image pulled onto the node by kubelet |
| **`imagePullPolicy: IfNotPresent`** | Allows kubelet to reuse a matching cached image on the node |
| **`ports.name: http`** | Named port referenced by Service and probes |
| **`envFrom.configMapRef`** | Injects ConfigMap keys as container environment variables |
| **`requests`** | CPU/RAM values used by the scheduler to place Pods onto nodes |
| **`limits`** | Runtime resource caps; exceeding RAM limits can trigger OOMKilled |
| **`startupProbe`** | Gives slow-starting apps boot time before liveness/readiness take over |
| **`readinessProbe`** | Controls whether the Pod is marked ready to receive Service traffic |
| **`livenessProbe`** | Helps kubelet detect stuck processes and restart containers |
| **`securityContext`** | Minimizes container process privileges |

### Requests, limits, and Java memory

**`cpu: 250m`** requests **0.25 vCPU** from the scheduler. **`memory: 512Mi`** sets the memory request. **`memory` limit `1Gi`** caps total container memory, **not just the Java heap**.

A JVM process consumes additional memory outside the heap for metaspace, code cache, thread stacks, direct buffers, and native libraries. Setting **`-Xmx`** equal to the container memory limit can cause **`OOMKilled`** even if heap usage looks fine.

Size based on real heap + native memory, load tests, GC tuning, and live metrics. Modern Java is container-aware, yet **never replaces measuring memory and tuning requests/limits**.

### Why have a separate `startupProbe`?

Spring Boot needs time to start the JVM, load classes, and initialize beans. An overly aggressive liveness probe can cause Kubernetes to kill and restart the app continuously before startup completes.

In the sample manifest, `startupProbe` checks every 10 seconds with **`failureThreshold: 30`**. The initial startup window spans roughly a few minutes depending on cadence, timeout, and kubelet behavior; **it is not a strict 300-second guarantee in every scenario**. While `startupProbe` has not yet succeeded, Kubernetes holds off running liveness and readiness probes.

Do not set enormous thresholds just to hide permanent startup bugs; optimize startup time and diagnose unavailable dependencies.

## 12. Writing a ClusterIP Service

The Service below exposes **port 80**, forwarding to the Pod's named port **`http`** (8080):

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: java-api
  namespace: java-demo
spec:
  type: ClusterIP
  selector:
    app: java-api
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
~~~

Kubernetes assigns a ClusterIP from the Service CIDR. Its internal DNS name is:

~~~text
java-api.java-demo.svc.cluster.local
~~~

Another Pod in the same namespace can call:

~~~text
http://java-api/api/hello
~~~

**Services select Pods strictly by labels.** Even with matching selectors, if zero Pods are **Ready**, the Service has no ready endpoints to serve traffic. Never change `targetPort` randomly if the API hasn't started yet; inspect Java logs, container ports, and endpoints together.

### ClusterIP does not create a public endpoint

With **`ClusterIP`**, no Azure Load Balancer public IP is provisioned by this Service. To expose an API to Internet users, evaluate an **Ingress** with an ingress controller/Gateway API, **Azure Application Gateway**, or a **`LoadBalancer`** Service per architecture. Those options require dedicated TLS, domains, authentication, WAF, and security controls.

In this exercise, **a public LoadBalancer is unnecessary**: **`kubectl port-forward`** is enough for verification.

## 13. Combined manifest and apply order

In practice, you can store all three resources in **`k8s/java-api.yaml`**, separated by **`---`** in order:

~~~text
1. ConfigMap/java-api-config
---
2. Deployment/java-api
---
3. Service/java-api
~~~

When applied, the Kubernetes API processes each resource. Placing ConfigMap before Deployment avoids missing-config errors and improves readability in learning materials. Controllers reconcile objects asynchronously as they appear; apply succeeding does not prove the app is Ready.

### Validate manifests before deploying

After creating the namespace and saving the manifest:

~~~bash
kubectl apply \
  --dry-run=client \
  --validate=true \
  -f k8s/java-api.yaml
~~~

This catches many syntax/schema errors at client/server discovery level depending on kubectl version. It **does not** verify image pulls, node capacity, Probe URLs, registry permissions, or service connectivity.

In production pipelines, add schema/policy validation, image scanning, IaC reviews, and staging tests.

## 14. Applying the Deployment and Service to AKS

Assuming namespace **`java-demo`** exists, the login server placeholder was replaced, the image was pushed, and AKS holds pull permissions:

~~~bash
kubectl apply -f k8s/java-api.yaml

kubectl get deployment -n java-demo
kubectl get pods -n java-demo -l app=java-api -o wide
kubectl get service -n java-demo java-api
~~~

Watch the rollout:

~~~bash
kubectl rollout status \
  deployment/java-api \
  -n java-demo \
  --timeout=180s
~~~

If the rollout stalls, **do not immediately bump timeouts or replica counts**. Inspect Pending, ImagePullBackOff, CrashLoopBackOff, NotReady Pods, and Kubernetes events to find the root cause.

### Verify the Service → Pod path

~~~bash
kubectl get endpointslice \
  -n java-demo \
  -l kubernetes.io/service-name=java-api
~~~

EndpointSlices are maintained by controllers to track backend endpoints. To inspect addresses and readiness details:

~~~bash
kubectl describe service java-api -n java-demo
kubectl get pods -n java-demo -l app=java-api --show-labels
~~~

If the Service lacks backends, check **selectors**, labels, readiness, and `targetPort`. Having Running replicas in a Deployment **is not enough** to prove the Service is receiving endpoints.

## 15. Accessing the application via `kubectl port-forward`

Instead of exposing a public service, run:

~~~bash
kubectl port-forward \
  -n java-demo \
  service/java-api \
  8080:80
~~~

Keep that terminal open, and in another terminal run:

~~~bash
curl -fsS http://localhost:8080/api/hello
curl -fsS http://localhost:8080/actuator/health/liveness
curl -fsS http://localhost:8080/actuator/health/readiness
~~~

Expected hello output:

~~~json
{"message":"Hello from AKS Deployment"}
~~~

**`port-forward`** is a debugging/practice tunnel, not a production ingress solution. The session disconnects if the forwarded Pod is replaced, and it does not test load balancing across both Pods. If local port 8080 is already busy, pick another local port.

### In-cluster verification

With appropriate permissions and security controls, a client Pod in the same namespace can call the Service using internal DNS. Microservices inside the same cluster never need public IPs to talk to each other.

If running an ephemeral debug Pod, use an organization-approved image complying with network/security policies. **Never launch unverified diagnostic images in production AKS** merely for a convenient `curl` binary.

## 16. Health probes: liveness, readiness, and startup

The three probes check three distinct questions:

| Probe | When it fails repeatedly | Design approach |
|---|---|---|
| **Startup** | Container may be restarted if failure threshold is exceeded | Give JVM/framework startup a realistic window |
| **Readiness** | Pod is marked unready to receive Service traffic | Reflects ability to serve requests in its role |
| **Liveness** | Kubelet may restart the container | Check only unrecoverable process hangs; avoid flaky external dependencies |

With Spring Boot Actuator, note that basic **`readinessState`** does not automatically include every external database or queue in all setups. If the app cannot serve traffic when a DB drops, define readiness carefully—but avoid tying liveness to external services, which triggers **restart storms**.

### Example of a common mistake

An API depends on a database. Its liveness probe runs an SQL query; the database blips for 30 seconds, causing Kubernetes to restart every Pod and prolong recovery. Better design:

- **Liveness:** confirms the app is not deadlocked or wedged internally.
- **Readiness:** stops receiving traffic when critical business dependencies cannot be served.
- **Monitoring:** tracks database health independently and fires alerts.

Probe endpoints must be lightweight, read-only, and never expose stack traces, credentials, or sensitive system details.

## 17. Rolling updates with Deployment

A Deployment with **`RollingUpdate`** gradually replaces old Pods with new Pods.

~~~text
Before update:
  Pod A: v1.0.0 Ready
  Pod B: v1.0.0 Ready

Rollout:
  Pod C: v1.0.1 Starting -> Ready
  Pod A: v1.0.0 Terminating
  Pod D: v1.0.1 Starting -> Ready
  Pod B: v1.0.0 Terminating

After update:
  Pod C: v1.0.1 Ready
  Pod D: v1.0.1 Ready
~~~

This is an illustrative sequence; actual Pod ordering can vary.

### `maxSurge` and `maxUnavailable`

In the manifest:

~~~yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
~~~

With **`replicas: 2`**, the controller can spin up at most one extra Pod above desired count during an update while avoiding dropping available Pods below desired rules. However, **zero downtime is not guaranteed** if nodes fail, readiness is misconfigured, clients hold long-lived connections, or the app ignores graceful shutdown.

**`maxSurge=1` requires extra node capacity.** If node pools are full, the new Pod stays Pending and the rollout stalls. Cluster autoscaler or spare capacity helps, though autoscaling takes time and respects quotas.

### Updating the image for rollout

After building/pushing **`java-api:1.0.1`**:

~~~bash
kubectl set image \
  deployment/java-api \
  java-api="<ACR_LOGIN_SERVER>/java-api:1.0.1" \
  -n java-demo

kubectl rollout status \
  deployment/java-api \
  -n java-demo \
  --timeout=180s
~~~

**Drift warning:** **`kubectl set image`** mutates the live Deployment; if your Git manifest still specifies the old image, the next **`kubectl apply` or GitOps sync** will revert it. In declarative workflows, update the **source manifest / Helm values** and let the pipeline sync.

### Rollback

Check revision history:

~~~bash
kubectl rollout history deployment/java-api -n java-demo
~~~

If the new version fails and the Deployment retains prior revisions:

~~~bash
kubectl rollout undo deployment/java-api -n java-demo
kubectl rollout status deployment/java-api -n java-demo
~~~

A Deployment rollback restores the previous **Pod template**; it **does not roll back database schemas, written data, or external secrets/configs**. Schema-changing releases therefore require backward compatibility and separate data recovery plans.

## 18. Scaling and availability

Manual scaling:

~~~bash
kubectl scale deployment/java-api \
  -n java-demo \
  --replicas=3

kubectl get deployment java-api -n java-demo
~~~

This updates desired replicas, while actual Running/Ready Pods depend on node capacity, quotas, networking, image pulls, and probes. Adding Pods does not speed up databases or increase downstream connection capacity.

### Horizontal Pod Autoscaler (HPA)

In production, **HPA** scales replicas based on CPU, memory, or custom/external metrics when a metrics pipeline is available. HPA **does not appear automatically** just because a Deployment sets requests/limits.

When using HPA, avoid concurrently modifying replicas manually or via GitOps without tracking which controller owns **`spec.replicas`**. Scaling to many Pods also increases database connections, request concurrency, and costs.

### PodDisruptionBudget and node distribution

Having two Pods in a Deployment does not guarantee placement on two different nodes or zones. To improve fault tolerance, consider:

- Node pools with enough nodes spanning multiple Availability Zones where supported by AKS.
- **`topologySpreadConstraints`** or affinity/anti-affinity to spread Pods.
- **`PodDisruptionBudget (PDB)`** to bound voluntary disruptions.
- Proper readiness, `terminationGracePeriodSeconds`, and graceful shutdown handling.

A PDB limits certain **voluntary evictions**, but does not prevent involuntary node/zone failures or create extra capacity.

## 19. Service types: when to use which?

| Service type | Access point | Common use cases |
|---|---|---|
| **ClusterIP** | Internal Kubernetes IP/DNS | Internal microservices, APIs behind an ingress |
| **NodePort** | Port opened on nodes per Kubernetes model | Targeted integration/test paths; rarely final Internet ingress |
| **LoadBalancer** | Provisions cloud load balancer per AKS config | TCP/UDP services needing an external or internal LB endpoint |
| **ExternalName** | CNAME DNS alias | Maps a service name to another DNS name; no proxy or Pod backends |

### Should you use LoadBalancer for a Java API?

In a lab testing Internet access, a **`LoadBalancer`** Service works, though it provisions an Azure Load Balancer / public IP, adding cost and exposure. In production, evaluate an **ingress controller / Gateway API**, **Azure Application Gateway / Application Gateway for Containers**, or **Azure Front Door** first—especially when needing multiple hosts/paths, TLS/WAF, and centralized policies.

**Conceptual example** for LoadBalancer:

~~~yaml
spec:
  type: LoadBalancer
  selector:
    app: java-api
  ports:
    - port: 80
      targetPort: http
~~~

This snippet is **not a complete manifest** and you do not need to deploy it. Never switch a production Service from ClusterIP to LoadBalancer without defining public/private annotations, IP SKU, TLS, firewalls, ingress, and budget.

### Can any Pod reach a ClusterIP Service?

ClusterIP exposes no public IP by default, yet **does not block other Pods in the cluster from calling it**. To govern east-west traffic, enforce NetworkPolicies supported by AKS/network plugins alongside service-level authentication and authorization inside the Java API.

A Service only performs network forwarding; it does not validate user tokens or enforce API business authorization.

## 20. Configuration: ConfigMap, Secret, and Azure Key Vault

### Non-sensitive configuration via ConfigMap

You already saw **`APP_MESSAGE`** in a ConfigMap. For settings like `LOG_LEVEL` or `FEATURE_X_ENABLED`, ConfigMaps decouple code/images from deployment environments.

Example of a Java API needing dependency config:

~~~text
ORDER_SERVICE_URL=http://order-service.internal
LOG_LEVEL=INFO
APP_MESSAGE=Hello from AKS
~~~

**Never rely on an env var containing a hostname to create access control.** Networking, DNS, and identity must still be configured properly.

### Secrets and sensitive data management

Never put passwords or tokens in ConfigMaps, Dockerfiles, repo manifests, or CLI commands saved in shell history. Kubernetes Secrets also require RBAC, encryption at rest, and secure injection.

On Azure, consider the **Azure Key Vault Secrets Store CSI Driver** paired with **Microsoft Entra Workload ID** where supported by AKS and the app. Conceptual flow:

~~~text
Java Pod (Kubernetes service account)
     |
     | Workload identity federation / workload ID
     v
Microsoft Entra ID
     |
     v
Azure Key Vault
     |
     v
Secrets consumed by app per designed integration
~~~

**The workload identity reading Key Vault is not necessarily the kubelet identity pulling images from ACR.** Never grant registry push rights to a Java Pod just because it reads secrets from Key Vault.

### When do ConfigMap changes take effect?

When using **`envFrom`**, Pods read environment variables at container startup. After updating a ConfigMap, perform a controlled rollout restart:

~~~bash
kubectl rollout restart deployment/java-api -n java-demo
kubectl rollout status deployment/java-api -n java-demo
~~~

In production, restarting multiple Pods requires spare capacity and proper readiness probes. When ConfigMaps are mounted as volumes, refresh behavior differs from env vars and depends on how the app reloads configuration.

## 21. Observing Java applications on AKS

Inspect resources top-down:

~~~bash
kubectl get deployment java-api -n java-demo
kubectl get replicaset -n java-demo -l app=java-api
kubectl get pods -n java-demo -l app=java-api -o wide
kubectl get service java-api -n java-demo
kubectl get endpointslice -n java-demo \
  -l kubernetes.io/service-name=java-api
~~~

### Inspecting logs

~~~bash
kubectl logs -n java-demo \
  -l app=java-api \
  --all-containers=true \
  --tail=100 \
  --prefix=true
~~~

Logs reveal Spring Boot startup, exceptions, listening ports, and business traces. Avoid logging access tokens, passwords, and user PII.

### Describe and events

When a Pod is Pending/NotReady:

~~~bash
kubectl describe deployment java-api -n java-demo
kubectl get pods -n java-demo -l app=java-api
kubectl get events -n java-demo \
  --sort-by=.metadata.creationTimestamp
~~~

To inspect a specific Pod:

~~~bash
kubectl describe pod <POD_NAME> -n java-demo
kubectl logs <POD_NAME> -n java-demo --previous
~~~

**`--previous`** only returns logs when a prior container instance exists inside that Pod; it helps for CrashLoopBackOff, though logs won't exist if a fresh Pod has never restarted.

### Azure Monitor and Application Insights

In production, evaluate **Azure Monitor managed service for Prometheus**, Container Insights, and **Application Insights / OpenTelemetry** as needed to capture metrics, logs/traces, and correlation across Pods, Services, and backends.

These tools require explicit configuration, permissions, and budget; **AKS does not automatically collect all JVM metrics or business traces** merely by existing.

## 22. Common errors when deploying Java

| Symptom | Possible cause | How to check |
|---|---|---|
| **ImagePullBackOff / ErrImagePull** | Wrong registry/image/tag, missing pull role, ACR firewall/DNS, CPU architecture mismatch | Pod events, kubelet identity, ACR permissions, network, tag/digest |
| **CrashLoopBackOff** | Java process exits due to missing config, classpath error, wrong JAR, OOM, or startup error | Current/`--previous` logs, exit code, runtime config |
| **OOMKilled** | Container exceeds memory limit; heap/native memory too high | `kubectl describe pod`, limits, JVM metrics |
| **Pending** | Insufficient CPU/RAM/nodes, quotas, taints/tolerations, zone/affinity | Scheduler events, node capacity, requests |
| **Running yet NotReady** | Readiness URL 404/503, app still starting, required dependency failing | Probe settings, logs, status, endpoint URL |
| **Service has ClusterIP yet unreachable** | Selector mismatch, zero ready endpoints, wrong `targetPort`, network policy | Labels, EndpointSlice, Service describe |
| **Port-forward connects then fails** | No Ready matching Pod, app not listening, local port busy | Port-forward output, Pods, target port |
| **HTTP 404 on `/actuator/health/readiness`** | Missing Actuator, wrong base path, or probes disabled | POM, Spring Boot config, startup logs |
| **HTTP 500** | App exception, database error, dependency or logic bug | App logs, traces, request correlation |
| **Rollout stuck** | New Pods not Ready or `maxSurge` lacks capacity | Rollout status, describe, Pod events |
| **2 replicas yet outage on node failure** | Both Pods landed on one node/zone; insufficient spare capacity | Pod placement, topology spread, node pools |
| **Stale config after editing ConfigMap** | `envFrom` does not update running Pods automatically | Rollout restart and inspect environment safely |
| **Works locally, fails on AKS** | Java version/CPU mismatch, filesystem permissions, env/secrets, or port | Image metadata, non-root user, logs |
| **Rollout undo fails to fix DB error** | Schema migration or data writes were not rolled back with Deployment | Database recovery plan and compatibility |

**Never change multiple layers at once.** Pick one hypothesis from events/logs, apply one reversible change, and re-verify.

## 23. Scenario A: ImagePullBackOff from private ACR

**Scenario:** pipeline pushes the image cleanly and Deployment applies, yet Pods show:

~~~text
STATUS: ImagePullBackOff
Failed to pull image ".../java-api:1.0.0"
~~~

### Step-by-step troubleshooting

1. Verify the image reference in the Deployment matches exact registry login server, repository, and tag/digest.
2. Run **`kubectl describe pod`** to read the exact message: **unauthorized**, **manifest unknown**, **DNS timeout**, or another registry error.
3. Verify the kubelet identity and **ACR role assignment permissions mode**.
4. For standard registry RBAC, check **`AcrPull`** on the right principal. For ABAC, check supported repository reader roles/conditions.
5. For private registries, check ACR login/data endpoints, Private DNS, egress/firewalls, and routing from AKS nodes.
6. Confirm the manifest exists and supports the node pool's CPU architecture.
7. Retry rollout after fixing the root cause and document the change.

**Never enable public access or admin passwords on production ACR** just because Pods failed to pull images. Separate identity, network, and artifact faults.

## 24. Scenario B: Spring Boot runs yet Service has no backends

**Scenario:** two Pods are Running and Service `java-api` has a ClusterIP, yet calling the Service fails.

### Diagnostic questions

- Are Pods **`READY 1/1`** or merely **`STATUS Running`**?
- Does **`kubectl get endpointslice`** show ready endpoints?
- Does Service selector **`app=java-api`** match Pod labels?
- Is Spring Boot actually listening on **8080**?
- Does Service **`targetPort: http`** match the container port name **`http`**?
- Does **`/actuator/health/readiness`** exist and return HTTP 200?
- Is a NetworkPolicy blocking client → Pod traffic?

If endpoints are unready because Actuator is missing, fix dependencies/config/probes properly. **Never delete `readinessProbe` just to make a Deployment appear green** when the app isn't ready for traffic.

## 25. Scenario C: Java OOMKilled after scaling

**Scenario:** the app runs locally, and on AKS each Pod has a **`512Mi`** memory limit, yet the JVM uses significant heap and native memory. Kubelet records `OOMKilled`.

### Remediation steps

1. Inspect **`kubectl describe pod`**, container `lastState`/exit reason, metrics, and logs.
2. Check memory limits, heap flags, thread counts, direct buffers, and class loading.
3. Benchmark production-like load and measure peak/percentile memory usage.
4. Shrink Java memory footprint or raise memory requests/limits with justification while checking node capacity.
5. Verify Java 21 container awareness / JVM ergonomics; never set **`-Xmx`** equal to the full container limit.
6. Tune concurrency/connection pools and investigate memory leaks if needed.

**Scaling out more Pods does not fix a memory leak** inside each Pod. If every Pod still OOMs, adding replicas simply multiplies failures and cost.

## 26. Complete hands-on exercise on AKS lab

### Goals and boundaries

This exercise creates a Java app, builds an image, pushes to ACR, deploys two Pods via Deployment, and verifies via a ClusterIP Service. Use only **existing or authorized lab clusters/registries**. Never run cluster deletion commands, subscription-wide ACR role changes, or open public LoadBalancers outside approved scope.

### Steps

1. Create the Maven project per section 5 and Dockerfile per section 6.
2. Run local **`mvn test`**, **`mvn package`**, **`docker build/run`**, and test **`/api/hello`** plus both health endpoints.
3. Sign in to Azure, select the lab subscription, capture ACR login server, and build/push **`java-api:1.0.0`**.
4. Check AKS kubeconfig context; confirm you target the **lab cluster**.
5. Create namespace **`java-demo`** if it does not exist and you have permission.
6. Save **`k8s/java-api.yaml`** containing **`ConfigMap`**, **`Deployment`**, and **`Service`** from sections 10–12 separated by **`---`**.
7. Replace **`<ACR_LOGIN_SERVER>`** with the valid registry hostname.
8. Verify AKS's image-pull identity has permissions matching the registry mode and network reachability to ACR works.
9. Run **`kubectl apply --dry-run=client --validate=true -f k8s/java-api.yaml`**, then **`kubectl apply -f k8s/java-api.yaml`**.
10. Watch **`kubectl rollout status`**, confirming **2/2** available replicas if cluster capacity permits.
11. Inspect **`Service`**, **`EndpointSlice`**, and **Pod labels/readiness**.
12. Run **`kubectl port-forward -n java-demo service/java-api 8080:80`** and **`curl /api/hello`**.
13. Update ConfigMap `APP_MESSAGE` and run **`kubectl rollout restart`** if permitted; verify the updated value.
14. Build/push version **`1.0.1`**, update the manifest image, roll out, and verify; rehearse rollback in the lab if needed.
15. Record any errors and costs incurred, and clean up **only resources created by this lab**.

### Verification checklist

| Item | Result to verify |
|---|---|
| Artifact | Runnable JAR; Docker image with tag/digest |
| Registry | Repository `java-api` holds the pushed release |
| Identity | AKS kubelet holds least-privilege pull permission |
| Deployment | 2 desired replicas with right image/ports/probes |
| Pods | 2 Pods Running **and Ready** (given cluster capacity) |
| Service | ClusterIP :80; selector `app=java-api` |
| EndpointSlice | Shows matching ready endpoints |
| HTTP | `/api/hello` returns JSON and `/actuator/health/readiness` succeeds |
| Rollout | New version deployed; know how to undo if needed |
| Security | No public LB, no hardcoded secrets, non-root container |
| Cost | Documented used resources and cleanup plan |

### Safe cleanup

If the manifest contains **only the three resources from this exercise**:

~~~bash
kubectl delete -f k8s/java-api.yaml

kubectl get all -n java-demo
kubectl get configmap -n java-demo
~~~

Deleting by manifest removes only declared resources, yet can impact workloads if you reused names. **Verify `current-context` and namespace before deleting.**

If namespace **`java-demo`** was created solely for this lab and holds no one else's resources:

~~~bash
kubectl delete namespace java-demo
~~~

Deleting a namespace deletes **all namespaced resources** inside it, not just the sample app. Never delete a shared namespace. **Never delete the organization's AKS cluster, node pools, or ACR** to finish an exercise. Clean up demo images in ACR according to the registry owner's retention policy.

## 27. Production deployment: additional layers required

The Deployment and Service in this lesson are technical foundations, not a complete production architecture. For a Java API serving real users, add:

| Domain | Questions before going to production |
|---|---|
| **Ingress/TLS** | Which ingress/Gateway/Application Gateway routes traffic? How are HTTPS, domains, WAF, and authentication configured? |
| **Network policy** | Which services/namespaces may call the Java API? How does egress reach databases and Key Vault? |
| **Identity** | Does the app use Workload ID for Azure dependencies? Does kubelet only have ACR pull rights? |
| **Secrets** | Do Key Vault, CSI Driver, or approved secret managers have RBAC and auditing? |
| **Availability** | Do node pools have headroom, multi-node/zone Pod distribution, PDBs, and autoscaling? |
| **Data** | Is the app stateless? If state is needed, does the database/storage have backup and DR? |
| **Health** | Do liveness/readiness/startup probes reflect real health without triggering restart storms? |
| **Resource limits** | Are CPU/memory/JVM sizes backed by load testing? |
| **Security** | Non-root, image scanning, SBOMs, signed images, admission policies, RBAC? |
| **Rollout** | Canaries/rolling updates, schema compatibility, rollbacks, and change approvals? |
| **Observability** | Logs/metrics/traces, alert rules, SLOs, and log retention costs? |
| **DR** | Are clusters/registries/data/ingress in a secondary region documented and rehearsed? |

### Avoid storing durable data in the container filesystem

Deployments manage replaceable Pods. Data written to a container's ephemeral filesystem is lost when Pods are replaced. For orders, documents, sessions, or uploaded files, use durable data services such as Azure SQL, Blob Storage, Azure Files, or PersistentVolumes per architecture.

**A Deployment with 2 replicas does not create database replication.** If the application requires transactions and data consistency, design storage and databases independently of Pod lifecycles.

### Cost considerations

AKS and ACR bill according to active SKUs and usage: node compute, disks, load balancers, public IPs, log ingestion/retention, registry storage, egress, and optional features. Creating a 2-replica Deployment can raise node utilization or trigger scale-out. **Budget alerts do not automatically cap resources or stop billing.**

## 28. Lesson completion checklist

- [ ] Understand that Deployment manages Pods/ReplicaSets while Service provides a stable endpoint.
- [ ] Built Java API into a JAR, ran locally, and ran inside a container on port 8080.
- [ ] Pushed image to ACR under a unique verified tag/digest.
- [ ] Granted AKS kubelet image-pull permissions matching registry mode without admin passwords.
- [ ] Verified kubeconfig context and namespace match the authorized lab environment.
- [ ] Deployment selector matches template labels; Service selector matches Pod labels.
- [ ] Service `port`/`targetPort` match container port and Java is genuinely listening.
- [ ] Probes target valid endpoints exposed by Spring Boot.
- [ ] CPU/memory requests and limits fit the JVM without `OOMKilled`.
- [ ] Cluster has sufficient node capacity for rolling updates with `maxSurge`.
- [ ] Service uses ClusterIP for the lab; avoided accidentally provisioning a public LoadBalancer.
- [ ] Inspected ReplicaSets, Pods, EndpointSlices, events, and logs to verify state.
- [ ] Tested `/api/hello` via `port-forward` and verified readiness.
- [ ] Practiced controlled rollout/rollback without relying on mutable `latest` tags.
- [ ] Separated non-sensitive ConfigMaps from secrets and workload identities.
- [ ] Prepared a safe cleanup plan and noted incurred costs.

## 29. Self-check questions

1. How do Deployment and Service differ? Why are both usually needed?
2. Why doesn't a Service route directly by Deployment name?
3. What happens if a Service selector does not match Pod labels?
4. How do **`containerPort`**, **`port`**, and **`targetPort`** differ?
5. Why might a Running Pod still be excluded from a Service's endpoints?
6. When should you use **`ClusterIP`** vs. **`LoadBalancer/Ingress`**?
7. In Spring Boot, what two distinct decisions do readiness and liveness probes govern?
8. Why does `startupProbe` help a slow-starting Java application?
9. What happens with **`maxSurge=1`** when the node pool is completely full?
10. Why doesn't rolling back a Deployment automatically roll back the database?
11. When hitting `ImagePullBackOff`, in what order should you check identity, networking, and image reference?
12. How does the AKS kubelet identity differ from a Java Pod's workload identity?
13. Why shouldn't database passwords be put in ConfigMaps or Dockerfiles?
14. With a `1Gi` memory limit, should you set JVM max heap to exactly `1Gi`?
15. If you update a ConfigMap consumed via `envFrom`, do running Pods automatically pick up the new values?
16. If an API is only called inside the cluster, does it need a public IP?
17. How should cluster HPA and Deployment `replicas` be coordinated to avoid overwriting configurations?
18. Why pin digests when deploying the same version across multiple regions?

## 30. References

- [What is Azure Kubernetes Service (AKS)?](https://learn.microsoft.com/azure/aks/what-is-aks) — AKS model and governance responsibilities.
- [Deploy an application to AKS](https://learn.microsoft.com/azure/aks/learn/quick-kubernetes-deploy-cli) — `kubectl` commands and demo apps on AKS.
- [Integrate Azure Container Registry with AKS](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration) — kubelet identity, pull permissions, and registry mode constraints.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — identities/permissions for pulling and pushing.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — desired state, ReplicaSet, and rolling updates.
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/) — ClusterIP, selectors, ports, and endpoint routing.
- [Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — how Kubernetes probes Pods.
- [Kubernetes resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) — requests, limits, and scheduling.
- [Configure ConfigMaps in Pods](https://kubernetes.io/docs/concepts/configuration/configmap/) — decoupling configuration from images.
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — application-level health and probes.
- [Azure Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — workload identity federated with Microsoft Entra ID.
- [Azure CLI: az aks](https://learn.microsoft.com/cli/azure/aks) — cluster permissions and AKS connectivity.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating compute, networking, and ACR costs.

**Conclusion:** Deploying Java on AKS does not end with **`docker push`** or **`kubectl apply`**. The Deployment must declare accurate images, resources, probes, and update strategies; the Service must match ready Pods and map ports accurately. Combining ACR permissions, Kubernetes RBAC, networking, observability, and controlled rollouts/rollbacks turns a local JAR into a scalable, operable, and resilient service on AKS.
