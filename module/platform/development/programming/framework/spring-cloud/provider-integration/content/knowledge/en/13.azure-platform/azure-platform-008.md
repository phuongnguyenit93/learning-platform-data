# Distinguishing Azure Library Integration from Application Hosting Platforms

A Spring Boot application can use **Spring Cloud Azure** to read Blob Storage and send messages via Service Bus while being deployed on **Azure App Service**, **Azure Kubernetes Service (AKS)**, a virtual machine, an on-premises enterprise server, or even AWS/Google Cloud. Conversely, an application running on Azure does not have to include any Spring Cloud Azure starter if it does not integrate with Azure services through those libraries.

Clearly understanding the difference between **service integration libraries** and the **hosting platform** helps prevent picking the wrong dependencies, assigning the wrong permissions, misdesigning networking, and confusing responsibilities between developers and the platform team.

This lesson belongs to the **Azure Platform** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; focusing on identity/permissions, storage, messaging, data, secrets, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the differences among **Spring Cloud Azure**, **Azure SDK for Java**, **Spring Boot**, the **hosting platform**, and the **Azure managed services** the application calls.
2. Distinguish **packaging/running Spring Boot** from **integrating Blob Storage, Service Bus, Key Vault, and Cosmos DB** at the Java layer.
3. Evaluate App Service, Azure Container Apps, AKS, Azure Functions, VMs, and non-Azure platforms according to deployment needs.
4. Design application configuration, workload identity, Azure RBAC, DNS/Private Endpoint, and observability for each environment.
5. Demonstrate the same Spring Boot business layer running locally and on App Service without rewriting Blob-calling logic.
6. Recognize limits of managed identity, cross-provider migration considerations, and cases where using the Azure SDK directly is preferable to a starter.
7. Build tests proving that the client genuinely calls services under the **runtime's identity**.

## 2. Three Layers to Distinguish in an Azure Architecture

~~~mermaid
flowchart TB
    U[User or calling system] --> A[Spring Boot application]
    subgraph Host["Application hosting layer"]
      A
      H[App Service / Container Apps / AKS / VM / other environment]
    end
    A --> L[Spring Cloud Azure starter or Azure SDK for Java]
    L --> I[Azure Identity / TokenCredential]
    L --> D[Blob Storage / Service Bus / Key Vault / Cosmos DB]
    I --> E[Microsoft Entra ID]
    P[Azure RBAC and service policies] -.-> D
    N[DNS / VNet / firewall / Private Endpoint] -.-> D
~~~

| Layer | Role | Question to Ask |
| --- | --- | --- |
| **Application code and framework** | Handles APIs, business logic, transactions, user security, Spring Boot configuration | What does the application do? |
| **Integration library** | Configures/instantiates clients and calls Azure data APIs | Which API/SDK does the app use to talk to Azure? |
| **Hosting platform** | Launches processes/containers, supplies CPU/RAM, scaling, runtime config, deployment, and network paths | Where does the program run and how is it operated? |
| **Azure managed service** | Stores data, messages, databases, secrets, configuration | Where do backing data and capabilities live? |
| **Identity, RBAC, network** | Authenticates and restricts access between workloads and services | Who may call what, and over which path? |

**Core point:** integration libraries and the hosting platform are **two independent decisions that influence each other**. App Service/AKS can supply credential mechanisms, networking, and operations; Spring Cloud Azure / Azure SDK still governs how Java code connects to the service.

### Brief Examples

- **Spring Boot + spring-cloud-azure-starter-storage-blob + App Service:** the starter configures the Blob client; App Service runs the application and can provide a managed identity.
- **Spring Boot + azure-storage-blob + AKS:** code builds the SDK client manually; AKS runs the Pod and can use Workload Identity to fetch tokens.
- **Spring Boot + spring-cloud-azure-starter-servicebus + on-premises server:** still calls Service Bus if the endpoint is reachable and credentials are valid.
- **Spring Boot + Spring Data JPA + self-managed PostgreSQL on App Service:** the application runs on Azure without requiring Spring Cloud Azure.
- **Spring Boot + AWS S3 SDK running on Azure Container Apps:** hosted on Azure while data lives on AWS; design credentials and networking around AWS.

## 3. What Does Spring Cloud Azure Actually Provide?

**Spring Cloud Azure** is a collection of libraries integrating Azure services with the Spring ecosystem, typically via **Spring Boot auto-configuration**, externalized configuration, dependency injection, and Spring Data, Spring Integration, or Spring Security integrations depending on the specific starter.

