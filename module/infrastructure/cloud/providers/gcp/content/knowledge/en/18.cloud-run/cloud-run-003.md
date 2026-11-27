# Deploying from Source Code and from Container Images on Cloud Run

> **Chapter:** Cloud Run  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability and cost.

Cloud Run lets you deploy an HTTP application into a container execution environment managed by Google Cloud, without having to operate virtual machines or Kubernetes nodes yourself. There are two common approaches: **deploying a source code directory directly** using **gcloud run deploy --source**, or **deploying an existing container image** using **gcloud run deploy --image**. Both create a **Cloud Run service/revision**, but they differ in build responsibilities, artifact identification, and CI/CD integration.

This lesson uses the same small Python Flask application to practice both deployment paths; the same mindset applies to Java (Maven/Gradle, Spring Boot), Node.js, and other supported runtimes. The examples are scoped to an authorized lab project and do not provision real infrastructure while merely reading the documentation.

## Learning Objectives

After this lesson, learners can:

1. Explain the **source → Cloud Build/buildpacks or Dockerfile → Artifact Registry → Cloud Run** flow and the **image → Cloud Run** flow.
2. Prepare the APIs, project, region, identities, and IAM permissions required for each path.
3. Write an application that satisfies the **container runtime contract**, listening on **0.0.0.0** and port **PORT**.
4. Deploy from source and from an image, and inspect revisions, URLs, logs, IAM, and traffic.
5. Choose a deployment method based on build control, reproducibility, software supply chain, and CI/CD requirements.
6. Detect build, image pull, port, health, and 401/403 errors and investigate them with gcloud/Cloud Logging.
7. Estimate cost drivers, set guardrails, and safely clean up lab resources.

## 1. Concepts and Architecture

A Cloud Run **service** is an endpoint capable of serving HTTP/HTTPS/gRPC as configured. Every deployment of a new image or change to revision configuration creates an **immutable revision**; traffic can be split across existing revisions. Cloud Run automatically manages the number of container instances based on traffic and autoscaling settings.

~~~mermaid
flowchart TB
    SRC["Source code: main.py + requirements.txt"] --> BUILD["Cloud Build\nBuildpacks or Dockerfile"]
    BUILD --> AR["Artifact Registry\nContainer image"]
    CUSTOM["CI / Docker build\nVerified image"] --> AR
    AR --> RUN["Cloud Run service\nImmutable revisions"]
    RUN --> ROUTE["Traffic routing\n100% or split"]
    ROUTE --> USER["HTTP client"]
~~~

### 1.1. Two Deployment Approaches

| Criterion | **Deploy from source** | **Deploy from image** |
|---|---|---|
| Command | **gcloud run deploy SERVICE --source .** | **gcloud run deploy SERVICE --image IMAGE_URL** |
| Input | Source directory | Image reference from a registry |
| Who builds? | Cloud Run orchestrates **Cloud Build** (default) | CI/CD, Docker, or Cloud Build built beforehand |
| How the image is created | Buildpacks if no Dockerfile; Dockerfile if present | Following a Dockerfile/build pipeline controlled by the team |
| Artifact Registry | Used to store the built image; may auto-create a source repository | Image must exist and be accessible in a supported registry |
| Customization level | Fast, fewer steps, but limited convenience build configuration | Full control over testing, caching, provenance, SBOM, multi-environment |
| Best suited for | Prototypes, dev, simple apps | Production CI/CD, artifact promotion, auditable releases |

**Key point:** source deploy **still creates an image**; it does not mean Cloud Run runs source files directly without a container environment. This document covers the standard **deploy from source with build** mode; the **prebuilt source without Cloud Build** option is currently a separate Preview feature and should not be confused with the default flow.

### 1.2. When the Source Directory Has a Dockerfile

- **With a Dockerfile:** source deploy uses the **Dockerfile** in the source directory to build.
- **Without a Dockerfile:** buildpacks detect the language, resolve dependencies, and build a container image according to supported capabilities.
- Therefore, adding a Dockerfile can **change how the build works** even though the `deploy --source` command stays the same.
- Source deploy typically uses the **cloud-run-source-deploy** repository in the region if that repository does not already exist; Cloud Run may prompt/auto-create it depending on permissions and configuration.

Artifact Registry is where images are stored, while Cloud Run imports the image at deploy time and retains the served version per its revision mechanism. The fact that a service is already running does not prove that old repositories/images can be deleted without affecting **subsequent deployments, rollbacks outside Cloud Run, or audits**.

### 1.3. Service, Revision, Instance, and URL

