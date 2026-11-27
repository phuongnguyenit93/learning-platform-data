# Pushing, Pulling, and Managing Access Control for Container Images in Artifact Registry

A development team packages an orders API into a **Docker container image**, using **Cloud Run** to serve HTTP requests, **GKE** for multi-replica workers, and **Compute Engine** for administrative tasks. If each environment rebuilds the image from source code, it is hard to verify that they are running the exact same version. If registry permissions are overly broad, a compromised account can overwrite or delete critical images. If pull access is misconfigured, deployments can stall with `ImagePullBackOff`, `PERMISSION_DENIED`, or image-not-found errors.

**Artifact Registry** is Google Cloud's artifact repository management service. For containers, it provides **Docker repositories** to store, distribute, and govern images by **tag** or **digest**, combined with **IAM** to decide who can read, push, administer, or delete artifacts. A standard workflow is **build one image → push to a repository → verify the digest → deploy that exact artifact** to GKE, Cloud Run, or another container runtime.

This lesson belongs to the **Containers and Artifact Registry** chapter in the **CLOUD_PROVIDERS_GCP** module. It connects project management, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and data with reproducible release pipelines, artifact protection, reliability controls, and cost management. The core scope is **pushing, pulling, and controlling access to container images**, rather than an introductory guide to all of Kubernetes or Docker.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **image, repository, tag, and digest**; read Artifact Registry image names accurately.
2. Create and inspect a **standard Docker repository** in a chosen location.
3. Authenticate Docker using the **gcloud credential helper** or **short-lived access tokens**, then build, tag, push, and pull images.
4. Assign **least-privilege IAM roles** to developers, CI/CD, GKE nodes, and identities involved in Cloud Run deployments.
5. Separate **artifact push/pull permissions** from **permissions to run, update, and act as a runtime service account**.
6. Prefer deploying by **image digest**, establishing release controls, provenance, vulnerability scanning, and rollback.
7. Isolate networking, authentication, authorization, repository, tag, digest, and runtime platform failures.

## 2. Core Components

### 2.1. What Is an Image?

A **container image** is an artifact bundle packaging filesystem layers, metadata, startup instructions, and the components needed to run a container. It is typically built from a `Dockerfile` or an equivalent build tool.

~~~text
Source code + Dockerfile
       |
       v
    docker build
       |
       v
Container image (layers + manifest)
       |
       v
Artifact Registry Docker repository
       |
       +--> Cloud Run
       +--> GKE
       +--> Compute Engine + container runtime
~~~

A **repository** holds multiple images/versions in a managed location and format. A **tag** is a convenient reference name, such as `v1.3.0`, `staging`, or `latest`. A **digest** is the content identifier of a manifest, typically formatted as `sha256:<hex>`.

A tag can be updated to point to a different digest if the repository permits it; a digest is bound to specific manifest contents. Therefore, for production, **pinning by digest** identifies the artifact more accurately than relying on tags alone.

### 2.2. Artifact Registry URI Structure

Docker images in Artifact Registry typically follow the form:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
~~~

Example:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

| Component | Example | Meaning |
| --- | --- | --- |
| `LOCATION` | `asia-southeast1` | Repository location and corresponding Docker Registry hostname. |
| `PROJECT_ID` | `retail-lab` | Project owning the Artifact Registry repository. |
| `REPOSITORY` | `retail-containers` | Managed Docker repository within the project/location. |
| `IMAGE` | `orders-api` | Image name or image subpath inside the repository. |
| `TAG` | `v1.0.0` | Label referencing a content version. |
| `sha256:DIGEST` | Actual digest string after push | Immutable reference to the corresponding manifest. |

**Common point of confusion:** repository `retail-containers` and image `orders-api` are **two different levels**. In the path above, `retail-containers` is the repository resource carrying an IAM policy and location; `orders-api` is an image inside that repository. Omitting the repository name or using the wrong location can cause `not found` errors even when the tag is right.

### 2.3. Container Registry and Artifact Registry

Older guides may reference domains like `gcr.io`, `us.gcr.io`, or the term **Container Registry**. Artifact Registry is the recommended artifact management solution for new workflows, supporting `LOCATION-docker.pkg.dev` hostnames as well as certain **gcr.io repositories hosted on Artifact Registry**. Do not assume every legacy `gcr.io` image automatically sits inside a `*.pkg.dev` repository or shares the same IAM.

When upgrading pipelines, verify the **actual registry type, repository, permissions, image address**, and migration process. This lesson uses `asia-southeast1-docker.pkg.dev` to demonstrate Artifact Registry directly.

### 2.4. Repository Modes

Artifact Registry provides repository modes for different needs:

| Type | Purpose | Push/pull notes |
| --- | --- | --- |
| **Standard repository** | Stores artifacts built/pushed by your team. | Primary choice for running `docker push` with internal images. |
| **Remote repository** | Caches/proxies artifacts from supported upstreams. | Not used as a push target for internal images like a standard repo. |
| **Virtual repository** | Provides a single aggregated endpoint over configured upstream repositories. | Primarily for retrieval; does not replace standard repositories for pushing. |

To learn the build–push–pull workflow and clear IAM management, we use a **standard Docker repository**. Other repository types have specific upstream policies, permissions, caching, and routing limits that should be checked against current documentation.

## 3. Image Release Flow Architecture

### 3.1. Build Once Across Environments

~~~mermaid
flowchart LR
    SRC["Git source / Dockerfile"] --> CI["CI: test + build"]
    CI --> AUTH["Short-lived identity + Writer permission"]
    AUTH --> REG["Artifact Registry: standard Docker repo"]
    REG --> META["Image digest + release metadata"]
    META --> RUN["Cloud Run revision"]
    META --> GKE["GKE Deployment"]
    META --> VM["Compute Engine worker"]
    IAM["Repo-level IAM"] -. "Writer for CI; Reader for consumers" .-> REG
    SEC["Scan / policy / provenance"] -. "Evaluate artifact" .-> META
~~~

This flow clearly separates:

1. **Build identity** builds and tests the artifact.
2. **Publisher identity** requires permission to push to the repository.
3. **Deployer identity** requires permission to deploy to Cloud Run/GKE/VM and, depending on the product, permission to read the image.
4. **Pulling identity** is used by the platform to download the image at deploy/startup time.
5. **Runtime identity** inside the application holds permissions to access data services such as Cloud Storage, Cloud SQL, Pub/Sub, or Secret Manager.

These are **not necessarily the same service account**. The principle of least privilege requires granting permissions only on the exact resources needed at each step.

### 3.2. Why Not Rebuild in Production?

If GKE runs `docker build .` on the `main` branch today and Cloud Run rebuilds tomorrow, dependency contents can differ even when the application tag is the same. A sound workflow:

- Build once in CI from a specific commit/version.
- Record the **successfully pushed digest** and test results.
- Promote **the exact same digest** through dev, staging, and production per organizational approval.
- When rolling back, revert the runtime to a **previously verified digest**, rather than relying on a shifting `latest` tag.

Digest pinning controls image contents; it **does not by itself guarantee an image has no vulnerabilities, contains no secrets, or behaves correctly**. Security and quality checks before release are still required.

## 4. Preparing the Project, Location, and Docker Repository

### 4.1. Input Inventory

Before taking action, define:

| Parameter | Example value | Design question |
| --- | --- | --- |
| Repository-owning project | `retail-lab` | Who manages IAM and Billing for artifacts? |
| Location | `asia-southeast1` | Is it close to GKE/Cloud Run/VMs and compliant with residency? |
| Repository | `retail-containers` | Which teams can read, write, and clean up artifacts? |
| Image name | `orders-api` | Does naming clearly trace back to the service? |
| Version tag | `v1.0.0` | Could it be overwritten, and does the release process allow it? |
| Publisher principal | CI service account | Does it only need `artifactregistry.writer`, or more permissions? |
| Consumer principals | GKE node SA / Cloud Run service agent, etc. | Who actually pulls the image? |
| Network path | DNS/TCP 443 to registry | Do workloads without external IPs have a route to the registry? |

**Repository location** is a property of the repository resource. Do not assume you can directly change a repository's location after creation. If a region move is needed, create a new repository, transfer artifacts, grant permissions, and update deployment URIs per service documentation.

### 4.2. Verify APIs and Tool Versions

Examples use Bash. `describe` and `list` commands are **read-only**; `enable`, `create`, `add-iam-policy-binding`, `push`, and `delete` modify real resources.

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"
IMAGE_NAME="orders-api"
IMAGE_TAG="v1.0.0"
HOST="${LOCATION}-docker.pkg.dev"
IMAGE_URI="${HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

# READ-ONLY: CLI account and project in use.
gcloud auth list
gcloud config get-value project
gcloud --version
docker --version
~~~

