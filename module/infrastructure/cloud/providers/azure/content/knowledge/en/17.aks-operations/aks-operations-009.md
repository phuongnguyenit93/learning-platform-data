# Image Security, Admission Policies, and AKS Workloads

An application running on **Azure Kubernetes Service (AKS)** can deploy cleanly as valid YAML while still shipping vulnerable container images, running as root, mounting sensitive `hostPath` directories, storing passwords in environment variables, or exposing wider network paths than needed. These configurations create risk even though the cluster is hosted on a managed Azure Kubernetes service.

AKS security must therefore be layered: **controlling image sources**, **scanning images in pipelines**, **verifying images and policies when Kubernetes admits requests**, **minimizing Pod privileges**, **restricting identities and networks**, and **monitoring at runtime**. No single tool replaces the full lifecycle.

This lesson belongs to the **AKS Operations** chapter of the **CLOUD_PROVIDERS_AZURE** module. Building on Azure subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and data services, we establish an operational model that blocks non-compliant deployments from entering the cluster while preserving clear exception paths, rollbacks, and observability.

> **Key principle:** Image scanning only reports issues known to the scanner at evaluation time. **Admission policies** govern requests to create or update Kubernetes resources. **Runtime protection** detects, blocks, or assists response to behavior inside running containers. These three layers are not interchangeable and must work together.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe container supply-chain risks: forged images, overwritten tags, vulnerable dependencies, secrets baked into images, and non-reproducible builds.
2. Design a **source → build → scan → sign/attest → registry → admission → runtime** pipeline.
3. Distinguish Azure Container Registry (ACR), Microsoft Defender for Containers, the Azure Policy add-on, Pod Security Admission (PSA), Gatekeeper, and other admission controllers.
4. Explain **mutating/validating admission**, **Audit/Deny/Warn** policy modes, enforcement scope, and the impact of webhook unavailability.
5. Build AKS workloads meeting baseline hardening controls: non-root, no privilege escalation, dropped Linux capabilities, seccomp, read-only root filesystem, and resource limits.
6. Apply Kubernetes Pod Security Standards (**Privileged**, **Baseline**, **Restricted**) per namespace and stage policies from audit/warn before enforcing.
7. Enforce an allowed-registry policy; distinguish **allowed registry**, **digest pinning**, and **signature verification**.
8. Separate kubelet image-pull identity from Pod workload identity; apply least privilege and Microsoft Entra Workload ID where appropriate.
9. Distinguish RBAC, NetworkPolicy, Kubernetes Secrets, and admission policies.
10. Diagnose rejected Deployments, uncreated Pods, `ImagePullBackOff`, or containers failing due to missing permissions; build runbooks and policy coverage reports.

## 2. Threat Model: What Needs Protection?

Consider an Orders system with these components:

- Source code for **orders-api** and **orders-worker**.
- Build pipelines producing container images.
- ACR hosting internal images.
- An AKS cluster with development, staging, and production namespaces.
- Azure SQL Database, Azure Storage, and Key Vault as backend dependencies.
- Azure Monitor/Log Analytics and Microsoft Defender for Cloud for visibility and threat detection.

Scenarios of concern:

| Risk | Attack / Incident Vector | Consequence |
|---|---|---|
| Vulnerable dependencies | Image bundles unpatched libraries or base OS packages | Attackers exploit the app or OS packages inside the container |
| Untrusted images | Pipeline/Deployment references unvetted public registries | Unreviewed code executes on cluster nodes |
| Mutable tags | Production tag gets overwritten with different contents | Two deploys of the same tag no longer run the same artifact |
| Secrets in images | Tokens baked into Dockerfiles, layers, or Git | Credentials remain exposed in layer history even if deleted later |
| Overprivileged Pods | `privileged`, `hostPID`, sensitive `hostPath`, root + broad capabilities | Escalated risk of node compromise and lateral impact on sibling workloads |
| Overbroad ServiceAccounts | Pod can read Secrets, edit Deployments, or list unneeded resources | Lateral movement inside the cluster or privilege escalation |
| Overly open network | Pod can reach every namespace or the public Internet | Lateral movement and data exfiltration |
| Missing guardrails | Non-compliant manifests are accepted by the API server | Misconfigurations spread rapidly through CI/CD |
| Unmonitored runtime | Containers spawn suspicious processes or connections unnoticed | Prolonged detection and remediation time |

Sound protection starts from a **threat model and trust boundaries**, not merely flipping on an add-on.

## 3. Defense-in-Depth Architecture

~~~mermaid
flowchart LR
    SRC["Git source + dependencies"] --> CI["CI: build, test, SCA, SBOM"]
    CI --> SCAN["Image scan + policy check"]
    SCAN --> SIGN["Sign/attest artifact by digest"]
    SIGN --> ACR["Azure Container Registry"]
    ACR --> ADM["AKS admission policy"]
    ADM --> NODE["Node/kubelet pulls image"]
    NODE --> POD["Pod runs with least privilege"]
    POD --> OBS["Logs, metrics, Defender, investigation"]
    ID["Entra ID / Workload Identity"] -. "Identity and permissions" .-> POD
    NET["NetworkPolicy / VNet / firewall"] -. "Traffic boundaries" .-> POD
~~~

### 3.1. Each Layer Answers a Different Question

| Layer | Question |
|---|---|
| Source & dependencies | Do source code and libraries come from trusted origins? |
| Build & image scan | Does the artifact contain known CVEs, secrets, risky packages, or misconfigurations? |
| Registry | Who can push/pull/delete images? Are artifacts stored, protected, and audited? |
| Provenance & signatures | Does the deployed image match an authentic artifact from a trusted build pipeline? |
| Admission policy | Does the incoming manifest violate cluster deployment rules? |
| Pod/runtime hardening | If the app is exploited, how tightly is its blast radius contained? |
| Kubernetes/Azure IAM | Do Pods and operators hold strictly scoped API and data-plane permissions? |
| Network | Which destinations can the Pod reach? |
| Runtime monitoring | Are suspicious behaviors, newly disclosed CVEs, or policy drift detected? |

**Security does not stop once admission accepts a Pod.** Code may harbor undiscovered vulnerabilities, logic flaws may exist, or new CVEs may be disclosed long after an image was deployed.

## 4. Images Are Release Artifacts That Must Be Governed

An OCI image consists of a manifest, filesystem layers, image configuration, and metadata. An image reference looks like:

~~~text
<registry-login-server>/<repository>:<tag>

Example:
acrordersprod.azurecr.io/orders/orders-api:2.4.1
~~~

A digest-pinned reference looks like:

~~~text
acrordersprod.azurecr.io/orders/orders-api@sha256:<actual-digest>
~~~

Where:

- **Registry** determines where to fetch the artifact.
- **Repository** identifies the image stream.
- **Tag** is a human-friendly alias that can change if the registry permits overwrites.
- **Digest** cryptographically identifies the exact image manifest, guaranteeing deployment of the exact tested artifact.

### 4.1. Why `latest` Is Insufficient

Scenario:

1. Pipeline A pushes a safe image to **`orders-api:latest`**.
2. Another pipeline or account overwrites that same tag.
3. Newly scheduled Pods pull the tag and receive different code.
4. Older Pods continue running the cached previous image.

Result: identical YAML manifests yield different running software across nodes. Use immutable release tags and **pin digests** whenever reproducibility matters.

**`imagePullPolicy: Always`** forces kubelet to check the registry on container start, yet **it does not make a tag immutable** and **does not replace cryptographic signatures**.

### 4.2. SBOM and Provenance

- **SBOM (Software Bill of Materials):** inventory of components, libraries, and versions inside the artifact.
- **Build provenance:** verifiable evidence linking source commit, workflow, builder, and published digest.
- **Image signature/attestation:** cryptographic proof or signed statements about an artifact used during trust verification.

Lacking an SBOM does not mean an image is malicious, but without component visibility, CVE triage, patching, and audits become much harder.

