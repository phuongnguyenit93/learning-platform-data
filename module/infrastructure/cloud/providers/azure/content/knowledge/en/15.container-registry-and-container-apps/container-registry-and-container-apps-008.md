# Deploying Microservices with Azure Container Apps

> **Chapter:** Container Registry and Container Apps  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data. Learn how to deploy, monitor, secure, and control costs for an application architecture on Azure.

## Lesson Objectives

Upon completing this lesson, you will be able to:

1. Explain the roles of **Azure Container Apps**, **Container Apps environment**, **Container App**, **revision**, **replica**, and **Azure Container Registry (ACR)**.
2. Decompose an application into microservices with clear boundaries of responsibility, APIs, and data.
3. Build and store container images, then deploy two microservices on Azure Container Apps using Azure CLI.
4. Configure **external/internal ingress**, service discovery, environment variables, secrets, and **managed identity**.
5. Understand **KEDA-based scaling**, scale-to-zero, synchronous HTTP calls, and asynchronous queue-based job processing.
6. Roll out new versions using **revisions**, traffic splitting, health checks, and rollbacks.
7. Design logging, tracing, network access controls, budgets, and incident troubleshooting procedures.

## 1. Problem: A Monolithic API Needs to Be Split into Independent Services

A retail company currently runs a single application that handles user requests, product catalogs, orders, and notifications. As demand grows, the development team wants to:

- Release catalog features without redeploying the entire application.
- Scale out the request-receiving API without scaling out the email-sending worker.
- Expose only the public API to the Internet; backend data services should only be called by internal components.
- Push images to a private registry and deploy traceable versions.
- Monitor per-service errors, control costs, and react to changing load.

A simple microservice design:

| Component | Responsibility | Access Method |
| --- | --- | --- |
| `gateway-api` | Public API, aggregates results, and validates input | HTTPS external ingress |
| `catalog-api` | Serves catalog data, owns catalog API and logic | HTTP internal ingress inside the environment |
| `orders-worker` | Processes orders/asynchronous tasks | Ingress not required; reads from queue |
| Azure Container Registry | Stores governed images | Managed identity with pull permissions |
| Azure Service Bus or Queue Storage | Decouples tasks, absorbs traffic bursts | Authenticated connection with least privilege |
| Azure Monitor / Log Analytics | Observes logs, metrics, and errors | Authorized operations team |

In the hands-on lab, we deploy **two HTTP services**; `orders-worker` is presented as an architectural extension without requiring you to provision extra resources.

~~~mermaid
flowchart LR
    U["Users\nInternet"]
    G["gateway-api\nexternal ingress :443"]
    C["catalog-api\ninternal ingress :8080"]
    Q["Queue / Service Bus\nif async is used"]
    W["orders-worker\nno ingress needed"]
    DB["Database / Storage"]
    ACR["Azure Container Registry\nversioned images"]
    OBS["Azure Monitor\nLogs + metrics"]
    U -->|"HTTPS"| G
    G -->|"Internal HTTP\nservice discovery"| C
    G -.->|"Event / message"| Q
    Q -.-> W
    C --> DB
    W -.-> DB
    ACR -.-> G
    ACR -.-> C
    G -.-> OBS
    C -.-> OBS
    W -.-> OBS
~~~

The diagram shows functional flows. In production, choose proper environment boundaries, private networking, per-hop TLS, service-to-service authentication, and database protection per requirements.

## 2. What Is Azure Container Apps?

**Azure Container Apps (ACA)** is a service for running containerized applications and microservice workloads without the development team having to manage the Kubernetes control plane. It lets you deploy container images and configure ingress, scaling, revisions, secrets, and telemetry at a high level of abstraction.

Foundational concepts:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Container image** | Artifact containing code and runtime environment | `myregistry.azurecr.io/catalog-api:v1` |
| **Container App** | Azure resource defining the containerized app and shared settings | `catalog-api` |
| **Container Apps environment** | Shared deployment boundary for multiple Container Apps, with configured networking and observability | `aca-env-dev` |
| **Revision** | Immutable snapshot of versioned/template configuration parts | `catalog-api--r1` |
| **Replica** | A running instance of a revision; can contain one or more containers per template | Replica #1 of revision r1 |
| **Ingress** | How TCP/HTTP traffic enters the app per supported mode | External or internal |
| **Scale rule** | Rule increasing/decreasing replicas based on traffic or events | HTTP concurrent requests, queue length |
| **Secret** | Sensitive value managed at the app level and referenced from container config | `db-password` |
| **Managed identity** | Microsoft Entra identity assigned to an Azure workload | Pull images from ACR without passwords |
| **Container Apps Job** | Resource running tasks to completion on schedule, manual trigger, or events | Batch data import |

### How Does ACA Differ from AKS, App Service, and Azure Functions?

| Service | Focus | When to Consider |
| --- | --- | --- |
| **Container Apps** | Containerized apps, microservices, event-driven workloads, scaling, and revisions with minimal infra ops | APIs, workers, service-to-service, queue consumers |
| **Azure Kubernetes Service (AKS)** | Kubernetes platform with deeper cluster/networking/extension control | Need Kubernetes APIs, controllers, or custom cluster operations |
| **Azure App Service** | PaaS websites/APIs with mature web hosting capabilities | Web apps, APIs needing straightforward deploy/hosting workflows |
| **Azure Functions** | Event-driven functions with tailored triggers and hosting models | Event-driven logic/short tasks or Functions workflows |
| **Azure Container Registry** | Stores images, OCI artifacts, and image access policies | CI/CD build/push/pull, not where containers run |

Choose ACA when you need to run containers under a managed service model, without assuming every Kubernetes requirement or stateful storage constraint is directly solved by Container Apps.

## 3. Resource Architecture and Deployment Boundaries

~~~mermaid
flowchart TD
    SUB["Azure subscription"]
    RG["Resource group: rg-aca-lab"]
    ACR["Azure Container Registry"]
    ENV["Container Apps environment\nregion + networking + logs"]
    G["Container App: gateway-api"]
    C["Container App: catalog-api"]
    GR1["Revision gateway--v1"]
    GR2["Revision gateway--v2"]
    CR["Revision catalog--v1"]
    REP["Replicas per scale rules"]
    SUB --> RG
    RG --> ACR
    RG --> ENV
    ENV --> G --> GR1 --> REP
    G --> GR2
    ENV --> C --> CR
~~~

One **environment** can host multiple Container Apps. Apps inside the same environment can use app-name service discovery when appropriate ingress is configured. The container app resource and environment resource have distinct configuration scopes and lifecycles.

### 3.1. An Environment Is Not a Container App

When creating an environment, you define the deployment context and choices around region, networking, observability, workload profiles, and supported capabilities. Creating the environment does not yet create the `gateway-api` service.

The Container App holds image settings, containers, resources, ingress, secrets, identities, scale rules, and revisions.

**Rule:** not all microservices belong in the same environment. Group by Dev/Prod environment, network boundaries, administrative permissions, and compliance needs. Never share production and lab environments just for service discovery convenience.

### 3.2. Revisions Differ from Replicas

- A **Revision** is created when updating properties within revision scope, such as container image, environment variables, or scale settings per supported mechanics.
- A **Replica** is an actual running instance of a revision; the system scales replica counts up or down based on scaling rules.

Example:

~~~text
catalog-api
  Revision r1 (image catalog-api:v1)
    Replica A
    Replica B

