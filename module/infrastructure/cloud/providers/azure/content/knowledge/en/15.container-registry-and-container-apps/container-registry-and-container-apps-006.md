# Azure Container Instances and Short-Lived Container Workloads

In the Microsoft Azure ecosystem, not every workload needs a virtual machine running 24/7 or a Kubernetes cluster. Some tasks run for only a few minutes: reading a batch of data, rendering a report, converting file formats, testing connectivity from a private network, or executing an approved maintenance script. Packaged as a container, these tasks can run on demand, write results to persistent storage, and exit.

**Azure Container Instances (ACI)** is a service for running containers on demand without provisioning and managing VMs, container hosts, or Kubernetes clusters. The fundamental deployment unit in ACI is the **container group**: one or more containers sharing portions of the network environment, attached storage, and configured lifecycle. ACI is especially convenient for **short-lived, batch, or experimental workloads** where orchestration needs are not yet complex.

This lesson belongs to the **Container Registry and Container Apps** chapter in the **CLOUD_PROVIDERS_AZURE** module. Learners already have context on subscriptions, resource groups, Microsoft Entra ID, Azure networking, storage, and cost management; here we combine those concepts to deploy, monitor, secure, and clean up a real container task.

> **Core Principle:** For one-off jobs, distinguish between a **container that completes successfully** and a **container that must keep serving continuously**. An inappropriate **restart policy** can cause a finished program to restart repeatedly, wasting resources or producing duplicate results.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Explain ACI, container groups, images, commands, environment variables, CPU/memory requests, and restart policies.
2. Decide when to use ACI instead of Azure Container Apps Jobs, AKS Job/CronJob, Azure Batch, or VMs.
3. Distinguish the three policies **Always**, **OnFailure**, and **Never**; interpret exit codes and job outcomes.
4. Run a short-lived workload using Azure CLI and a container group declared with Bicep.
5. Package a Java batch application into a container image and push it to Azure Container Registry (ACR).
6. Understand the flow of pulling images from a private registry, managing secrets, and access permissions.
7. Design network ingress/egress, VNets, persistent storage, and handling of repeated jobs.
8. Retrieve logs, inspect status, diagnose image pull failures, resource errors, or abnormal container exits.
9. Evaluate CPU/memory, runtime duration, costs, trigger schedules, and resource cleanup.
10. Design retries, idempotency, observability, and runbooks for production workloads.

## 2. What Problem Does Azure Container Instances Solve?

To run a container on a standard VM, the operations team must provision the OS, container runtime, networking, patching, monitoring, and cleanup mechanisms. With ACI, you ask Azure to create a **container group** from a specified image and configuration; the platform provisions and manages the underlying container infrastructure as a service.

A simple lifecycle:

~~~mermaid
flowchart LR
    T["User / scheduler / event"] --> A["Create ACI container group"]
    I["Container image in registry"] -->|"Pull image"| A
    A --> R["Run command or entrypoint"]
    R --> O["Write results to Azure Storage / DB"]
    R --> L["Emit logs, exit code, metrics"]
    O --> E["Job finishes; verify results"]
    L --> E
    E --> C["Keep metadata if needed then delete lab group"]
~~~

ACI eliminates host administration tasks, yet **does not decide for the development team** when to run, how to retry, trigger schedules, container permissions, or output data consistency.

### 2.1. Scenarios Where ACI Makes Sense

| Scenario | How ACI Is Used | What Needs to Be Designed |
|---|---|---|
| On-demand image conversion | Create container, read input blob, write processed blob, and exit | Idempotency, output checks, retries |
| End-of-day report generation | Scheduler calls API to create container group; Java job finishes | Schedule, Azure permissions, exit code checks |
| Testing a Java worker | Run development image for a few minutes | CPU/memory limits and lab cleanup |
| Running an approved ops script | Spin up a temporary group inside an appropriate VNet | Least privilege, auditing, no embedded secrets |
| Processing a small data batch | One container reads input and writes to Azure Storage | Data volume, timeouts, networking, and cost |
| Network diagnostics from a private network | Run an approved image in a private subnet | VNet permissions, DNS, logging |

### 2.2. When ACI Is Not the First Choice

ACI is generally **not the optimal choice** if:

- You have thousands of continuous jobs requiring built-in queues, retry policies, cron, and workload-level autoscaling.
- The application consists of many long-lived microservices needing service discovery, rollouts, autoscaling, and complex traffic management.
- You need Kubernetes features such as controllers, admission policies, Job/CronJob, or the operator ecosystem.
- Large-scale compute batch processing requires thousands of tasks, dedicated queuing/scheduling, and specialized orchestration.
- You require a static IP address, HTTPS ingress, TLS certificates, and full application routing.
- The workload demands hardware resources, execution duration, OS/architecture, or networking capabilities beyond ACI's supported limits.

In those cases, compare with **Azure Container Apps (especially Jobs)**, **Azure Kubernetes Service (AKS)**, **Azure Batch**, **Azure Functions**, or the appropriate managed web service.

## 3. Distinguishing ACI from Azure Container Apps Jobs and Other Services

| Service | Execution Unit | Key Characteristics | Best-Fit Examples |
|---|---|---|---|
| **Azure Container Instances** | Container group | Creates containers on demand without cluster management; lifecycle, restart policy, and resources per group | A batch job triggered by an external system |
| **Azure Container Apps Jobs** | Job execution | Platform supports **manual**, **scheduled**, or **event-driven** runs and execution orchestration per features | Recurring jobs or queue-triggered tasks needing configured retries/scaling |
| **Azure Container Apps applications** | Revision/replica | Runs containerized services with ingress, scaling, revisions, and environment governance | HTTP APIs, long-running background workers |
| **AKS Jobs/CronJobs** | Kubernetes Job/Pod | K8s orchestration, scheduling, policies, and cluster management | Organizations standardized on Kubernetes |
| **Azure Batch** | Pools/tasks | Compute batch orchestration, large tasks, and resource distribution | HPC or massive parallel task processing |
| **Azure Functions** | Function invocation | Event triggers, managed execution, numerous runtime bindings | Short event-driven logic without managing images unless needed |
| **Azure VM** | VM/process | Full control over OS and runtime | Workloads requiring deep host customization |

**Do not confuse ACI with Container Apps Jobs** merely because both run short-lived containers. With ACI, creating groups on a schedule, business-level retry decisions, and aggregating multi-run state typically must be handled by an **external orchestration system**.

Service features, regional availability, quotas, and pricing can change. Choose based on concrete requirements rather than product names alone.

## 4. Architectural Components of ACI

### 4.1. Container Image

