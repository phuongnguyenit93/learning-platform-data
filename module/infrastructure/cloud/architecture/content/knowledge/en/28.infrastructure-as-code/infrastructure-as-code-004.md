# Separating Environment Variables from Secrets and Sensitive Configuration

Infrastructure as Code (IaC) describes infrastructure and configuration in code that can be reviewed, version-controlled, and deployed repeatedly. IaC modules frequently require values that vary across environments, such as region, instance size, endpoints, bucket names, feature settings, database passwords, API tokens, and private keys. If all of these are handled like ordinary input variables, secrets can leak into Git, state files, plan artifacts, CI logs, images, or pipeline outputs.

**Separating environment variables from secrets and sensitive configuration** means designing a clear boundary between data describing deployment behavior and data that grants access or poses risk if exposed. The goal is not merely putting passwords in a secret manager; you must also define the source of truth, data classification, referencing mechanisms, authorized identities, provisioning timing, lifecycle, rotation, auditing, and safeguards to keep secrets out of unsafe artifacts.

This lesson belongs to the **Infrastructure as Code** chapter of the **Cloud Architecture** track. The track teaches how to architect cloud applications from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. This lesson focuses on organizing environment-specific configuration, keeping secrets out of source code, and managing their usage across both IaC pipelines and runtime workloads.

After this lesson, you will be able to:

- Distinguish among environment variables, application configuration, sensitive configuration, secrets, and key material.
- Define sources of truth and precedence for environment-specific configuration.
- Manage secrets using a secret manager/vault and workload identities.
- Keep secrets out of Git, IaC state, plans, logs, outputs, and artifacts.
- Design IaC modules that use references instead of plaintext secrets.
- Understand the limitations of `sensitive` marking, log masking, and state encryption.
- Deliver configuration securely to VMs, containers, and Kubernetes.
- Design bootstrap, rotation, revocation, and emergency response workflows.
- Implement policy-as-code, secret scanning, and drift checks.
- Test and audit configurations across dev, staging, and production.

## 1. Distinguishing configuration from secrets

Not all configuration is secret. Many values vary across environments without granting any access permissions.

- **Environment-specific configuration:** values describing the environment or deployment behavior, such as region, hostname, log level, feature settings, and replica count.
- **Application configuration:** parameters controlling application behavior, such as timeouts, retry limits, locale, and business thresholds.
- **Sensitive configuration:** configuration that is not a credential, yet if exposed could reveal internal topology or policies—such as internal endpoints, network layouts, or detailed security rules.
- **Secret/credential:** data used for authentication or granting access, such as passwords, API tokens, client secrets, and webhook signing secrets.
- **Cryptographic key material:** private keys, data encryption keys (DEKs), key-encryption keys (KEKs), or signing keys.
- **Public metadata:** service names, public endpoints, non-sensitive feature settings, or non-privileged identifiers.

| Data type | Example | Recommended handling |
| --- | --- | --- |
| Non-sensitive config | Region, instance type, port, log level | Version control or config store |
| Environment config | Domain, resource name, replica count | Environment-scoped IaC variables/config |
| Sensitive config | Internal topology, detailed security policy | Scoped access control, restricted logging/export |
| Secret | DB password, API token, OAuth client secret | Secret manager, short-lived identity when possible |
| Private key | TLS/signing private key | KMS/HSM or appropriately protected secret store |
| Public key/certificate | Public verification key, public certificate | Integrity, trust chain, and version control |
| Wrapped DEK | Encrypted data key | Stored alongside ciphertext metadata per encryption design |

A value may not be a secret yet still require protection because it reveals system structure. Conversely, do not mark every variable as a secret: doing so obscures reviews and hides real risks.

## 2. Environment variables are a delivery mechanism, not a secret vault

Environment variables (env vars) pass configuration to a process at startup. They do not encrypt themselves, enforce access policies, or manage lifecycles. Values can leak via process inspection, crash dumps, debug endpoints, diagnostic bundles, container metadata, orchestration control planes, or application logs.

Env vars are suitable for ports, regions, service modes, log levels, non-sensitive endpoints/config, and secret references. Some runtimes can receive secrets via env vars if the platform protects them well; however, for critical credentials or long-lived workloads, prefer identity-based retrieval or mounted secret files with tight permissions where supported by the platform.

Places where env vars can appear include process environments, process dumps, container/Pod specifications, CI task definitions, command lines, crash dumps, telemetry, and shell history. Restricting host/container control plane access, debug permissions, and logging is part of protecting env vars.

