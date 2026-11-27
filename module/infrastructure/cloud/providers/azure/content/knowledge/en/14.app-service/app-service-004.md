# Deploying Containers to App Service

A web application can run fine on a laptop yet fail when moved to the cloud due to a different runtime version, missing OS libraries, wrong port configuration, or an environment that prevents writing files where the app expects. Packaging an application as a **container image** describes the components needed to run the program consistently. **Azure App Service** lets you deploy a web app or API using that image on an Azure-managed platform, instead of provisioning and maintaining VMs or standing up a Kubernetes cluster just to run a small service.

Within the **Web Applications with App Service** chapter of the **CLOUD_PROVIDERS_AZURE** module, this lesson walks through building, testing, storing, and deploying a **Linux custom container** to **Azure App Service**, specifically via **Azure Container Registry (ACR)**. The entire workflow ties into the rest of the module: subscriptions and resource groups for resource organization, Microsoft Entra ID and managed identities for access control, virtual networks and Private Endpoints for data connectivity, Azure Monitor for observability, and Azure Cost Management for cost control.

After this lesson, you will be able to:

- Distinguish between a Dockerfile, image, container, registry, App Service Plan, and Web App.
- Build a minimal web image, test it on your development machine, and push it to ACR.
- Deploy a custom container from ACR to a Linux Web App, configuring ports and app settings.
- Set up a **managed identity** so App Service pulls private images without storing long-lived registry passwords.
- Explain startup behavior, health checks, scale-out, rolling releases, and deployment slots.
- Design network access, security, state storage, logging, image-pull error troubleshooting, and cost optimization.

## 1. Why deploy containers on App Service?

Azure App Service is a PaaS platform for running websites and APIs, providing capabilities such as an HTTPS entry point, app configuration, custom domains, certificates, scaling, monitoring, and deployment. In the **built-in runtime** model, you deploy source/artifacts and App Service manages a supported runtime. In the **custom container** model, you are responsible for building an image containing the runtime, libraries, and app, while App Service manages the hosting platform and container execution lifecycle as supported by the service.

For example, a Java API using native libraries, a Node.js app with specialized packages, or a Python server needing a specific OS version. Packaging them in an image lets you promote the same artifact through dev, test, and production; however, you must still account for differences in app settings, identity, networking, filesystem, scaling, and data.

| Hosting option | What you deploy | What Azure primarily manages | When suitable |
|---|---|---|---|
| App Service built-in runtime | App source code/package | Supported runtime and App Service platform | App uses a supported stack/runtime and you want minimal Docker overhead |
| **App Service custom container** | **Pre-built image** and Web App configuration | Container execution platform, HTTPS edge, scaling, and PaaS features | Need custom runtime/dependency packaging for web/API apps |
| Azure Container Apps | Image + container app/revision model | Container platform with microservice capabilities and supported autoscaling | Container workloads needing diverse scaling, service-to-service traffic, or background processing |
| Azure Kubernetes Service (AKS) | Workloads and Kubernetes manifests | Managed control plane; much of cluster/workload operations remain yours | Need Kubernetes APIs, scheduling, and full orchestration ecosystem |
| Azure VM | OS, runtime, container engine, and app | Underlying compute infrastructure | Host/OS control requirements beyond PaaS boundaries |

**No single option is always best.** App Service custom containers fit web/API apps that can run in a container under the service's model. If a workload needs complex multi-container coordination, privileged daemons, custom host networking, specialized batch jobs, or deep Kubernetes orchestration, evaluate Container Apps/AKS/VMs rather than forcing everything into a Web App.

### Shared responsibility

| Area | Application team responsibility | Azure platform responsibility |
|---|---|---|
| Application code | Develop, patch bugs, secure data | Does not automatically fix application bugs |
| Container image | Choose base image, patch OS packages, scan CVEs, sign/pin artifacts | Provides the App Service environment to run the image |
| App runtime | Define entrypoint, listener, port, health endpoint | Launches/monitors the container per service configuration |
| Data and secrets | Permissions, Key Vault, backups, durable data storage | Provides storage/security services as configured |
| Networking | Inbound/outbound configuration, identity, access restrictions | Network infrastructure and PaaS features |
| Scaling and SLA | Choose plan/SKU, instance counts, health checks, and app architecture | Operates service-level availability capabilities |

A container image **does not eliminate OS patching responsibility**: if your image uses a base with vulnerabilities, the engineering team must rebuild and deploy a patched image. Azure does not automatically rebuild your Dockerfile just because a new base image is released.

## 2. Deployment flow from source to users

An example system includes a repository containing source code and a Dockerfile, a build pipeline, Azure Container Registry, and Azure App Service:

~~~mermaid
flowchart LR
    DEV[Source code + Dockerfile] --> CI[Build/test/scan image]
    CI --> ACR[Azure Container Registry]
    ACR -->|Pull image| APP[Azure App Service Linux Web App]
    USER[HTTPS Users] --> APP
    APP -->|Managed identity / data| KV[Key Vault]
    APP -->|Private/network access| DB[(Azure SQL / Storage)]
    APP -. Logs + metrics .-> OBS[Azure Monitor / App Insights]
    ADMIN[Entra ID + Azure RBAC] -. Governance .-> ACR
    ADMIN -. Governance .-> APP
~~~

Walkthrough:

1. Developers update source code, Dockerfile, and unit tests.
2. CI runs tests, scans dependencies/images, and builds a **Linux image**.
3. The image is tagged by version or commit and pushed to a private registry such as **ACR**.
4. The Web App is configured to reference the target image/tag (or digest in supported workflows).
5. App Service needs **network reachability to the registry and pull permissions**, then instantiates containers on its workers.
6. The container listens on the expected IP/port; App Service routes HTTP/HTTPS traffic from the frontend to the container.
7. App settings/managed identity/networking enable data access; logs and metrics provide observability.

**A successful image build does not mean a successful deployment.** The registry may deny pull access, the app may crash at startup, or the port may be wrong. Each boundary requires its own verification.

### Key components to remember

| Component | Role | Example |
|---|---|---|
| **Dockerfile** | Recipe for building an image | Select Node/Python/Java base, copy code, declare startup |
| **Image** | Immutable artifact at the digest level | `orders-api:1.0.0` |
| **Container** | Running process created from an image | App Service starts an app instance |
| **Registry** | Stores images/repositories and tags | `myregistry.azurecr.io/orders-api:1.0.0` |
| **App Service Plan** | Shared compute capacity, OS, region, SKU, and scaling for Web Apps | Linux plan `asp-orders-prod` |
| **Web App** | Application resource, image config, settings, URL, identity | `app-orders-prod` |
| **Managed identity** | Workload identity managed by Entra | Web App pulls images and reads secrets with distinct permissions |
| **Health Check** | Evaluates instance readiness via an HTTP endpoint | `/health` |

An image tag is a mutable reference that can be updated to point to a different digest if the pipeline allows it. For reproducibility and reliable rollbacks, manage exact **image digests** and immutable tag policies rather than relying solely on `latest`.

## 3. Preparing a proper Dockerfile for App Service

This lesson's example uses a **Node.js HTTP server with standard library modules only**, so you can clearly observe port binding, startup, and health check behavior. Real applications can use Spring Boot, ASP.NET Core, Python, Go, or other runtimes, provided the image meets App Service requirements.

### 3.1. `server.js` file

~~~javascript
const http = require("node:http");