| Concept | Meaning |
|---|---|
| **Service** | Name and overall configuration, stable URL for clients |
| **Revision** | Immutable snapshot of the container and revision configuration |
| **Instance** | Container instance serving requests; can be created/destroyed during autoscaling |
| **Traffic** | Percentage of requests routed to revisions |
| **Service identity** | Service account used by code inside the container when calling Google APIs |
| **Deployer** | User/service account performing the deployment; not necessarily the runtime identity |
| **Build identity** | Service account used to build source/upload images; separate permissions from runtime |

Do not rely on an instance's local filesystem to store durable business data: instances can be replaced or scaled to zero. Use Cloud SQL, Cloud Storage, Firestore, or an appropriate service, and design retries/idempotency where needed.

## 2. Container Runtime Contract: Conditions for Cloud Run to Run

A service application must **listen for HTTP requests on 0.0.0.0 and the port provided via the PORT variable** (typically 8080 by default). Listening on **127.0.0.1** inside the container can prevent Cloud Run from connecting.

- The ingress container must start and listen on the corresponding port within the allowed startup window.
- Cloud Run terminates TLS at the platform layer; application code normally receives plain HTTP inside the container.
- Responses must complete within the configured request timeout.
- For a Cloud Run **service**, an HTTP listener is required; a Cloud Run **job** processes a task to completion and does not need an HTTP listener.
- Containers can scale to multiple instances; in-memory data/local caches and socket connections are not shared by default.
- PORT, CPU, memory, concurrency, timeout, and health probes must match the real application behavior.

### 2.1. A Single Lab Application for Both Paths