### 4.3. A Signed Image Differs from a Scanned Image

A **signed** image can still contain CVEs: a signature attests origin and integrity per the signing workflow, not absolute absence of vulnerabilities. Conversely, a **scanned** image can still be swapped out if Deployments use mutable tags without digest/provenance checks.

High-assurance environments need both **vulnerability scanning** and **origin/content verification**.

## 5. Azure Container Registry: Controlling Image Supply

ACR is Azure's managed private registry for storing container images and OCI artifacts for AKS.

### 5.1. Separating Permissions

| Principal | Needed Permissions | Avoid Granting by Default |
|---|---|---|
| Orders CI/CD | Push images to Orders repositories under supported permission mode | Subscription-wide Owner |
| AKS kubelet identity | Pull images required for deployment | `AcrPush`, registry admin user |
| Security scanner | Read artifacts/metadata needed for scanning | Unnecessary write/delete rights |
| Developer | Read/test rights per environment | Overwrite rights on production releases |
| App inside Pod | Access Storage/SQL/Key Vault for business logic | Registry or AKS administration rights |

With ACR in **RBAC Registry Permissions** mode, kubelet typically receives the **`AcrPull`** role. With **RBAC Registry + ABAC Repository Permissions**, roles such as **Container Registry Repository Reader** apply with repository conditions. Passing **`az aks --attach-acr`** does not replace assigning appropriate repository-scoped roles under ABAC mode.

### 5.2. Inspecting ACR and AKS Configuration

Read-only commands targeting an authorized subscription and resources:

~~~bash
az login
az account set --subscription "<subscription-id>"

ACR_NAME="<acr-name>"
AKS_RG="<aks-resource-group>"
AKS_NAME="<aks-cluster-name>"

az acr show \
  --name "$ACR_NAME" \
  --query "{name:name,loginServer:loginServer,sku:sku.name,id:id}" \
  --output json

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,identity:identity,kubelet:identityProfile.kubeletidentity}" \
  --output json
~~~

These commands **do not prove nodes can actually pull images**. Also verify exact identities, role assignments, ACR permission mode, network paths, and Pod Events.

### 5.3. A Private Registry Does Not Automatically Block External Images

Having AKS connected to ACR does not force Deployments to reference only that ACR. A developer permitted to create Pods can still pull public images if **admission guardrails and network egress controls are missing**.

To restrict image origins, enforce an allowlist policy over approved registries/repositories covering **`containers`**, **`initContainers`**, and **`ephemeralContainers`** wherever feasible.

## 6. Image Scanning Before and After Deployment

### 6.1. Pipeline Scanning

In CI/CD, scan artifacts after build and before release for:

- Application libraries, direct and transitive dependencies.
- OS packages in the base image and final image.
- Leaked secrets in source, build context, or filesystem layers.
- Risky Dockerfile patterns where supported by linters/scanners.
- License and package-source policies per organizational standards.
- Image manifest, architecture, provenance, and SBOM.

Scanners may include Microsoft Defender for Cloud / Defender for Containers where supported, Trivy, Grype, or enterprise tooling. Teams must explicitly document scanner versions, vulnerability databases, and release criteria rather than merely stating "scanned."

### 6.2. Choosing Release Blocking Thresholds

Illustrative policy table:

| Finding | Suggested Action | Notes |
|---|---|---|
| Critical CVE with fix available and reachable attack path | Block release, patch, and rebuild | Validate with real triage |
| High CVE without fix yet, directly exposed workload | Security review, mitigations, time-bound exception | Do not treat scanner output as the sole final judgment |
| Medium CVE in dependency unused at runtime | Track / assess reachability | Document evidence; do not ignore indefinitely |
| Hard-coded secret | Block, revoke/rotate secret, rebuild image | Deleting a file in a later layer leaves it in image layer history |
| Unknown-origin base image | Block or require trust verification | Consider mirroring approved base images |

Avoid blind rules like "block every High CVE regardless of context" without evaluating risk, false positives, and exception handling. Conversely, never **suppress every warning just to keep the pipeline green**.

### 6.3. Scanning Is Continuous

An image that passed yesterday may match a newly disclosed CVE today. Therefore:

1. Monitor new vulnerability findings across registry images and running workloads per supported features.
2. Identify the exact image digest and affected Pods/namespaces.
3. Prioritize by severity, exposure, exploitability, and business criticality.
4. Rebuild using patched base images/dependencies.
5. Re-release using the new digest.
6. Verify rollback paths, app health, and remediation evidence.

**Defender for Containers** provides vulnerability assessments, security posture insights, and runtime alerts depending on plan, region, and connectivity—it does not automatically mean **every image with a CVE is blocked by Kubernetes admission**. Blocking requires explicit enforcement policies and tooling.

## 7. Image Signing and Provenance Verification

A sound verification chain:

~~~mermaid
flowchart LR
    C["Reviewed commit"] --> B["Controlled build"]
    B --> T["Test + scan + SBOM"]
    T --> D["Immutable digest"]
    D --> S["Sign/attest digest"]
    S --> ACR["ACR"]
    ACR --> V["Admission verifies signature/provenance"]
    V --> AKS["Pod permitted to run"]
~~~

### 7.1. Where to Verify?

- **Pre-push:** verify source, dependencies, and build integrity.
- **Post-push:** capture the actual image digest from the registry and store matching provenance metadata and signatures.
- **Pre-deploy:** pipelines or admission controllers verify the release is authorized and carries valid signatures/attestations.
- **Post-deploy:** inspect running digests and reconcile against approved artifacts.

Tools like **Sigstore Cosign** can sign and verify OCI images. However, **storing images in ACR does not make Kubernetes check signatures at admission by default**. Blocking unsigned images requires deploying a supported admission verification engine and governing trusted keys/identities.

### 7.2. Illustrative Verification Command

Suppose the organization uses Cosign with an approved public key:

~~~bash
# IMAGE_DIGEST must be a real registry/repository@sha256:... reference
# cosign.pub is the governed, trusted public key
cosign verify --key cosign.pub "$IMAGE_DIGEST"
~~~

This command is an **illustrative verification check**, not an automated deployment step in this lesson. Keyless signature verification typically requires constraining certificate identity and OIDC issuer alongside a trust policy; never assume any valid Cosign signature equals an approved internal build.

### 7.3. Ways Signature Policies Are Misconfigured

- Checking that a signature exists without verifying **who signed it**.
- Fetching the public key from the same untrusted repository as the image.
- Skipping digest pinning in the Deployment while verifying a different digest.
- Allowing un-audited admission bypasses.
- Failing to protect signing keys or CI/CD OIDC identities.
- Lacking a key revocation/trust rotation plan if a signer is compromised.

**Allowed registry**, **digest pinning**, **signature validation**, and **vulnerability scanning** are four distinct controls. Enabling just one does not secure the supply chain.

## 8. How Kubernetes Admission Control Works

A request to create or update a Pod reaches the **Kubernetes API server**. After authentication and authorization, configured admission controllers can mutate or validate the object before persisting it.

~~~mermaid
flowchart LR
    U["kubectl / GitOps / CI"] --> AUTH["Authentication + Authorization"]
    AUTH --> MUT["Mutating admission<br/>if configured"]
    MUT --> VAL["Validating admission + policy"]
    VAL --> Q{"Valid?"}
    Q -->|No| DENY["Reject API request"]
    Q -->|Yes| STORE["Persist object → scheduler → kubelet"]
    STORE --> RUN["Pod runs"]
~~~

This diagram simplifies the flow; Kubernetes runs multiple built-in admission plugins and webhooks with distinct ordering, reinvocation rules, and conditions.

### 8.1. Mutating Admission

Can add or modify fields before persistence—such as injecting labels, sidecars, or policy-approved defaults.

**Risk:** silent mutations can make live manifests diverge from Git. Inspect post-admission resources and explicitly document active mutating policies.

