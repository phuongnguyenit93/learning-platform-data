# Image Tags, Digests, and Immutability Policies

> **Chapter:** Containers and Artifact Registry  
> **Module:** CLOUD_PROVIDERS_GCP

A development team packages a Java service into a container image, pushes it to **Artifact Registry**, and deploys it to **Google Kubernetes Engine (GKE)** or **Cloud Run**. During the first release, everything is stable. A week later, the pipeline reuses the `orders-api:production` tag for another build. Some new Pods run the new code while older Pods keep running the old code. The hard question during an incident is: **"Which exact artifact is running?"**

The issue goes beyond Docker image naming. Three mechanisms must be understood:

- An **image tag** is a human-readable name, such as `v1.4.2` or `build-2841-a1b2c3d`. On a default repository, the same tag can point to different images over time.
- An **image digest** is the content identifier of a **manifest** or **image index**, formatted as `sha256:<64 hex chars>`. Referencing by digest identifies the exact artifact to pull, provided it still exists and the caller has access.
- **Immutable image tags** is a Docker-format repository policy in Artifact Registry that prevents an existing tag from pointing to another digest, while also blocking untagging and deleting tagged images.

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage/database services, resource protection, release automation, and reliability and cost tracking. This lesson belongs to the **Containers and Artifact Registry** chapter and focuses on tracing what gets built, stored, and deployed.

**After this lesson, you will be able to:**

1. Read tag-based and digest-based references in Google Artifact Registry accurately.
2. Explain mutable tags, immutable tags, digests, manifests, layers, and multi-platform image indexes.
3. Choose tagging conventions for CI/CD, releases, hotfixes, staging, and production without accidental overwrites.
4. Enable, inspect, and operate **immutable image tags** on a Docker-format standard repository.
5. Use `docker` and `gcloud artifacts` to build, push, list digests, add tags, pull, and test.
6. Pin digests when deploying to GKE or Cloud Run; understand resolution behavior on both platforms.
7. Combine IAM, vulnerability scanning, provenance, Binary Authorization (where appropriate), and cleanup policies.
8. Design rollbacks, monitoring, troubleshooting, and cost optimization without losing release artifacts.

## 1. Artifact Registry Model: Repository, Image, Version, and Tag

**Artifact Registry** manages artifacts such as Docker/OCI container images, Maven/JARs, npm, Python packages, and other formats. A **repository** chooses its format, location, mode, and lifecycle/security policies.

Docker image syntax:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG

Example:
asia-southeast1-docker.pkg.dev/acme-lab-123/orders-repo/orders-api:v1.4.2
\___________________/ \__________/\_________/ \________/ \____/
     registry host       project   repository    image     tag
~~~

The same version can be referenced by **digest**:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:<FULL_HEX_DIGEST>

Illustrative example; digest IS TRUNCATED and CANNOT be used to pull:
asia-southeast1-docker.pkg.dev/acme-lab-123/orders-repo/orders-api@sha256:ab12cd34...
~~~

| Component | Meaning | Example |
| --- | --- | --- |
| Registry host | Docker endpoint and repository location | `asia-southeast1-docker.pkg.dev` |
| Project | Project containing the repository | `acme-lab-123` |
| Repository | Container for multiple image names/versions | `orders-repo` |
| Image name | Collection of versions of one app | `orders-api` |
| Tag | Human-readable label referencing a version | `v1.4.2` |
| Digest | Hash of a manifest or image index | `sha256:...` |
| Layer | Blob containing filesystem changes or image content | Dependencies, JAR... |
| Image version | Manifest/index identified by digest | May have multiple tags or no tags |

**One image version can have multiple tags; a tag points to exactly one image version at a time.** Conversely, an untagged version remains pullable by digest until it is deleted.

### 1.1. Example: Multiple Tags Pointing to One Digest

~~~text
Image: orders-api

Digest D1 = sha256:aaa... (illustrative)
   ├── v1.4.2
   ├── build-a1b2c3d
   └── release-20261119-01

Digest D2 = sha256:bbb... (illustrative)
   ├── v1.5.0-rc1
   └── build-e5f6a7b

Digest D3 = sha256:ccc... (illustrative)
   └── (untagged)
~~~

Multiple tags do not mean multiple independent copies of data. Tags are reference names; the registry manages content blobs/layers under its own storage mechanisms.

### 1.2. Repository Modes

| Mode | Purpose | Scope in this lesson |
| --- | --- | --- |
| **Standard** | Teams push/pull directly | **Primary focus:** tag immutability, retagging, version governance |
| **Remote** | Caches artifacts from upstreams like Docker Hub | Depends on upstream and cache, unlike standard pushes |
| **Virtual** | Aggregated endpoint over upstream repositories | Not a direct push target for release artifacts |

This lab uses a **Docker-format standard repository**. Do not assume every management operation on a standard repository behaves identically on remote or virtual repositories.

## 2. A Tag Is a Reference Name, Not a Content Identifier

In a **mutable-tags** repository:

1. Pipeline builds image A, pushes `orders-api:staging` → tag `staging` points to digest A.
2. Pipeline builds image B, re-pushes `orders-api:staging` → tag is **moved to digest B**.
3. Image A may remain in the registry, becoming **untagged** if no other tag points to it.
4. Machines deploying `:staging` at different times can receive different digests.

~~~mermaid
flowchart LR
    T["Tag staging"] --> A["Digest A\nOld build"]
    PUSH["Push build B with :staging"] -. "Mutable repository" .-> T
    T -. "After push" .-> B["Digest B\nNew build"]
    A -. "May still be stored" .-> OLD["A has not vanished\nStill pullable by digest"]
~~~

### 2.1. The `latest` Tag Does Not Automatically Pick the Newest Build

If a reference omits a tag, Docker workflows implicitly assume `latest`:

~~~bash
docker pull LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api
# Usually equivalent to:
docker pull LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api:latest
~~~

However, `latest` **has no algorithm for finding the highest version**. If a pipeline only pushes `:v2.0.0`, `latest` may still point to an old digest. In an immutable repository, `latest` is **also immutable** and cannot be updated to point to a newer build.

**Never use `latest` as a production release identifier.** Use unique version/build tags for traceability and digests for deployment.

### 2.2. Useful Tagging Conventions

| Tag | Example | Benefit | Limitation |
| --- | --- | --- | --- |
| Semantic version | `v1.4.2` | Easy to match release notes | Must never rebuild and overwrite a published version |
| Commit-derived | `git-a1b2c3d4` | Tied to source | One commit can produce multiple builds/digests |
| CI run/build ID | `build-28451` | Unique per pipeline run | Requires storing provenance to trace source |
| Release ID | `release-20261119-01` | Auditable history | Needs linkage to digest |
| Environment alias | `staging`, `prod` | Convenient when mutable | Unsuitable for immutable pinning |
| `latest` | `latest` | Handy for local trials | Does not prove current release |

**Commit SHA differs from image digest**: a commit hash describes Git source, whereas an image digest describes the built manifest/index. Two builds from the same commit can differ due to base images, dependencies, metadata, timestamps, build args, or CPU architecture.

Good conventions keep **release tags immutable in meaning**, give build tags a **unique build ID**, never place secrets/PII in tags, and never treat a `-prod` suffix as access control or proof of approval.