Create a learning project directory **cloud-run-hello/** in your own practice environment (not inside the lesson repository currently maintained by workers). Initially it contains two files, **without a Dockerfile yet**.

**main.py**

~~~python
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def hello():
    return jsonify(
        message="Hello from Cloud Run",
        release=os.getenv("RELEASE", "dev"),
        revision=os.getenv("K_REVISION", "local"),
    )

@app.get("/healthz")
def health():
    return "ok", 200

if __name__ == "__main__":
    # Only use the development server when running python main.py.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
~~~

**requirements.txt**

~~~text
Flask==3.1.2
gunicorn==23.0.0
~~~

Local commands (assuming Python 3, a virtual environment, and dependencies are properly installed):

~~~bash
python -m pip install -r requirements.txt
PORT=8080 RELEASE=local python main.py
# Another terminal: curl -fsS http://127.0.0.1:8080/healthz
~~~

The Flask development server is only for local testing. When deploying Python source, buildpacks can use **Gunicorn** as the production HTTP server; if you need to customize the start command, you can use a **Procfile** or buildpack configuration rather than enabling `debug=True` in production.

**For Java:** Spring Boot can run via buildpacks/Dockerfile once Maven/Gradle and the appropriate packaging plugin are configured; set the server port from the Cloud Run environment variable (for example configuring **server.port** to read PORT), accurate health endpoints, and appropriate JVM memory. Do not copy Flask syntax verbatim into Java.

## 3. Preflight: Project, APIs, IAM, Region

This step must be performed **before any deploy command**, especially when an operator works across multiple projects.

### 3.1. Read-Only: Verify Context

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
SRC_SERVICE="hello-src-lab"
IMG_SERVICE="hello-img-lab"
REPOSITORY="cloud-run-images-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# APIs currently enabled in the project.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:(run.googleapis.com OR cloudbuild.googleapis.com OR artifactregistry.googleapis.com)"

# Existing Cloud Run services in the region.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
~~~

The project must have **billing** and the appropriate APIs enabled: **Cloud Run Admin API**, **Cloud Build API** for source/Cloud Build pipelines, and **Artifact Registry API** when working with repositories/images. Enabling APIs modifies the project and requires **serviceusage.services.enable** permission; do not enable them ad hoc in production just to test.

### 3.2. Permissions by Role

| Principal | Typical permissions | Why |
|---|---|---|
| Source deployer | **roles/run.sourceDeveloper**, **roles/serviceusage.serviceUsageConsumer**, **roles/iam.serviceAccountUser** on the service identity | Allowed to build/deploy from source |
| Cloud Build service account | **roles/run.builder** on the project per source deploy docs; additional roles per specific pipeline | Build and store images |
| Image deployer | **roles/run.developer**, **roles/iam.serviceAccountUser**, and **roles/artifactregistry.reader** on the image repo | Deploy an existing image |
| CI build pushing images | Artifact Registry **Writer** on the repository, plus needed Cloud Build permissions | Push images, without needing Cloud Run Admin |
| Cloud Run service agent | Read access to images in another project when cross-project | Import images during deployment |
| Runtime service identity | Only the GCP API roles the app actually needs | Do not use Admin just to run an HTTP hello world |
| Client calling a private service | **roles/run.invoker** or equivalent role and a valid ID token | Call an HTTP endpoint with IAM authentication enabled |

Actual roles may depend on the organization, the type of service account used for builds, and security policies. **Build identity is not runtime identity.** If the image resides in another project, you typically need to grant Reader to the **Cloud Run service agent of the service's project** and the deployer on the source repository; do not grant it only to the runtime service account and assume the pull will succeed.

### 3.3. Enabling APIs — Conditional Change

~~~bash
# MODIFIES PROJECT — only for authorized users in an approved lab.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

For source deployments, administrators must verify the **actual Cloud Build service account** and its **Cloud Run Builder** role. Never grant Owner to resolve a 403 error. Some projects/organizations use a custom build account instead of the default one.

### 3.4. Distinguishing Ingress and Invocation Permissions

- **--no-allow-unauthenticated** requires IAM authentication for the Cloud Run service.
- **--allow-unauthenticated** allows callers without a Cloud Run IAM principal to invoke the service when configuration and organization policies permit; use only when **intentionally exposing a public service**.
- **--ingress** controls allowed network sources/paths into the service; it does not replace authentication.
- For a private service, learners can test via **gcloud run services proxy** or an **ID token** with Invoker permission.

This lab uses a **private service** by default to avoid accidentally exposing an endpoint publicly.

## 4. Lab A — Deploying Source Code Directly

**Prerequisites:** inside the **cloud-run-hello/** directory containing **main.py** and **requirements.txt**, **with no Dockerfile yet**; **PROJECT_ID, REGION, SRC_SERVICE** variables set as in Section 3. Deploy commands create resources and incur charges; run only in an authorized lab.

### 4.1. From Source to Revision

~~~mermaid
sequenceDiagram
    participant DEV as Developer CLI
    participant CB as Cloud Build / Buildpacks
    participant AR as Artifact Registry
    participant CR as Cloud Run
    DEV->>CR: gcloud run deploy --source .
    CR->>CB: Request source build
    CB->>CB: Detect Python, install dependencies
    CB->>AR: Push container image
    AR-->>CR: Image reference
    CR->>CR: Create immutable revision
    CR-->>DEV: Service URL and deploy status
~~~

~~~bash
# MODIFIES INFRASTRUCTURE — run only inside the lab source directory.
gcloud run deploy "$SRC_SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated

# READ-ONLY — verify URL and image/revision.
gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(metadata.name,status.url,status.latestReadyRevisionName,spec.template)"
~~~

The **--source .** command orchestrates the build via Cloud Build automatically; **there is no need** to run `docker build` or `gcloud builds submit` beforehand. For a Python app without a Dockerfile, buildpacks detect `requirements.txt` and can use Gunicorn with **main:app** as the entrypoint. The line **app = Flask(__name__)** in the example is the WSGI object that Gunicorn expects.

Cloud Run uses Artifact Registry to store the image. The source repository is usually named **cloud-run-source-deploy** in the deployment region and may be created on the first run. Do not delete this repository simply because the deployment finished, as multiple source builds or other pipelines may use it.

### 4.2. Reading Results and Testing the Private Service

~~~bash
# READ-ONLY: URL and latest revision.
gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="value(status.url)"

gcloud run revisions list \
  --service="$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

To test the private service over an authenticated tunnel, in terminal 1:

~~~bash
# Runs locally, requires Invoke permission; works on Linux/macOS/WSL.
gcloud run services proxy "$SRC_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --port=8080
~~~

In terminal 2:

~~~bash
curl -i http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/healthz
~~~

**Expected output:** HTTP 200, JSON containing **message**, **release=dev**, and the actual **revision**; **/healthz** returns **ok**. The proxy is only for developers with the proper identity/permissions and does not turn the service public.

You can also invoke it directly using an **ID token** generated by `gcloud` during dev testing:

~~~bash
SERVICE_URL="$(gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"

curl -i \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/"
~~~

A gcloud-generated user ID token works for documentation testing, but for **production service-to-service** calls you must use an ID token with the proper **audience**, issued to a service account holding Invoker permission. Do not put an access token instead of an ID token into the header and expect Cloud Run IAM to accept it.

### 4.3. Modify Source, Deploy a Second Time

Edit the message in **main.py** to a version 2 message, save it, then run:

~~~bash
# MODIFIES INFRASTRUCTURE: new build, new image, creates new revision.
gcloud run deploy "$SRC_SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated

# READ-ONLY.
gcloud run revisions list \
  --service="$SRC_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Each deployment creates a new revision with the artifact and configuration at that point in time. Editing code **does not trigger a deployment automatically** without a CI/CD trigger or deploy command. The new revision receives traffic according to the service's deploy/traffic settings; always **check traffic allocation** rather than assuming every deploy routes 100% if the service currently uses traffic splitting.

