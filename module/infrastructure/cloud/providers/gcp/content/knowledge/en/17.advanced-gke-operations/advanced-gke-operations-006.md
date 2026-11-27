# Cloud Service Mesh and Service-to-Service Communication Security

In an e-commerce platform running on Google Kubernetes Engine (GKE), `checkout` calls `orders-api`, which then calls `payments`. Kubernetes Services locate target endpoints, yet **network reachability does not equal API authorization**. If a Pod is compromised, an attacker may try calling internal services the original application never needed to access.

**Cloud Service Mesh (CSM)** adds a *service-to-service* control layer: workload identity, encrypted connections via **mutual TLS (mTLS)**, fine-grained authorization via **AuthorizationPolicy**, and centralized telemetry. This lesson belongs to the **Advanced GKE and Operations** chapter of the `CLOUD_PROVIDERS_GCP` module, connecting project/IAM/VPC administration with Compute Engine, GKE, Cloud Run, storage, databases, release automation, reliability, and cost.

**Example scope:** GKE uses **managed Cloud Service Mesh with Istio APIs and Envoy sidecars**. Cloud Service Mesh also supports Google Cloud APIs, Envoy/proxyless gRPC, and other environments; configurations for those models **cannot be copied verbatim** from the `security.istio.io` resources shown here.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **control plane** and **data plane**, as well as Istio APIs and Google Cloud APIs.
2. Explain mTLS, workload identity, trust domains, and certificate issuance/rotation.
3. Distinguish `PeerAuthentication`, `AuthorizationPolicy`, and `RequestAuthentication` from IAM, NetworkPolicy, and gateways.
4. Execute a tested rollout path of **PERMISSIVE → STRICT mTLS → least-privilege authorization**.
5. Author policies allowing only `checkout-sa` to call required endpoints on `orders-api`.
6. Inspect sidecars, `403`/`503` errors, and traffic logs, and roll back policy changes safely.
7. Evaluate mesh limitations, reliability, and costs before adopting in production.

## 1. What Problem Does a Service Mesh Solve?

Suppose three Kubernetes Services exist in namespace `commerce`:

| Service | Kubernetes ServiceAccount (KSA) | Business flow |
| --- | --- | --- |
| `checkout` | `checkout-sa` | Accepts orders, calls `orders-api` |
| `orders-api` | `orders-sa` | Processes orders, calls `payments` |
| `payments` | `payments-sa` | Processes payments |

Security requirement: **only `checkout-sa` may invoke order creation/read endpoints**; a `reporting` Pod must not be allowed to call `orders-api` merely because it sits in the same VPC or namespace.

~~~mermaid
flowchart LR
    C["checkout Pod<br/>KSA: checkout-sa"]
    CP["Envoy sidecar"]
    OP["Envoy sidecar"]
    O["orders-api Pod<br/>KSA: orders-sa"]
    P["payments"]
    U["Unauthorized Pod"]
    M["Managed control plane<br/>policy + identity + config"]
    C --> CP
    CP -->|"mTLS"| OP
    OP --> O --> P
    U -. "Blocked by policy" .-> OP
    M -. "xDS/policy/certs" .-> CP
    M -. "xDS/policy/certs" .-> OP
~~~

In the sidecar model, **Envoy** sits alongside the application container and handles traffic intercepted through the proxy. Policies are enforced at the destination proxy; Java applications typically do not manage mTLS certificates directly. Still, a mesh **does not automatically make an application with broken authorization secure**: business-logic authorization, Google API IAM, network isolation, and secret management remain essential.

## 2. Control Plane, Data Plane, and Deployment Options

| Component | Responsibility |
| --- | --- |
| **Control plane** | Distributes proxy configs, service discovery, routing, security policies, and certificate metadata |
| **Data plane** | Envoy sidecars handling live request traffic; enforces mTLS, policies, routing, and emits telemetry |
| **Certificate authority (CA)** | Issues short-lived workload certificates; may use Mesh CA or CA Service per supported configuration |
| **Fleet** | Manages membership and managed mesh across supported GKE clusters |
| **Istio APIs** | Kubernetes CRDs such as `PeerAuthentication`, `AuthorizationPolicy`, `VirtualService` |
| **Google Cloud APIs** | Another CSM configuration path; uses corresponding Cloud resources/APIs rather than arbitrary Istio CRDs |