## 3. What Does an Image Digest Actually Hash?

A **digest** is a content hash—such as SHA-256 of an OCI/Docker manifest or image index. With `orders-api@sha256:...`, clients request a specific manifest/index.

This digest is **not**:

- A hash of the tag name or Git commit.
- Always equal to the local Docker image ID.
- A hash of only one layer, or the entire source tree.
- Proof of authorship, signature, or security scan status.
- A guarantee that the artifact is stored forever.

### 3.1. Manifest, Config, and Layers

~~~mermaid
flowchart TD
    REF["IMAGE@sha256:D_MANIFEST"] --> MAN["OCI image manifest"]
    MAN --> CFG["Config blob\nEntrypoint, env, architecture"]
    MAN --> L1["Layer 1 digest\nBase filesystem"]
    MAN --> L2["Layer 2 digest\nDependencies"]
    MAN --> L3["Layer 3 digest\nApp JAR"]
    TAG["Tag v1.4.2"] -. "Reference name" .-> MAN
~~~

A manifest holds references to the config and layers. Changing any manifest bytes, annotation order, serialization format, or any layer digest changes the **manifest digest**. Docker's local image ID is typically a hash of the config JSON and can therefore **differ** from the registry manifest digest.

### 3.2. Multi-Platform: Index Digest vs. Child Manifest Digest

One tag can point to an **OCI image index / Docker manifest list** supporting multiple architectures:

~~~text
orders-api:v1.4.2
       |
       v
Index digest: sha256:INDEX...
       |
       +-- linux/amd64 -> Manifest digest: sha256:AMD...
       |
       +-- linux/arm64 -> Manifest digest: sha256:ARM...
~~~

When pulling a multi-platform image, the runtime picks the manifest matching its OS/CPU. Therefore:

- **Pinning the image index digest** fixes the set of child manifests listed inside it.
- When investigating a binary on a specific node, record both the **platform** and the **child manifest digest**.
- Scans/provenance/signatures may reference either the index or child manifest depending on the tool; verify exact scope.
- Do not compare an index digest against a child digest and wrongly conclude the image was tampered with.

### 3.3. Build Reproducibility

~~~text
Source commit A -> Build 42 -> Manifest D1
Source commit A -> Build 43 -> Manifest D2 (may differ)
Source commit B -> Build 44 -> Manifest D3

Tag v1.0.0 -> D1
Tag rc-2   -> D2
Deploy IMAGE@D1 -> requests exact D1 while artifact remains available
~~~

Digests lock the **artifact**, not build reproducibility. If reproducible builds are required, control base images by digest, dependencies, toolchains, build args, environment, timestamps, and output comparisons.

## 4. Mutable and Immutable Tags in Artifact Registry

Artifact Registry allows Docker-format repositories to use **mutable** or **immutable image tags**. This setting is a **repository property**, not an arbitrary per-tag flag.

### 4.1. Mutable: Default Behavior

When `Immutable image tags` is **off**, you can:

- Move an existing tag from D1 to D2 when pushing/retagging a new image.
- Untag an image version.
- Delete a tagged image per permissions and confirmation workflow.
- Leave an older image version untagged; it remains pullable by digest until deleted.

Mutable tags support aliases like `dev` or `staging`, but introduce non-reproducible deployment risks.

### 4.2. Immutable: What Gets Blocked

| Operation | Mutable repository | Immutable repository |
| --- | --- | --- |
| Push D1 with new tag `v1` | Allowed | Allowed |
| Push D2 with tag `v1` already pointing to D1 | Moves tag to D2 | **Rejected** |
| Add an **unused** tag to D1 | Allowed | **Allowed** |
| Remove `v1` from D1 | Allowed per permissions | **Rejected** |
| Delete D1 while `v1` is attached | Allowed per permissions/`--delete-tags` | **Rejected** |
| Delete an untagged image version | Allowed | Allowed |
| Move `latest` from D1 to D2 | Allowed | **Rejected** |
| Cleanup policy deletes tagged versions | Allowed if rule matches | **Cannot delete tagged versions** |
| Change repository labels while immutable is on | Allowed per permissions | Restricted per update settings |

**Immutability holds while the policy is active.** Someone with sufficient repository admin permissions can switch the setting back to mutable via `--no-immutable-tags`. This is **not WORM storage or retention lock**. The policy does not stop an administrator from toggling the setting and deleting artifacts.

### 4.3. Why Block Deleting Tagged Images?

An image pinned by digest must **still exist** for GKE scale-outs or new Cloud Run revisions/rollbacks. Blocking deletion of tagged versions helps prevent accidentally deleting an artifact carrying a release tag.

Still, an image can disappear if the repository is deleted, an admin disables immutability before deleting, or an out-of-band admin action occurs. A malicious image pushed with a new tag can also become "immutable." Thus **IAM, scanning, provenance, and auditing** remain mandatory layers.

### 4.4. Updating the Policy on an Existing Repository

~~~bash
# Mutates the repository, affecting all tags:
gcloud artifacts repositories update REPOSITORY \
  --location=LOCATION \
  --project=PROJECT_ID \
  --immutable-tags

# Use only with approval to disable the policy:
gcloud artifacts repositories update REPOSITORY \
  --location=LOCATION \
  --project=PROJECT_ID \
  --no-immutable-tags
~~~

If a pipeline currently reuses `:latest` or deletes tags on every build, enabling immutability will cause the next push or cleanup to fail. That restriction is intentional; **update the pipeline to use unique tags** rather than automatically disabling the policy.

### 4.5. Environment Classification

| Environment | Recommendation | Rationale |
| --- | --- | --- |
| Local developer | Mutable local tags | Fast iteration, unrelated to release registry |
| Dev repository | Can be mutable; unique build tags still preferred | Easy cleanup, controlled risk |
| Staging/release candidate | Unique tags, consider immutable | Reduces artifact confusion across tests |
| Production repository | Immutable tags + tight IAM + deploy by digest | Traceability, prevents accidental retagging/deletion |
| High-assurance | Add attestations, verification, backups | Immutable tags alone do not prove trustworthiness |

When separating dev and release repos, **promote the tested artifact** to the target repository and verify the final digest; copying tools may affect manifests/indexes depending on how they operate.

## 5. Tagging Conventions in CI/CD and Releases

A release pipeline should store **two references**:

1. **Human-readable name:** a unique version/build tag.
2. **Machine-executable identifier:** the manifest/index digest after pushing.

~~~mermaid
flowchart LR
  GIT["Source commit"] --> BUILD["Cloud Build / CI"]
  BUILD --> IMG["Artifact Registry\nUnique build tag"]
  IMG --> DIG["Resolve manifest digest"]
  DIG --> TEST["Scan, test, approval, attestation"]
  TEST --> DEPLOY["Deploy GKE/Cloud Run\nIMAGE@sha256:..."]
  DIG --> RECORD["Release manifest\nCommit + build ID + digest"]
  DEPLOY --> OBS["Logs, errors, rollout/rollback"]
~~~

### 5.1. Recommended Conventions