## 5. Lab B — Build Container Image First, Then Deploy

This flow **decouples build from deploy**: CI builds the image, runs tests/scans, and publishes an artifact with an explicit digest; Cloud Run deploys that exact artifact.

### 5.1. Add a Dockerfile After Lab A

Place the **Dockerfile** in the same source directory as `main.py` and `requirements.txt`:

~~~dockerfile
# Demo: production should pin the base image by digest and scan for CVEs.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./

# Non-privileged numeric user; the app does not need to write to /app.
USER 65532
EXPOSE 8080

# Cloud Run injects PORT; the shell expands the variable at container start time.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 main:app"]
~~~

**Important points:**

- **EXPOSE 8080** is image metadata; it does not guarantee the server listens on that port.
- **0.0.0.0:$PORT** satisfies the runtime contract; when running locally, supply the `PORT` variable.
- **USER 65532** lowers process privileges; the image must support running without root.
- Base image tags and dependencies must be scanned/pinned in production; this Dockerfile is for lab use.
- Use **.dockerignore** to exclude **.git, .env, credentials, virtualenv, caches, and unnecessary files** from the build context. Never write secrets into Dockerfile ENV/ARG instructions or image layers.

### 5.2. Create a Standard Docker Repository

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
REPOSITORY="cloud-run-images-lab"
IMG_SERVICE="hello-img-lab"

# MODIFIES INFRASTRUCTURE: only if the repository does not exist yet and you have permission.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Cloud Run image deployment lab"

# READ-ONLY: confirm repository format and location.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$REGION"
~~~

If the repository already exists, do not recreate it. Keep the repository in the same runtime region when appropriate to reduce pull latency/transfer and satisfy data residency requirements.

### 5.3. Build, Tag, and Push

~~~bash
IMAGE_BASE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/hello-api"
IMAGE_URL="$IMAGE_BASE:1.0.0"

# Configure the Docker credential helper on the build machine (does not grant IAM).
gcloud auth configure-docker "$REGION-docker.pkg.dev"

# MODIFIES local state: build Docker image from Dockerfile.
docker build -t "$IMAGE_URL" .

# MODIFIES Artifact Registry: push image.
docker push "$IMAGE_URL"

# READ-ONLY: image/digest metadata.
gcloud artifacts docker images list \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

CI must hold **Artifact Registry Writer** permission on the target repository. If the machine lacks a Docker daemon, you can run Cloud Build from the source directory (requiring appropriate build and push permissions):

~~~bash
# MODIFIES INFRASTRUCTURE: build and push via Cloud Build.
gcloud builds submit . \
  --tag="$IMAGE_URL" \
  --project="$PROJECT_ID"
~~~

Choose **one** build path; you do not need to run both Docker and Cloud Build. Record the **commit SHA, build ID, image digest, and scan/SBOM** for the release; tags are only convenient labels.

### 5.4. Run the Image Locally Before Deploying

~~~bash
# MODIFIES local state: run container image in Docker.
docker run --rm -p 8080:8080 -e PORT=8080 \
  -e RELEASE=image-lab "$IMAGE_URL"

# Another terminal, READ-ONLY:
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/healthz
~~~

If local testing does not return HTTP 200, check the app entrypoint, image architecture, port, and dependencies before deploying. On Apple Silicon or ARM64 CI runners, build a Linux architecture image supported by Cloud Run (per the image manifest and runtime contract), rather than assuming any local image runs on the cloud.

### 5.5. Deploy the Image to Cloud Run

~~~bash
# MODIFIES INFRASTRUCTURE: pushed image must exist and deployer must have Reader permission.
gcloud run deploy "$IMG_SERVICE" \
  --image="$IMAGE_URL" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated \
  --set-env-vars="RELEASE=1.0.0"

# READ-ONLY: actual image of the new revision.
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Deploy by digest in production CI.** Retrieve the actual digest from push output or Artifact Registry, then replace the image reference with:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/hello-api@sha256:FULL_DIGEST
~~~

When deploying by tag, Cloud Run **resolves the tag to a digest at deploy time** and that revision serves that specific image version rather than changing automatically if the tag is later overwritten. Still, for pipeline auditability and verifiable rollbacks, use the full digest in manifests and deployment records.

### 5.6. Image Workflow for CI/CD

~~~mermaid
flowchart LR
    SRC["Git commit"] --> TEST["Lint + Unit/Integration tests"]
    TEST --> BLD["Build OCI image"]
    BLD --> AR["Artifact Registry: image@digest"]
    AR --> SEC["CVE/SBOM/provenance checks"]
    SEC --> STAGE["Deploy staging by digest"]
    STAGE --> OK{"Smoke test / SLO PASS?"}
    OK -- "No" --> FIX["Block promotion"]
    OK -- "Yes" --> PROD["Promote same digest to production"]