| Component | Typical Role | Example |
| --- | --- | --- |
| **Spring Boot** | Builds Java applications, creates the application context, manages beans/config, runs web services | Spring MVC REST API |
| **Azure SDK for Java** | Provides Java APIs to interact with individual Azure services | BlobServiceClient, ServiceBusSenderClient, SecretClient |
| **Spring Cloud Azure starter** | Pulls in the SDK and auto-configures the corresponding beans/integrations | spring-cloud-azure-starter-storage-blob |
| **Azure Identity SDK** | Provides TokenCredential to acquire principal tokens | DefaultAzureCredential, ManagedIdentityCredential |
| **Azure hosting** | Runs JARs/containers, manages deployment and operations | App Service, AKS, Container Apps |

Spring Cloud Azure **uses the Azure SDK underneath**; it does not replace Azure SDK APIs. When an application injects a **BlobServiceClient** created by a starter, the upload method is still an Azure Storage SDK API.

A starter **does not create a Storage Account**, **does not create queues**, **does not enable managed identity**, **does not assign Azure RBAC roles**, and **does not guarantee network reachability**. Those belong to infrastructure and deployment management.

### Choosing a Starter by Service Need

| Need | Common Library Choice | Is Azure Hosting Mandatory? |
| --- | --- | --- |
| Store files in Blob | Spring Cloud Azure Blob starter or Azure Storage Blob SDK | Can run anywhere with connectivity and credentials |
| Send/receive Service Bus | Spring Cloud Azure Service Bus starter or Service Bus SDK | Does not have to run on Azure |
| Read Key Vault secrets | Spring Cloud Azure Key Vault starter or Secrets SDK | Does not have to run on Azure |
| Use Cosmos DB with Spring Data | Appropriate Spring Data Cosmos integration | Can run outside Azure if connectivity and auth are met |
| Read App Configuration | Spring Cloud Azure App Configuration starter / SDK | Does not have to share subscription/hosting |
| Deploy a plain REST API | No Azure starter needed if not using those integrations | Can run on Azure App Service |

Artifact names and APIs can differ across versions. Always choose a **Spring Cloud Azure BOM** compatible with **Spring Boot/JDK** and consult the guide for the starter in use.

## 4. What Problems Does Azure Hosting Solve?

The hosting platform governs **deployment and runtime operations**, such as:

- Running a Java runtime directly or a container image.
- Choosing CPU/RAM, autoscaling, and resource limits.
- Managing environment configuration, restarts, health checks, and secret injection.
- Exposing HTTP endpoints, ingress TLS, routing, and load balancing.
- Connecting VNets, DNS, outbound egress, firewalls, and Private Endpoints.
- Provisioning a workload identity via platform-supported mechanisms.
- Collecting metrics, logs, traces, managing rollouts/rollbacks, and availability.

These capabilities **do not depend on having a Spring Cloud Azure starter**. A Spring Boot application calling only an external database still requires the exact same hosting decisions.

### Comparison Table of Common Options

| Platform | Operational Model | When to Consider | What You Must Still Design Yourself |
| --- | --- | --- | --- |
| **Azure App Service** | PaaS running web apps/APIs via supported runtimes or containers | Spring Boot REST APIs when wanting less infrastructure management | App config, identity, outbound networking, scaling, deployment slots per configuration |
| **Azure Container Apps** | Managed platform for containers and microservices with revisions/scaling | Container workloads, HTTP APIs, or background processing needing streamlined operations | Container image, ingress, secrets/config, managed identity, networking, scale triggers |
| **AKS** | Managed Kubernetes control plane; team operates workloads and many cluster components | Many microservices needing the Kubernetes ecosystem, custom controllers/policies | Namespaces, service accounts, workload identity, ingress, resource limits, observability |
| **Azure Functions** | Function/event-driven model tied to hosting plan and language worker | Triggered or event-driven tasks suited to Functions packaging | Triggers/bindings, cold starts, function lifecycle, specific Spring integration support |
| **Azure VM** | IaaS, self-managing OS and runtime layers | Deep control over OS, agents, networking, or legacy apps | Patching, process lifecycle, scaling, monitoring, VM hardening |
| **Non-Azure environments** | On-prem, AWS, GCP, other container platforms | Multi-cloud architectures or specific data/hosting requirements | Egress to Azure, federation/credentials, latency, and network cost |
| **Azure Spring Apps (previously used platform name)** | PaaS tailored for Spring workloads | Evaluate only after checking current service status and support roadmap | Never equate this hosting product with the Spring Cloud Azure libraries |

**Product lifecycle note:** support status, regional availability, roadmaps, and transition timelines for Azure services change over time. When choosing a new platform, check official service lifecycle notices and organizational policy. Do not take the name **Azure Spring Apps** as proof that a project must use that product to run Spring Cloud Azure.

