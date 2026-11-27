# Managing Configuration, Secrets, and Workload Identity

A container image should be deployable across dev, staging, and production without rebuilding just because a database URL, log level, or service name changes. At the same time, database passwords, API keys, tokens, and certificates must never be carelessly baked into images or source code. Workloads must also prove their own identity when calling cloud APIs, object storage, message queues, or internal services.

Three closely related concepts answer different questions:

- **Configuration:** What values does the application need to behave properly in a specific environment or with specific features?
- **Secret:** What sensitive values must be protected, provisioned, rotated, and revoked?
- **Workload identity:** Which application or process is requesting access, and how does the system verify it?

In the **CLOUD_ARCHITECTURE** module, managing these three areas properly enables replaceable and scalable compute/containers, restricts data access, supports deployment automation, and controls security, reliability, cost, and operational risks under a Well-Architected mindset.

## 1. Distinguishing Configuration, Secrets, and Identity

| Concept | Question to Answer | Examples | Typical Management Approach |
|---|---|---|---|
| **Configuration** | What behavior or endpoints does the app need in this environment? | Log level, feature flags, API URLs, timeouts, queue names | Config files, environment variables, config services |
| **Secret** | What sensitive values prove authorization or protect data? | Database passwords, API tokens, private keys, signing keys | Secret managers, KMS/key vaults, credential issuance mechanisms |
| **Workload identity** | Who/which process is calling the resource? | Booking API production, notification worker, CI deploy job | IAM roles, managed identities, service accounts, federation |
| **Authorization policy** | What is the identity allowed to do on which resources? | Booking API can only write booking data and invoke payment creation | IAM/RBAC, resource policies, application authorization |
| **Certificate/trust material** | How do we verify an endpoint or workload? | CA bundles, mTLS certificates | PKI, certificate managers, rotation processes |

A URL without embedded credentials is typically configuration; a connection string with an embedded password is sensitive data; a role name or service account identifier is identity metadata rather than a secret credential itself. Conversely, access keys and private keys used to prove authority must be protected.

Practical rules:

- Non-sensitive configuration can live in image defaults, ConfigMaps, config files, or environment variables depending on requirements.
- Secrets should be issued by a secret management system or short-lived credential mechanism; avoid placing them directly in images, Git, or logs.
- Workload identities should be issued and verified by the platform at runtime, avoiding team-created long-lived credentials.

## 2. Principles for Container Configuration Design

### 2.1. Separating Images from Environment Configuration

The same application image should run across multiple environments when code and configuration are properly decoupled:

~~~text
                    Same application image
                              |
                 +------------+------------+
                 |            |            |
                DEV         STAGING        PROD
                 |            |            |
              config-dev   config-stage  config-prod
                 |            |            |
                 +------ Runtime behavior -+
~~~

For example, the Booking API can reuse the exact same image:

| Value | Dev | Staging | Production |
|---|---|---|---|
| `APP_ENV` | `dev` | `staging` | `prod` |
| `LOG_LEVEL` | `debug` | `info` | `warn` |
| `PAYMENT_API_URL` | Sandbox endpoint | Staging endpoint | Private production endpoint |
| `DB_POOL_MAX` | 5 | 10 | 30 |
| `FEATURE_NEW_CHECKOUT` | `true` | `true` | Per release plan |

These values are illustrative. Production may use different pools, timeouts, and logging; never inflate every parameter just because the environment is more critical. Database schema differences and service versions must be managed through migrations and API compatibility, not merely by swapping environment variables.

### 2.2. Configuration Precedence

An application may receive configuration from in-code defaults, config files, environment variables, config services, and deployment parameters. Define a clear precedence order to prevent conflicting values for the same key.

A reference convention:

1. Safe defaults inside the application.
2. Packaged config files for non-sensitive default values.
3. Environment configuration mounted or injected at deployment time.
4. Approved override parameters for a specific workload.

Actual sources and precedence depend on the framework. Some frameworks enforce their own precedence; document and test it. Never assume environment variables always override every other source.

Do not place secrets in ordinary config files just because the application already reads files. Configs may be logged, displayed, copied, or archived in artifacts; secrets require dedicated protection.

### 2.3. Validating Configuration at Startup

Applications should validate essential configuration immediately at startup:

- Are required keys present?
- Do values match expected types, bounds, and formats?
- Do URLs use expected schemes and valid hostnames?
- Are timeouts, pool sizes, and retry counts within allowed ranges?
- Do feature flags hold supported values?
- Do connections to required dependencies have appropriate readiness checks?

Java example validating several non-sensitive values:

~~~java
public record AppConfig(
        String environment,
        String paymentApiUrl,
        int requestTimeoutMillis,
        int databasePoolMax) {

    public static AppConfig fromEnvironment() {
        String environment = required("APP_ENV");
        String paymentApiUrl = required("PAYMENT_API_URL");
        int timeout = positiveInt("REQUEST_TIMEOUT_MS", 1500);
        int poolMax = positiveInt("DB_POOL_MAX", 10);

        if (!paymentApiUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "PAYMENT_API_URL must use HTTPS");
        }

        return new AppConfig(environment, paymentApiUrl, timeout, poolMax);
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required configuration: " + key);
        }
        return value;
    }

    private static int positiveInt(String key, int defaultValue) {
        String raw = System.getenv(key);
        if (raw == null || raw.isBlank()) return defaultValue;

        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) throw new IllegalArgumentException(
                    key + " must be greater than zero");
            return value;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    key + " must be an integer", ex);
        }
    }
}
~~~

Never print entire environment dumps or connection strings in error messages, as they may contain secrets. Validating URL format also does not replace certificate validation, DNS checks, and runtime access control.

### 2.4. Startup Config vs. Dynamic Config

- **Startup/static config:** read when the application starts, such as listening ports, pool initialization, or TLS configuration. Changes may require a rollout.
- **Dynamic config:** can be updated while the application runs, such as feature flags or certain business thresholds. Requires refresh mechanisms, caching, versioning, fallbacks, and auditing.
- **Secret rotation:** follows its own lifecycle; the application must adopt new credentials and safely stop using old ones.

Dynamic config is useful for rapid changes, but increases complexity: multiple replicas may receive config versions at different times. Track versions, update timestamps, confirmation of application, and rollback paths.

## 3. Managing Secrets Across Their Lifecycle

A secret is not just a password stored in one place. A secret has a lifecycle covering creation, distribution, usage, rotation, revocation, auditing, and compromise response.

~~~mermaid
flowchart LR
    CREATE["Create / issue"] --> STORE["Secret manager / protected store"]
    STORE --> GRANT["Grant access to workload identity"]
    GRANT --> USE["Fetch or mount at runtime"]
    USE --> ROTATE["Rotate / renew"]
    ROTATE --> USE
    ROTATE --> REVOKE["Revoke old credential"]
    STORE -. "Audit events" .-> AUDIT["Central audit and alerting"]
    USE -. "Access logs" .-> AUDIT
    REVOKE -.-> AUDIT
~~~

### 3.1. Secret Classification

| Type | Examples | Requirements to Consider |
|---|---|---|
| Password | Database user password | Rotation, strength policies, user privileges |
| API key/token | Credential for calling third-party services | Scope, expiry, revocation, quotas |
| Private key | Signing tokens, encryption, or client auth | Key protection, HSM/KMS where appropriate, rotation |
| Certificate | TLS/mTLS client/server certificates | Trust chain, expiry, issuance, and renewal |
| Database credential | Username/password or database access token | Separate principals per workload, schema rights, TTL |
| Signing/encryption key | Signing data or encrypting business payloads | Key versioning, rotation, access policies, ability to decrypt old data |

Not every certificate or key is stored the same way. Private keys used for signing or encryption may require an HSM or key management service; public certificates can be distributed more broadly, while their trust chains and paired private keys must still be protected.

### 3.2. Secret Managers and KMS

A **secret manager/key vault** manages secret values, versions, access policies, and audits. A **Key Management Service (KMS)** manages encryption key lifecycles and cryptographic operations or data key protection according to product capabilities. These two service groups may integrate, but are not always the same thing.

Service examples:

- AWS Secrets Manager and AWS Systems Manager Parameter Store; AWS KMS for key management.
- Azure Key Vault for secrets, keys, and certificates per feature tier; Managed HSM is a separate option for HSM needs.
- Google Cloud Secret Manager for secrets and Cloud KMS for cryptographic keys; Cloud HSM for managed hardware cryptographic needs.

Capabilities, pricing, limits, replication, permissions, and integration patterns must be evaluated per product. Do not assume a secret manager automatically rotates every credential type or that every rotation is zero-downtime.

