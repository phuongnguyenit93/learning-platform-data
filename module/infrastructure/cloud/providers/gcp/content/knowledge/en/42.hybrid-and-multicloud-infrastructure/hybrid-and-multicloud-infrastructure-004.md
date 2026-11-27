# Connect Gateway and Fleet-Based Cluster Access

## 1. Problem Statement: Managing Kubernetes in Hybrid and Multicloud Infrastructure

An organization may simultaneously operate GKE on Google Cloud, Kubernetes in an on-premises data center, and clusters on AWS or Azure. Each cluster typically has its own API server, private network, authentication mechanism, and Kubernetes RBAC. If engineers must connect to separate VPNs, configure bastion hosts, or store multiple kubeconfig files containing long-lived credentials, operations become hard to control and audit.

**Fleet** provides a way to group and manage a set of clusters within a logical scope on Google Cloud. **Connect Gateway** is a managed access path enabling users or service accounts to run Kubernetes commands against fleet-registered clusters. Administrators can use `kubectl`, the Google Cloud console, or automation systems under supported models without building a separate public proxy for every API server.

Key design goals include:

- Discovering fleet clusters from a centrally managed membership inventory.
- Using Google Cloud identities or federated enterprise identities instead of distributing static credentials per person.
- Applying Google Cloud IAM to control who can use the gateway.
- Applying Kubernetes RBAC **per cluster** to decide which resources each identity can read or modify.
- Reducing the need to open inbound firewalls or expose public Kubernetes API endpoints for clusters outside Google Cloud.
- Maintaining controlled cluster administration from the console, laptops, or CI/CD pipelines within authorized boundaries.

Connect Gateway is not an application load balancer, does not replace VPC/VPN/Cloud Interconnect for data-plane traffic, does not create fleet memberships automatically, and does not grant `cluster-admin` by default. It is primarily an access path for the **Kubernetes API/control plane**.

Within the **CLOUD_PROVIDERS_GCP** module, this lesson connects knowledge of organizations/projects, IAM, VPCs, GKE, CI/CD, reliability, and hybrid infrastructure. The same identity and policy model can support monitoring, health checks, and controlled deployments across multiple clusters, even when workloads live on different clouds.

## 2. Three Core Concepts: Fleet, Membership, and Gateway

### 2.1. Fleet

A Fleet is a logical grouping of Kubernetes clusters and related resources that enables multi-cluster governance on Google Cloud. A fleet is managed through a **fleet host project**. Clusters may reside in different physical or cloud environments yet appear together in the fleet inventory.

A fleet does not merge all control planes into a single Kubernetes API; each cluster retains its own Kubernetes API server, upgrade schedule, nodes, namespaces, and RBAC. Commands executed through the gateway still target **one specific membership**.

### 2.2. Membership

Each cluster registered to a fleet has a **membership resource** in Google Cloud. A membership has a name and a location (which may be `global` or a specific location depending on cluster type and registration method).

Examples:

~~~text
projects/FLEET_PROJECT_ID/locations/global/memberships/onprem-hanoi
projects/FLEET_PROJECT_ID/locations/global/memberships/eks-orders
~~~

These names are illustrative only. Do not assume the location is always `global`: operators must obtain the actual membership location from listing or describing the resource.

Memberships are used to discover and select target clusters. A membership name does not necessarily match the source cloud's cluster name or an old Kubernetes context name.

### 2.3. Connect Gateway and Connect service

Connect Gateway is a Google-managed API for authenticated clients to access the Kubernetes API of fleet clusters. For **clusters that are not GKE on Google Cloud**, requests typically traverse the Connect service and the Connect Agent running inside the cluster, then reach the API server. Connect Agent proactively maintains outbound connections to supported Google Cloud endpoints; this architecture avoids opening inbound ports from the internet to the Kubernetes API server just to use the gateway.

For **GKE clusters on Google Cloud**, the path can connect directly through the gateway's GKE integration and **does not require Connect Agent** for gateway access. Do not mechanically enforce agent-checking steps for every GKE cluster. Cluster type and integration version determine which components are actually required.

### 2.4. Request flow diagram

~~~mermaid
flowchart TB
    U[Operator / CI service account] --> AUTH[gcloud credentials or identity federation]
    AUTH --> GW[Connect Gateway API]
    GW --> IAM{Allowed by Google Cloud IAM?}
    IAM -- No --> DENY1[Blocked at gateway]
    IAM -- Yes --> TYPE{Cluster type}
    TYPE -- GKE on Google Cloud --> GK[GKE Kubernetes API]
    TYPE -- On-prem / attached / outside GCP --> CONNECT[Connect service]
    CONNECT --> AGENT[Connect Agent in cluster]
    AGENT --> API[Kubernetes API server]
    GK --> RBAC{Kubernetes RBAC}
    API --> IMP{Agent allowed to impersonate?}
    IMP -- No --> DENY2[Blocked in cluster]
    IMP -- Yes --> RBAC
    RBAC -- No --> DENY3[Forbidden]
    RBAC -- Yes --> OK[Read / modify resources per permissions]