// App Service forwards HTTP traffic to the configured port.
// In this example, the app's PORT and WEBSITES_PORT must match.
const port = Number(process.env.PORT || 8080);

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ready" }));
    return;
  }

  if (req.url === "/") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      service: "azure-app-service-container-demo",
      message: "Hello from a Linux custom container"
    }));
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "not-found" }));
});

server.listen(port, "0.0.0.0", () => {
  console.log("HTTP server started on port " + port);
});

process.on("SIGTERM", () => {
  console.log("Shutdown requested");
  server.close(() => process.exit(0));
});
~~~

**Why bind `0.0.0.0`?** If the application listens only on `127.0.0.1` inside the container, traffic from App Service infrastructure to the container's network interface may fail to connect. Listen on the address compatible with container networking and use the port matching forwarding configuration.

`/health` in this demo merely confirms the HTTP server responds. In production, design readiness checks around essential dependencies—without creating an endpoint that synchronously calls a cascade of external services such that one shared blip evicts all instances from the pool.

### 3.2. `Dockerfile` file

~~~dockerfile
# Choose a maintained base image and pin its digest for production.
FROM node:22-alpine

ENV NODE_ENV=production
ENV PORT=8080

WORKDIR /app
COPY --chown=node:node server.js /app/server.js

# Avoid running the app as root unless strictly necessary.
USER node

# EXPOSE is metadata only; the application must still actually listen.
EXPOSE 8080

CMD ["node", "server.js"]
~~~

In production, **pin base images by digest**, track Node/image support timelines, and rebuild when patches ship. `node:22-alpine` is a learning example, not a guarantee that it is always the newest base or compatible with every native dependency. For Java, Python, or .NET, use multi-stage builds to shrink the runtime image, strip build tools, and limit privileges inside the container.

### 3.3. Build and test locally

In a directory containing only `server.js` and `Dockerfile`:

~~~bash
docker build -t appservice-demo:1.0.0 .

# Forward host port 8080 to container port 8080.
docker run --rm --name appservice-demo-local \
  -p 8080:8080 appservice-demo:1.0.0
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Expect both endpoints to return HTTP 200, with `/` returning the service description JSON and `/health` returning `{"status":"ready"}`. If local Docker runs fail, fix them before pushing to the cloud: App Service cannot resolve syntax errors, wrong `CMD`s, missing files, or a process that never listens.

### 3.4. Test startup and shutdown

- `docker logs appservice-demo-local` should display the expected startup line.
- When sending `SIGTERM`, the server stops accepting connections and closes the listener cleanly.
- Do not write persistent data to the container filesystem and assume it survives restarts.
- Never place secrets inside a `Dockerfile`, build arguments baked into image metadata, or source code.
- Ensure the image targets the CPU architecture supported by App Service Linux; an ARM image built on a laptop may fail on x86_64 workers.

Inspect the image:

~~~bash
docker image inspect appservice-demo:1.0.0 \
  --format '{{.Os}}/{{.Architecture}}'
~~~

For example, expect `linux/amd64` for a compatible Linux x86_64 environment. On Apple Silicon/ARM machines, build explicitly for the target platform or use ACR Tasks / an appropriate CI runner instead of assuming a local image runs on Azure.

## 4. App Service Plan and Web App: two distinct resources

An **App Service Plan** defines shared compute capacity and attributes such as Linux OS, region, tier, worker count, and scaling. A **Web App** is the application configuration running on a plan: image, domain, app settings, identity, health check, logging, and deployment.

~~~mermaid
flowchart TB
    SUB[Subscription] --> RG[Resource group]
    RG --> PLAN[Linux App Service Plan]
    PLAN --> WEB1[Web App orders-api]
    PLAN --> WEB2[Web App internal-api]
    WEB1 --> IMAGE1[ACR Image orders-api]
    WEB2 --> IMAGE2[ACR Image internal-api]
~~~

One plan can host multiple compatible apps sharing compute. When two apps share a plan, traffic spikes or heavy CPU tasks in one app can affect the other if headroom is insufficient; scaling the plan affects shared costs. Conversely, separating plans isolates critical workloads while increasing the number of billing units.

### Criteria for selecting a plan

| Criterion | Decision needed |
|---|---|
| Operating system | **Linux** when running Linux custom containers |
| Region | Close to users/data sources; consider latency, feature availability, and residency |
| SKU | Sufficient CPU/RAM, scaling, deployment slots, networking, and SLA; don't automatically pick the cheapest |
| Instance count | Single instance for labs; production often needs multiple instances per SLO |
| App placement | Which apps can share a plan without hurting performance or security |
| Configuration management | Resource group/subscription/tags, Azure Policy, IaC, deployment process |

Do not group applications of vastly different criticality onto one plan merely because they use the same programming language. When **deployment slots** are required, pick a tier that supports them (typically Standard/Premium or above in the relevant App Service model); do not assume a Basic lab plan includes slots.

## 5. Azure Container Registry: storing images for Azure

**Azure Container Registry (ACR)** is a private container registry. A repository can hold multiple tags and manifests/digests:

~~~text
myregistry.azurecr.io/appservice-demo:1.0.0
myregistry.azurecr.io/appservice-demo:1.0.1
myregistry.azurecr.io/appservice-demo:commit-abc1234
~~~

Here:

- `myregistry.azurecr.io` is the **login server**.
- `appservice-demo` is the repository.
- `1.0.0` is the tag; the image is uniquely identified by its digest.

For production releases, prefer build/commit-based tags, validate artifacts, and record digests. Avoid using `latest` as the sole source of truth, because pushing a new image to `latest` neither guarantees all instances update simultaneously nor allows predictable rollbacks.

### Image control steps

1. Build from a reviewed Dockerfile.
2. Run functional tests and security scans on dependencies and base images.
3. Keep keys/tokens out of image layers and the Docker build context.
4. Push the image to an approved registry.
5. Record the digest, commit, build timestamp, and pipeline identity.
6. Deploy the exact version; monitor health and keep a rollback path.

ACR offers different SKUs and private networking features. If you need a **private endpoint** to ACR, select the corresponding SKU/features at deployment time; do not assume the Basic SKU supports all Premium capabilities.

## 6. Authentication when App Service pulls private images

A private image requires at least two things: **network reachability to the registry** and **pull permissions**. Creating ACR in the same resource group as the Web App **does not automatically grant permission** for the Web App to pull images.

### 6.1. Authentication options

| Mechanism | How it works | Assessment |
|---|---|---|
| **Managed identity** | Web App uses an Entra-managed identity to authenticate to ACR | Preferred when supported; avoids storing registry passwords |
| Service principal/credentials | App Service configured with registry credentials | Must be protected, rotated, and narrowly scoped |
| ACR admin account | Uses registry-issued username/password | Discouraged for production; broad permissions and manual key management |
| Public image | Registry allows unauthenticated pulls | Suitable only for approved public images; never for confidential artifacts |

The managed identity used to **pull images** is the Web App's workload identity—different from a developer's identity running `az acr build`—and does not automatically grant access to Key Vault or databases.

### 6.2. System-assigned and user-assigned identities

- **System-assigned:** tied to the Web App's lifecycle; convenient when each app has its own pull permissions.
- **User-assigned:** exists independently and can be attached to multiple appropriate workloads; lets you pre-stage permissions before creating the app, though sharing scope and lifecycle must be governed.