| Type | Tag | Rule |
| --- | --- | --- |
| CI build | `build-002841-a1b2c3d` | Unique per pipeline run |
| Release candidate | `rc-1.5.0-2` | Never reuse for a new candidate |
| Official release | `v1.5.0` | Applied after approval; meaning never changes |
| Hotfix | `v1.5.1` | **New tag**, never overwrite `v1.5.0` |
| Rollback | **Digest of prior release** | Change deployment config, never move `prod` tag |

**A short commit SHA alone may not be unique** when the same commit is built multiple times. Store Git SHA, CI run ID, digest, timestamp, base image source, and scan/approval results in the release record.

### 5.2. Promotion Without Rebuilding

~~~text
Build 2841 -> orders-api:build-2841-a1b2c3d -> digest D1
       |
       +-- test + scan + release approval
       |
       +-- add tag v1.5.0 to D1 (previously unused tag)
       |
       +-- deploy orders-api@D1
       |
       +-- release record: project/location/repo/name, digest, build, approver
~~~

**Adding a new tag does not rebuild.** As a result, the exact artifact D1 that passed testing is what reaches production. Rebuilding the same commit can yield D2 different from D1 even when the application seems identical.

### 5.3. What If `staging` and `production` Aliases Are Needed?

Immutable repositories do not fit "move `production` to a new image on every deploy." Replace that with:

- GitOps/Kubernetes manifests containing `IMAGE@sha256:...` updated via pull requests.
- A release database mapping `environment → digest` with audit/approvals.
- Cloud Run traffic splitting across **revisions** or application-layer release aliases.
- If mutable aliases are strictly required, keep them in a separate environment/repository and never treat them as release evidence.

## 6. Digests Do Not Replace Supply Chain Security

**Digest pinning** guarantees a specific artifact hash, but does not tell you **who built it, whether it is trustworthy, or whether it has unpatched CVEs**.

| Layer | Objective | Control |
| --- | --- | --- |
| Source control | Who changed the code? | Branch protection, reviews, signed commits if required |
| Build | Which code/deps built the image? | CI logs, provenance, SBOM, pinned base images |
| Artifact storage | Who can push/retag/delete? | Artifact Registry IAM + immutable tags |
| Vulnerability | Any CVEs violating severity policy? | Artifact Analysis/scanning, remediation |
| Authenticity | Built by a trusted pipeline? | Attestations/signatures and verification |
| Deploy approval | Is this digest allowed to run? | Binary Authorization or supported policy gates |
| Runtime | Least-privilege permissions/network? | GKE/Cloud Run IAM, security contexts, network policies |
| Audit/rollback | Which digest runs where? | Release records, GitOps, audit logs, metrics |

### 6.1. What Does a Manifest Digest Protect?

If a client requests manifest D1, altering manifest bytes while claiming digest D1 fails hash verification. That is the strength of **content-addressable identification**.

However, a hash does not prove the source was reviewed, the base image lacks vulnerabilities, the pusher is trusted, or the runtime is securely configured.

### 6.2. Vulnerability Scanning

Artifact Registry integrates with vulnerability scanning/Artifact Analysis per supported modes and enablement conditions. Scans should bind to the **image digest/version**; findings can change over time as CVE feeds update. An artifact that once "passed scan" is not immune to newly disclosed CVEs.

### 6.3. Provenance, Signatures, and Binary Authorization

A deployment control policy might require:

~~~text
Deploy only if:
  - digest D has provenance from an approved CI pipeline;
  - the release repository has appropriate IAM;
  - the image passed scanning and required attestations;
  - the service identity holds least-privilege pull access;
  - deployment manifests pin IMAGE@sha256:D;
  - the change/release record is approved.
~~~

This is a **recommended workflow**, not behavior automatically enabled by `--immutable-tags`. Binary Authorization and signing/verification mechanisms must be configured separately per product, region, and current policy.

### 6.4. Permissions to Modify Immutability

Because an administrator can disable the policy, you should:

- Separate CI service account **Writer** permissions from **Administrator**, granting Admin only to an approved governance group.
- Scope IAM to the exact repository/project needed.
- Monitor Audit Logs for repository setting or IAM changes.
- Never grant `roles/artifactregistry.admin` to a pipeline that only needs to push images.
- Audit repository deletion permissions, backup plans, and recovery capabilities.
- If using perimeters/organization policies, verify they apply to the intended resources.

**Immutable tags are a registry behavior safeguard, not permanent undeletable storage.**

## 7. Lab Setup: Dedicated Release Repository

**Objective:** Create a Docker-format **standard repository** with immutable tags enabled. Build a sample image, push with a new tag, read its digest, attempt pushing a different digest under the **same tag** to verify the registry rejects it, then attach a **new** release tag to the existing version and pull by digest.

**Never run against production or shared repositories.** Create/update/delete commands mutate real resources and may incur charges.

| Value | Example |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Location | `asia-southeast1` |
| Repository | `orders-release-lab` |
| Format/mode | Docker / Standard |
| Policy | Immutable image tags |
| Image name | `orders-api` |
| First tag | `v1.0.0` |
| Second tag | `v1.0.1` |
| Release tag | `release-20261119-01` |

### 7.1. IAM, Networking, and Tools

| Task | Typical role | Principle |
| --- | --- | --- |
| List/pull images, tags, versions | `roles/artifactregistry.reader` | Grant on the exact repository |
| Push images, add tags | `roles/artifactregistry.writer` | Build service account |
| Delete images/untag when policy permits | `roles/artifactregistry.repoAdmin` | Restrict to authorized operators |
| Create/edit immutable setting, cleanup | `roles/artifactregistry.admin` | Infrastructure admin team only |
| Enable Artifact Registry API | Appropriate Service Usage permissions | Project scope |
| GKE/Cloud Run pull | Runtime identity with Reader | Do not confuse with developer workstation rights |

You need an authorized Google Cloud CLI, Docker CLI/daemon or compatible OCI builder, connectivity to `LOCATION-docker.pkg.dev` (private VMs need an approved egress path), valid billing/quotas, and a repository not used by other teams.

Verify first using **read-only** commands:

~~~bash
gcloud config get-value project
gcloud auth list
gcloud artifacts locations list

gcloud artifacts repositories list \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1

gcloud services list --enabled --project=LAB_PROJECT_ID
~~~

If the Artifact Registry API is not enabled, an authorized administrator can enable it in the **lab project**:

~~~bash
# Project-mutating command: run only when approved
gcloud services enable artifactregistry.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

CI that only needs to push **must not hold permission to toggle immutability, delete repositories, or grant IAM**. In multi-project setups, grant Reader to the runtime service identity on the project **hosting the repository**.

## 8. Create an Immutable Repository and Verify

### 8.1. Google Cloud Console

1. Open **Artifact Registry → Repositories** and select the lab project.
2. Click **Create Repository** and enter `orders-release-lab`.
3. Select format **Docker** and repository mode **Standard**.
4. Select location `asia-southeast1` or an authorized region.
5. Enable **Immutable image tags**.
6. Review encryption, vulnerability scanning, IAM, and cleanup as required.
7. Create the repository, reopen its metadata, and verify the setting is enabled.

### 8.2. Creating the Repository with gcloud

~~~bash
# Mutating: creates a test repository; never use in production
gcloud artifacts repositories create orders-release-lab \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Lab immutable image tags" \
  --immutable-tags \
  --project=LAB_PROJECT_ID