An image is a relatively immutable package containing the program, dependencies, runtime, filesystem layers, and startup metadata. Example:

~~~text
myregistry.azurecr.io/orders/report-worker:1.2.0
    ├── Base image (JRE)
    ├── Java classes / dependencies
    ├── ENTRYPOINT
    └── Non-sensitive default configuration
~~~

**Do not treat an image tag as sole proof of content**: tags can be overwritten if the registry permits. Production should version clearly, scan for vulnerabilities, restrict push permissions, and optionally deploy by image digest for stronger reproducibility.

### 4.2. Container Group

A **container group** is the unit of deployment, resource allocation, and lifecycle in ACI. A group can contain a single container or multiple containers within service limits.

Containers in the same group share certain elements such as the network namespace/group IP address and can communicate over **localhost** per the supported model. This is convenient for logging/proxy sidecars, yet introduces lifecycle and resource coupling.

~~~mermaid
flowchart TB
    subgraph Group["Container group: report-job"]
      J["Java Worker Container<br/>1 vCPU, 1.5 GiB (example)"]
      S["Sidecar Container (optional)<br/>logging/proxy"]
      J <-->|"localhost / shared network"| S
    end
    CR["ACR / Registry"] -->|"Image pull"| Group
    Group -->|"HTTPS"| ST["Azure Blob Storage"]
    Group -->|"Logs / telemetry"| MON["Azure Monitor"]
~~~

For **one-off jobs**, start with **a single container** to keep determining when the entire group finishes simple. Multiple containers with a forever-running sidecar can keep the group alive even after the main container finishes.

### 4.3. Container and Resource Declarations

A typical deployment configuration includes:

- **Location**: supported Azure region.
- **OS type**: Linux or Windows where supported by the service/feature.
- **Image**: image reference from Docker Hub, MCR, or a private registry.
- **Resources**: requested vCPUs and memory per service conditions.
- **Command/entrypoint**: program to execute.
- **Restart policy**: Always, OnFailure, or Never.
- **Environment variables**: non-sensitive config and secrets using supported methods.
- **Networking**: public/private IP, ports, DNS, or subnet if configured.
- **Volumes**: Azure Files or supported volume types when data must outlive the container lifecycle.
- **Identity/registry credentials**: rights to pull images and access services.
- **Tags**: owner, environment, workload, run ID for cost/audit tracking.

Not every feature combination is supported across all regions and OSes. For example, Windows containers, VNet integration, managed identities, volume mounts, and resource shapes may carry distinct constraints.

## 5. Three Restart Policies and Their Implications for Jobs

This is the most critical decision when using ACI for short-lived tasks.

| Restart Policy | When Process Exits with Code 0 | When Process Exits with Non-Zero Code | Purpose |
|---|---|---|---|
| **Always** | May restart | May restart | Services/containers meant to run continuously; common default |
| **OnFailure** | Does not restart because exit succeeded | Attempts restart per service behavior | Jobs that must run until successful completion, accepting retries |
| **Never** | Does not restart | Does not restart | One-time tasks where final exit code must be preserved for external evaluation |

### 5.1. Always: Beware of Completed Jobs

If a Java worker finishes processing and calls **System.exit(0)**, selecting **Always** can cause ACI to launch the container again. Consequences:

- Report files duplicated or overwritten.
- Emails/notifications sent repeatedly.
- Extra requests sent to the database.
- Workload keeps consuming compute and memory even though the work is done.

**Never use Always for a one-off batch job** without a clear reason and an appropriate external termination mechanism.

### 5.2. OnFailure: Retries Do Not Replace Idempotency

When a process exits with a non-zero code, OnFailure can re-run it. However, the job may have partially completed before failing. Example:

1. Wrote report to Blob Storage.
2. Had not yet updated status in the database.
3. Container crashed.
4. Retry runs again and generates a second report copy.

Therefore, use **idempotency keys**, completion markers, upserts, or appropriate transactions. Never assume retries are harmless.

**Do not assume** ACI's OnFailure policy lets you configure full retry counts, exponential backoff, or dead-letter policies like a full orchestration system. If complex retry policies are needed, use an external orchestrator or a dedicated jobs service.

### 5.3. Never: Execute Once and Inspect Results

With **Never**, once a container finishes it is not automatically rerun by the restart policy. Success or failure must be evaluated by the orchestrator via:

- Container group state.
- **Container exit code**.
- Application logs.
- Output evidence in Storage/Database.
- Execution duration and alerts.

For jobs requiring **each trigger to create an independent execution**, the cleanest pattern is creating a new container group per unique **run ID** or an organization-supported instantiation pattern. Never rely on restarting an old group to simulate a daily schedule.

## 6. Container Group Lifecycle vs. Process Lifecycle

A container can be waiting, pulling an image, running, or terminated. The group is the outer management entity with an aggregate state.

~~~mermaid
flowchart LR
    A["Create request"] --> B["Pending / Pulling image"]
    B --> C["Running"]
    C --> D{"Process exit code?"}
    D -->|"0"| E["Succeeded / terminated"]
    D -->|"Non-zero"| F["Failed / terminated"]
    F -. "OnFailure may restart" .-> C
    E -. "Always may restart" .-> C
~~~

Depending on the API and timing, you may see **Pending**, **Running**, **Succeeded**, **Failed**, or container-level states like **Waiting**, **Running**, **Terminated**.

### 6.1. Exit Code Is a Technical Signal, Not Complete Business Proof

| Exit Code | Common Interpretation | Limitations |
|---|---|---|
| **0** | Process exited cleanly per app convention | Job could still output bad data if code lacks validation |
| **Non-zero** | Error occurred per app convention | Must inspect logs, error types, and output state |
| No exit code | Container has not finished or failed to start | Inspect group state and events |

Design batch programs to return a **non-zero exit code** whenever business operations fail to complete. At the same time, produce **verifiable results** in an external system outside the container.

### 6.2. When Are Charges Incurred?

ACI generally bills based on requested CPU/memory resources and eligible deployment/running duration per the service price sheet, subject to current metering rules and minimums. Startup time, image pulls, and container/group states are details to verify against current pricing documentation.

Key operational points:

- A container/group remaining **Running** can continue incurring charges.
- A job finishing under the right restart policy can stop consuming compute for that run, yet the **resource record** may persist until deleted.
- Azure Files, Azure Container Registry, logs, IPs/network resources, or supporting services may continue accruing fees.
- Never treat 10 seconds of process CPU time as proof that total metered billing duration is exactly 10 seconds.

Before production deployment, use the ACI pricing page, Azure Pricing Calculator, and Cost Management data to estimate actual configurations.

