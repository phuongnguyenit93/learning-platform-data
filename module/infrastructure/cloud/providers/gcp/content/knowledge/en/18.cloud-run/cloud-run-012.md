# Secrets, Environment Variables, and Volume Mounts on Cloud Run

## Learning Objectives

After this lesson, learners can:

1. Distinguish **environment variables**, **Secret Manager references**, and **volume mounts** by sensitivity, read timing, data lifetime, and deployment behavior.
2. Configure a Cloud Run service using **gcloud** and YAML; recognize the difference between incremental updates and full configuration replacement.
3. Grant **least-privilege IAM** to the service identity to read a secret or Cloud Storage bucket without storing JSON service account keys.
4. Choose the right volume type—**secret**, **in-memory**, **ephemeral disk**, **Cloud Storage FUSE**, or **NFS/Filestore**—and understand concurrency, POSIX, networking, and persistence limits.
5. Write **Java/Spring Boot** applications that safely read environment variables, secret files, and scratch data; design rotation, rollouts, and error handling.
6. Test scenarios for missing permissions, mount failures, out-of-memory errors, stale secrets, wrong paths, and unexpected costs.

## 1. Context and Three Types of Needs

In the **CLOUD_PROVIDERS_GCP** module, learners take Java applications from projects/IAM/VPCs to Compute Engine, GKE, and **Cloud Run**, integrating storage/databases, release automation, and reliability/cost monitoring.

Suppose the **orders-api** service runs Spring Boot on Cloud Run:

- Reads **APP_ENV=production** and **LOG_LEVEL=INFO**: standard non-secret configuration.
- Reads **PAYMENT_API_KEY**: sensitive credential that must live in **Secret Manager**.
- Processes PDFs in a temporary directory: needs bounded capacity, **does not need to survive instance restarts**.
- Reads images from **Cloud Storage** or shares documents via **Filestore NFS**: requires durable storage external to Cloud Run.

Cloud Run is a container platform capable of scaling out/in and creating **revisions**. Each instance has its own lifecycle; never treat files written inside one instance as shared or durable across instances. Env/secrets/volumes configuration belongs to a **revision**; updating service config creates a **new revision**, and running instances on older revisions may still use the old config during traffic migration.

### Quick Decision Table

| Need | Preferred solution | Reason |
|---|---|---|
| Profile, non-sensitive feature flag, endpoint | **Plain environment variable** | Simple, fixed per revision |
| Password/API key version-pinned for a release | **Secret Manager → environment variable** | Fetched at instance startup, reproducible |
| Certificate, key, or secret needing reload after rotation | **Secret Manager → mounted secret file** | File read, uses `latest` version when appropriate |
| Job creating small temp files, bounded by memory | **In-memory volume** | Fast, size-limited, non-persistent |
| Large temp files without consuming all RAM | **Ephemeral disk** on gen2 | Per-instance temp disk, separate quota/cost |
| Images, documents, models in object storage | **Cloud Storage SDK** or FUSE mount when file paths are required | Data outside instance; FUSE is not full POSIX |
| Sharing an NFS directory tree across many clients | **Filestore/NFS volume** | Shared file namespace over VPC, with NFS locking limits |
| Critical transactional data | **Cloud SQL/AlloyDB/Spanner** or suitable database | Never use temp dirs or object mounts in place of a database |

## 2. Environment Variables: Per-Revision Configuration

### 2.1. Characteristics

Environment variables are injected into the container when the instance starts. Java example:

~~~java
String env = System.getenv().getOrDefault("APP_ENV", "dev");
String logLevel = System.getenv().getOrDefault("LOG_LEVEL", "INFO");
~~~

The application can read configuration without opening a separate file, however:

- Plain variables live in the **revision configuration** and are visible to anyone authorized to inspect config. **Never put plaintext secrets in `--set-env-vars` or Dockerfile `ENV`.**
- Each revision holds its own configuration snapshot; updating env vars on a service creates a new revision. Do not treat env vars as a live hot-reload mechanism inside running containers.
- **PORT** is injected by Cloud Run to specify the HTTP port the ingress container must listen on; **do not set PORT manually**. Keys starting with **X_GOOGLE_** are reserved, and variable names cannot be empty or contain **=**.
- Environment variables configured at **build** time differ from **runtime**; never bake sensitive information into image layers.

### 2.2. Basic gcloud Commands

Assume project **shop-dev-001**, region **asia-southeast1**, and service **orders-api** already exist. All names are illustrative; update commands can create new revisions and affect traffic.

~~~bash
# Read-only: verify project and configuration
gcloud config get-value project
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1

# Incremental update: preserves other existing variables
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-env-vars=APP_ENV=staging,LOG_LEVEL=INFO

# Remove only a single key
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --remove-env-vars=OLD_FEATURE_FLAG
~~~

**Choose the right flag:**