~~~

Read back the configuration:

~~~bash
gcloud artifacts repositories describe orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Check the **`dockerConfig.immutableTags`** field in metadata or the Immutable image tags column in the Console. If omitted from a summarized table, inspect full JSON/YAML output before drawing conclusions.

**Limits:** `--immutable-tags` does not sign images, perform vulnerability scanning, prevent admins from altering settings, or turn the repository into WORM storage.

### 8.3. Docker Authentication

~~~bash
# Writes credential helper settings on the practice machine
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
~~~

This configures the credential helper **on the machine running Docker**; it does not grant IAM. If `docker push` returns 403, check the active identity, Writer permission on the right repo, API/network, and CI scope. Never copy service account JSON keys or access tokens into source code to "fix" permission errors.

## 9. Build, Push, and Record the Digest

### 9.1. Small Dockerfile for the Lab

Create a dedicated lab directory containing the following `Dockerfile`:

~~~dockerfile
FROM alpine:3.20

ARG BUILD_MESSAGE=first
LABEL lab.build.message="${BUILD_MESSAGE}"

CMD ["sh", "-c", "echo Immutable tag lab; sleep 3600"]
~~~

This Dockerfile demonstrates producing two builds with distinct metadata and is **not a production image**. The base tag `alpine:3.20` can change over time; real releases require base digest pinning, dependency scanning, minimal images, and SBOM/provenance.

### 9.2. Bash/Cloud Shell Variables

~~~bash
export PROJECT_ID=LAB_PROJECT_ID
export LOCATION=asia-southeast1
export REPO=orders-release-lab
export IMAGE=orders-api

export IMAGE_PATH="${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"
echo "${IMAGE_PATH}"
~~~

In PowerShell, variable syntax and command chaining differ. The examples below assume **Bash**; adapt for your shell.

### 9.3. Build D1, Push `v1.0.0`

~~~bash
# Run inside the directory with the lab Dockerfile
docker build \
  --build-arg BUILD_MESSAGE=first \
  -t "${IMAGE_PATH}:v1.0.0" .

docker push "${IMAGE_PATH}:v1.0.0"
~~~

Because tag `v1.0.0` does not exist yet, the immutable repository accepts the push. Docker prints a digest after pushing; cross-check against Artifact Registry metadata rather than copying an arbitrary layer hash.

### 9.4. Read Digests and Tags in Artifact Registry

~~~bash
# List image names
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Image versions with manifest digests and tags
gcloud artifacts docker images list "${IMAGE_PATH}" \
  --include-tags

# For structured verification/recording workflows
gcloud artifacts docker images list "${IMAGE_PATH}" \
  --include-tags \
  --format=json
~~~

Record the **full 64-hex-character digest**, not just the truncated prefix shown in tables. A release record should capture:

~~~text
Project/repository/location: LAB_PROJECT_ID / orders-release-lab / asia-southeast1
Image name: orders-api
Tag: v1.0.0
Digest: sha256:<FULL_64_HEX>
Commit: <GIT_COMMIT>
Build run: <CI_RUN_ID>
Builder: <SERVICE_IDENTITY>
Test/scan result: <LINK_OR_ID>
Approval: <CHANGE_REQUEST>
~~~

**Never substitute a truncated hash, local Docker image ID, or Git commit SHA for the registry manifest digest.**

### 9.5. Docker Pull and `RepoDigests`

~~~bash
docker pull "${IMAGE_PATH}:v1.0.0"

docker image inspect "${IMAGE_PATH}:v1.0.0" \
  --format='{{json .RepoDigests}}'
~~~

`RepoDigests` shows the `repo@digest` references known to the Docker daemon. For multi-platform images, the index digest and platform-specific manifest digest can differ; record the exact identifier used by your deployment platform.

## 10. Test Pushing a Duplicate Tag to Prove Immutability

### 10.1. Build D2 with the Same `v1.0.0` Tag

~~~bash
# Build a local image with a different label from D1
docker build \
  --build-arg BUILD_MESSAGE=second \
  -t "${IMAGE_PATH}:v1.0.0" .

# Expected to FAIL because remote tag v1.0.0 is already bound to D1
docker push "${IMAGE_PATH}:v1.0.0"
~~~

**Expected outcome:** The registry rejects the push because immutable tags forbid moving `v1.0.0` from D1 to D2. D1 in the registry is not overwritten.

- The **local** image tagged `v1.0.0` now points to D2; do not confuse local with **remote**.
- If the push somehow succeeded, check whether the two images genuinely had different digests and whether the policy is actually enabled.
- Never disable the policy just to make a test pass.
- Re-pushing the **exact same digest** does not demonstrate moving a tag to a new version.

### 10.2. Push D2 Under a New Tag

~~~bash
# Assign a new tag to local image D2
docker tag "${IMAGE_PATH}:v1.0.0" "${IMAGE_PATH}:v1.0.1"

# Tag v1.0.1 is unused, so D2 can be pushed
docker push "${IMAGE_PATH}:v1.0.1"

# Verify both versions
gcloud artifacts docker images list "${IMAGE_PATH}" --include-tags
~~~

Expected:

~~~text
:v1.0.0 -> D1
:v1.0.1 -> D2
~~~

**Lesson:** Every hotfix or rebuild producing a new digest must use a **new tag** when the image lives in an immutable repository. Update pipelines to use unique build IDs instead of aliases like `:latest`/`:prod`.

### 10.3. Post-Test Questions

1. Does building D2 locally alter the remote tag? **No**.
2. Is pushing D2 with an unused tag allowed? **Yes**, if IAM, quotas, and other policies allow it.
3. Does D1 vanish when D2 is pushed? **Not automatically**.
4. To deploy D1, what should you use? **Digest D1** or a verified immutable tag.
5. Should you disable immutability to fix a "tag exists" error in production? **No**; create a new tag and fix the release workflow.

## 11. Adding a New Release Tag to a Verified Digest

Once D1 passes integration tests and security gates, attach a human-readable release tag. **Do not rebuild** from the same source and treat the new image as the tested artifact.

### 11.1. Add a Tag from an Existing Tag

~~~bash
# Registry tag mutation; target tag MUST NOT already exist:
gcloud artifacts docker tags add \
  "${IMAGE_PATH}:v1.0.0" \
  "${IMAGE_PATH}:release-20261119-01"
~~~

The syntax is `gcloud artifacts docker tags add IMAGE_VERSION TARGET_TAG`, where `IMAGE_VERSION` accepts a **tag or full digest**. In production pipelines, reference the source digest that cleared release gates:

~~~bash
# Syntax example; replace FULL_64_HEX_DIGEST with the real digest
gcloud artifacts docker tags add \
  "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST" \
  "${IMAGE_PATH}:release-20261119-01"
~~~

This contains a **placeholder** and cannot run verbatim without a valid digest. An **unused** tag can be added to D1 in an immutable repository. If `release-20261119-01` already pointed to D2, moving it to D1 will be rejected.

### 11.2. Verify Release Tags

~~~bash
gcloud artifacts docker images list "${IMAGE_PATH}" --include-tags
gcloud artifacts docker tags list "${IMAGE_PATH}"
~~~