## 3. Three data zones to separate

A foundational architecture can separate three zones:

1. **IaC inputs/configuration:** non-secret data or references to configuration/secret sources used to describe resources and environment parameters.
2. **Secret system:** holds secret values, policies, versions, rotation, and audit trails.
3. **Runtime workload:** receives needed configuration and retrieves secrets under an authenticated identity, strictly within its permitted scope.

~~~mermaid
flowchart TB
    G["Git: IaC modules and non-secret config"] --> CI["CI/CD runner"]
    CI --> CLOUD["Cloud API / IaC provider"]
    CI --> ID["Deployment identity"]
    ID --> SM["Secret manager / KMS"]
    SM -->|Controlled reference or injection| RT["Runtime workload"]
    CLOUD --> RT
    RT --> APP["Application uses config and credentials"]
~~~

Secrets should appear in plaintext only at the boundary where they are genuinely needed and for the shortest possible duration. If a provider resolves a reference at deploy time and then writes plaintext into state, the reference has not eliminated the risk; you must inspect the actual data flow.

## 4. Sources of truth and configuration precedence

Configuration typically comes from module defaults, environment files, IaC variables, pipeline parameters, config services, and runtime overrides. Without defined precedence, the same deployment can behave differently depending on injection order.

A reasonable precedence chain is:

**Platform defaults → Environment configuration → Service configuration → Permitted runtime overrides**

Each layer requires an owner and a scope. Not every key should be overridable at every layer. Regions or resource naming may be fixed by the platform; application timeouts may be tuned by service teams within bounds; mandatory security policies must never be overridden by tenants or at runtime.

A configuration contract should define key/type, required/optional, default, allowed values, valid range, validation, environment applicability, owner, sensitivity, source of truth, version, compatibility, reload behavior, and auditing. Do not dump everything into schemaless JSON/YAML.

## 5. File structure by environment

Non-sensitive configuration can be stored per environment, sharing common modules while separating input files. File names and paths indicate the environment without containing secrets.

~~~text
infra/
  modules/
    app-service/
      main.tf
      variables.tf
      outputs.tf
  environments/
    dev/
      backend.hcl
      app.tfvars
    staging/
      backend.hcl
      app.tfvars
    production/
      backend.hcl
      app.tfvars
  policies/
    require-encryption.rego
    deny-public-storage.rego
~~~

`tfvars` files can be committed when they contain only reviewed, non-secret values. Backend configs locate the state store but should never hold static access keys. Authentication to cloud APIs and backends should rely on workload identities or short-lived credentials.

Example of non-secret inputs:

~~~hcl
# environments/production/app.tfvars
environment          = "production"
region               = "ap-southeast-1"
instance_type        = "compute-optimized-medium"
replica_count        = 3
log_level            = "INFO"
public_base_url      = "https://app.example.com"
database_secret_ref  = "secret/production/booking/database"
~~~

A secret reference is not a secret value, yet it can still reveal system names or internal structure. Classify references appropriately and apply suitable file read permissions.

## 6. Secret managers and vaults

A secret manager/vault provides centralized storage for secrets along with access policies, versioning, auditing, and rotation. Some services also support dynamic secrets, leases, and workload identity integration.

A secret system must answer: who can create or update secrets; which workloads can read which secrets; whether permissions are scoped by service, environment, and tenant; whether secrets have versions and expiry; whether rotation is automated; whether read/write/rotate/revoke actions are audited; whether the service has HA/DR and backups; what happens if the store is temporarily unavailable; and how issued sessions, tokens, or connections are revoked.

Centralized does not mean a single identity can read every secret. Separate namespaces, policies, and administrative boundaries by environment, domain, and sensitivity tier.

## 7. Workload identities instead of static credentials

Workloads should not store long-lived access keys solely to reach a secret manager. VMs, containers, functions, or CI runners should use platform-issued identities.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant I as Cloud identity provider
    participant S as Secret manager
    participant D as Database
    W->>I: Request short-lived identity
    I-->>W: Scoped identity token
    W->>S: Read authorized secret reference
    S-->>W: Secret version/value
    W->>D: Authenticate to database
~~~

Policies should restrict subject, service account, environment, audience, namespace, and resource. A deployment runner permitted to provision resources does not necessarily need permission to read application runtime secrets. Separating deployment identity from runtime identity reduces blast radius.