### 3.3. Delivering Secrets at Runtime

A common flow:

1. The workload's identity is verified by the platform.
2. The workload requests a specific secret from the secret manager.
3. The secret manager evaluates policies and returns the credential if the principal is authorized.
4. The application uses the secret strictly within the needed scope.
5. Secrets are never written to logs, exceptions, metric labels, or unprotected temporary files.
6. Secret access and modification events are audited.

| Approach | Description | Pros | Trade-Offs |
|---|---|---|---|
| Fetch via SDK/API | Application calls secret manager at startup or on refresh | Direct control over versioning/caching/refresh | Code must handle timeouts, retries, caching, and service errors |
| Mount/inject as file or environment variable | Platform/agent delivers secret into runtime | Simpler app code, integrates with mounts | Can leak via process environment, debugging, file permissions, or snapshots; updates are not always automatically reloaded by apps |

For highly sensitive secrets, fetching via workload identity and holding them in memory only as needed reduces exposure in files or process environments. This is not an absolute guarantee: memory dumps, debug endpoints, and heap dumps must still be locked down.

### 3.4. Zero-Downtime Rotation

A widely used pattern is credential overlap:

1. Create a new credential version.
2. Grant permissions and verify the new credential works.
3. Update workloads to adopt the new version.
4. Monitor replicas that switched over and watch for connection errors.
5. Revoke the old credential once confident no clients still depend on it.

For databases, this may require two principals or a provider-supported rotation mechanism. Changing a user's password immediately while some replicas still hold the old value will cause request failures. For mTLS, manage the overlap window across trust bundles, new certificates, and old certificates.

**Rotation is not simply changing a string.** It is a coordinated rollout across the secret issuer, consumers, caches, open connections, and revocation mechanisms.

## 4. Workload Identity: Every Application Has Its Own Identity

When workloads call cloud services, the system needs to know who the caller is. Long-lived access keys create numerous problems: they must be stored, distributed, rotated, and revoked; if leaked into an image or Git, tracking down every copy is difficult.

**Workload identity** allows the platform to verify a workload and issue short-lived credentials or tokens according to policy. The goal is to minimize or eliminate static secrets used for authenticating workloads to cloud APIs.

Examples:
- The Booking API needs to read one secret and write booking data.
- The Notification Worker only needs to read from a queue and fetch an email-sending credential.
- CI/CD has permission to deploy the Booking API, but must not read payment data.
- The monitoring agent is only permitted to ship telemetry.

If all four share a single admin service account/role, a bug or compromise in one workload can spill over into other systems.

### 4.1. Authentication vs. Authorization

- **Authentication:** the system verifies which principal is making the request.
- **Authorization:** which actions that principal is permitted to perform on which resources.

Workload identity establishes authentication and supplies the principal for policy evaluation. It does not automatically grant or govern all application permissions.

For instance, `booking-api-prod` is authenticated, yet only permitted to read `booking/prod/payment-api-client`, access required booking data, and invoke the API to create a payment intent. It cannot delete audit logs, alter IAM policies, or invoke refund APIs unless business logic permits it.

### 4.2. Short-Lived Credentials and Federation

A common pattern is for a workload to receive an identity-proving token from its runtime environment and exchange it for short-lived cloud credentials. With federation, the cloud trusts a configured issuer or identity provider, inspecting claims and conditions before issuing a role/token.

Claims may include subject, audience, issuer, namespace, service account, repository, or workload attributes depending on the platform. **Trust policies must tightly scope the exact trusted subject**, rather than accepting every token emitted by an issuer.

Never log federation tokens; short-lived tokens remain valid credentials until they expire or are revoked by supported mechanisms.

## 5. Workload Identity Mechanisms Across Cloud Platforms

| Platform | Common Mechanisms | Scenarios |
|---|---|---|
| **AWS** | IAM roles for compute (EC2 instance profiles, ECS task roles), IAM Roles for Service Accounts (IRSA), or EKS Pod Identity | Pods/services receive dedicated roles instead of storing access keys |
| **Azure** | Managed Identity (system-assigned or user-assigned), Workload Identity Federation for eligible workloads | VMs, App Service, Container Apps, AKS, or pipelines fetch tokens via identity |
| **Google Cloud** | Service Accounts attached to workloads, Workload Identity Federation, Workload Identity for GKE | Compute or Kubernetes workloads access Google Cloud APIs without embedded JSON keys |