In the Console, open Repositories → image → version list and inspect both **Tags** and **Image digest**. Verify `v1.0.0` and `release-20261119-01` both point to D1, rather than trusting a "release" tag name alone.

### 11.3. Pull Exactly by Digest

~~~bash
# Executable only after replacing with the real digest from Artifact Registry
docker pull "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST"
~~~

If the image exists and IAM/networking are valid, Docker requests that exact manifest/index. Future deployments still require the registry to **retain the artifact**; digest pinning does not guarantee an image stays pullable forever.

### 11.4. Freezing Evidence Beyond the Tag

The release record should capture: full digest-based image URI, human tag, Git commit, build ID, test/scan evidence, SBOM, signing/attestation reference, approver, environment, and timestamp. That forms the authoritative record of "what was approved," rather than a tag string alone.

## 12. Deploying to GKE by Digest

Kubernetes natively supports digest-based image references:

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
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/orders-release-lab/orders-api@sha256:FULL_64_HEX_DIGEST
          ports:
            - containerPort: 8080
~~~

The manifest above is for learning only; placeholder digests **cannot be deployed**. Production workloads need resource requests/limits, probes, `securityContext`, `serviceAccount`, secret delivery, and network policies.

### 12.1. Risk When Kubernetes Uses Mutable Tags

Suppose a Deployment sets `image: orders-api:v1.0.0` in a mutable repository:

1. Pod A is scheduled at 09:00 and pulls digest D1.
2. A pipeline accidentally pushes digest D2 under the same tag at 09:10.
3. Pod B is scheduled during scale-out at 09:15 and may pull D2.
4. Two Pods in the **same Deployment with the exact same image string** now run different artifacts.

With `orders-api@sha256:D1`, new Pods explicitly request D1. This is why Google Cloud recommends **image digests** for stable, reproducible deployments.

### 12.2. `imagePullPolicy` Does Not Replace Digests

Kubernetes provides values such as `Always` and `IfNotPresent`:

- With mutable tags, `Always` makes the node resolve/pull the tag at container creation; `IfNotPresent` may reuse a cached image.
- With digest references, both still point to the **same artifact identity**, provided the object still exists.
- Running Pods do not automatically swap images when a registry tag changes; a managed rollout/restart/replacement is required.
- A node holding a cached image does not prove a **new** node can pull it if the image was deleted from the repository.

**Do not use `latest` and expect `Always` to keep all replicas on the same version.** Manage rollouts explicitly.

### 12.3. Inspecting Pod Image Digests

~~~bash
# Read-only; select the right cluster context and namespace
kubectl get deployment orders-api -n NAMESPACE -o yaml
kubectl get pods -n NAMESPACE -l app=orders-api -o wide

kubectl get pods -n NAMESPACE -l app=orders-api \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.name}{": "}{.imageID}{"\n"}{end}{end}'
~~~

When reading `imageID`, the container runtime may report the **platform-specific child digest** rather than the image index digest. Check OS/architecture, manifest list, and source digest before assuming the image changed.

### 12.4. Rolling Out a New Digest

~~~bash
# Mutates the Deployment; run only when approved
kubectl set image deployment/orders-api \
  orders-api=LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api@sha256:FULL_NEW_DIGEST \
  -n NAMESPACE

kubectl rollout status deployment/orders-api -n NAMESPACE
~~~

In a GitOps model, update manifests/Helm values in Git with the **vetted digest** so controllers apply changes with an audit trail. Rollbacks likewise select the prior release digest rather than moving a `:production` tag.

### 12.5. Runtime Identity and Pull Permissions

The node/identity pulling the image must have read access to the Artifact Registry repository, typically `roles/artifactregistry.reader` on the target repository. For **cross-project pulls**, permissions in the GKE project do not automatically grant access in the image project; verify the service account/node identity and grant permissions at the proper scope. Missing permissions trigger `ErrImagePull` or `ImagePullBackOff` even when the digest is completely valid.

## 13. Cloud Run: Image Tags Are Resolved at Revision Deploy Time

Cloud Run allows deploying by tag or exact digest. One crucial difference: when deploying by **tag**, Cloud Run **resolves the tag to a digest at deploy time**, and the **created revision uses the resolved digest**. Later changes to that tag **do not silently mutate running revisions into another image**.

~~~mermaid
flowchart LR
  T["Deploy orders-api:v1.0.0"] --> RES["Cloud Run resolves tag"]
  RES --> D1["Revision R1: digest D1"]
  NEXT["Deploy orders-api@D2"] --> D2["Revision R2: digest D2"]
  D1 --> TRAF["Traffic routing between revisions"]
  D2 --> TRAF
~~~

### 13.1. Illustrative Deploy by Digest

~~~bash
# CREATES/UPDATES a Cloud Run service; execute only in a lab project
gcloud run deploy orders-api \
  --image=LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/orders-api@sha256:FULL_64_HEX_DIGEST \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --no-allow-unauthenticated
~~~

**Important:** the lab Alpine Dockerfile only runs `sleep`—it is not a web server conforming to the **Cloud Run container runtime contract**. Do not expect this lab image to serve HTTP on Cloud Run; substitute a real application image listening on the proper port/host with readiness handling.

### 13.2. Why Still Pin Digests If Cloud Run Locks Revisions?

- Re-running deploy commands with a **mutable tag** at a later time can create a new revision with a different digest.
- Release evidence must prove the tested artifact and deployed artifact are **identical**.
- Comparing rollbacks/incidents is cleaner when release records use full digests.
- External CD tools, promotion workflows, or deploy scripts may not share Cloud Run's resolution rules.

### 13.3. Proper Rollback at the Cloud Run Layer

Rollbacks typically route traffic back to a known revision or redeploy an approved digest—**without** modifying tags in Artifact Registry.

Verify database schemas, secrets, environment config, IAM, and external dependencies expected by the older revision. **Immutable revisions do not mean systems outside the revision are immutable.** The revision's image digest must also remain in the registry for related deploy/pull operations.

## 14. A Controlled Build → Verify → Deploy Pipeline

### 14.1. Cloud Build with a Unique Build Tag

Example `cloudbuild.yaml` in a **separate** practice project:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders-release-lab/orders-api:build-$BUILD_ID
      - .
images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders-release-lab/orders-api:build-$BUILD_ID
~~~

Cloud Build provides substitutions such as `$PROJECT_ID` and `$BUILD_ID` in the build context. The reference uses a **unique build ID** rather than overwriting `:latest`. In real builds, verify the build service account has push access **on the repository**, read access to base images/dependencies, and passes security checks.

**Never auto-deploy just because `docker build` succeeded.** Once the image is pushed, the pipeline should fetch the **full digest from Artifact Registry**, verify the tag/build/version, store provenance, run tests/scans, check approvals, and only then update deployments by digest. That step is described conceptually because parsing digests from Cloud Build outputs/JSON depends on your CI tooling and artifact mode.

### 14.2. Separating Build Pipelines and Release Pipelines