~~~

The diagram depicts logical control layers. Exact paths and authentication components may vary across GKE, attached clusters, GKE Distributed Cloud, and identity modes. Consult the documentation specific to the deployed cluster type.

## 3. How Does Connect Gateway Differ From Direct Kubernetes Connectivity?

| Aspect | Direct API server connection | Via Connect Gateway |
|---|---|---|
| Endpoint | Private IP/DNS of the API server | Google Cloud-managed gateway endpoint bound to the membership |
| Cluster discovery | Manually maintain endpoint list | List fleet memberships |
| Client authentication | Per API server or provider mechanism | Google Cloud identity / supported federation options |
| Authorization | Kubernetes RBAC and provider mechanisms | IAM at gateway, plus RBAC inside the cluster |
| Laptop access | Often requires VPN, peering, or bastion | Access gateway over suitable connectivity without reaching cluster's private network |
| Clusters outside Google Cloud | May require opening ingress to the API server | Connect Agent maintains outbound connection from cluster to Connect service |
| Observability/audit | Cluster and separate infrastructure logs | Adds Google Cloud API audit logs alongside Kubernetes logs |
| When gateway is unavailable | Direct admin path may still remain | Admin access via gateway is lost; requires a break-glass plan |

The gateway **does not replace** per-cluster emergency operations mechanisms. Platform teams should maintain controlled break-glass admin access and an independent connectivity path if connectivity to Google Cloud or the Connect service fails.

## 4. Prerequisites

### 4.1. Tools and projects

Prepare the following:

1. A project designated as the fleet host project with appropriate administrative permissions.
2. A Kubernetes cluster eligible for/already registered to the fleet; registration steps depend on cluster type.
3. Up-to-date Google Cloud CLI and a `kubectl` version compatible with the server.
4. A valid Google Cloud identity (user, service account, or federated workforce identity).
5. IAM permissions for the gateway and matching RBAC permissions inside the cluster.
6. An admin kubeconfig **with direct cluster access** to bootstrap RBAC initially, if the cluster does not yet have gateway policies configured.
7. Network egress for Connect Agent and external authentication components if the cluster type requires the agent.

Project names, memberships, namespaces, accounts, and contexts in the commands below are placeholders. Never run them verbatim in production; verify targets before making any IAM or RBAC changes.

### 4.2. Enabling required Google Cloud APIs

Per the Connect Gateway setup guide, administrators can enable the following APIs on the fleet host project:

~~~bash
gcloud services enable \
  connectgateway.googleapis.com \
  gkeconnect.googleapis.com \
  gkehub.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=FLEET_PROJECT_ID
~~~

This list applies to the basic `kubectl`/gateway path. If logging in solely via the Google Cloud console, requirements for enabling `connectgateway.googleapis.com` may differ. With Google Groups, GKE Identity Service, or federation, additional APIs and configuration may be needed. Do not bulk-enable APIs without checking Organization Policies and service governance processes.

The operator running this command needs the `serviceusage.services.enable` permission or a suitable role such as Service Usage Admin. This is a bootstrap task for platform admins, not a permission granted to every operator.

### 4.3. Checking existing memberships

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID
~~~

The output shows membership names, external IDs, and related details. If a cluster is not yet registered, follow the procedure **for that exact cluster type**: GKE on Google Cloud, GKE attached cluster, GKE Distributed Cloud, or self-managed Kubernetes. Commands and Connect Agent behavior may differ.

Do not confuse `gcloud container clusters list` with `gcloud container fleet memberships list`: listing GKE clusters in one project does not list all clusters registered to a fleet.

## 5. Agent and Networking for Clusters Outside Google Cloud

### 5.1. Role of Connect Agent

On clusters that are not GKE on Google Cloud, Connect Agent establishes a secure connection from the cluster to the Connect service on Google Cloud and forwards authorized requests from the gateway to the Kubernetes API server.

For the agent to function, you typically need:

- The agent pod/deployment installed per the registration workflow.
- The cluster able to resolve DNS and send HTTPS/TLS egress to the required endpoints.
- Network policies, firewalls, proxies, and certificates not blocking the connection.
- The agent's service identity configured per the supported method.
- Necessary Kubernetes permissions for the agent to forward requests and impersonate identities per policy.
- A healthy Kubernetes API server reachable by the agent at its internal endpoint.

**Never expose a public IP for the API server just to troubleshoot an agent issue.** Check egress, DNS, proxies, and logs first. If private egress or a corporate proxy is used, verify hostnames, SNI, CA trust, and allow policies against documentation for that cluster type.