These mechanisms are not identical in trust models, token exchange, limits, networking, and auditing. Verify the exact service and version before selecting.

### 5.1. AWS

EC2 instances can attach an instance profile containing an IAM role; applications obtain temporary credentials via the metadata service with appropriate protections. ECS task roles bind credentials directly to tasks. In EKS, IRSA or EKS Pod Identity grants permissions per Kubernetes workload rather than letting all Pods share a broad node role.

Avoid placing developer access keys in images, giving the node role permission to read every secret, writing overly broad trust conditions allowing any service account, or letting Pods access node metadata credentials unnecessarily when the platform can restrict it.

### 5.2. Azure

Managed Identity allows workloads to acquire tokens through the platform without storing client secrets. A system-assigned identity ties its lifecycle to the resource; a user-assigned identity exists independently and can attach to multiple resources as needed. Sharing a single identity across multiple workloads requires evaluating blast radius and revocation ownership.

In AKS, Workload Identity uses federation between a Kubernetes service account and a Microsoft Entra application/managed identity as configured. Trust must strictly constrain issuer, subject, and audience. Never attach a single broad-privilege identity to all Pods just to simplify configuration.

### 5.3. Google Cloud

A Google Cloud service account represents a workload or application. Workload Identity Federation enables workloads outside Google Cloud or in Kubernetes environments to verify via a trusted identity provider and receive scoped permissions. In GKE, Workload Identity maps a Kubernetes service account to a Google Cloud IAM principal per configuration.

Avoid baking JSON service account keys into images, committing them to repositories, or sharing them across teams. If an exceptional case requires a static key, require clear justification, narrow scope, secure storage, and a rotation/revocation plan.

## 6. Configuration and Identity in Kubernetes

Kubernetes provides primitives for configuring workloads; understand the limits of each.

### 6.1. ConfigMap

**ConfigMap** stores non-sensitive configuration data. It can be injected as environment variables or mounted as files. ConfigMaps are not secret stores, and data is not protected like credentials merely by living in the Kubernetes API.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: booking-api-config
  namespace: booking-prod
data:
  APP_ENV: "prod"
  LOG_LEVEL: "info"
  PAYMENT_API_URL: "https://payments.internal"
  REQUEST_TIMEOUT_MS: "1500"
~~~

### 6.2. Secret

Kubernetes **Secret** stores sensitive data using encoded representations (typically base64 when serialized as YAML), yet **base64 is not encryption**. By default, data protection in etcd depends on cluster configuration; you need encryption at rest, strict RBAC, backup protection, and API access controls.

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: booking-db-credential
  namespace: booking-prod
type: Opaque
stringData:
  username: "booking_runtime"
  password: "INJECT_AT_DEPLOYMENT_TIME"
~~~

This is a placeholder, not a usable password. Never put real secrets into YAML files, Git, or shell commands saved in history. External secret managers can be integrated via CSI drivers or dedicated controllers, provided synchronization, read permissions, and secret lifecycles are carefully reviewed.

### 6.3. ServiceAccount and RBAC

A Kubernetes `ServiceAccount` gives a Pod an identity when interacting with the Kubernetes API; Kubernetes RBAC restricts permissions within the cluster. It is **distinct from a cloud IAM identity**, even though it can be federated/mapped to let workloads access cloud services.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: booking-api
  namespace: booking-prod
automountServiceAccountToken: false
~~~

If a Pod does not need to call the Kubernetes API and does not need a service account token, disable automatic mounting as appropriate. If API access is needed, supply the token and narrowly scoped permissions; do not disable tokens blindly if doing so breaks the workload.

Example RBAC allowing a workload to read ConfigMaps only within its namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: booking-config-reader
  namespace: booking-prod
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: booking-config-reader-binding
  namespace: booking-prod
subjects:
  - kind: ServiceAccount
    name: booking-api
    namespace: booking-prod
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: booking-config-reader
~~~

These are strictly Kubernetes API permissions inside the namespace. They do not automatically grant access to external secret managers or permission to call the Payments API; those permissions are granted through their respective identity/policy mechanisms.