On registries using **Azure RBAC registry permissions**, the **AcrPull** role at the registry scope is commonly used for pulling. If the registry uses **ABAC repository permissions**, repository access requires the matching repository roles/conditions per service capability rather than assuming `AcrPull` always applies. Permissions must match the ACR permission mode and per-repository access requirements.

### 6.3. Encryption and secrets

Never hard-code `DOCKER_REGISTRY_SERVER_PASSWORD` or storage connection strings in a Dockerfile. If credentials must be used where managed identity is not yet applicable, manage secrets via an approved store (such as Key Vault), restrict visibility, enforce expirations, and rotate regularly. Consider **Key Vault references** for supported app settings, keeping in mind that the app's runtime identity and image-pull identity may require different roles/scopes.

## 7. End-to-end hands-on: build in ACR and deploy a Linux Web App

This section outlines an Azure CLI lab (Bash / Cloud Shell in Bash mode). **Do not execute these commands while authoring content.** Run them only inside an authorized test subscription; replace placeholders with unique account/app names and verify quotas and costs.

### 7.1. Prerequisites

- Logged into Azure CLI with permissions to create resource groups, ACR, Linux App Service Plans, and Web Apps in a test subscription.
- Permission to **assign Azure RBAC roles** on ACR so the Web App's managed identity can pull images; a standard Contributor role alone is often **not sufficient** for role assignments.
- Local Docker or support for `az acr build` via ACR Tasks.
- Current directory contains the `Dockerfile` and `server.js` from section 3.
- Valid network connectivity between ACR and the Web App; this initial lab assumes the public registry endpoint is not completely locked down.
- Willingness to pay for App Service Plan and ACR resources while they exist; an App Service Plan can continue incurring charges even when the Web App has zero traffic.

### 7.2. Select subscription and resource names

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-appservice-container-lab"
LOCATION="southeastasia"
ACR="<globallyuniquelabregistry>"
PLAN="asp-container-lab"
APP="<globally-unique-web-app-name>"
IMAGE="appservice-demo"
TAG="1.0.0"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name, tenantId:tenantId}" -o table
~~~

Values in `<...>` are **placeholders**. The ACR name must comply with Azure Container Registry naming rules (allowed characters only, globally unique); the Web App name must be globally unique within the App Service domain namespace. Check region availability, plan quotas, and feature prerequisites before continuing.

### 7.3. Create the resource group and test ACR

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --sku Basic \
  --admin-enabled false

LOGIN_SERVER=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query loginServer -o tsv)

echo "$LOGIN_SERVER"
~~~

`Basic` is for lab demonstration, not the default choice for production or ACR instances needing private endpoints or advanced features. Do not enable the admin account merely to simplify deployment. If your environment requires a private-only registry, design private build runners and private image pull paths from the start; this public lab does not substitute for that architecture.

### 7.4. Build the image in ACR

Inside the directory with the Dockerfile:

~~~bash
az acr build \
  --registry "$ACR" \
  --image "$IMAGE:$TAG" \
  .

az acr repository show-tags \
  --name "$ACR" \
  --repository "$IMAGE" \
  --output table
~~~

`az acr build` uploads the build context and uses ACR's supported build service, avoiding a local Docker daemon push in this workflow. Still watch out for `.dockerignore`, accidental secrets in the build context, and registry build permissions. In CI/CD, use a separate identity and approval gate for **push**, distinct from the Web App's **pull-only** identity.

Example image reference after building:

~~~text
<registry-name>.azurecr.io/appservice-demo:1.0.0
~~~

### 7.5. Create a Linux App Service Plan

~~~bash
az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux
~~~

`B1` demonstrates a basic plan only. For production, evaluate performance, instance counts, health checks, networking, scaling, deployment slots, availability, and SKU pricing. If you plan to practice **deployment slots**, upgrade to a tier that supports slots before creating one.

### 7.6. Create a Web App using the ACR image

~~~bash
az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP" \
  --deployment-container-image-name "$LOGIN_SERVER/$IMAGE:$TAG"
~~~

Some Azure CLI versions have slightly different parameter names or behaviors for container images; check `az webapp create --help` in your environment. **A transient image-pull error may occur right after creation** because the Web App does not yet have a managed identity and ACR pull permission; the next steps configure the required permissions. Do not work around this by blindly enabling ACR admin credentials.

### 7.7. Grant managed identity and ACR pull permission

~~~bash
# Enable system-assigned managed identity for the Web App.
PRINCIPAL_ID=$(az webapp identity assign \
  --resource-group "$RG" \
  --name "$APP" \
  --query principalId -o tsv)

# Retrieve the Azure resource ID of the ACR.
ACR_ID=$(az acr show \
  --resource-group "$RG" \
  --name "$ACR" \
  --query id -o tsv)

# Example for a registry using standard RBAC permissions mode.
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
~~~

If the registry uses **ABAC-enabled repository permissions**, do not treat this `AcrPull` snippet as sufficient: assign the exact repository roles and conditions matching the configured mode. Role assignments may take time to propagate; the caller must also hold role-assignment permissions at the registry scope.

### 7.8. Instruct App Service to use managed identity for image pulls

~~~bash
# Configure the Web App to use managed identity when authenticating to ACR.
# Supported Azure CLI syntax for site configuration;
# verify with: az webapp config set --help
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --generic-configurations '{"acrUseManagedIdentityCreds": true}'

# Explicitly set the custom container registry endpoint and image.
# Check the latest options via: az webapp config container set --help
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --container-image-name "$LOGIN_SERVER/$IMAGE:$TAG" \
  --container-registry-url "https://$LOGIN_SERVER"
~~~

If your Azure CLI version uses older parameter names (prefixed with Docker), check `--help` for the actual command rather than falling back to password auth just because a flag name differs. In **Deployment Center → Containers** or the equivalent config blade in the Azure Portal, you can also verify the registry, image, tag, and managed identity auth setting.

**Important:** never pick a random user-assigned identity that is not attached to the Web App. With a UAMI, configure the exact identity App Service uses for ACR pulls (typically tied to client ID), grant ACR permissions, and verify connectivity. The example above uses a system-assigned identity to minimize moving parts.

### 7.9. Declare the HTTP port and restart the app

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings "WEBSITES_PORT=8080" "PORT=8080"

az webapp restart \
  --resource-group "$RG" \
  --name "$APP"

HOST=$(az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query defaultHostName -o tsv)

echo "https://$HOST"
~~~

These two settings have **different jobs**: `WEBSITES_PORT` tells App Service which HTTP port the custom container exposes; `PORT` is read by **the sample app in this lesson** to pick its listening port. Do not assume `WEBSITES_PORT` automatically appears as an environment variable inside the container across all versions/features; setting `PORT` explicitly prevents relying on that assumption.

### 7.10. Verify from the user perspective

~~~bash
curl -i "https://$HOST/"
curl -i "https://$HOST/health"
~~~

Expected result: HTTP 200 and JSON from the sample app. If you encounter 503 or continuous container restarts, inspect image pull status, port, entrypoint, and logs; **do not conclude the App Service Plan lacks CPU** without evidence. If DNS/endpoints differ due to a custom domain, test against the configured hostname.

### 7.11. Inspect image configuration and managed identity

~~~bash
az webapp identity show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

az webapp config container show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

az role assignment list \
  --assignee "$PRINCIPAL_ID" \
  --scope "$ACR_ID" \
  --output table
~~~

If commands return configuration fields containing credentials/tokens in environments using other registry auth methods, **never paste raw output into public tickets**. For private ACRs, verify both network name resolution and pull permissions, not just the role list.