## 7. Lab A: Running a Short-Lived Job with Azure CLI

In this lab, we run a simple container that prints logs, waits a few seconds, and exits cleanly. **No ports or public IP are needed** because this is not an HTTP service.

### 7.1. Prerequisites

- An Azure subscription and permissions to create resource groups/container groups.
- Azure CLI installed or using Azure Cloud Shell.
- Selected region supports ACI with the illustrative CPU/memory shape.
- Environment can pull images from a public registry without network policy blocks.
- Lab budget, assigned owner, and cleanup procedure after practice.

**Note:** the example uses **busybox:1.36** from a public registry. For enterprise environments, pin image digests and use organization-approved, vulnerability-scanned images; public registries may enforce rate limits or change distribution behavior.

### 7.2. Create the Resource Group

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-aci-batch-lab"
REGION="southeastasia"

az group create \
  --name "$RG" \
  --location "$REGION"
~~~

A resource group organizes lab resources by lifecycle, yet **does not automatically enforce a spending cap**. Budgets and alerts can be created at the scope if permitted.

### 7.3. Create a One-Off Container Group

~~~bash
CG="aci-report-demo"

az container create \
  --resource-group "$RG" \
  --name "$CG" \
  --location "$REGION" \
  --image "busybox:1.36" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --restart-policy Never \
  --command-line "/bin/sh -c 'echo job-start; date; sleep 8; echo job-completed'"
~~~

Explanation:

- **--image** selects an image with a shell and basic utilities.
- **--cpu 1**, **--memory 1.5** are illustrative configurations; these are **requested capacity** and must be verified against SKU/region limits.
- **--restart-policy Never** ensures the container executes only once per policy.
- **--command-line** overrides the image's default command; command syntax may need testing to match how the CLI handles quoting.
- **No --ports or --ip-address Public** because the worker does not serve Internet connections.

This command requests real resource creation and may incur charges. Run only in an approved lab subscription. If image pull or container provisioning fails, read the detailed message instead of switching to broader registry permissions.

### 7.4. Monitor Status

~~~bash
az container show \
  --resource-group "$RG" \
  --name "$CG" \
  --query "{name:name,groupState:instanceView.state,containers:containers[].{name:name,state:instanceView.currentState.state,exitCode:instanceView.currentState.exitCode}}" \
  --output json
~~~

If the job is still Running, check again after an appropriate interval. Once the container finishes, inspect **groupState**, **container state**, and **exitCode**.

An **illustrative** output:

~~~json
{
  "name": "aci-report-demo",
  "groupState": "Succeeded",
  "containers": [
    {
      "name": "aci-report-demo",
      "state": "Terminated",
      "exitCode": 0
    }
  ]
}
~~~

Actual container names are determined by deployment configuration and may differ. The snippet above is **not live command output**. Across API/CLI versions, status field names may vary; inspect the full JSON if a filtered query returns null.

### 7.5. Read stdout/stderr

~~~bash
az container logs \
  --resource-group "$RG" \
  --name "$CG"
~~~

In the lab, expect lines similar to:

~~~text
job-start
...
job-completed
~~~

Logs show which steps the program passed through, yet are **insufficient** if the job writes data externally across multiple steps. Combine exit codes with checks against Blob/Database/job outputs.

### 7.6. When Re-Running Is Needed

Do not treat a completed group as a "scheduler." In standard batch workflows, each execution can use a new **run ID**:

~~~text
aci-report-20261120-001
aci-report-20261120-002
~~~

Ensure names meet ACI naming rules, do not collide, and do not expose sensitive data. The orchestrator must prevent two triggers of the same job from accidentally overwriting each other.

### 7.7. Clean Up the Group

After saving required logs and output evidence:

~~~bash
az container delete \
  --resource-group "$RG" \
  --name "$CG" \
  --yes
~~~

Deleting a container group **does not automatically delete** Azure Storage, ACR, or Log Analytics workspaces it used. Delete only lab resources confirmed with their owner.

## 8. Lab B: Running an HTTP Container to Distinguish Jobs from Services

A container serving HTTP continuously has a different lifecycle from a worker that logs and exits. Illustrative example using a sample web image hosted on Microsoft Container Registry:

~~~bash
WEB_CG="aci-web-demo"
DNS_LABEL="<unique-valid-dns-label>"

az container create \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --location "$REGION" \
  --image "mcr.microsoft.com/azuredocs/aci-helloworld" \
  --cpu 1 \
  --memory 1.5 \
  --ip-address Public \
  --ports 80 \
  --dns-name-label "$DNS_LABEL" \
  --restart-policy Always
~~~

In this scenario:

- The container **must keep running** to serve HTTP.
- **Always** fits better than Never when you want the process restarted per container group policy.
- Public IP/DNS exposes the lab app to the Internet; **never** use an HTTP port 80 demo configuration for sensitive data or production products.
- If TLS/WAF/custom domain/HA are required, use a managed ingress architecture and appropriate supported features.

Inspect the endpoint from actual properties:

~~~bash
az container show \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --query "{state:instanceView.state,ip:ipAddress.ip,fqdn:ipAddress.fqdn,ports:ipAddress.ports}" \
  --output json
~~~

Once the FQDN is verified, test HTTP per lab rules:

~~~bash
curl -i "http://<actual-fqdn>/"
~~~

Do not treat this FQDN or public IP address as a permanent endpoint. When a group is deleted/recreated, verify IP changes, naming, DNS, and service support behavior.

After the lab:

~~~bash
az container delete \
  --resource-group "$RG" \
  --name "$WEB_CG" \
  --yes
~~~

**Comparison:** Web services aim for **stable Running**; batch jobs aim for **Succeeded and exit code 0**. Both run on ACI, yet restart policies, monitoring, and completion criteria differ.

## 9. Declaring ACI with Bicep

With Infrastructure as Code, a container group can be declared as a managed resource instead of being created manually over and over. The following example creates **a one-off Linux job** with no public IP.

~~~bicep
@description('Name of the container group job')
param containerGroupName string = 'aci-batch-once'

@description('Deployment region')
param location string = resourceGroup().location

@description('Approved image for the lab')
param image string = 'busybox:1.36'

resource group 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: containerGroupName
  location: location
  properties: {
    osType: 'Linux'
    restartPolicy: 'Never'
    containers: [
      {
        name: 'job'
        properties: {
          image: image
          command: [
            '/bin/sh'
            '-c'
            'echo start; sleep 8; echo done'
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 1.5
            }
          }
        }
      }
    ]
  }
}

output containerGroupId string = group.id
~~~

Save this content into a Bicep file in your IaC project **if you are actually practicing**. This lesson does not create files outside the assigned documents.