### 6.4. Injecting ConfigMaps and Secrets into Pods

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: booking-prod
spec:
  replicas: 3
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api:1.4.2
          envFrom:
            - configMapRef:
                name: booking-api-config
          env:
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: booking-db-credential
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: booking-db-credential
                  key: password
          ports:
            - name: http
              containerPort: 8080
~~~

This example illustrates wiring. In production, control how Secrets are created/updated, encryption at rest in Kubernetes, `get`/`list`/`watch` Secret permissions, manifest read access, and exposure via debug/process environments. When using CSI or external secret operators, how mounted files update and how apps reload/restart depend on the driver/controller.

### 6.5. Pod Identity Is Not Node Identity

Multiple workloads sharing a node should not inherently share the node's permissions. If a Pod can retrieve node-level credentials, a compromised Pod can access far more resources than intended. Prefer per-Pod/service account or per-task identities, restrict metadata access where supported, and separate node agent permissions from applications.

## 7. Delivering Configuration and Secrets Safely in CI/CD

Deployment pipelines are a critical ingress path. Configuration and secret injection must keep secrets out of source code, artifacts, and logs.

1. Build images without environment secrets.
2. Scan images and artifacts to catch accidentally packaged secrets.
3. Attach non-sensitive configuration at deploy time or via a config service.
4. When the workload runs, its identity fetches only the secrets it needs.
5. Admission/cluster/cloud policies validate deployment configs against baselines.
6. Monitor rollouts, secret-read failures, token/certificate expirations, and access patterns.
7. When replacing secrets, perform overlap rotation and verify replicas switch over.

~~~mermaid
flowchart LR
    SRC["Source + code review"] --> BUILD["Build image without secrets"]
    BUILD --> SCAN["Scan dependencies / image / secrets"]
    SCAN --> REG["Image registry"]
    REG --> DEPLOY["Deploy with non-secret config"]
    DEPLOY --> ID["Workload identity"]
    ID --> SM["Secret manager"]
    SM --> APP["Runtime application"]
    SM -. "Access audit" .-> LOG["Audit / monitoring"]
~~~

Never pass secrets via build arguments or bake them into Dockerfiles as a storage shortcut; build inputs can remain visible in image history, layers, or logs depending on the tooling. Docker BuildKit secret mounts can work for secrets needed strictly during build steps, but must never be used to embed runtime credentials inside the image.

Key rules:
- Never commit `.env` files containing secrets; only commit `.env.example` with dummy values and descriptions.
- Mask secrets in pipeline logs, yet do not rely solely on masking since secrets can be encoded, split, or printed during debugging.
- Use OIDC/workload federation wherever possible instead of long-lived pipeline credentials.
- Separate roles for building, publishing artifacts, and deploying to production.
- Maintain a revocation process when secrets leak; deleting a file in a new commit does not invalidate the exposed credential.

## 8. Updating Configuration, Secrets, and Resilience

### 8.1. Config Reloads

When configuration changes, containers can pick up new values via rollouts, file mounts, or config agents. Decide whether the app reloads files periodically or only at startup; whether invalid configs retain the previous version or halt the process; whether replicas must update in lockstep or can skew versions; whether config versions are logged/emitted as metrics; and how rollbacks work.

Never allow configuration to change silently without auditing and versioning. For business-impacting parameters like booking caps or feature flags, enforce ownership, approvals, and scope verification.

### 8.2. Secret Rotation and Caching

Applications may cache secrets to reduce calls to the secret manager and avoid hard dependency on every request. However, caches require expiration and refresh logic. Excessive TTLs slow down revocation; zero caching makes the system fragile during secret manager disruptions.

Reference strategy:
- Fetch secrets at startup and cache with bounded TTL.
- Refresh ahead of expiration/rotation windows.
- If a new credential fails, never log the credential value; fall back per defined policy.
- Never continue using revoked credentials indefinitely.
- With multiple replicas, roll out gradually and support both old and new credentials during a controlled overlap period.

### 8.3. When the Secret Manager Is Unavailable

This is an operational dependency. Decide how long running workloads can continue with cached secrets versus failing startup. There is no universal answer:

- Running APIs can continue using valid in-memory credentials until expiration.
- New Pods lacking secrets and caches may fail to start.
- Workers can continue processing jobs that do not need the secret, but must not mark success if they cannot reach the provider.
- Emergency procedures must avoid distributing shared static passwords just to get applications running again.

Account for this dependency in RTO, recovery procedures, quotas, and availability targets.