For **GKE on Google Cloud**, current guidance recommends **managed Cloud Service Mesh**: Google manages the control plane and supported data plane components. For new GKE users, the managed control plane uses a **Traffic Director**-based implementation supporting Istio APIs. Some older fleets run an `ISTIOD` control plane with a modernization path; **never assume every cluster uses the exact same control plane implementation**.

**Key point:** the term "Traffic Director" in `implementation` does not mean you must abandon Istio APIs in the GKE configuration shown here. Conversely, Google Cloud Service Routing / Network Security APIs or proxyless gRPC belong to a separate configuration track requiring their own docs and feature matrix.

## 3. Three Identity and Authentication Layers Not to Confuse

| Layer | Technology | Question answered |
| --- | --- | --- |
| **Peer authentication** | Workload **mTLS** certificates | Which workload identity is calling? |
| **End-user/request authentication** | JWT/OIDC via `RequestAuthentication` | Which user/client token accompanies the request? |
| **Authorization** | `AuthorizationPolicy` | Which workload/path/method is that identity allowed to call? |
| **Google Cloud resource IAM** | IAM and Workload Identity Federation for GKE | Is the Pod allowed to read Cloud Storage / Secret Manager / BigQuery? |

A KSA like `checkout-sa` maps to a workload identity recognized by the mesh. Cloud Service Mesh uses a trust domain and certificates, typically in SPIFFE format:

~~~text
spiffe://PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa
~~~

Inside the `source.principals` field of an Istio `AuthorizationPolicy`, the standard format **omits the `spiffe://` prefix**:

~~~text
PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa
~~~

**Replace `PROJECT_ID` with the real trust domain** from your mesh configuration; do not assume `cluster.local` or a Google IAM service account email is the mTLS identity. In-cluster meshes using Citadel CA may use a different trust domain. For multi-cluster setups, verify roots of trust, trust domains, and fleet memberships.

## 4. mTLS: Encrypting Communication Is Not Authorization

With mTLS, **both client and server** present certificates for mutual authentication over an encrypted channel. The mesh handles certificate issuance and rotation via the configured CA.

| `PeerAuthentication.mtls.mode` setting | Behavior |
| --- | --- |
| `PERMISSIVE` | Accepts both plaintext and mTLS; helpful during migration |
| `STRICT` | Accepts only mTLS on targeted workloads/ports |
| `UNSET` | Inherits parent-level policy |
| `DISABLE` | **Not supported** in managed Traffic Director `PeerAuthentication`; do not use in managed CSM templates |

**Auto mTLS** may be enabled by default, yet client proxies still send **plaintext to workloads without sidecars**, and servers in `PERMISSIVE` mode still accept plaintext. Therefore, "mesh enabled" **does not mean all traffic enforces mTLS**.

### 4.1. Enforce STRICT on `orders-api` First

Once legitimate callers have sidecars and health/probe/gateway paths are tested, apply a workload-scoped policy:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: orders-strict
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  mtls:
    mode: STRICT
~~~

Only Pods labeled `app: orders-api` in this namespace are governed by this policy. When rolling out across a namespace, omit the selector in namespace `commerce`. When enforcing **mesh-wide**, place a selectorless policy in root namespace `istio-system` per CSM guidance; never enforce cluster-wide on the very first test.

**Caution:** callers bypassing sidecars, probes, or misconfigured gateways can fail once `STRICT` takes effect. Validate impact before production changes.

## 5. AuthorizationPolicy: Who Can Call Which Endpoint?

`PeerAuthentication` guarantees peer identity and encryption; it **does not restrict** callers so that only `checkout` can reach `orders`. `AuthorizationPolicy` defines which identities, HTTP methods/paths, or ports are permitted.