### 8.2. Validating Admission

Evaluates the request; if enforced rules are violated, the API server rejects the operation.

Examples:

- Image is not from an approved registry.
- Pod declares **`privileged: true`**.
- Missing required seccomp, `allowPrivilegeEscalation`, or resource limits.
- Forbidden `hostPath` mount.
- Deployment lacks mandatory governance labels.
- Workload targets an unauthorized namespace.

### 8.3. Admission Is Not Runtime Security

Admission evaluates objects at API request time. It **does not monitor syscalls** after containers start, nor does it automatically delete or patch already-running Pods when you tighten a policy the next day.

Evaluating existing workloads requires audits, background scans, inventories, or compliance controllers. Detecting runtime anomalies requires telemetry and runtime security tools.

### 8.4. Controllers Are a Critical Link

When you create a Deployment, the API server may accept the Deployment object, only for **its Pod template to be rejected later when the ReplicaSet tries to create Pods**. In that situation:

- The Deployment object still exists.
- The ReplicaSet fails to spawn desired Pods.
- Events report **`FailedCreate`** with the policy violation.
- **`kubectl rollout status`** times out.

Therefore, seeing **`kubectl apply`** succeed is not enough. Always verify rollout status, Pod status, and Events.

## 9. Admission and Policy Mechanisms on AKS

Multiple control mechanisms exist—do not treat them as completely equivalent.

| Mechanism | Primary Focus | Limitations to Remember |
|---|---|---|
| **Kubernetes Pod Security Admission (PSA)** | Enforces Pod Security Standards per namespace via enforce/audit/warn | Does not replace custom policies for registries, labels, or image signatures |
| **Azure Policy add-on for AKS** | Audits/enforces Azure Policy Kubernetes definitions using policy/Gatekeeper components per support | Depends on add-on health, policy assignments, scope, and supported features |
| **OPA Gatekeeper** | `ConstraintTemplate`/`Constraint` validation across Kubernetes resources | Must operate webhooks/policies and avoid conflicts with add-on-managed policies |
| **Kyverno** | Kubernetes-native YAML policies for validate/mutate/generate and image verification per version | Requires operating/upgrading engine, curating policies, watching latency/availability |
| **ValidatingAdmissionPolicy (CEL)** | In-tree CEL validation inside Kubernetes where supported by version | Does not natively verify image signatures or call external scanners |
| **Custom admission webhook** | Custom validation via external service | Must engineer TLS, HA, timeouts, failurePolicy, and security |

Choose mechanisms based on **AKS version, add-ons, coverage requirements, operational capacity, and organizational policy**. Never stack multiple admission engines enforcing the same rule without clear ownership and conflict resolution.

## 10. Pod Security Standards: Privileged, Baseline, Restricted

Kubernetes defines three Pod security tiers:

### 10.1. Privileged

**Privileged** imposes essentially no Pod Security Standard restrictions. Use it only when a namespace or workload has explicitly reviewed and approved special system requirements, such as certain infrastructure components.

Never use Privileged as the default standard for business applications.

### 10.2. Baseline

**Baseline** blocks common privilege-escalation vectors without requiring every app to meet the strictest hardening profile. It works well as an initial standardization step for environments with legacy workloads.

### 10.3. Restricted

**Restricted** enforces stricter hardening suited to standard application workloads that can run with minimal privileges, including security context, capabilities, seccomp, and related protections per policy version.

Legacy images running as root, writing to the root filesystem, or relying on broad Linux capabilities may fail Restricted immediately. Fix the image/application first rather than permanently downgrading namespace enforcement.

### 10.4. Three PSA Modes

| Mode | What Happens |
|---|---|
| **enforce** | Rejects new/updated Pods violating the assigned level |
| **audit** | Records violations in audit annotations/logs without blocking |
| **warn** | Returns warnings to the client on non-compliant requests without blocking |

PSA evaluates **namespace labels**. Changing a label does not automatically evict already-running Pods; however, recreating Pods during rollouts or node failures will be gated by the new policy.

## 11. Hands-On PSA: Moving from Warn/Audit to Enforce

**Prerequisites:** lab AKS kubeconfig, RBAC rights to manage namespaces/labels, and a Kubernetes version supporting PSA. Practice only on an approved namespace.

### 11.1. Create a Test Namespace

~~~bash
az aks get-credentials \
  --resource-group "<aks-rg>" \
  --name "<aks-name>"

kubectl config current-context

kubectl create namespace orders-security-lab
~~~

Never recreate existing namespaces or apply Restricted policies onto **`kube-system`**. Infrastructure namespaces run specialized Pods incompatible with Restricted.

### 11.2. Enable Warn and Audit First

~~~bash
NS="orders-security-lab"

kubectl label namespace "$NS" \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted \
  --overwrite
~~~

When creating a non-compliant Pod, the client receives warnings, yet the request is not rejected until **`enforce=restricted`** is enabled.

### 11.3. An Intentionally Non-Compliant Pod for Testing

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: insecure-demo
  namespace: orders-security-lab
spec:
  containers:
    - name: app
      image: nginx:alpine
      securityContext:
        privileged: true
~~~

Save this manifest as **`insecure-demo.yaml`** in your lab directory if practicing and run:

~~~bash
kubectl apply --dry-run=server -f insecure-demo.yaml
~~~

Kubernetes returns a warning about the privileged Pod. **Server-side dry run** requires participating admission components to support dry-run; if an unrelated webhook lacks support, the test may fail for technical reasons rather than policy.

Never deploy real privileged Pods in production to test admission. Use **dry-run in a lab environment** only.

### 11.4. Transition to Enforce via Process

Once workloads are remediated, violations reviewed, and owners approve:

~~~bash
kubectl label namespace "$NS" \
  pod-security.kubernetes.io/enforce=restricted \
  --overwrite
~~~

Test again:

~~~bash
kubectl apply --dry-run=server -f insecure-demo.yaml
~~~

Expect the request to be rejected with a Pod Security Standard violation message. If no warning or denial appears, inspect namespace labels, API version, workload kind, and cluster PSA settings.

### 11.5. Managing Policy Versions

PSA supports **`pod-security.kubernetes.io/enforce-version`**, **`audit-version`**, and **`warn-version`** labels in supported Kubernetes versions. You can use **`latest`** or pin a Kubernetes minor version per policy.

Avoid letting AKS Kubernetes upgrades silently shift enforcement behavior if your organization requires predictable rollouts. At the same time, schedule periodic version bumps so standards do not fall far behind.

### 11.6. What PSA Does Not Do for You

PSA does not:

- Restrict images to your internal ACR.
- Verify digests, signatures, or provenance.
- Read scanner CVE reports.
- Enforce NetworkPolicies or egress rules.
- Grant workload identity or Key Vault permissions.
- Scan filesystems inside running containers.

That is why additional admission policies and defense-in-depth layers are required.

## 12. Sample Deployment with Least-Privilege Security Context

A workload running in a Restricted namespace must be prepared from **Dockerfile/image** through Pod spec.

### 12.1. Illustrative Manifest

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-security-lab
  labels:
    app: orders-api
    team: orders
spec:
  replicas: 2
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        team: orders
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          # Replace with an actual built and approved image/digest.
          image: acrordersprod.azurecr.io/orders/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
~~~

**This is a security template manifest**, not deployable as-is: replace the placeholder digest, ensure the image supports UID 10001, read-only root filesystem, temp writes to **`/tmp`**, and exposes **`/ready`** and **`/health`**. Without those traits, admission may accept the Pod while the app crashes at startup.

### 12.2. Purpose of Each Control