## 9. Protecting Configuration and Secrets Against Leaks

| Location | Risk | Control |
|---|---|---|
| Source control | Secrets in commits or history | Secret scanning, revoke/rotate, protected branches |
| Container image | Secrets embedded in layers or metadata | Secret-free builds, image scanning |
| Environment/process | Exposed via debug, crash dumps, or process read access | Restrict process inspection, avoid secret-bearing dumps |
| Kubernetes API/etcd | Broad RBAC reads secrets; backups may contain data | Least-privilege RBAC, encryption at rest, backup protection |
| CI/CD logs | Debug commands or error traces print secrets | Masking, avoid `echo`/`env` dumps, log checks |
| Application logs/traces | Tokens, `Authorization` headers, connection strings | Redaction, field allowlists, and tests |
| Temporary files | Secret files copied or stored on unprotected volumes | Restrict files, permissions, memory-backed volumes where suitable |
| Developer laptops | Secrets downloaded and stored locally | Prefer runtime access, endpoint policies, device controls |
| Support bundles | Heap dumps/config snapshots with sensitive data | Sanitization, encryption, restricted access, and retention |

**Base64 is not encryption**, and a private network does not stop a compromised workload from reading secrets if IAM permits it. Security must combine identity, authorization, storage protection, encryption, monitoring, and credential-leak incident response.

When a potential secret leak is detected:

1. Identify the credential type and the resources it grants access to.
2. Revoke/rotate prioritized by risk, with controlled rollout to avoid unintended outages.
3. Inspect audit logs to determine timestamps, principals, and scope of use.
4. Search for copies in images, Git, logs, artifacts, caches, or backups.
5. Update workloads, confirm the new credential works, and verify the old credential is dead.
6. Document the incident, root cause, and preventive measures.

## 10. Managing Configuration Across Multiple Environments

Dev, staging, and prod typically share the same code while differing in endpoints, secrets, and permissions. Never change `APP_ENV` alone and assume everything is isolated.

| Component | Dev | Staging | Production |
|---|---|---|---|
| Identity | Narrowly scoped dev role | Staging role | Restricted and reviewed prod role |
| Secrets | Sandbox credentials | Staging credentials | Dedicated production credentials |
| Database | Test dataset | Prod-like dataset with controlled data | Real data with appropriate protections |
| API endpoints | Mock/sandbox environment | Test endpoints | Private/controlled production endpoints |
| Logging | Debug if needed, no secrets | Info and test tracing | Data-controlled logs, retention/auditing |
| Config changes | Flexible within team scope | Follows test process | Reviewed/approved with version tracking |
| Access | Developers by team | QA/Release roles | Separated deploy/runtime rights, JIT admin |

Never copy production secrets into staging to mimic production behavior. For integration testing, use dedicated credentials, anonymized or synthetic data, and sandbox endpoints whenever possible.

Illustrative naming convention for configs and secrets:

~~~text
booking/dev/database/username
booking/dev/database/password
booking/staging/payment-api/client-token
booking/prod/database/credential
booking/prod/payment-api/client-certificate
~~~

This is an illustrative convention, not a mandatory secret manager syntax. Choose a structure matching your platform's hierarchy, versioning, policy scoping, and naming limits.

## 11. Trade-Offs Across Well-Architected Dimensions

| Dimension | Benefits of Good Design | Risks / Costs | Review Questions |
|---|---|---|---|
| **Reliability** | Renewable credentials; versioned configs; replaceable workloads | Secret manager/IdP outages block new Pods; broken rotation drops connections | Are sensible caches, overlap windows, rollbacks, and rotation drills in place? |
| **Security** | Least privilege, workload identity, secret managers, auditing | Tokens/secrets leaked via logs, heap dumps, or broad cloud roles | Who can read each secret? Can it be revoked and traced? |
| **Scalability** | Multiple replicas obtain identity and config independently | Simultaneous secret fetches cause throttling; config rollouts skew versions | Are caching, jitter, rate control, and safe refresh implemented? |
| **Performance** | Credentials fetched on demand, runtime-appropriate configs | Additional network calls to secret managers or identity providers | Are bootstrap, refresh, and token exchange latencies measured? |
| **Cost** | Reduces static key toil and incidents; clear automated permissions | Secret operations fees, KMS, HSM, controllers, and auditing | Which services justify costlier protection? Are unused secrets pruned? |
| **Operations** | Rotation/auditing/config rollouts can be automated | Adds dependencies, policies, and operational procedures | Are owners, runbooks, expiry alerts, and break-glass procedures defined? |
| **Sustainability** | Cuts resources and credentials lingering past need | Old secret versions, configs, or unused identities accumulate | Are lifecycles, TTLs, and cleanup/review schedules enforced? |