| Flag | Behavior | Warning |
|---|---|---|
| **--update-env-vars** | Adds or updates specified keys while keeping others | Good for small changes |
| **--set-env-vars** | Replaces the entire plain variable set with the provided list | Can silently drop unlisted keys |
| **--remove-env-vars** | Removes specified keys | Check if the app still references them |
| **--clear-env-vars** | Deletes all configured plain environment variables | Broad-impact operation |
| **--env-vars-file** | Loads key/value pairs from a file | Never commit files containing real secrets |

When values contain commas, special characters, or multiple lines, use **env-vars-file** or the custom delimiter syntax supported by gcloud. Never paste real tokens/keys into CLI commands because shell history, build logs, and change-review records can retain them.

### 2.3. Spring Boot and Listening Port

~~~properties
# application.properties
spring.profiles.active=${APP_ENV:dev}
logging.level.root=${LOG_LEVEL:INFO}
server.port=${PORT:8080}
~~~

In a real project, use **Spring externalized configuration**; this file holds only **references**, not secrets. Cloud Run requires the ingress container to listen on **0.0.0.0** at port **PORT**, not solely loopback.

## 3. Secret Manager: Where Sensitive Values Belong

**Secret Manager** manages secrets and **versions**, IAM, lifecycle, auditing, and rotation. On Cloud Run, there are two managed integration modes:

| Injection method | When value is fetched | When inaccessible | Rotation |
|---|---|---|---|
| **Environment variable reference** | Before the container instance starts | Instance **fails to start** if secret fetch fails | Value in running instances does not change; **pin numeric version** and roll out a new revision |
| **Secret volume mount** | When the app **reads the mounted file** | Instance may start, then **file read fails** | Mounting **latest** can observe new versions on subsequent reads; app must still reload |

Cloud Run checks access permissions to configured secrets **at deploy time**. Passing deploy-time validation does not guarantee the service identity keeps access forever: IAM can be revoked, a secret version disabled/destroyed, or the backend may error at runtime.

### 3.1. Why Not Store Secrets as Plaintext Env Vars?

Unsafe example:

~~~bash
# DO NOT RUN: plaintext secret can persist in history/revision
gcloud run services update orders-api \
  --set-env-vars=PAYMENT_API_KEY=ACTUAL_REAL_SECRET
~~~

Instead, keep secrets in Secret Manager and configure only a **reference** to the secret. Even when injected as an env var, an app might accidentally dump environment variables or leak them via heap dumps; never print secret values in logs or health endpoints.

### 3.2. IAM for the Right Identities

Distinguish clearly:

- **Deployer**: person/CI modifying Cloud Run configuration; needs deploy permissions and permission to use the service account (such as Cloud Run Developer and Service Account User within the proper scope).
- **Service identity**: the service account that the **container runs as**; needs **Secret Manager Secret Accessor** on each specific secret and read/write permissions on buckets as appropriate.
- **Secret administrator/rotator**: creates, updates versions, or manages IAM; **should not** be the runtime identity itself.

If Java calls Cloud Storage or Secret Manager APIs directly via client libraries, use **Application Default Credentials (ADC)** from the service identity—**never bundle JSON key files** or point `GOOGLE_APPLICATION_CREDENTIALS` at a long-lived key.

### 3.3. Regional and Scope Limitations

Cloud Run services documentation currently notes **regional Secret Manager secrets are not supported** in the built-in integration; use **secrets supported via the standard resource path**. For a secret in another project, reference **projects/PROJECT_NUMBER/secrets/SECRET_NAME** and grant IAM on the secret in the source project. Do not confuse **project number** with **project ID**, and do not assume any Secret Manager replication policy automatically satisfies all data residency rules.

## 4. Practice A — Secret Manager → Cloud Run Env and File

### 4.1. Lab Context

| Property | Example |
|---|---|
| Project | **shop-dev-001** |
| Cloud Run region | **asia-southeast1** |
| Service | **orders-api** |
| Runtime service account | **orders-runtime@shop-dev-001.iam.gserviceaccount.com** |
| Secret | **orders-db-password** |
| Image | **asia-southeast1-docker.pkg.dev/shop-dev-001/apps/orders-api:1.0.0** |

These resources are examples and must exist beforehand if not already created. Provisioning real resources incurs charges. Work only in a lab project and never copy real password values into chat, Git, terminal output, or source code.

### 4.2. Create a Secret and a Safe Lab Version

~~~bash
# Modifies project; requires appropriate permissions and billing.
gcloud services enable secretmanager.googleapis.com \
  --project=shop-dev-001

gcloud secrets create orders-db-password \
  --project=shop-dev-001 \
  --replication-policy=automatic

# Use a dummy placeholder file (no real password) created safely.
gcloud secrets versions add orders-db-password \
  --project=shop-dev-001 \
  --data-file=./lab-placeholder-secret.txt

# Inspect metadata; DO NOT print payload
gcloud secrets versions list orders-db-password \
  --project=shop-dev-001
~~~

