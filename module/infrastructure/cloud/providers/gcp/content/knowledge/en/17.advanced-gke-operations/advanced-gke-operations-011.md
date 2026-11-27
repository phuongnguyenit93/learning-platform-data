# Binary Authorization and GKE Workload Policies

## Learning Objectives

After this lesson, you will be able to:

1. Explain how **Binary Authorization** (BinAuthz) controls *which images can be deployed* on Google Kubernetes Engine (GKE), and distinguish it from IAM, Kubernetes RBAC, and Pod Security Admission.
2. Understand **image digests**, **attestors**, **attestations**, **Artifact Analysis notes**, and the roles of Cloud Build, Artifact Registry, and Cloud KMS in the software supply chain.
3. Configure a **project-singleton policy** using **ALWAYS_ALLOW**, **ALWAYS_DENY**, **REQUIRE_ATTESTATION**, **DRYRUN_AUDIT_LOG_ONLY**, and **ENFORCED_BLOCK_AND_AUDIT_LOG**.
4. Practice enabling enforcement on a cluster, exporting/importing policies, testing blocked Pods vs. attested Pods, and using audited breakglass in emergencies.
5. Distinguish **deploy-time enforcement** from **Continuous Validation (CV)** on running Pods, including scanning scope limits and CV's Preview status.
6. Design a least-privilege CI/CD workflow for Java apps on GKE with rollback, monitoring, and cost controls.

## 1. Why Do Workloads Need Pre-Execution Policies?

In the **CLOUD_PROVIDERS_GCP** module, a platform spans projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases. A Java app may pass tests, build into a container image, and push to **Artifact Registry**. Yet a developer permitted to create Deployments in the cluster could still specify an unvetted external image unless image checks run at deploy time.

For example, a store's production cluster should only run images that:

- Were built by an approved pipeline.
- Passed security/release verification.
- Reference an immutable **sha256 digest** matching the approved release.

**Binary Authorization** is an *admission* control gate: it inspects PodSpec images against a **policy** before allowing Pods using those images to deploy. It does not scan binaries for malware on its own, replace application testing, or grant Artifact Registry pull access.

~~~mermaid
flowchart LR
    SOURCE["Git commit"] --> BUILD["Cloud Build<br/>build + test + scan"]
    BUILD --> REG["Artifact Registry<br/>image@sha256:digest"]
    BUILD --> APPROVE["Security/release approver<br/>attestation"]
    APPROVE --> NOTE["Artifact Analysis<br/>note / occurrence"]
    REG --> DEPLOY["GKE Deployment"]
    DEPLOY --> GATE{"Binary Authorization<br/>enforcement policy"}
    NOTE --> GATE
    GATE -->|Valid| POD["Pod created"]
    GATE -->|Invalid| DENY["Rejected + Audit Log"]
~~~

### GKE Policy Is Not a Single Layer

| Layer | Question | Illustrative tools |
|---|---|---|
| **Identity** | Who can deploy or call the GKE API? | Google Cloud IAM, Kubernetes RBAC |
| **Image admission** | Is this image approved for deployment? | **Binary Authorization** |
| **Pod security** | Does the container run privileged, with `hostPath`, or as root? | Pod Security Admission, Policy Controller/Gatekeeper |
| **Runtime** | Are running images still policy-compliant? | **Binary Authorization CV**, Cloud Logging/Monitoring |
| **Data/API access** | Which secrets, buckets, or databases can the Pod read? | Workload Identity Federation for GKE, IAM, NetworkPolicy |

Because each layer mitigates a different risk, **BinAuthz does not replace** least-privilege RBAC, vulnerability scanning, network isolation, or runtime hardening.

## 2. Key Concepts to Distinguish

| Component | Role | Do not confuse with |
|---|---|---|
| **Container image** | Package of code and dependencies run by a container | Git source code or a Kubernetes Deployment |
| **Tag** (e.g., `orders:1.2.0`) | Mutable name that can be repointed to another image | Immutable content identifier |
| **Digest** (`sha256:...`) | Content-addressable identifier of an image manifest | Hash of a standalone JAR file |
| **Attestor** | Authority verifying signatures for an approval stage | A user with Artifact Registry Writer IAM |
| **Attestation** | Signed record tied to an image digest representing process approval | Automatic proof the image has zero vulnerabilities |
| **Artifact Analysis note** | Root metadata object defining an attestation kind | A copy of an image blob |
| **Occurrence** | Attestation record attached to a specific image | Deployment allow policy |
| **Project-singleton policy** | Project-wide deploy-time enforcement rule set | CV platform policy |
| **CV platform policy** | Check-based policy monitoring images in running Pods | Admission rule blocking new Pods |

**Illustrative digest-pinned image reference:**

~~~text
asia-southeast1-docker.pkg.dev/shop-prod-001/containers/orders-api@sha256:<64-hex-chars>
~~~

The string above is a placeholder, not a real digest; replace it with the actual digest from your registry or build output. Pin digests in production manifests to prevent tag mutation attacks. An attestation verifies a **digest**, not a mutable tag name.

### What Does an Attestation Mean?

Suppose security signs only when source is reviewed, unit/integration tests pass, vulnerability gates accept remaining risk, and the release owner approves. The attestation then serves as **cryptographic proof that the approval workflow ran**. If the signer or pipeline is compromised, a valid signature can still accompany a malicious image. Protecting **signing keys and attestation permissions** is just as critical as enforcing the admission gate.

