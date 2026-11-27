# Secrets, Persistent Volumes, and Observability in Container Apps

An API running on **Azure Container Apps** needs a database password, must write report files so other replicas can read them, and the operations team needs to pinpoint why a revision keeps restarting. These three requirements belong to three distinct layers: **secrets** protect sensitive values, **persistent volumes** retain data outside the container lifecycle, and **observability** provides visibility into the state, logs, and performance of running applications.

If you package all configuration inside the container image, write files to the local filesystem, and only watch a few lines of logs on screen, the system may work on a developer machine yet break during scale-out, revision updates, or replica restarts. This lesson explains how to structure these three layers practically, resiliently, and auditably.

This content belongs to the **Container Registry and Container Apps** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module explores the Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, while guiding deployment, monitoring, security, and cost control for application architectures. Here, the focus is **Azure Container Apps**, not a Kubernetes cluster directly administered by the learner.

> Illustrative examples use Container Apps running in a managed environment, volumes backed by Azure Files, and secrets referencing Azure Key Vault. Command names, mount limits, authentication mechanisms, and logging features may vary by Azure CLI version, environment type, and service capabilities. In real deployments, verify supported configurations in your target subscription and region.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Container Apps environment**, **container app**, **revision**, **replica**, and **container**.
2. Explain the differences between a **secret**, a plain environment variable, and configuration baked into an image.
3. Manage app-level secrets, use `secretRef`, and integrate **Azure Key Vault** with managed identity where supported.
4. Establish a secret rotation workflow, restarting or deploying revisions to pick up updated values safely.
5. Distinguish a **container's writable filesystem**, **EmptyDir**, and **Azure Files persistent volumes**.
6. Configure environment-level volumes and mount volumes into a revision's containers.
7. Identify risks of concurrent writes, file locking, ephemeral data, backups, and networking when using Azure Files.
8. Inspect **console logs**, **system logs**, Azure Monitor metrics, and distributed traces.
9. Write Log Analytics queries, configure alerts, and correlate logs with revisions, replicas, and request IDs.
10. Diagnose errors such as unreadable secrets, failed mounts, replica restarts, scale-to-zero, or missing application logs.
11. Design solutions balancing security, data durability, performance, and cost.

## 2. Understanding Operational Units in Container Apps

Azure Container Apps is a managed container platform supporting capabilities such as **HTTP/TCP ingress per supported configuration**, revisions, scaling, and integrated logging/monitoring.

| Object | Role | Impact When Changed |
|---|---|---|
| **Container Apps environment** | Shared boundary for a group of Container Apps: network infrastructure, log config, and environment settings like storage mounts. | Changes can affect multiple apps sharing the environment. |
| **Container app** | Logical resource holding app configuration, ingress, app-level secrets, and revisions. | Can have multiple revisions depending on revision mode. |
| **Revision** | Immutable snapshot of deployment template properties such as image, container env, volumes, and scale rules per config capabilities. | Template changes typically create a new revision; certain app-level settings do not. |
| **Replica** | A running instance of a revision containing one or more containers/sidecars per template. | Can be created, reclaimed, or restarted during scaling/rollouts. |
| **Container** | Process, image, env vars, and declared volume mounts. | Internal filesystem must not be treated as durable storage. |
| **Container Apps Job** | Mechanism for running workloads per execution, schedule, or event. | Not identical in revision/ingress semantics or lifecycle to long-running apps. |

### Two Revisions and Multiple Replicas Model

```text
Container Apps environment: cae-orders-prod
│
├── Storage mapping: reports-storage --> Azure Files share
├── Logging destination: Log Analytics / supported sink
│
└── Container App: orders-api
    ├── App-level secret: db-password
    ├── App-level ingress: HTTPS endpoint
    │
    ├── Revision: orders-api--r1
    │   ├── Replica A --> container orders-api
    │   └── Replica B --> container orders-api
    │
    └── Revision: orders-api--r2
        ├── Replica C --> container orders-api
        └── Replica D --> container orders-api
```

**Single revision** and **multiple revisions** modes differ in deployment and traffic behavior. In multiple revisions mode, traffic can be split across revisions per configuration. **A container app secret is not a separate per-replica secret**, while environment variables declared in the revision template determine how each container references that secret.

## 3. Three Data Layers That Must Be Designed Separately

| Data | Example | Appropriate Placement | What Not to Do |
|---|---|---|---|
| **Secrets** | API tokens, DB passwords, sensitive connection strings. | App-level secrets or Key Vault references via managed identity. | Hardcode into Dockerfiles, Git, logs, or images. |
| **Non-sensitive configuration** | `LOG_LEVEL=info`, queue names, non-sensitive feature flags. | Environment variables or policy-compliant configuration stores. | Use secrets merely because every variable feels "confidential." |
| **Persistent state** | Report files, user documents, shared data. | Azure Files, Blob Storage, databases, or dedicated storage services. | Write solely to the container's writable layer. |
| **Ephemeral data** | Rebuildable caches, short-lived intermediate files. | EmptyDir or appropriate scratch storage. | Place on persistent shares unnecessarily. |
| **Logs/metrics/traces** | Exceptions, request IDs, latency, scale errors. | stdout/stderr, Azure Monitor, Log Analytics, and tracing backends. | Write only to a volatile local file. |

A well-designed Container App is typically **stateless at the HTTP serving layer**: containers can be replaced at any moment, while important data lives outside the replica lifecycle.

## 4. What Is a Secret in Azure Container Apps?

A **secret** is a configuration entry holding a protected value managed at the **container app level**. The application does not bake the value into the image; containers can reference secrets through environment variables or other platform-supported mechanisms.

For example, an app needs:

- `DB_PASSWORD` to connect to a database.
- `PAYMENT_API_TOKEN` to call a payment service.
- A credential for a scale rule or supported integration.

In Container Apps, the secret name might be `db-password`; the container uses **`secretRef: db-password`** to inject the value into the `DB_PASSWORD` variable. Those two names belong to two separate configuration layers.

### Distinguishing Plain Configuration from Secrets