## 8. Ports, HTTPS, and container startup lifecycle

### 8.1. Public port and internal port are two different layers

From the user's perspective, Azure App Service exposes HTTP/HTTPS connectivity through its service frontend. A custom container connects via **one primary application HTTP port** per platform configuration; App Service is not a general forwarder for arbitrary Docker TCP/UDP ports.

~~~text
Client HTTPS :443
        |
        v
Azure App Service frontend (TLS termination per config)
        |
        v
Application in container :8080 (HTTP)
~~~

Therefore:

- `EXPOSE 8080` in a Dockerfile is **metadata**; it does not automatically tell App Service which port to route to.
- `WEBSITES_PORT=8080` configures the port the platform routes to in Linux custom containers.
- The app must listen on `0.0.0.0:8080`; `127.0.0.1` inside the container can prevent the frontend from reaching it.
- Misconfigured internal HTTPS redirects in the app can cause redirect loops after TLS termination; understand `X-Forwarded-Proto` and your framework's trusted proxy configuration.
- When using WebSockets, streaming, or long-running requests, review timeouts, keep-alives, sessions, and App Service limits instead of assuming every connection stays open indefinitely.

### 8.2. Startup and warm-up

App Service must pull the image, create the container, run the entrypoint, and wait for the app to become ready. Slow startup caused by huge images, database migrations, loading AI models, or flaky dependencies can cause the platform to mark the app as failing to start.

Design choices:

1. Shrink image size and strip dev dependencies/build tools unnecessary at runtime.
2. Move schema migrations or long setup tasks to an **independent deployment step**; do not let every instance race to run migrations.
3. Separate readiness from liveness. Listening on a port does not mean the app is ready for business traffic.
4. Configure startup/warm-up behavior and timeouts using supported App Service settings/features when needed; do not raise timeouts indefinitely to mask bugs.
5. Log clearly at startup and on failures without logging secrets.

When adjusting settings such as container startup timeout or warm-up paths, check current property names and limits for Linux custom containers and test them; there is no single optimal timeout for every app.

### 8.3. Environment variables, settings, and secrets

App Service app settings are exposed to the app as configuration/environment variables per supported mechanisms. For example:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings \
    "NODE_ENV=production" \
    "LOG_LEVEL=info" \
    "FEATURE_X_ENABLED=false"
~~~

Changing app settings can trigger an application restart/recycle; evaluate the impact on active sessions and deployment windows. Some settings configure the App Service platform rather than app parameters; name and document them clearly.

For **database passwords, API keys, and certificates**, prefer managed identity/Entra authentication when target services support it. If secrets are required, store them in Key Vault and access them through approved mechanisms, avoiding `Dockerfile ENV SECRET=...` and hard-coding in source/images. When connecting to SQL or Storage, distinguish the Web App's **control-plane permissions** from **data-plane permissions** on data resources.

## 9. Health Check, Always On, and scaling

### 9.1. Health Check

**App Service Health Check** sends requests to a configured path (such as `/health`) and uses the HTTP response to evaluate each instance. An endpoint should return **2xx** promptly when the app can serve traffic. Returning 401 due to required authentication, redirects, or timeouts can mark the instance unhealthy depending on service behavior; design a clear endpoint and limit returned data.

In the Azure Portal, open Web App → **Health check** (or the Monitoring section) → set path `/health`, configure supported options, and check status after saving. Across different plans/tiers and instance counts, verify how unhealthy instances are removed from rotation and replaced under App Service rules.

| Endpoint | Purpose | Example |
|---|---|---|
| `/health/live` | Is the process alive? | Returns 200 if the event loop/server is running |
| `/health/ready` | Can it handle new requests? | Returns 200 once essential resources are initialized |
| `/health/deep` | Deep dependency diagnostics | For authenticated monitoring; not necessarily for platform health checks |

The demo only returns 200 on `/health`; production needs real logic while avoiding letting a non-essential dependency evict all instances simultaneously. Never return stack traces, connection strings, or internal details from a publicly reachable endpoint.

### 9.2. Always On

**Always On** on supported tiers prevents the app from being idled out under service behavior. It **does not replace** Health Check, readiness, load testing, or an application SLA. For containers with slow startup, choose an appropriate plan/tier and configuration to maintain responsiveness after quiet periods.

### 9.3. Scale up and scale out

- **Scale up:** pick a worker SKU with higher CPU/RAM in the App Service Plan.
- **Scale out:** increase instance/worker counts on the plan or configure autoscale where supported.
- **Apps must handle multiple instances:** never keep sessions or critical records solely in RAM or local filesystem. Use external caches, databases, or Blob Storage.
- **Each instance pulls the image and starts independently:** oversized images and slow startups slow down scaling.
- **Plan scaling affects all apps on the plan:** budget total capacity, not just one Web App's usage.

For low-traffic workloads, adding instances just "for HA" should be evaluated alongside SLA/tier/zone support, readiness, and data dependencies. Multiple instances in one region do not replace a regional outage recovery strategy.

## 10. Deployment Center, version tags, CI/CD, and safe releases

### 10.1. Recommended release workflow

~~~mermaid
flowchart LR
    COMMIT[Reviewed commit] --> TEST[Unit/integration tests]
    TEST --> BUILD[Build image + scan]
    BUILD --> PUSH[Push immutable ACR tag]
    PUSH --> STAGE[Deploy staging]
    STAGE --> VERIFY[Smoke/health/security tests]
    VERIFY --> APPROVE[Approval]
    APPROVE --> PROD[Deploy or swap production]
    PROD --> OBS[Observe, roll back if needed]
~~~

Every release should record the commit, version, image digest, pipeline execution ID, environment, and approver. Do not auto-update production whenever `latest` changes if your organization requires testing and approval. Use automation (GitHub Actions, Azure Pipelines, or an approved CI/CD system) with **federated identity** instead of storing long-lived service principal secrets in repositories.

### 10.2. Releasing a new version

Suppose version `1.0.1` has been tested and built:

~~~bash
NEW_TAG="1.0.1"

az acr build \
  --registry "$ACR" \
  --image "$IMAGE:$NEW_TAG" \
  .

# Example updating the Web App image after review.
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --container-image-name "$LOGIN_SERVER/$IMAGE:$NEW_TAG" \
  --container-registry-url "https://$LOGIN_SERVER"
~~~

For critical production traffic, avoid updating production directly as in the demo command. Deploy to a **staging slot** on a supported tier, validate, and swap/cut over according to plan. If referencing images by digest, verify supported reference syntax and ensure the pipeline tracks digests per environment.

### 10.3. Deployment slots

Slots create parallel app environments within a Web App on supported tiers. They let you test a release before shifting production traffic, though they are not completely isolated across every resource: slots share the App Service Plan and may share dependencies unless separated explicitly.

A workflow:

1. Create a `staging` slot on a Web App in a supported plan.
2. Configure the new image version for staging, along with separate secrets/connections if needed.
3. Mark **slot-specific app settings** that stay bound to each environment; review database/storage connections before swapping.
4. Warm up staging, run smoke tests, and verify health and telemetry.
5. Approve and swap using built-in mechanics; verify production post-swap.
6. On regression, roll back/swap back or revert to a verified image digest after confirming data compatibility.

**Swapping does not automatically roll back schema/data migrations.** If a release makes backward-incompatible database schema changes, reverting to the old image can still fail. Use backward-compatible migrations (expand/contract) and separate backup/restore plans.