gateway-api
  Revision r1 (image gateway-api:v1)
    Replica C
  Revision r2 (image gateway-api:v2)
    Replica D
~~~

One revision can have multiple replicas. **Increasing replicas does not create a new revision.** In multiple-revision mode, multiple revisions can remain active simultaneously and receive different traffic weights per ingress configuration.

### 3.3. Revision Scope vs. Application Scope

Some property changes create a new revision (such as image and versioned template properties). Some app-level properties can change **without creating a new revision** (such as secrets or ingress configuration within supported scopes).

Practical implication: **changing a secret does not guarantee running containers automatically reload the new value**; a revision restart or new revision rollout may be required depending on how secrets are referenced and runtime behavior. When deploying to production, understand the scope of the property being changed.

## 4. Designing Microservices Before Writing Deployment Commands

### 4.1. Defining Boundaries of Responsibility

Microservices are more than "splitting one application into multiple containers." Each service should have clear responsibilities and interfaces:

- `gateway-api` owns public HTTP handling and response aggregation.
- `catalog-api` owns serving product information.
- `orders-worker` processes queues/asynchronous tasks and must support retries and idempotency.

Clean boundaries let teams deploy and scale services independently without cascading impact when one feature changes. However, too many services add networking, tracing, authorization, and operational overhead.

### 4.2. Synchronous HTTP vs. Asynchronous Queues

| Communication Pattern | Characteristics | Best Fit | Risks |
| --- | --- | --- | --- |
| **HTTP request/response** | Caller waits for downstream completion | Reading catalogs, quick lookups | Timeouts, cascading failures, fan-out |
| **Message queue** | Publisher enqueues message; consumer processes later | Order processing, email, image processing | Duplicate delivery, retries, dead-lettering |
| **Event publish/subscribe** | Multiple subscribers react to events | System synchronization, event-driven workflows | Event schema/versioning and eventual consistency |
| **Dapr (optional)** | Sidecar providing service invocation, pub/sub, state APIs, etc. via components | Reducing infrastructure integration code | Adds runtime configuration, observability, and permissions |

In the lab, `gateway-api` calls `catalog-api` over HTTP. For real order workflows, do not hold an HTTP request open for minutes waiting for an entire workflow to finish; consider a queue + background worker.

### 4.3. Health Endpoints and Stateless Design

Every HTTP service should expose a fast endpoint, such as `GET /healthz`, to indicate the process is alive. For deeper readiness, add `/ready` returning status based on ability to serve requests.

When scaling multiple replicas:

- Never store critical session state solely in one replica's RAM.
- Never store uploads or data needing durability on the local temporary filesystem.
- Use databases, Blob Storage, or appropriate shared storage.
- Design retries, timeouts, idempotency, and graceful shutdown.
- Bound connections per replica so downstream services are not overwhelmed.

### 4.4. Security Boundaries

**Internal ingress** prevents directly exposing the app via ACA's public ingress path in standard designs, yet **does not automatically authenticate that the caller is an authorized application**. If only `gateway-api` should call `catalog-api`, add internal authentication/authorization, appropriate network segmentation, or mTLS/service invocation mechanisms per capabilities and configuration.

Never assume "internal" means a microservice is safe from unauthorized calls from other workloads inside the same environment.

## 5. Example of Two Containerized Microservices

The example uses **Python FastAPI** for readability. The files below are illustrated **within this lesson**, not created on your machine or repository. You can create the following structure inside your own lab directory:

~~~text
aca-microservices-lab/
  catalog/
    app.py
    requirements.txt
    Dockerfile
  gateway/
    app.py
    requirements.txt
    Dockerfile
~~~

### 5.1. catalog-api: Providing Internal Data

File `catalog/app.py`:

~~~python
from fastapi import FastAPI

app = FastAPI(title="catalog-api")

PRODUCTS = [
    {"id": "p-101", "name": "Keyboard", "price": 59},
    {"id": "p-102", "name": "Mouse", "price": 29},
]

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/items")
def list_items():
    return {"items": PRODUCTS}
~~~

File `catalog/requirements.txt`:

~~~text
fastapi
uvicorn
~~~

File `catalog/Dockerfile`:

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
~~~

In production, pin dependency versions, scan images for vulnerabilities, sign/verify artifacts per policy, and pin image digests. The catalog data here is **in-memory mock data**, not production data.

### 5.2. gateway-api: Receiving Requests and Calling Catalog over HTTP

File `gateway/app.py`:

~~~python
import os

import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI(title="gateway-api")
CATALOG_URL = os.getenv("CATALOG_URL", "http://catalog-api").rstrip("/")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/products")
async def products():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CATALOG_URL}/items")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504, detail="catalog-api timeout"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="catalog-api unavailable"
        ) from exc
~~~

File `gateway/requirements.txt`:

~~~text
fastapi
uvicorn
httpx
~~~

File `gateway/Dockerfile` (similar to catalog):

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
USER 10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
~~~

Both applications listen on port **8080** inside the container. Gateway calls an internal URL like `http://catalog-api/items`; the short name `catalog-api` will be resolved by ACA within the same environment **once appropriate ingress is enabled on the target service**.

In practice, never return full internal error details to clients. The example returns a generic message and keeps root cause details in service logs to avoid leaking internal addresses or secrets.

### 5.3. Local Testing Before Pushing to Azure

From the root directory containing `catalog` and `gateway`:

~~~bash
docker build -t catalog-api:local ./catalog
docker build -t gateway-api:local ./gateway

# Run catalog in a dedicated Docker network for the lab.
docker network create aca-lab-net
docker run --rm --name catalog-api \
  --network aca-lab-net \
  -p 8081:8080 \
  catalog-api:local

# Open another terminal; the gateway container reaches catalog
# by container name within the Docker network.
docker run --rm --name gateway-api \
  --network aca-lab-net \
  -e CATALOG_URL=http://catalog-api:8080 \
  -p 8080:8080 \
  gateway-api:local
~~~

Test the APIs:

~~~bash
curl http://localhost:8080/healthz
curl http://localhost:8080/products
curl http://localhost:8081/items
~~~

In local Docker, the two containers communicate directly on **port 8080** via Docker network DNS. After deploying to ACA with ingress, the internal URL `http://catalog-api` does not need a manual container port in this example because ACA ingress routes traffic to `target-port=8080`.

Never expose the catalog port to the Internet in production just because the local test used `-p 8081:8080`; that was solely for inspecting the container in the lab.

## 6. Preparing Azure Resources and Costs

### 6.1. Requirements

- An Azure subscription permitted to create resources and incur charges.
- Current Azure CLI and `containerapp` extension.
- Docker for local testing if practicing Section 5; `az acr build` can build on Azure.
- Permissions to manage resource groups, Container Apps environments, Container Apps, ACR, and user-assigned managed identities.
- If creating role assignments, permission to **assign roles** at the ACR scope; holding Contributor does not automatically grant that permission.
- The ACR resource name must be **globally unique within the service namespace** and follow naming rules.

**Costs may accrue** from ACR, Container Apps compute/requests, environment/logs, networking, and supporting services. Run write commands only in an approved lab; verify pricing for your actual region and subscription.

### 6.2. Declaring CLI Environment Variables

The commands below use **Bash**. If using PowerShell, adapt variable and command substitution syntax accordingly.

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-aca-lab"
LOCATION="southeastasia"
ENV="aca-env-lab"
ACR="acrdemounique12345"
IDENTITY="id-aca-pull"