### Scenarios to Weigh

**Environment variables vs. file mounts?** Environment variables are easy to configure but can leak through process inspection or debugging; file mounts offer tighter permission controls, yet write copies onto filesystems/volumes and require reload handling. Choose based on threat model, platform support, and app reload capabilities.

**Fetch secrets per request vs. cache?** Fetching per request increases latency, cost, and secret manager dependency; long caching extends the window an old credential stays in use. In practice, teams usually cache with bounded TTLs, proactive refresh, and clear policies.

**One shared identity for multiple services vs. one identity per workload?** Sharing simplifies onboarding, but widens blast radius and obscures auditing. Separating identities produces more policies and requires automation.

**External secret manager vs. Kubernetes Secrets?** Kubernetes Secrets integrate cleanly with Pods, yet cluster admins/RBAC/etcd/backups all enter the trust boundary. External secret managers centralize lifecycle management, at the cost of network dependencies, controllers, and federation permissions. Some environments combine both; clarify which copy is the source of truth and which is synced.

## 12. Testing and Observing the Config/Secret/Identity Lifecycle

Designs must include both positive tests (permitted access) and negative tests (denied access).

| Test | Expected Outcome | Evidence |
|---|---|---|
| Deploy the same image to dev and staging | App picks up environment-appropriate endpoints/configs | Config version, startup validation logs |
| Booking API Pod reads its own secret | Succeeds with the proper identity | Secret audit log, workload principal |
| Booking API reads Payments admin secret | Denied | IAM decision/denied audit event |
| Pod without workload identity | Fails to obtain cloud credentials | Token/federation log and denied event |
| Secret rotation | New replicas use new credentials; old replicas transition before revocation | Rotation event, connection metrics |
| Temporary secret manager outage | Workloads behave per cache/startup policy | Error metrics, readiness, runbook execution |
| Log containing `Authorization` header | Sensitive value is redacted | Log tests, automated scanning |
| Pod not needing Kubernetes API | Service account token is not auto-mounted when disabled | Pod spec and API audit |
| Old credential revoked | Requests using old credential are rejected | Provider audit and app error metrics |
| Dynamic config change | Replicas adopt new version/roll back per rules | Config version and rollout status |

### Metrics and Alerts to Track

- Expiring secrets, expiring certificates, delayed or failed rotations.
- Secret read counts by principal, unused secrets, or anomalous access spikes.
- Token issuance/federation errors, credential exchange latency, and authorization denials.
- Startup failures due to missing config/secrets, restart counts, and readiness status.
- Config versions per replica, lagging replicas, and reload errors.
- IAM policy modifications, newly issued workload identities, and unusual permission scopes.
- Secret scanning findings across repositories, artifacts, and image registries.

Never log secret values while debugging these metrics. Record secret identifiers, versions, principals, operations, and outcomes safely; avoid logging payloads or tokens.

## 13. Practical Design and Implementation Process

1. **Inventory configuration:** list variables, files, feature flags, endpoints, timeouts, and defaults.
2. **Classify data:** tag non-sensitive values, secrets, keys, or certificates; identify authoritative sources.
3. **Design identities:** create dedicated principals per workload and pipeline; grant least privilege per environment.
4. **Select config/secret sources:** ConfigMaps/config services for config; secret managers/KMS/key vaults for secrets and keys; identity federation for runtime credentials.
5. **Design delivery:** environment variables, mounted files, SDK/API, or CSI/controllers; define TTLs, caching, reloading, and failure behavior.
6. **Design rotation:** owners, schedules, overlap, rollout, verification, and revocation; establish emergency leak procedures.
7. **Protect build/deploy paths:** keep runtime secrets out of images; scan source/artifacts; separate build and deploy identities.
8. **Test permissions:** verify intended workloads can read required secrets while others are denied; test out-of-scope access.
9. **Design observability:** audit access, config versions, expirations, token/secret errors, startup, and rotations.
10. **Operate continuously:** review permissions, delete stale secrets/identities, update runbooks, and rehearse rotations and incidents.