| Stage | Input | Output / Check |
| --- | --- | --- |
| Checkout source | Commit SHA, branch policy | Reviewed source |
| Build | Source + pinned dependencies | OCI manifest/index digest D |
| Push | Unique build tag | Version D in Artifact Registry |
| Verify | D + build metadata | Scan/SBOM/provenance/attestations |
| Approve | Evidence and release request | Authorization for D in target environment |
| Promote | Approved D | New release tag or artifact copy with digest verification |
| Deploy | **Repo/image@D** | GKE Deployment / Cloud Run revision |
| Observe | Requests/errors/SLOs | Go/no-go, rollback |
| Retain | Release metadata | Keep policy + ensuring D remains pullable |

If promoting across repositories changes the digest, **re-scan/re-verify the destination digest**, attach corresponding evidence, and ensure the release record does not store only the source digest.

### 14.3. Avoiding TOCTOU During Tag Resolution

*Time-of-check/time-of-use* occurs when you "test a tag yesterday, deploy the tag today," yet the mutable tag shifted in between.

~~~text
Wrong:
  Test :staging -> D1
  Someone else re-pushes :staging -> D2
  Deploy :staging -> D2

Better:
  Test digest D1
  Approve D1
  Deploy IMAGE@sha256:D1
~~~

Immutable tags reduce the chance of tag movement while enabled, yet **digest pinning** provides stronger proof at the deployment boundary and does not rely on future repository setting assumptions.

### 14.4. Practical Hotfixes and Rollbacks

Suppose production runs D1/`v1.5.0` and a bug is found:

1. Create a hotfix from source, run a new CI build → D2/`build-2842`.
2. Scan/test D2, apply a **new** `v1.5.1` tag—never overwrite `v1.5.0`.
3. Deploy D2 following your rollout strategy.
4. On failure, revert to **D1** via GitOps/Cloud Run traffic or deployment approval.
5. Verify state/schema backward compatibility and real user behavior.

**Rollback ≠ retagging `v1.5.0` to D2 or deleting D2 to force the runtime onto D1.** Artifacts and release history must remain intact and traceable.

## 15. Controlling IAM, Service Identities, and Private Access

### 15.1. Right Identity for the Right Action

Within one system, roles may include:

- **Developer:** reads/inspects images, or pushes to a dev repository.
- **CI build service account:** Writer on build/release repositories per workflow.
- **Release approver/service account:** sufficient permissions to add **new tags** or promote artifacts, without blanket project administration.
- **GKE node / Cloud Run service agent / runtime identity:** appropriate image pull permissions.
- **Repository administrator:** modifies immutable settings, IAM, and cleanup policies upon approval.
- **Security reviewer:** views digests, scan reports, and audit logs without delete rights.

A "Permission denied" on `docker push` typically points to **Writer**, whereas `ImagePullBackOff` points to **Reader/runtime identity**, networking, or a wrong name/digest. Never resolve both with broad Owner permissions.

### 15.2. Shared VPC and Multi-Project Environments

Example:

~~~text
Project A: shared-artifacts
  └── Artifact Registry: orders-release-lab (immutable)

Project B: staging-cluster
  └── GKE cluster: pulls digest D

Project C: production-service
  └── Cloud Run service: deploys digest D
~~~

Reader permission must be granted on the repository in **Project A** to the service identities actually performing pulls. Granting Reader only in Project B/C **is not necessarily sufficient**. Also verify network reachability to the registry hostname and Private Google Access/Private Service Connect/NAT if workloads live in private subnets.

### 15.3. Never Put Credentials Inside Images

Never add JSON keys, access tokens, or Docker credentials into image layers or Dockerfile `ARG`/`ENV` instructions where they persist in history. When builds need secrets, use proper CI/build secret mechanisms and inspect layers/provenance.

**Immutable tags cannot erase secrets baked into an image.** If an image containing a secret is accidentally released, revoke/rotate credentials, audit access, follow incident response procedures, and handle the artifact per approval—never wait for a new tag to magically fix a leak.

### 15.4. IAM and Trust Boundaries When Changing Policies

Disabling immutable tags is a **critical governance action**, as it reopens tag movement and deletion of tagged artifacts. You should:

- Restrict `roles/artifactregistry.admin` to authorized personnel/processes.
- Require change approval, auditing, and clear business justification.
- Prefer **creating a new tag** rather than disabling immutability to fix a release.
- Alert on and review Audit Logs whenever repository policies change.
- Periodically audit IAM drift and service account keys.

## 16. Cleanup Policies: Why Do Immutable Tags Affect Cost?

**Artifact Registry cleanup policies** automatically retain or delete artifact versions based on **age, tag state, prefixes, and version count**. However, when a repository **enables immutable tags**, **tagged image versions cannot be deleted** by cleanup policies. This is an important trade-off between preserving release history and reducing storage costs.

### 16.1. Untagged Versions vs. Tagged Versions

~~~text
Mutable repository:
  :staging -> D1
  Push D2 with :staging
  :staging -> D2
  D1 becomes untagged and eligible for cleanup once conditions match

Immutable repository:
  :v1.0.0 -> D1
  :v1.0.1 -> D2
  Cannot untag or move tags.
  Cleanup rule "Delete tagged" CANNOT delete D1/D2.

Untagged version in an immutable repo:
  Eligible for cleanup when policy conditions match.
~~~

Enabling immutable tags does not protect every artifact indefinitely; **untagged versions can still be deleted**. Conversely, tagged versions can accumulate for years if teams attach a release tag to every CI run.

### 16.2. Cleanup Policy Attributes

| Attribute | Example | Notes |
| --- | --- | --- |
| Tag state | `tagged`, `untagged`, `any` | Immutable repos block deleting tagged versions |
| Tag prefix | `release`, `rc`, `build` | Meaningful only when matching the right tags |
| Package prefix | `orders-` | Distinct from the full registry URI |
| Version prefix | `v1` | Distinguish version name from tag |
| Version age | `olderThan: 30d` | Not the age of the source commit |
| Keep most recent | `keepCount: 5` | Keeps the newest versions per scope |
| Dry run | Test policy | Runs in the background; does not output an immediate full list |

Cleanup policies primarily target supported **standard repositories**; they do not automatically apply identically to virtual repositories or remote repository upstream caches.

### 16.3. Example JSON for the Lab Repository

Keep **at least the 5 newest versions** of each package and delete **untagged** versions older than 30 days unless protected by a keep rule:

~~~json
[
  {
    "name": "delete-untagged-after-30d",
    "action": { "type": "Delete" },
    "condition": {
      "tagState": "untagged",
      "olderThan": "30d"
    }
  },
  {
    "name": "keep-latest-five",
    "action": { "type": "Keep" },
    "mostRecentVersions": {
      "keepCount": 5
    }
  }
]
~~~

This is an illustrative configuration for `cleanup-lab.json` on a **lab machine**. Keep rules protect matching versions; immutable tags continue blocking deletion of tagged versions.

### 16.4. Dry Run Before Enabling Real Deletion

~~~bash
# Updates cleanup policy settings; DRY RUN only, deletes no artifacts
gcloud artifacts repositories set-cleanup-policies orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --policy=cleanup-lab.json \
  --dry-run
~~~

Dry run still updates the **repository configuration**, even without deleting artifacts. Artifact Registry evaluates policies via a periodic background job, typically taking roughly **one day** to show results. Viewing dry-run audit events may require enabling **Artifact Registry Data Access / Data Write logs** and holding log-read permissions.

Apply live deletion only after reviewing results and securing approval:

~~~bash
# OPERATION CAN DELETE ARTIFACTS: run only after review/approval
gcloud artifacts repositories set-cleanup-policies orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --policy=cleanup-lab.json \
  --no-dry-run
~~~

**Image deletion cannot be undone by changing the cleanup policy.** Never put `--no-dry-run` into a production pipeline until artifact owners confirm retention and rollback windows.

### 16.5. Blocked Tag Deletion and Image Deletion

Suppose the immutable repo holds `v1.0.0`:

~~~bash
# Illustrative syntax; EXPECTED to fail due to immutable policy
gcloud artifacts docker tags delete "${IMAGE_PATH}:v1.0.0"

# EXPECTED to be rejected: image still has tags in an immutable repo
gcloud artifacts docker images delete \
  "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST" \
  --delete-tags
~~~

The `--delete-tags` flag is **not a way to bypass immutability**. When finite retention is required, design your repository layout and governance up front before creating hundreds of thousands of release tags.

### 16.6. Separating Repositories to Manage Cost

| Repository | Usage | Retention |
| --- | --- | --- |
| `orders-dev` | Experimental builds, mutable tags as needed | Delete untagged/old dev versions per policy |
| `orders-candidate` | RCs with unique tags | Retain during testing window |
| `orders-release` | Approved releases, immutable | Retain tagged images for audit/rollback needs |
| `orders-archive` | Long-term archival artifacts | Dedicated DR/backup/provenance policies |

A policy to "Delete tagged releases after 90 days" **cannot execute while immutable tags remain enabled**. That constraint must be decided at design time, not patched mid-flight when storage bills climb.

## 17. Observability and Total Cost

### 17.1. Signals to Track

| Signal | Goal |
| --- | --- |
| Versions per image | Spot unexpected growth in release repositories |
| Tagged/untagged counts | Assess cleanup feasibility |
| Storage bytes and cost | Track by location/repository and over time |
| Docker push failures | Catch tag collisions and IAM issues |
| Pull failures / 404s | Detect missing Reader roles or deleted versions |
| Repository setting changes | Alert on disabled immutability or broadened IAM |
| Scan/provenance results | Support security gates |
| CI run → digest mapping | Distinguish multiple builds from the same commit |
| GKE `imageID`s / Cloud Run revisions | Reconcile runtime artifacts with release records |
| Cleanup dry-run logs | Inspect versions at risk of deletion |

### 17.2. Costs That Can Accrue

Artifact Registry can bill for storage of manifests/layers/packages, network transfer, vulnerability scanning, and related services. CI/Cloud Build, audit logs, and monitoring carry their own charges. When an image version is deleted, **unreferenced layers do not necessarily vanish immediately**; the registry garbage-collects data periodically.

Do not equate "500 tags" with "500 full filesystem copies": layers can be shared. Still, **500 immutable tagged versions can grow storage and block cleanup from removing them**, especially when every build creates fresh application layers. Monitor **billed bytes** and use Cloud Billing Reports/Budgets rather than estimating from tag counts alone.

### 17.3. Why Retain Release Evidence?

Six months after an incident, SREs need to know: production digest, prior digest, CI run, source commit, build config, pushing identity, scan/attestations, approver, deployment events, and artifact path.

If you keep only the digest string while the **image bytes were deleted from the registry**, you cannot pull the image back from the hash alone. Retention must ensure images survive throughout rollback, forensic, and compliance windows.

## 18. Common Issue Diagnostic Table

| Symptom | Common cause | Check / Resolution |
| --- | --- | --- |
| Push fails with `tag immutability enabled` | Tag already points to another version | Use a new unique tag; do not disable policy |
| Push fails with `permission denied` / 403 | Missing Writer or wrong repo/project | Check identity, IAM scope, API/network |
| Docker reports `unauthorized` | Invalid credential helper/token | Configure the right registry host; avoid long-lived keys |
| Push succeeds but tag not visible | Wrong location/repository/image name | Check full URI and `--include-tags` |
| Pull by digest fails with `manifest unknown` | Wrong digest, deleted artifact, or wrong path | Check full hash and version existence |
| Pulling `:latest` gets an older build | `latest` does not auto-update | Pin digests and new versions |
| Cannot delete tag | Blocked by immutable policy | Redesign retention; do not force-delete |
| `--delete-tags` still fails | Tagged images cannot be deleted when immutable is on | Cannot be bypassed via flag |
| Cleanup does not delete tagged images | Immutable protection or keep rule | Inspect dry-run logs and policy |
| GKE `ImagePullBackOff` | Reader, path, network, or architecture | Check Pod events, runtime service identity, registry |
| Pods in same Deployment run different digests | Mutable tag, staggered pulls/caching | Pin digest, run controlled rollouts |
| Cloud Run revision unchanged after retag | Revision locks digest at deploy time | Deploy a new revision or adjust traffic routing |
| Image runs wrong architecture | Multi-arch index missing matching child manifest | Check platform/architecture |
| Digest differs from local image ID | Manifest hash differs from config hash | Compare matching digest types |
| Repo is immutable yet artifact untrusted | Immutable tags are not scanning/provenance | Enforce verification gates |
| Cross-project pull 403 | Reader missing on repo in artifact project | Grant permission on the exact repo to the service identity |
| Cannot roll back | Old digest deleted or incompatible schema | Retention, DR, and rollback plans |

### 18.1. Layered Diagnostic Flow

~~~mermaid
flowchart TD
  S["Push/Pull/Deploy failure"] --> URI["Verify full project/repo/image/tag/digest"]
  URI --> K{"Push or pull error?"}
  K -- "Push" --> P{"Tag already exists in immutable repo?"}
  P -- "Yes" --> TAG["Use a new tag; do not move old tag"]
  P -- "No" --> IAM["Check Writer/API/credentials/quotas"]
  K -- "Pull" --> V{"Version still exists?"}
  V -- "No" --> RET["Check cleanup/retention or wrong URI"]
  V -- "Yes" --> READER["Check Reader, egress, runtime architecture"]
  TAG --> TEST["Verify digests, release evidence, and retry"]
  IAM --> TEST
  RET --> TEST
  READER --> TEST
~~~

**Never blindly open public IAM, delete all tags, or turn off immutability** just to make CI turn green again.

## 19. Case Study: Releasing a Java API Across GKE and Cloud Run

**Context:** A company operates a Java ordering API, with staging on GKE and production on Cloud Run. Images are built from Git via CI and stored in Artifact Registry. Security requires knowing **the exact reviewed binary** and supporting reliable rollbacks.

A reference workflow:

~~~text
Source commit: a1b2c3d
CI run: build-2841
Build repository:
  orders-api:build-2841-a1b2c3d -> digest D1

CI:
  unit/integration/security/contract tests -> approve D1