Preview and deploy to the lab resource group:

~~~bash
az deployment group what-if \
  --resource-group "$RG" \
  --template-file aci-batch.bicep \
  --parameters containerGroupName="aci-batch-bicep-demo"

az deployment group create \
  --resource-group "$RG" \
  --template-file aci-batch.bicep \
  --parameters containerGroupName="aci-batch-bicep-demo"
~~~

**Important note on idempotent deployments:** IaC declares desired resource state, **not a job scheduling mechanism**. Do not treat re-running a deployment with the same group name as a guarantee of creating **a fresh execution** with independent history. If multiple runs with separate audit trails are needed, design explicit run IDs and lifecycles.

When creating a group with multiple containers, completion state and billing depend on every container in the group. For short-lived jobs, avoid adding an indefinitely running sidecar.

## 10. Packaging a Java Batch Worker

In the Azure cloud module, a fitting example is a **Java worker generating a report**, finishing, and exiting. Unlike a Java web app, the worker **does not need an open HTTP port** and should not remain Running forever.

### 10.1. Illustrative Java Source

File **BatchReport.java**:

~~~java
import java.time.Instant;

public final class BatchReport {
    public static void main(String[] args) {
        String jobId = System.getenv()
                .getOrDefault("JOB_ID", "local-demo");

        try {
            System.out.println("START job=" + jobId
                    + " at=" + Instant.now());

            // In a real system: read data from Azure Storage
            // or DB, process it, then write output to persistent storage.
            long recordsProcessed = 10;

            System.out.println("recordsProcessed=" + recordsProcessed);
            System.out.println("SUCCESS job=" + jobId
                    + " at=" + Instant.now());

            // Exit code 0 means the process completed by convention.
        } catch (Exception error) {
            System.err.println("FAILED job=" + jobId
                    + " error=" + error.getMessage());
            System.exit(1);
        }
    }
}
~~~

This example is intentionally simple to illustrate **lifecycle and exit codes**, not a production data pipeline. In production, validate data sources, report correctness, retries, and output storage methods.

### 10.2. Multi-Stage Dockerfile

Place **Dockerfile** in the project root:

~~~dockerfile
# Build stage: compile using JDK
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY BatchReport.java .
RUN javac -d /out BatchReport.java

# Runtime stage: only JRE needed
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /out /app
ENTRYPOINT ["java", "-cp", "/app", "BatchReport"]
~~~

For an image used repeatedly, **pin the base image version or digest** per policy and rebuild periodically for patches. Real-world Java images may also need dependencies, toolchains, CA certificates, timezones, locales, and shutdown signal handling.

### 10.3. Local Build and Test

~~~bash
docker build -t orders-report:1.0.0 .

docker run --rm \
  -e JOB_ID="local-001" \
  orders-report:1.0.0

# Inspect exit code immediately after docker run if needed
echo $?
~~~

If the program finishes successfully, the Docker process returns exit code **0** and the container is removed by **--rm**. To test retries, create a controlled test scenario resulting in a non-zero exit code.

### 10.4. Output Data Must Not Live Only in the Container Filesystem

A container's writable filesystem is **ephemeral** relative to the ACI lifecycle. When a container stops, is deleted, recreated, or runs on another host, never rely on data stored solely in the writable layer as a durable result.

Common ways to persist output:

- **Azure Blob Storage**: report files, JSON, CSV, PDF, or artifacts.
- **Azure Files**: file shares when programs require filesystem semantics and service support.
- **Azure SQL Database / Azure Cosmos DB**: business state with appropriate schema and consistency.
- **Queue/Event**: notify downstream workflows that a result has finished processing.

Prefer application protocols and SDKs that write output with **transactions/checkpoints/idempotency**. Avoid treating a single local file write as job completion.

## 11. Pushing the Image to Azure Container Registry (ACR)

ACI can pull images from public registries or a private ACR. For production, ACR lets organizations manage images, access permissions, names/digests, retention, and security tooling per policy.

### 11.1. Image Supply Chain Flow

~~~mermaid
flowchart LR
    DEV["Git source"] --> CI["CI build + test + scan"]
    CI --> IMG["Container image with version/digest"]
    IMG --> ACR["Azure Container Registry"]
    ACR -->|"Pull with right permissions"| ACI["ACI container group"]
    ACI --> OUT["Azure Storage / Database"]
~~~

### 11.2. Example Creating a Lab ACR and Pushing an Image

The commands below are **illustrative only**, requiring proper permissions, a unique registry name, and cost verification before running.

~~~bash
ACR_NAME="<globally-unique-acr-name>"
IMAGE_NAME="orders-report"
IMAGE_TAG="1.0.0"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --location "$REGION"

# Requires Docker engine or appropriate build environment
az acr login --name "$ACR_NAME"

docker tag \
  orders-report:1.0.0 \
  "$ACR_NAME.azurecr.io/$IMAGE_NAME:$IMAGE_TAG"

docker push \
  "$ACR_NAME.azurecr.io/$IMAGE_NAME:$IMAGE_TAG"
~~~

After pushing, verify the repository/tag and, where possible, record the **image digest**:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "$IMAGE_NAME" \
  --output table
~~~

Never enable the broad-privilege **admin user** merely to run a lab quickly in production. For CI/CD, use an identity granted push permissions and an appropriate authentication mechanism.

### 11.3. ACI Pulling Private Images

For ACI to pull a private image, a **registry authentication mechanism** is required:

- Prefer **managed identity and AcrPull permissions** at the appropriate scope **if** the specific combination of ACI, region, and registry/network in use supports this mechanism.
- Some workflows use a registry username/password or token; these are credentials that must be protected, rotated, and excluded from CLI history/repositories.
- If the registry uses a private endpoint, verify networking paths, DNS, ACI private networking support, and image pull requirements.
- Verify the image tag/digest exists and that the image architecture/OS matches the container group.

Never pass an ACR password in command-line examples as **--registry-password plaintext**. Follow current ACI + ACR documentation for your organization's chosen deployment mechanism and ensure credentials cannot leak.

## 12. Environment Variables, Secrets, and Managed Identities

A Java worker often needs configuration values such as:

~~~text
JOB_ID=report-20261120-001
INPUT_CONTAINER=orders
OUTPUT_CONTAINER=reports
LOG_LEVEL=INFO
~~~

These values are not secrets. Using CLI, you can configure:

~~~bash
az container create \
  --resource-group "$RG" \
  --name "aci-env-demo" \
  --location "$REGION" \
  --image "busybox:1.36" \
  --cpu 1 \
  --memory 1.5 \
  --restart-policy Never \
  --environment-variables JOB_ID=lab-001 LOG_LEVEL=INFO \
  --command-line "/bin/sh -c 'echo JOB_ID=$JOB_ID; echo done'"