### Sample ADR — Provisioning Database Credentials via Workload Identity

> **Context:** The Booking API runs three replicas in Kubernetes. Currently, the database password is stored in a single configuration file shared across dev and production.
>
> **Decision:** Separate database principals per environment; assign cloud workload identities to Kubernetes service accounts; workloads use their identity to access a secret manager or platform-supported short-lived database authentication. Images contain no credentials. Endpoints and pool sizes come from ConfigMaps/config services.
>
> **Rationale:** Eliminates secret exposure in Git/images and restricts permissions per workload and environment.
>
> **Trade-Offs:** Adds configuration for federation, IAM policies, secret providers, auditing, and rotation workflows; new Pods depend on identity/secret services at startup.
>
> **Verification:** Dev cannot read prod secrets; Booking API retrieves the right credential; old credentials are revoked post-rotation; Pods restarting during a secret manager disruption behave according to the runbook.
>
> **Review Triggers:** Platform changes identity mechanisms, database adds better token-based auth support, workload count grows, or RTO requirements change.

## 14. Practice Exercise

An e-commerce system runs three containers: Order API, Payment Worker, and Report Worker. All three share a single `.env` file containing the database password, payment API key, and cloud access key. This file is committed to an internal repository, and every workload can read all variables. When deploying to staging, the team only swaps `APP_ENV` while continuing to share the production cloud key. During one incident, debug logging printed the entire environment into CI logs.

**Requirements:**

1. Classify the variables into configuration, secrets, and identity/policy.
2. Identify at least five risks caused by sharing the `.env` file and cloud access key.
3. Design separate identities for Order API, Payment Worker, Report Worker, and CI/CD.
4. Choose an appropriate secret manager/config mechanism; explain how workloads retrieve values at runtime.
5. Propose a rotation process that does not disrupt payment processing.
6. Explain how to remediate secrets exposed in the repository and CI logs.
7. Write a test matrix for dev/staging/prod covering both allowed and denied access.
8. If using Kubernetes, describe the roles of ConfigMap, Secret, ServiceAccount, RBAC, and workload identity.

### Solution Guidance

- Remove credentials from the repository and logs. Once committed or logged, treat credentials as potentially compromised and rotate/revoke them—even if a newer commit deleted the file.
- Separate principals per workload: Order API only reads/writes orders; Payment Worker holds rights for payment processing and required queues; Report Worker holds read access to authorized data or reporting stores; CI/CD holds deploy rights without needing runtime secrets.
- Separate environments: dev/staging/prod each get dedicated endpoints, identities, database principals, and secrets; never use production cloud keys in staging.
- Place non-sensitive configs such as `APP_ENV`, `LOG_LEVEL`, timeouts, and API endpoints in environment-specific config services/ConfigMaps.
- Use a secret manager and workload identity; if file mounting or Kubernetes Secrets are required, enforce strict RBAC, encryption at rest, and synchronized lifecycles.
- Rotation: create new credentials, verify permissions, roll out workers, monitor for errors, then revoke old credentials. For payments, check in-flight transactions and callbacks/webhooks.
- Remediate leaked logs: restrict access, retention, and copies; revoke credentials, assess whether logs were downloaded/shared, and file an incident record.
- Testing: each workload reads only its own secrets; dev cannot read prod; Report Worker cannot call payment APIs unless required; CI/CD deploys only its target apps; logs contain no tokens or passwords.

### Self-Check Questions

1. Why can a database URL be configuration while a connection string with a password must be protected as a secret?
2. Why is base64 encoding in a Kubernetes Secret not encryption?
3. How does workload identity differ from an IAM policy or Kubernetes RBAC?
4. When a Pod has its own service account, what else is required for that Pod to call a cloud API?
5. Why does rotation require overlap and consumer verification before revoking old credentials?
6. When a secret manager is unavailable, how long should secrets be cached and what requirements drive that decision?
7. How do you ensure deploy pipelines do not inherit runtime privileges or unnecessary administrative permissions?

A strong container architecture manages **configuration as versioned operational data**, **secrets as sensitive assets with lifecycles**, and **workload identity as the foundation for least-privilege access**. When these three pieces are designed distinctly yet coordinated properly, the same image can deploy safely across environments, workloads can be replaced and scaled, and credential rotation or revocation remains controlled and auditable.