**lab-placeholder-secret.txt** is test data prepared by the learner, not a file committed inside the lesson repository. In production, secrets are ingested via controlled channels, temporary plaintext files follow security policy, and none are committed to VCS.

### 4.3. Grant Read Access to One Secret for Runtime

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Inspect policy (without viewing secret value)
gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001
~~~

Never grant **roles/secretmanager.admin** project-wide to an application that only needs to read a single secret. If deployment reports missing permissions, inspect the **exact configured service identity** rather than switching to an overly privileged identity.

### 4.4. Inject Secret via Environment Variable

~~~bash
# Service and runtime SA must already exist. VERSION=1 is illustrative.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-secrets=DB_PASSWORD=orders-db-password:1
~~~

Java reads it with **System.getenv("DB_PASSWORD")**, but must never log the value. **Numeric versions** keep revisions deterministic; when secret version 2 is added, instances on the old revision continue using their assigned version. Referencing **latest** as an env var can cause instances starting at different times to pick up different versions, so Google recommends pinning versions.

### 4.5. Mount Secret as a File

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-secrets=/etc/secrets/db/password=orders-db-password:latest
~~~

The command specifies an **absolute file path** on the left; **/etc/secrets/db/** is the mount directory and **password** is the generated file. When the secret rotates and `latest` is referenced, subsequent file reads can retrieve the new version; **Java must still actively re-read the file and refresh connection pools**.

Never mount onto a path holding critical application files: mounts **shadow existing files in the target directory**. Cloud Run forbids mounting onto **/dev, /proc, /sys**, and their subdirectories, or mounting multiple secret volumes to the same path.

### 4.6. Verify Configuration Without Exposing Secrets

~~~bash
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --format export

gcloud run revisions list \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --service=orders-api
~~~

Inspect **secret names, versions, mount paths, and service identity**; avoid commands printing full env payloads. The app may log *whether the secret file exists/is readable* or an approved version indicator, **never the password itself**.

**Edit warning:** **--update-secrets** adds/updates the named references while keeping others; **--set-secrets** replaces the entire secrets configuration and can accidentally remove other secrets. When deploying full YAML via replace, review diffs carefully because multiple revision settings can be overwritten at once.

## 5. Rotation and Revision Changes

A successful rotation follows: **create new credential in target system → add new Secret Manager version → switch app to new version → verify → revoke old credential**. Adding a version in Secret Manager **does not** automatically change a database password or partner API key.

~~~mermaid
flowchart LR
    A["Create new credential"] --> B["Add Secret Manager version 2"]
    B --> C{"How does app read secret?"}
    C -->|Env| D["Create new revision pinning version 2"]
    C -->|Mounted file latest| E["App re-reads file + refreshes clients"]
    D --> F["Canary / smoke test"]
    E --> F
    F --> G["Shift traffic, measure SLOs"]
    G --> H["Revoke old credential"]
~~~

**With env references:** roll out a new revision, optionally canary/split traffic, and watch startup errors; running instances' env vars do not change in place. **With mounted files:** when using `latest`, reading the file can pick up the new version, yet the app must reload; once the old password becomes invalid, any connection pool caching the old credential will fail.

**Risks to manage:**

- If Secret Manager becomes unreachable, env secrets can block **cold starts**, whereas mounted files can fail at **read time**. Design appropriate retries/backoff, timeouts, and SLOs.
- If a volume mount pins a **specific version** instead of `latest`, adding a new secret version **does not automatically switch** the file.
- Plan **disable/destroy** rules for old versions and rollback safety; never destroy the sole version still used by a serving revision.
- If a sensitive credential leaks, **revoking it at the target service** matters more than merely disabling the Secret Manager version.
- Older revisions may still serve traffic, especially during canaries; never revoke the old credential until confirming every serving revision has migrated.

## 6. Cloud Run Volume Types and Lifecycles

Cloud Run lets you mount storage at paths so apps read/write them like files, yet semantics vary sharply by type:

| Type | Where does data live? | Persistence | Core limitations |
|---|---|---|---|
| **Secret volume** | Secret Manager | Secret lives outside the instance; mount is a read interface | IAM, versioning, refresh, and runtime read errors |
| **In-memory volume** | RAM of containers inside the same instance | Lost when instance stops | Writes count against container memory limit; OOM risk |
| **Ephemeral disk** (gen2) | Per-instance temporary disk | Lost when instance stops | Separate quota/capacity/cost; not shared across instances |
| **Cloud Storage volume** | Cloud Storage via **Cloud Storage FUSE** | Durable objects per bucket config | Not full POSIX, no file locking, network/API latency |
| **NFS volume** | External NFS server / Filestore | Governed by storage backend | VPC networking, no-lock mode, NAS latency/cost |

Volume mounts are scoped to **a single Cloud Run instance**. If a revision scales from 1 to 10 instances, **each instance gets its own private temp RAM/disk**. Multiple containers (sidecars) **within the same instance** can share a mounted volume if both mount it; it is not shared storage across instances.