### 7.1. Bootstrap and secret zero

To read its first secret, a workload still needs an initial way to authenticate. Common approaches include managed identities/instance roles, OIDC federation from CI, Kubernetes service account token federation, short-lived workload certificates, or narrowly scoped bootstrap credentials with a short TTL.

Never solve bootstrap by hardcoding a master password in an image. If a bootstrap secret is unavoidable, treat it as a critical asset with a retirement plan.

## 8. IaC variables and sensitive marking

IaC tools typically provide mechanisms to mark sensitive inputs and outputs. For example, in Terraform:

~~~hcl
variable "database_password" {
  type      = string
  sensitive = true
}
~~~

`sensitive` marking helps suppress certain values from CLI output or UI displays per tool semantics. However, it **does not automatically encrypt or remove the value from state**. Providers may still persist the value into state, plan artifacts, debug logs, or API requests. Always verify the behavior of your specific tool/provider and version.

Prefer passing secret references or using integrations that support ephemeral/write-only arguments when resources and providers support those semantics. Never assume adding `sensitive = true` solves secret management.

Outputs marked `sensitive` may be masked on display yet remain stored in state or readable by authorized consumers. Do not export secrets as outputs merely to pass them to another module; prefer sharing references/identities so each workload retrieves its own secrets directly.

## 9. IaC state and plans are sensitive assets

State files map real-world resources and can contain inputs, attributes, connection details, or secrets returned by providers. Plan files can also contain sensitive values depending on the tool and provider.

- Store remote state in a backend with encryption at rest and in transit.
- Enable versioning, locking, and access control.
- Scope state read/write permissions by team, workspace, and environment.
- Separate production state from dev/staging state.
- Never commit state, plans, or state backups to Git.
- Restrict plan artifact downloads and enforce short retention.
- Protect CI logs and provider debug output.
- Avoid outputting secrets from modules.
- Test state backup/restore and incident procedures.
- Do not allow unauthorized users to read state even if they lack runtime permissions.

Encryption at rest protects data in storage, yet anyone permitted to read state can still access the decrypted contents. Enforce least privilege, auditing, and minimize secrets entering state in the first place.

State isolation ensures pipelines can only read what they manage. State locking prevents concurrent overwrites; it is not an authorization control. Encryption likewise does not substitute for restricting downloads and exports.

## 10. Secret injection to VMs and containers

Common patterns include:

- Runtime calling the secret manager via workload identity.
- An agent/sidecar fetching secrets and writing them to a tightly permissioned mounted file.
- An orchestrator integrating with a secret provider to mount or sync secrets.
- CI/CD injecting at deploy time when the runtime platform provides strong protection.

Prefer approaches that keep secrets out of images and out of broadly readable deployment manifests.

### 10.1. VMs

Use a managed identity or instance profile so the instance can retrieve secrets. If written to a file, enforce strict ownership/mode, filesystem encryption, backup controls, and cleanup. Avoid placing secrets in `cloud-init`/`user-data` if metadata APIs allow unauthorized processes to read them back.

### 10.2. Containers

Never bake secrets into image layers via Dockerfile `ARG`/`ENV`. Values can persist in image history, build caches, registries, or runtime metadata. Use runtime secret integrations, mounted files, or identity-based fetches.

Never put secrets in labels, annotations, or image tags. Restrict `exec`/debug access into production containers, as users with those permissions can inspect environments or secret files.

### 10.3. Kubernetes

A Kubernetes `Secret` is an object for managing sensitive data, yet base64 representation is not encryption. Configure encryption at rest for etcd as supported by the cluster, enforce least-privilege RBAC, restrict `list`/`watch`, enable auditing, and apply network access controls.

Consider External Secrets Operator or Secret Store CSI integrations, workload identity federation, secret volume mounts, and policy-driven refresh/rollout. Protect etcd backups, the API server, RBAC, and node access. Base64 is merely encoding.

## 11. CI/CD pipelines and deployment-time secrets

CI/CD pipelines hold elevated privileges: reading repositories, provisioning infrastructure, publishing artifacts, and deploying to production. A compromised pipeline can expose secrets or tamper with infrastructure.

- Use OIDC federation/short-lived credentials instead of static cloud keys.
- Separate identities for plan, apply, image build, and runtime.
- Restrict environment approvals and protected branches.
- Never print environment variables or command lines containing secrets.
- Log masking is only a mitigation layer, not a substitute for output controls.
- Restrict download access to plan, state, and build artifacts.
- Never expose production secrets to forks or untrusted pull requests.
- Pin action/plugin/provider versions and verify provenance.
- Scan commits, repository history, and artifacts.
- Audit who ran apply and under which identity.