### 5.2. GKE on Google Cloud is a different case

Current Google Cloud documentation states that the gateway connects directly to GKE clusters without requiring Connect Agent. If an operator does not see a `gke-connect` namespace on a registered GKE cluster, do not jump to the conclusion that Connect Gateway is broken.

Conversely, for clusters outside Google Cloud, errors indicating no active connections typically require inspecting the agent and Connect service. When registering clusters via CLI, agent installation flags and defaults have evolved across tool versions, so consult the registration guide for your specific cluster type and CLI version rather than assuming it is always installed.

### 5.3. Not a data plane

Connect Gateway is for Kubernetes API administration. End-user HTTP traffic to cluster services, data replication, database connections, or cross-cloud pod-to-pod traffic **does not flow through the gateway like a service mesh**.

Connecting hybrid/multicloud workloads requires separate design: VPC, Cloud VPN, Cloud Interconnect, peering, DNS, firewalls, ingress, service mesh, or another supported mechanism. Running `kubectl get pods` successfully via the gateway does not mean pods can reach a database in another cloud.

## 6. Two Authorization Layers: IAM and Kubernetes RBAC

### 6.1. Google Cloud IAM controls the gateway

IAM determines whether an identity may call the Connect Gateway API and fetch membership connection details. Common predefined roles include:

| Role | Primary responsibility | Notes |
|---|---|---|
| `roles/gkehub.viewer` | View memberships and support fetching kubeconfig details | Does not grant permission to read all pods |
| `roles/gkehub.gatewayReader` | Read-only gateway access | Typically used for operational observability |
| `roles/gkehub.gatewayEditor` | Gateway read/write | Still requires matching Kubernetes RBAC |
| `roles/gkehub.gatewayAdmin` | Gateway administration and permission for supported streaming APIs | Granted to a small group; not automatically Kubernetes `cluster-admin` |

The `gkehub.gateway.stream` permission is required for `kubectl exec`, `attach`, `cp`, and `port-forward` over the gateway; among predefined gateway roles, `roles/gkehub.gatewayAdmin` includes this permission. When streaming is not needed, do not automatically grant Admin just to run simple read commands.

Gateway roles are granted at the Google Cloud scope matching the membership/fleet project and organizational policies. Google Cloud role scopes are **distinct** from Kubernetes namespaces.

### 6.2. Kubernetes RBAC decides what you can do inside the cluster

Once a request reaches the API server, Kubernetes RBAC checks permissions via `Role` or `ClusterRole` attached by `RoleBinding`/`ClusterRoleBinding`. For non-GKE clusters using the agent, an additional policy must allow Connect Agent to **impersonate** the user or service account behind the request.

Thus, an operation must pass both checks:

~~~text
Identity allowed to use Connect Gateway?     IAM: YES
Connect Agent allowed to impersonate?        Bootstrap RBAC: YES (when agent is needed)
Identity allowed to get/list pods?           Cluster RBAC: YES
==================================================
Result                                       ALLOWED
~~~

If IAM allows it but Kubernetes RBAC denies it, the request still fails. If RBAC allows it but the gateway IAM role is missing, the request is blocked before reaching the Kubernetes API server.

### 6.3. Distinguishing end identity from Connect Agent identity

Two principals have distinct responsibilities:

- **End caller** (e.g., `alice@example.com` or a CI/CD service account): authenticated at the gateway; must hold both IAM roles and Kubernetes permissions.
- **Connect Agent**: forwards requests to the Kubernetes API server and needs permission to impersonate the caller's identity when the connection path requires it.

Never grant `cluster-admin` to everyone simply because the agent uses impersonation. Agent impersonation permissions and end-user resource permissions are two separate policies.

## 7. Example: Granting Read-Only IAM to Operators

Suppose an SRE team needs to observe pods in cluster `onprem-hanoi` without modifying deployments.

An administrator grants IAM on the fleet host project:

~~~bash
gcloud projects add-iam-policy-binding FLEET_PROJECT_ID \
  --member="user:sre-reader@example.com" \
  --role="roles/gkehub.viewer"

gcloud projects add-iam-policy-binding FLEET_PROJECT_ID \
  --member="user:sre-reader@example.com" \
  --role="roles/gkehub.gatewayReader"
~~~

The email here is illustrative; in production, verify exact subjects and follow access approval workflows. Use Google Groups where supported by the environment and authentication setup to reduce per-user management; do not assume group support is enabled automatically on every cluster type.

IAM permissions complete only the first step. Users still need Kubernetes RBAC for the target namespaces, plus the agent impersonation policy where required.

## 8. Creating Namespace-Scoped Kubernetes RBAC

### 8.1. Declaring read-only permissions