## 7. In-Memory Volumes: Scratch Data That Needs Bounds

In-memory volumes suit small transformations, temporary scratch files, and sharing data between sidecars inside the same instance. Example mounting **/mnt/work**:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/work,type=in-memory,size-limit=256Mi
~~~

Notes:

- **256Mi is a cap**, not an extra 256 MiB of RAM granted by Cloud Run. Bytes written count against the **writing container's memory limit**.
- If the volume fills up, writes fail; if the container hits its memory limit first, the instance can crash/OOM.
- If no limit is specified, the automatic default can be **half of total container memory**, still leaving risk that one container exceeds its own memory limit.
- Files vanish when the instance stops, scales in, or shifts revisions. Never store the sole copy of important data here.

Cloud Run service YAML (template excerpt only; do not run as a full service replacement):

~~~yaml
spec:
  template:
    spec:
      containers:
      - image: IMAGE_URL
        volumeMounts:
        - name: scratch
          mountPath: /mnt/work
      volumes:
      - name: scratch
        emptyDir:
          medium: Memory
          sizeLimit: 256Mi
~~~

## 8. Ephemeral Disk: Temp Files Larger Than RAM

Cloud Run supports **ephemeral disks** in the **second-generation (gen2)** execution environment. The disk is provisioned, formatted **ext4**, and encrypted per instance; data is **permanently lost when the instance stops**, including crashes, scale-ins, or traffic shifts to another revision.

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --execution-environment=gen2 \
  --add-volume=name=processing-disk,type=ephemeral-disk,size=10Gi \
  --add-volume-mount=volume=processing-disk,mount-path=/mnt/processing
~~~

**Limits per current documentation:** each disk ranges from **1Gi to 100Gi**; instances default to a **10 GiB** total cap (larger sizes require quota requests); there are caps on volume counts and a **regional project quota** across concurrent instances. Verify availability, quotas, and pricing in your actual project/region.

This option fits processing PDFs, videos, or intermediate files larger than available RAM, yet **never** treat it like a Compute Engine persistent disk. When outputs must be kept, **stream/upload incrementally to Cloud Storage** during processing rather than waiting for `SIGTERM` (cleanup time before `SIGKILL` is very short).

Corresponding YAML:

~~~yaml
spec:
  template:
    spec:
      containers:
      - image: IMAGE_URL
        volumeMounts:
        - name: processing-disk
          mountPath: /mnt/processing
      volumes:
      - name: processing-disk
        emptyDir:
          medium: Disk
          sizeLimit: 10Gi
~~~

Before applying full YAML via **gcloud run services replace**, export the live config, preserve required identity/network/secrets/traffic fields, and review the diff. After UI edits, verify **medium: Disk** was not accidentally switched to **Memory**, which can trigger OOMs.

## 9. Cloud Storage Volume: Object Storage Exposed as File Paths

**Cloud Storage FUSE** mounts a bucket like a directory inside the container. Actual data remains in **Cloud Storage**; mounting does not turn object storage into a block disk or POSIX NFS.

### 9.1. Least-Privilege Permissions and Read-Only Mount

Suppose bucket **shop-product-images-UNIQUE** exists, holding pipeline-published images. Cloud Run runtime only needs read access:

~~~bash
# Modifies IAM on existing bucket; authorized lab only.
gcloud storage buckets add-iam-policy-binding \
  gs://shop-product-images-UNIQUE \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Mount onto existing service. Mount requires Cloud Run gen2.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --execution-environment=gen2 \
  --add-volume=mount-path=/mnt/products,type=cloud-storage,bucket=shop-product-images-UNIQUE,readonly=true
~~~

The app reads **/mnt/products/images/sku-1001.jpg** via standard filesystem APIs. The bucket must exist and the service identity must hold matching permissions. For workflows creating/updating objects, grant exact roles (Object Creator/User as appropriate), never project-wide Storage Admin.

### 9.2. Limitations to Plan For

- Cloud Storage FUSE is **not fully POSIX-compliant**; there is no **file locking** preventing multiple writers from overwriting the same object. Concurrent writes to the same name cause **last-write-wins** and lost updates.
- Reading/listing many small files incurs API/network latency unlike local disk. **Metadata cache TTL** and mount options affect performance and listing freshness.
- On writes, Cloud Storage FUSE uses memory for caches/buffers and streaming write paths per config; **benchmark real memory/throughput** with large files. Object commits depend on write/close lifecycle—do not assume bytes just written are immediately visible via the object API.
- Mounting happens **before container startup**; if Cloud Storage is unreachable or mounting exceeds its timeout, the instance fails to start. Documentation notes roughly **30 seconds** max for mounting.
- Mounted buckets still incur **Cloud Storage operations, storage, retrieval/egress** charges per billing rules. Check bucket location, IAM, lifecycle, and data residency.