Example allowing only KSA `checkout-sa` to call `GET` and `POST` on the orders API:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: orders-from-checkout
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/orders", "/api/orders/*"]
~~~

**Conditions for this sample to work as intended:**

- `PROJECT_ID.svc.id.goog` matches the source workload's real trust domain.
- Callers use mTLS so the proxy can populate `source.principal`.
- Backend Pods carry label `app: orders-api` and traffic passes through the proxy.
- The API protocol is recognized as HTTP; raw TCP cannot evaluate HTTP methods/paths as general conditions.
- No **other broad `ALLOW` policy** matches the workload and permits unwanted callers.

In Istio authorization, **`DENY` is evaluated before `ALLOW`**; if any `ALLOW` policy applies, a request must match at least one `ALLOW`. When no `ALLOW` policy applies to a workload, the default behavior is generally allow unless a `DENY` policy or another control blocks it.

### 5.1. Default Deny Can Cause an Outage

To deny all requests by default to workloads in namespace `commerce`, create an `action: ALLOW` policy **with no rules**:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: default-deny
  namespace: commerce
spec:
  action: ALLOW
~~~

This policy **does not override narrower `ALLOW` policies**. Instead, requests not matched by any other `ALLOW` policy are denied. **Do not deploy it before inventorying every flow** to `checkout`, `orders`, `payments`, gateways, health checks, and service agents—otherwise the application can stop serving traffic.

### 5.2. Why Avoid `ALLOW rules: [{}]`?

In `AuthorizationPolicy`, `rules: [{}]` with `action: ALLOW` is a rule that **matches every request**, unintentionally opening access. By contrast, **omitting `rules` / empty rules** means *allow nothing*. Distinguish these two carefully when reviewing YAML or Helm templates.

### 5.3. Scope Policies by Workload Rather Than Namespace

`selector.matchLabels` binds a policy to selected Pods. A selectorless policy applies across the entire namespace. Prefer **dedicated KSAs per service**, stable labels, GitOps workflows, and verifying which Pods a policy selects rather than sharing generic `app` labels across workloads.

## 6. User JWTs vs. Workload Certificates

Suppose end users call an API through a gateway carrying a JWT. `RequestAuthentication` verifies the token's **issuer, JWKS, and audience** where supported:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: orders-jwt
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  jwtRules:
    - issuer: "https://issuer.example.com/"
      jwksUri: "https://issuer.example.com/.well-known/jwks.json"
      audiences: ["orders-api"]
~~~

**This is an illustrative sample:** the URLs do not point to a real identity provider. Crucially, **`RequestAuthentication` alone does not require a JWT on every request**: requests without a token can still pass through. To require a JWT, pair it with an `AuthorizationPolicy` checking `requestPrincipals: ["*"]` on permitted paths, combined with mTLS principals when both **service identity and user identity** are needed.

Never substitute client-supplied JWTs for workload mTLS in internal calls, nor treat service-to-service mTLS as proof that an end user is authorized for a business action.

## 7. Preparing the GKE Cluster and Namespace Safely

The following assumes **managed Cloud Service Mesh is already provisioned**, the GKE cluster runs a supported version, belongs to a **fleet**, Workload Identity Federation for GKE is configured as needed, and your account has permission to inspect mesh and Kubernetes resources. **Never run policy-changing commands in production without approval.**

### 7.1. Read-Only Checks

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID

gcloud container fleet mesh describe \
  --project=FLEET_PROJECT_ID

kubectl config current-context
kubectl get namespace commerce --show-labels
kubectl get pods -n commerce
kubectl get peerauthentication,authorizationpolicy,requestauthentication -n commerce
~~~

In the fleet mesh output, check **`controlPlaneManagement.state`**, **`dataPlaneManagement.state`**, and **`implementation`**. `ACTIVE` shows managed component health—**it does not guarantee every Pod already has a sidecar**.

### 7.2. Enabling Sidecar Injection Matching the Control Plane

For managed Cloud Service Mesh's **Traffic Director implementation** using Istio APIs, GKE docs prescribe the default label:

~~~bash
kubectl label namespace commerce \
  istio.io/rev- istio-injection=enabled --overwrite
~~~

This command **modifies the namespace**; check control plane type, migration plans, and existing labels first. Other control planes or release channels may use different revision labels; never blindly apply `istio.io/rev=asm-managed` to every cluster.

Injection occurs only when **new Pods are created**. For existing deployments, perform a controlled rollout (targeting a specific Deployment):

~~~bash
kubectl rollout restart deployment/orders-api -n commerce
kubectl rollout status deployment/orders-api -n commerce
~~~

Verify the sidecar container:

~~~bash
kubectl get pods -n commerce \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}'
~~~

Each `orders-api` Pod should list both the application container and `istio-proxy` in the Envoy sidecar model. If missing, halt the `STRICT` mTLS step and inspect the injection webhook, namespace labels, Pod annotations, policies, and control plane version.

**Never run `rollout restart` across all Deployments** without checking PodDisruptionBudgets, readiness probes, and capacity.

## 8. Lab: Testing Allow and Deny Between Two Service Accounts

**Assumptions:** namespace `commerce` is enrolled in managed CSM, sidecars are active, and `orders-api.commerce.svc.cluster.local:8080` is a Kubernetes Service exposing HTTP `GET /api/orders` returning `200` when unblocked. Adjust paths and ports to match your real app.

### 8.1. Two Client Identities

Use two ServiceAccounts **in the lab namespace**; if these names are already used by production apps, avoid colliding with production:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-sa
  namespace: commerce
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: untrusted-sa
  namespace: commerce
---
apiVersion: v1
kind: Pod
metadata:
  name: test-allowed
  namespace: commerce
spec:
  serviceAccountName: checkout-sa
  containers:
    - name: curl
      image: curlimages/curl:8.12.1
      command: ["sleep", "3600"]
---
apiVersion: v1
kind: Pod
metadata:
  name: test-denied
  namespace: commerce
spec:
  serviceAccountName: untrusted-sa
  containers:
    - name: curl
      image: curlimages/curl:8.12.1
      command: ["sleep", "3600"]
~~~

This sample uses a public curl image; in egress-restricted environments, use an **approved digest/image from Artifact Registry**. Launch the test Pods after enabling injection, and confirm both run `istio-proxy`, reach Ready, and receive workload certificates.

### 8.2. Applying Narrowly Scoped Policies

1. Confirm `PeerAuthentication` from section 4 targets only `orders-api`.
2. Confirm no other broad `ALLOW` policy applies to the backend.
3. Replace `PROJECT_ID` in `orders-from-checkout` with the **real trust domain**.
4. Apply the YAML in the authorized lab environment and wait for proxy config sync.
5. Run requests from **both client Pods**:

~~~bash
kubectl exec -n commerce test-allowed -c curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  http://orders-api.commerce.svc.cluster.local:8080/api/orders

kubectl exec -n commerce test-denied -c curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  http://orders-api.commerce.svc.cluster.local:8080/api/orders
~~~

**Expected result:** `checkout-sa` is permitted by the `ALLOW` policy and sees HTTP `200` if the app returns 200; `untrusted-sa` is rejected, typically with HTTP `403` from the proxy. If the permitted client receives `404` or `500`, separate application bugs from mesh authorization. A Pod lacking a sidecar may fail the mTLS handshake (connection error) rather than receiving HTTP 403.

### 8.3. Additional Negative Tests

| Test | Expected outcome if section 5 policy is accurate |
| --- | --- |
| `checkout-sa` calls `GET /api/orders` | Allowed if application handles it |
| `untrusted-sa` calls the same endpoint | Denied |
| `checkout-sa` calls `DELETE /api/orders/123` | Denied because method is not in `ALLOW` |
| Sidecarless Pod calls `orders-api` under `STRICT` mTLS | Plaintext connection fails |
| Authorized client hits an app bug | May get app 4xx/5xx; not an mTLS failure |

In production, never treat `200` alone as proof of security. Verify **mTLS peer identity**, policy matching, and logs; then verify negative tests fail as intended.

### 8.4. Clean Up the Lab Intentionally

Delete the two **test Pods** and `untrusted-sa` when finished. **Do not delete `checkout-sa`** if live workloads use it. For policies, roll back only lab-created policies after confirming impact on remaining security flows.

## 9. Gateways, Egress, and Flows Not Automatically Protected by the Mesh

| Flow | Controls needed |
| --- | --- |
| Internet client → app | HTTPS/TLS at load balancer/ingress gateway, Cloud Armor where appropriate, API auth/authz |
| Gateway → in-mesh backend | mTLS/identity and `AuthorizationPolicy` for the **gateway identity** where permitted |
| Service A → Service B in mesh | `PeerAuthentication STRICT` + least-privilege `AuthorizationPolicy` |
| Pod → Google APIs | IAM/Workload Identity Federation, VPC egress, and VPC Service Controls if needed |
| Pod → external systems | Egress gateway/proxy, DNS, firewalls, NetworkPolicy, and target-side controls |
| Cloud Run ↔ GKE mesh | Integrate/route per supported CSM features; never assume Cloud Run is a sidecarred Pod |

**An ingress gateway does not automatically secure all Internet ingress.** Beyond in-mesh mTLS, handle client TLS, end-user auth, WAF/rate limiting, gateway policies, and risks of direct traffic bypassing the gateway.

Account for **port exceptions, `hostNetwork` Pods, traffic bypassing sidecar interception, out-of-mesh endpoints**, and managed CSM limits. A service mesh does not replace **Kubernetes NetworkPolicy**, GKE Dataplane V2, or VPC firewalls; use network segmentation to eliminate unintended bypass paths.

## 10. Observing mTLS, Policy Denials, and Reliability

Cloud Service Mesh integrates with Cloud Logging, Cloud Monitoring, and Cloud Trace depending on feature configuration. On GKE managed mesh, **traffic logs** are typically enabled by default; **Envoy access logs** are separate and not necessarily enabled.

Signals to monitor:

| Signal | Helps answer |
| --- | --- |
| Request rate, p95/p99 latency, 4xx/5xx | Are mesh policies introducing errors or latency? |
| mTLS auth policy and source principal | Is the expected workload calling the expected endpoint? |
| Authorization denials | Are denials valid blocks or accidental business-traffic drops? |
| Envoy proxy readiness / config sync | Are sidecars receiving updated configs and certs? |
| Pod CPU/memory, restarts | How does sidecar overhead affect autoscaling and capacity? |
| Cloud Trace request spans | Which hop in the call chain adds latency? |
| Cloud Billing logs/metrics | Is telemetry inflating costs? |

Read-only policy and log checks:

~~~bash
kubectl get peerauthentication,authorizationpolicy,requestauthentication -A

# Envoy container logs (request access logs appear only if enabled)
kubectl logs -n commerce deployment/orders-api \
  -c istio-proxy --tail=100
~~~

In **Logs Explorer**, search Cloud Service Mesh **server/client traffic logs** by cluster and service; verify exact log names and resource labels against your active setup. Starting example:

~~~text
logName="projects/PROJECT_ID/logs/server-accesslog-stackdriver"
resource.labels.namespace_name="commerce"
~~~

Never print JWTs, `Authorization` headers, or personal data in access logs. Log volume, trace sampling, and metric retention all carry cost implications.

## 11. Deploying Policies Without Causing Outages

1. **Inventory** service-to-service flows: caller KSAs, namespaces, services/ports, HTTP methods/paths, gateways, cron jobs, health probes, and external endpoints.
2. **Verify mesh readiness** per cluster/namespace: Pods have sidecars and valid workload identities.
3. **Migrate mTLS:** keep `PERMISSIVE` during transition; enable `STRICT` on canary workloads, then namespaces/mesh once coverage is verified.
4. **Test authorization** with narrowly scoped `AuthorizationPolicy` rules; validate allow and deny with real client identities. Use dry-run annotations where supported by your CSM version and telemetry.
5. **Tighten access** by KSA + operation; never open `ALLOW` to all principals/paths just to clear an error.
6. **Review changes via GitOps/IaC**, measuring latency, 403/503 rates, mesh telemetry, Java app health, and rollout impact.
7. **Prepare rollback:** preserve prior manifests, a list of newly added policies, owners, and rollback criteria.
8. **Expand across namespaces/clusters** only once SLOs hold and zero legitimate flows are blocked.

Any `PeerAuthentication` or `AuthorizationPolicy` change can **immediately impact production traffic** once distributed by the control plane; never treat policy YAML as zero-risk.

### 11.1. Rollback Order During an Incident

- Determine whether requests fail at the **TLS handshake**, **`AuthorizationPolicy`**, or **application**.
- Revert only the newly changed policy or canary rather than deleting all mesh security.
- Keep verified policies protecting other business flows intact.
- After rolling back, re-run negative tests to ensure access was not unintentionally widened.

## 12. Troubleshooting: 403, 503, TLS, and Missing Sidecars

| Symptom | Common cause | What to check |
| --- | --- | --- |
| HTTP `403` from Envoy | Missed `ALLOW`, matched `DENY`, bad JWT, or wrong principal | `AuthorizationPolicy`, traffic logs, trust domain, labels |
| Connection reset / SSL error after `STRICT` | Caller lacks sidecar or mismatched TLS mode | Pod injection, `PeerAuthentication`, `DestinationRule` |
| HTTP `503`, `no healthy upstream` | Missing endpoints, unsynced Envoy, failing readiness probe | Service/endpoints, proxy readiness, health checks |
| Pod missing `istio-proxy` | Wrong namespace label, injection disabled, or stale Pod | `kubectl get ns --show-labels`, rollout status |
| Policy has no effect | Selector mismatch, traffic bypasses proxy, unsynced config | Pod labels, CRD status, logs/xDS |
| HTTP method/path unexpectedly denied | Policy omits health path, gRPC path differs, or route rewrite | Actual route, logs, policy `operation` fields |
| Mesh TLS works, Google API returns `403` | Missing IAM / Workload Identity permissions | GKE KSA-to-IAM mapping, resource policy, audit logs |
| JWT verified yet anonymous requests pass | Only `RequestAuthentication` created without `AuthorizationPolicy` | `requestPrincipals`, effective `ALLOW` policies |
| Proxy CPU/memory spikes, Pod restarts | Sidecar overhead, tight resource limits | Per-container metrics, node pressure |
| External calls ignore mesh policy | Bypassed sidecar, unconfigured egress gateway | VPC routes, NetworkPolicy, `ServiceEntry`/gateway |

**Do not diagnose every `403` as an IAM error**: mesh authorization, the API application, gateways, and Google IAM can all return denials. Check response headers, caller identity, proxy/access logs, and recent policy timestamps.

## 13. Cost and Limitations

A mesh adds **Envoy sidecars** (CPU/memory), networking overhead, certificate management, telemetry, and potentially service tier/edition charges. In autoscaled GKE clusters, sidecar resource requests/limits reduce how many Pods fit per node, which can raise node counts and bills.

Optimize around three principles:

- Enroll **workloads genuinely needing service-to-service controls**, rather than forcing every utility Pod into the mesh unnecessarily.
- Measure **latency, CPU, memory, and log volume** overhead before and after; balance log retention against investigation needs.
- Check **Cloud Service Mesh / GKE / Observability pricing** and feature limits for your managed control plane. Do not assume every upstream Istio feature is fully supported.

**A mesh is not a substitute for HA architecture**: applications still require readiness/liveness probes, PodDisruptionBudgets, multi-zone capacity, load balancing, backups, IAM, and dedicated SLOs.

## 14. End-to-End Scenario: Securing `checkout` → `orders` → `payments`

**Requirements:** `checkout` creates orders; `orders-api` calls `payments`; `reporting` reads aggregated data only from a separate API; all internal flows require mTLS and deny unlisted callers by default.

Design:

| Communication pair | Control |
| --- | --- |
| `checkout-sa` → `orders-api` | `STRICT` mTLS + `ALLOW` by principal/method/path |
| `orders-sa` → `payments` | Separate `ALLOW` policy on `payments` for `orders-sa` |
| `reporting-sa` → `orders-api` | No matching `ALLOW`; denied |
| Ingress gateway → `checkout` | Gateway TLS, client auth, and ingress-tier policy |
| `orders-api` → Cloud SQL / Storage | IAM/Workload Identity and private networking—**not** `AuthorizationPolicy` in place of IAM |

Roll out to **one canary workload/namespace**, run positive/negative tests, and only then broaden default-deny and `STRICT`. Record `403/503` rates, latency, and resource overhead before and after to confirm both security and SLO compliance.

## 15. Self-Check Questions

**1. If a client has network reachability to `orders-api`, is it authorized to call the API?**

*Answer:* No. Network reachability and service authorization are distinct; use `AuthorizationPolicy` by workload identity and operation.

**2. With auto mTLS enabled, can you guarantee all internal requests are encrypted?**

*Answer:* No. `PERMISSIVE` mode and sidecarless callers can still use plaintext; plan a deliberate move to `STRICT`.

**3. Does mTLS authenticating `checkout-sa` prove an end user is authorized to place an order?**

*Answer:* No. Peer workload identity is separate from end-user JWTs and business authorization.

**4. Why doesn't `RequestAuthentication` enforce JWT presence by itself?**

*Answer:* It validates JWTs when presented, but requires an `AuthorizationPolicy` such as `requestPrincipals: ["*"]` to reject requests lacking a JWT.

**5. Should `principals` use a Google IAM SA email or a SPIFFE-based trust domain?**

*Answer:* Use the mesh principal, e.g., `PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa` matching your configured CA/trust domain; do not default to IAM emails.

**6. How does a namespace default-deny `ALLOW` policy with no rules differ from an `ALLOW` policy with `rules: [{}]`?**

*Answer:* No rules → matches nothing (denies); an empty rule `{}` → matches every request (allows all).

**7. Enabling `STRICT` on `orders` breaks a sidecarless client. Why?**

*Answer:* The backend accepts only mTLS, while the out-of-mesh client sends plaintext; onboard the client or route via a compatible gateway.

**8. Does a `403` when calling BigQuery from a meshed Pod always come from `AuthorizationPolicy`?**

*Answer:* No. It can come from IAM, Workload Identity, VPC Service Controls, or the API itself; inspect logs layer by layer.

**9. Why doesn't `kubectl label namespace ... istio-injection=enabled` add sidecars to existing Pods right away?**

*Answer:* Injection happens at Pod creation time; you must roll out Deployments and verify newly created Pods.

**10. Does a mesh replace VPC firewalls, NetworkPolicy, and Cloud Armor?**

*Answer:* No. The mesh governs flows passing through its data plane; network and edge controls block bypass paths and protect Internet ingress.

## 16. Pre-Production Checklist

- [ ] Selected the right managed control plane, Istio/Google Cloud API model, and verified feature support.
- [ ] Fleet/cluster/namespace properly configured; workload Pods have sidecars and dedicated KSAs.
- [ ] Trust domain and CA verified; never assumed principals are IAM emails.
- [ ] Tested `STRICT` mTLS on canary workloads, including health checks, gateways, and legacy callers.
- [ ] `AuthorizationPolicy` scoped by workload, principal, method/path/port with no accidental allow-alls.
- [ ] Dedicated policies defined for gateways, jobs, service agents, and out-of-mesh flows.
- [ ] JWT validation paired with `AuthorizationPolicy` requiring tokens where end-user auth is needed.
- [ ] IAM, VPC, NetworkPolicy, and Cloud Armor/ingress cover remaining layers.
- [ ] Tested both permitted and blocked clients, measuring logs, latency, CPU, and memory.
- [ ] GitOps reviews, rollback manifests, SLO alerts, and on-call owners ready.
- [ ] Projected data plane, telemetry, and GKE capacity costs.
- [ ] Re-verify policies after every change to KSAs, service labels, gateways, or topology.

## 17. Conclusion

**Cloud Service Mesh secures service-to-service communication on three pillars: workload identity, mTLS, and policy-based authorization.** Auto mTLS eases migration, yet **`STRICT` mTLS plus least-privilege `AuthorizationPolicy`** is what enforces internal boundaries. Examples here use Istio APIs for compatible GKE managed mesh setups; in production, always verify control plane type, trust domain, feature support, and bypass/edge flows before enforcing.

## Official References

- [Cloud Service Mesh overview](https://cloud.google.com/service-mesh/docs/overview)
- [Provision managed control plane on GKE](https://cloud.google.com/service-mesh/docs/onboarding/provision-control-plane)
- [Cloud Service Mesh security overview](https://cloud.google.com/service-mesh/docs/security/security-overview)
- [Configure transport security and STRICT mTLS](https://cloud.google.com/service-mesh/docs/security/configuring-mtls)
- [AuthorizationPolicy overview](https://cloud.google.com/service-mesh/docs/security/authorization-policy-overview)
- [Supported Istio APIs for managed Cloud Service Mesh](https://cloud.google.com/service-mesh/docs/onboarding/api-support)
- [Cloud Service Mesh security best practices](https://cloud.google.com/service-mesh/docs/security/anthos-service-mesh-security-best-practices)
- [Request proxy traffic logs](https://cloud.google.com/service-mesh/docs/observability/access-logs)
- [Cloud Service Mesh pricing](https://cloud.google.com/service-mesh/pricing)