### Azure Spring Apps and Spring Cloud Azure Are Two Different Concepts

- **Spring Cloud Azure**: the Java libraries/starters an application adds to its build file.
- **Azure Spring Apps**: the name of a hosting service developed for Spring workloads; not a Spring Cloud Azure Maven dependency.
- **Spring Boot**: an application framework, not exclusively tied to Microsoft hosting.

A service **deployed on App Service** can still use Spring Cloud Azure normally. An application **running on a GCP VM** can also use the Azure Blob SDK if it has valid authentication and networking. Conversely, deploying a JAR to a hosting service does not automatically turn every Azure dependency into a Spring bean.

## 5. Decision Matrix: Libraries and Runtime Location Are Two Axes

| Where Does the App Run? | Not Using Azure Services | Using Azure SDK Directly | Using Spring Cloud Azure Starter |
| --- | --- | --- | --- |
| Developer workstation | Standard Spring Boot app | Use AzureCliCredential or appropriate credential | Starter auto-configures client when dependencies and properties are valid |
| App Service | Works | Can use managed identity via Azure Identity | Can use starter and managed identity |
| Container Apps | Works | SDK via managed identity if runtime is configured | Starter works similarly; verify credential config |
| AKS | Works | SDK via AKS Workload ID or appropriate auth mechanism | Starter also works once identity/networking are complete |
| VM on Azure | Works | SDK + VM identity or supported credential | Starter and Spring properties work if runtime supports them |
| AWS/GCP/on-prem | Works | Azure SDK with valid federation/credentials and network path to Azure | Starter still works; Azure identity does not appear automatically |

**There is no rule saying "Spring Cloud Azure only runs on Azure".** Compatibility of JDK, dependencies, credentials, data endpoints, and networking are the true technical prerequisites.

However, running an app on another provider and calling Azure can incur **latency**, **egress/inter-region charges**, data-residency issues, and cross-cloud dependency risks. Hosting decisions must weigh non-functional concerns, not just "can the SDK make the call?".

## 6. Responsibilities Between Application Teams and Platform Teams

| Question | Application Team Typically Owns | Platform / Identity Team Typically Owns |
| --- | --- | --- |
| Choose Blob or Service Bus | Business and API analysis | Participates in operational/limit review |
| Add starters/SDKs and manage BOM | Dependency declarations, client code, tests | Version/security policies if applicable |
| Create Storage Account / Service Bus namespace | Supplies resource and region requirements | Provisions via IaC/pipeline |
| Enable managed identity or Workload ID | Specifies needs / identity mode | Attaches identity to runtime, configures trust |
| Assign data roles | Lists minimal required operations and scopes | Creates role assignments with delegated admin rights |
| Connect Private Endpoint | Configures right endpoint, tests from runtime | VNet, private DNS, network policies, and routing |
| Health checks, retries, idempotency | Application/SDK code | Monitors resource capacity and platform observability |
| Deployment and rollback | App versions, migrations, smoke tests | Pipelines, environments, health and scaling policies |

This division of responsibilities is a **reference**, not a mandate for every organization. What matters is clear ownership of every task—especially **identity, RBAC, and network paths**.

## 7. Same Spring Boot Application Calling Blob Storage

Suppose **Documents API** receives documents, stores them in the **documents** Blob container, and returns the object name. The application must work locally and on Azure hosting without changing the business layer.

### 7.1. Choosing a Dependency Approach

With Spring Cloud Azure, example Maven dependency:

~~~xml
<!-- Snippet: import a compatible Spring Cloud Azure BOM in
     pom.xml dependencyManagement before declaring the starter. -->
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
~~~

In **dependencyManagement**, the BOM is typically:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-dependencies</artifactId>
    <version>${spring-cloud-azure.version}</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
~~~

These are **snippets**, not a complete POM. The **spring-cloud-azure.version** property must be verified compatible with the project's Spring Boot/JDK. Do not hard-code individual Azure SDK versions when the BOM already manages them.

### 7.2. application.yml for Spring Cloud Azure

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}

app:
  documents:
    container-name: ${AZURE_BLOB_CONTAINER:documents}
~~~

For example, in Azure public cloud, account name **stordersdev01** typically resolves to an endpoint shaped like **https://stordersdev01.blob.core.windows.net** under the version's auto-configuration. For other cloud environments, emulators, or special endpoints, configure according to your Spring Cloud Azure version's documentation.

Never put connection strings, account keys, client secrets, or SAS tokens into Git. Spring Boot can read environment variables from a dev workstation, App Service application settings, Container Apps configuration, or Kubernetes Pods.