~~~

**Note:** your local shell may expand **$JOB_ID** before passing the command, depending on quoting. To print an environment variable **inside the container**, escape/quote properly for the shell and tool in use. To avoid confusion, you can also declare commands and environment variables in YAML/Bicep and inspect logs.

### 12.1. Never Expose Secrets as Arbitrary Plaintext Environment Variables

- Never embed passwords/tokens in source code, Dockerfiles, image layers, Git, or command history.
- Use **secure environment variables** or secret references supported by ACI deployment mechanisms when truly required.
- Better yet, for Azure services supporting Azure AD/Entra authentication, use the container group's **managed identity** and the Azure SDK.
- Grant least privilege, such as read access to the exact Blob container or write access to the exact destination per actual authorization capabilities.
- Verify the identity is **assigned to the container group** and the role assignment has taken effect; creating an identity alone does not grant data permissions.
- Never print secret values to stdout/stderr even when a container is short-lived.

### 12.2. Java Example Reading Configuration

~~~java
String jobId = System.getenv("JOB_ID");
String inputContainer = System.getenv("INPUT_CONTAINER");

if (jobId == null || jobId.isBlank()) {
    throw new IllegalArgumentException("Missing JOB_ID");
}
~~~

When connecting to Azure Storage/Key Vault, use the Azure SDK with an appropriate credential provider. Acquiring a token inside a container must match the supported managed identity/runtime mechanism; do not assume every identity endpoint behaves identically across ACI, App Service, and VMs.

### 12.3. Authorization Is Not Only Image Pull

Two independent permission sets:

1. **Image pull**: allows the runtime to retrieve the image from the registry.
2. **Data plane/workload access**: allows the Java worker to read Blobs, write database tables, or access secrets.

A successful image pull does not mean the application has Azure Storage permissions; conversely, a managed identity with Blob rights does not automatically gain permission to pull private images.

## 13. Networking: Public IP, VNet, and Outbound

### 13.1. Batch Jobs Do Not Need Public Inbound

A one-off worker typically only needs **outbound HTTPS** to Azure Storage or external APIs. Do not assign a public IP/port to a container that has no endpoint meant for client requests.

Even when using public networking, evaluate:

- Does the destination allow ACI's outbound IPs?
- DNS resolution, TLS, and firewalls on target services.
- Potential egress IP changes, rate limits, and quotas.
- Risks of exposing images or endpoints with overly broad permissions.

**Do not rely on an immutable outbound IP** from ACI if the service does not guarantee one. If static egress is mandatory, design private networking with a NAT Gateway or a supported equivalent solution.

### 13.2. ACI in a VNet

A container group can be deployed into an Azure Virtual Network subnet under supported conditions. In that case:

- An appropriate subnet is required, typically requiring **delegation to Microsoft.ContainerInstance/containerGroups**.
- Verify IP address planning, NSGs, route tables, DNS, and services supporting ACI in a VNet.
- ACI VNet deployments use private networking; **they do not directly assign a public IP to a VNet-injected group** in the typical supported model.
- If public ingress is needed, design a supported ingress gateway/proxy/load balancer rather than treating the container group itself as an Application Gateway.
- Outbound/NAT paths and image pulls must be verified for the region, subnet, and registry type.
- Groups sharing a subnet must have governed permissions, quotas, and IP allocations.

Diagram:

~~~mermaid
flowchart LR
    T["Authorized event / scheduler"] --> M["Azure control plane"]
    M --> ACI["ACI group in private subnet"]
    ACI -->|"Private IP / TLS"| DB["DB or Storage Private Endpoint"]
    ACI -->|"Via NAT / firewall if needed"| API["External API"]
    DNS["Private DNS / custom DNS"] -. "Name resolution" .-> ACI
~~~

### 13.3. What to Understand About Subnets

Creating a VNet alone is not enough to run a group privately. You must:

1. Create or select a subnet with adequate address space.
2. Verify ACI subnet delegation.
3. Verify regional support and ACI networking feature prerequisites.
4. Create the group referencing the subnet/resource ID.
5. Confirm DNS and routing from the group to dependencies.
6. Test connectivity on real ports (e.g., HTTPS/443) and verify responses.
7. Monitor network egress, firewall logs, and NAT resources if present.

**Never open NSG inbound Any/Any** to troubleshoot a DNS or image pull failure. Pinpoint the exact layer blocking traffic.

## 14. Persistent Storage: Azure Files, Blob Storage, and Lifecycle

A container group is not permanent data storage. If a job generates critical files, ensure they are persisted in durable storage before exiting with code 0.

### 14.1. Three Data Storage Patterns

| Need | Approach | Trade-offs |
|---|---|---|
| Small temp files during execution | Writable container filesystem or supported ephemeral volume | Lost when group is deleted/redeployed; never use as the sole copy |
| Object-style input/output files | Azure Blob Storage via SDK or HTTPS | APIs, retries, identity, object semantics; ideal for reports, CSV, JSON |
| Shared directory with file semantics | Azure Files volume mount if OS and feature supported | Must manage quotas, permissions, networking, file locking, and cost |

### 14.2. Mounting Azure Files

ACI supports mounting Azure Files volumes in supported configurations. With volume mounts:

- Create the Storage Account and Azure file share beforehand.
- Ensure network connectivity to the file service and mount authentication.
- Mount the volume to a container path in the group configuration.
- Check OS limits, POSIX/SMB permissions, file locking, and performance.
- Never embed storage account keys into unprotected repositories or IaC.

Logical illustration:

~~~text
Container /work
    └── /work/output/report.csv
                 |
                 v
Azure Files share: reports
~~~

Volume and credential declarations must follow current ACI documentation. For Java jobs that simply generate one file and upload it, the **Azure Blob SDK** is usually simpler than SMB mounts.

### 14.3. Verify Output Before Reporting Success

A safe execution protocol:

1. Job receives a unique **runId**.
2. Reads input with versioning/ETags if appropriate.
3. Processes and writes output to a staging path, e.g., **reports/runId/tmp/**.
4. Validates size, checksum/schema, and business rules.
5. Publishes a marker **reports/runId/success.json** or updates transactional status appropriately.
6. Only then exits **0**.
7. On error, logs failure details without secrets and exits **non-zero**.
8. Orchestrator advances only when seeing both exit code 0 and valid output status.

Reason: exiting with code 0 before data is successfully uploaded creates a dangerous **false positive**.

## 15. Designing Event-Driven or Scheduled Jobs

ACI provides container compute; it does not natively define a full cron scheduler or business queue. To run on schedules or events, use an external service.

### 15.1. Workflow of a Scheduled Job

~~~mermaid
flowchart TB
    S["Scheduler: Logic Apps / Automation / Function"] --> V["Check schedule, quota, concurrency"]
    V --> I["Create run ID + ACI container group"]
    I --> W["Java worker processes data"]
    W --> R{"Exit code and output?"}
    R -->|"Pass"| OK["Mark success"]
    R -->|"Fail"| FAIL["Mark failure / controlled retry"]
    OK --> C["Save logs, delete group"]
    FAIL --> C
~~~

A scheduler needs permissions to create and read container groups at the defined scope; use a **managed identity**, never storing usernames/passwords in code or job definitions.

### 15.2. Avoiding Duplicate Jobs

When an event is redelivered or a scheduler retries after a timeout, two container groups might process the same input. Use:

- **Job ID** derived from the event/queue message or batch identifier.
- **Idempotency key** in a state store.
- **Already succeeded** check prior to writing output.
- Unique constraints or durably stored orchestration state.
- Concurrency limits and locking/leasing per service support.
- Retry policies at the orchestrator level; avoid unbounded retries across every layer.

For example, instead of writing a fixed **report.csv**, a job can write **reports/2026-11-20/run-123/report.csv**, then update an approved report pointer after verification.

### 15.3. When to Use Azure Container Apps Jobs

If requirements routinely call for **Cron schedules**, **event-driven scaling**, **parallel executions**, **retry policies**, or **execution history** per supported service features, evaluate Azure Container Apps Jobs before building multiple Logic Apps/Functions wrappers around ACI.

ACI remains useful when you need to quickly spin up a container group via API or directly control a single group's lifecycle for a simple task.

## 16. CPU, RAM, Limits, and Performance

### 16.1. Resources Are Both a Technical and Financial Decision

Example:

~~~text
Job A: 1 vCPU and 1.5 GiB RAM, runs for a few minutes
Job B: 2 vCPU and 4 GiB RAM, processes a larger dataset
~~~

Increasing CPU/RAM may make a job run faster, yet per-unit-time costs also rise. Conversely, under-provisioning RAM causes processes to be killed or fail startup.

**Do not assume linear speedup**: a Java worker may be bottlenecked by I/O, API throttling, database connections, garbage collection, or networking rather than CPU.

### 16.2. Time–Cost Optimization Problem

Suppose two configurations of the same task:

| Configuration | Requested Resources | Test Duration | Notes |
|---|---|---|---|
| A | 1 vCPU, 1.5 GiB | 6 minutes | Fewer resources, runs longer |
| B | 2 vCPU, 3 GiB | 4 minutes | More resources, finishes faster |

These are **hypothetical figures**, not ACI benchmarks. To compare costs, apply **current vCPU-second and memory-second unit rates** and metering rules, plus Storage, Registry, and log costs. You cannot pick B solely because it finishes sooner.

### 16.3. Limits to Verify

- Maximum vCPUs/GiB per group and per container in the region.
- Subscription quotas and container group limits.
- OS, image architecture, and supported features.
- Startup and image pull time; large images slow down cold starts.
- Networking/VNet, IPs, ports, DNS, and NAT capabilities.
- Number of containers per group, volumes, log sizes, and API limits.
- Regional capacity availability at deployment time.
- Alignment between container CPU/memory requests and group limits.

Never use ACI to promise few-second startups in every scenario. For strict SLAs, measure startup distributions (p50/p95) and consider pre-warmed alternatives or another service.

## 17. Evaluating ACI Costs for Short-Lived Workloads

### 17.1. Quantitative Example

A hypothetical batch job:

- Runs **20 times/day**.
- Each run takes **4 minutes** (simulated duration for a single run).
- **30-day** month.
- Each container group requests **1 vCPU and 1.5 GiB RAM**.

Total runtime in the example:

~~~text
20 runs/day × 4 minutes/run × 30 days = 2,400 minutes
2,400 minutes ÷ 60 = 40 hours

Converted vCPU-hours        = 1 × 40   = 40 vCPU-hours
Converted GiB-hours         = 1.5 × 40 = 60 GiB-hours
~~~

This is an **illustrative resource-time calculation, not an Azure invoice**. Actual metered billing time depends on service rules, especially creation/start/stop phases and minimum billing increments. Regional prices also differ.

If a container service is left **running continuously** for 30 days:

~~~text
30 days × 24 hours = 720 hours
~~~

That represents a vastly larger provisioned duration than the hypothetical 40-hour batch job. Still, a fair comparison must account for cold starts, image size, throughput, failures/retries, and supporting orchestration services.

### 17.2. Commonly Overlooked Cost Items

| Component | How Costs Can Accrue |
|---|---|
| ACI compute | Billed vCPU/memory and duration |
| Azure Container Registry | Registry tier, image storage, and add-on features |
| Azure Blob Storage/Azure Files | Stored data, transactions, backups, and retention |
| Azure Monitor/Log Analytics | Ingestion, retention, queries, and alerts |
| Network/NAT Gateway/Firewall | Resource/data charges and configuration |
| Orchestration services | Logic Apps/Functions/Automation and API calls depending on model |
| Image scanning/security | Scanning services, security management, or external tools |
| Operations | Engineering effort managing jobs, failures, and reports |

When a job stops running, **do not assume** ACR, Storage, workspaces, NAT Gateways, or network resources stop billing. In particular, NAT resources can bill continuously even when no containers are running, per service pricing.

### 17.3. Post-Deployment Measurement

In Cost Management:

1. Select the subscription/resource group containing the container group.
2. View costs by service/resource/meter over a window long enough for billing data to settle.
3. Cross-check run counts, durations, CPU/memory requests, and retry counts.
4. Compare with orchestrator logs and actual container states.
5. Separate storage, registry, and networking costs to avoid wrong conclusions.
6. Set budgets/alerts for labs and workload groups.

Cost data can lag behind execution, so a chart immediately after running delete is not final proof for a billing period.

## 18. Monitoring and Verifying Job Outcomes

### 18.1. Minimum Signals to Observe

| Signal | Meaning |
|---|---|
| Container group creation request | Whether Azure accepted the deployment request |
| Provisioning state / group state | Whether the group was created and started running |
| Container state / exit code | How the process terminated |
| Startup, image pull, and error events | Whether registry, capacity, network, or image errors occurred |
| Stdout/stderr logs | Which steps the application executed |
| Output verification | Whether reports/files/business state are accurate |
| Run ID and correlation ID | Connects logs to the specific run and input data |
| Runtime duration | Monitors SLOs and costs |
| Retry count and dead-letter/failed jobs | Prevents infinite retries |
| Security/audit events | Who deployed which image and changed configs |

### 18.2. Inspecting Status and Logs via CLI

~~~bash
az container list \
  --resource-group "$RG" \
  --output table

az container show \
  --resource-group "$RG" \
  --name "$CG" \
  --output json

az container logs \
  --resource-group "$RG" \
  --name "$CG"
~~~

For multi-container groups, specify the target container with **--container-name** if supported by your CLI version:

~~~bash
az container logs \
  --resource-group "$RG" \
  --name "$CG" \
  --container-name "<container-name>"
~~~

In production, logs must be collected and stored before the container group is deleted per retention policies; **group-attached stdout/stderr does not replace a durable log store**.

### 18.3. Streaming Live While Running

Commands like **az container attach** can stream output/events while a group is active:

~~~bash
az container attach \
  --resource-group "$RG" \
  --name "$CG"
~~~

For jobs lasting only a few seconds, attach may connect after the process has already exited. Therefore, runbooks should prioritize **show + logs + output validation** rather than relying on interactive sessions to confirm success.

### 18.4. Long-Term Monitoring

For production applications, you should:

- Forward logs/telemetry to an appropriate observability platform where supported by ACI and configuration.
- Use Azure Monitor/Log Analytics and orchestrator monitoring for job failures and runtimes.
- Include correlation IDs in all key log entries.
- Alert if expected output is missing before a deadline.
- Alert on abnormal retry spikes or excessively long-running containers.
- Separate **platform deployment error** alerts from **application business error** alerts.

Never write customer data, secrets, connection strings, or tokens to stdout.

## 19. Troubleshooting: From Image to Business Outcome

| Symptom | Possible Causes | How to Check |
|---|---|---|
| Container group fails to create | Wrong region, quota, invalid CPU/memory, missing permissions | CLI/Activity Log messages, limits, and RBAC |
| Unable to pull image | Wrong image/tag, private registry auth, registry network, rate limiting | Image ref, pull credentials, ACR permissions, DNS |
| Image pulled but process does not run | Wrong ENTRYPOINT/CMD, incompatible OS/architecture | Container events, startup logs, image metadata |
| Job finishes and immediately runs again | **restartPolicy Always** | Check restart policy and exit events |
| Job Failed after a few seconds | Process exited non-zero, missing env/secret, dependency error | Container exit code, stderr, and config |
| Group stays Running too long | Infinite loop, sidecar not exiting, hung external API | Logs, deadlines, timeouts, and group components |
| Job Succeeded but report is missing | Wrote only to local file or insufficient output validation | Check upload/commit and Blob/Database paths |
| Duplicate reports generated | Retry/scheduler spawned two executions | Run IDs, idempotency keys, and orchestration logs |
| Cannot connect to Storage/DB | DNS, firewall, VNet, private endpoint, identity | Network path, RBAC, and app logs |
| No stdout/stderr visible | App does not log, group deleted, wrong container name | Check group state and log retention |
| ACI finished yet bill continues | ACR, Storage, NAT, logs, or metering lag | Cost Management by resource/meter |
| Container killed due to low memory | Low memory request or Java heap exceeded limit | Events, memory usage, JVM flags |
| Private network does not work | Subnet delegation/UDR/NSG/DNS or unsupported VNet feature | Subnet config, effective routes, ACI networking docs |
| Public endpoint unresponsive | Port not opened, process bound to localhost, wrong DNS/port | Group IP, image listener, and logs |

### 19.1. Four-Layer Investigation Process

**Layer 1 — Deployment:** did the container group creation request succeed? Correct subscription, region, SKU, quota?

**Layer 2 — Image/runtime:** did image pull succeed, command exist, container OS/architecture match, and process start?

**Layer 3 — Application/dependencies:** are env vars, managed identity, DNS, networking, Storage/DB, memory, and timeouts working?

**Layer 4 — Business outcome:** is output the right version, free of duplicates, with exit code 0 and a completion marker?

Fix the right layer. Never resolve a private registry error by blindly enabling the admin user, nor open public database firewalls Any/Any to work around a DNS issue.

### 19.2. Java Worker Running Out of Memory

Java uses heap, metaspace, stacks, JIT code cache, and native memory. For a group requesting **1.5 GiB**, do not set heap to 1.5 GiB and expect the JVM to stay safe. Leave headroom for non-heap memory and the container runtime, monitoring GC and peak memory.

JVM settings must be tested with real workloads; never hard-code an **-Xmx** exceeding the memory declared for the container.

### 19.3. When ACI Runs Past Business Limits

Do not rely solely on restart policies. The orchestrator should enforce a **deadline** per job:

1. Create the group with a run ID.
2. Record the start timestamp.
3. Poll status with backoff while limiting API calls.
4. If overdue, log/emit an event and issue stop/delete per runbook.
5. Check whether output partially completed.
6. Decide whether to retry with idempotency or route to a manual handling queue.

## 20. Security and Production Operations

### 20.1. Least Privilege and Identities

Separate responsibilities:

- CI pipeline: allowed only to push images to approved registries/repositories.
- Orchestrator: allowed only to create/read/delete container groups within required scope.
- Container runtime: allowed only to pull required images.
- Java worker: allowed only to read inputs and write outputs at permitted locations.
- Operator: allowed to inspect health/logs without automatically having permission to read sensitive secrets.

Azure RBAC resource management roles do not automatically grant data-plane access on Blob/SQL/Key Vault. Inspect role assignments on each service.

### 20.2. Container Image Hygiene

- Use minimal images from trusted sources.
- Scan for CVEs, inspect dependencies, and sign/govern artifacts when required by workflow.
- Pin versions/digests; avoid relying solely on **latest** in production.
- Avoid running processes as root when unnecessary and where supported by base image/config.
- Never bake private keys, passwords, or tokens into image layers.
- Rebuild images when runtime or OS patches are released.
- Verify SBOMs and licenses if required by organizational policy.

### 20.3. Network Boundary

- Do not assign a public IP if the job only needs outbound connectivity.
- If using a VNet, configure subnet/delegation and DNS per requirements.
- Restrict flows to required private endpoints and APIs.
- Use TLS for data in transit.
- Establish deterministic egress if destination systems enforce IP allowlists.
- Never assume containers running in a VNet automatically have permission to access every private resource.

### 20.4. Data Safety

- Critical input/output must reside in durable storage.
- Enforce timeouts, idempotency, retries, and dead-letter/failed statuses.
- Never delete inputs immediately upon starting processing.
- Write outputs keyed by run ID and publish only after validation.
- Maintain appropriate backup/retention on the storage tier.
- Deleting a container group must never delete business data meant to be retained.

### 20.5. Change Management Workflow

When changing images, CPU/memory, restart policies, or networking:

1. Review changes and blast radius.
2. Test on a small dataset.
3. Measure time-to-start, duration, exit code, and output correctness.
4. Check failure modes and retry behavior.
5. Confirm logs/alerts are complete.
6. Monitor real costs during the initial rollout window.
7. Maintain a path back to a known-good image/config.

## 21. Pre-Production Checklist for Short-Lived Workloads

- [ ] Defined when the job is considered complete and what exit codes mean.
- [ ] Confirmed ACI is the right choice over ACA Jobs, Functions, AKS Jobs, or Batch for the requirements.
- [ ] Image is versioned/digest-pinned and built/tested/scanned per workflow.
- [ ] Correct restart policy: **Never** or **OnFailure** for appropriate jobs; never accidentally Always.
- [ ] CPU/memory requests are sufficient and within supported quotas/regions.
- [ ] Container group contains no unintended infinitely running sidecars.
- [ ] Inbound/public IP is disabled if unneeded.
- [ ] Verified DNS, firewalls, private endpoints, VNet egress, and image pulls.
- [ ] Registry credentials/managed identities are properly configured per supported mechanisms.
- [ ] No secrets in images, repos, command history, or logs.
- [ ] Jobs use run IDs and idempotency to prevent duplicate processing.
- [ ] Outputs are persisted durably and validated prior to exiting cleanly.
- [ ] Deadlines, bounded retries, and failed-job handling are defined.
- [ ] Logs, metrics, correlation IDs, and SLO alerts are active.
- [ ] Schedules or event triggers reside in an appropriate orchestration system.
- [ ] Analyzed ACI costs plus ACR/Storage/NAT/logging costs.
- [ ] Procedures exist to clean up container groups while preserving run evidence.
- [ ] Tested recovery from image pull failures, OOMs, and data connectivity drops.

## 22. Practice Exercises and Reasoning Scenarios

### Exercise 1: Workload Classification

Choose ACI, Azure Container Apps Jobs, Azure Functions, AKS, or Azure Batch for each case:

1. Running a script to process a CSV file for a few minutes, manually triggered by an operator.
2. Cron job running once nightly, needing retries and execution history.
3. 24/7 HTTP REST API with autoscaling and multiple revisions.
4. Tens of thousands of parallel compute tasks.
5. An organization already running AKS that wants to run batch Jobs using existing Kubernetes policies.

Explain the trade-offs rather than merely naming a service.

### Exercise 2: Testing Three Restart Policies

Write a container script that prints **start**, then exits **0**. Run it in a lab with restart policies **Never**, **OnFailure**, and **Always** in separate groups, observing behavior and costs. Next, change the script to exit **1** and observe the differences.

**Warning:** with Always, a restart loop may occur; test only in an approved lab with strict time bounds.

### Exercise 3: Running a Java Batch Image

1. Create **BatchReport.java** and the example Dockerfile.
2. Build/test locally and inspect the exit code.
3. Push to a lab ACR using appropriate permissions.
4. Configure ACI to pull the private image via a supported mechanism.
5. Run with restartPolicy Never and pass JOB_ID.
6. Read logs, exit code, and verify output.
7. Clean up lab resources after saving evidence.

### Exercise 4: Designing an Idempotent Job

A "file uploaded" event may be delivered at-least-once and may be replayed. The worker reads the file, generates a PDF, and updates a database.

Design:

- Idempotency key.
- Mechanism preventing two concurrent executions.
- Output path incorporating run ID.
- Success confirmation method.
- Retry handling when the database is temporarily unavailable.
- Handling when the PDF uploaded yet the database has not committed.

### Exercise 5: Private Networking

An ACI worker may only call Azure SQL via Private Endpoint and write to Blob Storage inside a private network. Diagram subnet/delegation, DNS, VNet paths, RBAC, firewalls, and NAT for egress if required. Explain why assigning a public IP to the group is not a prerequisite for accessing a private database.

### Exercise 6: Cost Analysis

A job runs 30 times/day, 3 minutes each time, with 1 vCPU and 2 GiB, over a 30-day month.

1. Calculate total minutes and resource hours under the assumptions.
2. Calculate converted vCPU-hours and GiB-hours.
3. List cost items tied to CPU/memory/time and separate fixed/ancillary items.
4. Explain why estimates break if Always puts the job into an infinite loop.
5. Propose per-run monitoring KPIs.

### Self-Check Questions

1. What is a container group in ACI?
2. What risk does the default Always restart policy pose to a batch job?
3. Under what scenario can OnFailure produce duplicate output?
4. How does Never differ from OnFailure in handling non-zero exit codes?
5. Is a Succeeded group state sufficient proof that a business report is accurate?
6. Why does ACI not natively replace a CronJob/queue orchestration system?
7. When should you choose ACA Jobs instead of writing a custom scheduler around ACI?
8. How does pulling an image from a private ACR differ from a Java worker's permission to read Azure Blobs?
9. Why should output never be written solely to the container's writable filesystem?
10. When is a NAT Gateway or explicit egress design required?
11. What costs beyond CPU/memory are involved with ACI?
12. Why inspect every container when a group includes sidecars?
13. When a group fails to start, should you investigate image pull or business logic first?
14. How do you prove a job executed effectively once in business terms?

## 23. References

- [Azure Container Instances overview — Microsoft Learn](https://learn.microsoft.com/azure/container-instances/container-instances-overview)
- [Container groups in Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-container-groups)
- [Container restart policies](https://learn.microsoft.com/azure/container-instances/container-instances-restart-policy)
- [Quickstart: Deploy a container instance using Azure CLI](https://learn.microsoft.com/azure/container-instances/container-instances-quickstart)
- [Deploy container groups with Azure CLI and YAML](https://learn.microsoft.com/azure/container-instances/container-instances-multi-container-yaml)
- [Use Azure Container Registry with Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-using-azure-container-registry)
- [Deploy container instances into an Azure virtual network](https://learn.microsoft.com/azure/container-instances/container-instances-vnet)
- [Mount an Azure file share in Azure Container Instances](https://learn.microsoft.com/azure/container-instances/container-instances-volume-azure-files)
- [Azure Container Apps jobs overview](https://learn.microsoft.com/azure/container-apps/jobs)
- [Azure Container Instances pricing](https://azure.microsoft.com/pricing/details/container-instances/)
- [Azure Container Registry pricing](https://azure.microsoft.com/pricing/details/container-registry/)