| Field | Purpose | Caveats |
|---|---|---|
| **`runAsNonRoot`** | Requires processes not to run as UID 0 | Image/entrypoint must be compatible |
| **`runAsUser`/`runAsGroup`** | Sets unprivileged UID/GID | Files in the image must have matching permissions |
| **`allowPrivilegeEscalation: false`** | Prevents processes from gaining extra privileges via kernel mechanisms | Does not replace full container/VM isolation |
| **`capabilities.drop: ALL`** | Strips default Linux capabilities | Rare specialized apps needing a capability require documented review |
| **`seccompProfile: RuntimeDefault`** | Applies runtime default seccomp profile | Can block legacy syscalls needed by older apps |
| **`readOnlyRootFilesystem: true`** | Blocks writes to container root FS | Mount writable volumes for legitimate temp paths |
| **`automountServiceAccountToken: false`** | Omits unnecessary Kubernetes API token mounts | Do not blindly set on apps needing the Kubernetes API or Workload Identity |
| **`requests`/`limits`** | Bounds and schedules resource usage | Overly low values cause throttling or OOMKills |
| **`probes`** | Separates running vs ready-to-serve states | Misconfigured probes cause restarts or outages |
| **`emptyDir /tmp`** | Allows bounded temp writes with read-only root FS | Contents do not survive Pod lifecycle |

This sample enables **`readOnlyRootFilesystem`** for extra hardening, though it is not strictly mandatory in all versions of Pod Security Standards Restricted. Organizations can enforce stricter internal policies than Restricted.

### 12.3. Why Can Running Non-Root Fail?

Images may contain:

- Files readable only by root.
- Entrypoints trying to `chown` or write under **`/usr`** or **`/opt`**.
- Processes binding privileged ports (<1024) or using dropped capabilities.
- Apps writing logs to a read-only directory.
- Native libraries invoking syscalls blocked by seccomp.

Always **fix the Dockerfile/code and test the image** rather than working around errors with **`runAsUser: 0`**, **`privileged: true`**, or writable root filesystems.

## 13. Example Java Container Compatible with Non-Root

To see how image configuration connects to Kubernetes, here is a minimal Java HTTP server serving health endpoints. It illustrates security posture only and does not replace Spring Boot/Jetty/Tomcat in production.