```text
App-level secrets
  db-password  ──────────────┐
                             │ referenced via secretRef
Revision template            ▼
  Container: orders-api
    env:
      LOG_LEVEL   = info                 (plain value)
      DB_PASSWORD = secretref:db-password (sensitive value)
```

**Do not place passwords directly into `env.value`** even though the container can read it. The value can leak through templates, CLI output, IaC state, or auditing tools not designed to hold secrets. Instead, declare a dedicated secret and reference it by name.

### A Secret Does Not Automatically Create Access Permissions

For instance, if a container holds a secret with a valid token yet a **network firewall** blocks the route to the database, the app still cannot connect. Conversely, opening network access to the database does not replace valid credentials. Verify **secrets, identities, networking, and target-system permissions** together.

## 5. App-Level Secrets and Revision Boundaries

This is one of the most important operational distinctions in Container Apps:

- **Secrets reside in container-app-level configuration**, not frozen as part of each revision's immutable template in the same way versioned image/env templates are.
- **Environment variables referencing secrets** live in the revision's container template.
- Adding, editing, or deleting an app-level secret **does not necessarily create a new revision**.
- A container process reading environment variables at startup **should not be assumed to update its in-memory value automatically when a secret rotates**.
- After updating a secret, verify the refresh behavior of the secret source and platform. For app-level secret updates, you often must **restart revisions** or **deploy a new revision** via supported workflows so containers pick up the new value; Key Vault references follow their own refresh behavior.

### Lifecycle Example

```text
09:00  Secret db-password = version A
       Revision r1 starts running, reads DB_PASSWORD=A

10:00  Security team rotates credential to version B
       App secret or Key Vault reference is updated

10:01  Do not assume running process r1 already received B
       → Verify refresh/restart behavior for the secret type

10:05  Safe rollout/restart, monitor new replicas
       → Confirm DB connection succeeds with B

10:15  Revoke A after confirming zero remaining dependencies
```

**Note on Key Vault references:** when referencing an unpinned version, the platform may update the reference and restart revisions using the secret per documented behavior. Never substitute real testing with assumptions like "every secret needs a manual restart" or "every secret updates instantaneously." Measure detection lag and confirm revisions/replicas actually use the new credential.

## 6. Using Azure Key Vault and Managed Identity

For production environments, centralized secret management typically stores **actual values in Azure Key Vault** and configures Container Apps to **reference** them using managed identity.

### Components

1. **Key Vault:** stores secrets, versions, rotation policies, and audit logs.
2. **Managed identity:** the container app's Azure identity, either system-assigned or user-assigned per supported features.
3. **Azure RBAC/Key Vault access policy:** permits the identity to perform only required **Get secret** operations, without granting full vault administration.
4. **Network access:** if the vault restricts networks, the Container Apps environment must have an appropriate path to reach it.
5. **Container Apps secret reference:** points to the Key Vault secret using that identity.
6. **Revision template:** references the app-level secret name via `secretRef`.

### Recommended Setup Sequence

1. Create or select a Key Vault in an approved tenant/subscription.
2. Create a test secret, e.g., `orders-db-password`; never use production passwords in lessons.
3. Enable managed identity on the Container App.
4. Grant an appropriate secret-read role (e.g., **Key Vault Secrets User** under Azure RBAC) at the narrowest needed scope.
5. Verify networking/DNS lets both the app and platform services reach the vault per supported mechanics.
6. Create an app-level secret referencing the Key Vault secret URI with that identity.
7. Reference the app secret in the revision template.
8. Test connectivity to the target system; never print the secret value to "verify."
9. Set up monitoring for Key Vault access denials or expired secrets.

**Managed identity eliminates storing a client secret just to authenticate to Key Vault.** That does not mean every downstream target automatically supports managed-identity sign-in. If the database supports Microsoft Entra authentication, consider eliminating application passwords altogether where suitable.

## 7. Sample YAML: App Secrets, Key Vault, and secretRef

The snippet below illustrates **relevant configuration fields**, not a complete deployable manifest. Image names, vault URLs, and identities are placeholders; the app must already have its identity and permissions configured.

```yaml
configuration:
  secrets:
    - name: db-password
      keyVaultUrl: https://kv-orders.example.vault.azure.net/secrets/db-password
      identity: system

template:
  containers:
    - name: orders-api
      image: example.azurecr.io/orders-api:1.0.0
      env:
        - name: LOG_LEVEL
          value: info
        - name: DB_PASSWORD
          secretRef: db-password
```

**Reading the two layers:**

- `configuration.secrets`: declares the app-level secret (Key Vault reference).
- `template.containers[].env[].secretRef`: injects the secret's value into a container environment variable.

The URL above illustrates structure only. In practice, use the real URI formatted as `https://<vault-name>.vault.azure.net/secrets/<secret-name>` for a valid, existing vault. If using a user-assigned identity, the `identity` field must specify the exact resource ID/identity per supported schema instead of `system`.

### Never Place Secrets in Code or Terminal History

Anti-pattern to avoid:

```bash
# DO NOT DO THIS: password appears directly in command history.
az containerapp update --name orders-api \
  --resource-group rg-apps \
  --set-env-vars "DB_PASSWORD=MyProductionPassword"
```

This is an **anti-pattern example**, not a command to execute. Avoid commands passing secret values in CLI arguments. Use Key Vault references, managed identities, and deployment workflows that protect sensitive data.

### Constraints When Modifying Secrets

- Modifying a secret can impact **multiple revisions** sharing the reference.
- Deleting a secret still referenced by a revision or scale rule can cause startup or authentication failures.
- A time-limited token may expire while replicas stay running; apps need retries, refreshes, or redeploys per design.
- Secrets injected as environment variables can still be leaked by buggy app code via crash reports, debug endpoints, or logs.
- Permissions to view app metadata and permissions to read secret values must be governed separately; never grant secret-read rights just to inspect secret names.

## 8. Safe Secret Rotation and Revocation Workflow

A proper **rotation** includes validation and a rollback plan. Suppose you must rotate the database password used by an app:

1. **Scope:** which container apps, revisions, jobs, or connections use the old credential?
2. **Prepare new credential:** if the target system allows, provision the new credential in parallel to avoid cutting active connections.
3. **Update Key Vault:** create a new secret version or secret per design.
4. **Verify permissions and reachability:** managed identity has Get rights; DNS/networking allow access.
5. **Roll out safely:** depending on the secret mechanism, restart revisions or deploy a new revision; optionally use traffic splitting in multiple revisions mode to reduce risk.
6. **Verify:** inspect DB connection metrics, error logs, health probes, and HTTP 5xx rates on new replicas.
7. **Revoke old credential:** only after confirming all consumers have switched over.
8. **Record evidence:** timestamp, approver, affected resources, secret version, and outcome.
9. **Rollback:** if errors appear, maintain a recovery path that never pastes secrets into chat or tickets.

**Never log statements** like `"DB_PASSWORD is " + password`. During testing, log only `"secret loaded"` or connection check status—never values, prefixes, suffixes, or tokens.

## 9. Why a Container Filesystem Is Not Persistent Storage

Each replica has an independent lifecycle. Container Apps can spin up or reclaim replicas during autoscaling, revision updates, host maintenance, retries, or failures.

Suppose an app writes `/app/uploads/customer.pdf` to the container's writable layer:

```text
Replica A:
  /app/uploads/customer.pdf  ← contains data

Replica B:
  /app/uploads/              ← lacks A's file

Replica A is replaced:
  data stored solely on the writable layer can be lost
```

This causes two common failures:

- A user uploads via replica A, refreshes onto replica B, and gets 404 because the file does not exist on B.
- After an image rollout or scale-to-zero and back up, files in the old writable layer vanish.

Rule: **container images + local writable filesystems are never the sole home for important data**. Choose storage decoupled from replica lifecycles, or keep apps stateless with Blob Storage/databases.

## 10. Comparing EmptyDir, Azure Files, and Other Storage Approaches

| Mechanism | Lifecycle / Sharing | Good For | Avoid For |
|---|---|---|---|
| **Container writable layer** | Tied to container instance; no durability on replacement. | Small temp files, regenerable caches. | User files, sole checkpoints. |
| **EmptyDir volume** | Ephemeral to the **replica** lifecycle; shareable across containers inside that replica via mounts. | Scratch space, files exchanged between sidecars in one replica. | Data needed after replica loss or shared across replicas. |
| **Azure Files volume** | File share outliving replicas; mountable across replicas per supported configuration. | Shared files, exported reports, apps requiring a filesystem. | Assuming drop-in database transactions or high-perf filesystem for every workload. |
| **Azure Blob Storage** | Durable object storage accessed via SDK/API; not natively a POSIX filesystem. | Uploads, artifacts, media, logs/exports, large files. | Apps strictly requiring POSIX atomic locks unsupported by Blob APIs. |
| **Database/managed state store** | State managed under DB consistency models. | Sessions, orders, transactional state. | Simple large blobs where object storage fits better. |

**EmptyDir does not mean "permanently provisioned disk."** When a replica is reclaimed, ephemeral data is not a recovery point. In multi-replica workloads, each replica gets its own EmptyDir space, not shared across the app.

### Selection Rules

- **User-uploaded files:** prefer Blob Storage if the app supports object APIs.
- **Mountable shared directory:** Azure Files when protocol/performance requirements fit.
- **Caches/temporary processing:** EmptyDir when lost data can be recomputed.
- **Sessions and transactional state:** Redis/databases matching consistency and SLA needs.
- **Sensitive config:** secrets/Key Vault; never put them in a shared file just to avoid `secretRef`.

## 11. Azure Files Persistent Volume Model in Container Apps

With Azure Files mounts, distinguish **two configuration objects**:

1. **Environment-level storage:** the Container Apps environment holds connection details to an Azure Files share under a logical storage mapping name. At this layer, the environment requires share authentication supported by the feature.
2. **App revision volume:** the revision template declares a volume referencing that storage mapping name, and **volumeMounts** maps the volume to a path inside the container.

```text
Azure Storage account: stordersfiles
    |
    +-- File share: reports
             |
             | SMB / network + credentials per supported config
             v
Container Apps environment: cae-orders-prod
    |
    +-- environment storage mapping: reports-storage
             |
             v
Container App: orders-api
    |
    +-- Revision template
          |
          +-- volume name: reports-volume
          |     storageType: AzureFile
          |     storageName: reports-storage
          |
          +-- container volumeMount:
                /mnt/reports
```

**This volume is not a manually created Kubernetes PersistentVolumeClaim (PVC).** Container Apps uses its own managed storage mount declarations; never copy AKS `PersistentVolume`/`PersistentVolumeClaim` manifests verbatim into app YAML expecting identical behavior.

### Prerequisites to Verify

- Storage account and file share already exist.
- Azure Files protocol and mount mechanism are supported by the Container Apps environment (e.g., SMB in common scenarios).
- Network connectivity from the environment to Storage, including firewalls, DNS, and private endpoints if using private access.
- Credentials/auth for the environment storage mapping are valid and protected.
- Storage mapping name matches `storageName` in the app volume.
- Read-only/read-write permissions, OS user settings, file permissions, and mount paths.
- Azure Files quotas, IOPS, throughput, latency, and connection limits fit application load.

An app container reading secrets from Key Vault **does not mean** Azure Files mounts automatically use that same managed identity. Environment storage authentication has its own configuration; do not assume Identity → Key Vault rights also authorize Azure Files SMB mounts.

## 12. Sample YAML: Azure Files Volume and volumeMounts

This is a **configuration excerpt**, assuming the environment already defines storage mapping `reports-storage` pointing to a file share and the app uses a compatible image.

```yaml
template:
  containers:
    - name: orders-api
      image: example.azurecr.io/orders-api:1.0.0
      env:
        - name: REPORT_DIRECTORY
          value: /mnt/reports
      volumeMounts:
        - volumeName: reports-volume
          mountPath: /mnt/reports

  volumes:
    - name: reports-volume
      storageType: AzureFile
      storageName: reports-storage
```

Reading the links:

- `template.volumes[].name` is the volume name **within the revision**.
- `storageType: AzureFile` specifies the mount type.
- `storageName: reports-storage` references the storage mapping **on the environment**.
- `volumeMounts[].volumeName` binds the container to the volume.
- `mountPath` is the directory the app reads and writes.