az extension add --name containerapp --upgrade
~~~

Replace `ACR` with an **actually unique** registry name consisting only of valid characters and approved by your organization. If the extension is already installed, upgrading may require Internet access and developer environment permissions.

### 6.3. Create Resource Group, ACR, and Container Apps Environment

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --sku Basic

az containerapp env create \
  --name "$ENV" \
  --resource-group "$RG" \
  --location "$LOCATION"
~~~

These are **billable resource creation operations**. A new environment typically creates or links logging/observability settings depending on flags and current CLI behavior; verify the exact target Log Analytics workspace if data governance policies apply.

The default environment creation command does not guarantee private VNet or production DNS routing. If private networking is needed, choose a compatible environment type, subnet, routing, DNS, and ingress mechanism from the outset.

### 6.4. Build and Push Both Images to ACR

From the root `aca-microservices-lab` directory containing the two source folders:

~~~bash
az acr build \
  --registry "$ACR" \
  --image catalog-api:v1 \
  ./catalog

az acr build \
  --registry "$ACR" \
  --image gateway-api:v1 \
  ./gateway

LOGIN_SERVER=$(az acr show \
  --name "$ACR" \
  --resource-group "$RG" \
  --query loginServer \
  --output tsv)

echo "$LOGIN_SERVER"
~~~

The resulting image references take the form:

~~~text
<login-server>/catalog-api:v1
<login-server>/gateway-api:v1
~~~

For example `acrdemounique12345.azurecr.io/catalog-api:v1`. For production, use immutable tags paired with **image digests** to trace builds; never rely on a silently overwritten `latest` tag without version governance.

### 6.5. Managed Identity for Container Apps to Pull Images

There is no need to enable the ACR admin user or paste registry passwords into source code. Use a **user-assigned managed identity**:

~~~bash
az identity create \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --location "$LOCATION"

IDENTITY_ID=$(az identity show \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --query id \
  --output tsv)

PRINCIPAL_ID=$(az identity show \
  --resource-group "$RG" \
  --name "$IDENTITY" \
  --query principalId \
  --output tsv)

ACR_ID=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query id \
  --output tsv)
~~~

For an ACR using **classic registry RBAC permissions mode** supporting this role, grant `AcrPull`:

~~~bash
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
~~~

**Verification point:** ACR may use **repository-scoped ABAC permissions mode**; in that case, the required role model differs from `AcrPull`. Verify the permission mode, matching role, and organizational policy before assigning permissions. Role assignments may take time to propagate. The identity needs only pull rights, not push rights or subscription Owner.

If role assignment fails, never fall back to embedding an ACR admin password in production commands as a "quick fix." Contact the IAM administrator to grant the proper role.


## 7. Deploying Two Microservices with Azure Container Apps

Example objectives:

- `catalog-api` accepts traffic only via **internal ingress**, with no direct public URL.
- `gateway-api` has **external ingress** so users can call it over HTTPS.
- Both run in `aca-env-lab`, pulling images from ACR via the user-assigned managed identity.
- Gateway calls catalog using the service name `http://catalog-api` in the same environment.
- Set **min replicas = 1** in the lab to reduce cold starts during testing; set max based on capacity and budget.

### 7.1. Create catalog-api First

~~~bash
az containerapp create \
  --name catalog-api \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$LOGIN_SERVER/catalog-api:v1" \
  --user-assigned "$IDENTITY_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$IDENTITY_ID" \
  --ingress internal \
  --target-port 8080 \
  --transport auto \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 3
~~~

**Parameter meanings:**

| Parameter | Role | Notes |
| --- | --- | --- |
| `--environment` | Specifies the Container Apps environment | Both apps must share the environment to use short names as shown |
| `--image` | Image ref containing catalog code | Fails if missing from registry or lacking pull permissions |
| `--user-assigned` | Attaches the managed identity to the app | Must exist and be managed at the right scope |
| `--registry-identity` | Identity used to authenticate when pulling from registry | Separate from automatically granting ACR permissions |
| `--ingress internal` | Creates an internal endpoint within ACA's supported scope | Not a caller authentication mechanism |
| `--target-port 8080` | Port on which the container process listens | Must match `uvicorn --port 8080` |
| `--cpu`, `--memory` | Resources per replica | Must be a combination supported by the workload profile |
| `--min-replicas`, `--max-replicas` | Autoscaling bounds | 1–3 is purely a lab example |

Creating an app is a **billable operation** requiring appropriate permissions. CLI syntax may vary across extension versions; check `az containerapp create --help` if your CLI expects different syntax.

### 7.2. Verify catalog-api

~~~bash
az containerapp show \
  --resource-group "$RG" \
  --name catalog-api \
  --query "{name:name, state:properties.provisioningState, ingress:properties.configuration.ingress, latestRevision:properties.latestRevisionName}" \
  --output json

az containerapp revision list \
  --resource-group "$RG" \
  --name catalog-api \
  --output table
~~~

Confirm:

1. Provisioning state succeeded.
2. Image ref matches the right version and registry.
3. Internal ingress is enabled with target port 8080.
4. A revision is active and replicas are ready as expected.
5. No `ImagePullBackOff`, process startup failure, or port mismatch errors.

`catalog-api` does not need a public endpoint just for health checks. Use logs, internal ingress calls from an app in the same environment, or an authorized debug mechanism.

### 7.3. Deploy gateway-api with External Ingress

~~~bash
az containerapp create \
  --name gateway-api \
  --resource-group "$RG" \
  --environment "$ENV" \
  --image "$LOGIN_SERVER/gateway-api:v1" \
  --user-assigned "$IDENTITY_ID" \
  --registry-server "$LOGIN_SERVER" \
  --registry-identity "$IDENTITY_ID" \
  --ingress external \
  --target-port 8080 \
  --transport auto \
  --env-vars CATALOG_URL=http://catalog-api \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 5
~~~

The `CATALOG_URL` environment variable holds the internal address called by the gateway app. Since both Container Apps share the same environment and catalog has ingress enabled, the short name `http://catalog-api` resolves through ACA **service discovery**.

If the two apps are deployed in **two different environments**, calling by short name is no longer valid. You must then design DNS/FQDNs, network reachability, and security for cross-environment communication.

### 7.4. Retrieve the URL and Test End-to-End Flow