Example granting read access to pods/deployments in namespace `team-a`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: workload-reader
  namespace: team-a
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
~~~

This Role applies only within namespace `team-a`. If operators need to read `namespaces` or `nodes` (cluster-scoped resources), a separate `ClusterRole` and binding are required. Avoid granting cluster-wide permissions when only one namespace needs observation.

### 8.2. Binding permissions to a user

Example `RoleBinding` for a user, applied on the cluster after confirming proper identity mapping:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sre-reader-team-a
  namespace: team-a
subjects:
  - kind: User
    name: sre-reader@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: workload-reader
  apiGroup: rbac.authorization.k8s.io
~~~

`subjects[].name` must match the identity seen by the cluster through the gateway. With group-based authentication or identity federation, subject formats vary by provider and cluster setup; do not blindly change `kind: User` to `Group` without proper group-propagation mechanisms.

### 8.3. Configuring impersonation policies with the helper tool

For clusters requiring Connect Agent, Google Cloud provides a command to generate RBAC including both the required impersonation policy and corresponding binding:

~~~bash
gcloud container fleet memberships generate-gateway-rbac \
  --membership=onprem-hanoi \
  --role=role/team-a/workload-reader \
  --users=sre-reader@example.com \
  --project=FLEET_PROJECT_ID \
  --kubeconfig=PATH_TO_DIRECT_ADMIN_KUBECONFIG \
  --context=DIRECT_ADMIN_CONTEXT
~~~

First create role `team-a/workload-reader` with direct admin access and inspect the generated YAML output. After reviewing subjects, namespaces, and permissions, an administrator can re-run with `--apply`. This is a bootstrap operation that **modifies cluster RBAC**; it should not be run by read-only users and must not grant `clusterrole/cluster-admin` just "for a quick test."

The kubeconfig path and context in the bootstrap command must point to the **direct admin connection of the exact cluster**, not a gateway context for another cluster. You can run `kubectl config current-context` and `kubectl get ns --context=DIRECT_ADMIN_CONTEXT` to confirm beforehand, only when authorized.

The `generate-gateway-rbac` command and flags may evolve; always check the help output of your Google Cloud CLI version. For organizations managing RBAC via GitOps, review and apply the YAML through a protected pipeline instead of manual edits.

## 9. Accessing a Fleet Membership With kubectl

### 9.1. Logging in with gcloud

The operator logs in with a Google Cloud identity holding the required IAM roles:

~~~bash
gcloud auth login
gcloud config set project FLEET_PROJECT_ID
~~~

If using Workforce Identity Federation, follow the provider's sign-in flow. Never store access tokens, kubeconfigs containing credentials, or key files in source control.

### 9.2. Fetching the gateway kubeconfig

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID

gcloud container fleet memberships get-credentials onprem-hanoi \
  --project=FLEET_PROJECT_ID \
  --location=global
~~~

Replace `global` with the membership's actual location. `get-credentials` configures `kubeconfig` so the client routes requests via the gateway and may **switch the current context**. Inspect `kubectl config get-contexts` and confirm the active context afterward.

Use the `KUBECONFIG` environment variable pointing to a separate file when working across multiple clusters to avoid accidentally overwriting an active admin context. Never manually edit the server URL in a gateway kubeconfig; regenerate it with a current gcloud CLI version when needed.

### 9.3. Running read-only commands

~~~bash
kubectl config current-context
kubectl get pods -n team-a
kubectl get deployments -n team-a
kubectl auth can-i get pods -n team-a
kubectl auth can-i delete deployments -n team-a
~~~

With a read-only role in `team-a`, the expected result is seeing pods/deployments in that namespace and **being denied deployment deletion**. `kubectl get namespaces` may fail if the operator lacks permission to list cluster-scoped resources; that is proper RBAC enforcement, not a gateway bug.

Never run `kubectl apply`, `delete`, `rollout restart`, or `patch` during read-only testing. For production, log a change ticket before any mutating operation.

### 9.4. Verifying context and location

When managing multiple fleet memberships, acting on the wrong context can affect the wrong cluster. Always verify:

- Active fleet host project.
- Membership name and location.
- Kubeconfig file in use.
- `kubectl config current-context`.
- Target namespace.
- Final identity and effective RBAC roles.

Prefer scripts that validate project, context, and namespace—especially before operations with side effects.

## 10. Using Service Account Impersonation for Automation

A CI/CD pipeline must not rely on a developer's personal Google Cloud permissions. Create a dedicated service account for read or deployment actions via the gateway.

Example using temporary impersonation settings in gcloud:

~~~bash
gcloud config set auth/impersonate_service_account \
  fleet-deployer@FLEET_PROJECT_ID.iam.gserviceaccount.com

gcloud container fleet memberships get-credentials onprem-hanoi \
  --project=FLEET_PROJECT_ID \
  --location=global