### 10.4. Continuous deployment from the registry

App Service supports registry/webhook integration for some image update workflows. When enabling continuous deployment, understand:

- Which events trigger a restart or new image pull.
- Registry webhook/permission requirements and restrictions when ACR network access is locked down.
- Whether approvals exist between build and production.
- How the running digest is tracked and how rollbacks work.

When strict approvals are required, prefer an explicit **push image → test → update Web App** pipeline instead of letting production follow a mutable tag automatically.

## 11. Networking: inbound, outbound, and private image pulls

When App Service runs containers, separate at least three network paths:

1. **Client → Web App**: HTTP/HTTPS ingress, domains, TLS, and access restrictions.
2. **Web App → data services/APIs**: outbound path to Azure SQL, Storage, Key Vault, or partner APIs.
3. **App Service platform → image registry**: path used to pull images on creation, restarts, and scale-out.

One path working **does not prove** the other two work. For instance, users may reach the webpage while the app cannot query the database; conversely, the Web App may hold ACR pull permissions yet fail to start if DNS/private endpoints are misconfigured.

### 11.1. Inbound: access restrictions and Private Endpoint

App Service provides a default public hostname as supported. Based on requirements:

- **Access restrictions** limit which sources can connect to the app over the corresponding ingress path.
- **Private Endpoint for Web App** brings private inbound access into a VNet per service capabilities; clients need proper DNS/routing and permissions.
- **Application Gateway / Azure Front Door with WAF** can protect HTTP/HTTPS traffic when L7 inspection and host/path routing are needed.
- **Authentication/Authorization** in App Service or in app code controls who may actually invoke features; Private Endpoints and IP allowlists do not replace application authorization.

If an app serves only internal staff over a private network, design private ingress from the outset rather than leaving it on the internet and trying to bolt on block rules later. When placing Front Door or a public gateway in front, lock down the **origin** so clients cannot bypass the protective edge where required.

### 11.2. Outbound: VNet Integration

**Regional VNet Integration** lets supported App Service apps make outbound connections into VNet resources. It **does not automatically make Web App inbound traffic private**; that is the role of a Private Endpoint or dedicated ingress design.

~~~mermaid
flowchart TB
    CLIENT[Internet / Internal Client] --> FRONT[App Service ingress]
    FRONT --> APP[Linux Web App custom container]
    APP -->|Regional VNet Integration| INTSUB[Delegated integration subnet]
    INTSUB --> SQL[Azure SQL Private Endpoint]
    INTSUB --> KV[Key Vault Private Endpoint]
    INTSUB --> STORAGE[Blob Storage Private Endpoint]
    INTSUB --> FW[Azure Firewall / NAT egress if applicable]
    APP -. Configured image pull path .-> ACR[ACR]
~~~

Plan subnets carefully:

- The **integration subnet** must meet App Service sizing and delegation requirements to supply enough IPs during scaling and worker upgrades.
- **Private Endpoints** for SQL/Storage/Key Vault typically live in separate appropriate subnets; do not dump them into the delegated integration subnet.
- **DNS** must resolve service names to private endpoints accurately from the App Service workload, not just from an admin workstation.
- **UDR/firewall/NAT** affects outbound paths according to routing and supported route-all settings; test actual traffic paths.
- When the App Service Plan scales out, VNet integration IP capacity must cover all instances plus temporary IPs needed during platform upgrades.

### 11.3. ACR private endpoint and image pulls over VNet

When ACR disables public network access or uses a private endpoint, App Service needs a **private network path** to pull images. This is a frequent cause of production startup failures even when builds and pushes succeed.

Design requirements:

1. ACR SKU and region/features supporting private endpoints; create a private endpoint for the registry.
2. Proper Private DNS for `<acr-name>.azurecr.io` and associated endpoints per ACR architecture, including data endpoints when required.
3. App Service outbound VNet integration with routing/DNS reaching the ACR private endpoint.
4. Enable **image pull over VNet**, typically via `WEBSITE_PULL_IMAGE_OVER_VNET=true` on supported Linux App Service configurations.
5. Web App managed identity holds pull permissions matching the active ACR permission mode.
6. Test image pulls during **restarts and scale-out**, not only initial deployment.

If the registry is private-only, running `az acr build` from an environment without registry network access can also be affected; provision authorized build runners and verify ACR network rules. A **Private Endpoint does not grant pull permissions**, and **AcrPull does not establish network routing**. Both layers must be verified independently.

### 11.4. Internet egress and public outbound IPs

When a Web App calls partner APIs, identify the source IPs seen by partners—especially if partners enforce allowlists. App Service assigns outbound addresses per configuration/tier that can change on certain plan/scaling operations; if business requirements demand stable source IPs, consider **VNet Integration combined with NAT Gateway** or **Azure Firewall** under a supported egress design.

Do not treat `az webapp show` outbound IP lists alone as an eternal guarantee across all operations. With forced tunneling, UDRs, or route-all enabled, paths differ from defaults; test egress reachability and live connection logs after changes.

### 11.5. Network test matrix

| Flow | Target | Controls |
|---|---|---|
| User → Web App | HTTPS hostname or private ingress | TLS, custom domain, access restrictions, auth/WAF |
| Web App → Azure SQL | Private Endpoint or approved network path | VNet Integration, DNS, port, Entra/database permissions |
| Web App → Blob Storage | Blob private endpoint | DNS, routing, identity, and Storage Blob Data role |
| Web App → Key Vault | Private vault endpoint | Network policy, Key Vault data-plane RBAC, managed identity |
| App Service → ACR | Registry + data endpoints | Pull identity, role, image tag, and DNS/network |
| Web App → Partner API | Internet/public endpoint | NAT/Firewall, DNS, TLS, IP allowlist, and retries |

## 12. Application state, filesystem, and persistent data

Containers suit **stateless** apps, yet some legacy apps still write uploads, sessions, caches, or temporary images to local disk. In App Service, containers can be replaced during deploys, restarts, scaling, or platform maintenance. Never assume data in an image's writable layer persists forever or is shared across all instances.

### 12.1. Data classification

| Data type | Appropriate location | Why |
|---|---|---|
| Source/runtime/dependencies | Built image | Reproducible releases |
| Secrets | Key Vault / approved secret store | Avoid exposure in images and config files |
| User-uploaded files | Azure Blob Storage or supported file service | Durable storage, permissions, backups/lifecycle |
| Multi-instance sessions | Designed distributed cache/DB | Survives instance routing changes |
| Transactional data | Azure SQL, Cosmos DB, or appropriate DB | Concurrency, queries, transactions, and backups |
| Application logs | stdout/stderr, Azure Monitor/App Insights, or log pipeline | Searchable across restarts and scaling |
| Temporary files | Temp directories within supported limits | Self-cleaning; never treated as permanent storage |

### 12.2. Persistent storage for Linux custom containers

App Service offers capabilities to mount/persist storage such as `/home` in Linux custom container setups, commonly involving `WEBSITES_ENABLE_APP_SERVICE_STORAGE`. **Default behavior and support scope must be verified per app type/feature**; do not assume writing files to `/home` guarantees durability and synchronization for every business need.

Even with persistent storage enabled, evaluate:

- How data is shared across instances.
- Storage quotas and I/O performance.
- File locking, consistency, and concurrent writers.
- Backup/restore and file lifecycle.
- Data separation across deployment slots or environments.

For images, documents, backups, or customer files, prefer **Azure Blob Storage**/dedicated file services and store metadata in a database if needed. Never use a writable container layer as a "free database."