~~~

Separate the identities of **CI builder**, **deployer**, **Cloud Run service agent**, and **runtime service account**. Do not grant Project Editor/Owner to all of them simply because the pipeline needs to both build and deploy.

## 6. Comparing Actual Results of the Two Labs

| Observation | Source deploy | Image deploy |
|---|---|---|
| Input required by deployer | Source directory and build permissions | Image URL/digest and deploy permissions |
| Dockerfile | Optional; used if present | Build pipeline can use a Dockerfile |
| Is Cloud Build called during deploy? | Yes in the default source-with-build flow | No: deploy only uses the pre-built image |
| Artifact Registry | Stores output image; source repo may be auto-created | Image repository managed separately |
| Does editing source immediately create a revision? | No, requires deploy/CI trigger | No, requires build/push/deploy via pipeline |
| Immutable revision | Yes | Yes |
| SBOM, signer, promotion controls | Can be added to build pipeline | Cleaner when CI separates build and deploy |
| Ability to protect service with IAM/ingress | Identical | Identical |
| Runtime scaling, network, logs | Identical for equivalent configuration | Identical for equivalent configuration |

**Rule of thumb:** use **--source** when prioritizing speed and simple builds; use **--image** when you need tested/scanned artifacts, reuse across environments, digest pinning, and strict separation of build vs. deploy permissions. Do not treat them as two different "platforms": ultimately both deploy Cloud Run revisions from container images.

## 7. Revisions, Traffic Splitting, and Rollback

Every deployment of a new image or revision configuration creates an **immutable revision**. This allows shifting traffic gradually from an old version to a new one without overwriting the running image.

### 7.1. Inspecting Revisions and Traffic

~~~bash
# READ-ONLY.
gcloud run revisions list \
  --service="$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.traffic,status.latestReadyRevisionName,status.url)"
~~~

When verifying a change, check **which revision is Ready** and **which revision is currently receiving traffic**. A Ready revision does not automatically mean it serves 100% of requests; the service might still route traffic to an older version or use a canary split.

### 7.2. Rollback via Traffic, Not by Overwriting a Tag

Suppose the list returns two verified revisions: **hello-img-lab-old** and **hello-img-lab-new** (illustrative names; replace with actual revision names).

~~~bash
# MODIFIES TRAFFIC — only in the lab service after selecting the right revision.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-revisions="hello-img-lab-old=100"

# READ-ONLY — verify traffic after rollback.
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.traffic)"
~~~

This rollback **shifts traffic back to the older revision**; it does not automatically roll back database schemas, Secret Manager versions, business data, or Google APIs called by the service. If the environment runs database migrations, you need a separate backward-compatible migration strategy.

### 7.3. 10% Canary Traffic

~~~bash
# MODIFIES TRAFFIC — only after both revisions exist and passed smoke tests.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-revisions="hello-img-lab-old=90,hello-img-lab-new=10"
~~~

Monitor error rate, latency, and request count **per revision**. A low-traffic canary may not gather enough samples to evaluate properly; ensure adequate traffic/SLO windows. Once all checks pass, you can route 100% to the approved revision. Command:

~~~bash
# MODIFIES TRAFFIC: route 100% to the latest revision and future deployments
# following the 'to-latest' policy; do not use if a fixed split is required.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-latest
~~~

**Distinction:** automatically following latest differs from pinning a specific revision name. CI/GitOps must know which traffic management mode is active so it does not overwrite an SRE canary or rollback.

## 8. Security at Deploy Time and Runtime

### 8.1. Three Permission Boundaries

~~~mermaid
flowchart LR
    DEV["Deployer IAM"] -->|"Create revision"| RUN["Cloud Run"]
    BUILD["Build SA + registry Writer"] -->|"Push image"| AR["Artifact Registry"]
    RUN -->|"Service identity"| API["Cloud SQL / Storage / Pub/Sub"]
    CALLER["Invoker ID token"] -->|"HTTP request"| RUN
    AR -->|"Image access"| RUN
~~~

- **Build permission** allows creating and publishing images; it does not grant access to Cloud SQL.
- **Deploy permission** allows modifying Cloud Run revisions/config; it does not necessarily allow calling business APIs.
- **Runtime service identity** needs minimal roles for the Google APIs actually called by application code.
- **Invoke permission** controls clients calling a private Cloud Run service. For service-to-service calls, use an **ID token whose audience is the service URL or appropriate custom audience**, not a Google APIs access token.