### 11.1. Plan review and apply identity

Pipelines can generate a plan using read/plan permissions and require approval before apply. Plan artifacts must be protected because they can contain internal or sensitive details. The apply identity should hold only the permissions needed for its specific scope—never default to account-wide administrator access.

Never grant production secrets to pipelines executing code from forks or untrusted branches. Separate unprivileged build/test jobs from privileged jobs that run only after approval.

## 12. Environment separation

Dev, staging, and production have different data sensitivity, identities, networks, and access privileges. Never simply swap an `ENV` variable while sharing credentials, state, or secret namespaces.

| Component | Dev | Staging | Production |
| --- | --- | --- | --- |
| Cloud account/project | Isolated dev scope | Isolated preprod scope | Dedicated production scope |
| State backend | Separate | Separate | Separate, strictly restricted |
| Secret namespace | `dev/service` | `staging/service` | `production/service` |
| Workload identity | Dev role | Staging role | Production role |
| Data | Synthetic/test | Masked or synthetic | Production per policy |
| Apply approval | Automated within bounds | Reviewed | Protected approval/change control |
| Network | Non-production isolation | Preprod isolation | Production segmentation |

Never copy production secrets to staging for realism. Use separate secrets and synthetic or properly masked data. Never share the same API token across multiple environments, as doing so prevents scoped revocation.

## 13. Sensitive configuration beyond credentials

Some configurations are not passwords yet can reveal security posture or help attackers map the system: internal hostnames/private IPs, route/firewall allowlists, admin endpoints, security feature switches, KMS key identifiers, secret paths, fraud thresholds, and backup topologies.

These values do not necessarily belong in a secret manager. They can reside in a restricted config store, encrypted state, and audited repositories. Classify them by the impact of disclosure, tampering, or deletion; avoid dumping everything into the same secret namespace.

## 14. Rotation and reload

Secret rotation only works if consumers actually switch to the new version. An IaC apply may update a secret reference while running processes still hold old credentials in memory or connection pools.

1. Create the new credential in the target system.
2. Store the new version in the secret manager.
3. Grant read access to the runtime identity.
4. Refresh the secret reference or trigger a workload reload.
5. Open new connections/requests and verify.
6. Monitor consumers still using the old version.
7. Revoke the old credential after a bounded overlap window.
8. Audit and update inventory.

~~~mermaid
flowchart TD
    A["Create new credential"] --> B["Publish new secret version"]
    B --> C["Refresh workload"]
    C --> D["Verify new connections"]
    D --> E{"All consumers migrated?"}
    E -- "No" --> F["Investigate and retry"]
    F --> C
    E -- "Yes" --> G["Revoke old credential"]
    G --> H["Audit and close rotation"]
~~~

Do not revoke the old credential immediately before consumers have refreshed. Nor should overlap extend indefinitely; set an expiry, owner, and alerts.

## 15. Secret leakage and incident response

Whenever a secret appears in Git, logs, or artifacts, treat it as compromised until proven otherwise. Deleting the line in a new commit does not invalidate values preserved in history or caches.

1. Identify the secret, its owner, permissions, and the resources it unlocks.
2. Identify every exposure location: commits, artifacts, CI logs, images, state, dumps, or tickets.
3. Revoke/rotate the credential at the source of authority.
4. Invalidate active sessions, tokens, or connections where possible.
5. Issue a new credential and deploy via the emergency path.
6. Inspect audit, API, and database access logs for signs of abuse.
7. Purge or restrict exposed copies per policy while preserving required evidence.
8. Search for copies across Git history, artifact registries, caches, and backups.
9. Rotate dependent secrets that could have been read using the exposed credential.
10. Document the incident, root cause, scope, and preventive measures.

If a secret inside IaC state leaks, address state permissions, plan artifacts, backups, and exports together. Deleting a state file without understanding backend versioning can break infrastructure management; follow the IaC tool's recovery procedures.

## 16. Secret scanning and policy-as-code

Secret scanning detects token- or password-like strings in Git diffs, history, artifacts, or container images. Scanners can produce false positives or miss encoded/transformed secrets; findings require verification and remediation workflows.