**Very common mistake:** the environment defines storage `reports-storage`, yet the revision specifies `storageName: report-storage` (missing `s`). Mounts fail even while the storage account and file share remain healthy.

### EmptyDir Example for Scratch

```yaml
template:
  containers:
    - name: processor
      image: example.azurecr.io/processor:1.0.0
      volumeMounts:
        - volumeName: scratch
          mountPath: /tmp/work

  volumes:
    - name: scratch
      storageType: EmptyDir
```

If sharing EmptyDir with a sidecar in the **same replica**, add a matching `volumeMount` to the sidecar; **never** expect a sidecar in another replica to read those files.

### Do Not Confuse Volume Paths with Existing Image Contents

Mounting a volume onto a path that already holds files in the image **masks the underlying contents** at runtime. Therefore pick `/mnt/reports` rather than mounting over folders holding critical app binaries or configs. During rolling updates, two revisions may mount the same share concurrently; applications must handle concurrent reads/writes safely.

## 13. Persistent Does Not Automatically Mean Consistent or Safe

A persistent file share survives container replacements, yet keep in mind:

### Multiple Replicas Writing the Same File

Suppose replicas A and B write `/mnt/reports/status.json` simultaneously. Outcomes can include:

- Overwriting each other.
- Reading half-written files.
- File lock contention or access errors depending on app and protocol.
- One replica caching stale data while another replica wrote updates.

Azure Files provides supported protocol semantics, yet **does not automatically turn an app lacking concurrency control into a safe transactional system**.

Mitigations:

- Use unique filenames keyed by job or request ID.
- Write to a temporary file, flush/validate, and rename per filesystem semantics.
- Use queues/workers to serialize writes or use appropriate distributed locks.
- Store transactional data in a database rather than a file share.
- Test the app with **at least two replicas** and rolling revision deployments.

### Persistent Volumes Are Not Backups

If someone accidentally deletes a file on Azure Files, all replicas see the deletion per share semantics. A persistent volume only decouples data from the **replica lifecycle**; it does not provide version history or ransomware immunity.

Evaluate:

- Azure Files snapshots/backups and soft delete for shares where supported.
- Retention, RPO/RTO, recovery targets, and file restore procedures.
- Redundancy (LRS/ZRS/GRS/GZRS) per account type and region.
- File/share deletion permissions, access key rotation, and auditing.
- Storage account, network, or regional outages.

## 14. Networking, Identity, and Performance of Azure Files Mounts

A mount can fail even when the Storage account exists and keys are accurate. Inspect the **network path from the Container Apps environment to Azure Files**.

### Networking

- For storage accounts with firewalls, confirm traffic from the environment is permitted.
- If using private endpoints, ensure accurate private DNS resolution for the Azure Files endpoint and routing to the private IP.
- Verify ports/protocols required by Azure Files (e.g., SMB over TCP 445 in SMB scenarios).
- Do not confuse the Container App's HTTPS ingress with outbound networking from replicas to Azure Files.
- If egress routes through firewalls/UDRs, ensure Storage flows are not inadvertently blocked.

### Credentials

- Environment storage mappings typically define share authentication separately per supported mechanism, such as storage account keys in standard Azure Files mount setups.
- Never print account keys in tickets, public Terraform plans, shared YAML files, or command history.
- When rotating keys, update mappings/credentials in a tested sequence to avoid dropping mounts.
- Check alternative auth modes per actual support; **never assume the managed identity used for app secrets automatically grants mount rights**.

### Performance

- A file share has capacity, IOPS, and throughput caps based on the selected tier.
- Scaling up replicas multiplies reads/writes against the same share, turning storage into a bottleneck.
- Many tiny files generate heavy metadata operations.
- Private networking/region and file sizes affect latency.
- Monitor Azure Files metrics alongside app metrics, not just container CPU.

If a workload only exports a few report files hourly, Azure Files fits nicely. If the app serves millions of images or Internet uploads, Blob Storage with object APIs is usually superior operationally.

## 15. Three Pillars of Container Apps Observability

**Observability** answers three distinct questions:

- **Logs:** what happened, and which errors appeared at what time?
- **Metrics:** is the system showing anomalies in replica count, request rate, CPU, memory, latency, or errors?
- **Traces:** which services did a request traverse, and which component was slow or failed?

| Pillar | Examples | Tools / Data Sources |
|---|---|---|
| Logs | Exceptions, startup logs, probe failures, scale events. | Console logs, system logs, Log Analytics, and configured log sinks. |
| Metrics | Replica count, CPU/memory utilization, requests, errors, latency. | Azure Monitor metrics, dashboards, and alert rules. |
| Traces | HTTP request → API → database → queue worker. | Application Insights/OpenTelemetry or configured tracing integration. |

**Do not assume simply enabling Container Apps provides full distributed tracing.** End-to-end tracing usually requires instrumentation, exporters/agents, and an appropriate tracing backend. Having logs and metrics does not automatically emit spans for every request.

## 16. Console Logs vs. System Logs: Reading the Right Source

Azure Container Apps distinguishes two critical log streams:

### Console Logs

These capture application/container output on **stdout** and **stderr**, for example:

```text
2026-11-20T08:00:00Z level=info service=orders-api revision=r12
  event=startup completed

2026-11-20T08:02:14Z level=error service=orders-api revision=r12
  event=storage_write_failed request_id=demo-4 reason=timeout
```

If an application writes logs solely to `/app/logs/service.log` inside the container filesystem without a log shipper, that output **will not automatically appear** in console logs. In Container Apps, write structured application logs to stdout/stderr.

### System Logs

These contain events emitted by the **Container Apps platform**, helping investigate:

- Revision creation or activation.
- Replica/container starts or failures.
- Image pull, configuration, or container startup errors.
- Health probe failures.
- Scale operations and environment-level events.
- Volume mount or runtime config failures when logged by the platform.

**System logs do not replace console logs.** If an app crashes with an exception before starting its HTTP server, console logs hold the stack trace while system logs reveal replica restarts and probe failures.

### Adding Context to Every Log

An event should include appropriate fields:

- `timestamp` (UTC).
- `service` and `revision`.
- `replica` or instance identifier when available.
- `request_id` / `trace_id`.
- `severity`, `event`, `duration_ms`.
- Error type, dependency, HTTP status code.
- `job_id` for background processing.

**Never log:** passwords, access tokens, Storage account keys, full connection strings, payment card details, or unnecessary personal data.

## 17. Observing Revisions, Replicas, and Scaling

Container Apps can scale on HTTP concurrency, CPU/memory, or supported event sources via KEDA. As load rises, more replicas launch; when load subsides, replicas scale down to configured minimums, including **scale-to-zero** when supported by the app and scale rules.

### What to Check

| Signal | Question |
|---|---|
| **Active revisions** | Which revision receives traffic? Are old revisions still active? |
| **Replica count** | Does the app spin up enough replicas under load? Is scaling too slow? |
| **Min/max replicas** | Do scale bounds match traffic profiles and budget? |
| **CPU/memory usage** | Is there throttling, OOM, or hitting resource limits? |
| **Request rate/error rate** | Did errors rise after a rollout or during scale-out? |
| **Latency p95/p99** | Is a subset of requests slow even while averages look fine? |
| **Scale triggers** | Are rules or secrets used to authenticate event sources still valid? |
| **Restarts/terminations** | Did replicas restart due to crashes, health probes, revision swaps, or scale actions? |

An app at `minReplicas: 0` may have **zero running replicas** when no traffic/events arrive. Seeing no new console logs during idle periods does not prove logging is broken. Still, if an app must process work continuously, ensure trigger types and min replicas match.

### Revision Rollout and Observation

Suppose r12 is newly deployed:

1. Check Ready/Healthy replica count for r12.
2. Check r12 console logs for startup, secret, and volume mount errors.
3. Compare HTTP 5xx and p95 latency between r11 and r12.
4. In multiple revisions mode, adjust traffic per supported rollout strategy.
5. If r12 fails, roll back to r11 per procedure; **remember revision rollback does not undo writes already made to Azure Files or databases**.

## 18. Using the Azure Portal to Inspect Logs and Metrics

A basic operational workflow:

1. Open [Azure Portal](https://portal.azure.com/) and select the right subscription.
2. Open **Container Apps** and choose the app to inspect.
3. View **Revisions and replicas** to confirm active revisions, states, and replica counts.
4. Open **Log stream** or **Logs** per current Portal UI; select the right container and log type.
5. Compare console logs with system logs at the **exact same UTC timestamp**.
6. Open **Metrics** to inspect requests, CPU, memory, replicas, and supported metrics.
7. If the environment sends logs to Log Analytics, open the workspace and query by app/revision/time.
8. Check **Alerts** to see which events fired alerts.
9. If the app uses tracing, open Application Insights/trace backend to inspect affected requests.

**Seeing logs in Log stream does not mean long-term retention is configured.** Verify logging destination, workspace, retention window, sampling, and ingestion caps.

## 19. Inspecting Status via Azure CLI

The commands below are **read-only metadata or log queries**; they do not expose secret values or modify apps. Substitute placeholders accordingly. If the CLI reports missing commands, check the **containerapp** extension version via CLI docs in an authorized environment.

### Verify Context

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table
```

### Inspect App and Revisions

```bash
az containerapp show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{name:name,revisionMode:properties.configuration.activeRevisionsMode,minReplicas:properties.template.scale.minReplicas,maxReplicas:properties.template.scale.maxReplicas}" \
  --output json

az containerapp revision list \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### List Secret Names Without Printing Values

```bash
az containerapp secret list \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "[].name" \
  --output tsv
```

The goal is inspecting **configured secret names**. Avoid flags that reveal values, avoid saving sensitive full configs to log files, and never send CLI outputs containing secrets to unauthorized recipients.

### List Environment Storage Mappings

```bash
az containerapp env storage list \
  --name "<ENVIRONMENT_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

The environment storage mapping name must match `storageName` in the revision template. Listing storage mappings does not prove a file share mounted cleanly on replicas; inspect system logs and mount paths too.

### View Console Logs and System Logs

```bash
az containerapp logs show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --type console \
  --tail 50

az containerapp logs show \
  --name "<APP_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --type system \
  --tail 50
```

You may need to specify revision, replica, or container in multi-component apps. Check `az containerapp logs show --help` for your CLI version's options. During incidents, record UTC timestamps and log sources so logs from prior revisions are not mixed with active ones.

## 20. Querying Log Analytics with KQL

When the Container Apps environment sends logs to **Log Analytics**, you can search events by app and timeframe. Table names and schemas can differ by logging integration and service version; many workspaces contain tables such as `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL`.

### Finding Application Error Logs

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == "orders-api"
| where Log_s has_any ("error", "exception", "failed")
| project TimeGenerated, ContainerAppName_s, RevisionName_s,
          ContainerName_s, Log_s
| order by TimeGenerated desc
```

### Finding Platform Errors

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == "orders-api"
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated desc
```

These are **reference schema query examples**. If your workspace uses `ContainerAppConsoleLogs` or different column names, inspect **Tables/Schema** in Log Analytics, verify real rows, and adapt the query. Never conclude "zero errors" simply because a query copied from another schema returned empty results.

### Correlating Logs with Metrics and Traces

Suppose a dashboard flags a spike in HTTP 5xx at 08:15:

1. Select the 08:10–08:20 UTC window.
2. Search console logs for errors on the revision receiving traffic.
3. Check system logs for crash, probe failure, volume mount, or scaling events.
4. If logs contain trace IDs, open the tracing backend to see which dependency timed out.
5. Check Azure Files/Storage, Key Vault, or database metrics if errors involve those services.

A log line mentioning `timeout` alone does not prove the database timed out; cross-check request ID, timestamp, and dependency traces.

## 21. Distributed Tracing and Correlation IDs

When requests traverse multiple services, `orders-api` logs alone may not reveal the root cause:

```text
Client
  |
  v
API Gateway / Ingress
  |
  v
orders-api  --HTTP--> payment-api
  |
  +--SQL--> database
  |
  +--Queue--> order-worker
```

With OpenTelemetry or equivalent instrumentation, each request carries a **trace ID** and **spans** measuring time spent in each component.

Example:

```text
trace_id = 71f3... (illustrative, not a token)
  orders-api POST /orders          580 ms
    ├── database INSERT             35 ms
    ├── payment-api POST /charge   490 ms
    └── queue publish               12 ms
```

This reveals that `payment-api` accounts for most of the latency instead of guessing ingress is slow.

### Prerequisites for Valuable Tracing

- Applications are instrumented with an appropriate SDK/agent or integration.
- Trace context propagates across HTTP/gRPC/queues per standard protocols where supported.
- Exporters send telemetry to Application Insights or an approved tracing backend.
- Sampling/retention captures failing requests reliably.
- Logs include trace IDs to link directly to spans.
- Never place secrets or sensitive PII inside span attributes.

**Dapr can assist observability in Dapr-enabled apps**, yet enabling Dapr does not automatically trace all database calls and custom methods inside app code. Verify exact instrumentation and telemetry export pipelines.

## 22. Designing Alerts by Impact, Not Just Resources

A pretty dashboard cannot replace actionable alerts with clear ownership.

| Alert Condition | Purpose | Response |
|---|---|---|
| HTTP 5xx rate rises steadily | Customers are hitting errors. | Check revision rollouts, logs, dependencies. |
| Unusual replica restarts/crashes | Application instability. | Classify OOM, secret, probe, image, or mount causes. |
| p95 latency breaches threshold | Service slowdown. | Compare traces, CPU/memory, downstream latency. |
| Replicas pinned at max for prolonged period | Possible capacity shortfall or poorly tuned scale rules. | Check throughput, rules, quotas, and service limits. |
| Repeated auth errors in console logs | Secrets/identities or downstream permissions changed. | Check Key Vault/DB/Storage roles and rotation timelines. |
| Rising Azure Files write errors | Persistent storage failing requests. | Check mounts, networking, quotas, IOPS, locks. |
| Zero new logs when app should be active | Broken logging pipeline or stalled app. | Verify requests, revision state, and log destination. |
| Anomalous rise in log/storage costs | Excess telemetry or workload shift. | Tune sampling, retention, log verbosity, and budgets. |

### Avoiding Alert Noise

- Alert on **error rates/ratios** and observation windows, not raw absolute counts alone.
- Distinguish zero traffic caused by **valid scale-to-zero** from zero traffic caused by an outage.
- Maintain **per-revision** dashboards to spot newly deployed regressions quickly.
- Define owner, severity, escalation, and runbooks for every alert.
- Test with simulated faults in a lab before relying on alerts in production.

## 23. Deployment Workflow via the Azure Portal

### Phase A: Preparation

1. Select subscription, resource group, and region.
2. Have a Container Apps environment and app with images governed in Azure Container Registry or a compatible registry.
3. Prepare the app's managed identity, Key Vault secrets, and secret-read permissions if integrating Key Vault.
4. Create an Azure Storage account/file share if the app genuinely requires a persistent filesystem.
5. Map data sources: plain variables, secrets, file shares, Blob Storage, and logs.
6. Finalize networking, DNS, retention, backups, metrics, and budget requirements.

### Phase B: Configure Secrets

1. Open **Container Apps → your app → Secrets** in the Portal.
2. Add app-level secrets with securely managed values or supported Key Vault references.
3. If using Key Vault, choose the managed identity, secret URI, and verify permissions.
4. Open the revision's container config and add environment variables **referencing the secrets**.
5. Deploy the revision per procedure, checking health and authentication logs.
6. Document rotation mechanisms and how existing revisions refresh secrets.

### Phase C: Configure Persistent Volumes

1. Create the Azure Files share in the storage account, confirming protocol and connectivity.
2. Under **Container Apps environment**, declare **environment storage** pointing to the share via supported methods.
3. In Container App configuration, add an Azure Files volume referencing the storage mapping name.
4. Mount the volume at a dedicated container path, e.g., `/mnt/reports`.
5. Deploy the new revision and check system logs during mount.
6. Test reading/writing a **lab** file and reading it back from another replica or revision if required by your app model.
7. Verify backups, concurrent write safety, and behavior when storage is unavailable.

### Phase D: Enable Observability

1. Specify the destination for application/system logs on the environment.
2. Configure a Log Analytics workspace or appropriate logging sink.
3. Emit structured stdout/stderr logs including request IDs and trace IDs.
4. Open Azure Monitor metrics for the app and build per-revision dashboards.
5. Integrate tracing if workflows span multiple services.
6. Set alerts for 5xx errors, restarts, latency, auth failures, mount errors, and quotas.
7. Run an incident drill in a lab to confirm you can trace failures back to root cause.

## 24. Troubleshooting Secrets, Key Vault, and Revisions

| Symptom | Possible Cause | Isolation Steps |
|---|---|---|
| Container lacks `DB_PASSWORD` variable | Missing `secretRef` in env template or typo in secret name. | Inspect revision template and app-level secret names. |
| Secret exists yet cannot be read | Identity lacks permission or Key Vault blocks access. | Check identity, roles, vault firewall/DNS, and Key Vault logs. |
| App keeps using old credential after rotation | Revision not refreshed or Key Vault ref has not synced per supported mechanics. | Check version reference, revision restart/rollout, and refresh timing. |
| Replica fails startup after deleting secret | Secret still referenced by env var or scale rule. | Inspect dependencies and restore secret safely. |
| Secret matches yet DB reports unauthorized | Target user/password mismatch or DB rights revoked. | Check DB auth, account lockouts, and networking without printing credentials. |
| One revision works while another fails | Different template/`secretRef`/runtime/identity, or uneven refresh. | Compare configurations and logs per revision. |
| App leaks secret in logs | Code dumps env/config or exception includes credentials. | Stop exposure, rotate secret, audit log access, fix logging. |

### Runbook When Secret Rotation Breaks an App

1. Identify the app, revision, timestamp of the Key Vault secret change, and HTTP 5xx rate.
2. Inspect Key Vault secret version/expiration/permissions and managed identity.
3. Confirm container env references the exact app-level secret name.
4. Verify networking to Key Vault and downstream services.
5. If needed, restart the revision or roll out a new revision via supported methods and watch readiness.
6. Inspect logs **free of secret values**, checking only connection status.
7. Restore service with the prior credential version **only if still valid and approved**, without logging its value.
8. Document root cause, affected revisions, and updates to the rotation procedure.

## 25. Troubleshooting Persistent Volumes

| Symptom | Causes to Check | Resolution Direction |
|---|---|---|
| Replica fails to start after adding volume | Wrong `storageName`, missing mapping, invalid volume config. | Read revision YAML and environment storage; check system logs. |
| Mount fails | Nonexistent share/account, bad credentials, blocked network/SMB. | Verify Azure Files, keys, firewalls, DNS/routes, and ports. |
| App reports `Permission denied` on write | File permissions, read-only access mode, UID/GID, or app path. | Check mode, ownership, and target directory inside container. |
| Write succeeds yet another replica cannot see it immediately | App wrote to local path instead of mount, caching, or concurrency. | Check mount path, flush/locking, and replication semantics. |
| Files disappear after scale or revision change | Wrote only to writable layer/EmptyDir, not persistent share. | Verify actual `storageType` and `mountPath`. |
| Share slows down during scale-out | IOPS/throughput quotas, lock contention, many tiny files. | Measure Azure Files metrics and optimize workload/tier. |
| Storage outage causes app 5xx | Hard dependency on share with no fallback. | Add appropriate retries/backoff, queues, caches, and circuit breakers. |
| Rolled back revision yet files remain at new version | Persistent storage lives outside revisions. | Restore from backups/snapshots; never treat app rollback as data rollback. |

### Checking Paths from Inside a Container

When a replica is running and administrators have authorized console/exec access, run **read-only** checks:

```bash
pwd
ls -ld /mnt/reports
df -h /mnt/reports
```

Never write test files into sensitive production directories just to verify mounts. When write tests are needed, use an authorized lab share/directory with unique filenames and clean up per procedure.

## 26. Troubleshooting Missing Logs or Metrics

### Case 1: No Console Logs

Check in order:

1. Does the app have an active revision and genuinely running replicas?
2. Is traffic/events arriving, or did the app validly scale to zero?
3. Does code write to stdout/stderr or only to a local file?
4. Did you select the exact container/revision/replica and UTC timeframe?
5. Is a logging destination configured on the environment?
6. Does the workspace have the right subscription, permissions, and ingestion/retention?
7. Does your KQL query match actual table/schema names?

### Case 2: Console Logs Exist Yet System Logs Are Missing

Check log category, recent deployment activity, logging destination, and query permissions. Zero system events during a quiet period **does not automatically prove a fault**.

### Case 3: Metrics Look Healthy Yet Users Report Slowness

- Average latency can mask p95/p99 latency spikes.
- Low CPU does not prove databases or Storage are unthrottled.
- Certain metrics depend on data sources/agents or feature support.
- Traces reveal which downstream call slowed down the request.
- Sometimes requests get blocked before reaching the app, so app metrics miss ingress failures.

### Case 4: Replica Restarts Repeatedly

- Check exit codes, OOM errors, and readiness/liveness probes.
- Read app console logs immediately prior to the restart.
- Check system logs for image pulls, revision activations, mounts, and scaling.
- Diff recent changes: image, secrets, volumes, env vars, and resource limits.
- Never blindly raise memory limits when the root cause is an exception crash-loop from bad credentials.

## 27. Balancing Cost, Security, and Reliability

Potential cost-generating components:

| Group | Cost / Limits to Estimate |
|---|---|
| **Container Apps compute** | CPU, memory, replica counts, active time, and environment billing model. |
| **Azure Files** | Capacity, tier, read/write transactions, performance, and redundancy. |
| **Key Vault** | Operations, key/secret management, networking, and logging per service pricing. |
| **Azure Monitor/Log Analytics** | Log ingestion, retention, alerts, queries, and exports. |
| **Application Insights/tracing** | Telemetry volume, sampling, storage/retention, and related charges. |
| **Networking** | Private endpoints, VNet egress, NAT/firewalls, and data transfer where applicable. |
| **Backup/DR** | Snapshots, retention, vaults, or independent data protection solutions. |

### Grounded Choices

- Never provision an Azure Files share just for **temporary caches** that can safely vanish when replicas exit.
- Never keep **debug logs** containing huge payloads indefinitely.
- Never slash log retention so low that incidents discovered days later lack investigative data.
- Never scale replicas excessively when all replicas contend on one small file share.
- Never distribute storage account keys across every app as app-level secrets when identity-based APIs or narrower permissions work.
- Never treat using managed identity as an excuse to skip securing management endpoints, logs, and networks.

### Workload Budgeting Example

Suppose a service exports a report once per hour:

1. Measure processing duration, needed CPU/RAM, and concurrent requests.
2. Estimate file storage size after 30/90/365 days.
3. Measure read/write operations and Azure Files latency if using mounts.
4. Calculate active replica time and log costs at chosen verbosity.
5. Test `minReplicas=0` where workload and trigger types allow; check cold starts and deadlines.
6. Compare Blob object storage when the app does not require filesystem semantics.

Exact prices depend on region, SKU, data volume, and billing model versions; use the Azure Pricing Calculator and real measurements rather than relying on hypothetical lesson figures.

## 28. Hands-On Exercise: API with Secrets, Shared Volume, and Logging

**Scenario:** A team deploys `orders-api` on Container Apps. The app calls a database using a secret, writes CSV files to Azure Files so two replicas share read access, and needs dashboards to investigate errors.

Requirements table:

| Component | Illustrative Value |
|---|---|
| Container Apps environment | `cae-orders-lab` |
| Container app | `orders-api` |
| Image | `example.azurecr.io/orders-api:1.0.0` |
| App-level secret | `db-password` |
| Key Vault secret | `orders-db-password` |
| Container env | `DB_PASSWORD` → `secretRef: db-password` |
| Azure Files share | `reports` |
| Environment storage mapping | `reports-storage` |
| Revision volume | `reports-volume` |
| Mount path | `/mnt/reports` |
| Replicas during test | 2 |
| Logging | Console/system logs to Log Analytics per configuration |
| Monitoring | HTTP 5xx, p95 latency, replicas, mount errors |

### Tasks

1. Diagram the **environment/app/revision/replica** boundaries, placing secrets and volumes at the right layers.
2. Describe the steps to grant managed identity permissions so the Container App reads the Key Vault secret.
3. Write the YAML excerpt for `secretRef` and `volumeMounts` matching supported schemas.
4. Contrast `DB_PASSWORD` with `reports-storage`: do they share the exact same authentication mechanism?
5. Run or describe how to **list secret names** without printing values.
6. Describe how to verify files inside `/mnt/reports` persist after one replica is replaced.
7. Test two replicas writing separate files without concurrently overwriting the same filename.
8. Format a JSON log including timestamp, revision, replica, request ID, event, duration, and error code—with zero secrets.
9. Write a Log Analytics query finding errors on the new revision after deployment.
10. Design two alerts: one for rising HTTP 5xx, one for volume write errors.
11. Write a runbook for when DB credentials rotate yet one replica keeps using the old credential.
12. Describe how to recover if someone deletes a report file, evaluating backups and retention.

### Reference Solution

**Secrets:** Key Vault holds the real value. The app's managed identity holds secret-read permission. App-level secret config references Key Vault; the revision template injects `DB_PASSWORD` from `db-password`. During rotation, verify refresh/restart mechanics and watch connection errors.

**Volumes:** the Azure Files share is declared at the environment level as `reports-storage`. The revision template defines volume `reports-volume` with `storageType: AzureFile` and mounts it at `/mnt/reports`. Azure Files mapping authentication is **not automatically** `DB_PASSWORD` or the app's Key Vault rights.

**Data:** two replicas write separate files named `report-<job-id>.csv`; verify files from another replica or after a rollout. On accidental deletion, use Azure Files snapshots/backups rather than expecting revision rollbacks to recover files.

**Observability:** the app emits JSON to stdout, the platform emits system logs, and the app/environment emit metrics. Select the deployment timeframe and revision, comparing logs against p95 latency and 5xx rates; instrument tracing if multi-step DB/queue calls need analysis.

**Acceptance:** zero secrets appear in logs or IaC output, share reads/writes work under proper permissions, files survive replica replacement, alerts detect lab faults, and a restore runbook exists.

## 29. Self-Check Questions

**Question 1.** In Container Apps, what is `secretRef` used for?

A. Create an Azure Files share.  
B. Reference an app-level secret for container use without writing the raw value into the env template.  
C. Create a new revision every time a secret is read.

**Answer: B.** Secrets are declared at app level; templates reference them by name.

**Question 2.** Does simply adding a new secret automatically create a new Container Apps revision?

**Answer:** No. Secrets are app-level configuration; the revision template is a separate configuration layer. When changing a secret, check refresh/restart mechanics so apps pick up the new value.

**Question 3.** Does an app's managed identity with Key Vault secret-read permission automatically guarantee Azure Files volume mounts work?

**Answer:** No. Azure Files environment storage mappings have separate authentication, network connectivity, and permission requirements.

**Question 4.** Why can writing files to `/app/uploads` inside a container lose data after a rollout?

**Answer:** The writable layer belongs to the container/replica lifecycle; new instances do not automatically inherit files from old instances.

**Question 5.** Is EmptyDir shared across all replicas of the same Container App?

**Answer:** No. EmptyDir is ephemeral storage scoped to a single replica; containers inside that replica can share via mounts, yet other replicas do not share the same EmptyDir.

**Question 6.** To let a container mount Azure Files, where must the storage mapping be declared?

**Answer:** At the **Container Apps environment** level; then the revision template references it via `storageName` and the container mounts it via `volumeMounts`.

**Question 7.** When two replicas mount the same Azure Files share, can you assume both can write the same JSON file concurrently without synchronization?

**Answer:** No. Applications must handle concurrency, file locks, or use per-job-ID files/databases to prevent conflicts.

**Question 8.** Is a persistent volume an automatic backup for your data?

**Answer:** No. It decouples file lifetimes from replicas; you must still configure snapshots/backups and deletion controls.

**Question 9.** How do console logs differ from system logs?

**Answer:** Console logs come primarily from container stdout/stderr; system logs primarily reflect Container Apps platform events such as revisions, probes, startup, or scaling.

**Question 10.** An app scales to zero and emits no new logs—does that prove logging is broken?

**Answer:** No. With zero running replicas or zero events/traffic, no new console logs are generated.

**Question 11.** Having logs and metrics enabled means every HTTP request automatically gets distributed traces, right?

**Answer:** No. Instrumentation and an appropriate exporter/tracing backend are typically required.

**Question 12.** Why might an example KQL query against `ContainerAppConsoleLogs_CL` fail in a different workspace?

**Answer:** Table/column names and data types can differ by logging destination and schema. Inspect actual tables present in your workspace.

**Question 13.** An older revision works while a new revision crashes immediately at startup. Which changes should you inspect?

**Answer:** Image, env `secretRef`, permissions/Key Vault references, volume mappings, `mountPath`, resource limits, probes, and per-revision system/console logs.

**Question 14.** Does rolling back a revision automatically revert files written to Azure Files?

**Answer:** No. Persistent shares live outside revisions; an independent data backup/restore plan is required.

**Question 15.** To cut logging costs, should you disable all error logs?

**Answer:** No. Reduce debug verbosity, strip unnecessary payloads, and tune sampling/retention while retaining enough data to diagnose incidents.

**Question 16.** What is a safe way to verify secret rotation?

**Answer:** Verify managed identity/permissions/networking, update references per supported mechanics, restart/roll out when needed, observe health/5xx rates, and revoke old credentials only after all consumers have transitioned.

**Summary:** Azure Container Apps manages elastic workloads cleanly when **secrets are separated from images, persistent data is separated from replicas, and telemetry is separated from local filesystems**. Design cleanly across **app → revision → replica**, selecting Key Vault/managed identity, Azure Files/Blob Storage, and Azure Monitor/Log Analytics to fit your needs. A well-operated application proves that rotating secrets causes no unnecessary outages, scaling/rollouts never lose data, and incidents always have enough logs, metrics, and traces to pinpoint root causes and recover.