In cross-project image deployments, the Cloud Run **service agent** of the runtime project may need **roles/artifactregistry.reader** on the source repository alongside the deployer's read permission. Do not make the repository public just to fix a 403 error.

### 8.2. Environment Variables and Secrets

Non-secret config variables such as **RELEASE**, log level, or feature flags can be passed via **--set-env-vars** at deploy time, though this replaces the entire variable set per the flag's semantics; to update individual variables, use **--update-env-vars** per the documentation.

**Never use environment variables or Dockerfiles to embed service account keys or passwords** as plain text in scripts or Git. For credentials, prefer **Cloud Secret Manager integration** (secret environment variables or mounted volumes) and grant **Secret Manager Secret Accessor** on the specific secret to the runtime identity.

Never print env lists containing secrets to logs or tickets. Changing the service account, secret references, CPU/memory, or timeout typically creates a new revision; plan rollouts the same way as image updates.

### 8.3. Ingress, TLS, and Private Networking

| Requirement | Appropriate design |
|---|---|
| Public API | Ingress and IAM/public policy per approval; app auth, WAF/Cloud Armor via LB as needed |
| Private endpoint via Cloud Run IAM | Require authentication; Invoker + ID token |
| Accept traffic only via internal VPC / load balancer | Supported Cloud Run ingress settings and LB architecture |
| Service calling a private database in a VPC | **Direct VPC egress** or connector per architecture |
| Service calling Cloud Storage/Google APIs | Runtime IAM + network routing per configuration |

**Ingress and IAM are two independent layers.** Internal ingress does not automatically allow any caller access if the service still requires Invoker. Conversely, allowing public invocation does not bypass ingress restrictions.

### 8.4. Container Images and Safe Releases

In production:

1. Check dependencies/base images and CVEs.
2. Use immutable versions/digests, recording commit SHA, build ID, and SBOM/provenance.
3. Never store secrets in source code, build contexts, or image layers.
4. Separate SAs for build, deploy, and runtime.
5. Deploy verified images to staging, run smoke/load tests, then promote the **same digest**.
6. Restrict permissions to alter traffic, delete revisions, and modify IAM.
7. Configure Cloud Logging/Monitoring and maintain an appropriate rollback window.

## 9. Troubleshooting: Pinpointing the Layer of Failure

| Symptom | Relevant layer | What to check |
|---|---|---|
| Source build fails | Cloud Build/buildpack/Dockerfile | Build logs, runtime/dependencies, ignored files, Build SA |
| `--source` reports permission denied | IAM/API | `run.sourceDeveloper`, `run.builder`, `serviceUsage`, SA user |
| Build image push 403 | Artifact Registry | Repo path/region, Writer IAM, Docker helper/Cloud Build SA |
| Deploy image not found | Image registry | Exact URL, existing tag/digest, repo format and location |
| Cross-project image deploy 403 | Service agent/repo IAM | Reader on source repository for the required principals |
| Revision not Ready | Container startup | PORT, bind `0.0.0.0`, startup errors, env/secrets, memory |
| Service returns HTTP 401/403 | Invoke IAM or app auth | ID token/audience, `roles/run.invoker`, ingress |
| HTTP 404 | Wrong path or URL/service | Service URL, app routes, revision traffic |
| HTTP 503 | Instance startup/capacity/health | Revision status, logs, concurrency/max instances |
| HTTP 504 | Request timeout / dependency | Latency, downstream, timeout, worker behavior |
| App only listens on 127.0.0.1 | Container runtime | Bind `0.0.0.0:$PORT` |
| Runs locally, fails on Cloud Run | Architecture/env/resources | Linux image, PORT, dependencies, memory, stdout logs |
| Deployed but still returns old response | Traffic/revision/cache | `status.traffic`, revision name, image digest, cache |
| Costs still accrue with low traffic | Min instances, build, registry, logs, egress | Billing SKUs and service settings |

### 9.1. Read-Only Investigation Commands

~~~bash
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format=yaml

gcloud run revisions list \
  --service="$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services logs read "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=50

gcloud artifacts docker images list \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

**Distinguish build logs from runtime logs.** If Cloud Build fails before deployment, no Cloud Run revision may have been created yet; inspect Cloud Build execution logs. If deployment created a revision that failed at startup, inspect **Cloud Run revision/container logs** and error details. Avoid pasting access tokens, Authorization headers, or secrets into tickets.

### 9.2. Four Steps to Verify Port Errors

1. In **Dockerfile/CMD**, does the entrypoint actually start the server?
2. Does the server bind **0.0.0.0** instead of **127.0.0.1**?
3. Does the server read its port from **PORT**, and does it match the port configured in Cloud Run?
4. Is there an import/runtime error, missing dependency, or OOM before the server opens the port?