~~~

The source user or workload must have appropriate permission to impersonate the service account (e.g., Token Creator in impersonation flows). The target service account must also hold gateway IAM roles, membership viewer access, and Kubernetes RBAC on the cluster. **Permission to impersonate a service account does not automatically grant Kubernetes permissions.**

After finishing, use an isolated gcloud config or unset impersonation so subsequent commands do not inadvertently continue acting under that identity:

~~~bash
gcloud config unset auth/impersonate_service_account
~~~

In external CI such as GitHub Actions, prefer Workload Identity Federation for short-lived credentials rather than storing long-lived service account JSON keys. Deployment jobs should have access only to memberships and namespaces belonging to the target environment. Separate staging and production pipelines with distinct identities and approvals.

## 11. Google Groups and External Identity Providers

### 11.1. Group-based access governance

As operator headcount grows, assigning IAM and RBAC per email becomes hard to maintain. You can combine Google Groups with GKE Identity Service and Connect Gateway group support to authorize by group in **supported environments**.

Conceptual workflow:

1. The organization maintains SRE or application team groups in its identity system.
2. Administrators configure group support for the corresponding cluster type.
3. IAM gateway roles are granted to the group or principal set.
4. Kubernetes RBAC bindings reference group names supported by the cluster authentication component.
5. Verify that new members gain access and departing members actually lose access.
6. Monitor claim/group membership size limits and authentication logs.

Do not assume all attached clusters and GKE versions support Google Groups identically; check group setup docs for your exact cluster type and note support limits and prerequisites.

### 11.2. Third-party workforce identities

Enterprises can use Microsoft Entra ID, Okta, or other OIDC/SAML identity providers via **Workforce Identity Federation** so employees can log in and receive IAM permissions on Google Cloud. This differs from **Workload Identity Federation**, which is for non-human applications/workloads.

When using third-party identities:

- Map subject/group claims accurately.
- Use attribute conditions to restrict identity providers/trust.
- Grant gateway IAM roles to properly scoped workforce principals/principal sets.
- Configure the Kubernetes side to recognize the matching subjects and groups.
- Verify revocation, token expiry, auditing, and header/claim limits.
- Never copy Google user email syntax directly into RBAC for federated principals if documentation specifies a different format.

## 12. Streaming Commands: exec, attach, cp, and port-forward

Certain `kubectl` commands open long-lived streaming connections, unlike standard GET/LIST requests:

- `kubectl exec`: run commands inside a container.
- `kubectl attach`: attach to a running process.
- `kubectl cp`: transfer files via the underlying stream mechanism.
- `kubectl port-forward`: tunnel to a pod/service port through the Kubernetes API.

Connect Gateway imposes additional prerequisites for these commands:

1. Requires the `gkehub.gateway.stream` IAM permission; among predefined roles, `roles/gkehub.gatewayAdmin` includes this permission.
2. Requires Kubernetes RBAC on `pods/exec`, `pods/attach`, or `pods/portforward` subresources depending on the command.
3. Per current gateway guidance, the cluster must run Kubernetes **1.30 or higher** for `attach`/`cp`/`exec` and **1.31 or higher** for `port-forward`; the `kubectl` client needs **1.31 or higher**.
4. Streaming permissions should be restricted to break-glass/investigation groups with approval, not granted by default to everyone reading pods.

A user might run `kubectl get pods` successfully yet fail on `kubectl exec` due to missing stream permissions, missing subresource RBAC, or unmet version requirements. That is not necessarily a network failure.

Never `exec` into production workloads to inspect secrets, dump environments, or view sensitive data without proper authorization and controlled procedures.

## 13. Integrating With CI/CD and GitOps

### 13.1. Pipeline pattern

Connect Gateway can support automation using kubeconfig to inspect status or deploy manifests to fleet clusters. A single pipeline can deploy the same workload type across GKE, on-premises, and attached clusters using different contexts.

~~~mermaid
flowchart LR
    SRC[Reviewed Git commit] --> CI[Build + test]
    CI --> ART[Artifact Registry image digest]
    ART --> CD[Approval / deploy job]
    CD --> ID[CI service account]
    ID --> GW[Connect Gateway]
    GW --> S[Staging fleet membership]
    GW --> P[Production fleet membership]
    S --> V[Smoke / readiness verification]
    P --> MON[Monitoring + rollback]
~~~

Separate service accounts per environment and never allow untrusted pull-request pipelines to receive production gateway permissions. If using Cloud Deploy with GKE attached clusters, consult the guide for **attached targets**, as the rollout execution service account must have matching IAM/RBAC on the target cluster.

### 13.2. Safe operational steps

A controlled deployment flow:

1. Build the image once and store it by immutable digest.
2. Scan, test, and record provenance.
3. An approved pipeline obtains short-lived credentials for the deploy service account.
4. Fetch the gateway kubeconfig for the staging membership.
5. Deploy and verify readiness/rollout within the authorized namespace.
6. Run smoke tests.
7. Promote to production after approval, reusing the exact same image digest.
8. Monitor SLOs, error rates, and latency; halt or roll back on regressions.

Never commit long-lived kubeconfigs to repositories. If a job temporarily generates a kubeconfig, keep it in an ephemeral workspace and delete it afterward. Even without static private keys, a kubeconfig exposes cluster endpoints and contexts.

### 13.3. Boundary between deploy permissions and cluster administration

A deployment job only needs permissions to manage Deployments, Services, ConfigMaps, or specific resources in its namespace. Never grant `cluster-admin` merely to update an image. Changes to ClusterRoles, CRDs, admission webhooks, namespaces, nodes, and networking generally belong to a separate platform pipeline with distinct approvals.

Use RBAC and policy-as-code to detect drift; never allow CI to escalate its own permissions at deploy time.

## 14. Security and Risk Controls

### 14.1. Defense in depth

A sound design enforces controls at every layer:

| Layer | Recommended controls |
|---|---|
| Identity | MFA or federation, short-lived credentials, account lifecycle management |
| Fleet inventory | Clearly named memberships, project governance, and ownership |
| IAM | Appropriate Gateway Reader/Editor/Admin, membership viewer, periodic access reviews |
| Agent/connection | Egress controls, TLS, service identity, health monitoring |
| Kubernetes RBAC | Namespace-scoped Roles, no indiscriminate `cluster-admin` |
| Workload runtime | NetworkPolicy, Pod Security, secret handling, namespace isolation |
| Change management | GitOps/reviews, approvals, CI/CD separation, auditing |
| Incident response | Break-glass path, IAM/RBAC revocation, logs, restore plan |

Connect Gateway protects only the gateway access path. It does not automatically block all direct paths to the Kubernetes API server. If static kubeconfigs or public endpoints still exist, control those paths independently.

### 14.2. Least-privilege principle

Example read-only SRE group for namespace `team-a`:

- Google Cloud IAM: `gatewayReader` + `gkehub.viewer`.
- Kubernetes RBAC: Role reading pods/deployments in namespace `team-a`.
- Agent impersonation: configured for end users per guidance if required.
- No `cluster-admin`, no Secret creation rights, no streaming unless required.

Example application release team:

- IAM: `gatewayEditor` + viewer (or narrower suitable permissions).
- RBAC: update Deployments and view status in assigned namespaces.
- Approvals: separated between production and staging.
- Cannot modify RBAC, CRDs, or cluster-scoped resources without authorization.

A principal allowed by IAM to perform updates can still be blocked by Kubernetes RBAC if missing `patch` or `update` verbs; that is the intended behavior of two-layer authorization.

### 14.3. Auditing and sensitive data

Monitor:

- Cloud Audit Logs for activities related to the gateway, IAM, and fleet memberships per service logging capabilities.
- Kubernetes API server audit logs capturing actor, verb, resource, namespace, and outcome.
- Connect Agent/Identity Service logs when forwarding or authentication issues arise.
- History of IAM and RBAC modifications, linked to approved tickets/commits.
- Logins/impersonations by user accounts, service accounts, and workforce identities.

Avoid logging access tokens, kubeconfigs containing sensitive details, credential provider responses, or secret payloads. When debugging with `kubectl -v`, restrict log access and scrub sensitive fields before sharing.

## 15. Layered Troubleshooting

When `kubectl` cannot reach a cluster via the gateway, narrow down the issue from the outside in rather than immediately granting broader permissions.

### 15.1. Diagnostic workflow

~~~mermaid
flowchart TD
    A[kubectl via gateway fails] --> B{Membership in fleet?}
    B -- No --> C[Check project, location, registration]
    B -- Yes --> D{gcloud auth and IAM valid?}
    D -- No --> E[Check user/SA, gateway role, viewer]
    D -- Yes --> F{Gateway kubeconfig valid?}
    F -- No --> G[Regenerate get-credentials, check context]
    F -- Yes --> H{Cluster reachable?}
    H -- No --> I[Check Connect Agent / egress / DNS / API server]
    H -- Yes --> J{RBAC and impersonation valid?}
    J -- No --> K[Check gateway impersonation RBAC + user RoleBinding]
    J -- Yes --> L[Check resource, namespace, version, streaming permissions]
~~~

### 15.2. Common scenario table