### 13.1. `HealthServer.java`

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class HealthServer {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
                System.getenv().getOrDefault("PORT", "8080"));

        HttpServer server = HttpServer.create(
                new InetSocketAddress("0.0.0.0", port), 0);

        server.createContext("/health", exchange -> {
            byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.createContext("/ready", exchange -> {
            byte[] bytes = "READY".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        System.out.println("Java health server on port " + port);
    }
}
~~~

### 13.2. Multi-Stage Dockerfile

~~~dockerfile
# Educational sample: production builds must pin base image digests and scan for CVEs.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY HealthServer.java .
RUN javac HealthServer.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/HealthServer.class /app/

# Root is unnecessary to listen on port 8080.
USER 10001:10001
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "HealthServer"]
~~~

The final image contains only compiled bytecode and the JRE. Because the app does not write to **`/app`**, `readOnlyRootFilesystem` works alongside a temp mount for any writable paths; always test exact JRE/base image requirements.

Local build/test commands:

~~~bash
docker build -t orders-health:lab .
docker run --rm -p 8080:8080 orders-health:lab
~~~

In another terminal:

~~~bash
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/ready
~~~

Before pushing to ACR, ensure an approved registry, push permissions, and image scanning. Never bake secrets into Dockerfiles, build args, or image layers.

### 13.3. Testing Under Real `securityContext`

A passing local build **is not enough** to prove compatibility under Restricted PSA in AKS. When deploying to a staging namespace:

1. Pin the image digest and ensure nodes hold pull permissions.
2. Deploy with the target UID/GID, seccomp, capabilities, and filesystem restrictions.
3. Inspect Pod Events, readiness/liveness, logs, and exit codes.
4. Probe endpoints via `port-forward` or internal Service.
5. Test under scale-out, Pod restarts, and dependency outages.
6. Promote to production only after both security policies and smoke tests pass.

## 14. Azure Policy Add-On for AKS

**Azure Policy** applies Kubernetes-related policy definitions across supported AKS clusters. The Azure Policy add-on integrates with in-cluster policy components (backed by Gatekeeper in supported architectures) to audit, report compliance, and deny non-compliant requests per policy assignments.

### 14.1. Capabilities and Limitations

Requirements commonly audited or enforced via built-in definitions:

- Allow images only from approved registries.
- Block privileged containers.
- Block unapproved host namespaces or `hostPath` mounts.
- Require specific `securityContext` or resource configurations.
- Govern additional Pod/cluster fields supported by definitions.

**Not every Azure Policy definition supports every AKS version, object kind, or effect.** An **`Audit`** assignment only logs compliance; blocking requires **`Deny`** (or supported equivalent) without broad exclusions.

### 14.2. Enabling the Add-On

On an existing lab AKS cluster on a supported tier/feature set:

~~~bash
az aks enable-addons \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --addons azure-policy
~~~

Verify:

~~~bash
az aks show \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --query "addonProfiles.azurepolicy" \
  --output json
~~~

Before enabling in production, verify cluster version, permissions, telemetry costs/sinks, existing add-on status, and Azure Policy prerequisites. Never toggle the add-on off and on repeatedly to clear an undiagnosed admission error.

### 14.3. Assigning Policies at the Right Azure Scope

Example Portal workflow:

1. Open **Azure Policy → Definitions** and search built-in definitions for **Kubernetes Service / AKS** matching "Allowed container images/registries" or target hardening rules.
2. Read the active definition's conditions, parameters, supported effects, and limitations.
3. Click **Assign**, choose the right subscription/resource group/cluster scope, and set parameters.
4. Start in **`Audit`** mode where appropriate; review compliance and affected workloads.
5. Remediate images, manifests, and deployment pipelines.
6. Switch to **`Deny`** during an approved change window.
7. Verify with **server-side dry-run**, staging rollouts, and compliance dashboards.

Exact built-in definition names and effects evolve in the Azure Policy catalog. Never hard-code unverified definition IDs as universal defaults across subscriptions.

### 14.4. Scope and Exclusions

Assigning a policy at a subscription containing multiple AKS clusters affects more than one production namespace. Review:

- Azure assignment scope and `notScopes`.
- Approved **policy exemptions**.
- Namespace exclusions supported/bounded by the policy add-on.
- Unowned clusters and namespaces.
- Compatibility of active policies when upgrading AKS/Kubernetes versions.
- How existing resources are audited versus how new objects are denied.

Never cite **`kube-system`** exclusions as an excuse to grant broad exemptions to business namespaces. System components require policies tailored to their role.

## 15. Illustrative Policy: Allow Images Only from Internal ACR

There are several ways to restrict registries. A **Kubernetes-native** approach on supported versions is **`ValidatingAdmissionPolicy`** using CEL. Below is a simple example showing image-string validation logic; it **does not verify image signatures or vulnerability status**.

### 15.1. Policy Validating Pod Image References

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: approved-acr-images.example.com
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods"]
  validations:
    - expression: >-
        object.spec.containers.all(c,
          c.image.startsWith('acrordersprod.azurecr.io/')) &&
        (!has(object.spec.initContainers) ||
          object.spec.initContainers.all(c,
            c.image.startsWith('acrordersprod.azurecr.io/'))) &&
        (!has(object.spec.ephemeralContainers) ||
          object.spec.ephemeralContainers.all(c,
            c.image.startsWith('acrordersprod.azurecr.io/')))
      message: "Pod images must use the approved ACR."
~~~

This policy checks all three container lists and rejects references lacking the approved prefix. This **registry-prefix validation example** has clear limitations:

- Does not prove the repository/tag/digest exists.
- Does not verify signatures or scanner approval.
- Does not restrict registry credentials or outbound traffic on its own.
- Only inspects **Pod create/update** per `resourceRules`; does not automatically audit all existing images across controllers.
- Does not evaluate Deployment templates at Deployment creation time; controller-spawned Pods are the evaluated objects in this example.
- Does not address path traversal quirks, aliases, or artifact distribution controls; security reviews must evaluate production policies thoroughly.

### 15.2. Binding to Test Only in Labeled Namespaces

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: approved-acr-images-lab
spec:
  policyName: approved-acr-images.example.com
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        policies.example.com/require-acr: "true"
~~~

Label the lab namespace:

~~~bash
kubectl label namespace orders-security-lab \
  policies.example.com/require-acr=true \
  --overwrite
~~~

**Do not enforce sample policies in production without thorough testing.** `ValidatingAdmissionPolicy` depends on Kubernetes/AKS version and supported API features. Test CEL expressions, matching rules, policy approvals, and RBAC over creating Bindings in a live cluster.

When staging before `Deny`, check **`Warn`/`Audit`** in `validationActions` per API support. Limit scope with namespace labels and watch Events before expanding.

### 15.3. Preventing Policy Bypass

- Ensure policies do not overlook `initContainers` or `ephemeralContainers` where relevant.
- Restrict who can edit **namespace labels** and Bindings.
- Restrict who can create/modify **`ValidatingAdmissionPolicy`** objects.
- Watch workloads running in unlabeled namespaces.
- Align CI/CD and admission checks around the same rules with clear ownership.
- Never confuse **registry prefix validation** with signature verification.
- Review any documented Kubernetes bypass vectors or admission-exempt paths if applicable.

## 16. Gatekeeper and Kyverno: Advanced Policy Options

### 16.1. Gatekeeper

**OPA Gatekeeper** uses `ConstraintTemplate` and `Constraint` objects to validate Kubernetes resources. The Azure Policy add-on deploys/operates Gatekeeper components for supported Azure Policy definitions.

If a team wants to manage custom Gatekeeper constraints directly, clarify:

- Use the Azure Policy add-on's managed Gatekeeper or run a separate installation?
- Who owns CRDs, templates, and webhooks?
- Are there conflicts or overwrites with Azure-synced policies?
- Which policies run in audit vs enforce mode?
- How are exemptions and existing-resource audits handled?
- Are webhook availability and latency monitored?

Never manually edit add-on-managed resources without understanding their lifecycle and supportability.

### 16.2. Kyverno

**Kyverno** lets you author Kubernetes-YAML policies for validate/mutate/generate tasks and image verification depending on version.

An organization might adopt Kyverno to:

- Enforce internal ACR images or digest pinning.
- Validate `securityContext` and metadata.
- Verify image signatures/attestations against configured trust policies.
- Generate or report policy violations per tool capabilities.

Adding another policy engine increases API server dependencies and upgrade overhead. Do not install Kyverno just to solve something PSA or built-in Azure Policy already handles well.

### 16.3. Choosing Tools by Requirement

| Requirement | Mechanism to Consider |
|---|---|
| Block common privileged/root postures | PSA Restricted/Baseline, targeted policies |
| Allowed registry/repository | Azure Policy, Gatekeeper, Kyverno, or `ValidatingAdmissionPolicy` |
| Signature/provenance verification | Admission engine with genuine cryptographic image verification |
| Constrain namespace metadata/labels | CEL, Gatekeeper/Kyverno, or appropriate Azure Policy |
| Runtime network protection | NetworkPolicy + enforcing CNI, NSG/Azure Firewall where appropriate |
| Azure data-plane access | Microsoft Entra Workload ID + data-plane RBAC |
| Runtime compromise detection | Defender for Containers and runtime telemetry/tooling |
| Multi-cluster compliance auditing | Azure Policy / Defender dashboards and dedicated reporting |

**An "allowed registries" policy does not sign images or remove CVEs.** State precisely which mechanism satisfies which control.

## 17. Admission Webhooks: Fail-Open, Fail-Closed, and Availability

A validating/mutating webhook requires a reachable service endpoint from the API server per supported Kubernetes/AKS architecture. If the webhook crashes, has an expired certificate, or times out:

- With **`failurePolicy: Fail`**, matching requests are rejected: **fail-closed**.
- With **`failurePolicy: Ignore`**, the API server allows requests through when the webhook fails to respond: **fail-open** for that check.

Both choices carry clear trade-offs:

| Mode | Benefit | Risk |
|---|---|---|
| `Fail` | Guardrails are never silently bypassed during webhook outages | Can block deployments or operations during policy service outages |
| `Ignore` | Reduces availability impact when webhooks fail | Non-compliant workloads can slip in during the outage window |

**Never flip a production webhook to `Ignore` just because one deployment is stuck.** Investigate root cause, outage duration, blast radius, approved exceptions, and recovery steps first.

### 17.1. Admission Operational Metrics

- Request volume and denial rate per policy.
- Admission webhook latency and timeouts.
- TLS certificate expiration and service health.
- Top namespaces/apps generating violations.
- Active exemptions and expiration dates.
- Legacy Pods predating enforcement that remain un-remediated.
- Rollout failures caused by admission and time-to-resolve.

If a policy locks out critical operations, follow a time-bound, audited **break-glass runbook** with named owners—never hand `cluster-admin` to every developer to bypass checks.

## 18. Kubernetes RBAC: Admission Does Not Replace API Authorization

**Kubernetes RBAC** determines who can perform actions on API resources. Admission evaluates objects/actions after authentication and authorization pass.

Examples:

- A user permitted to create Deployments in **`orders-prod`** can still have non-compliant Pod templates rejected at Pod creation time by admission.
- A Pod admitted by policy **should not automatically hold permission to list all Secrets**.
- `cluster-admin` can modify almost anything, so it must stay tightly restricted.

### 18.1. Dedicated ServiceAccount per Workload

If a Pod does not need to call the Kubernetes API:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders-security-lab
automountServiceAccountToken: false
~~~

Reference it in the Deployment:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
~~~

This snippet must be placed inside the Deployment spec—it is **not a standalone Deployment manifest**. Dedicated ServiceAccounts make permissions much easier to govern than sharing the `default` ServiceAccount across apps.

### 18.2. Namespace-Scoped Role

A legitimate ops job might need **`get`/`list` on Pods** in a namespace without needing to read Secrets or edit ClusterRoles:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-viewer
  namespace: orders-security-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-viewer-binding
  namespace: orders-security-lab
subjects:
  - kind: ServiceAccount
    name: orders-observer
    namespace: orders-security-lab
roleRef:
  kind: Role
  name: pod-viewer
  apiGroup: rbac.authorization.k8s.io
~~~

This example assumes **`ServiceAccount orders-observer`** already exists in the namespace. Never add **`secrets/get`** simply because a script returned Forbidden; review actual functional needs first.

### 18.3. Verifying Permissions

~~~bash
kubectl auth can-i get pods \
  --as=system:serviceaccount:orders-security-lab:orders-observer \
  -n orders-security-lab

kubectl auth can-i list secrets \
  --as=system:serviceaccount:orders-security-lab:orders-observer \
  -n orders-security-lab
~~~

Impersonating via **`--as`** requires **`impersonate`** privileges; if rejected, that may reflect the caller's permissions rather than proving the ServiceAccount is misconfigured. An authorized cluster admin can run the check via approved procedures.

## 19. Workload Identity: Accessing Azure Without Static Secrets

An application reading Blob Storage or Key Vault should never bake storage keys or long-lived client secrets into images. **Microsoft Entra Workload ID** for AKS is the preferred mechanism for injecting identity into workloads.

### 19.1. Distinguishing Kubelet vs Workload Identity

| Identity | Responsibility |
|---|---|
| **AKS kubelet identity** | Pulls images from ACR before containers start |
| **AKS control plane identity** | Manages Azure control-plane operations per cluster design |
| **Workload identity bound to ServiceAccount** | Java/Node/Python code inside Pods calls Azure APIs under assigned RBAC |
| **CI/CD identity** | Builds, scans, signs, and pushes artifacts |

Never assign **`AcrPush`** to the Orders workload identity just so the app can read Blob Storage. Avoid `imagePullSecrets` or ACR admin passwords whenever kubelet managed identity integration is supported and secure.

### 19.2. Workload ID Prerequisites

You need AKS OIDC issuer and Workload Identity enabled, a user-assigned managed identity or Entra application, a **federated identity credential** matching issuer/subject/audience, and data-plane RBAC on the target Azure resource.

Azure CLI example to enable these features on an **approved cluster** if not yet enabled:

~~~bash
az aks update \
  --resource-group "<aks-rg>" \
  --name "<aks-name>" \
  --enable-oidc-issuer \
  --enable-workload-identity
~~~

This mutates cluster configuration; never run it in production without a change plan and compatibility review.

### 19.3. ServiceAccount for a Java API

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api-azure
  namespace: orders-security-lab
  annotations:
    azure.workload.identity/client-id: "<managed-identity-client-id>"
~~~

Pods using this ServiceAccount require the workload identity label per AKS mechanics:

~~~yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api-azure
~~~

These are **YAML fragments to insert into a Deployment**, not standalone deployable manifests. A federated credential must exist with subject **`system:serviceaccount:orders-security-lab:orders-api-azure`**, matching the AKS OIDC issuer, expected audience, and target role assignment.

When using Workload Identity, **do not blindly copy `automountServiceAccountToken: false`** from API-less Pod templates; Workload Identity relies on projected token injection per supported mechanics. Verify how the ServiceAccount token is projected and mounted by the webhook/SDK.

### 19.4. Granting Azure Data-Plane Permissions

Full workflow:

1. Create or identify an authorized Azure identity.
2. Configure the federated credential matching cluster issuer, namespace, and ServiceAccount.
3. Assign the narrowest target role—e.g., Blob Data Reader at the right scope or Key Vault Secrets User where allowed.
4. Ensure the Pod uses that exact ServiceAccount and an SDK supporting Workload Identity.
5. Verify connectivity, role propagation, and networking/private DNS.
6. Monitor 401/403 errors; never resolve them by granting subscription-wide Owner.

Workload Identity handles **authentication/identity only**—it does not guarantee network reachability to Blob/Key Vault or assign the right RBAC roles automatically.

## 20. Kubernetes NetworkPolicy and Network Boundaries

Admission blocks dangerous Pod configs, yet **does not restrict live network traffic**. Preventing lateral movement requires NetworkPolicies or other network controls.

### 20.1. Default-Deny in a Namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: orders-security-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

This policy blocks all ingress and egress by default for Pods in the namespace when the **active network plugin/datapath enforces NetworkPolicies**.

**Note:** applying default-deny without allow rules breaks DNS, databases, metrics, and Kubernetes API access. Test in a lab first and map out a traffic matrix beforehand.

### 20.2. Allowing DNS by Actual Labels

Illustrative example allowing DNS queries only to CoreDNS Pods carrying matching labels:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: orders-security-lab
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Verify live CoreDNS labels and DNS architecture on your cluster.** Not every AKS cluster uses **`k8s-app: kube-dns`**, and custom DNS forwarding, NodeLocal DNSCache, or specific dataplanes may require different rules.

### 20.3. Do Not Confuse NetworkPolicy with NSG

- **Kubernetes NetworkPolicy** governs Pod-level traffic enforced by the network plugin.
- **Azure NSG** governs Azure networking at NIC/subnet scope per architecture.
- **Azure Firewall/NVA** enforces centralized ingress/egress inspection.
- **Private Endpoint** provides private connectivity to supported PaaS services.
- **Admission policy** validates manifests, never filtering runtime packets.

AKS network security requires layered controls matched to the cluster's CNI/network plugin, UDRs, DNS, firewalls, and dataplane.

## 21. ResourceQuota, LimitRange, and Abuse Prevention

Dropping OS privileges is not enough if a user can spawn unbounded Pods, request infinite CPU/memory, or exhaust shared cluster capacity.

### 21.1. Namespace ResourceQuota

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-security-lab
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "30"
~~~

`ResourceQuota` caps total declared/consumed resources in a namespace per Kubernetes rules. It does not replace right-sized per-container **`requests`/`limits`**, autoscaling, or cluster capacity planning.

### 21.2. LimitRange

**`LimitRange`** sets per-namespace min/max/default requests/limits where appropriate. When admission injects defaults, a Pod's live resources can differ from the original manifest.

Never rely on `LimitRange` to guess optimal application sizing. Measure CPU, memory, GC, startup, and peak loads. Requests that are too low cause overcommit; limits that are too low cause throttling or OOMKills.

### 21.3. Why Are Quotas Also a Security Control?

A compromised workload or misbehaving deployment can spawn excessive Pods/Jobs and starve sibling teams of availability. Quotas combined with scoped create/update Kubernetes RBAC shrink that blast radius.

Still, a namespace `ResourceQuota` does not prevent every form of cluster exhaustion; pair it with node pool isolation, autoscaler bounds, Pod priority, budgets, and monitoring.

## 22. Secrets, Key Vault, and Data Protection

### 22.1. Kubernetes Secrets Are Not Inherently Fully Secure

A Kubernetes **`Secret`** stores Base64-encoded strings in manifests when using the `data` field, yet **Base64 is not encryption**. RBAC over reading Secrets, encryption at rest, and etcd/API access remain separate concerns.

Never commit manifests holding plaintext secrets or Base64-encoded passwords to Git. Never print tokens to CI logs or Pod logs.

### 22.2. Key Vault and the CSI Driver

AKS integrates with the **Azure Key Vault provider for Secrets Store CSI Driver** where supported. Workloads mount secrets/certificates from Key Vault via a `SecretProviderClass`, identity, and networking; some modes optionally sync into Kubernetes Secrets when configured.

Checks to verify:

- Mount only the secrets each application genuinely needs.
- Use a dedicated workload identity with least-privilege Key Vault permissions.
- Confirm networking/Private Endpoint/DNS reachability to Key Vault.
- Verify **rotation** behavior and how the process reloads updated secrets.
- Minimize risks of secrets leaking into logs or temp files.
- Never treat the CSI driver as a replacement for admission controls or container hardening.

### 22.3. Data on Persistent Volumes

Image policies and `securityContext` alone do not secure data stored on PersistentVolumes. Ensure:

- Appropriate `StorageClass`/PVC configuration.
- Proper filesystem/UID/GID permissions and `fsGroup` where needed and supported.
- Volume backups, snapshots, and tested restores.
- Encryption and access controls at the storage tier.
- Data classification, retention, and deletion workflows.
- Never mount sensitive `hostPath`/host filesystems into app Pods to work around permission errors.

## 23. Monitoring Compliance, Admission, and Runtime

Production security requires auditable evidence, not just checkboxes in a design doc.

### 23.1. Observation Sources

| Data Source | Questions Answered |
|---|---|
| Azure Policy compliance | Which clusters/namespaces/resources violate assigned definitions? |
| PSA warnings/audit | Which Pods failed Baseline/Restricted during the observation window? |
| Admission webhook metrics/logs | Which policies denied requests, timed out, or threw TLS errors? |
| Kubernetes Events | Did ReplicaSets/Pods hit `FailedCreate` due to admission? |
| ACR diagnostic logs | Who pushed/pulled images or modified the registry per supported logs? |
| Defender for Containers | Which CVEs, posture issues, or runtime alerts fired per configuration? |
| Azure Activity Log | Who changed AKS, ACR, roles, or policy assignments at the Azure control plane? |
| Kubernetes audit logs | Who created/modified Pods/Roles/Secrets/Policies per audit config? |
| Container Insights / Azure Monitor | Process restarts, OOMs, node resources, logs, requests |
| CI/CD provenance | Which commit, builder, and digest produced the running release? |

These telemetry streams have individual enablement and billing conditions. **Never assume AKS automatically streams all Kubernetes audit logs to Log Analytics** or enables every Defender capability out of the box.

### 23.2. Security KPIs to Report

- Percentage of production images using **digest pinning**.
- Percentage of scanned images and remediation SLA for Critical/High CVEs.
- Percentage of Pods meeting Restricted security posture.
- Count of **`Deny`** blocks and **`Audit`/`Warn`** findings by team/namespace.
- Active exemptions, expired exemptions, or exemptions lacking owners.
- Percentage of workloads using managed/workload identities instead of static credentials.
- Workloads still using `privileged`/`hostPath`/`hostNetwork` with documented business justification and approval.
- Admission webhook availability and latency.
- Mean time from CVE disclosure to patched digest rollout.
- Security/observability cost and impact on release lead time.

Never celebrate "zero violations" if policies were disabled or all namespaces excluded. KPIs must always report **policy coverage** alongside violations.

## 24. Troubleshooting When Admission or Security Policies Block Rollouts

### 24.1. Errors to Distinguish

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| **`kubectl apply` Forbidden** | Missing Kubernetes RBAC | `kubectl auth can-i`, RoleBindings, context |
| **`admission webhook denied`** | Manifest violated a validating policy | Read policy name, message, and blocked fields |
| **`violates PodSecurity restricted`** | Root, privileged, capabilities, or seccomp non-compliant | Check `securityContext` and PSS version |
| **Deployment exists yet 0 Pods** | ReplicaSet Pod creation rejected by admission | `kubectl describe rs/deployment`, Events |
| **`ImagePullBackOff`** | ACR role, network, tag, or digest error | Kubelet identity, Pod Events, registry, DNS |
| **`CrashLoopBackOff`** | Image pulled yet app crashed | `kubectl logs`, entrypoint, filesystem permissions |
| **`CreateContainerConfigError`** | Missing Secret/ConfigMap/key or volume | Describe Pod, inspect references |
| **403 from Key Vault / Blob** | Wrong workload identity/role or network issue | ServiceAccount, federation, data-plane RBAC |
| **Pod runs yet cannot reach SQL** | NetworkPolicy, DNS, firewall, Private Endpoint | Traffic matrix, CNI, effective routes |
| **Webhook timeout** | Admission backend/TLS/network failure | Webhook service, certificates, timeout/`failurePolicy` |
| **Policy compliant yet image has CVEs** | Policy only inspects manifest structure; scanners run separately | Scan/Defender findings and live digest |
| **Kubernetes API still permits privileged Pod** | Namespace not enforcing, exemption, wrong scope | Namespace labels, bindings, constraints, policy effects |

### 24.2. Kubernetes Diagnostic Commands

~~~bash
NS="orders-security-lab"

kubectl get namespace "$NS" --show-labels

kubectl get deployments,replicasets,pods -n "$NS"

kubectl get events -n "$NS" --sort-by=.lastTimestamp

kubectl describe deployment orders-api -n "$NS"

kubectl get pods -n "$NS" -o wide
~~~

If a Pod already exists, use its real name:

~~~bash
POD="<pod-name>"

kubectl describe pod "$POD" -n "$NS"

kubectl logs "$POD" -n "$NS" --tail=100
~~~

If a Pod **was never created due to admission**, **no application logs exist** to read. Inspect **ReplicaSet events, webhook logs, and API admission denials** instead of retrying `kubectl logs` repeatedly.

### 24.3. When a Legitimate Workload Conflicts with Policy

1. Confirm workload owner, namespace, and blocking policy.
2. Identify the exact violating field.
3. Remediate the image/manifest: non-root user, writable temp volume, drop capabilities, pin digest.
4. Test with **server-side dry-run** or in a staging namespace.
5. If a business exception is genuinely required, issue a scoped, time-bound, audited exception with an owner.
6. Never weaken cluster-wide policy for a single legacy app.
7. Post-deploy, verify Ready status, dependency connectivity, and scanner results.

### 24.4. When Webhook Infrastructure Fails

- Check whether webhook controller/Pods are Ready.
- Check Service/Endpoints and API server connectivity per AKS architecture.
- Check TLS CA bundle, certificate expiry, and rotation mechanics.
- Check CPU/memory saturation, network policies, and timeouts.
- Check **`failurePolicy`** and real impact on API availability.
- Recover via an approved runbook.

**Never delete an arbitrary `MutatingWebhookConfiguration` or `ValidatingWebhookConfiguration`** just to "unblock" a deployment—that strips cluster-wide security guardrails.

## 25. Phased Policy Rollout

Rolling out guardrails on a production cluster must be managed like a controlled software release.

### 25.1. Phase 1 — Inventory

Collect:

- Namespaces and owners.
- Workloads/DaemonSets using root, privileged, `hostPath`, or `hostNetwork`.
- Image registries and whether digests are pinned.
- Secrets/static credentials and ServiceAccounts.
- Existing NetworkPolicies and ingress/egress requirements.
- Active build pipelines and scanners.
- Stale Pods running old versions with no rebuild plan.
- Infrastructure components requiring legitimate exemptions.

### 25.2. Phase 2 — Audit/Warn

- Enable **PSA `warn`/`audit`** on pilot namespaces.
- Assign Azure Policy definitions in **`Audit`** mode where appropriate.
- Group violations by team.
- Triage false positives and legacy workloads.
- Remediate images/manifests and validate in staging.
- Build an exception register with expiration dates.

### 25.3. Phase 3 — Scoped Enforce

- Start with lower-risk namespaces.
- Enable **PSA `enforce`** or admission **`Deny`** for vetted rules.
- Validate rollouts, CI/CD deploys, and autoscaling scale-out.
- Monitor `FailedCreate` events and webhook latency.
- Expand gradually across production with explicit owner sign-off.

### 25.4. Phase 4 — Continuous Compliance

- Scan and rebuild images regularly.
- Govern signing keys and identities.
- Audit exceptions and revoke them upon expiration.
- Re-test policies during AKS/Kubernetes version upgrades.
- Measure policy coverage and meaningful block rates.
- Rehearse admission outages and policy rollbacks.
- Report residual risk to operations leadership.

**Note:** A `Deny` policy primarily blocks new mutations; **it does not automatically fix already-running resources**. Schedule rolling replacements for legacy non-compliant Pods.

## 26. Runbook: Responding to a Vulnerable or Malicious Image

Hypothetical incident: a scanner flags an exploitable CVE in **`orders-api@sha256:...`**, running across several namespaces.

### 26.1. Response Steps

1. Validate the alert: exact CVE, exact image digest, and which workloads actually run it.
2. Assess exposure and exploitability per environment.
3. Notify owners/SecOps; declare an incident if warranted.
4. Block further deploys of the risky digest via CI/CD and admission controls.
5. Build a patched image, scan, sign/attest, and publish the new digest.
6. Roll out safely with health checks and error-rate monitoring.
7. If compromise is suspected, preserve forensic logs, audit identities/secrets, contain blast radius, and rotate credentials per incident response.
8. Verify all clusters and namespaces have eliminated the vulnerable digest.
9. Review policy exemptions, image retention, root cause, and monitoring gaps.

### 26.2. Do Not Delete Pods to "Fix a CVE"

If the Deployment still references the vulnerable image, the controller immediately recreates Pods running the exact same image. Deleting Pods without updating the Deployment and image source **is not remediation**.

Likewise, rushing an untested emergency image onto incompatible runtimes can cause an outage; balance containment speed, safe rollout, and rollback readiness according to risk.

## 27. Cost and Operations

Image/admission security adds ownership cost to AKS, yet prevents far larger outages and security incidents.

| Component | Potential Cost / Operational Impact |
|---|---|
| ACR | Registry SKU, image/layer storage, build tasks, networking/geo-replication per features |
| Microsoft Defender for Containers | Plan/feature licensing for scanning, posture, runtime, or node coverage per current pricing |
| Azure Policy / Gatekeeper / Kyverno | Policy governance plus cluster CPU/RAM for controllers/webhooks and telemetry |
| AKS node pools | Compute, managed disks, and capacity for workloads plus policy agents |
| Azure Monitor / Log Analytics | Ingestion, retention, alerting, and Kubernetes audit logs |
| Network | Private Endpoints, NAT Gateways, firewalls, and egress per topology |
| CI/CD & scanning | Build minutes/runners, scanners, artifact signing/key management |
| Operations | CVE triage, false-positive handling, exceptions, version upgrades, and incident response |

Never assume **enabling the Azure Policy add-on is zero-overhead**. Controllers/webhooks consume CPU/memory and require maintenance, and telemetry logs incur ingestion charges.

### 27.1. Effectiveness Metrics

Beyond raw violation counts, track:

- Mean time from CVE discovery to patched release.
- Images deployed outside standard CI/CD.
- Admission latency and webhook error rates.
- Incidents caused by over-privileged Kubernetes/Entra roles.
- Secrets eliminated from images and repos.
- Percentage of nodes/Pods covered by runtime monitoring.
- Deployments blocked legitimately by policy vs app bugs.
- Scanner, log retention, controller, and test-environment spend.

Good controls reduce risk **without creating an unmanaged single point of failure**.

## 28. Pre-Production AKS Security Checklist

- [ ] Approved registry/repository allowlist is defined.
- [ ] CI/CD enforces source, dependency, image build, and CVE scanning controls.
- [ ] Production images use versioning and digest pinning per policy.
- [ ] Signatures/provenance are verified by an actually enforcing solution if required.
- [ ] CI/CD push, kubelet pull, and workload identities are separate and least-privilege.
- [ ] ACR permission mode (RBAC/ABAC) and role assignments are verified.
- [ ] ACR admin passwords and long-lived Docker registry credentials are avoided unless strictly required.
- [ ] PSA Baseline/Restricted enforced appropriately per namespace.
- [ ] Azure Policy / admission engine has clear owners, scopes, effects, and time-bound exceptions.
- [ ] Policies inspect all relevant resource kinds and container types.
- [ ] Containers run non-root where feasible, without privilege escalation, dropping capabilities, with seccomp.
- [ ] Root filesystem is read-only where appropriate, with bounded writable temp mounts.
- [ ] No sensitive `hostPath` mounts or host namespaces outside approved exceptions.
- [ ] Dedicated ServiceAccounts, least-privilege Kubernetes RBAC, and disabled token automount when unused.
- [ ] Workload Identity / Key Vault configured for Azure data-plane access.
- [ ] Kubernetes Secrets governed cleanly; zero secrets in images, Git, or logs.
- [ ] NetworkPolicies enforced by the CNI with explicit allow rules for DNS and dependencies.
- [ ] `ResourceQuota`/`LimitRange`, `requests`/`limits`, and node isolation properly sized.
- [ ] Monitoring covers admission denials, webhook timeouts, image CVEs, and runtime alerts.
- [ ] Runbooks exist for webhook outages, urgent CVEs, and policy-blocked Pods.
- [ ] Tested rollouts/rollbacks, time-bound exceptions, and workload backups/DR.
- [ ] Costs tracked across ACR, AKS, Defender, logs, and policy components.

## 29. Hands-On Exercises

### Exercise 1: Security Layering

Given the Orders pipeline: Git → JAR build → Docker image → ACR → AKS → Azure SQL.

Diagram at least six control layers. Identify which layer addresses CVEs, provenance, allowed registries, Pod privileges, data identity, network isolation, and runtime detection.

### Exercise 2: PSA in a Staging Namespace

In a lab AKS cluster:

1. Create namespace **`orders-security-lab`**.
2. Label it **`warn=restricted`** and **`audit=restricted`**.
3. Test a privileged Pod manifest with **`kubectl apply --dry-run=server`**.
4. Record the warnings.
5. Enable **`enforce=restricted`**.
6. Re-run the manifest and observe the denial message.
7. Explain why already-running legacy Pods are not automatically evicted.

Never perform this on system or production namespaces.

### Exercise 3: Hardening a Java API

A Java app needs port 8080 and temp writes to **`/tmp`**. Write a Deployment with a non-root UID, `RuntimeDefault` seccomp, drop `ALL` capabilities, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `emptyDir` `/tmp`, `requests`/`limits`, and probes.

Then explain why the image/Dockerfile must be built to support these settings.

### Exercise 4: Allowed ACR Policy

Suppose the organization allows images only from **`acrordersprod.azurecr.io`**. Write an expression validating image prefixes in `containers`/`initContainers` and list the limitations of that check. Compare **allowed registry**, **digest pinning**, **signature verification**, and **CVE scanning**.

### Exercise 5: Workload Identity

A Pod needs to read Blob Storage without needing rights to edit Deployments:

1. Distinguish kubelet identity from workload identity.
2. Specify the ServiceAccount and namespace.
3. Describe the OIDC issuer, federated credential, and data-plane role.
4. Explain why granting `AcrPull` to the Pod does not grant Blob read access.
5. Resolve a 403 from Blob without assigning subscription-wide Owner.

### Exercise 6: NetworkPolicy

Design default-deny for **`orders-security-lab`**, then allow only DNS, internal ingress requests, and outbound traffic to approved dependencies. List prerequisites regarding the network plugin/CNI, DNS, and Private Endpoints.

### Exercise 7: Admission Incident

A Deployment is accepted by the API yet creates zero Pods; Events report **`FailedCreate`** and **`violates PodSecurity restricted`**.

- Which resource do you inspect first?
- Why shouldn't you start with Pod logs?
- When do you fix the Dockerfile versus the manifest?
- If an emergency exception is required, what bounds must it carry?
- How do you prove the remediated rollout is both compliant and Healthy?

### Exercise 8: Newly Disclosed CVE

A production image develops a Critical CVE three weeks after release. Plan triage, rebuild, scan, signing, rollout, digest verification, secret revocation/rotation if warranted, and auditing namespaces still running the old version.

### Self-Check Questions

1. Why don't image scanning and admission policies replace each other?
2. Does `imagePullPolicy: Always` make an image tag immutable?
3. Do digests and image signatures serve the exact same purpose?
4. Which security levels and actions does PSA support?
5. When raising a namespace to Restricted, are currently running Pods automatically deleted?
6. How do fail-closed and fail-open admission webhooks differ?
7. Why can a Deployment succeed while its ReplicaSet fails to create Pods?
8. How does Kubernetes RBAC differ from admission policy?
9. When should you use the Azure Policy add-on instead of writing custom Gatekeeper/Kyverno?
10. Does an Azure Policy "allowed registry" definition automatically verify image signatures?
11. Does `readOnlyRootFilesystem` require changing how a Java app writes temp files?
12. Why doesn't Workload Identity directly solve kubelet image pulls?
13. Does Kubernetes `NetworkPolicy` work if the CNI does not enforce it?
14. Can a validly signed image still contain CVEs?
15. When a Pod does not exist due to admission denial, which events should you read?
16. Why should indefinite namespace exemptions be avoided?
17. Why must scanners keep monitoring for new CVEs after an image is deployed?
18. Does a policy reporting 100% compliance while applied to zero namespaces provide meaningful security?

## 30. References

- [Security concepts for Azure Kubernetes Service](https://learn.microsoft.com/azure/aks/concepts-security)
- [AKS security best practices for clusters and workloads](https://learn.microsoft.com/azure/aks/operator-best-practices-cluster-security)
- [Microsoft Defender for Containers overview](https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction)
- [Understand Azure Policy for Kubernetes](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes)
- [Azure Policy add-on for AKS](https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-kubernetes#install-the-azure-policy-add-on-for-aks)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)
- [Kubernetes admission controllers](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)
- [Kubernetes Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)
- [Kubernetes security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [ACR RBAC and ABAC repository permissions](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication)
- [Sigstore Cosign documentation](https://docs.sigstore.dev/cosign/overview/)
- [Azure Kubernetes Service pricing](https://azure.microsoft.com/pricing/details/kubernetes-service/)