Policy-as-code can prohibit plaintext passwords/tokens in disallowed resource attributes; secrets in outputs, tags, labels, user-data, or image build arguments; static cloud access keys in CI; public storage or overly permissive security groups; runtime workloads using administrator identities; production resources referencing `dev` secret namespaces; state backends lacking encryption, locking, or access policies; Kubernetes Secrets/etcd lacking encryption/RBAC baselines; and credentials without owners or expiry.

Policies must inspect real provider/resource semantics rather than merely matching field names containing `password`. Some resources offer write-only arguments, while some providers persist values into state. Understand schema and behavior.

## 17. Safe IaC module interfaces

Modules should request minimal inputs and prefer references over plaintext secrets.

~~~hcl
variable "environment" {
  type = string
}

variable "database_secret_arn" {
  type        = string
  description = "Reference to a secret managed outside this module"
}

resource "example_app_service" "booking" {
  name        = format("booking-%s", var.environment)
  environment = var.environment
  secret_reference = var.database_secret_arn
}
~~~

Resources and providers here are illustrative. Only pass references if the target platform supports runtime secret retrieval; some providers/resources resolve references at deploy time and write plaintext into state or APIs. Verify the data flow before choosing an abstraction.

Outputs should return resource IDs, endpoints, ARNs/references, or non-sensitive metadata. Another module needing credentials should use its own identity to fetch secrets from the secret manager within its own scope; modules should not serve as plaintext conduits between stacks.

## 18. IaC state, remote backends, and recovery

The state backend is the control plane for IaC. Protect its confidentiality, integrity, and recoverability.

- Encryption at rest and in transit.
- Authentication via short-lived identities.
- Least privilege per workspace/state key.
- State locking to prevent concurrent updates.
- Versioning and retention.
- Access logs/auditing.
- Backup/restore testing.
- Never make state buckets public.
- Never download state to personal laptops outside approved procedures.
- Secure handling for crash logs and debug traces.

If state is lost, infrastructure may still exist while IaC loses resource mappings. If state is exposed, resource mappings—and potentially secrets—are compromised. Recovery runbooks must address both scenarios separately.

## 19. Runtime configuration and secret delivery

Once IaC provisions infrastructure, runtimes still need to receive the right configuration and secret versions.

- **Pull at startup:** fetches config/secrets at launch; easy to reason about versions, though it may not update mid-process.
- **Pull periodically:** polls for versions periodically; requires caching, retries, and jitter.
- **Push/invalidation:** config service emits events for workloads to reload; must handle lost/duplicate events and phased rollouts.
- **Mounted file refresh:** an agent/provider updates mounted files; the app must support reloading or restarts.
- **Environment injection:** platform injects values at process start; usually requires a restart or redeploy to pick up new versions.

### 19.1. Last-known-good and failure behavior

If the secret manager is temporarily unavailable, workloads may use cached secrets that remain valid per policy; stale secrets should never be used indefinitely. Entitlement or security configs may need to fail closed. Branding or log formatting can usually fall back safely to defaults.

For each configuration category, define TTL, freshness, fail-open vs. fail-closed behavior, emergency revocation semantics, and recovery when the store returns.

## 20. Drift detection and configuration auditing

Drift is the difference between desired state in IaC and actual cloud state. Manual console edits can introduce unreviewed settings, open public access, or swap secret references.

- Run plan/drift detection on a schedule and before major changes.
- Record actor, timestamp, resource, and before/after values.
- Distinguish emergency hotfixes from unauthorized changes.
- Review impact before importing or reconciling.
- Avoid blindly overwriting production solely because it differs from state.
- Update the IaC source of truth after approved changes.
- Track which secret/config versions workloads are actually running.

Drift detection must never print secret values into logs or reports. Use redacted diffs alongside metadata and version identifiers.

## 21. Access permissions and separation of duties

| Role | Typical permissions needed | Should not have by default |
| --- | --- | --- |
| Developer | Read modules, open PRs, validate non-prod | Production secrets/state and production apply |
| CI plan identity | Read APIs/state needed for planning | Plaintext secrets or broad destructive permissions |
| CI apply identity | Apply within approved scope | Organization-wide admin |
| Runtime identity | Read specific secrets and call dependencies | IaC state write or secret administration |
| Secret rotator | Create versions/rotate within scope | Read access to all secrets |
| Security operator | Auditing, policies, and incident response | Arbitrary use of business credentials |
| Break-glass operator | Time-bound emergency access | Standing unmonitored privileges |