| Symptom | Possible cause | How to inspect |
|---|---|---|
| Membership not found | Wrong project/location or not registered to fleet | `gcloud container fleet memberships list` and membership metadata |
| `get-credentials` denied | Missing gateway/`gkehub.viewer` role or wrong login | Check gcloud account, project, IAM bindings |
| Kubeconfig points to wrong gateway endpoint | Outdated CLI or stale context | Update CLI and re-run `get-credentials`; do not edit manually |
| No active connections | Agent disconnected or not installed on non-GCP cluster | Inspect `gke-connect` namespace, pod/logs, DNS/egress |
| `Forbidden` from Kubernetes API | User missing RoleBinding or agent cannot impersonate | Check both RBAC policy types |
| Can view pods, cannot view nodes | Namespace-only Role; nodes are cluster-scoped | May be intentional authorization; do not grant ClusterRole blindly |
| `exec`/`port-forward` blocked | Missing stream permission/RBAC or outdated version | Check IAM role, subresource RBAC, and kubectl/K8s versions |
| Group identity not recognized | Group support unconfigured or wrong claim | Check Identity Service, groups, federation mappings |
| Connection succeeds but commands are slow | Network/agent/API server overload, client timeout | Track latency, agent logs, API server health |
| Auth plugin error | Missing `gke-gcloud-auth-plugin` or incompatible CLI | Install plugin, update CLI, regenerate kubeconfig |

### 15.3. Reading agent logs in the right place

For non-GKE clusters where Connect Agent fails, inspect `gke-connect` workloads via a **direct admin kubeconfig** (if the gateway itself is disconnected). Check pod status, restarts, events, DNS, proxies, and egress. Do not try to use a broken gateway `kubectl` path to diagnose the gateway itself while ignoring direct access.

For directly connected GKE clusters, inspect memberships, IAM, kubeconfig, and control plane first instead of looking for an optional/unneeded agent.

### 15.4. Distinguishing 401, 403, and broken connections

- **401/unauthenticated:** token, login, credential helper, or identity provider.
- **403 at gateway:** insufficient IAM permissions to call the gateway API.
- **403 from Kubernetes:** user RBAC or impersonation policy denies access.
- **Network/connection error:** membership not connected, Connect Agent lost egress, unhealthy control plane, or blocked gateway path.
- **404/resource not found:** wrong membership, namespace, resource name, or endpoint; verify which cluster the request hit first.

Error messages can vary across CLI/API versions; inspect response sources, audits, and logs to pinpoint the blocking layer. Never "fix" every error with `roles/owner` or `cluster-admin`.

## 16. Reliability, Availability, and Break-Glass Planning

The gateway is a dependency in the Kubernetes management path. If Google Cloud APIs, the identity provider, DNS, internet egress, or Connect Agent experience an outage, operators may temporarily lose gateway access even while cluster workloads keep running normally.

You should maintain:

- A direct management path with scoped, controlled, and audited permissions when the gateway is unavailable.
- Separate runbooks for GKE clusters on Google Cloud and clusters outside Google Cloud.
- Monitoring for Connect Agent status, membership state, and API latency.
- Credential rotation and time-bound emergency access procedures.
- Drills simulating egress loss, identity provider outages, and agent recovery.
- Incident classification: control plane, gateway, IAM, or application issue.
- Never make business-critical application data flows depend on Connect Gateway for real-time data exchange.

Do not assume enabling the gateway improves data-plane availability or performs cluster failover. It provides a consistent management path; workload DR/HA strategies must be designed separately.

## 17. Practical Scenario: GKE and EKS Clusters in the Same Fleet

A company operates:

- `gke-prod`: GKE on Google Cloud.
- `eks-orders`: an Amazon EKS cluster registered to the fleet.
- `onprem-reporting`: Kubernetes in the data center.
- The SRE team needs read access to pods/deployments; the platform team holds admin rights; the release pipeline needs to update deployments in namespace `orders`.

### 17.1. Design

1. The fleet host project holds memberships for all three clusters.
2. Identify which clusters use Connect Agent and their corresponding network egress needs.
3. The SRE team receives IAM `gatewayReader` and `gkehub.viewer`; read-only Kubernetes RBAC in the namespaces they need to inspect.
4. The platform team retains IAM/RBAC bootstrap and incident-response rights; do not grant these to all developers.
5. The deploy pipeline uses a dedicated service account and short-lived tokens, with gateway access restricted to target-environment memberships.
6. Non-GCP clusters have agent impersonation policies and RoleBindings for end identities.
7. Production deployments require approval and reuse the exact image digest verified in staging.
8. Monitor Cloud Audit Logs, Kubernetes API audit logs, agent health, and application SLOs.

### 17.2. Verification steps

In an authorized test environment:

~~~bash
gcloud container fleet memberships list --project=FLEET_PROJECT_ID

gcloud container fleet memberships get-credentials eks-orders \
  --project=FLEET_PROJECT_ID \
  --location=MEMBERSHIP_LOCATION