The lab machine needs Docker Engine or a compatible Docker environment, permission to run the Docker CLI, and network connectivity. In Windows PowerShell, variable syntax and line continuation differ from Bash; do not copy `$VAR="..."` or trailing `\` verbatim into PowerShell.

### 4.3. Enable the Artifact Registry API

~~~bash
# WRITE: execute on an authorized project.
gcloud services enable artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

Enabling APIs requires appropriate service management permissions, not merely `roles/artifactregistry.reader`. If the project already has the API enabled, skip this write operation.

### 4.4. Create a Standard Docker Repository

~~~bash
# WRITE: create a new repository; do not rerun if the repo already exists.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="Container images for retail workloads"

# READ-ONLY: verify repository format, location, and metadata.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# READ-ONLY: list repositories in the location.
gcloud artifacts repositories list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Do not write real resources into a read-only or unapproved project. For production, configure **cleanup policies**, tag immutability (if applicable), CMEK, and other controls up front via IaC rather than bolting them on ad hoc after artifacts are already in use.

## 5. Authenticating Docker to Artifact Registry

### 5.1. Docker Needs Registry Credentials

`gcloud auth login` authenticates the Google Cloud CLI, but **does not automatically make every `docker push`/`pull` use the right token**. Docker needs an appropriate credential mechanism for the `LOCATION-docker.pkg.dev` hostname.

There are two common methods:

1. **gcloud credential helper:** Docker retrieves credentials from gcloud when accessing the configured hostname.
2. **Short-lived access token:** Docker logs in using a token issued for a Google principal that expires per policy.

Do not use **long-lived JSON service account keys** as the default for personal machines or CI/CD. Prefer valid user identities or **Workload Identity Federation/short-lived credentials** in automation. Never print tokens to build logs or commit Docker config files containing secrets.

### 5.2. Use the gcloud Docker Credential Helper

~~~bash
# WRITE to the Docker configuration on the machine running the command.
gcloud auth configure-docker "${LOCATION}-docker.pkg.dev"

# Inspect credential helper config if diagnostics are needed.
# Docker reads the config file at the location determined by DOCKER_CONFIG
# or the user's default configuration directory.
~~~

The command above configures Docker to invoke the credential helper for the **specified hostname**. It does not grant IAM permissions to the gcloud account. If gcloud is using the wrong principal or the repository does not allow that principal to write, `docker push` will still be denied.

**`sudo docker` warning:** on Linux, `sudo docker` may read root's Docker config instead of the user who ran `gcloud auth configure-docker`. Keep Docker execution consistent with the user configuring it; do not fix this by copying tokens haphazardly between accounts.

### 5.3. Use a Short-Lived Access Token

In environments permitting CLI access tokens, you can log in as follows:

~~~bash
gcloud auth print-access-token | docker login \
  -u oauth2accesstoken \
  --password-stdin "https://${LOCATION}-docker.pkg.dev"
~~~

This example assumes gcloud is already authenticated with the right identity and the token holds appropriate permissions. Short-lived tokens **expire**, so pipelines need per-session token issuance rather than relying on stored long-lived tokens.

In CI/CD running outside Google Cloud, **Workload Identity Federation** can exchange an identity from the CI provider for short-lived Google Cloud credentials, reducing the need to manage service account private keys. Specific setup steps depend on the CI provider and organizational policy.

### 5.4. Authentication vs. Authorization

| State | Possible outcome |
| --- | --- |
| No valid credential/token | `401 Unauthorized`, authentication required, or pull/push fails. |
| Valid credential but missing IAM permission | `403 Permission denied`, `denied: Permission ...`, or similar message. |
| Authorized but wrong URI/repository/image/tag | `not found`, `manifest unknown`, or path error. |
| Correct IAM and URI, but network cannot reach registry | DNS timeout, TLS timeout, proxy/firewall error. |

**Do not try to fix `403` by changing the tag, and do not try to fix timeouts by granting Owner.** Identify the failure layer first.

## 6. Build, Tag, and Push a Container Image

### 6.1. Minimal Application Sample

For a self-contained example, learners can create `app.py` and `Dockerfile` **inside a separate practice directory they control**. The two code blocks below are examples, not instructions to modify any files in this learning module.

`app.py`:

~~~python
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/"):
            body = b"orders-api demo OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

port = int(os.environ.get("PORT", "8080"))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
~~~

`Dockerfile`:

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/app.py
ENV PORT=8080
EXPOSE 8080
CMD ["python", "/app/app.py"]
~~~

This is a minimal lab application, not a production web server. For real applications, use an approved base image, run as non-root when appropriate, pin dependencies/base images, build multi-architecture images if needed, scan for vulnerabilities, and never put credentials into Docker layers.

### 6.2. Build and Test Locally

~~~bash
# READ LOCAL SOURCE + WRITE LOCAL IMAGE:
docker build -t orders-api:local .

# RUN LOCAL: start a container for testing.
docker run --rm -p 8080:8080 orders-api:local

# In another terminal, test HTTP.
curl -fsS http://127.0.0.1:8080/healthz
~~~

The expected `curl` output is `orders-api demo OK`. After testing, stop the container. If the host environment already uses port `8080`, choose another host port such as `-p 18080:8080` and update the test URL.

**A successful build does not mean the image can run on every platform.** Image architecture, entrypoint, listening port, and runtime permissions must be compatible with the target Cloud Run/GKE/VM environment.

### 6.3. Tag the Image with the Repository URI

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"
IMAGE_NAME="orders-api"
VERSION="v1.0.0"

IMAGE_URI="${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${VERSION}"

# WRITE LOCAL TAG: attach the registry name to the built image.
docker tag orders-api:local "$IMAGE_URI"

# READ LOCAL: confirm the image tag.
docker image ls
~~~

`docker tag` does not upload bytes to the registry; it only creates another name reference in the local Docker image store. The registry hostname must match the repository's location and owning project.

### 6.4. Push to Artifact Registry

~~~bash
# WRITE REMOTE: upload layers/manifest into the repository.
# Requires valid Docker credentials and artifactregistry.writer permission.
docker push "$IMAGE_URI"

# READ-ONLY REMOTE: list current images/tags.
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Docker can **upload only layers not already present in the registry** thanks to content addressing, but every push still requires valid write permissions and a valid manifest/tag. On unstable networks, retries may be necessary; avoid running concurrent pipelines pushing to the same release tag without race-prevention rules.

### 6.5. Verify the Digest and Record the Release Artifact

After pushing, Docker's output usually includes a line containing the digest. You can also inspect the image in the registry:

~~~bash
# READ-ONLY REMOTE: view versions, digests, and tags.
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Use the real digest read from the push output/registry, for example:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:<REAL_DIGEST>
~~~

`<REAL_DIGEST>` is a **placeholder**, not a valid digest for running commands. In a release manifest, store `git_commit`, the digest-based image URI, pipeline run ID, build timestamp, test results, and approval policy.

**A tag is not a security signature.** If multiple users hold Writer permissions and the repository lacks overwrite controls, tag `v1.0.0` can be changed later. Digests verify exact artifact identity, while security still requires least-privilege access and provenance checks.

## 7. Pulling and Running Images from a Repository

### 7.1. Pull by Tag or Digest

On a machine with valid Docker credentials and Reader permission:

~~~bash
# READ REMOTE + WRITE LOCAL IMAGE CACHE:
docker pull \
  asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0

# Prefer digests in production workflows; replace with the real value.
# docker pull \
#   asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:...
~~~

Docker downloads the manifest and required layers to the local image store. **Pulling does not run the container**, and pull permission does not grant access to data inside Cloud SQL or Cloud Storage.

### 7.2. Run the Pulled Image

~~~bash
docker run --rm -p 8080:8080 \
  asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

If a real application needs database credentials or a service identity, use an appropriate runtime mechanism. **Do not store service account keys inside the image or in environment variables printed to logs.** When containers run in Compute Engine, GKE, or Cloud Run, prefer managed workload identities over sharing static keys.

### 7.3. Pull Fails: What Order Should You Check?

1. Does the URI have the exact **location hostname, project, repository, image, and tag/digest**?
2. Does the calling machine have DNS/TCP/TLS reachability to `LOCATION-docker.pkg.dev`?
3. Which user/service account's credentials is Docker currently using?
4. Does that principal have read permission on the repository?
5. Has the image/digest been pushed, and has it not been deleted by a cleanup policy?
6. Is the runtime architecture/manifest compatible with the deployment environment?

Do not check `docker login` alone and conclude every pull will succeed; each repository can have a different IAM policy.

## 8. IAM: Who Can Read, Write, or Administer Artifacts?

### 8.1. Common Roles

| Role | Typical purpose | Should not be granted to |
| --- | --- | --- |
| `roles/artifactregistry.reader` | View and download artifacts from authorized repositories. | Users with no need to consume the image. |
| `roles/artifactregistry.writer` | Push or update artifacts in a repository per role permissions. | Runtimes that only pull; they should not be able to modify images. |
| `roles/artifactregistry.repoAdmin` | Administer repositories/artifacts per role permissions. | CI that only needs to push one image. |
| `roles/artifactregistry.admin` | Broader Artifact Registry administration across the assigned scope. | Runtime apps or all developers by default. |

**Role names do not replace reading actual permissions and scopes.** For deleting artifacts, configuring cleanup policies, creating repositories, or modifying IAM, verify the exact permissions required. Holding Writer does not mean full resource administration, nor is Admin needed for a routine push.

### 8.2. Permission Scope

IAM can be assigned at the **repository**, **project**, or appropriate ancestor scope. Higher scopes grant access across multiple repositories:

~~~text
Organization
└── Project: retail-lab
    ├── Repository: retail-containers
    │   ├── orders-api
    │   └── catalog-api
    └── Repository: platform-tools
        └── diagnostics
~~~

If an application team only needs to push to `retail-containers`, prefer **repo-level Writer** instead of project-wide Admin. However, within **a single repository**, Reader/Writer roles generally apply across artifacts inside that repository rather than splitting per tag. If `orders-api` and `catalog-api` have different security or ownership requirements, splitting them into two repositories may be necessary.

### 8.3. Grant Reader to a User or Service Account

Assuming the repository already exists:

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"

# READ-ONLY: inspect the direct IAM allow policy of the repository.
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# WRITE: grant read access to an illustrative service account.
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:gke-pull@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

The service account `gke-pull@retail-lab.iam.gserviceaccount.com` is an illustrative name; the account must exist, be properly configured on the node/workload, and be the **principal actually performing the pull**. Adding the binding does not create the service account or reconfigure the node pool.

### 8.4. Grant Writer to CI/CD

~~~bash
# WRITE: CI publisher has permission to write artifacts in the right repository.
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:ci-publisher@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
~~~

The `ci-publisher` pipeline can build and push images within its role scope. However, to **deploy to Cloud Run or update a GKE Deployment**, the pipeline also needs target service permissions (such as Cloud Run Admin/Developer, appropriate Kubernetes cluster permissions, and permission to act as the runtime service account when required). **Artifact Registry Writer does not grant deployment permissions.**

### 8.5. Revoke Permissions

~~~bash
# WRITE: remove a directly granted Reader binding.
gcloud artifacts repositories remove-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:gke-pull@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

Removing one binding may **not be enough** if the principal still inherits the role from the project, folder/organization, a group, or another binding. Evaluate effective permissions as well as any applicable IAM Conditions/deny policies. Revoking Reader also does not necessarily purge images already cached locally or immediately terminate running containers.

### 8.6. Cross-Project Sharing

A common architecture:

~~~text
Project: platform-images
  Repository: prod-images
    orders-api@sha256:...

Project: retail-prod
  Cloud Run service / GKE cluster
    needs to pull images from platform-images
~~~

**The image-owning project** must grant read permission to the identity actually pulling, even when the workload runs in a different project. Check the consuming product's service agent/node service account, repository location, cross-project support, and IAM policies.

Never grant `allUsers` or project Editor just to "quickly share" an image between two projects. If teams want independent lifecycle controls, use separate repositories per environment/team, while managing promotion of the verified digest and controlling which artifacts are allowed to deploy.

## 9. Which Identity Do GKE, Cloud Run, and Compute Engine Use to Pull?

### 9.1. GKE: The Node Service Account Is Usually the Pull Principal

In many GKE configurations, the **kubelet/container runtime on the node** obtains credentials to pull images from Artifact Registry via the Compute Engine node's **node service account**. Do not confuse a Pod's **Kubernetes ServiceAccount** or **Workload Identity Federation for GKE** (used to call Google APIs at runtime) with the identity the node uses during image pulls.

~~~mermaid
flowchart LR
    DEP["Kubernetes Deployment: image URI"] --> SCHED["GKE scheduler / node"]
    SCHED --> NODE["Node runtime + node service account"]
    NODE --> REG["Artifact Registry"]
    REG --> POD["Image downloaded; Pod starts"]
    WIF["Pod workload identity"] -. "Permissions to call Cloud APIs at runtime" .-> POD
~~~

For pulls to succeed, verify:

- The actual node service account (which may be a custom node SA or the default Compute Engine SA depending on setup).
- IAM `roles/artifactregistry.reader` on the source repository; especially critical when the image is in **another project**.
- Node **OAuth access scopes** if the node configuration still restricts API scopes.
- Network connectivity, DNS, and egress from the node to the Artifact Registry hostname.
- Image URI, tag/digest, architecture, and Kubernetes controller permissions.

Example Deployment referencing an image by digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: retail
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
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
~~~

`REPLACE_WITH_REAL_DIGEST` is a placeholder, not a pullable digest. Replace it with a valid digest obtained from the registry. **Do not use the `latest` image tag for production version management** when you need to know the exact deployed artifact.

When seeing `ImagePullBackOff`, inspect `kubectl describe pod`, events like `ErrImagePull`, node identity, repo IAM, and networking. A Pod having a service account authorized to access Cloud Storage does not prove the node is allowed to pull images.

### 9.2. Cloud Run: Distinguish Deployer, Service Agent, and Runtime SA

When deploying an image to **Cloud Run**, at least three identities must be distinguished:

| Identity | Role |
| --- | --- |
| **Deployer user/CI** | Submits the create/update Cloud Run service request; needs deploy permissions and may need image read permissions plus permission to act as the runtime SA. |
| **Cloud Run service agent** of the service-running project | Cloud Run's system identity involved in fetching images/managing required resources; when the image is in another project, it typically needs Reader on the source repository. |
| **Runtime service account** | The identity Cloud Run application code uses to call Cloud SQL, Cloud Storage, Secret Manager, Pub/Sub, etc., once the container is running. |

For an image in the **same project**, default service agent permissions may suffice; for a **cross-project repository**, grant explicit permissions per official documentation. The Cloud Run service agent typically has the form:

~~~text
service-PROJECT_NUMBER@serverless-robot-prod.iam.gserviceaccount.com
~~~

Replace `PROJECT_NUMBER` only with the actual numeric project number of the **Cloud Run consumer**, not the alphanumeric project ID. Verify the exact principal from the IAM/service agents view before granting permissions.

Deploy example after substituting the real digest:

~~~bash
# WRITE: create/update a Cloud Run service.
# The digest URI must exist, and the deployer must have appropriate permissions.
gcloud run deploy orders-api \
  --project=retail-prod \
  --region=asia-southeast1 \
  --image="asia-southeast1-docker.pkg.dev/platform-images/prod-images/orders-api@sha256:REPLACE_WITH_REAL_DIGEST"
~~~

This illustrative command does not configure Cloud Run ingress/auth, environment/secrets, or IAM for the runtime service account. For production, define all of those in reviewed configurations to avoid accidentally allowing unauthenticated public access.

### 9.3. Compute Engine: VMs Explicitly Run Docker Pull

A VM running Docker containers does not have a built-in registry controller like GKE. Operators or VM automation must:

1. Install Docker or an appropriate container runtime.
2. Authenticate to Artifact Registry using a user identity or the **VM-attached service account** via supported methods.
3. Hold `artifactregistry.reader` on the repository.
4. Ensure VM OAuth scopes do not block API access.
5. Have network/DNS reachability to Artifact Registry and valid egress policies.

Never embed service account JSON keys in Docker images. For VMs without external IPs, configure **Private Google Access, Cloud NAT, or appropriate Google APIs connectivity** matching the hostname and topology. `*.pkg.dev` has specific DNS/endpoint requirements in some private access models; do not apply generic `*.googleapis.com` rules to registry hostnames without checking documentation.

### 9.4. Multiple Platforms Sharing One Artifact

| Platform | Image control point | Scaling/runtime mechanism |
| --- | --- | --- |
| **GKE** | Node pulls image; Pod spec references tag/digest. | Kubernetes Deployments/Jobs, node pools, and architecture-based autoscaling. |
| **Cloud Run** | Deployer + service agent hold image permissions; revision binds image. | Cloud Run manages instances/concurrency and revision traffic. |
| **Compute Engine** | VM/automation authenticates Docker pull and runs container. | VM/MIG/systemd or orchestration tools chosen by operations. |

Do not assume one platform's permissions carry over automatically to another. The same image digest can run in multiple places, but **environment variables, ingress, secrets, identities, volumes, and networks** still differ.

## 10. Designing CI/CD Without Long-Lived Keys

### 10.1. Separating Build, Publish, and Deploy Responsibilities

A pipeline may consist of:

~~~mermaid
flowchart TD
    S["Commit / pull request"] --> T["Lint, unit/integration tests"]
    T --> B["Build container image"]
    B --> SEC["Scan, SBOM, provenance/policy"]
    SEC --> P["CI publisher: push to Artifact Registry"]
    P --> DG["Record digest + release metadata"]
    DG --> ST["Deploy staging by digest"]
    ST --> QA{"Tests/approval pass?"}
    QA -- "Yes" --> PR["Deploy production with same digest"]
    QA -- "No" --> BL["Block release and investigate"]
~~~

This workflow must clearly define the principal at each step, the target repository, CI permissions, deployment environments, and logging/auditing. **Giving a single Admin account to the entire pipeline** enlarges the blast radius if a token leaks.

### 10.2. CI Publisher Permissions

CI needs:

- Source read access and build environment access per the CI tool.
- Short-lived Google Cloud credentials, e.g., via **Workload Identity Federation** if CI runs outside Google Cloud.
- `roles/artifactregistry.writer` on the authorized push repository.
- Target Cloud Run/GKE deploy permissions **only if** the pipeline performs deployment.
- Least-privilege secret access, avoiding printing secrets into build logs or image layers.

A service account running Cloud Build must also be granted appropriate permissions; **do not assume every project grants Cloud Build write access to every Artifact Registry repository by default**. Identify the exact build service account (default or custom) and current IAM policies.

### 10.3. Tag by Commit and Release by Digest

Example tagging strategy:

~~~text
orders-api:commit-9a71c3d
orders-api:release-2026-11-19
orders-api:v1.3.0
~~~

Tags help humans and tooling locate images, but **the digest is the exact artifact reference**. Once CI finishes pushing:

1. Read the actual digest of the pushed image/manifest.
2. Record the digest in release metadata; link it to the Git commit and test results.
3. Deploy to staging using the digest URI.
4. Once release criteria pass, deploy to production using **that exact same digest**.
5. Roll back to a previously approved digest without necessarily rebuilding.

For multi-architecture images, the **manifest list/index** and each platform-specific manifest have different digests; record the reference matching the image deployed by your runtime. Test the target architecture before releasing.

### 10.4. Vulnerability and Image Provenance Controls

Artifact Registry can integrate with **Artifact Analysis/vulnerability scanning**, policies, and release enforcement tools like **Binary Authorization** in supported environments. When setting quality gates, consider:

- Where does the base image come from, is it digest-pinned, and is it updated regularly?
- Does the image have unaddressed critical vulnerabilities without an approved exception?
- Are **SBOMs**, signatures/attestations, or provenance available to trace build origin?
- Has the image been tested on the right environment/architecture?
- Does the runtime only run approved digests, or can it pull `latest` arbitrarily?

**Vulnerability scanning does not prove an image is completely safe**: findings depend on detection databases, recognized packages, and scan timing. Nor should overly rigid tag immutability block security updates; release a new image with a new tag/version/digest and advance deployments through the pipeline.

## 11. Repository Security and Least Privilege

### 11.1. Dedicated Repositories for Sensitive Scopes

You can split:

~~~text
Project: platform-images
  Repository: dev-images
    CI dev → Writer
    Dev GKE nodes → Reader

  Repository: prod-images
    Release publisher → Writer
    Production Cloud Run/GKE pull identities → Reader
    Regular developers → no Writer
~~~

Repository boundaries make access easier to audit than letting everyone push to one repository holding all production images. However, separation only has value if **IAM is not over-granted at the project/folder level** and promotion workflows are genuinely enforced.

### 11.2. Avoid Unintended Public Repositories

Container images can contain source code, configs, runtime dependencies, and internal details. Never grant `allUsers`/`allAuthenticatedUsers` unless there is an explicit public artifact publishing process. If a public image is needed, design a dedicated repository and review contents, licenses, secrets, and lifecycle.

**Artifact Registry Reader is not application data access**, yet viewing/pulling an image can expose internal intellectual property (source code, dependencies, endpoints). Therefore, Reader IAM must also be granted on a need-to-know basis.

### 11.3. Secrets and Sensitive Information in Images

Never store:

- Private keys, registry login tokens, or service account JSON keys.
- Database passwords in `ENV`, Dockerfiles, or files `COPY`'d into layers.
- `.env`, `.npmrc`, credential caches, or debug outputs containing secrets.

Even if a file is deleted in a later Dockerfile layer, the secret **can still remain in an earlier layer**. Use tool-supported build secrets, `.dockerignore`, runtime secret injection, and Secret Manager IAM where appropriate.

### 11.4. Retention, Tag Immutability, and Cleanup

| Mechanism | Goal | Risk if misconfigured |
| --- | --- | --- |
| **Tag policy/immutability** | Prevent or control overwriting important tags per supported features. | Legacy pipelines attempting to overwrite tags will fail; requires a new-version strategy. |
| **Cleanup policy** | Automatically clean up unneeded artifacts per supported conditions. | Deleting active or rollback digests if not properly protected. |
| **Release metadata** | Link digest, commit, environment, timestamp, and test results. | Unable to determine which artifact to restore. |
| **IAM audit** | Track Writer/Admin grants and repository changes. | Broad project-level roles undermine repository separation. |

Before enabling automatic cleanup, inventory **digests actively used** by Cloud Run revisions, GKE Deployments, and VMs/MIGs; define retention windows for rollbacks, tags to protect, and handling of untagged images. If the tool supports dry-run, use it during review. **Deleting a tag** and **deleting an image digest** do not always have the same effect; inspect the exact target before running destructive commands.

### 11.5. Repository Encryption and Storage Location

Artifact Registry encrypts data at rest according to the service model; in certain cases **customer-managed encryption keys (CMEK)** can be configured at repository creation per supported conditions. Check location/key policies, KMS permissions, the impact of disabling keys, and rotation workflows. Do not assume choosing `asia-southeast1` for a repository automatically restricts all pipeline side-data to that region; residency requirements must account for logs, build outputs, scanners, and related artifacts.

## 12. Layered Troubleshooting

### 12.1. Common Error Matrix

| Symptom | Possible cause | First check |
| --- | --- | --- |
| `denied: Permission ...` on push | CI/user lacks Writer on repository, IAM Conditions, or policy. | Authenticated principal, repo/project IAM allow policy. |
| `401 Unauthorized` on pull | Docker lacks valid credentials, token expired, or helper wrong user. | `gcloud auth list`, Docker credential helper, and token expiry. |
| `403 Permission denied` despite `docker login` | Token is valid, but principal is not authorized for the repo. | `artifactregistry.reader` role on repo in right project/location. |
| `manifest unknown` or `not found` | Wrong tag/digest, deleted image, or wrong repository. | List images/tags in repo and compare URI. |
| `lookup ... docker.pkg.dev` error | DNS, proxy, or environment lacks resolution path. | DNS resolver, egress policy. |
| `connection timed out` | VPC route, NAT/PGA/endpoint, firewall, or proxy blocking. | DNS → TCP 443 → policy → network path. |
| Push succeeds but GKE `ImagePullBackOff` | Node SA lacks Reader/cross-project access, wrong image URI, or scopes/network. | Pod events, node service account, repository IAM. |
| Cloud Run reports inaccessible image | Wrong digest, service agent/deployer lacks permission, cross-project repo. | Artifact path, Cloud Run service agent, and deployer IAM. |
| Container runs locally but Cloud Run startup fails | Wrong port, binding `127.0.0.1`, architecture, command/entrypoint. | Cloud Run revision logs and runtime config. |
| Tag `v1.0.0` runs different code than yesterday | Tag was overwritten or multiple pipelines push to same tag. | Before/after digests, audit logs, and release metadata. |
| VM disk/cache runs out of space | Many old images/layers, uncleaned cache. | Docker disk usage and local cleanup policy. |
| Image storage costs rising | Many versions/layers, large images, unoptimized cleanup. | Artifact inventory and Cloud Billing. |

### 12.2. Read-Only Inspection Commands

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"

# Right project and identity?
gcloud auth list
gcloud config get-value project

# Does the repository exist with the right location/format?
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# Direct IAM bindings on the repository?
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# Which images/tags currently exist?
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Not seeing a Reader binding directly on a repository **does not prove a user lacks access**, because it may be inherited from the project, folder, organization, or a group; IAM deny policies or conditions could also apply. Evaluate effective permissions in each case.

### 12.3. Diagnosing GKE ImagePullBackOff

~~~bash
# READ-ONLY: run from an environment with kubeconfig for the right cluster/namespace.
kubectl -n retail get pods
kubectl -n retail describe pod orders-api-EXAMPLE-POD
kubectl -n retail get deployment orders-api -o yaml
~~~

`orders-api-EXAMPLE-POD` is a placeholder Pod name. In `describe`, inspect **Events** and the exact pull message:

1. `Failed to pull image` with `403`: check **node service account** permissions.
2. `not found`/`manifest unknown`: check whether the URI and digest/tag exist.
3. `i/o timeout`: check DNS/egress and node networking.
4. `no matching manifest`: check architecture.
5. Pull succeeds but `CrashLoopBackOff`: past the registry layer; investigate the container process/config.

GKE can use image caches and pull mechanisms that vary by runtime. A running Pod does not prove node pull permissions still work if IAM was later revoked and a node must pull the image fresh.

### 12.4. Diagnosing Cloud Run

~~~bash
# READ-ONLY: inspect the image URI bound to the service/revision.
gcloud run services describe orders-api \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format=yaml
~~~

If deployment fails because of the image:

- Verify repository/project/location and that the image digest actually exists.
- Identify the **deployer** principal and the **Cloud Run service agent** in the service-running project.
- For cross-project images, check the Reader binding on the **source repository** for the appropriate service agent.
- If the image was pulled but the revision fails to become ready, inspect startup logs, `PORT`, timeouts, entrypoint, memory, and runtime dependencies.

**Do not grant `artifactregistry.admin` to the runtime service account** as a blanket fix; runtime calls to Cloud APIs and platform image pulls are two separate paths.

## 13. Comprehensive Scenario: One Image for GKE and Cloud Run

### 13.1. Context

A retail company has:

- Project `platform-images` holding tested images in Artifact Registry.
- Project `retail-dev` running GKE for order-processing workers.
- Project `retail-prod` running the Cloud Run orders API.
- Cloud SQL storing orders, Cloud Storage storing photos and reports.
- CI building the `orders-api` image on commits, while the release team approves digests for production.

The goal is to **never rebuild images** between dev/staging/prod, keep write permissions strictly with CI, give runtimes only needed API and data permissions, and support fast rollbacks when a revision fails.

### 13.2. Repo and IAM Design

| Subject | Permission scope | Rationale |
| --- | --- | --- |
| CI publisher | `roles/artifactregistry.writer` on the release repo. | Pushes new images and manifests. |
| Regular developer | `roles/artifactregistry.reader` on dev or authorized repos. | Views/pulls for testing; cannot alter production images. |
| `retail-dev` GKE node service account | Reader on the image repository. | Nodes can pull images even across projects. |
| `retail-prod` Cloud Run service agent | Reader on `platform-images` repo as needed cross-project. | Platform can fetch the deployment image. |
| CI deployer | Appropriate Cloud Run/GKE deploy permissions plus required image/runtime SA permissions. | Deploys without being Admin across all repositories. |
| Runtime SA | Least-privilege Cloud SQL/Storage/Secret Manager permissions. | Application runs business logic after startup. |
| Platform security team | Appropriate audit and policy administration permissions. | Verifies provenance and artifact changes. |

### 13.3. Responsibility Diagram

~~~mermaid
flowchart TB
    CI["CI: build + test + push"] --> REPO["Artifact Registry\nplatform-images/prod-images"]
    REPO --> MAN["Release manifest: image digest"]
    MAN --> D["Deployer: staging / production"]
    D --> G["GKE workload in retail-dev"]
    D --> C["Cloud Run service in retail-prod"]
    REPO -. "Reader: GKE node SA" .-> G
    REPO -. "Reader: Cloud Run service agent" .-> C
    R["Runtime service identities"] -. "Cloud SQL / Storage / secrets" .-> G
    R -.-> C
    AUD["Audit + policy + scan"] -. "Release gate" .-> MAN
~~~

### 13.4. Safe Release Workflow

1. CI checks out the exact Git commit, runs tests, and builds the image.
2. CI authenticates to Google Cloud using short-lived credentials and pushes to the standard Docker repo.
3. The pipeline reads the digest, records build metadata, and runs required policy/scan checks.
4. Deploy to staging by digest; verify readiness, request logs, and integration tests.
5. Release approvers approve the digest without re-pushing a new image under the same tag.
6. Production GKE Deployments/Cloud Run revisions reference the approved digest.
7. Cloud Monitoring tracks error rates, latency, and business metrics; on failure, roll back to a previously stored digest/revision.
8. Cleanup policies retain active digests and a defined set of rollback versions per policy.

**Important:** Cloud Run and GKE may require different runtime parameters (ports, startup behavior, security contexts, DB connectivity). Sharing the same artifact controls the build source, but does not replace testing on each platform.

### 13.5. Testing Failure Scenarios

| Simulated incident in test environment | What to prove |
| --- | --- |
| Revoke CI Writer | Push is denied; existing artifacts remain usable by Reader consumers whose access is unchanged. |
| Revoke GKE node SA Reader | New nodes can no longer pull without other permissions; running Pods may continue until a fresh pull is needed. |
| Repoint image tag to new digest | Deployments pinned to the old digest do not drift with the tag; rollback stays deterministic. |
| Move image to another project | Update URI, repo IAM, service agent/node SA, and deployer permissions. |
| Accidentally delete release digest | Detect via audit logs; evaluate recovery from stored artifacts/caches/backups if available. |
| Registry egress blocked | Distinguish DNS/TCP timeouts from IAM 403 errors. |

## 14. Monitoring and Cost Management

### 14.1. What to Monitor?

**Artifact layer:**

- Number of repositories, images, and versions per team/environment.
- Layer/artifact storage volume and growth trends over time.
- Actively deployed tags/digests and unreferenced artifacts.
- Changes to IAM, cleanup policies, repository settings, and push/delete events.
- Scanning/policy check results and base image age.

**Deploy/runtime layer:**

- Deployment failure rate due to image pull errors.
- Time to create new Pods or Cloud Run revisions; startup errors.
- Recovery/rollback time after a bad image.
- Application service request success rate, latency, and SLOs.

Successful `docker push` counts do not prove a service is healthy. On GKE, verify Pod health/rollouts; on Cloud Run, verify revision readiness and real traffic.

### 14.2. Artifact Registry Cost Is Not Just Storage

Costs can include:

- Storage of image layers/versions by volume and pricing policy.
- Data transfer when pulling images across billable locations/paths.
- Build compute costs (e.g., Cloud Build runners, VMs, CI providers).
- Security scanning, logging, or add-on features where applicable.
- Network fees and deployment frequency when pulling large images repeatedly.

Do not assume using a "Google Cloud internal" registry makes **all image pulls and data transfer free**. Pricing depends on regions, source/destination, usage tiers, and active rate cards. Track costs in Billing by project/repository and actual traffic.

### 14.3. Cutting Costs Without Losing Rollbacks

1. Use appropriate base images and remove unneeded dependencies and build files.
2. Apply multi-stage builds, `.dockerignore`, and sensible caching/build strategies.
3. Avoid pushing duplicate copies of identical images into many repositories unless required by governance.
4. Configure cleanup with **keep rules** for active digests/tags and approved rollback candidates.
5. Periodically audit stale images, expired releases, and test environments.
6. Avoid hastily deleting images still referenced by Cloud Run/GKE; test before enabling broad cleanup rules.

Smaller images can reduce pull times, but size optimization matters less than ensuring **images are valid, protected, and rollback-ready** in production.

## 15. Hands-on Exercises

### Exercise 1 — Reading a URI

Given the image:

~~~text
europe-west1-docker.pkg.dev/finance-prod/app-images/invoice-worker:v2.5.1
~~~

Identify the **location, project ID, repository, image name, and tag**. For an immutable deployment, what else is needed? Why can't you assume a digest from the tag name?

**Hint:** you need the real digest returned after pushing or queried from the registry, never inferred from a version label.

### Exercise 2 — Least-Privilege Access

A CI pipeline only needs to push the `orders-api` image, while three GKE nodes only need to pull. Choose the right IAM roles and scopes. If the same repository also holds a sensitive `payments-api` image, should the repository be split?

**Hint:** Writer for CI, Reader for the node SA, repo-level bindings; split repositories when images have different access requirements.

### Exercise 3 — Debugging `ImagePullBackOff`

A GKE Pod reports `ErrImagePull`, yet the Pod already has a Kubernetes ServiceAccount authorized to call Cloud Storage. Explain why the Pod still fails to pull an image from a repository in another project. List the steps to verify the **node service account**, URI, scopes, and networking.

### Exercise 4 — Cross-Project Cloud Run

Cloud Run in project `retail-prod` references an image in a repo belonging to `platform-images`. State the roles of the **deployer**, **Cloud Run service agent**, and **runtime service account**. Which principal typically must be granted Reader on the source repository, and why is granting Reader only to the runtime SA insufficient?

### Exercise 5 — Tag or Digest?

A pipeline pushed tag `v1.0.0`; the following week another pipeline pushed new contents to the same tag. Which deployments might change when pulling/redeploying by tag, and how do digest-pinned deployments differ? Propose release and rollback rules.

### Exercise 6 — Resolving a 403 Error

A developer ran:

~~~bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
docker push asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

The push returned `PERMISSION_DENIED`. Outline the sequence to check gcloud identity, Docker config/user, project/repo, IAM policy, and effective roles. Why is granting `roles/artifactregistry.admin` unnecessary if only Writer permission is missing?

### Exercise 7 — Handling an Image Containing a Secret

A developer added `COPY .env /app/.env` in a Dockerfile and deleted the file in the next layer, then pushed the image. Can the secret be considered gone from the image? Propose a workflow to rotate the credentials, rebuild a clean image, inspect layers, block bad builds, and audit who pulled it.

### Exercise 8 — Choosing Storage Locations and Estimating Costs

A GKE cluster runs in Singapore, production Cloud Run runs in Europe, and CI runs in another region. Would you choose one repository or multiple repositories? How should you weigh **location, data residency, transfer cost, IAM, pull speed, and release control requirements**?

### Exercise 9 — Cleaning Up Old Images

The infrastructure team has 300 image versions and wants to delete those older than 60 days. Describe how to identify digests still in use by GKE/Cloud Run, keep rules for rollbacks, review/dry-run where supported, and the approval workflow before enabling cleanup.

## 16. Production Checklist

| Item | Requirement to meet |
| --- | --- |
| **Repository** | Standard Docker repo in the right project/location, with an owner and documented identifier. |
| **Image naming** | URI clearly identifies location/project/repository/image; tags/versions follow convention. |
| **Digest** | Record real digest after push; deploy production by digest where appropriate. |
| **Build** | Tested, approved base image, no embedded credentials, matching architecture. |
| **Publisher identity** | CI uses short-lived credentials, Writer on needed repo, no broad Admin. |
| **Pull identities** | GKE node SA, Cloud Run service agent/deployer, VM principal matched to each platform. |
| **Cross-project IAM** | Source repository grants Reader to the exact pulling principal of the consuming project. |
| **Networking** | DNS/TCP 443 to registry; VPC egress/Private Google Access/NAT per supported topology. |
| **Runtime identity** | Permissions to call Cloud SQL/Storage/secrets separated from image pull permissions. |
| **Security gate** | Vulnerability scans, provenance/SBOM/signatures/policies matching security tier. |
| **Release management** | Staging verification, approval, recorded digest/commit, rehearsed rollback. |
| **Tag/cleanup policy** | Prevent unintended release tag overwrites; retain active digests. |
| **Audit** | Track IAM changes, pushes/deletes, policy updates, and deployer identities. |
| **Observability** | Alerts on pull/deploy failures, runtime startup errors, 5xx, and SLOs. |
| **Cost** | Estimate storage/layers/transfer/build/scanning costs; monitor Billing. |

## 17. Official References and Key Takeaways

Repository formats, location availability, service agent identities, and IAM rules may change over time. When deploying on Google Cloud, verify against:

- [Artifact Registry overview](https://cloud.google.com/artifact-registry/docs/overview)
- [Repository types and formats](https://cloud.google.com/artifact-registry/docs/repositories)
- [Create a Docker repository](https://cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Configure authentication for Docker](https://cloud.google.com/artifact-registry/docs/docker/authentication)
- [Push and pull Docker images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Control access with IAM](https://cloud.google.com/artifact-registry/docs/access-control)
- [Artifact Registry cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Deploy images to Cloud Run](https://cloud.google.com/run/docs/deploying)
- [GKE and Artifact Registry image pulling](https://cloud.google.com/artifact-registry/docs/integrate-gke)
- [Vulnerability scanning in Artifact Registry](https://cloud.google.com/artifact-analysis/docs/on-demand-scanning-overview)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- [gcloud artifacts reference](https://cloud.google.com/sdk/gcloud/reference/artifacts)

**Key takeaway:** Artifact Registry manages **where images are stored and distributed**; Docker credentials identify **who is requesting access**; IAM governs **who can pull, push, or administer the repository**; and the GKE/Cloud Run/Compute Engine platform determines **who actually downloads and runs the image**. Combining the right URI, IAM, runtime identity, networking, digest, and CI/CD workflow enables teams to ship a verified container image across multiple environments while preserving auditability, rollback capability, security, and cost control.