~~~bash
GATEWAY_FQDN=$(az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo "$GATEWAY_FQDN"

curl -i "https://$GATEWAY_FQDN/healthz"
curl -i "https://$GATEWAY_FQDN/products"
~~~

When working, the `/products` endpoint returns JSON resembling:

~~~json
{
  "items": [
    {"id": "p-101", "name": "Keyboard", "price": 59},
    {"id": "p-102", "name": "Mouse", "price": 29}
  ]
}
~~~

This tests **both microservices working together**, not just the gateway process. Gateway's `/healthz` can return 200 while `/products` returns 502/504 if catalog fails or internal communication breaks.

### 7.5. HTTP/TLS on Public and Internal Paths

- With **external HTTP ingress**, ACA provides an HTTPS endpoint and manages TLS at the entry point per environment/domain capabilities.
- The `gateway-api` container still listens on HTTP port 8080 inside the container; ingress forwards traffic to the target port.
- The internal call `http://catalog-api` in the example uses HTTP through ACA ingress mechanics, **which does not imply end-to-end TLS or mTLS is separately configured**.
- In production designs, assess internal path encryption, service authentication, Dapr/service invocation, private networking, and security policies.

**Do not assume choosing `--ingress internal` automatically verifies JWTs or restricts calls solely to the gateway app.** Service-to-service authorization is a separate concern.

## 8. Service Discovery and Internal Networking

### 8.1. External and Internal Ingress

| Type | Who Can Use the Endpoint? | Example |
| --- | --- | --- |
| **External ingress** | Reachable from outside per network/environment configuration and security controls | `gateway-api` |
| **Internal ingress** | Exposes an internal entry point within ACA-supported scope for authorized apps/workloads | `catalog-api` |
| **No ingress** | Receives no incoming requests via ACA ingress; can still run workers/event consumers | `orders-worker` |

**External** does not necessarily mean the endpoint is always public on the Internet: an **internal Container Apps environment** or network design can alter reachability. Distinguish **environment-level networking** from **app-level ingress**.

**Internal** also does not mean an app only accepts requests from one specific app; evaluate who has network access and enforce appropriate authentication/authorization.

### 8.2. Why Does Calling by Short Name Work?

When multiple Container Apps live in the same environment and the target enables appropriate ingress, service discovery lets callers reference the app name instead of hard-coding individual replica IPs:

~~~text
gateway-api
  GET http://catalog-api/items
      |
      v
ACA service discovery + ingress
      |
      v
catalog-api replicas
~~~

Benefits:

- No need to update IPs when catalog scales replicas.
- Callers do not track lists of replica IPs.
- Catalog revisions can change while keeping the service name stable.

Limitations:

- App names do not replace API versioning; services must stay compatible.
- Synchronous HTTP calls still need timeouts, bounded retries/backoff, and circuit breakers where appropriate.
- Large payloads or deep service call chains increase latency.
- If catalog scales to 0, the first request may hit a cold start.
- A DNS name does not guarantee the target app is healthy or authorized to access data.

### 8.3. VNets and Private Dependencies

An application may need to reach Azure SQL, Storage, or Key Vault over a controlled network. In that case:

1. Verify the Container Apps environment supports the required VNet option and workload profile.
2. Prepare a subnet with sizing and delegation/rules supported by the environment type.
3. Determine whether **private endpoints** are needed for dependent services.
4. Design DNS resolution (Private DNS Zone/Private Resolver when needed).
5. Configure outbound access, firewalls, and NAT as required.
6. Verify Azure RBAC/data-plane permissions independently of networking.

Placing two Container Apps in the same environment does not automatically make Azure SQL/Storage connections private. Never just swap a service URL for a private IP without proper DNS and network setup.

### 8.4. Separating Environments by Operational Boundaries

A deployment model:

| Environment | Purpose | Example Policy |
| --- | --- | --- |
| `aca-env-dev` | Functional testing | Low budget, mock data, scale-to-zero allowed |
| `aca-env-staging` | Integration/revision testing | Production-like config, test data |
| `aca-env-prod` | Serving users | Least-privilege identity, private dependencies, monitoring/SLOs |

Do not share a single environment across Dev and Prod when strict security and permission isolation are required.

## 9. Scaling with KEDA and Scale-to-Zero

Azure Container Apps leverages **Kubernetes Event-driven Autoscaling (KEDA)** under a managed service model. You do not manage a KEDA operator yourself in standard Container Apps.

### 9.1. Replica Count Differs from Revisions

Suppose `gateway-api` has revision `r1` with 2 replicas; KEDA can scale from 2 to 5 replicas when load rises **without creating a new revision**. Changing the image from `v1` to `v2` creates a new revision in the app template.

### 9.2. Common Scaling Types

| Type | Signal | Scenario |
| --- | --- | --- |
| **HTTP scaling** | Concurrent request count per supported threshold | Web APIs, frontends |
| **TCP scaling** | Concurrent TCP connections per supported ingress mechanics | Suitable TCP workloads |
| **Event-driven scaling** | Queue length or event source metric via supported KEDA scaler | Service Bus, Queue Storage consumers |
| **Custom scaler** | Custom metric/trigger per supported integrations | Specialized business integrations |

**CPU/memory scaling** behaves differently from HTTP/event scaling depending on configuration; never assume crossing a CPU threshold automatically scales an app without configured scale rules and min/max bounds.

### 9.3. minReplicas and maxReplicas

| Setting | Pros | Cons |
| --- | --- | --- |
| `minReplicas=0` | Can scale to zero, lowering idle costs per billing model conditions | Cold start on new requests/events; not suitable for all SLOs |
| `minReplicas=1` | Keeps at least one replica active per configuration | Consumes compute even during low traffic |
| `maxReplicas=5` | Caps scaling/costs and downstream load | May be insufficient under massive traffic spikes |

Scale-to-zero is only available when the workload and corresponding **scale trigger** support it. Not every CPU-bound worker lacking HTTP ingress or event scalers will wake automatically from zero. If a long-lived listener is needed, set appropriate min replicas.

### 9.4. Configuring an HTTP Scaling Rule

Example updating the scale rule on gateway where supported by the environment:

~~~bash
az containerapp update \
  --resource-group "$RG" \
  --name gateway-api \
  --min-replicas 1 \
  --max-replicas 5 \
  --scale-rule-name http-concurrency \
  --scale-rule-type http \
  --scale-rule-http-concurrency 50
~~~

This command **modifies revision configuration** and may create a new revision. An HTTP concurrency threshold of 50 **does not mean strictly 50 requests/second**; it is a threshold on **concurrent in-flight requests** as defined by the scaler. Check extension/CLI support and inspect revisions/templates after updating.

### 9.5. Sizing by Concurrency, Latency, and SLO

If an average request takes 0.2 seconds and the system receives 100 requests/second in steady state, approximate concurrent requests in flight are:

\[
L=\lambda W = 100\times0.2=20
\]

If one replica safely serves 10 concurrent requests within the target SLO, at least around 2 replicas are needed under this simple model, **before accounting for headroom, burst skew, cold starts, or dependency bottlenecks**.

Never pick scale rules from CPU alone when APIs spend significant time waiting on databases. Measure **p95/p99 response time** and real application concurrency.

### 9.6. Event-Driven Workers from Queues

The `orders-worker` microservice can process messages from Azure Service Bus or Queue Storage:

~~~mermaid
flowchart LR
    G["gateway-api"]
    Q["Service Bus Queue"]
    K["KEDA scaler\nqueue length"]
    W["orders-worker replicas"]
    DB["Database / external APIs"]
    G -->|"Publish order event"| Q
    Q -->|"Consume"| W --> DB
    Q -.->|"Metric / backlog"| K -.->|"Scale"| W
~~~

A proper consumer must:

- Authenticate to the queue using a managed identity/appropriate permission.
- Handle duplicate messages via an **idempotency key**.
- Enforce bounded retries and **dead-letter** messages exceeding attempt limits.
- Complete/acknowledge messages only after successful processing per queue semantics.
- Cap connections to databases and downstream APIs as replicas scale up.
- Consider **Container Apps Jobs** if the workload is run-to-completion.

Never use high replica counts to mask out-of-order consumers or missing idempotency logic.

## 10. Revisions, Rollouts, and Traffic Splitting

### 10.1. When Is a New Revision Created?

In Container Apps, changing properties inside the **revision template**—such as image, CPU/memory, environment variables, or scale configuration—can create a new revision. App-level settings like secrets and ingress may follow different update lifecycles.

This lets you keep a stable version running while routing a fraction of traffic to a new version before cutting over completely.

### 10.2. Single-Revision vs. Multiple-Revision Mode

| Mode | Characteristics | Usage |
| --- | --- | --- |
| **Single revision mode** | Typically only one active revision at a time per orchestration | Simple releases |
| **Multiple revision mode** | Keeps multiple revisions active, splitting HTTP ingress traffic by weight | Canary, A/B, rapid rollback |

In **multiple revision mode**, two active revisions can consume compute simultaneously; account for costs and limits. Traffic splitting operates on **HTTP ingress**; do not assume identical behavior for event consumers without ingress.

### 10.3. Preparing v2 and Enabling Multiple-Revision Mode

In an approved lab, modify `gateway/app.py` or its response logic (without breaking key API contracts), then build:

~~~bash
az acr build \
  --registry "$ACR" \
  --image gateway-api:v2 \
  ./gateway
~~~

Switch mode:

~~~bash
az containerapp revision set-mode \
  --resource-group "$RG" \
  --name gateway-api \
  --mode multiple
~~~

Then deploy the new image:

~~~bash
az containerapp update \
  --resource-group "$RG" \
  --name gateway-api \
  --image "$LOGIN_SERVER/gateway-api:v2"
~~~

Note: **do not overwrite tag `v1` to point to a different image** and expect ACA to recognize a new revision. Using a new tag/digest aids tracking and triggers a revision when updating the image template.

### 10.4. Viewing Revision Names and Traffic Distribution

~~~bash
az containerapp revision list \
  --resource-group "$RG" \
  --name gateway-api \
  --output table

az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query properties.configuration.ingress.traffic \
  --output json
~~~

Example when two real revisions exist:

~~~text
gateway-api--r1    (image v1)
gateway-api--r2    (image v2)
~~~

These names are illustrative only. Actual revision names are generated by Azure with unique suffixes; **never guess revision names from image tags**.

Once names and health of each revision are verified, apply traffic weights:

~~~bash
# Replace both placeholders with ACTUAL revision names from revision list.
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name gateway-api \
  --revision-weight \
    "<REVISION_V1>=90" \
    "<REVISION_V2>=10"
~~~

The goal is routing roughly **90% of HTTP ingress traffic to v1 and 10% to v2**, per the service's traffic distribution mechanism. This is not a guarantee that every 10 requests sends exactly 1 to v2; small samples may vary.

### 10.5. Canary and Rollback

Safe release workflow:

1. Build/push image v2 with clear tag/digest, scanned per security policy.
2. Deploy the new revision and verify image, startup, health, and dependencies.
3. Shift a small percentage of traffic to v2.
4. Compare 5xx rates, p95 latency, CPU, logs, and traces **by revision**.
5. Gradually increase traffic when SLOs hold and no business errors appear.
6. If v2 fails, shift traffic back to the stable revision; deactivate the faulty revision only after confirming rollback and zero remaining dependencies.

Example rollback to v1:

~~~bash
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name gateway-api \
  --revision-weight \
    "<REVISION_V1>=100" \
    "<REVISION_V2>=0"
~~~

Verify active status and weights after every change. Shifting traffic **does not automatically roll back database schemas or already-processed messages**. For production microservices, design backward-compatible APIs and database migrations for safe rollbacks.

## 11. Secrets, Configuration, and Managed Identity

### 11.1. Environment Variables Are Not for Secrets

In the example, `CATALOG_URL` is a service address, not a secret:

~~~bash
--env-vars CATALOG_URL=http://catalog-api
~~~

However, never pass passwords, connection strings containing credentials, or tokens directly as plaintext environment variables in shell history or deployment pipeline logs.

Azure Container Apps supports **secrets** at the application level and referencing secrets in container configuration. You can combine **Key Vault references** with managed identity where supported for centralized secret lifecycle governance.

### 11.2. Separating Permission Types

| Task | Identity/Permission Needed | Notes |
| --- | --- | --- |
| Deploy Container App | Azure RBAC management-plane rights on environment/app | Distinct from workload runtime rights |
| Pull image from ACR | Identity attached to app with matching pull rights | No registry admin password needed |
| Read Azure Key Vault secret | Workload managed identity with secret read rights | Depends on vault RBAC/access-policy model |
| Read/write Blob Storage | Identity with matching data-plane role | Network access must also permit it |
| Consume Service Bus | Identity with data receiver role | No namespace admin rights needed |
| Publish Service Bus | Identity with data sender role | Scoped to the exact queue/topic |

**A managed identity is an identity, not automatic permission to everything.** Attach the identity to the Container App, then assign the exact role at the exact scope and verify propagation.

### 11.3. Changing a Secret Does Not Always Create a New Revision

Secrets are managed at application scope in the ACA model. Updating a secret value may not create a new revision or immediately refresh the value inside running processes.

Safe workflow:

1. Update the secret/Key Vault reference using supported mechanisms.
2. Verify identity permissions and reference status.
3. Restart the revision or roll out a new revision if required by how the app reads secrets.
4. Verify the system still connects to dependencies.
5. Revoke old credentials only after confirming the app uses the new value.

### 11.4. Never Use Container Filesystems for Business Storage

Replicas can be created or deleted during autoscaling or revision deployments. Data stored solely inside a container's filesystem can be lost when a replica is replaced.

Data classification:

| Data Type | Appropriate Storage |
| --- | --- |
| Request/session | Stateless tokens or shared cache/session store |
| Uploads | Blob Storage or durably engineered storage services |
| Business databases | Azure SQL/Cosmos DB/PostgreSQL per requirements |
| Temporary scratch | Ephemeral storage; acceptable to lose when replica terminates |
| Shared file volumes | Azure Files volumes when supported by ACA and architecture |
| Secrets | Container Apps secrets/Key Vault; never baked into images |

Do not assume an Azure Files volume is a drop-in replacement for a database or solves concurrent-write problems; evaluate file semantics and performance.

## 12. Observability with Logs, Metrics, and Traces

### 12.1. Three Complementary Signal Types

- **Logs:** applications record errors, requests, startup/shutdown, dependency failures, and revisions.
- **Metrics:** request rates, replica counts, CPU, memory, network/HTTP metrics, queue backlogs, and scaling state.
- **Traces:** follow a single request from gateway through catalog to storage/database.

If gateway returns 502, distinguish among:

1. Gateway code cannot reach catalog due to DNS/ingress.
2. Catalog scaled to zero and is not yet ready or failed startup.
3. Catalog returned 500 due to a dependency.
4. Gateway's 5-second HTTP timeout is shorter than reality.
5. Container crashed, image pull failed, or revision is unhealthy.

### 12.2. Viewing Logs with Azure CLI

~~~bash
az containerapp logs show \
  --resource-group "$RG" \
  --name gateway-api \
  --type console \
  --tail 50

az containerapp logs show \
  --resource-group "$RG" \
  --name catalog-api \
  --type console \
  --tail 50
~~~

To stream live in the lab:

~~~bash
az containerapp logs show \
  --resource-group "$RG" \
  --name gateway-api \
  --type console \
  --follow
~~~

With multiple revisions/replicas, select the right revision and replica when viewing logs or filter by labels in the workspace. Console logs primarily capture container stdout/stderr; they do not guarantee structured logging or correlation IDs are configured in the app.

### 12.3. Checking Revision and Replica Status

~~~bash
az containerapp revision list \
  --resource-group "$RG" \
  --name gateway-api \
  --output json

az containerapp show \
  --resource-group "$RG" \
  --name gateway-api \
  --query "{latestRevision:properties.latestRevisionName, ingress:properties.configuration.ingress, template:properties.template}" \
  --output json
~~~

An app showing successful provisioning status can still have container startup failures. Inspect **revision health, replica readiness, startup logs, and image pulls**.

### 12.4. Log Analytics

Depending on environment configuration and log ingestion settings, ACA can send console/system logs to Log Analytics. Common tables include `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL` with fields depending on schema/logging mode.

Example console log query in a workspace with the corresponding table:

~~~kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= ago(1h)
| where ContainerAppName_s in ("gateway-api", "catalog-api")
| project TimeGenerated, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated desc
~~~

**Important:** actual table/column names may vary between resource-specific/legacy schemas and environment pipelines. If a table or column does not exist, inspect the actual schema before editing the query; never infer "zero errors" solely from an empty result.

### 12.5. Correlation IDs and Distributed Tracing

When gateway calls catalog, generate/propagate a **trace ID** and pass context using standards like W3C Trace Context:

~~~text
Client request
  trace_id = abc...
  gateway-api /products
    catalog-api /items
      database query
~~~

Use the OpenTelemetry SDK and an exporter matching your observability system such as Application Insights per supported architecture. Record:

- `service.name`.
- Environment and revision identifier.
- HTTP route and status.
- Dependency latency and error category.
- Never log bearer tokens, passwords, connection strings, or unnecessary sensitive data.

**Never rely solely on a single "500 error" line**: you need to know which request, which revision, which dependency, and at what timestamp.


## 13. Troubleshooting Deployment or Inter-Service Calls

### 13.1. Troubleshooting Table

| Symptom | Common Causes | Evidence and Checks |
| --- | --- | --- |
| App created yet image fails to pull | Wrong image ref, missing ACR rights, private registry, identity still propagating | Check system logs, ACR login server, image tag, identity, and role |
| Container restarts continuously | Process crash, missing env vars, import error, low memory | Console logs, startup command, replica status, CPU/memory |
| Public gateway returns 404 | Wrong route `/products`, app booted wrong code, ingress wrong port | `curl /healthz`, routes in app, target port |
| Gateway returns 502/504 calling catalog | Catalog unready, wrong DNS/ingress, timeout, or backend error | Gateway logs, catalog logs, internal test call |
| `http://catalog-api` does not resolve | Apps in different environments, catalog ingress disabled, or different DNS config | Compare environment ID, ingress, and app name |
| Catalog has internal ingress yet denies access | Authentication/network controls or unauthorized caller | Check policies, app auth, networking, and logs |
| Gateway public FQDN unreachable | Provisioning/ingress unready, wrong FQDN, environment networking | Check `properties.configuration.ingress.fqdn`, provisioning, and environment |
| App errors after changing secret | Process has not loaded new value, wrong Key Vault rights | Check identity, secret reference, restart/rollout |
| Replicas stuck at minimum | No matching scale rule, load below threshold, or unsupported metric | Check scale config and system metrics/logs |
| App scales to 0 and never wakes | Missing qualifying trigger, scaler cannot read event metric | Check KEDA scaler, min replicas, queue permissions |
| Event worker processes duplicates | Message delivery may retry; consumer lacks idempotency | Message IDs, deduplication, dead-lettering |
| Canary produces skewed results | Traffic weights not updated or tests hit revision FQDN directly | Check revision list, ingress traffic, FQDN used in test |
| High cost despite low traffic | min replicas holding compute, multiple active revisions, profile/Log Analytics | Check replica counts, workload profile, retention, and billing |

### 13.2. Layered Troubleshooting

When a client calls `https://<gateway-fqdn>/products` and receives HTTP 502:

**Layer 1 — Public endpoint**

- Call `GET /healthz` on gateway.
- Confirm gateway external ingress, target port 8080, and exact FQDN.
- If `/healthz` also fails, focus on gateway startup, ingress, and TLS/provisioning.

**Layer 2 — Gateway application**

- Read console logs to see whether gateway actually sent the request to `CATALOG_URL`.
- Verify `CATALOG_URL` in the running revision's config; do not look only at the deployment script.
- Check HTTP timeout and exception category.

**Layer 3 — Catalog internal service**

- Confirm `catalog-api` is in the same environment.
- Inspect internal ingress and revision health.
- Test `GET /items` from an authorized network/workload path.
- Read catalog logs and inspect dependencies.

**Layer 4 — Downstream**

If catalog accesses a database, inspect managed identity, DNS, private endpoints, firewalls, connection pools, and SQL metrics. Never raise `maxReplicas` just to mask SQL timeouts.

### 13.3. Startup/Readiness Differs from App Resource Existence

Seeing an ACA resource exist does not mean the HTTP process is ready:

- The image may still be pulling.
- The container may be starting or crash-looping.
- The process may bind `127.0.0.1` instead of `0.0.0.0`.
- Target port differs from the process's actual listening port.
- Misconfigured liveness/readiness probes can trigger restarts or keep replicas out of traffic.
- A mandatory dependency may not be ready yet.

With the FastAPI example, `uvicorn` runs `--host 0.0.0.0 --port 8080` so ACA ingress can forward properly. If you change the port in the Dockerfile or entrypoint, update `--target-port` too.

## 14. Designing Reliability Between Microservices

### 14.1. Timeouts, Retries, and Idempotency

Synchronous service calls must bound wait times. For example, gateway uses a 5-second timeout calling catalog. If catalog does not respond, gateway returns 504 instead of hanging requests indefinitely.

However, **retries** must be deliberate:

- For idempotent HTTP GETs, bounded retries can handle transient errors.
- For an order-creating HTTP POST, blind retries can create duplicate orders.
- Use **idempotency keys**, backoff with jitter, and timeout budgets.
- Cap retry counts to avoid piling extra load onto a failing service.
- Use circuit breakers or cache/stale fallbacks where business logic allows.

### 14.2. Role-Based Health Checks

| Endpoint | Purpose | Example |
| --- | --- | --- |
| `/healthz` | Process is alive | Returns 200 quickly without depending on too many systems |
| `/ready` | Service is ready for new requests | Initialization done; essential dependencies usable |
| `/metrics` | Exports telemetry per supported tools | Should not expose sensitive data publicly |
| `/items` | Business API | Real logic and dependencies |

In ACA, liveness/readiness/startup probes can be defined using supported container probe configs. **Do not assume merely coding `/healthz` automatically configures Azure probes.** Verify the template includes probes with appropriate thresholds.

### 14.3. Container Apps Jobs vs. Long-Running Workloads

If a task only needs to run on events, schedules, or manual commands and then finish, **Container Apps Jobs** may fit better than a Container App running an HTTP server forever.

| Scenario | Option to Consider |
| --- | --- |
| API continuously serving HTTP | Container App with ingress |
| Long-running queue consumer scaling on backlog | Ingress-less Container App with KEDA event scaler |
| Scheduled data import that exits | Scheduled Container Apps Job |
| Migration/manual batch run | Manual Container Apps Job |
| Queue-driven run-to-completion task | Event-driven Container Apps Job where appropriate |

Choose based on error handling, duration, retries, concurrency, and completion mechanics; do not force every task into an HTTP API.

### 14.4. Dapr Is Optional, Not Mandatory

**Distributed Application Runtime (Dapr)** provides building blocks such as service invocation, pub/sub, state management, or bindings via a sidecar and configured components.

Dapr can standardize polyglot interactions, yet:

- Requires selecting proper backend components and authentication.
- Increases configuration, logs, and operational surface to govern.
- Does not automatically keep API contracts or data consistent.
- Does not automatically solve every idempotency/transaction requirement.
- **You do not need Dapr enabled** just to use `http://catalog-api` service discovery inside the same ACA environment as shown.

### 14.5. API Versioning and Database Migrations

A team deploys `catalog-api:v2` while `gateway-api:v1` is still running. If v2 removes a JSON field still used by gateway v1, a canary rollout can fail even though both containers report Healthy.

You should:

1. Define API contracts and schemas.
2. Make **backward-compatible changes** first.
3. Run contract/integration tests across services.
4. Remove old fields only after all consumers have upgraded.
5. Split database migrations into safe, appropriately reversible steps.
6. Test retry/duplicate processing while multiple versions run side by side.

## 15. Production Security: From Image to Runtime

### 15.1. Protecting the Image Supply Chain

- Use ACR or a registry with controlled access.
- Separate CI/CD **push** rights from ACA runtime **pull** rights.
- Use clear image tags/digests; never rely on `latest` for auditable deployments.
- Scan dependencies/images per security workflows.
- Minimize image size and run as non-root when compatible with the app.
- Never package private keys, tokens, passwords, or production `.env` files into images.
- Establish artifact signing/verification and controlled build paths if required by your organization.

### 15.2. Environment and Application Permissions

Roles must be separated by duty:

| Group | Permissions Needed | Should Not Have by Default |
| --- | --- | --- |
| Developer | Read logs, deploy apps in Dev | Rights to alter entire production networking |
| CI/CD deployment principal | Update Container Apps/registry at exact scope | Subscription-wide Owner |
| Workload identity | Pull images, read business-scoped secrets/data | Push images or create role assignments |
| SOC/SRE | Metrics, logs, incident operations | Rights to read secrets or delete environments |
| FinOps | Cost visibility, budgets/alerts | Rights to modify business data |

A managed identity is only an identity; Azure RBAC must assign the right role at the right resource, and data-plane access must be authorized separately when required.

### 15.3. Ingress Does Not Replace Authentication

Public external ingress requires:

- Properly configured TLS/HTTPS and certificate management.
- Authentication/authorization, API gateway, or identity proxy where required by business logic.
- Rate limiting, WAF, or appropriate L7 protections.
- Proper CORS, without treating CORS as an authentication mechanism.
- Custom domain, DNS, and certificate rotation management.

Internal ingress still requires defining the **trust boundary**: which apps may call, which tokens/service identities are accepted, and which data may be read or mutated.

### 15.4. Environment-Specific Secrets and Config

- Dev/Staging/Prod have distinct secrets and corresponding identities.
- Production secrets never reside in repos or command logs.
- Scope Key Vault/Storage/Service Bus access to the minimum required.
- Test rotation and recovery rather than waiting for secrets to expire.
- Never dump all env vars to logs when they may contain secrets.

### 15.5. Resource Limits and Protecting Downstream Services

Bound CPU/memory per replica to prevent incompatible configurations or budget overruns. Yet if memory is set too low, containers can OOM or crash-loop.

When raising max replicas, inspect total connections, queues, consumers, and backend quotas. **Scaling out does not automatically increase Database or Service Bus capacity.**

## 16. Costs and Workload Profile Selection

### 16.1. Potential Cost Items

An ACA architecture can accrue charges from:

| Component | Cost Factors to Check |
| --- | --- |
| Container Apps compute | vCPU/memory usage, replica count, workload profile, and billing rules |
| HTTP requests | Request billing model per tier/service conditions if applicable |
| Dedicated workload profile | Provisioned compute capacity and utilization under profile model |
| Azure Container Registry | SKU, image storage, builds/tasks, and networking |
| Log Analytics/Monitor | Data ingestion, retention, alerts, and observability |
| Networking | VNets, private endpoints, egress/NAT, data transfer |
| Service Bus/Storage/Database | Dependent resources and transactions |
| Multiple active revisions | Concurrent compute during canary rollouts |
| Min replicas > 0 | Replicas staying active during low traffic |

**Pricing varies by region, workload profile, plan, and time.** Never treat a fixed number in a lesson as a production cost guarantee.

### 16.2. Consumption vs. Dedicated Workload Profiles

- **Consumption:** suits elastic load-based scaling with scale-to-zero on supported triggers; compute/request billing follows applicable policies.
- **Dedicated workload profiles:** suit predictable capacity needs, specialized compute/networking traits, or tailored cost models with separate pricing.

When choosing, weigh region, resource requirements, scale bounds, idle duration, networking model, and profile support. Never assume **Consumption is always cheaper** or dedicated is always faster: benchmark real workloads and use pricing calculators.

### 16.3. Sizing with Little's Law

Suppose:

~~~text
Incoming rate:       200 requests/second
Average latency:     0.25 seconds
Average concurrency ≈ 200 × 0.25 = 50 requests
~~~

If one replica safely handles roughly 10 concurrent requests within SLO, you need at least about **5 replicas in an ideal model**, before adding headroom.

If peak-hour latency rises to 1 second due to a slow database, concurrency can jump to **200**; adding replicas without fixing the database can worsen backlogs and inflate costs.

Therefore size according to:

- Real request rates and concurrency.
- CPU/memory per replica.
- p95/p99 latency and error rates.
- Headroom and warm-up time.
- Database connections, queue consumers, and service quotas.
- Max replicas balanced for both cost and downstream limits.

### 16.4. Reducing Costs Without Breaking SLOs

- Use `minReplicas=0` for services that tolerate cold starts and have supported triggers.
- Use `minReplicas=1` or higher for endpoints requiring consistently low latency.
- Cap max replicas based on backend load tests.
- Avoid hoarding excessive images/tags or leaving unneeded active revisions running.
- Tune log retention, sampling, and verbosity to match audit requirements.
- Use Cost Management budgets and cost alerts.
- Clean up lab resources after studying using a verified checklist.

## 17. Comprehensive Hands-On Exercise

### 17.1. Scenario

The Dev team wants to deploy:

- `catalog-api` serving internal data, 1–3 replicas.
- `gateway-api` public HTTPS, 1–5 replicas.
- Images in ACR, pulled via managed identity.
- Both apps in the same environment.
- Ability to release gateway v2 and run a canary check.
- Error logging and cost tracking.

**Completion criteria:** calling HTTPS `/products` on gateway returns catalog data, catalog has no direct public ingress, and you can explain how scaling and rollbacks are configured.

### 17.2. Action Checklist

| Step | Task | Evidence |
| --- | --- | --- |
| 1 | Select subscription and verify permissions | `az account show` accurate |
| 2 | Create lab environment/ACR | Resources present in right region/resource group |
| 3 | Build/push `catalog-api:v1` and `gateway-api:v1` | Both image tags visible in ACR |
| 4 | Provision identity and pull permissions | No ACR admin password used |
| 5 | Deploy catalog with internal ingress | App has healthy revision, target port 8080 |
| 6 | Deploy gateway with external ingress and `CATALOG_URL` | Public HTTPS FQDN active |
| 7 | Call `GET /healthz` and `GET /products` | HTTP 200, valid response |
| 8 | Inspect min/max replicas and logs | Template and console logs readable |
| 9 | Build/push v2, enable multiple revisions and canary | Two revisions have traffic weights |
| 10 | Roll back to v1 on simulated fault | Ingress traffic restored 100% to v1 |
| 11 | Check resource usage and costs | Cost estimate and budget created |
| 12 | Clean up lab when permitted | No accidental deletion of another team's resources |

### 17.3. Scenario Question A — Gateway Returns 502

Gateway `/healthz` returns 200, yet `/products` returns 502. Catalog logs indicate the process did not start on the expected port.

**Question:** where does the primary fault lie?

**Hint:** not in frontend TLS or gateway's FastAPI `/healthz` code. Check catalog's target port 8080, process binding to `0.0.0.0`, revision health, and console logs, then test internal calls from gateway.

### 17.4. Scenario Question B — Scaling to 10 Replicas Causes SQL Errors

A service starts with 2 replicas, each using up to 30 SQL connections. When scaled to 10, potential connections become:

\[
10\times30=300
\]

If the database safely handles roughly 150 connections per load tests, this scale-out can cause contention or timeouts.

**Answer:** adjust connection pooling, concurrency, database capacity, and max replicas; never assume higher max limits are always better.

### 17.5. Scenario Question C — 10% Canary Still Shows Errors on v1

`gateway-api:v2` receives only 10% of ingress traffic, yet a database migration altered the schema so v1 also fails.

**Lesson:** traffic splitting at the gateway does not isolate all shared changes. Database schemas, queues, and data contracts must be designed for multi-version compatibility.

### 17.6. Scenario Question D — Worker Receives a Message Twice

The `orders-worker` service processes an order, then restarts before acknowledging message completion. The queue redelivers the same message.

**Answer:** the consumer must enforce **idempotency** by order ID/message ID and complete messages strictly per queue semantics; retries and dead-lettering must be handled deliberately.

### 17.7. Scenario Question E — Choosing minReplicas

| Workload | Option to Consider |
| --- | --- |
| Payment API needing low p99, zero cold starts | Keep min replicas > 0 with headroom |
| Worker running a few times daily from a queue | Can set min=0 if event scaler fits |
| Catalog called continuously by many APIs | Set min replicas to match real load, not just idle savings |
| Batch import running on schedule then exiting | Evaluate a Container Apps Job |

No single min replicas value fits every service. Decisions must tie to SLOs, trigger behavior, and cost.

## 18. Cleaning Up and Protecting the Lab Environment

### 18.1. Clean Up Only Verified Lab Resources

After testing, inventory the Apps, environment, ACR, identity, Log Analytics workspace, and role assignments created. If resource group `rg-aca-lab` **contains solely resources created by this lab** and you have verified no other workloads depend on them, you may delete the resource group per approved procedures.

~~~bash
# READ-ONLY check before cleaning up.
az resource list \
  --resource-group "$RG" \
  --output table
~~~

Deleting resources is a **destructive operation** and should never run until scope is 100% verified:

~~~bash
# Run only when RG holds solely lab resources and deletion is approved.
az group delete \
  --name "$RG" \
  --yes
~~~

Never run this on a resource group holding shared resources. If the environment or ACR is shared with other services, delete only individually identified lab resources after checking dependencies.

### 18.2. Post-Cleanup Checks

- No lab compute/registry resources remain incurring unwanted charges.
- Role assignments and identities reviewed per procedure.
- No secrets or sensitive test data left in logs/artifacts.
- Data requiring retention has been backed up or exported per policy.
- Cost Management shows no lingering anomalous spend from the lab environment.

## 19. Self-Check Questions

**Question 1.** How does a Container Apps environment differ from a Container App?

**Answer:** An environment is the shared deployment context covering networking/observability/workload profiles; a Container App is the application resource defining images, ingress, secrets, identities, revisions, and scaling.

**Question 2.** An app has one revision yet four replicas. How many configuration versions are deployed?

**Answer:** One revision running across four replicas; replica count does not equal revision count.

**Question 3.** Why is setting `--ingress internal` on `catalog-api` insufficient to guarantee only `gateway-api` can call it?

**Answer:** Internal ingress limits network reachability per environment settings, yet does not authenticate or authorize caller identities. Trust boundaries and auth controls are still required if business rules demand them.

**Question 4.** If two apps share the same ACA environment, how does gateway typically call catalog?

**Answer:** With appropriate ingress configured, it can use an internal URL like `http://catalog-api` via ACA service discovery rather than managing replica IPs.

**Question 5.** A managed identity is attached to an app, yet it still cannot pull the ACR image. Why?

**Answer:** The identity needs the exact pull role matching the ACR permission mode and scope; role assignments might still be propagating, or the image reference/networking may be wrong.

**Question 6.** When changing the image from `gateway-api:v1` to `gateway-api:v2`, what happens?

**Answer:** Updating the container image in the revision template creates a new revision per ACA mechanics; verify health and traffic routing. It does not immediately delete the old revision.

**Question 7.** Does KEDA HTTP concurrency 50 mean the service automatically scales at 50 requests/second?

**Answer:** No. Concurrency measures simultaneous in-flight requests; requests/second also depends on request processing time and traffic shape.

**Question 8.** Why can `minReplicas=0` cause high latency on the first request?

**Answer:** The service must spin up a replica from zero once triggered; cold start and warm-up delays can occur.

**Question 9.** During a 90/10 rollout between v1 and v2, can you immediately delete v1?

**Answer:** You should not. Keeping v1 active enables fast rollback if needed; verify health, data compatibility, traffic, and dependent resources before deleting.

**Question 10.** Why can scaling out a worker from 2 to 10 destabilize a database?

**Answer:** Total concurrent connections/requests to the database can surge past backend limits; control concurrency, connection pooling, and database capacity.

**Question 11.** What kinds of tasks suit Container Apps Jobs?

**Answer:** Run-to-completion tasks triggered manually, on schedules, or by events per service support, rather than continuously listening HTTP servers.

**Question 12.** Why might changing a secret not create a new revision or immediately update running processes?

**Answer:** Secrets are scoped at the app level and apps may only read them at startup; a restart/rollout workflow and secret reference check are needed.

## Key Takeaways

- **Azure Container Apps** runs containerized microservices without requiring you to operate Kubernetes clusters.
- A **Container Apps environment** hosts multiple apps; each app has **revisions** and each revision has **replicas** adjusted by scaling.
- Use **external ingress** for public-facing entry points and **internal ingress** for internal services, while still designing authentication/authorization and private networking when needed.
- Store images in **ACR**, use **managed identities** with least-privilege pull rights; never place credentials inside images or scripts.
- **KEDA scaling** reacts to concurrency/queues/events; `minReplicas=0` can save costs yet requires accepting cold starts and valid triggers.
- **Multiple revisions + traffic splitting** support canary rollouts and rollbacks, yet do not protect against breaking schema migrations or event contracts.
- Reliable microservices require **stateless design, timeouts, bounded retries, idempotency, health checks, logs, metrics, and tracing**.
- Always verify **SLOs, access permissions, regions/networking, budgets, and costs** before and after deployment.