### 7.3. Writing a Hosting-Independent Business Layer

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentsStorage {

    private final BlobContainerClient container;

    public DocumentsStorage(
            BlobServiceClient blobServiceClient,
            @Value("${app.documents.container-name}") String containerName) {
        this.container = blobServiceClient.getBlobContainerClient(containerName);
    }

    public void upload(String name, byte[] bytes) {
        container.getBlobClient(name).upload(
                new ByteArrayInputStream(bytes), bytes.length, false);
    }
}
~~~

**DocumentsStorage** contains no code saying "if running on App Service then..." or "if running on AKS then...". It consumes the **BlobServiceClient** bean created by Spring Cloud Azure and does not care where the process runs.

The architectural goal is to **vary environment configuration and identity provisioning**, while keeping document storage logic unchanged. The example uses **overwrite=false** so it does not silently replace a blob with the same name. Production also needs size limits, streaming, validation, idempotency, conflict handling, and API caller authorization.

### 7.4. If Using the Azure SDK Directly

An application that does not need auto-configuration can construct the client as a Spring bean:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobConfiguration {

    @Bean
    public TokenCredential tokenCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean
    public BlobServiceClient blobServiceClient(
            TokenCredential tokenCredential,
            @Value("${app.azure.blob.endpoint}") String blobEndpoint) {
        return new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(tokenCredential)
                .buildClient();
    }
}
~~~

With this approach, set **app.azure.blob.endpoint** in application.yml and include both **azure-identity** and **azure-storage-blob** under consistent BOM version management. If you already use a starter that auto-configures **BlobServiceClient**, do not define a second bean of the same type without explicitly handling auto-configuration and qualifiers.

**Observation:** the DocumentsStorage class stays identical when switching between a starter-created bean and an application-created bean, provided the client API contract meets the need.

## 8. Environment A: Developing on a Laptop

On a developer's machine, the JDK and Spring Boot run locally; only the data service lives on Azure. A common approach is signing in via Azure CLI:

~~~bash
az login

az account show   --query "{tenant:tenantId, subscription:id, name:name}"   --output json
~~~

With **DefaultAzureCredential**, the Azure Identity SDK tries eligible sources per its chain/version; Azure CLI is only **one** source. If you need to force the lab environment to use the CLI account to avoid identity mix-ups, select **AzureCliCredential** explicitly.

To let the app upload, the developer account still needs the **Storage Blob Data Contributor** role on the appropriate test Storage Account/container. Signing in to CLI and having ARM read access to resource metadata **does not grant** Blob data permissions.

A developer's laptop may have direct Internet access, whereas production has a proxy or Private Endpoint. Therefore, local success does not prove the hosting platform's network path.

## 9. Environment B: Azure App Service and Managed Identity

App Service can run Java applications using a supported runtime or container model, receive app settings, and expose a managed identity when enabled.

### 9.1. Logical Deployment Workflow

1. Provision App Service with the required runtime/container, region, and networking.
2. Enable **system-assigned managed identity** or attach a **user-assigned managed identity** as appropriate.
3. Retrieve the identity's **principal ID** and assign data permissions on the target Storage Account/container.
4. Add **AZURE_STORAGE_ACCOUNT** and **AZURE_BLOB_CONTAINER** to application settings.
5. Deploy the JAR/container and verify a real upload request.
6. Configure health checks, logs, metrics, scaling, and rollback; verify outbound DNS/VNet connectivity to Blob works.

Azure CLI example for an existing App Service:

~~~bash
az webapp identity assign   --resource-group "<app-resource-group>"   --name "<app-service-name>"

az webapp identity show   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --query "{principalId:principalId, tenantId:tenantId}"   --output json
~~~

Assign the data role on the target Storage Account using an account **permitted to assign roles**:

~~~bash
az role assignment create   --assignee-object-id "<app-managed-identity-principal-id>"   --assignee-principal-type ServicePrincipal   --role "Storage Blob Data Contributor"   --scope "<storage-account-resource-id>"
~~~

These commands are **lab templates**; replace placeholders with real values, run only against authorized resources, and document the scope. After assigning a role, allow time for permissions to propagate.

### 9.2. Environment Configuration Without Putting Secrets in Code

~~~bash
az webapp config appsettings set   --resource-group "<app-resource-group>"   --name "<app-service-name>"   --settings AZURE_STORAGE_ACCOUNT="<storage-account-name>" AZURE_BLOB_CONTAINER="documents"
~~~

The client still uses the exact same **DocumentsStorage**. What differs are mainly the app settings and the runtime's credential chain/identity.