Approvals depend on environment and impact. Never allow the same identity to modify protective policies, self-approve, and execute changes that disable those policies.

## 22. End-to-end example: booking service

A booking service requires a database connection, a payment API integration, and a TLS certificate. IaC provisions networking, compute, identity, secret references, and monitoring. Actual credentials are managed outside Git.

| Component | Managed by IaC | Managed by secret/certificate system |
| --- | --- | --- |
| Database | Instance/cluster, subnets, parameters, identity policies | Password or dynamic credentials |
| Payment integration | Egress routes, runtime permissions, secret references | Provider token/client secret |
| TLS | Load balancer listeners, certificate references | Certificates, private keys, renewals |
| Application config | Non-secret env vars, timeouts, region, feature settings | Sensitive endpoints/credentials per classification |
| Runtime | Service account/managed identity, deployment | Secret retrieval and refresh |

~~~mermaid
flowchart TB
    SRC["IaC source + environment config"] --> PLAN["Validate / plan"]
    PLAN --> APPROVE["Review and approve"]
    APPROVE --> APPLY["Apply infrastructure"]
    APPLY --> WI["Provision workload identity"]
    WI --> DEPLOY["Deploy application with references"]
    DEPLOY --> SM["Secret manager"]
    SM --> APP["Runtime retrieves authorized secret"]
    APP --> DB[("Database")]
~~~

A deployment workflow:

1. Review module/environment configs, confirming zero plaintext secrets.
2. Provision networking, database, workload identities, and secret access policies.
3. Create/ingest credentials into the secret manager via a separate process.
4. Grant least-privilege access for the booking workload to read its corresponding references.
5. Deploy the application with non-secret configs and secret references.
6. Verify workload identity, secret retrieval, and database connectivity.
7. Enable auditing/alerts for secret reads and failed authentication attempts.
8. Test rotation in staging, verifying connection refresh.
9. Verify IaC state, plans, and CI logs contain no plaintext secrets.
10. Run DR tests to confirm recovered workloads still access keys/secrets per policy.

## 23. Common design mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Committing passwords to `tfvars`/`env` | Credentials persist in Git history | Secret references and scanning |
| Assuming env vars are inherently secure | Secrets leak via process/debug/dumps | Workload identity, mounts, or secret integrations |
| Relying solely on `sensitive` flags | Values can still persist in state/plans | Inspect tool/provider behavior, minimize secrets in IaC |
| Storing static cloud keys in CI | Long-lived credentials, huge blast radius | OIDC federation/short-lived identities |
| Sharing secrets across dev and production | One compromised environment exposes another | Separate namespaces/accounts/identities |
| Printing env/secrets in debug logs | Secrets leak through log pipelines | Redaction, log testing, and never dumping environments |
| Passing secrets in Docker build args | Can persist in layers/history/caches | Runtime retrieval or secret mounts |
| Treating Kubernetes Secret base64 as encryption | Anyone reading API/etcd obtains raw values | Encryption at rest and RBAC |
| Broad/public state backend permissions | Exposes resource mappings and state secrets | Encryption, private access, least privilege |
| Exporting secrets as module outputs | Spreads plaintext across stacks | Output references/metadata only |
| Rotating only in the secret store | Runtimes keep old connections/credentials | Refresh, verify, revoke after overlap |
| Missing secret owner/expiry | Orphaned secrets persist indefinitely | Inventory, owners, and expiry alerts |
| Treating sensitive config carelessly as secret or vice versa | Hard to govern and masks real risk | Impact-based classification |
| Auto-remediating drift without review | Overwrites hotfixes or causes outages | Review diffs and guarded remediation |
| Failing to test DR key access | Workloads recover but cannot fetch credentials | DR identity/secret/key access tests |

## 24. Design and implementation process

1. **Classify data:** config, sensitive config, secrets, credentials, and key material.
2. **Define sources of truth:** where each key is managed, owner, and precedence.
3. **Design environment boundaries:** separate accounts/projects, state backends, identities, and secret namespaces.
4. **Design IaC interfaces:** schema-validated inputs; prefer secret references; avoid plaintext outputs.
5. **Configure the secret manager:** access policies, versioning, auditing, expiry, rotation, and recovery.
6. **Design workload identities:** trust, subjects, audiences, and least privilege for deploy/runtime.
7. **Protect state/plans:** encryption, locking, versioning, access control, artifact retention, and log redaction.
8. **Design secret delivery:** pull, mount, injection, refresh, TTL, and failure behavior.
9. **Establish CI/CD guardrails:** protected branches/environments, OIDC, secret scanning, and policy-as-code.
10. **Design rotation/incident response:** overlap, verification, revocation, leak response, and evidence.
11. **Check drift/audits:** desired vs. actual config, secret versions, and effective permissions.
12. **Rehearse:** secret leaks, rotation, state recovery, and runtime restoration in another region.