### 12.3. Application configuration

Keep **images environment-agnostic**: the same artifact should run in dev, test, and prod with different app settings, secrets, and networks. Never build three separate images differing only by a connection string baked into the Dockerfile; that multiplies artifacts and secret exposure risk.

An app setting update can recycle the app, so manage changes via IaC/pipeline reviews and separate **slot-specific** settings to prevent data leakage between staging and production.

## 13. Container security from build to runtime

A container image is part of the software supply chain. Wrapping an app in Docker **does not eliminate CVEs** or stop an attacker from abusing the app's permissions to read data.

### 13.1. Before pushing to the registry

- Use trusted base images and **pin digests** for reproducible builds.
- Regularly patch runtime/OS packages; minimize unnecessary packages.
- Scan source dependencies and container images with approved scanners.
- Where required, generate SBOMs, store provenance/signatures, and enforce artifact verification.
- Use multi-stage builds to exclude compilers/build tools from runtime images when appropriate.
- Exclude `.env`, private keys, credentials, and backup files from the Docker build context using `.dockerignore`.
- Avoid running the app as root unless genuinely required; limit writable paths.
- Keep image push permissions on a dedicated CI identity, never using production's pull-only identity to push.

Example `.dockerignore` for a Node.js repo:

~~~text
.git
node_modules
.env
.env.*
*.pem
*.key
secrets/
coverage/
tmp/
~~~

`.dockerignore` is a risk-reduction layer, **not a replacement** for secret scanners or Dockerfile reviews. If a secret was previously committed/pushed to a registry, deleting it from the current Dockerfile does not revoke the already-published secret; rotate it and audit existing artifacts.

### 13.2. While running on App Service

- Web App uses a **managed identity** to call Entra-supported Azure services; grant least-privilege scoped permissions.
- Restrict public ingress and enforce HTTPS/TLS, auth, and WAF as needed.
- Never write tokens, SAS strings, account keys, or sensitive customer data to logs.
- Enforce quotas/concurrency, rate limits, and timeouts at the app or gateway layer.
- Apply Azure Policy, RBAC, and auditing around image/config changes.
- Configure diagnostics, Health Check, and alerts to catch runtime failures.
- Do not switch to `USER root` in a Dockerfile to paper over file permission errors; fix ownership and mounts instead of opening full privileges.

### 13.3. Image refreshes and CVEs

Respond to a new CVE in `node:22-alpine` or an app library by:

1. Identifying affected image digests and package versions.
2. Updating the base image/dependency to a supported patched release.
3. Rebuilding the image and running tests/security scans.
4. Deploying to staging/canary and validating before production.
5. Verifying the live runtime runs the new digest, not just the tag.
6. Retaining audit evidence and handling old images/exposed secrets per retention policy.

**App Service does not automatically rebuild your custom image** when a vendor ships a new base image. Updating a Web App runtime setting is not the same as shipping a patched image.

## 14. Container logging and observability

When failures occur, clearly identify whether the issue is in **image pull**, **startup**, **routing**, **application code**, or **dependencies**. Each has distinct log sources.

### 14.1. Telemetry sources

| Source | Key data |
|---|---|
| Container startup/deployment logs | Image pulls, registry authentication, entrypoint, and container startup |
| Application stdout/stderr | Runtime errors, request handling, sanitized stack traces |
| App Service metrics | Request counts, response times, HTTP 4xx/5xx, CPU/memory, instance count |
| Health Check | Instance readiness or unhealthy status on configured path |
| Application Insights | Request traces, dependency failures, distributed tracing when instrumented |
| Azure Activity Log | Who modified container images, app settings, identities, networking, or plans |
| ACR diagnostics | Registry activity according to enabled data sources/features |
| Azure Monitor/Log Analytics | Aggregation and alerting once appropriate log streams are configured |

Do not assume creating a workspace automatically routes all logs into it. Enable application instrumentation, log settings, diagnostic settings, or exporters as needed, and evaluate ingestion and retention costs.

### 14.2. Viewing logs in practice with Azure CLI

~~~bash
# Enable container logging to filesystem in the lab when supported by CLI/runtime.
az webapp log config \
  --resource-group "$RG" \
  --name "$APP" \
  --docker-container-logging filesystem

# Stream Web App logs to observe startup and requests.
az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

If no logs appear, verify that the right logging option is enabled, the app is running, log streaming connects cleanly, and the SKU/container model supports it. `log tail` suits labs and short investigations; production needs durable log storage, access control, and retention rather than watching an open terminal window.

### 14.3. SLO-aligned alerts

Key alerts should have clear owners and runbooks:

1. Elevated HTTP 5xx rates or p95 latency after a release.
2. Frequent container restarts or startup failures across instances.
3. Prolonged Health Check failures.
4. High CPU/RAM/connection utilization ahead of peak hours.
5. Registry pull failures during scaling or restarts.
6. Timeouts or 403 errors calling SQL/Storage/Key Vault.
7. Out-of-band changes to image tag/digest or App Service settings outside pipelines.
8. Egress IP/network policy changes causing partner APIs to reject connections.

For example, if a site returns 503 after deployment, adding instances will not help if **no instance can pull the image**. Triage via logs first before picking a fix.

## 15. Troubleshooting: container not behaving as expected

### 15.1. Ordered diagnostic workflow

When a URL fails to respond, avoid changing ACR, Dockerfile, ports, NSGs, and database settings all at once—you will lose track of what fixed it.

1. **Does the Web App exist on the right plan/OS?** Check App Service Plan state, Web App state, Linux OS, and SKU.
2. **Does the referenced image exist?** Verify exact login server, repository, tag/digest, and ACR build results.
3. **Are ACR pull conditions met?** Check managed identity, role assignments, permission mode, registry networking, and DNS.
4. **Did the container start?** Read startup logs; check CPU architecture, entrypoint, dependencies, and runtime exceptions.
5. **Is the app listening on the right port?** Cross-check `WEBSITES_PORT`, `PORT`, `EXPOSE`, and bind address.
6. **Are internal responses valid?** Probe `/` and `/health`, separating platform 503s from application 500s.
7. **Do dependencies work?** Check VNet Integration, Key Vault, SQL, Blob, DNS, and data-plane RBAC.
8. **Did the issue appear only after scaling or deploy?** Check every instance, tag/digest, startup duration, shared state, and slot settings.
9. **Were any recent config changes made?** Check the Activity Log and deployment pipeline.
10. **Can we roll back?** On faulty releases, revert to a verified image digest or swap back the deployment slot per runbook instead of making untracked live edits in production.

### 15.2. Symptom and cause matrix