**Note:** if multiple identities or environment credential sources exist, DefaultAzureCredential may pick an unintended principal. For production requiring a deterministic identity, use explicit credential configuration per your Azure Identity / Spring Cloud Azure version's API, and verify the actual principal through safe observability.

## 10. Environment C: AKS and Workload Identity

AKS hosts Spring Boot inside a Kubernetes Pod. AKS supports configuring **Microsoft Entra Workload ID** so a Pod can use an Entra identity without storing long-lived client secrets inside the image.

What differs from App Service is **how the identity is provided**, not rewriting every Blob business class.

### 10.1. Required Components

| Component | Responsibility |
| --- | --- |
| **AKS OIDC issuer** | Issues workload identity tokens per cluster configuration |
| **Kubernetes service account** | Represents the workload within a namespace |
| **Federated credential in Entra** | Trusts the specific workload's issuer/subject/audience |
| **Entra identity** | Principal receiving access tokens to call Azure |
| **Role assignment** | Permits the principal to write Blobs at the required scope |
| **Pod label/annotation and token projection** | Supplies metadata/tokens to the Azure Identity SDK per Workload ID config |

Service account illustration:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: documents-api
  namespace: documents
  annotations:
    azure.workload.identity/client-id: "<user-assigned-managed-identity-client-id>"
~~~

Pod template in a Deployment:

~~~yaml
spec:
  template:
    metadata:
      labels:
        app: documents-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: documents-api
      containers:
        - name: app
          image: "<registry>/documents-api:<tag>"
          env:
            - name: AZURE_STORAGE_ACCOUNT
              value: "<storage-account-name>"
            - name: AZURE_BLOB_CONTAINER
              value: "documents"
~~~

This is a **Deployment snippet**, not a complete deployment manifest. Configure selectors, deployment metadata, resource requests/limits, readiness/liveness probes, and security policies for your environment.

### 10.2. Does Spring Cloud Azure Need AKS-Specific Code?

If the SDK and starter version in use supports workload identity, the Blob service bean and business logic can remain unchanged. However, AKS **does not automatically grant an Entra identity just because a Pod has the right label**. You must enable OIDC/Workload ID, create a federated credential matching issuer/subject/audience, assign the right role, and ensure token projection works.

Another critical distinction: **node identity differs from Pod/workload identity**. Never treat the AKS node's permission to access Storage as proof that the Pod is using Workload Identity properly.

### 10.3. Kubernetes Runtime Risks

- When Pods scale to multiple replicas, control retries/idempotency for uploads and message processing.
- Ensure routing, DNS, and network policies let Pods reach both Azure Blob and the Microsoft Entra token endpoint.
- If using a **Private Endpoint**, configure private DNS inside the AKS network.
- If running sidecars, a service mesh, or proxies, verify both the token-acquisition path and the data-plane path.
- Do not confuse a readiness probe with an RBAC check; successful startup does not guarantee the first Azure call succeeds.

## 11. Environment D: Azure Container Apps, Azure Functions, and VMs

### Azure Container Apps

Container Apps fits when you want to run containers and use platform features such as revisions and scaling without managing an entire Kubernetes cluster. The Spring Boot app is still built as a container image listening on an HTTP port.

The platform can support managed identities and networking/secrets configuration, yet the deployment team must still enable/attach the identity, grant roles on target resources, and configure the proper endpoints.

For background workers receiving Service Bus messages, look beyond whether the container starts and design the **queue consumer**, retries, concurrency, scale signals, and duplicate-message handling.

### Azure Functions

Functions follows an event-driven model: applications are typically deployed around a **function entrypoint/trigger and runtime contract**. A Spring Boot web server packaged as a JAR does not automatically become an Azure Function simply by uploading it to Azure.

If using the Spring Cloud Function adapter or a supported integration model, consult the documentation for the chosen runtime/extension. Spring Cloud Azure starters may participate in parts of the integration, yet **function packaging and bootstrapping** remain a hosting-level decision.

### Azure VM

A VM gives deep control over the operating system, JVM, and agents. If the VM has a managed identity, the Azure Identity SDK can fetch tokens through the environment mechanism. However, the operations team must manage OS patching, daemon/service processes, health checks, log rotation, restarts, firewalls, and scaling.

Having an Azure VM **does not mean** an identity is enabled or data permissions are already granted. The Azure SDK does not enable VM identities automatically.

## 12. Running Spring Boot Outside Azure While Calling Azure Managed Services

An application running on AWS, Google Cloud, or in a data center can call Azure Blob or Service Bus if all of the following are satisfied:

1. **Service endpoint:** knowing the exact hostname/namespace and protocol requirements.
2. **Identity:** configuring valid credentials with Microsoft Entra or another service-supported authorization method.
3. **RBAC:** the principal holds appropriate data permissions on the target Azure resource.
4. **Networking:** Internet/VPN/peering/proxy/private connectivity satisfies the Azure service's policy.
5. **Latency, reliability, and cost:** accounting for data transfer, failure domains, retries, and cross-cloud observability.

**ManagedIdentityCredential** tied to Azure runtimes does not appear automatically on an AWS VM or a typical GKE Pod. If the non-Azure environment supports OIDC, consider **workload identity federation** to Microsoft Entra with properly scoped trust; otherwise, use an appropriate credential mechanism and manage secrets securely per policy.

**Notable limitations:**

- A Storage Private Endpoint inside an Azure VNet is not automatically reachable from every AWS/GCP workload; appropriate routing and DNS are required.
- Service Bus/Event Hubs have specific message ordering, at-least-once delivery, and protocol characteristics. Do not assume they can be swapped with SQS/Pub/Sub without architectural changes.
- Data residency and egress costs may justify placing workloads closer to the data.
- Container hosting platforms may have different lifecycles/scaling than Azure, even with the same image and code.

## 13. Runtime Identity Differs from Deployment Pipeline Identity

A common design mistake is seeing **CI/CD deploy succeed** and concluding the application can therefore read Key Vault or Blob. In reality there are two principals:

~~~mermaid
flowchart LR
    CI[CI/CD deployer] -->|ARM deployment permission| H[App Service / Container Apps / AKS]
    H --> APP[Spring Boot runtime identity]
    APP -->|Data-plane permission| B[Blob / Service Bus / Key Vault]
    P[Pipeline IAM role] -.-> CI
    R[Runtime data role] -.-> APP
~~~

| Subject | Required Permissions | Typically Not Needed |
| --- | --- | --- |
| **CI deployer** | Permission to update resources / deploy artifacts within chosen scope | Reading all production secrets and data |
| **Runtime managed/workload identity** | Least-privilege data permissions on Blob/Service Bus/Key Vault/Cosmos | Owner permission on the subscription |
| **Local developer** | Permissions on dev/test resources and appropriate logs | Production application permissions |
| **Integration-test identity** | Permissions on test resources and controlled cleanup | Modifying real data outside lab scope |

For Blob, some management roles may carry indirect permission to list access keys; therefore carefully audit sensitive **management actions**, not just DataActions. For Key Vault/Cosmos, identify the service's own data-plane authorization model.

## 14. Networking and Endpoints: Varying by Hosting Platform

**Hosting** directly affects the network path; the **library** simply sends requests using the configured endpoint and transport.

| Environment | Hosting-Specific Network Checks |
| --- | --- |
| Laptop | Internet/corporate proxy, certificate trust, local machine firewall |
| App Service | Outbound routing/VNet integration, DNS, access restrictions |
| Container Apps | VNet/environment networking, egress, and DNS |
| AKS | Pod DNS, CNI/network policies, node egress, private DNS, service mesh |
| VM | NSG/firewall, routing, DNS, proxy, VM network settings |
| AWS/GCP/on-prem | Cross-cloud connectivity, egress IPs, VPN/private links, DNS resolvers |

### Two Network Flows to Check Separately

When an application uses **DefaultAzureCredential** or managed/workload identity, two flows can occur:

~~~text
Spring Boot runtime
    ├── identity/token flow → Entra / managed identity endpoint / token broker
    └── data flow → Blob / Service Bus / Key Vault service endpoint
~~~

An HTTP proxy configured for the Blob client is not necessarily used by the Azure Identity SDK when fetching tokens. Some messaging clients use **AMQP** over TCP/WebSockets rather than sharing Blob's HTTP transport. Network design must examine each service's **actual protocol**.

### Private Endpoint Does Not Replace Azure RBAC

Inside an Azure VNet, a Storage Account with a Private Endpoint is usually still called via its standard service hostname; internal DNS can resolve it to a private IP via Private Link configuration. Using raw IP addresses or invented hostnames can break TLS/endpoint checks.

Whether hosted on AKS or App Service, **Private Endpoint only solves the network path**; the principal still requires the corresponding Data Contributor/Reader role on the resource.

## 15. Operations: What Is Owned by Hosting vs. SDK?