## 25. Well-Architected assessment

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Is the secret/config service HA? Are runtime refresh and last-known-good policies defined? Can state/backups be recovered? Does rotation avoid downtime? |
| **Security** | Is plaintext anywhere in Git/state/logs/images? Are identities least privilege? Are environment and tenant secrets isolated? Who can read/rotate/destroy? |
| **Performance Efficiency** | Does secret retrieval add startup/request latency? Are cache TTLs and refresh intervals reasonable? Do IaC plans/applies operate at the right scope? |
| **Cost Optimization** | Are secret store/KMS calls, state retention, logs, and automation costs managed? Are unused credentials cleaned up? |
| **Operability** | Are inventories/owners, audits, drift detection, expiry alerts, rotation runbooks, policy-as-code, and DR tests in place? |

### Acceptance checklist

- [ ] Every variable is classified as non-sensitive config, sensitive config, secret, or key.
- [ ] Sources of truth, owners, schemas, defaults, and precedence are defined.
- [ ] Committed config/IaC files contain no plaintext credentials or private keys.
- [ ] Dev/staging/production environments have separate states, identities, and secret scopes.
- [ ] Runtimes/CI use workload identities or short-lived credentials where supported.
- [ ] Secret manager policies are scoped by workload, environment, and tenant.
- [ ] IaC `sensitive` marking is not mistaken for encryption or complete state redaction.
- [ ] Remote state has encryption, locking, versioning, access control, and tested restores.
- [ ] Plans, state, artifacts, and logs are neither public nor broadly downloadable.
- [ ] Container images contain no secrets in layers, `ARG`, `ENV`, or build caches.
- [ ] Kubernetes Secrets are protected with encryption at rest, RBAC, and auditing.
- [ ] Module outputs return references/metadata, never plaintext secrets.
- [ ] Rotation includes overlap, refresh, verification, revocation, and auditing.
- [ ] Secret leak response covers Git history, artifacts, state, logs, and dependent credentials.
- [ ] Policy-as-code and secret scanning run in CI/CD.
- [ ] Drift detection does not expose secrets and enforces remediation guardrails.
- [ ] DR tests verify workloads retrieve required secrets/keys upon recovery.

## 26. Applied exercise

A team deploys a booking service using Terraform and Kubernetes. The repository contains a `production.tfvars` file with a database password, a payment provider API token passed via a CI variable, a Kubernetes Secret holding a webhook signing key, and a state backend stored in object storage. Developers have read access to the repository but should not access production secrets. Workloads run across two regions; credential rotation must not disrupt transactions.

Design the following:

1. Classify each value and determine its appropriate storage location.
2. How do you purge the credential from Git history and handle this as an incident?
3. Design identities for CI plan/apply and runtime workloads.
4. Which variables should the Terraform module accept to configure the database and payment integration?
5. What checks prove secrets are not written into state or plans?
6. Which policies protect the remote state/object storage?
7. How does the Kubernetes workload retrieve the webhook signing key, and who has read permissions?
8. Design rotation overlap and connection pool/consumer updates across both regions.
9. If the secret manager is temporarily unavailable, which workloads fail open vs. fail closed?
10. Which DR/audit tests prove that after failover, workloads still retrieve the right secrets without opening cross-environment access?

A well-founded design removes plaintext from the repository, rotates and revokes exposed credentials, uses OIDC/managed identities for short-lived access, keeps only references in IaC, and lets runtimes fetch secrets via identity. Remote state is environment-isolated, encrypted, locked, and access-restricted; rotation rolls out by cohort with overlap and verification; and DR tests validate key/secret access without ever copying production credentials into staging.

**Key takeaway:** environment variables are merely a transport mechanism; IaC variables are merely a configuration interface; and `sensitive` marking does not guarantee secrets are excluded from state. Secure design separates non-sensitive configuration from secrets, uses identities for just-in-time access, minimizes where plaintext appears, and governs rotation, auditing, and recovery across the entire lifecycle.