Promotion to release repository (immutable):
  orders-api:v1.6.0 -> digest D1'
  (must verify D1' in destination registry; may differ from D1 if manifest changes)

Staging GKE:
  image = release-repo/orders-api@D1'

Production Cloud Run:
  revision from release-repo/orders-api@D1'

Release record:
  Git SHA + build ID + destination digest + evidence + approval
~~~

### 19.1. Why Not Rebuild When Promoting?

If production rebuilds from the same commit after the base image changed, the output can become D2 even though staging tested D1. **Promoting the verified artifact** preserves artifact identity. If a copy tool alters the manifest/index digest across repos, document and re-verify the destination digest and evidence rather than using tags to mask differences.

### 19.2. Hotfixes and Rollbacks

When D1 has a bug, create a new hotfix build → D2, run scans/tests, apply a **new release tag**, and deploy D2 by digest. On failure, revert configuration/traffic to D1 per change approval. Never retag `v1.6.0` to D2 or delete D2 to "force" the runtime onto D1.

Rollbacks also depend on data, schema migrations, secrets, IAM, and external dependencies—not just swapping an image string.

## 20. Review Exercises and Guiding Answers

1. **Is a tag a digest?** No. A tag is a mutable reference; a digest identifies a manifest/index.
2. **Are two tags on the same digest two different image binaries?** No. They may simply be two names for one version.
3. **Can two builds from the same Git commit have different digests?** Yes, due to changing build inputs/metadata.
4. **Once immutability is on, can you push D2 with a tag D1 already uses?** No, when the digest differs.
5. **Can you add an unused tag to D1?** Yes, in a standard repository with appropriate permissions.
6. **Does `latest` automatically point to the newest version?** No.
7. **Does immutability stop an Admin from disabling the policy?** No. IAM/auditing/change control are still needed.
8. **Does digest pinning by itself guarantee zero CVEs?** No. Scanning and provenance are still required.
9. **Can GKE Pods sharing a mutable tag run different digests?** Yes.
10. **Does a running Cloud Run revision change automatically when a mutable tag updates?** No; revisions resolve tags to digests at deploy time.
11. **Is a multi-platform index digest differing from a child digest a sign of tampering?** Not by default; they are hashes of different objects.
12. **Will a cleanup rule deleting tagged items older than 30d delete tagged images in an immutable repo?** No.
13. **When hitting `ImagePullBackOff`, should you disable immutability?** No; check IAM/URI/network/digest/platform.
14. **Can a release record holding only a digest restore an image after deletion?** No; artifact bytes must be retained.
15. **Is replacing D1 with hotfix D2 by re-pushing `v1.0.0` valid?** Not in an immutable workflow; use a new tag and deploy D2 by digest.

### Self-Assessment Exercise

Fill in the table after completing the lab:

| Question | Result to record |
| --- | --- |
| Does the repository have immutability enabled? | `dockerConfig.immutableTags` field or Console |
| Which digest does `v1.0.0` point to? | Full digest D1 |
| Did pushing D2 with `v1.0.0` succeed? | No, if D2 differs from D1 |
| Pushing D2 with `v1.0.1`? | Succeeds when permissions/config are valid |
| Which digest does the new release tag point to? | Same D1 |
| Did pulling by digest succeed? | Yes, if artifact/identity/network are valid |
| Do D1/D2 differ in manifest hash? | Verified from registry |
| Can tagged versions be cleaned up while immutable? | No |
| What will GKE/Cloud Run runtimes use? | Exact approved release digest |

## 21. Production Readiness Checklist

- [ ] Confirmed correct project, location, repository mode, and format.
- [ ] Verified image tag policy on the release repository.
- [ ] CI uses unique tags and never reuses `latest`, `staging`, or released versions.
- [ ] Release records store full manifest/index digests rather than commit SHAs or truncated digests.
- [ ] Multi-platform images checked for platform/child manifests where needed.
- [ ] Tests/scans/provenance/approvals bound to the exact digest.
- [ ] Promotion does not rebuild tested artifacts; destination digests verified.
- [ ] GKE uses `IMAGE@sha256:FULL_DIGEST` in manifests/GitOps.
- [ ] Cloud Run release records bind to revisions and resolved digests.
- [ ] Runtime identities hold Reader on the right repo, including cross-project.
- [ ] CI Writer lacks unnecessary admin/delete rights.
- [ ] Auditing alerts on repository immutability or IAM changes.
- [ ] Cleanup policies dry-run tested, accounting for tag immutability and keep rules.
- [ ] Release retention covers rollback/incident/DR windows.
- [ ] Reviewed storage, egress, scanning, CI, and logging costs.
- [ ] Runbooks exist for tag collisions, 403, `ImagePullBackOff`, and `manifest unknown`.
- [ ] Never disable immutability as a quick fix for a bad release.

## 22. Cleaning Up Lab Resources and Deletion Limits

If you created a **dedicated repository** `orders-release-lab` for this lesson, inspect its contents and confirm **no GKE/Cloud Run service references its images**. Tagged versions in an immutable repository cannot be deleted individually while the policy remains active.

~~~bash
# Read-only checks before deciding on cleanup
gcloud artifacts repositories describe orders-release-lab \
  --location=asia-southeast1 --project=LAB_PROJECT_ID

gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/LAB_PROJECT_ID/orders-release-lab/orders-api \
  --include-tags
~~~

If the **entire repository** is strictly your own lab data, past its retention need, and authorized for cleanup, an administrator can delete the repository. This is a **different destructive action** from deleting one tagged version; never use it to bypass production retention.

~~~bash
# DESTROYS the entire lab repository; run only after verifying ownership
gcloud artifacts repositories delete orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

A deleted image can break future pulls, scale-outs, redeployments, or rollbacks. Never assume `kubectl rollout undo` or `git revert` can recover bytes once an artifact is gone.

## 23. Official Google Cloud Documentation

CLI syntax, feature support, and pricing models may change. When deploying in practice, cross-check these references:

- [Artifact Registry: Container concepts](https://docs.cloud.google.com/artifact-registry/docs/container-concepts) — versions, manifests, layers, tags.
- [Repository and image names](https://docs.cloud.google.com/artifact-registry/docs/docker/names) — tag/digest reference syntax.
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos) — Docker repositories, `--immutable-tags`.
- [Update repository settings](https://docs.cloud.google.com/artifact-registry/docs/repositories/update-repo-settings) — enabling/disabling immutable policies.
- [Manage images](https://docs.cloud.google.com/artifact-registry/docs/docker/manage-images) — list, tag, untag, delete.
- [Push and pull images](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling) — build/push/pull and authentication.
- [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control) — Reader/Writer/Admin roles.
- [Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy) — Delete/Keep/dry run and immutability.
- [Troubleshoot container image issues](https://docs.cloud.google.com/artifact-registry/docs/docker/troubleshoot) — errors, permissions, pull issues.
- [About container image digests in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-container-images) — benefits of digest pinning.
- [Deploy container images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying) — revisions resolving tags to digests.
- [Artifact Analysis](https://docs.cloud.google.com/artifact-analysis/docs/overview) — vulnerabilities/metadata.
- [Binary Authorization](https://docs.cloud.google.com/binary-authorization/docs/overview) — deploy admission.
- [Cloud Build: build container images](https://docs.cloud.google.com/build/docs/building/build-containers) — CI/build/push.
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) — storage and data transfer.

**Key takeaway:** **Tags** are reference names, **digests** are manifest/index identities, and **immutable tags** are repository policies blocking tag movement and tagged-image deletion while enabled. Reliable releases **build once, verify by digest, apply unique release tags, and deploy by digest**, while governing IAM, provenance, scanning, cleanup, costs, and rollback readiness.