| Concern | Owned by Hosting Platform | Owned by App / SDK |
| --- | --- | --- |
| Instance count, CPU/RAM | Hosting autoscale and resource limits | Concurrency control, connection pools |
| HTTP ingress/TLS to users | Ingress / reverse proxy / certificate configuration | API endpoints, Spring Security |
| Supplying credentials to workload | Attaching managed identity, projected tokens, runtime env | TokenCredential, verifying selected source |
| Successful Blob calls | Egress/networking and reachable resource | Right endpoint, upload API, retries, error handling |
| Sending/receiving Service Bus | Network connectivity, worker scaling | Ack/settlement, retries, idempotency, DLQ |
| Metrics/logs | Platform collection and monitoring backend | Business metrics, Azure SDK diagnostics, correlation IDs |
| Deployment rollback | Slots/revisions/rolling updates | Backward compatibility of schemas and config |
| Secret protection | Secure environment / secret store, access policies | Never log tokens/secrets, never embed credentials |

**Retries and scaling** especially require coordination: when AKS or Container Apps scales up consumer replicas, the same queue can face duplicate processing or downstream load spikes. A successful SDK message send does not guarantee business-level exactly-once semantics; idempotency and clear processing flows are essential.

## 16. Testing Independence Between Library and Hosting

### 16.1. Unit Testing Business Logic

Place storage logic behind an interface/adapter or appropriate mock client to verify:

- Valid input data translates into the right upload call.
- 403/404/409 errors and timeouts map to appropriate business responses.
- No Azure account, managed identity, or running App Service is required.
- Tests do not depend on a laptop's Azure CLI cache.

Unit tests verify code logic, **not identity or networking**.

### 16.2. Integration Tests on Azure Dev/Test

Run a real operation using the corresponding **runtime identity**:

1. Enable the right identity on the host; configure the endpoint and role on a test Storage Account.
2. Deploy the test application or job.
3. Upload a uniquely named blob, read it back, and delete/clean up.
4. Record request ID, status/error code, latency, and credential source at an approved level.
5. Test a missing-role scenario on the test resource and a controlled DNS/proxy failure.
6. Verify the test ran under the runtime identity, not a personal Azure CLI session.

**Azurite** helps test part of the Blob API locally; it does not fully replace Entra managed identity, Azure RBAC, private networking, or real managed services.

### 16.3. Post-Deploy Smoke Tests

A check verifying only that the **Spring context starts** is insufficient: many Azure clients initialize without contacting the service. Include a monitored, non-destructive smoke test against test data or an appropriate read/write check that will not inadvertently add production load.

### 16.4. Cross-Hosting Test Matrix

| Check | Local | App Service | AKS |
| --- | --- | --- | --- |
| Spring Boot context starts | Yes | Yes | Yes |
| BlobServiceClient bean configured | Yes | Yes | Yes |
| Environment credential works | Azure CLI / dev identity | Managed identity | Workload identity |
| Data role on right principal | Dev identity | App Service identity | Pod identity |
| DNS/egress to endpoint | Laptop network | VNet / outbound | Pod / VNet network |
| Test upload with real runtime identity | Yes | Yes | Yes |

Code-level criteria are similar, yet **identity, networking, and scaling results cannot be inferred from a single environment**.

## 17. Troubleshooting: Which Layer Failed?

| Symptom | Potentially Involved Layer | How to Handle |
| --- | --- | --- |
| Build cannot find starter | Dependency / BOM | Select the right artifact and Spring Boot compatibility matrix |
| Spring fails to create BlobServiceClient | Auto-configuration / bean | Check starter, application properties, bean ambiguity |
| App Service deploys successfully yet upload returns 403 | Runtime identity / RBAC or network policy | Verify actual principal, data role, scope, and service error |
| Runs locally yet AKS reports CredentialUnavailable | Workload identity wiring | Check OIDC, service account, pod label, token file |
| Blob SDK times out inside AKS | DNS / routing / network | Debug from Pod, Private Endpoint, outbound policy |
| App starts yet Function trigger never fires | Hosting model | Check Function runtime/trigger and packaging model |
| Service Bus sender receives 401/403 | Credential/authorization or endpoint | Check namespace, Entra token, Data Sender role |
| CI can create Storage yet app cannot read blobs | Separation of deploy identity and runtime identity | Grant data-plane role to the actual application identity |
| Same code runs on GCP yet cannot obtain managed identity | Credential incompatible with hosting | Design federation or another supported credential |
| Wrong Blob URL despite right subscription | Service endpoint | Verify endpoint/account; avoid confusing with ARM resource ID |
| Multiple replicas produce duplicate messages | Business logic / scaling | Idempotency, message settlement, retries, and concurrency |

A **403 from Azure Blob** differs from a **407 from an HTTP proxy**, and differs from a **CredentialUnavailableException**. Read the root cause, error code, and confirm whether the request ever reached Azure before swapping dependencies or granting broader roles.

## 18. Lab Exercise: Same Spring Boot API on Two Hosting Targets