| Symptom | Possible cause | Verification / fix |
|---|---|---|
| Logs show `unauthorized` or `denied` on pull | Web App lacks pull permission; wrong identity or ACR uses ABAC | Check principal ID, permission mode, role/repository scope, allow RBAC propagation |
| `manifest unknown` / image not found | Wrong repository/tag or image not pushed | List tags/digests in ACR; verify image reference |
| `no matching manifest for platform` | Image built for wrong CPU/OS architecture | Inspect manifest and build compatible `linux/amd64` image |
| Container starts then repeatedly exits | Bad `CMD`/`ENTRYPOINT`, code crash, missing library | Read container logs, check exit code; run locally |
| Container runs but App Service returns 503 | Wrong port, bound localhost, startup incomplete | Check `WEBSITES_PORT`, `PORT`, `0.0.0.0` listener, startup logs |
| `/` works, `/health` returns 401/404 | Wrong path or endpoint requires login | Fix Health Check path/readiness logic; don't leak sensitive data |
| Works locally but fails in Azure | Env/arch mismatch, missing secret, outbound DNS, or PaaS access | Compare app settings, image arch, managed identity, and VNet |
| SQL/Storage/Key Vault returns 403 | Wrong RBAC, credential, firewall, or service policy | Separate data-plane permissions from network policy; check tokens/endpoints |
| ACR pull fails only after disabling public access | Missing VNet-based image pull, private DNS, or routing | Check `WEBSITE_PULL_IMAGE_OVER_VNET`, VNet integration, registry data endpoints |
| Only newly scaled-out instances fail | New instance fails image pull or hits startup/resource limits | Inspect per-instance logs, pull auth, DNS, startup, and subnet IPs |
| Staging change breaks production | Sticky slot settings missing or shared database/secrets | Review swap config, database/Key Vault, and connection references |
| Uploaded files vanish after restart | Written to ephemeral writable layer | Move data to Blob Storage/DB or appropriate durable storage |
| New image does not appear after pushing `latest` | Cached tag/unchanged reference/no restart or inactive webhook | Verify running digest and use explicit pipeline deployments |
| Partner API rejects source IP | Outbound IP changed after plan/network change | Check egress path, NAT/Firewall, allowlist, and DNS |

**Never copy credentials into logs** while debugging image pull errors. Mask tokens and registry passwords in URLs or responses before sharing with support teams.

### 15.3. Useful configuration inspection commands

~~~bash
# Web App and associated plan.
az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,host:defaultHostName,plan:serverFarmId}" \
  -o json

# Settings list; may contain sensitive values.
# View only in authorized terminals; never paste raw output publicly.
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

# Image and registry configuration.
az webapp config container show \
  --resource-group "$RG" \
  --name "$APP" \
  --output json

# Image versions present in the registry.
az acr repository show-tags \
  --name "$ACR" \
  --repository "$IMAGE" \
  -o table
~~~

When escalating for technical support, capture timestamps, request/correlation IDs, Web App resource ID, image digest, impact scope, and recent changes—without attaching secrets or tokens.

## 16. Choosing the right architecture and controlling costs

### 16.1. Is an App Service custom container truly necessary?

| Question | If the answer is "Yes" |
|---|---|
| Does the app need a custom runtime or native dependencies hard to run on built-in stacks? | Containers offer clear advantages |
| Is it solely a web/API app without host-level privileged operations? | App Service custom container can fit well |
| Are there background workers, queue consumers, or multiple tightly coupled containers? | Evaluate Container Apps, Functions, AKS, or another compute service |
| Do you need Kubernetes scheduling, CRDs, operators, or complex service meshes? | AKS may be a better fit than App Service |
| Do you want simpler operations for a monolithic app? | App Service is generally easier to operate than self-managed VMs/Kubernetes |
| Does the app rely on local mutable state that cannot be separated immediately? | Refactor storage/sessions or evaluate suitable platforms before scaling out |

Do not choose containers simply because a Dockerfile already exists. A built-in runtime app can be simpler, require fewer OS patches, and cut build/scan overhead. On the other hand, containers boost reproducibility, environment portability, and dependency control when genuinely needed.

### 16.2. Cost drivers to estimate

| Item | Cost impact |
|---|---|
| **App Service Plan** | Worker/instance charges by SKU and duration; idle apps do not make paid plans free |
| **ACR** | Registry SKU, image storage, network, and operations per pricing tier |
| **Scale out** | Extra workers raise compute cost and may require more VNet integration IPs |
| **Application Insights / Log Analytics** | Ingestion, retention, tracing, alerts, and log volume |
| **Private networking** | Private Endpoints, NAT Gateway, Azure Firewall, data processing/egress per topology |
| **Blob Storage / Database** | Data capacity, operations, backups, redundancy, and access |
| **CI/CD/build** | Build runners, artifact retention, image scans, and security services |
| **Traffic** | Outbound data transfer, cross-region traffic, and delivery services if used |

Charges and billing terms vary by region, SKU, and date. Use Azure Cost Management and live Azure pricing for your actual subscription rather than hard-coding prices in documentation.

### 16.3. Practical optimizations

- Reduce image size for faster pulls and lower build/registry storage time.
- Purge unused tags/digests under retention policies without deleting rollback candidates.
- Share App Service Plans when workloads are compatible and teams accept shared capacity; isolate plans when isolation is needed.
- Right-size SKUs and configure scaling rules using real load metrics rather than average CPU alone.
- Limit verbose debug logging and sensitive payloads; set sensible sampling and retention.
- Deploy Private Endpoints/NAT/Firewalls only where security and traffic justify the cost.
- Apply `owner`, `application`, `environment`, and `costCenter` tags; configure budget alerts and review trends.

**A budget alert is not a hard spending cap.** Stopping or deleting a Web App while keeping the App Service Plan, ACR, or NAT Gateway still incurs charges on remaining resources. Confirm costs through billing data, not simply because a webpage stopped responding.

## 17. Architectural scenario: deploying an orders API

**Hypothetical scenario:** A company has a Java orders API previously running on a VM; engineering wants to migrate it to an App Service custom container. The API calls Azure SQL and Azure Blob Storage, reads secrets from Key Vault, and calls a partner system. The data is production, requiring zero downtime during peak hours.

### 17.1. Suggested architecture

~~~mermaid
flowchart TB
    DEV[Git repository] --> CI[CI build, tests, image scan]
    CI --> ACR[ACR private images]
    APP[Linux App Service custom container] --> SQL[Azure SQL Private Endpoint]
    APP --> BLOB[Blob Storage Private Endpoint]
    APP --> KV[Key Vault Private Endpoint]
    APP --> NAT[NAT Gateway / approved egress]
    NAT --> PARTNER[Partner API]
    USER[Users] --> EDGE[HTTPS edge / WAF if needed]
    EDGE --> APP
    APP -. Diagnostics .-> MON[Azure Monitor / App Insights]
    ACR -. Image pull with managed identity .-> APP
    APP --- VNET[Regional VNet Integration]
    VNET --- SQL
    VNET --- BLOB
    VNET --- KV
~~~

The diagram shows logical connections; concrete declarations of the App Service Plan, Web App, frontend, private endpoints, and subnets must follow your regional landing zone architecture. DNS and routing between VNet Integration and private endpoints must be verified; a line in a diagram does not automatically configure firewall rules or RBAC.

### 17.2. Approved rollout steps

1. **Separate subscriptions/resource groups** by platform and workload model; define owners, environments, and Azure RBAC roles.
2. **Dockerize and test** the Java API using multi-stage builds, non-root image, `/health/ready` readiness probe, and version metadata.
3. **Build/scan/push** the image to ACR and record the digest per commit.
4. **Assign permissions:** CI identity gets scoped push only; Web App managed identity gets image pull and least-privilege data access.
5. **Provision** Linux App Service Plan/slot, Web App, app settings, and container HTTP port.
6. **Networking:** regional VNet integration, private endpoints + DNS for SQL/Storage/Key Vault, ACR pull path, and partner-facing outbound IP.
7. **Staging:** deploy the image; run unit/integration, health, TLS, auth, data-plane, and load tests.
8. **Production rollout:** approved swap/cutover, monitor 5xx/latency, keep rollback image ready.
9. **Operations:** monitor telemetry, patch base images, rotate secrets, and govern costs.