**Never use GCS FUSE for a PostgreSQL/MySQL data directory**, even though the app can open paths and issue File I/O. If a Java app handles objects independently without needing POSIX paths, the **Google Cloud Storage Java SDK** is usually simpler with clearer semantics.

### 9.3. Mounting Only a Prefix and Cache Options

For large buckets, use the **only-dir** mount option to scope the visible directory subtree:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/products,type=cloud-storage,bucket=shop-product-images-UNIQUE,readonly=true,mount-options="only-dir=images"
~~~

**Caution:** mounting a single prefix **does not restrict IAM**. If the service account holds Object Viewer on the entire bucket, it can still access other objects via the SDK/API. To isolate sensitive data, enforce permissions at the bucket/managed-folder level or use proper boundaries.

## 10. NFS/Filestore Volume: Sharing Directories Over VPC

When multiple containers or instances need a **shared directory tree**, NFS fits better than in-memory or ephemeral disks. On Google Cloud, **Filestore** provides managed NFS servers; Cloud Run can also mount other reachable NFS servers.

### 10.1. Prerequisites

1. NFS server/Filestore instance is running with a known **IP and export path**.
2. The Cloud Run service connects to a **VPC** that routes to the server; use **Direct VPC egress** (preferred for performance) or Serverless VPC Access depending on environment.
3. Firewalls, NFS export permissions, client UID/GID, and network policies align. Never expose NFS to the public Internet.
4. Configure Cloud Run **gen2** where required by the mount feature, and verify network/latency in testing.

### 10.2. Example Share Mount

Suppose an NFS server at IP **10.20.10.5** exports **/shared**, and VPC connectivity is already configured:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/shared,type=nfs,location=10.20.10.5:/shared,readonly=true
~~~

This IP is a **hypothetical example**, not a real server. Without a valid VPC route, mounting can time out or fail startup even though the Cloud Run update command succeeds.

### 10.3. NFS Limitations on Cloud Run

- **Cloud Run does not support NFS file locking**; volumes mount in **no-lock** mode. Never run apps relying on NFS locks to prevent concurrent writers.
- NFS shared storage **does not replace database transactions** and does not prevent two workers from overwriting the same file. Use unique filenames, external coordination, or a concurrency-safe backend.
- NFS latency depends on networking, Filestore tier, client connections, I/O sizes, and Cloud Run instance count; benchmark it.
- Filestore bills by provisioned capacity/tier plus potential network/backup fees, unlike a local scratch directory.
- If the NFS backend becomes unreachable, workloads can **hang or fail I/O**; design timeouts, health endpoints, and graceful degradation.

**Do not confuse VPC connectivity with IAM:** the Cloud Run deployer needs config permissions to deploy, whereas NFS file operations are governed by **network reachability, export rules, and POSIX filesystem permissions**—not per-request Cloud Storage IAM.

## 11. Java Example: Safely Reading Config, Secrets, and Scratch Data

The snippet below demonstrates how an app **avoids printing secrets to stdout**, validates a mounted secret file, writes temporary scratch data, and stores final outputs elsewhere.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class CloudRunConfiguration {
    private static final Path SECRET_PATH =
        Path.of("/etc/secrets/db/password");
    private static final Path SCRATCH_DIR =
        Path.of("/mnt/work");

    private CloudRunConfiguration() {}

    public static String profile() {
        return System.getenv().getOrDefault("APP_ENV", "dev");
    }

    // For secret volumes; re-read only when the app intentionally refreshes.
    public static String readDbPassword() throws IOException {
        return Files.readString(SECRET_PATH, StandardCharsets.UTF_8);
    }

    public static Path createTempReport(byte[] contents) throws IOException {
        Objects.requireNonNull(contents, "contents");
        Files.createDirectories(SCRATCH_DIR);
        Path report = Files.createTempFile(SCRATCH_DIR, "orders-", ".csv");
        Files.write(report, contents);
        return report;
    }

    public static void main(String[] args) throws Exception {
        String env = profile();
        String password = readDbPassword();
        if (password.isEmpty()) {
            throw new IllegalStateException("Required DB secret is empty");
        }
        // Log status only; never log the password.
        System.out.println("Config ready for " + env);
    }
}
~~~

**Technical notes:**

- Never blindly call **`trim()`** on passwords/tokens: leading or trailing whitespace can be valid characters. Preserve exact bytes, never log plaintext, and handle character encoding per the target system's contract.
- **Java `String`s** live on the heap and are not guaranteed to be zeroed promptly; minimize retention and never embed them in logs or exception messages.
- **`Files.createTempFile`** generates unique filenames, preventing collisions across concurrent requests inside the same instance. Still clean up per request/job and monitor capacity limits.
- Important outputs must be uploaded to **Cloud Storage or a database** via appropriate SDKs/APIs; never expect **/mnt/work** to survive scale-in.
- If using **env secrets**, Java calls **`System.getenv("DB_PASSWORD")`** instead of reading a file; avoid mixing both without a clear reason.

### Rotation with a Java Connection Pool