**Scenario:** develop the Documents API storing files in the private **documents** Blob container. The goal is to keep the Java business layer identical when running locally and on App Service, then analyze moving to AKS.

### Part A — Preparing the Application and Test Data

1. Create a Spring Boot project with the Blob starter or direct Azure SDK following a compatible BOM/JDK.
2. Create or obtain a Storage Account and **documents** container in a lab environment.
3. Write the **DocumentsStorage** service with an upload method, configuring account/container via environment variables.
4. Write unit tests exercising Blob operations through a mocked abstraction; avoid requiring live Azure in unit tests.

### Part B — Running Locally

1. Run **az login** with a dev account.
2. Grant Blob write permissions at an appropriate test scope to the dev principal.
3. Run Spring Boot, upload a uniquely named blob, and read it back.
4. Record the endpoint, confirmed credential source, error codes (if any), latency, and request ID.

### Part C — Running on App Service

1. Package the exact same application as a JAR/container matching the hosting plan.
2. Enable managed identity on App Service and grant **Storage Blob Data Contributor** on the test account/container to the exact principal.
3. Configure application settings for **AZURE_STORAGE_ACCOUNT** and **AZURE_BLOB_CONTAINER**; configure credential mode per SDK/version if needed.
4. Deploy, perform a similar upload, and verify networking and runtime identity.
5. Revoke permissions on the test resource to observe the 403 error, then restore lab permissions.

### Part D — Analyzing AKS

1. Draft Pod/Deployment manifests with the Workload ID service account and label.
2. List the issuer/subject/audience federation parameters and role assignments that must be configured.
3. Explain why **DocumentsStorage** does not need to change, while Pod and Azure Identity configuration must change.
4. Evaluate readiness/liveness probes, scaling, retries, and Private Endpoint for a real deployment.

**Suggested Results Table:**

| Item | Local | App Service | AKS (Design) |
| --- | --- | --- | --- |
| Artifact | Spring Boot JAR | Same JAR/container | Same container |
| Library | Spring Cloud Azure Blob starter | Same starter | Same starter |
| Runtime identity | Developer / CLI | Managed identity | Workload identity |
| Data role | Dev principal | App Service principal | Pod / Entra principal |
| Network | Local egress | App Service outbound | Pod / VNet egress |
| Evidence | Upload test + SDK log | Upload test + platform log | Manifest + test plan |

### Self-Check Questions

1. Why does an application running on App Service not necessarily need a Spring Cloud Azure dependency?
2. Does Spring Cloud Azure require the application to run on an Azure hosting platform?
3. When moving from local to App Service, which parts of the application can stay unchanged and which configurations must change?
4. Does enabling managed identity on App Service automatically grant Blob write permissions?
5. What is the difference between the CI deployer's identity and the Spring Boot runtime's identity?
6. When an AKS Pod uses Workload Identity, why is node permission not proof that the Pod holds data permissions?
7. Why do Private Endpoint and RBAC solve two different problems?
8. When moving Spring Boot from Azure to AWS while still using Blob Storage, what risks outside Java code must be evaluated?
9. Can Azure Functions accept any executable Spring Boot JAR as an HTTP Function without changing packaging?
10. Why does a successfully started Spring context not prove the Blob client can access data?

## 19. Key Takeaways

- **Spring Cloud Azure / Azure SDK for Java** are library-layer integration choices. **App Service, Container Apps, AKS, Functions, and VMs** are application hosting/operations choices.
- A Spring Boot app running on Azure does not have to use Spring Cloud Azure; an app using Spring Cloud Azure does not have to run on Azure.
- Hosting provides runtime, scaling, networking, and identity capabilities; starters/SDKs provide clients and APIs to call managed services. **Neither automatically grants Azure RBAC.**
- Keep business code environment-independent; configure endpoints, credential modes, roles, and networking at the deployment boundary. Verify BOM/SDK, dependency, and actual cloud service compatibility.
- Test using the **target runtime's identity and network path**; distinguish library, hosting, authentication, authorization, and network failures.
- When building multi-cloud integrations across AWS/Azure/GCP, compare **identity models, data semantics, latency, egress costs, observability, and service lifecycles** alongside choosing a starter.

## References

- [Spring Cloud Azure overview and documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Azure SDK for Java overview](https://learn.microsoft.com/azure/developer/java/sdk/overview)
- [Azure App Service overview](https://learn.microsoft.com/azure/app-service/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/azure/container-apps/overview)
- [Azure Kubernetes Service overview](https://learn.microsoft.com/azure/aks/intro-kubernetes)
- [Azure Functions overview](https://learn.microsoft.com/azure/azure-functions/functions-overview)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Microsoft Entra Workload ID for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview)