### 17.3. Test matrix

| Test | Expected outcome | If it fails, investigate |
|---|---|---|
| Image pull from private ACR | Worker pulls the exact digest | Entra identity, AcrPull/ABAC, registry DNS/network |
| Health/ready after startup | Returns 2xx once genuinely ready | Port, entrypoint, app startup, dependencies |
| Client HTTPS access | Valid cert/TLS, proper auth | Domain, ingress policy, application auth |
| API access to SQL | Right DB and identity permissions | VNet integration, private DNS, SQL auth |
| API reading Blob Storage | Reads intended container only | Storage data RBAC, network, and object path |
| API reading Key Vault | Necessary secrets only | Managed identity, Key Vault RBAC, network |
| API calling partner | Source IP and TLS match allowlist | NAT/Firewall, DNS, routing, retry logic |
| Scale from 1 to 2 instances | Both start, pass health, and serve | Image pull, subnet IPs, shared state, plan capacity |
| Swap and rollback | Safe version transition with zero data loss | Slot settings, migrations, digests, health metrics |

**Design questions:** What happens if ACR becomes unreachable when an instance needs to restart or scale out? If a database migration alters the schema, can the old image roll back? If the NAT Gateway changes public IPs, will the partner reject API requests? Answer these before go-live, not during an incident.

## 18. Self-guided implementation and evaluation lab

**Prompt:** Build a simple HTTP API with `/` and `/health`, package it as a Linux container, push it to ACR, and deploy it to Azure App Service. The app must use a private registry without storing registry passwords in the Dockerfile. Then prepare a plan to connect Azure SQL via a private endpoint and build a safe deployment pipeline.

Complete these tasks:

1. Draw a diagram of source → build → ACR → App Service → client, labeling the image-pull path vs. HTTP request path.
2. Write a `Dockerfile` using a maintained base image, running non-root, listening on port 8080. Explain the difference between `EXPOSE` and an actual listener.
3. Build and test locally with Docker; prove `/` and `/health` return HTTP 200.
4. Create an ACR/private repository and build a specifically versioned tag; read back the tag/digest.
5. Create a Linux App Service Plan and Web App in a lab subscription configured with the ACR image.
6. Assign a managed identity and appropriate pull permissions; explain what changes if the registry uses ABAC repository permissions.
7. Set `WEBSITES_PORT=8080` and `PORT=8080`; explain the symptoms when either one is wrong.
8. Configure log streaming/Health Check; record startup messages and endpoint states.
9. Diagram the **outbound** path to Azure SQL via VNet Integration/Private Endpoint/DNS. Explain why that is not an inbound Private Endpoint for the Web App.
10. Assuming ACR disables public access, list the additions needed for private registry DNS, image pull over VNet, and permissions.
11. Describe a pipeline releasing `1.0.1` with scanning, staging validation, approval, production rollout, and digest-based rollback.
12. List three ways secrets can leak during Docker builds/logs/app settings and propose mitigations.
13. Estimate cost groups across plan/ACR/logging/networking, apply tags, and set a budget alert.
14. Write a runbook for "deployment succeeded, yet the Web App returns 503."
15. Conclude the lab by identifying **the exact resources permitted for deletion**, without impacting the subscription or shared resources.

### Expected outcomes rubric

| Component | Evidence required |
|---|---|
| Source + Dockerfile | Clean build, matching Linux architecture, non-root execution |
| Local container | Listening on 0.0.0.0:8080, `/health` returns 200 |
| ACR | Versioned image tag/digest and least-privilege pull identity |
| Web App | Linux plan, right image, right `WEBSITES_PORT` |
| HTTP edge | Successful client HTTPS access |
| Data | Clear distinction between private endpoint networking, DNS, and data-plane RBAC |
| Deployment | Versioned releases, staging verification, rollback method |
| Observability | Startup logs, health checks, error metrics, and owned alerts |
| FinOps | Lab resources inventoried; no forgotten billable plan/ACR/network resources |

The lab is complete when you can independently diagnose **an image-pull error**, **a port error**, and **a SQL connectivity error** using separate evidence instead of changing every setting at once.

## 19. Lab cleanup and mistakes to avoid

Before deleting anything:

1. Confirm your subscription with `az account show` and verify the resource group is a **lab you own**.
2. List the Web App, App Service Plan, ACR, public/private endpoints, log workspaces, and any linked resources.
3. Verify the plan does not host another team's shared Web App.
4. Verify ACR does not hold images used by other environments or pipelines.
5. Follow retention policies for logs, images, and evidence.
6. Only when certain the RG holds **exclusively test resources** should you delete the RG per approved procedures.

~~~bash
az account show --query "{id:id,name:name}" -o table
az resource list --resource-group "$RG" -o table

# WARNING: deleting a resource group destroys every resource inside it.
# Only after confirming the RG is strictly for this lab:
# az group delete --name "$RG" --yes
~~~

Common mistakes:

| Mistake | Consequence | How to avoid |
|---|---|---|
| Push image but forget pull identity | App Service cannot start the private image | Assign role and verify ACR permission mode |
| Set only `EXPOSE 8080` | Frontend doesn't know the port; app may fail to listen | Configure `WEBSITES_PORT`, `PORT`, and bind `0.0.0.0` |
| Rely on mutable `latest` tag | Unclear which digest is running; hard to roll back | Use immutable tags/digests and deployment history |
| Bake secrets into Dockerfile/`.env` in image | Secrets leak via registry/layers/history | Use managed identity, Key Vault, `.dockerignore`, and scanners |
| Enable VNet Integration and assume public ingress closed | Web App may still expose a public endpoint | Use Private Endpoint/access restrictions and auth |
| Create ACR private endpoint without VNet pull/DNS | Builds or startups fail when public registry access is off | Verify the full network pull path |
| Write customer uploads to local container disk | Data loss on restart/scaling | Use Blob Storage/DB or appropriate durable storage |
| Treat Health Check as complete functional testing | Deployments can still fail business logic or other dependencies | Run synthetic checks and integration tests |
| Swap staging/production sharing an incompatible DB | Rolling back the image doesn't fix data/schema | Use compatible migrations and backups |
| Delete Web App but leave plan/ACR/NAT running | Ongoing charges continue | Inventory all related resources |

## 20. Key takeaways

Deploying containers to Azure App Service is a chain of tasks with clear boundaries:

1. **Build the right image:** Dockerfile with matching runtime, entrypoint, port, security, and CPU architecture.
2. **Store trusted artifacts:** ACR stores versioned images by tag/digest; build, test, and scan before releasing.
3. **Configure the platform:** Linux App Service Plan and Web App referencing the right image, with `WEBSITES_PORT` and proper app settings.
4. **Authenticate image pulls:** managed identity with matching registry/repository permissions; private ACR also requires private networking and DNS.
5. **Secure and connect the app:** inbound HTTPS/auth, outbound VNet Integration, private endpoints/data-plane RBAC, and durable state outside writable container layers.
6. **Operate releases:** health checks, metrics/logging, scaling, staging/slots, rollbacks, and base image updates must all be verified.
7. **Control costs:** choose suitable SKUs/instances and manage ACR/image retention, logs, and networking.

Most importantly: **"container image built and pushed successfully" does not mean "web app ready to serve."** A deployment is only operationally complete once registry pulls, startup, routing, security, dependencies, monitoring, and recovery have all been tested in the real Azure architecture.