When using HikariCP and a `latest` mounted secret file, the file changing on disk **does not automatically update the connection pool**. The application must implement one of two workflows:

1. **Pin secret versions in env vars**, roll out a new revision referencing the new version, verify health, and shift traffic.
2. **Re-read the file** in a controlled refresh loop, update connection credentials/reconfigure the pool, and drain old sessions. Test credential overlap windows with the database or partner.

For databases supporting **IAM authentication** (such as certain Cloud SQL setups), consider using it to reduce static passwords. However, Cloud Run's IAM **does not automatically turn every JDBC connection into an authenticated one**; you must still configure the matching database connector/auth mechanism.

## 12. Cloud Run Services, Jobs, and Multi-Container Instances

### 12.1. Services vs. Jobs

- A **Cloud Run service** receives HTTP requests, runs instances/revisions, and supports traffic splitting.
- A **Cloud Run job** runs tasks to completion, does not serve HTTP traffic, and does not use revision traffic splitting like a service.
- Both can use env vars, Secret Manager, and supported volume types, yet **`gcloud run services`** and **`gcloud run jobs`** are **two separate command groups**.

Example creating a job reading a secret via env var:

~~~bash
gcloud run jobs create nightly-report \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/shop-dev-001/jobs/report:1.0.0 \
  --service-account=orders-runtime@shop-dev-001.iam.gserviceaccount.com \
  --set-secrets=DB_PASSWORD=orders-db-password:1
~~~

Trigger jobs via explicit execution, schedules, or workflows and grant callers job execution permissions; never assume creating a job immediately runs or schedules it.

### 12.2. Sidecars Share Volumes Within an Instance, Never Across Instances

~~~mermaid
flowchart TB
    LB["Cloud Run routing"] --> A["Instance A"]
    LB --> B["Instance B"]
    subgraph A1["Instance A: 2 containers"]
      APP1["Java API"] --> MEM1["in-memory volume A"]
      SC1["Sidecar"] --> MEM1
    end
    subgraph B1["Instance B: 2 containers"]
      APP2["Java API"] --> MEM2["in-memory volume B"]
      SC2["Sidecar"] --> MEM2
    end
    A --> A1
    B --> B1
    APP1 --> GCS["Cloud Storage / Filestore if shared state needed"]
    APP2 --> GCS
~~~

When defining a volume shared between **two containers in the same instance**, declare the volume **once** and mount it inside each container. Within each Cloud Run instance, account for resource limits (memory/disk/CPU) both per container and in aggregate.

## 13. Security, Reliability, and Total Cost

### 13.1. Layered Security

| Layer | Controls required |
|---|---|
| **Source/image** | No secrets in Dockerfile ARG/ENV, source, or build logs; scan images |
| **Deployer** | Properly scoped Cloud Run Developer and Service Account User; control who can edit revisions |
| **Runtime identity** | Dedicated service account for orders-api; Secret Accessor on one secret, Object Viewer on read bucket |
| **Secret versions** | Version pinning for env vars, rotation/revocation, zero plaintext in logs |
| **Volumes** | Mount only what the container needs; read-only where writes are unnecessary |
| **Network** | VPC routes/firewalls for NFS; HTTPS/TLS for external APIs; no public file shares |
| **Observability** | Audit IAM/config changes, startup/OOM/I/O metrics, and redacted logs |

### 13.2. Performance and Cost

| Choice | What to observe | Cost risks |
|---|---|---|
| **Plain env** | Revision rollouts, config drift | Negligible compute cost, though misconfiguration causes downtime |
| **Secret Manager** | Version access errors, API latency, rotation | Active versions, access operations, optional logging/KMS |
| **In-memory** | Memory usage, OOMs, concurrent requests | Must provision sufficient memory |
| **Ephemeral disk** | GiB/instance, concurrent instances, throughput | Provisioned disk, regional quota, and instance duration |
| **Cloud Storage FUSE** | p95/p99 latency, operations, caching, egress | Object requests, storage, network, and memory |
| **NFS/Filestore** | NFS latency, availability, VPC errors | Provisioned share capacity, networking, backups |

**Increasing Cloud Run concurrency** can save instances while causing multiple concurrent requests to share RAM, temp disk, or object mounts; benchmark memory, p95 latency, and Java thread-safety. Allocating 1Gi temp disk per instance across **100 instances** incurs vastly different quota and cost than 1Gi for the whole service.

## 14. Systematic Troubleshooting