## 3. How Deploy-Time Enforcement Evaluates Policy

Each project has **one** Binary Authorization **project-singleton policy**. GKE clusters with enforcement enabled in that project evaluate against that policy, honoring cluster/namespace/service-account rules where configured.

### 3.1. Evaluation Mode vs. Enforcement Mode

| Field | Value | Behavior |
|---|---|---|
| `evaluationMode` | **ALWAYS_ALLOW** | Permits images matching the rule scope |
| `evaluationMode` | **ALWAYS_DENY** | Marks images matching the rule scope as non-compliant |
| `evaluationMode` | **REQUIRE_ATTESTATION** | Requires valid attestations verified by **all attestors** in `requireAttestationsBy` |
| `enforcementMode` | **DRYRUN_AUDIT_LOG_ONLY** | **Does not block**, but logs violations to Cloud Audit Logs |
| `enforcementMode` | **ENFORCED_BLOCK_AND_AUDIT_LOG** | Blocks violating deployments and logs them |

These two fields are **independent**: `ALWAYS_DENY` paired with **dry-run** still permits Pods to deploy while logging impact; switching to **enforced** blocks them. Conversely, `ALWAYS_ALLOW` paired with `ENFORCED_BLOCK_AND_AUDIT_LOG` still lets every image through—a common misunderstanding.

### 3.2. Default Policy Is Not "Trusted Images Only"

When a project is created, the default Binary Authorization policy looks like:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: ALWAYS_ALLOW
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
~~~

Thus **enabling Binary Authorization on a cluster without updating the policy still allows every application image**. Define your own rules and soak them in dry-run mode before blocking production.

### 3.3. Policy Evaluation and Exemptions

| Policy field | Meaning |
|---|---|---|
| `defaultAdmissionRule` | Applies when no more specific rule matches |
| `clusterAdmissionRules` | Per-cluster rule keyed by **`LOCATION.CLUSTER_NAME`**; overrides default rule when matched |
| `kubernetesNamespaceAdmissionRules` | Rule scoped to a GKE namespace |
| `kubernetesServiceAccountAdmissionRules` | Rule scoped to a Kubernetes ServiceAccount, keyed by **`NAMESPACE:SERVICE_ACCOUNT`** |
| `admissionWhitelistPatterns` | Exemption list by image path/pattern |
| `globalPolicyEvaluationMode: ENABLE` | Evaluates Google's system policy to exempt Google-managed system images |

Namespace and KSA rules help when staging and production share a project, though **separating projects by trust boundary** is preferred whenever possible. Never assume all rules AND together; they follow rule-selection semantics, so inspect the exported policy and test thoroughly.

**Keep `globalPolicyEvaluationMode: ENABLE`** in most GKE clusters. Disabling it can cause platform updates to block GKE system images unless admins maintain a manual system allowlist.

### 3.4. Exempt Images Can Punch Holes in Your Policy

Example allowlist:

~~~yaml
admissionWhitelistPatterns:
  - namePattern: asia-southeast1-docker.pkg.dev/shop-prod-001/approved-system-images/**
~~~

This pattern **widens exemptions**; restrict it to paths with clear ownership. A `**` wildcard matches more subpaths than `*`. Never add `**` across an entire project or a public registry just to clear a deployment error.

## 4. Limitations and Enforcement Timing to Remember

**BinAuthz enforcement checks at deploy time, not continuously every second.**

- If a policy switches from allow to deny today, **already-running Pods are not terminated**. New or recreated Pods are evaluated at admission.
- Per current GKE documentation, deploy-time enforcement inspects images in **`containers`** and **`ephemeralContainers`** of PodSpec; **it does not check `initContainers` or image volumes at deploy time**. Never treat BinAuthz as inspecting every image field in a Pod.
- **Continuous Validation** can inspect **init and ephemeral container** images while monitoring running Pods; CV only **logs violations and does not kill Pods**.
- An image passing BinAuthz can still develop new CVEs, leak secrets, or run with unsafe Pod security settings.
- If the Binary Authorization backend becomes unreachable, **fail-open** behavior can occur and is recorded in audit logs. Never claim "BinAuthz always fails closed during every outage."

**Operational takeaway:** pair BinAuthz with **Pod Security Admission / Policy Controller**, image vulnerability scanning, least-privilege IAM, auditing, and CV where appropriate. <https://docs.cloud.google.com/binary-authorization/docs/setting-up>

## 5. Preparing a Safe Practice Setup

Example **lab** project values (all placeholders):

| Attribute | Value |
|---|---|
| Project | **shop-dev-001** |
| GKE cluster | **gke-release-lab** |
| Region | **asia-southeast1** |
| Artifact Registry | **asia-southeast1-docker.pkg.dev/shop-dev-001/containers** |
| Attestor | **release-approver** |
| Artifact Analysis note | **release-note** |
| Cloud KMS key | **global/release-ring/release-signing** |
| Namespace | **shop** |

Note: enabling GKE, Artifact Registry, Cloud KMS, logging, and Binary Authorization can incur charges. **Never practice in production**, and never import a restrictive policy before backing up the existing policy. This lab illustrates commands without creating live resources.

### 5.1. Check Context and Enable APIs

~~~bash
gcloud config get-value project
gcloud auth list
gcloud container clusters list --project=shop-dev-001
gcloud artifacts repositories list --project=shop-dev-001 \
  --location=asia-southeast1

# Modifies project; run only with assigned permissions.
gcloud services enable binaryauthorization.googleapis.com \
  containeranalysis.googleapis.com \
  cloudkms.googleapis.com \
  --project=shop-dev-001
~~~

Viewing and editing policies require Binary Authorization roles such as **`roles/binaryauthorization.policyViewer`** or **`roles/binaryauthorization.policyEditor`**. Permissions to update GKE clusters, grant IAM, create attestors, sign with KMS, and push images are **distinct**—never grant Owner just to follow a lab.

### 5.2. Inspect Policy and Back Up the Original

~~~bash
gcloud container binauthz policy export \
  --project=shop-dev-001 > policy-original.yaml

gcloud container clusters describe gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(name,binaryAuthorization)"
~~~

`policy-original.yaml` is an export for review and rollback in your lab environment, not a file stored in the learning repository. If the existing policy contains rules for multiple clusters, preserve unrelated rules during edits.

### 5.3. Enable Enforcement on the Lab Cluster

~~~bash
gcloud container clusters update gke-release-lab \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE
~~~

This modifies the cluster; allow a few minutes for enforcement to propagate. If the cluster already uses **Continuous Validation**, use **`POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE`** and retain existing policy bindings—picking enforcement-only **disables CV**.

## 6. Designing a Two-Phase Enforcement Policy

### 6.1. Phase 1 — Dry-Run to Measure Impact

Once an attestor exists (section 7), sample policy file:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
~~~

**Explanation:** unattested images within scope are still **allowed to deploy**, while violations are written to audit logs. Do not leave dry-run as a permanent production control.

To test:

~~~bash
# Review policy diff before importing.
gcloud container binauthz policy import policy-dryrun.yaml \
  --project=shop-dev-001

gcloud container binauthz policy export --project=shop-dev-001
~~~

**Import overwrites the project-singleton policy**, affecting all enforcement-enabled clusters in that project. Use an isolated lab project, change tracking, and backups; commands here illustrate the workflow.

### 6.2. Phase 2 — Enforce Once All Releases Are Signed

Keep the rest of the policy intact, changing only:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
~~~

Edit the **complete** policy file (retaining `name`, `globalPolicyEvaluationMode`, and required rules) before importing:

~~~bash
gcloud container binauthz policy import policy-enforced.yaml \
  --project=shop-dev-001
~~~

**Never save only the `defaultAdmissionRule` snippet and import it**: the import expects the full policy schema. When a rule lists **two attestors**, both must attest the exact image digest—not "either one."

### 6.3. Cluster-Specific Rule for Production

Abbreviated example keeping staging audit-only while production blocks:

~~~yaml
name: projects/shop-dev-001/policy
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
  requireAttestationsBy:
    - projects/shop-dev-001/attestors/release-approver
clusterAdmissionRules:
  asia-southeast1.gke-release-lab:
    evaluationMode: REQUIRE_ATTESTATION
    enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
    requireAttestationsBy:
      - projects/shop-dev-001/attestors/release-approver
~~~

**A matching cluster rule replaces the default rule** rather than running both. This helps when multiple clusters share a project with different needs, though separating environments into distinct projects still offers cleaner governance and isolation.

## 7. Creating an Attestor, Signing Key, and Attestation

An **attestor** without a public key cannot verify signatures. **Cloud KMS** is recommended for protecting private signing keys; never store signing keys inside Git repositories, container images, or shared CI workers.

### 7.1. Create an Artifact Analysis Note

Commands below target **Cloud Shell/Bash** (do not run verbatim in PowerShell with the same syntax):

~~~bash
# Contents of note-payload.json (contains no private key):
cat > note-payload.json <<'EOF'
{
  "name": "projects/shop-dev-001/notes/release-note",
  "attestation": {
    "hint": {"human_readable_name": "Approved production release"}
  }
}
EOF

curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-binary @note-payload.json \
  "https://containeranalysis.googleapis.com/v1/projects/shop-dev-001/notes/?noteId=release-note"
~~~

Binary Authorization uses the **global Artifact Analysis API endpoint** for these notes rather than a regional endpoint. The caller needs permission to create Artifact Analysis notes; this mutating step belongs strictly in the lab project.

### 7.2. Create an Attestor Referencing the Note

~~~bash
gcloud container binauthz attestors create release-approver \
  --project=shop-dev-001 \
  --attestation-authority-note=release-note \
  --attestation-authority-note-project=shop-dev-001

gcloud container binauthz attestors describe release-approver \
  --project=shop-dev-001
~~~

### 7.3. Create an Asymmetric Key in Cloud KMS

~~~bash
gcloud kms keyrings create release-ring \
  --project=shop-dev-001 \
  --location=global

gcloud kms keys create release-signing \
  --project=shop-dev-001 \
  --location=global \
  --keyring=release-ring \
  --purpose=asymmetric-signing \
  --default-algorithm=ec-sign-p256-sha256 \
  --protection-level=software
~~~

A new **key version** is typically `1`, though always verify from command output. In production, restrict **KMS signing** strictly to the approved release pipeline; anyone editing BinAuthz policy should not automatically have permission to sign images.

### 7.4. Register the Public Key on the Attestor

~~~bash
gcloud container binauthz attestors public-keys add \
  --project=shop-dev-001 \
  --attestor=release-approver \
  --keyversion-project=shop-dev-001 \
  --keyversion-location=global \
  --keyversion-keyring=release-ring \
  --keyversion-key=release-signing \
  --keyversion=1

gcloud container binauthz attestors describe release-approver \
  --project=shop-dev-001
~~~

The attestor uses the public key for verification while the private key stays in Cloud KMS. In multi-project architectures, configure IAM for **attestors/notes/occurrences** per official multi-project guidance; never assume a cluster project's service agent can read security resources in another project automatically.

### 7.5. Sign the Exact Image Digest After Testing

Suppose CI built and pushed the Java app image. Fetch the **actual digest** from Artifact Registry or build metadata and inspect it:

~~~bash
gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/shop-dev-001/containers \
  --include-tags \
  --project=shop-dev-001
~~~

Once you confirm the image URL in the form `.../orders-api@sha256:<actual-digest>`, set `IMAGE_TO_ATTEST` to that exact string:

~~~bash
IMAGE_TO_ATTEST="asia-southeast1-docker.pkg.dev/shop-dev-001/containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST"

# SIGNING and creating attestation; run ONLY after release approval:
gcloud container binauthz attestations sign-and-create \
  --project=shop-dev-001 \
  --artifact-url="$IMAGE_TO_ATTEST" \
  --attestor=release-approver \
  --attestor-project=shop-dev-001 \
  --keyversion-project=shop-dev-001 \
  --keyversion-location=global \
  --keyversion-keyring=release-ring \
  --keyversion-key=release-signing \
  --keyversion=1

gcloud container binauthz attestations list \
  --project=shop-dev-001 \
  --attestor=release-approver \
  --attestor-project=shop-dev-001 \
  --artifact-url="$IMAGE_TO_ATTEST"
~~~

The signing command does not run tests, scans, or approval checks itself: **your pipeline and approvers must enforce those gates before signing**. Passing an unreplaced placeholder fails; never deploy placeholders to production.

**Chain of custody:**

~~~text
CI builder (push image) → Security/release approver (decision)
 → KMS signer (sign digest) → Artifact Analysis attestation
 → GKE Binary Authorization (verify signature per policy)
~~~

### 7.6. The `built-by-cloud-build` Attestor

Google Cloud also offers the **`built-by-cloud-build`** attestor to deploy images attested automatically by Cloud Build in supported flows. It is simpler than managing a custom signer, yet **"built by Cloud Build" does not mean security-approved**. For high-risk workloads, require an independent **`release-approved`** attestor or enforce provenance and vulnerability checks per organizational policy.

## 8. Testing Admission and Inspecting Pods

### 8.1. Deployment Using an Immutable Digest

The following manifest intentionally contains a placeholder shorter than 64 hex characters:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
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
      serviceAccountName: orders-ksa
      containers:
        - name: orders-api
          image: asia-southeast1-docker.pkg.dev/shop-dev-001/containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
~~~

The Java app must implement `/actuator/health/readiness` and reference a real digest; this sample demonstrates policy wiring and **will not run until placeholders are replaced**. Passing BinAuthz never guarantees the readiness probe succeeds or the Pod has enough RAM/CPU.

### 8.2. Positive and Negative Tests

~~~bash
gcloud container clusters get-credentials gke-release-lab \
  --project=shop-dev-001 \
  --region=asia-southeast1

kubectl config current-context
kubectl get namespace shop

# Apply only after inserting a real digest and configuring permissions.
kubectl apply -f orders-deployment.yaml
kubectl get deployment orders-api -n shop
kubectl get pods -n shop
kubectl get events -n shop --sort-by=.lastTimestamp
~~~

Evaluate at least four test cases:

| Case | Expected outcome under enforced `REQUIRE_ATTESTATION` |
|---|---|
| Valid image digest, signed by attestor | **Pod admitted**; other Kubernetes rules still apply |
| Same image, **different unattested digest** | **Blocked at admission** |
| Attested digest, KSA lacks Cloud Storage IAM | **BinAuthz allows Pod to start**, but Storage calls fail with `403` |
| Signed image, Pod violates Pod Security Admission | **Blocked by Pod Security**, not BinAuthz |

When blocked, look for messages like `imagepolicywebhook.image-policy.k8s.io` or `Denied by attestor`. Distinguish admission denials from **`ImagePullBackOff`** (which happens *after* Pod creation and points to image URLs, registry reachability, or pull IAM).

### 8.3. Do Not Equate `kubectl apply` Success with Running Pods

`kubectl apply` on a **Deployment** can succeed because the API server stores the Deployment object, while its ReplicaSet fails to create Pods due to admission webhook rejections. Always inspect:

~~~bash
kubectl describe deployment orders-api -n shop
kubectl get replicaset -n shop
kubectl describe replicaset -n shop
kubectl get events -n shop --sort-by=.lastTimestamp
~~~

Because **no Pod is created**, `kubectl logs` on a nonexistent Pod will not help. Inspect **ReplicaSet events** and **Cloud Audit Logs** instead.

## 9. Continuous Validation (CV): Monitoring Running Pods

**Continuous Validation** using **check-based platform policies** is currently **Preview** per Google Cloud documentation and differs completely from the deploy-time policy in section 6.

| Feature | Deploy-time enforcement | CV |
|---|---|---|
| Policy | **Project-singleton policy** | One or more **platform policies** |
| Timing | When images are submitted in a Pod/deployment | Periodically evaluates running Pods |
| On violation | Blocks or dry-runs per `enforcementMode` | **Logs violations to Cloud Logging; never kills Pods** |
| Image scope | `containers`, `ephemeralContainers`; skips init/image volumes at deploy time | Inspects **`init` and `ephemeral` containers** during checks |
| Policy updates | Primarily affects new deployments | Detects running Pods that fell out of compliance |
| Maturity | GA enforcement model | Check-based CV **Preview** |

CV evaluates Pods at least every **24 hours**; short-lived Pods may emit logs after exiting. CV **never terminates runtime workloads immediately** when vulnerabilities or policy drift appear.

Documented supported checks include **trusted directory, image freshness, vulnerability, simple signing attestation, Sigstore signature, and SLSA/provenance**. Availability, quotas, and prerequisites vary by feature.

### 9.1. Sample CV Platform Policy

File **`cv-policy.yaml`** illustrates checks requiring both a trusted directory and images uploaded within 30 days:

~~~yaml
gkePolicy:
  checkSets:
    - displayName: Company image quality
      checks:
        - displayName: Trusted Artifact Registry directory
          trustedDirectoryCheck:
            trustedDirPatterns:
              - asia-southeast1-docker.pkg.dev/shop-dev-001/containers
        - displayName: Image freshness
          imageFreshnessCheck:
            maxUploadAgeDays: 30
~~~

The 30-day rule here is purely illustrative; for long-term supported releases, requiring every image to be under 30 days old creates alert noise without valid exemptions.

### 9.2. Creating a Platform Policy via Beta CLI

~~~bash
gcloud beta container binauthz policy create cv-review \
  --platform=gke \
  --policy-file=cv-policy.yaml \
  --project=shop-dev-001

gcloud beta container binauthz policy describe cv-review \
  --platform=gke \
  --project=shop-dev-001
~~~

Unlike **`gcloud container binauthz policy import`** in section 6, this creates a **named CV platform policy** without altering the project-singleton enforcement policy.

### 9.3. Enabling CV Without Accidentally Disabling Enforcement

~~~bash
# Run ONLY when authorized to update the cluster.
gcloud beta container clusters update gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --binauthz-evaluation-mode=POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE \
  --binauthz-policy-bindings=name=projects/shop-dev-001/platforms/gke/policies/cv-review
~~~

**Warning:** passing `--binauthz-evaluation-mode=POLICY_BINDINGS` **turns off project-singleton enforcement**, leaving only CV monitoring. Passing `PROJECT_SINGLETON_POLICY_ENFORCE` alone can turn off existing CV bindings. Always read back the evaluation mode and bindings after updating so neither policy gets dropped.

~~~bash
gcloud container clusters describe gke-release-lab \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(binaryAuthorization)"
~~~

CV logs provide evidence for security/ops to **file tickets, block future releases, rebuild images, and roll out fixes**—they never remediate Pods automatically. Legacy continuous validation using the project-singleton policy is **deprecated**; use **check-based platform policies** for new setups.

## 10. Breakglass in Emergencies

If an urgent production hotfix lacks an attestation during a severe outage, GKE offers a **breakglass** label to bypass **BinAuthz enforcement** for that Pod. It is an **audited emergency escape hatch**, not a fix for flaky release pipelines.

### 10.1. Exact Label and Placement in a Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: emergency-hotfix
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: emergency-hotfix
  template:
    metadata:
      labels:
        app: emergency-hotfix
        image-policy.k8s.io/break-glass: "true"
    spec:
      containers:
        - name: hotfix
          image: asia-southeast1-docker.pkg.dev/shop-dev-001/containers/hotfix@sha256:REPLACE_WITH_REAL_DIGEST
~~~

**The label must be inside `spec.template.metadata.labels` of the Pod template**, not only on `Deployment.metadata.labels`. A Pod carrying `image-policy.k8s.io/break-glass: "true"` bypasses BinAuthz enforcement and generates a breakglass audit event **even if the image would otherwise pass policy**.

### 10.2. Mandatory Runbook When Using Breakglass

1. Incident commander confirms the outage and verifies no faster approved path exists.
2. Review the image digest, build origin, and blast radius; never deploy an unverified image just because it is an emergency.
3. Only authorized operators may add the label; monitor breakglass events immediately.
4. Apply strictly to the affected workload, recording **ticket, approver, digest, timestamp, and justification**.
5. Once the release is properly attested, roll out a clean deployment **without the breakglass label**.
6. Review audit logs, cross-check CV findings, and complete a postmortem.

**Note:** anyone permitted to create Pods in the cluster can potentially attach a breakglass label. Enforce **RBAC, admission policies, and alerting** to prevent abuse. Breakglass bypasses Binary Authorization only—it does not bypass IAM, Pod Security Admission, Artifact Registry pull permissions, or network policies.

## 11. Audit Logs, Alerts, and Responding to Violations

GKE records BinAuthz events in **Cloud Audit Logs**, including **blocked deployments, breakglass, dry-run violations, and fail-open**. CV writes violations to **Cloud Logging** in its own log stream.

### 11.1. Viewing Blocked Deployment Events

Illustrative Logs Explorer filter:

~~~text
resource.type="k8s_cluster"
logName:"cloudaudit.googleapis.com%2Factivity"
(protoPayload.methodName="io.k8s.core.v1.pods.create" OR
 protoPayload.methodName="io.k8s.core.v1.pods.update")
protoPayload.response.status="Failure"
(protoPayload.response.reason="VIOLATES_POLICY" OR
 protoPayload.response.reason="Forbidden")
~~~

Depending on cluster version and event details, `reason` values can vary. Open a sample log entry to inspect the principal, resource, image reference, and rejected rule/attestor.

### 11.2. Monitoring Breakglass, Dry-Run, and Fail-Open

| Type | Useful log marker | Response |
|---|---|---|
| **Breakglass** | `image-policy.k8s.io/break-glass` | Verify incident ticket, approver, Pod, and exception expiration |
| **Dry-run** | `imagepolicywebhook.image-policy.k8s.io/dry-run` | Measure impact before switching to enforce |
| **Fail-open** | `image-policy.k8s.io/failed-open`, `imagepolicywebhook.image-policy.k8s.io/failed-open`, or variants | Assess risk while the validation backend was briefly unavailable |
| **CV violation** | Check-based platform policy logs | Identify Pod/image/failing check, file a ticket, and roll out a fix |

Example querying breakglass events over the past week:

~~~bash
gcloud logging read \
  'resource.type="k8s_cluster" AND "image-policy.k8s.io/break-glass"' \
  --project=shop-dev-001 \
  --freshness=7d \
  --order=desc \
  --limit=50
~~~

**Never treat "no logs found" as absolute proof of zero violations.** Check project ID, time window, Logs Viewer permissions, log exclusions, logging settings, and filter syntax before concluding.

### 11.3. Operational Dashboard

Signals to measure:

- Share of **deployments blocked by BinAuthz** out of total deployments.
- **Breakglass** event count and duration of active exceptions.
- **Fail-open** and dry-run violations by cluster/namespace/team.
- **CV findings** by image digest, check type, and severity.
- Time from build to attestation, and releases delayed by missing signatures.
- **Pod rollout readiness**, error rates, and rollback duration to gauge user SLO impact.

Pair alerts with owners and runbooks instead of auto-killing every Pod flagged by CV: a CV finding may call for risk triage, rebuilding, or a scheduled safe rollout.

## 12. Separation of Duties and Supply Chain Security

### 12.1. Never Let the Same Principal Edit Policy and Sign Releases

| Principal / group | Required permissions | Should NOT automatically hold |
|---|---|---|
| **Build runner** | Read source, build/test, push to Artifact Registry | Edit BinAuthz policy, unilaterally sign releases |
| **Security/release approver** | Sign via KMS and create attestations within approved scope | Arbitrarily alter images post-signing |
| **Platform policy admin** | Binary Authorization Policy Editor, rule reviews | Broad KMS signing permissions |
| **GKE deployer** | Update Kubernetes workloads via IAM/RBAC | Artifact Registry Admin or KMS sign |
| **GKE image pull identity** | Artifact Registry Reader | Signing or policy-editing rights |
| **Auditor** | Policy Viewer, Cloud Logging Viewer | Override or alter gates |

For **Cloud KMS asymmetric signing**, the signing principal needs `cloudkms.cryptoKeyVersions.useToSign` via an appropriate role on the specific key. Creating attestations also requires permissions on Artifact Analysis occurrences and related resources; in multi-project topologies, BinAuthz's service agent needs read access to attestors/notes/occurrences per official docs.

### 12.2. Registry, Signatures, and Admission Are Three Distinct Boundaries

- **Artifact Registry IAM:** who can push/pull images.
- **KMS/attestor:** who can cryptographically sign approval for an image digest.
- **BinAuthz policy:** which signatures GKE trusts at deployment time.

If an image is deleted or the node pull identity lacks permissions, Pods hit **`ImagePullBackOff`** even after passing BinAuthz. Conversely, having pull access without an attestation gets blocked at admission. Fix each failure at its proper layer.

### 12.3. Strengthening GKE Policy Posture

Combine:

1. **Pin image digests** for deterministic rollouts.
2. **Vulnerability scanning, SBOMs, and build provenance**, signing only when criteria pass.
3. **Pod Security Admission** or **Policy Controller** for `privileged`, `hostPath`, capabilities, resource limits, or registry rules.
4. **Workload Identity Federation for GKE** so Java apps read Cloud Storage / Secret Manager without static keys.
5. **NetworkPolicy, private clusters/VPC, and least-privilege IAM** to contain compromised containers.
6. **Backups and rollback capability** for services and data; BinAuthz cannot recover an app after a buggy rollout.

For **Cloud Run**, Binary Authorization also integrates, yet **service configuration syntax and deployment workflows differ from GKE**—never run `gcloud container clusters update` commands for Cloud Run.

## 13. Common Issues and How to Distinguish Them

| Symptom | Possible cause | Check next |
|---|---|---|
| BinAuthz enabled, unvetted images still run | Policy still on `ALWAYS_ALLOW` or `DRYRUN` | Export policy; inspect evaluation/enforcement modes |
| Pod blocked with `Denied by attestor` | Digest lacks attestation or signer/public key mismatch | `attestations list`, `attestors describe`, exact digest |
| Attestation exists, deployment still blocked | Policy requires **multiple** attestors, wrong cluster rule, or digest mismatch | `requireAttestationsBy`, `clusterAdmissionRules`, exact digest |
| Image tag `v1` deploys wrong build | Tag moved or build/push race | Pin digest; inspect registry manifest |
| Deployment created, Pods never appear | ReplicaSet rejected by admission webhook | `kubectl describe rs`, Events, Cloud Audit Logs |
| Pod created, enters `ImagePullBackOff` | Node/pull identity lacks Artifact Registry Reader or missing digest | `kubectl describe pod`, registry IAM |
| Pods running before policy tightened stay up | Enforcement runs mainly at new deployments | CV, plan controlled rollout/replacement |
| CV logs errors while Pod stays up | **CV never terminates Pods** | Identify failing check and ship a fix through release pipeline |
| Enabling CV disables enforcement | Passed `POLICY_BINDINGS` instead of combined mode | Describe cluster evaluation mode |
| Cluster/system workloads fail after policy edit | Disabled `globalPolicyEvaluationMode` or missing system allowlist | Roll back policy; re-enable system policy |
| Cannot query attestations | Missing cross-project read access to Artifact Analysis/attestors | Service agent IAM, attestor note/resource |
| Attestation signing fails on KMS | Missing `useToSign`, wrong key version, or disabled key | KMS IAM, algorithm, signing key state |
| Missing breakglass audit event | Wrong log filter/project/time or label not on Pod template | `image-policy.k8s.io/break-glass`, Pods, Cloud Audit Logs |
| `initContainer` not blocked at deploy time | **Documented scope limit of deploy-time enforcement** | Pod Security / Policy Controller and CV |
| Fail-open event logged | BinAuthz backend unavailable/timed out | Inspect control health; audit admitted Pods |

### 13.1. Ordered Diagnostic Workflow

1. Check **`kubectl get events`** and `describe deployment/replicaset/pod` to see if Pods were ever created.
2. If rejected at admission, verify **policy project**, **cluster evaluation mode**, **matching rule**, and **attestor list**.
3. Compare the manifest's `@sha256:...` digest against the **attestation artifact URL**—not just the tag.
4. Check attestor public keys, KMS key versions, and Artifact Analysis permissions if signing or verification fails.
5. If Pods were created yet fail pull/runtime, troubleshoot **Artifact Registry, node identity, Kubernetes scheduling, and Java app logs**.
6. Query Cloud Audit Logs for breakglass, dry-run, or fail-open events.
7. Update policy only after impact review; test on staging and promote to production under change control.

## 14. End-to-End Scenario: Java E-Commerce Platform

Company **Thinh An** runs:

- `orders-api`, `payment-adapter`, and `inventory-worker` on **GKE**, built via Cloud Build.
- Images in **Artifact Registry**; transactional data in **Cloud SQL**; product images in **Cloud Storage**.
- Production clusters enforce BinAuthz; test clusters use dry-run during transition.
- An independent security team holds the **Cloud KMS signing key**; the platform team manages policies.

### 14.1. Controlled Release Flow

~~~mermaid
flowchart TB
    A["Commit + review"] --> B["Cloud Build: tests + SBOM + scan"]
    B --> C["Push image to Artifact Registry"]
    C --> D["Capture immutable digest"]
    D --> E["Release approval / KMS attestation"]
    E --> F["GKE deploy by digest"]
    F --> G{"BinAuthz admission"}
    G -->|Pass| H["Rollout + readiness + SLOs"]
    G -->|Fail| I["Block + Audit Log + ticket"]
    H --> J["CV: monitor running images"]
    J -->|Finding| K["Investigation + fix release"]
~~~

### 14.2. Phased Policy Selection

| Phase | Enforcement | CV | Gate to advance |
|---|---|---|---|
| **Staging** | `REQUIRE_ATTESTATION + DRYRUN` | Optional Preview testing in lab | Zero false positives blocking valid pipelines |
| **Canary production** | `REQUIRE_ATTESTATION + ENFORCED` on selected cluster/path | Check-only per policy | Rollouts unblocked; readiness passes |
| **Steady production** | Enforced across approved workload scope | Track violations and check findings | All new images digest-pinned & attested; on-call/rollback ready |
| **Emergency incident** | Breakglass only with approver and audit | CV keeps logging findings | Remove breakglass label once hotfix is signed |

### 14.3. Availability and Cost Considerations

- **SLOs:** missing attestations can block scale-outs, rolling updates, or self-healing after node failures if new Pods are rejected. Ensure deployed images stay attested and pullable.
- **Reliability:** pair multi-replica Deployments, readiness probes, PodDisruptionBudgets, and digest rollbacks; BinAuthz cannot make a Java API survive a Cloud SQL outage.
- **Cost:** account for GKE/Artifact Registry, Cloud KMS signing ops, Artifact Analysis/attestation storage, Binary Authorization service, logging/monitoring, and scanning per current pricing. **CV Preview** carries its own pricing/availability terms—never assume unverified flat rates.
- **Operations:** log policy versions and image digests in release records, and restrict policy changes during peak traffic windows.

## 15. Exercises and Guided Answers

### Exercise A — Distinguish Dry-Run and Enforce

Given the policy:

~~~yaml
defaultAdmissionRule:
  evaluationMode: ALWAYS_DENY
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY
~~~

**Question:** will a non-exempt Pod be blocked? **Answer:** not by this rule, because dry-run permits deployment while logging the violation. Switching to `ENFORCED_BLOCK_AND_AUDIT_LOG` blocks it.

### Exercise B — Digest vs. Attestation

Image `orders-api:v2` pointed to digest **A** when signed; later, the publisher repoints tag `v2` to digest **B**. Policy requires attestor `release-approver`.

**Question:** is image B automatically approved? **Answer:** no. An attestation on digest A does not cover B. Pin digests in manifests and verify attestations for the exact deployed image.

### Exercise C — Two Attestors

Rule:

~~~yaml
evaluationMode: REQUIRE_ATTESTATION
enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
requireAttestationsBy:
  - projects/shop-dev-001/attestors/ci-build
  - projects/shop-dev-001/attestors/security-approved
~~~

**Question:** is having only the `ci-build` attestation enough? **Answer:** no; valid attestations are required from **all** listed attestors. Missing any one violates the rule.

### Exercise D — Symptom After Enabling CV

An engineer updates a GKE cluster with:

~~~text
--binauthz-evaluation-mode=POLICY_BINDINGS
~~~

**Question:** what can go wrong? **Answer:** this mode enables only CV monitoring and can **accidentally disable project-singleton enforcement**. To keep both active, use `POLICY_BINDINGS_AND_PROJECT_SINGLETON_POLICY_ENFORCE` and preserve policy bindings.

### Exercise E — Pod with an Untrusted `initContainer`

**Question:** does deploy-time enforcement guarantee blocking an untrusted image in `initContainers`? **Answer:** no; GKE docs state deploy-time enforcement checks only `containers` and `ephemeralContainers`. Layer Kubernetes/Pod Security controls and CV monitoring where supported.

### Exercise F — Emergency Hotfix

A production outage needs an immediate hotfix. The image is built, yet the attestation pipeline is delayed. Ops wants to add `image-policy.k8s.io/break-glass: "true"`.

**Write a checklist:** who approves, which digest, blast radius, who may edit the Pod template, where logs appear, and when to strip the label and re-sign. **Guidance:** use breakglass only with approval, ticket, monitoring, and an expiration timeline; place the label on the **Pod template**, not solely on Deployment metadata.

### Exercise G — Designing Policies for Two Teams

The payment team requires a **security attestation**, while the reporting team only requires build origin during a pilot phase.

**Task:** propose partitioning via projects/clusters/namespaces/KSAs, signer IAM, dry-run/enforce policies, and negative tests. **Guidance:** separate trust boundaries where feasible, avoid overly broad exemptions, never let build runners sign with security's key, and run negative attestor/digest tests in staging.

## 16. Key Takeaways and Official References

**Eight key takeaways:**

1. **Binary Authorization** enforces **image admission**—it does not prove source code or runtime behavior is completely secure.
2. **Immutable digests** matter more than mutable tags; **attestations are signed approvals** bound to an image digest.
3. **Project-singleton policy** governs deploy-time blocking; enabling enforcement on a cluster while keeping **`ALWAYS_ALLOW`** adds no protection.
4. **`DRYRUN_AUDIT_LOG_ONLY`** permits deployments while logging violations; **`ENFORCED_BLOCK_AND_AUDIT_LOG`** blocks them.
5. **Attestors** are verification authorities; separate release signers/approvers from builders and policy admins.
6. **CV platform policies** (Preview) monitor running Pods; CV **logs findings and never kills Pods**.
7. **Breakglass** uses an audited Pod label reserved solely for approved emergency exceptions.
8. Combine **IAM/RBAC, Pod Security, registry protection, scanning, CI/CD, monitoring, and rollback** for defense in depth.

**Official Google Cloud documentation:**

1. [Binary Authorization overview](https://docs.cloud.google.com/binary-authorization/docs/overview) — enforcement model and attestations.
2. [Concepts and policies](https://docs.cloud.google.com/binary-authorization/docs/key-concepts) — policy types, attestors, and signatures.
3. [Set up Binary Authorization for GKE](https://docs.cloud.google.com/binary-authorization/docs/setting-up) — enforcement scope and setup steps.
4. [Configure policy using gcloud](https://docs.cloud.google.com/binary-authorization/docs/configuring-policy-cli) — evaluation/enforcement modes and cluster/namespace/KSA rules.
5. [Policy YAML reference](https://docs.cloud.google.com/binary-authorization/docs/policy-yaml-reference) — rule syntax and exemptions.
6. [Get started using gcloud with GKE](https://docs.cloud.google.com/binary-authorization/docs/getting-started-cli) — creating attestors, Cloud KMS keys, and attestations.
7. [Create attestations](https://docs.cloud.google.com/binary-authorization/docs/making-attestations) — signing image digests and verification.
8. [Built by Cloud Build attestor](https://docs.cloud.google.com/binary-authorization/docs/deploy-cloud-build) — Cloud Build image attestations.
9. [Continuous Validation overview](https://docs.cloud.google.com/binary-authorization/docs/overview-cv) — Preview scope and limits.
10. [Quickstart continuous validation](https://docs.cloud.google.com/binary-authorization/docs/quickstart-cv) — platform policies and cluster bindings.
11. [Use breakglass](https://docs.cloud.google.com/binary-authorization/docs/using-breakglass) — Pod label and auditing.
12. [View Binary Authorization GKE audit logs](https://docs.cloud.google.com/binary-authorization/docs/viewing-audit-logs) — blocked, breakglass, fail-open, and dry-run logs.