kubectl config current-context
kubectl get pods -n orders
kubectl auth can-i get pods -n orders
kubectl auth can-i delete pods -n orders
~~~

Expected outcomes for read-only SRE access:

- Membership appears in inventory.
- Gateway kubeconfig creates the right context.
- Can read pods in the authorized namespace.
- Cannot delete pods or modify Deployments.
- Audit logs record the corresponding identity and actions.
- Revoking either the IAM gateway role or Kubernetes RoleBinding blocks access at that respective layer.

Note: never perform ad-hoc permission changes/revocations in production as an impromptu test. Use a sandbox cluster and dedicated test accounts, with a runbook to restore permissions if testing impacts access.

### 17.3. Lessons learned

A team can standardize **connectivity and identity** yet still must protect each cluster's Kubernetes boundaries. Fleet/Gateway does not mean every cluster shares identical permissions or runtime characteristics. Authorization must reflect environment, namespace, responsibility, and risk level.

## 18. Pre-Production Operational Checklist

### Fleet and infrastructure

- [ ] Clusters registered to the right fleet host project; membership names/locations verified.
- [ ] GKE on Google Cloud distinguished from attached/on-prem/external clusters.
- [ ] Connect Agent installed where needed with appropriate network egress.
- [ ] Required APIs enabled; CLI/`kubectl`/auth plugin versions compatible.
- [ ] Ownership, runbooks, and break-glass paths documented.

### IAM, authentication, and RBAC

- [ ] Gateway IAM roles granted following least privilege.
- [ ] Viewer permissions granted for membership discovery where needed.
- [ ] Agent impersonation policies configured for clusters requiring the agent.
- [ ] Kubernetes Roles/RoleBindings scoped to genuinely required namespaces and resources.
- [ ] `cluster-admin` not granted when workloads/operators only need read access.
- [ ] Groups/third-party identities tested end-to-end if used.
- [ ] IAM and RBAC revocation verified to behave as designed.
- [ ] No sensitive tokens/keys/kubeconfigs stored in Git.

### Access and CI/CD

- [ ] Gateway kubeconfigs generated from the right membership and location.
- [ ] Every mutating operation validates project/context/namespace beforehand.
- [ ] CI/CD uses dedicated service accounts and short-lived credentials.
- [ ] Production deployments require approvals and narrow namespace permissions.
- [ ] Streaming commands granted only when required and version prerequisites are met.
- [ ] Gateway and cluster audit logs have appropriate retention.

### Reliability and security

- [ ] Dashboards/alerts cover Connect Agent, gateway access failures, and API server health.
- [ ] Response plans exist for gateway, identity provider, or egress outages.
- [ ] Gateway is never treated as a replacement for VPN/service mesh/data-plane networking.
- [ ] Emergency management path and responsible operator permissions tested.
- [ ] Periodic reviews prune unused IAM, RBAC, and stale memberships.

## 19. Self-Check Questions

1. How does a fleet differ from a Kubernetes cluster and a membership?
2. Why is Connect Gateway not a single shared Kubernetes API server for the entire fleet?
3. How does the request path differ between GKE on Google Cloud and clusters outside Google Cloud?
4. Why can a user who already has `gatewayReader` still receive `Forbidden` when reading pods?
5. Why does Connect Agent need an impersonation policy? Does that mean users are granted `cluster-admin`?
6. Why can `kubectl get namespaces` fail even when `kubectl get pods -n team-a` succeeds?
7. When is `roles/gkehub.gatewayAdmin` needed instead of `gatewayReader`/`Editor`?
8. How do you ensure `kubectl` commands do not accidentally target the wrong cluster?
9. Why should a read-only SRE group not receive streaming permissions by default?
10. Does Connect Gateway replace VPN, Interconnect, or a service mesh for workload traffic?
11. If an EKS cluster loses Connect Agent connectivity, which components must be checked?
12. How should a deployment pipeline using the gateway structure its service account, IAM, and Kubernetes RBAC?
13. Why is a break-glass admin path needed when the gateway or identity provider is unavailable?
14. When do group-based RBAC and Workforce Identity Federation require additional configuration?

## References

- [Connect to registered clusters with the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway)
- [Set up the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup)
- [Using the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/using)
- [Set up the Connect gateway with Google Groups](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup-groups)
- [Set up the Connect gateway with third-party identities](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup-third-party)
- [gcloud container fleet memberships get-credentials](https://docs.cloud.google.com/sdk/gcloud/reference/container/fleet/memberships/get-credentials)
- [GKE attached clusters overview](https://docs.cloud.google.com/kubernetes-engine/multi-cloud/docs/attached/eks/concepts/overview)
- [Cloud Deploy to GKE attached clusters](https://docs.cloud.google.com/deploy/docs/anthos-targets)
- [Kubernetes RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