| Symptom | Common cause | Check first |
|---|---|---|
| Revision fails startup, missing secret env | Secret version missing/disabled or runtime SA lacks permission | Secret Manager version, **secretAccessor**, Cloud Run revision logs |
| Secret reference deploy returns 403 | Deployer or **runtime identity** lacks permission | Configured service account, secret IAM policy |
| App starts, then reading secret file fails | IAM revoked, version disabled, or wrong path | Mounted path, runtime access, Secret Manager audit logs |
| Secret rotated yet env unchanged | Env resolved at **instance startup**, never updated in-place | Deploy new revision pinning new version; check traffic split |
| Mounted secret file changed yet JDBC still fails | Java did not reload connection pool | App credential lifecycle and database auth |
| Files in `/etc/secrets` disappear after mount | Mount **shadows an existing directory** | Choose a dedicated mount path |
| Cloud Run fails startup on GCS mount | FUSE cannot reach bucket / mount timeout / IAM | Bucket, gen2 execution env, service identity, startup logs |
| GCS FUSE writes slow or unexpectedly overwritten | Object APIs lack file locks and differ from POSIX writes | Use SDK, unique object names, generation preconditions |
| In-memory volume full | `size-limit` or container memory too low | Cloud Monitoring memory, quotas, scratch usage |
| Ephemeral disk hits quota | Regional allocation or per-instance disk quota | Disk GiB × max instances, quotas, gen2 |
| Temp directory vanishes | Instance stopped/scaled in | Important data must persist outside instances |
| NFS mount times out | Cloud Run not attached to right VPC, or wrong route/firewall/export | Direct VPC/connector, IP, NFS server, firewall |
| NFS file writes collide | NFS mounts without locking on Cloud Run | Use unique filenames or external coordination |
| Cloud Run receives new env yet clients see old behavior | Old revision still serves traffic or app caches values | Revisions and traffic percentages |
| ImagePull/auth error | Artifact Registry image URL or deploy/pull identity | Runtime error details, Artifact Registry IAM, digest |

**Quick triage runbook:**

1. Confirm **project, region, service/job, revision, and service identity**.
2. Separate **deploy**, **cold start**, **runtime read**, **network mount**, and **application logic** failures.
3. For secret errors: verify **secret resource/version, Secret Accessor on the exact principal, mount path, and IAM policy** without printing payloads.
4. For volume errors: verify **type, gen2, mount path, size limit, bucket IAM, and VPC routes/NFS export**.
5. If failures appear only after rotation: check **revisions still serving traffic**, pinned env vars, file reload logic, and whether the target system rotated credentials.
6. Roll back to a known-good revision if needed, document root cause, and update tests/alerts. **Never disable security by granting Owner to runtime.**

## 15. End-to-End Scenario: Orders and Reporting

A Java system comprises three workloads:

~~~mermaid
flowchart LR
    CUSTOMER["Client"] --> API["Cloud Run orders-api"]
    API --> SM["Secret Manager<br/>payment credential"]
    API --> DB["Cloud SQL"]
    API --> BUCKET["Cloud Storage<br/>product assets"]
    API --> TMP["In-memory scratch<br/>per instance"]
    JOB["Cloud Run nightly-report job"] --> DISK["Ephemeral disk<br/>temporary output"]
    JOB --> BUCKET
    LEGACY["Legacy document service"] --> NFS["Filestore NFS<br/>shared files"]
~~~

| Workload | Config/secret | Volume | Reliability measures |
|---|---|---|---|
| **orders-api** | Plain `APP_ENV`; payment API token from Secret Manager, pinned version | Small in-memory scratch; SDK reads bucket | Canary revisions, verify secret IAM and p99 latency |
| **nightly-report job** | Plain API config; credentials via service identity | 10Gi ephemeral disk; exports CSV to Cloud Storage | Incremental checkpoints; never wait until shutdown to upload |
| **legacy-documents** | Credentials via Secret Manager mounted file | Filestore NFS or object storage matching semantics | NFS no-lock; avoid concurrent writes to the same file |

**Architectural takeaway:** Never store the sole copy of documents, sessions, or payment state in `/tmp`, in-memory volumes, or ephemeral disks. Data that must survive scaling and revisions belongs in **databases, Cloud Storage, Filestore, or another durable backend**.

### Minimum Acceptance Test Matrix

| Test | Expected result |
|---|---|
| New revision pins secret version 2 | New instances read exact configured version |
| Old revision still serving traffic | Uses old version and keeps working while old credential remains valid |
| Runtime SA missing `secretAccessor` | Test catches deploy/start/read error depending on mode |
| Anonymous principal tries to read API secret | Denied Secret Manager access |
| In-memory reaches `size-limit` | App handles write error cleanly without silently dropping orders |
| Ephemeral disk wiped after scale-in | Final outputs already uploaded durably |
| Object mount with multiple writers | Uses unique object names / generation preconditions |
| NFS unavailable | App does not hang indefinitely; triggers timeout/retry/alert per design |
| Using Cloud Run gen1 with gen2-only disk | Config rejected as invalid; caught in testing |

## 16. Hands-On Exercises and Answers

### Exercise A — Choosing Environment Variables vs. Secrets

**Task:** Classify `APP_ENV`, `LOG_LEVEL`, `PAYMENT_API_KEY`, `DB_PASSWORD`, and `PUBLIC_ENDPOINT`.