Never blindly increase memory when the actual cause is listening on the wrong port.

## 10. Scaling, Reliability, and Cost

Cloud Run manages autoscaling automatically; services can scale to zero when idle if no minimum instances are configured. Each instance has CPU/memory/concurrency and a request timeout, impacting both latency and billing.

| Setting | Impact |
|---|---|
| **Min instances** | Keeps instances warm, reduces cold starts, but increases cost |
| **Max instances** | Caps scale to protect downstreams/budgets, though brief overshoots and 429/503s can occur when capacity saturates |
| **Concurrency** | Simultaneous requests per instance; too high can overload Java threads/DB pools |
| **CPU / Memory** | Sized via profiling; too low causes OOM/high latency |
| **Request timeout** | Caps request duration; does not replace async job mechanisms |
| **Billing setting** | Billed per request or instance lifecycle depending on current config |
| **Region** | Latency, data residency, network transfer, and available features |

### 10.1. Tune Using Measurements

For example, in a Java API service, 1 instance at concurrency 80 might spike concurrent DB queries, whereas setting concurrency=1 might spin up many instances with higher cost and cold starts. Never pick a "universal optimal number"; measure **p95/p99 latency, CPU/memory usage, DB connection counts, 5xx rates, cold starts, and cost per successful request**.

**Warning about max instances:** this is a scaling guardrail, **not a hard billing cap**. Cloud Run may briefly exceed the limit during certain autoscaling intervals; builds, storage, logging, and egress are also billed separately.

### 10.2. Cost Sources When Comparing Both Paths

| Line item | Source deploy | Image deploy |
|---|---|---|
| Cloud Build | Present in the default build flow | Present if pipeline uses Cloud Build |
| Artifact Registry | Stores generated images | Stores built images, shareable across services |
| Cloud Run compute/requests | Per service/revision configuration | Per service/revision configuration |
| Network egress | Per request/downstream traffic | Similar |
| Logs/metrics | Per volume/retention | Similar |
| Secret Manager/KMS/Cloud SQL | Per integrated service | Similar |

Do not compare costs merely by deployment count. Use **Cloud Billing Reports** broken down by service/SKU over time, calculating cost/request or cost/job across equivalent workloads. Source deploy may be more convenient, but that does not mean runtime execution is cheaper.

## 11. Case Study: From Java Source to Image-Digest Release

**Context:** an e-commerce team has a **checkout** API written in Java and plans to use Cloud Run to avoid managing VMs or GKE for a stateless HTTP service.

### 11.1. Development Phase

Developers run **gcloud run deploy --source .** against a dev project. Buildpacks detect Maven/Gradle or the Dockerfile if present; Cloud Build creates the image and Cloud Run creates a revision. The team verifies:

- The app listens on the right PORT and the health endpoint returns HTTP 200.
- The runtime service account holds only the permissions needed for dev resources.
- No DB passwords are baked into source images or variables committed to Git.
- Cloud Logging surfaces exceptions/latency; scaling handles test traffic.

### 11.2. Production Phase

CI builds the image from a merged commit, runs tests and vulnerability scans, records the digest and build provenance, and pushes to Artifact Registry. The pipeline deploys to staging separately, then **promotes the exact same digest** to production via **--image**.

The SRE team shifts 10% traffic to the new revision while watching p95 latency, 5xx rates, and DB connections. If metrics breach SLOs, they run **update-traffic --to-revisions** to revert to the previous revision. Order data remains in Cloud SQL/Firestore or other durable stores so rollbacks do not depend on container filesystems.

### 11.3. Architectural Decisions

| Decision | Reason |
|---|---|
| Source deploy for dev | Fast, no need to manage local Docker |
| Image deploy for prod | Same tested/scanned digest, easy to audit/roll back |
| Private service + service-to-service ID token | Avoids exposing a public endpoint unnecessarily |
| Dedicated runtime SA | Least-privilege GCP API permissions |
| Secrets in Secret Manager | Separates credentials from images and source |
| SLO-monitored traffic split | Reduces release risk |
| Cloud Billing/Budget alerts | Controls build, registry, and runtime spend |

Not every organization has to use source in dev and images in prod; what matters is choosing a **reproducible, auditable workflow** suited to your requirements. If source deploy is integrated into CI with provenance controls, it can still serve production.

## 12. Lab Cleanup and Exercises

### 12.1. Clean Up Only the Resources You Created

Before deleting, verify that the project, region, both service names, and the repository **are owned by you**, with no active traffic or other pipelines depending on them.

~~~bash
# READ-ONLY.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Only when authorized and lab resources are confirmed:

~~~bash
# DELETES REAL RESOURCES — only for the two lab services.
gcloud run services delete "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services delete "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Deleting a service **does not automatically delete** Artifact Registry images, Cloud Build logs, Cloud Logging data, reserved IPs, Secret Manager secrets, or other services. Delete the **cloud-run-images-lab** repository separately only when certain it was created exclusively for this lab, has no remaining versions/consumers to retain, and is approved. **Do not delete the default cloud-run-source-deploy repository** because it may be shared across multiple source deployments.

### 12.2. Quick Self-Check Quiz

1. When a source directory **has no Dockerfile**, which tool does deploy-from-source use by default to build the image?
2. If a source directory **has a Dockerfile**, does `--source` ignore the Dockerfile?
3. Does using `--image` ask Cloud Run to rebuild from source?
4. What type of token does `curl` need to call a private service?
5. Does a revision deployed from tag **:stable** automatically change its image if the `stable` tag is overwritten later?
6. Why can running an app on **127.0.0.1:8080** fail on Cloud Run?
7. When rolling back an HTTP release, should you shift traffic or overwrite a tag?
8. Does **roles/run.invoker** automatically allow CI to push images to Artifact Registry?
9. Why can min instances increase the bill even when traffic is near zero?
10. Does deploying new code automatically roll back a database schema or Secret Manager version?

**Answers:** (1) Cloud Build + buildpacks; (2) no, the Dockerfile is used; (3) no; (4) a valid ID token with Invoker permission and matching audience; (5) no, the revision already resolved the digest; (6) it must listen on **0.0.0.0:$PORT**; (7) shift traffic back to a verified revision; (8) no; (9) keeps instances warm and allocated; (10) no.

### 12.3. Verifiable Hands-On Exercises

**Exercise A — Source:** from the two lab Python files, deploy a private **hello-src-lab**; record the URL, latest Ready revision, **/healthz** response, source build logs, and Artifact Registry image location.

**Exercise B — Image:** add the Dockerfile, build/push tag **1.0.0**, record the digest, and deploy **hello-img-lab** from that image. Prove the service runs the exact pushed digest and compare steps/timing with Lab A.

**Exercise C — Rollback:** deploy version 2 with a new message, verify two revisions; split traffic 90/10 in the lab and then route 100% back to version 1. Record p95 latency, HTTP errors, and traffic config before/after.

**Exercise D — Decision:** a team must release to staging and production with SBOM requirements, security sign-off, and no rebuilds during promotion. Choose source or image, and specify IAM, digest/provenance, and rollback design.

Reports must include at minimum:

~~~text
PROJECT / REGION / OWNER:
SOURCE_SERVICE / READY_REVISION:
SOURCE_BUILD_ID / ARTIFACT_REGISTRY_LOCATION:
IMAGE_REPOSITORY / IMAGE_TAG / IMAGE_DIGEST:
IMAGE_SERVICE / READY_REVISION:
IAM_AUTHENTICATION / INGRESS:
PORT / HEALTH_CHECK_RESULT:
TRAFFIC_SPLIT / ROLLBACK_RESULT:
LOGS / ERRORS:
BILLING_GUARDRAILS:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Record **actual observed results**; never mark PASS without running the test. Never include credentials, ID tokens, or secrets in the report.

## 13. Official References and Checklist

- [Cloud Run: Deploy services from source code](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run: Deploy container images](https://docs.cloud.google.com/run/docs/deploying)
- [Cloud Run: Deployment options](https://docs.cloud.google.com/run/docs/deployment-options-for-services)
- [Cloud Run: Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud Run: Set build service account](https://docs.cloud.google.com/run/docs/configuring/services/build-service-account)
- [Cloud Run: Service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Cloud Run: Authenticate developers](https://docs.cloud.google.com/run/docs/authenticating/developers)
- [Cloud Run: Traffic splitting and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Buildpacks: Python build](https://docs.cloud.google.com/docs/buildpacks/python)
- [Cloud Run: Troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Artifact Registry: Docker authentication](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

**Deployment checklist:** confirm project/region/identity → verify APIs/permissions → build traceable source or image → ensure **0.0.0.0:$PORT** → deploy private or intentionally public → verify revision/URL/auth/health → monitor logs/SLOs → manage traffic, digests, and rollbacks → verify costs and clean up lab.

**Connection to the CLOUD_PROVIDERS_GCP track:** Cloud Run lets you deploy HTTP services without directly managing GKE nodes or Compute Engine VMs. **Source deploy** helps you start fast, while **image deploy** gives you artifact governance and CI/CD release control. In both cases, combine **Artifact Registry, IAM, VPC/networking, durable storage/databases, Cloud Monitoring, and Cloud Billing** to deploy safely, reliably, and cost-effectively.