**Answer:** `APP_ENV`, `LOG_LEVEL`, and `PUBLIC_ENDPOINT` are plain env vars; `PAYMENT_API_KEY` and `DB_PASSWORD` belong in Secret Manager. For **reproducible releases**, pin secret versions as env vars; if the app supports reloading files dynamically, consider mounted `latest`.

### Exercise B — Debugging Secret Rotation

A service runs revision R1 with **`DB_PASSWORD=orders-db-password:1`**. Secret version 2 is created and version 1 is disabled immediately, without deploying a new revision.

**Question:** What happens? **Answer:** R1 still references version 1; running instances keep the old env var, while cold starts/restarts fail because version 1 is disabled. You must deploy revision R2 pinning version 2, shift traffic, and verify before disabling version 1.

### Exercise C — Understanding File Sharing

A service runs **3 Cloud Run instances**, each configured with a **256Mi** in-memory volume. Two containers inside instance A mount the same volume.

**Question:** How many volumes exist? Can containers in instance B see instance A's files? **Answer:** There is **one scratch volume per instance**, so three independent volumes; sidecars inside A share volume A, while B cannot see A's files. Use a durable external backend for shared state.

### Exercise D — Choosing NFS vs. GCS Mount

Two workers must write to the same file and rely on **file locking** to guarantee ordering. The team plans to use NFS on Cloud Run or GCS FUSE.

**Question:** Is this safe? **Answer:** Not by default. Cloud Run NFS mounts in **no-lock** mode, and GCS FUSE lacks file locking; redesign write coordination using unique filenames, queue/database coordination, or a runtime/storage layer supporting those semantics.

### Exercise E — Designing 20Gi Scratch Space

A video processing job needs 20Gi of regenerable scratch space, while containers only provision 2Gi memory. Choose the volume type and explain.

**Answer:** Consider **ephemeral disk** on gen2, but check the default **10Gi per-instance limit** and regional quota and request an increase before configuring 20Gi. Never choose a 20Gi in-memory volume without sufficient RAM; upload outputs to Cloud Storage before the task exits.

### Exercise F — Auditing IAM

`orders-runtime` is granted **`roles/secretmanager.secretAccessor` at the project level** and **`roles/storage.admin` across the whole project**, even though the app reads only one secret and one bucket.

**Task:** Narrow permissions. **Answer:** Scope `secretAccessor` down to the **specific secret**, and Object Viewer down to the **read bucket**; audit inherited roles and organization policies, and never use static service account keys.

### Exercise G — Lab Runbook with gcloud

Prepare a runbook (no need to execute against production):

1. Create a Secret Manager secret and a non-sensitive test version.
2. Grant `secretAccessor` to the runtime service account.
3. Deploy a Cloud Run revision using **`--update-secrets`** with a version-pinned env var.
4. Deploy another revision using a **`latest`** secret file mount.
5. Attach a 128Mi in-memory volume and observe temp files vanishing when instances recycle.
6. Mount a Cloud Storage bucket **read-only** and verify IAM.
7. Monitor 403s, startup failures, memory, and logs; execute a rollback.

**Pass criteria:** never print or commit secrets, avoid `--set-secrets` accidentally dropping other references, record revision names and traffic state, and test unauthorized identities.

## 17. Summary and References

**Six core principles:**

1. **Env vars** suit non-secret configuration tied to a revision; **PORT** is provided by Cloud Run—do not set it manually.
2. **Secret Manager** stores secrets. Env secrets resolve at instance startup; mounted secrets read on file access. Rotation must account for apps, target systems, and older serving revisions.
3. **Runtime service identity** needs least-privilege IAM on secrets/buckets; deployer, rotator, and runtime are distinct roles.
4. **In-memory and ephemeral disks** live strictly within a single instance; never use them as durable storage.
5. **Cloud Storage FUSE** exposes object storage as file paths without **full POSIX semantics**; **NFS/Filestore** offers shared files, yet Cloud Run NFS **does not support locking**.
6. Always verify **gen2, IAM, VPC, quotas, concurrency, revision traffic, startup/latency, and cost** before production rollout.

**Official Google Cloud documentation:**

1. [Configure environment variables for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables) — env flags, reserved variables, revision behavior.
2. [Configure secrets for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — Secret Manager env/volume, permissions, rotation, and limits.
3. [Configure secrets for Cloud Run jobs](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets) — secret configuration for jobs.
4. [Configure in-memory volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/in-memory-volume-mounts) — memory limits and sharing across containers.
5. [Configure an ephemeral disk for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/ephemeral-disk) — gen2, disk quotas, temporary storage.
6. [Configure Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts) — FUSE, concurrency, IAM, performance, and mount options.
7. [Configure NFS volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/nfs-volume-mounts) — Filestore/VPC/no-lock.
8. [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity) — ADC, IAM, and runtime service accounts.
9. [Secret Manager best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices) — version pinning, rotation, and data protection.
10. [Cloud Storage FUSE overview](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview) — object vs. filesystem semantics.
