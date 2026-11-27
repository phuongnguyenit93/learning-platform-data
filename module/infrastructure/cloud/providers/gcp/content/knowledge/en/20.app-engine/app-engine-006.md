# Data connectivity and using service accounts in App Engine

A Java application deployed on **App Engine** needs to read images from Cloud Storage, query orders in Firestore or Cloud SQL, and fetch passwords from Secret Manager. Putting JSON credentials inside source code creates severe key-exposure risk; granting **Editor** to the entire application lets a single security flaw impact far more resources than necessary. A better approach is using a **service account bound to the App Engine version**, Google Cloud client libraries with **Application Default Credentials (ADC)**, and **least-privilege** IAM.

This lesson belongs to the **App Engine** chapter of the **CLOUD_PROVIDERS_GCP** module: from projects/IAM/VPC to application services, storage, databases, release automation, and reliability/cost monitoring. The focus is **secure data connectivity from Java on App Engine**, not a full tutorial on writing web applications.

After this lesson, you will be able to:

- Distinguish the **app-level default service account**, **per-version service account**, deployer account, and service agents.
- Use **ADC** instead of JSON private keys so Java apps can call Cloud Storage, Firestore, Secret Manager, and Cloud SQL.
- Grant IAM roles at the right **bucket, secret, database/project, and Cloud SQL instance** scope as needed.
- Distinguish IAM permissions from database user permissions, alongside network paths to private-IP resources.
- Choose **Direct VPC egress** or a **Serverless VPC Access connector** for App Engine Standard; understand differences from Flexible.
- Deploy a version with `app.yaml` and verify its effective service account.
- Diagnose `403` errors, Cloud SQL timeouts, oversized pools, project misconfigurations, and unexpected costs.

> **Lab scope:** project names, buckets, secrets, Cloud SQL instances, and service accounts are placeholders. IAM and deploy commands apply only to authorized projects; never run them in production without verifying owners, existing permissions, and costs.

## 1. App Engine data connectivity architecture

~~~mermaid
flowchart TD
  A["HTTPS client"] --> B["App Engine service: orders-api"]
  B --> C["Java-running version"]
  C --> D["ADC: version's service account identity"]
  D --> E["Cloud Storage API: images/documents"]
  D --> F["Firestore API: documents"]
  D --> G["Secret Manager API: secret version"]
  D --> H["Cloud SQL Java Connector / IAM"]
  H --> I["Cloud SQL: MySQL/PostgreSQL"]
  J["VPC egress / firewall / DNS"] --> H
  K["Cloud IAM roles on target resources"] --> E
  K --> F
  K --> G
  K --> H
~~~

An application simultaneously needs:

1. **Identity**: which service account is running the version?
2. **Permissions**: does that service account have permissions on the resource in the right project?
3. **Network path**: are API endpoints or private IPs reachable through the network/VPC?
4. **Application-level data authorization**: are the Cloud SQL DB user, Firestore security logic, IAM Conditions, encryption, and business rules properly configured?

**Having IAM does not automatically provide network reachability.** For example, the Cloud SQL connector can authenticate identity yet still fail to reach a private IP if the VPC path is missing. Conversely, TCP 3306 reachability does not replace database authentication.

### Choosing where to store data

| Need | Service | Connection method | Things to note |
|---|---|---|---|
| Images/PDFs, uploads, backups | **Cloud Storage** | Google Cloud Storage Java client | Bucket IAM, object lifecycle, avoid writing persistent files to local disk |
| NoSQL documents and document queries | **Firestore Native mode** | Firestore Java server client | Indexes, read/write costs, IAM permissions, and app-level authorization |
| Legacy systems using Datastore API | **Firestore in Datastore mode** | Cloud Datastore client | Different API and query model from Firestore Native |
| Transactional SQL, joins | **Cloud SQL** | JDBC + Cloud SQL Java Connector, pooling | DB authentication, networking, connection limits, HA/backups |
| Passwords and API keys | **Secret Manager** | Secret Manager API/Java client | Secret-level IAM and caching/rotation |
| Shared cache | **Memorystore** | Redis client over private IP | VPC egress, TTLs, never use as sole source of truth |

The local filesystem on App Engine is not durable business storage shared across all instances/versions. Large uploaded files or state that must survive deployments and scale-outs belong in Cloud Storage or an appropriate database.

## 2. Three identity layers: deployer, runtime, and service agent

App Engine has **one default application identity** and can have a **dedicated identity per version**:

| Identity | Example | Role |
|---|---|---|
| **App-level default service account** | `PROJECT_ID@appspot.gserviceaccount.com` or custom service account | Default runtime identity when a version does not specify one |
| **Per-version service account** | `orders-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime identity of **new versions** when specified at deploy time |
| **Deployer/CI/CD identity** | `ci-deploy@PROJECT_ID.iam.gserviceaccount.com` | Builds/deploys code; needs `iam.serviceAccounts.actAs` on the runtime SA |
| **Service agents** | Google-managed per-API identities | Execute infrastructure/build/deploy tasks; not Java code's runtime identity |

**Key conditions:**

- A per-version service account must **already exist** and belong to the **same project** as the App Engine application.
- It can be specified via `app.yaml: service_account` or `gcloud app deploy --service-account`; if both are provided, **the CLI flag takes precedence**.
- Updating the app-level default with `gcloud app update --service-account` affects only **versions deployed after the change**. Already running versions keep their old service account until redeployed.
- The runtime service account is **separate** from the deployer's account. Granting the deployer Storage Admin does not grant Java code bucket read access; granting the runtime Object Viewer does not let it deploy.

App Engine may create `PROJECT_ID@appspot.gserviceaccount.com` by default; **do not assume this account always has Editor**. In newer organizations or with the `iam.automaticIamGrantsForDefaultServiceAccounts` organization policy, automatic Editor grants may be blocked. If an older project still has Editor on the default account, narrow it using Policy Simulator and controlled change management.

### Permission map for two versions

~~~text
App Engine app (project shop-prod)
  ├── Default SA: shop-prod@appspot.gserviceaccount.com
  ├── Service: orders
  │     ├── Version v1 → default SA (deployed earlier)
  │     └── Version v2 → orders-runtime@shop-prod.iam.gserviceaccount.com
  └── Service: report
        └── Version v1 → report-runtime@shop-prod.iam.gserviceaccount.com
~~~

If traffic is still split 50/50 between orders v1 and v2, requests **may execute under two different IAM identities**. Always verify which versions actually receive traffic before changing permissions rather than looking only at the service name.

## 3. Setting up a service account and least-privilege IAM

Assume the App Engine project is `shop-lab` and the Cloud Storage bucket holding images is `shop-images-lab-unique`. Create a **dedicated service account for Java orders**:

~~~bash
APP_PROJECT="shop-lab"
APP_SA_NAME="orders-runtime"
APP_SA="$APP_SA_NAME@$APP_PROJECT.iam.gserviceaccount.com"
BUCKET="shop-images-lab-unique"

gcloud config set project "$APP_PROJECT"
gcloud iam service-accounts create "$APP_SA_NAME" \
  --display-name="App Engine orders runtime"

# Allow the runtime only to read objects in a single bucket.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$APP_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

The `roles/storage.objectViewer` role covers reading/listing objects; if the app needs uploads, grant `storage.objects.create` or a suitably narrow role. **Never grant `roles/storage.admin` just to read files.** On buckets with uniform bucket-level access enabled, bucket/managed-folder IAM replaces object ACLs.

### Granting permissions by operation

| Operation | Reference IAM role | Recommended scope |
|---|---|---|
| Read Cloud Storage objects | `roles/storage.objectViewer` | Specific bucket to read |
| Create new objects without deleting old ones | `roles/storage.objectCreator` | Specific upload bucket |
| Read a secret version | `roles/secretmanager.secretAccessor` | **Specific secret** |
| Read/write Firestore from a server app | `roles/datastore.user` when appropriate | Target database/project; consider IAM Conditions/DB scoping |
| Connect to Cloud SQL via connector | `roles/cloudsql.client` | Supported project/instance; verify effective permissions |
| Publish Pub/Sub events | `roles/pubsub.publisher` | Single topic to publish to |

IAM roles **do not replace database authentication**. Cloud SQL requires a valid DB user/password or IAM DB authentication; the Firestore Java server client accesses data via IAM, so user/tenant authorization must be enforced inside the **server application**.

### Inspecting which identity a version uses

~~~bash
gcloud app describe
gcloud app services list
gcloud app versions list --service=orders
gcloud app versions describe VERSION_ID --service=orders
~~~

In `gcloud app describe`, check the app-level default service account. For a specific version, check the configured service account in Console **App Engine → Versions** or the `versions describe` output. These commands are **read-only**; run them before adding or revoking IAM roles in production.

## 4. Application Default Credentials (ADC): never embed JSON keys

On App Engine, Google Cloud client libraries automatically obtain **short-lived access tokens** for the runtime identity through **Application Default Credentials (ADC)**. Java code never needs to read a `private_key` or store a service account JSON file inside an image/artifact.

~~~mermaid
sequenceDiagram
  participant APP as Java app (App Engine version)
  participant ADC as Google Cloud Java client / ADC
  participant META as App Engine metadata/credential provider
  participant API as Google Cloud API
  APP->>ADC: Call Storage/Firestore/Secret Manager
  ADC->>META: Request short-lived credential
  META-->>ADC: Access token for runtime SA
  ADC->>API: Request with token
  API-->>APP: Result or 403 per IAM
~~~

Java example initializing clients:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

public final class GoogleClients implements AutoCloseable {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();
    private final Firestore firestore =
        FirestoreOptions.getDefaultInstance().getService();
    private final SecretManagerServiceClient secrets;

    public GoogleClients() throws Exception {
        // Automatically picks up App Engine version's ADC. No JSON key provided.
        secrets = SecretManagerServiceClient.create();
    }

    public Storage storage() { return storage; }
    public Firestore firestore() { return firestore; }
    public SecretManagerServiceClient secrets() { return secrets; }

    @Override public void close() throws Exception {
        secrets.close();
        firestore.close();
    }
}
~~~

This snippet illustrates **Java client libraries**, requiring compatible `google-cloud-storage`, `google-cloud-firestore`, and `google-cloud-secretmanager` dependencies managed via the Google Cloud Libraries BOM (or your project's dependency manager). Create clients **once per application lifecycle**, reuse connection pools, and close on shutdown rather than creating/closing on every HTTP request.

**Local differs from production:** on a laptop, you can run `gcloud auth application-default login` to get **user ADC** for testing. That does not prove the App Engine runtime SA has the required IAM permissions. Never treat `gcloud auth login` as a reliable stand-in for application ADC.

**Security:** never set `GOOGLE_APPLICATION_CREDENTIALS` pointing to an old JSON key in `app.yaml`. That environment variable causes ADC to prefer that key over the runtime identity. Never log bearer tokens or secret payloads.

## 5. Reading and writing Cloud Storage in Java

Assume the service only needs to read images from bucket `shop-images-lab-unique`, with Object Viewer IAM granted in section 3. Pass the client and bucket name from configuration:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class ImageRepository {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();

    public void listImages(String bucket) {
        Page<Blob> objects = storage.list(
            bucket,
            Storage.BlobListOption.prefix("catalog/")
        );
        for (Blob object : objects.iterateAll()) {
            System.out.println(object.getName());
        }
    }

    public byte[] getImage(String bucket, String name) {
        Blob object = storage.get(BlobId.of(bucket, name));
        if (object == null) {
            throw new IllegalArgumentException("Image not found");
        }
        // Only use getContent for small files; large files must be streamed.
        return object.getContent();
    }
}
~~~

If only `roles/storage.objectViewer` is granted, file writes are denied by IAM. For upload functionality, grant `roles/storage.objectCreator` on the target bucket; if overwriting/deleting is needed, evaluate exact permissions rather than jumping to Storage Admin. **Object names are untrusted input**: validate prefixes, size, MIME types, and user permissions; never allow one tenant to guess object names and read another tenant's documents.

**Avoid storing files on App Engine's local filesystem for durable sharing.** Standard uses a sandbox with temporary storage; Flexible runs VMs, yet files on an instance are still not shared or durable storage designed for application data. Use Cloud Storage for images, reports, and uploads; use Firestore/Cloud SQL for metadata and transactions.

## 6. Firestore Native and Datastore mode

**Firestore Native mode** fits document data, while **Firestore in Datastore mode** serves the Datastore API and legacy apps. The two modes are not interchangeable: choose the right database mode and client library from the start, as APIs, indexes, and query models differ.

Java server client example reading a Firestore Native document:

~~~java
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.concurrent.TimeUnit;

public final class OrderReader {
    // For a DB in another project, configure setProjectId(DATA_PROJECT)
    // instead of defaulting to the App Engine project.
    private final Firestore db =
        FirestoreOptions.getDefaultInstance().getService();

    public String readStatus(String orderId) throws Exception {
        DocumentSnapshot doc = db.collection("orders")
            .document(orderId)
            .get().get(5, TimeUnit.SECONDS);
        if (!doc.exists()) {
            return "NOT_FOUND";
        }
        return doc.getString("status");
    }
}
~~~

Example permission: `roles/datastore.user` for the runtime SA on the resource/project containing the Firestore database per resource IAM capabilities. Server services authenticate via **IAM**, so do not rely on Firebase client security rules to protect end users. **The application itself must authenticate and authorize** whether a user may read `orderId`; never pass an order ID straight from a URL without checking tenant/owner permissions.

Firestore considerations:

- Client API calls incur charges by read/write/delete operations, storage, and networking.
- For write-heavy workloads, design indexes, avoid document hot spots, handle transaction retries, and paginate queries.
- Set timeouts on async futures; never call unbounded `get()` on HTTP request paths.
- When data resides in **another project**, specify the database project in `FirestoreOptions` and grant IAM to the runtime SA from the App Engine project.

## 7. Reading Secret Manager for credentials

Database passwords, API tokens, or business private keys must never sit in plaintext in `app.yaml`, Git, or Java source. Create a **Secret Manager secret** through an approved workflow, then grant read access **only to that specific secret**:

~~~bash
SECRET_PROJECT="security-lab"
SECRET="orders-db-password"
APP_SA="orders-runtime@shop-lab.iam.gserviceaccount.com"

# Assumes the secret already exists with an enabled version.
gcloud secrets add-iam-policy-binding "$SECRET" \
  --project="$SECRET_PROJECT" \
  --member="serviceAccount:$APP_SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets get-iam-policy "$SECRET" \
  --project="$SECRET_PROJECT"
~~~

Fetching a secret in Java via ADC:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DbSecretProvider {
    public String getDbPassword(String projectId, String secretId)
            throws Exception {
        SecretVersionName name =
            SecretVersionName.of(projectId, secretId, "latest");

        try (SecretManagerServiceClient client =
                 SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                client.accessSecretVersion(name);
            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

In production code, reuse a shared client and **cache secrets short-term** with a refresh mechanism supporting rotation (do not call Secret Manager on every SQL query). Java `String` contents cannot be deterministically wiped from memory, so minimize retention scope/lifetime and never log plaintext secrets. On `403`, verify the **right project/secret/version**, runtime SA, and IAM policy; if the secret version is disabled, valid IAM still cannot read it.

## 8. Cloud SQL: IAM, JDBC, and private IP

Cloud SQL is managed separately, not a database “automatically included” inside App Engine. SQL connectivity requires:

1. **IAM**: the runtime SA holds permissions such as `roles/cloudsql.client` within the granted scope.
2. **Database auth**: DB user/password fetched from Secret Manager, or IAM database authentication where supported by the engine/configuration.
3. **Network**: a valid path to the Cloud SQL instance's **public IP** or **private IP**; the connector does not create VPC routes on its own.
4. **Connection pool**: cap connections per instance because App Engine can autoscale.

### JDBC via the Cloud SQL Java Connector

Assume **Cloud SQL for MySQL**, instance connection name `DATA_PROJECT:REGION:INSTANCE`. Example using MySQL Connector/J, Cloud SQL Java Connector SocketFactory, and HikariCP:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

public final class MySqlPool {
    public static DataSource create(
            String instanceConnectionName,
            String dbName,
            String dbUser,
            String dbPassword,
            boolean privateIp) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:mysql:///" + dbName);
        config.setUsername(dbUser);
        config.setPassword(dbPassword); // Fetch from Secret Manager, never hardcode.
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000);

        config.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.mysql.SocketFactory");
        config.addDataSourceProperty(
            "cloudSqlInstance", instanceConnectionName);
        config.addDataSourceProperty(
            "ipTypes", privateIp ? "PRIVATE" : "PUBLIC");
        config.addDataSourceProperty(
            "cloudSqlRefreshStrategy", "lazy");

        // Initialize the pool once per application instance.
        return new HikariDataSource(config);
    }
}
~~~

This assumes Maven/Gradle declares compatible versions of **HikariCP**, **MySQL Connector/J**, and **Cloud SQL Java Connector**. `cloudSqlRefreshStrategy=lazy` suits serverless models where background CPU activity may pause when idle.

**Connecting via private IP:** `ipTypes=PRIVATE` tells the connector to use Cloud SQL's private address, **but** App Engine Standard must have **Direct VPC egress or a Serverless VPC Access connector**, along with matching VPC routes/firewall rules/DNS. In Flexible, VM instances live inside the configured VPC network and can reach private-IP resources over that network. If using public IP, follow approved Cloud SQL connector and network policies; never open `0.0.0.0/0` in authorized networks to fix connectivity errors.

### Why can connection counts cause overload?

Suppose App Engine scales up to **20 application instances**, each opening a JDBC pool with `maximumPoolSize=20`; the app can hold up to **400 connections** from one service alone:

~~~text
20 App Engine instances × 20 JDBC connections/instance
  = 400 database connections (nominal maximum)
~~~

That count excludes background jobs, admin tools, and other services. Cloud SQL caps connections according to machine tier; scaling App Engine without capping pools easily triggers `too many connections`. **Start with small pools**, monitor Cloud SQL connection utilization, and measure throughput/latency before raising limits.

Also use **prepared statements**, connection timeouts, idle timeouts, backoff retries, and transaction idempotency. Retried HTTP requests can still write duplicate rows if SQL operations lack unique business keys.

## 9. How App Engine Standard and Flexible connect to VPCs differently

When calling **Google Cloud APIs** such as Cloud Storage, Firestore, and Secret Manager through supported endpoints, you typically do not need a VPC connector just to reach those APIs. However, reaching a **private IP** for Cloud SQL, Memorystore, or VMs requires an appropriate network path.

| Environment | Path to private IP | Notes |
|---|---|---|
| **App Engine Standard** | **Direct VPC egress** or **Serverless VPC Access connector** | Direct VPC egress is recommended by Google Cloud docs; verify Preview status/region/conditions before production |
| **App Engine Flexible** | VM instances run on the configured VPC network | No Serverless VPC Access connector needed solely to reach private IPs on the attached VPC |
| **Both** | IAM + firewall/routes/DNS + application auth | VPC connectivity does not replace Google Cloud IAM or DB authentication |

### Standard: Direct VPC egress

In a **Standard** version's `app.yaml`, you can add **Direct VPC egress** configuration:

~~~yaml
# Networking section, added to Standard app.yaml once VPC/subnet exist.
vpc_access:
  network_interface:
    network: app-vpc
    subnet: app-subnet
    tags:
      - appengine-orders
  vpc_egress: private-ranges-only
~~~

`private-ranges-only` routes only internal IP ranges through the VPC; `all-traffic` sends all outbound traffic through the VPC and requires checking Cloud NAT, firewalls, DNS, and egress costs if Internet access is needed. **Direct VPC egress for App Engine is currently documented as Preview**; verify availability, quotas, and operational terms for your region/project before use. Changing this network setting requires **deploying a new version** and shifting traffic rather than editing a running version in place.

### Standard: Serverless VPC Access connector

If Direct VPC egress is not suitable yet, use a connector created by the platform team in the same region:

~~~yaml
# ALTERNATIVE option; do not combine with vpc_access above.
vpc_access_connector:
  name: projects/shop-lab/locations/asia-southeast1/connectors/app-connector
  egress_setting: private-ranges-only
~~~

A connector incurs **VM operating charges per configuration even during low traffic** and has throughput/instance limits; monitor utilization, subnet CIDRs, and firewalls. With Shared VPC, host-project permissions and firewall rules may be required. Attaching a connector to a new version does not retroactively update older versions.

### Flexible: VPC sits at the VM level

App Engine Flexible uses managed Compute Engine VMs, connecting to a VPC via environment configuration. **Conceptual** example in Flexible `app.yaml`:

~~~yaml
runtime: java
env: flex
network:
  name: app-vpc
~~~

This is not a Standard `app.yaml`: never mix `env: flex` with Standard's `instance_class: F2` or `vpc_access`. Both environments still require IAM, firewall, and cost controls; Flexible has a different instance billing model from Standard.

## 10. Per-version app.yaml configuration and controlled deployment

For the **Java second-generation runtime** on App Engine Standard, a sample `app.yaml` for the orders service:

~~~yaml
runtime: java21
service: orders
instance_class: F2

# Identity attached to the VERSION created by this deployment.
service_account: orders-runtime@shop-lab.iam.gserviceaccount.com

automatic_scaling:
  min_instances: 0
  max_instances: 10

env_variables:
  GCS_BUCKET: "shop-images-lab-unique"
  DATA_PROJECT: "data-lab"
  SECRET_PROJECT: "security-lab"
  SQL_INSTANCE_CONNECTION_NAME: "data-lab:asia-southeast1:orders-db"
  DB_NAME: "orders"
  DB_USER: "orders_app"

# Specify only when the artifact is built and the file actually exists
# in the deployment source. The web server must listen on 0.0.0.0:8080.
entrypoint: "java -jar target/orders.jar"
~~~

**Important explanations:**

- `runtime: java21` is a Java second-generation example; pick a supported Java runtime for real apps.
- `service_account` is the **version's runtime SA**, **not** the deployer identity. If `--service-account` is passed on the CLI, the CLI value wins.
- `max_instances` caps the scaling target for the version, not an absolute cost ceiling; also factor in other versions, Cloud SQL, and networking.
- Never store `DB_PASSWORD` in `env_variables`; read it via Secret Manager (section 7).
- `entrypoint` here assumes CI/Maven builds an **executable JAR** at `target/orders.jar`. If the app uses a WAR or default buildpack, configure a valid entrypoint matching the real layout. The web server must bind **`0.0.0.0:8080`**.
- Add the `vpc_access` or `vpc_access_connector` block from section 9 only when **private IP connectivity** is required and networking is verified.

### Canary flow for a new version

~~~bash
APP_PROJECT="shop-lab"
gcloud config set project "$APP_PROJECT"

# Confirm App Engine application exists; app location cannot be changed arbitrarily.
gcloud app describe

# Build Java application via project pipeline, producing target/orders.jar.
# After testing the image/JAR, deploy the version WITHOUT shifting traffic.
gcloud app deploy app.yaml \
  --version=orders-wif-v2 \
  --no-promote

gcloud app versions describe orders-wif-v2 --service=orders
gcloud app versions list --service=orders
~~~

These commands illustrate the practitioner workflow and are **not executed while authoring documentation**. If a version with that name already exists, never overwrite a serving version without checking traffic/rollback. After verifying the new version and its identity, operations can **shift traffic gradually** via Console or `gcloud app services set-traffic`, keeping rollback to the prior version intact.

### A subtle failure caused by an identity change

If v1 previously ran with the App Engine default SA holding Editor, while v2 uses `orders-runtime` with only Object Viewer, an API endpoint writing to Cloud Storage **will fail only when requests land on v2**. At 10% canary traffic, failures appear intermittently. Therefore test **every operation and every version**, not just `/healthz` returning HTTP 200.

## 11. Local environments, CI/CD, and secrets

| Execution context | Recommended credential acquisition | Avoid |
|---|---|---|
| Dev laptop | User ADC via `gcloud auth application-default login` or policy-approved account impersonation | Copying service account private keys into the repo |
| CI/CD | Workload Identity Federation for pipelines or short-lived scoped deploy identities | Long-lived JSON keys in pipeline variables |
| App Engine version | Runtime service account + infrastructure ADC | Setting `GOOGLE_APPLICATION_CREDENTIALS` to an old key |
| Cross-project data | App Engine project's runtime SA granted IAM on target project resources | Confusing the SA's project with the data's project |

Local:

~~~bash
# Uses local developer identity; do not run this inside App Engine.
gcloud auth application-default login

# Java client reads ADC from local credentials.
# Test against dev resources, never production buckets/secrets.
~~~

To prevent environments from touching the wrong data, use **distinct project IDs/bucket names/secrets** via non-secret config. In CI/CD, run offline unit tests with emulators/mocks when feasible; run integration tests against dev resources with low-privilege roles.

### Secret rotation

1. Create a new secret version and confirm consumers support the new credential.
2. Maintain an overlap window for databases/APIs when rotating both passwords and users.
3. App Engine clients reading `latest` follow their caching policy; refresh secrets or redeploy if instances cache the old value.
4. Check DB auth errors and verify logs **never expose secrets**.
5. Disable the old version once no consumers remain, with a clear rollback plan.

Do not assume creating a `latest` version in Secret Manager automatically re-authenticates all open connection pools with the new password.

## 12. Monitoring, security, and cost

In production, monitor **data access**, **instance counts**, and **external dependencies** together.

### Operational security

- Grant the runtime service account only the IAM roles the app needs, preferring bucket/secret/topic/database scope over project-wide grants.
- Separate **deployer** from **runtime** permissions; grant `iam.serviceAccounts.actAs` only to humans/pipelines authorized to deploy with that service account.
- Use **Secret Manager**, encryption at rest, and scoped audit logging; never print database passwords, tokens, or PII to stdout.
- When using Cloud SQL, separate IAM Client permissions from database user privileges and keep TLS/authentication through the connector.
- Avoid using an App Engine default service account that still holds `Editor` across multiple services; use dedicated per-version service accounts where permissions differ.
- When multiple versions receive traffic, check **both identities and permissions** before revoking an older version's access.
- Enforce per-user/tenant authorization inside the Java server, especially when the Firestore server client or Cloud SQL can read multiple records.

### Metrics to monitor

| Layer | Metrics/logs | What it catches |
|---|---|---|
| App Engine | Request count, 4xx/5xx, P95 latency, instance count, version traffic | Errors appearing post-deploy or isolated to one version |
| IAM/Audit | PermissionDenied, principal email, role changes | Wrong SA, missing role, privilege drift |
| Cloud Storage | Read/write operations, 403/404, network egress | Wrong bucket, revoked access, abnormal access spikes |
| Firestore | Document reads/writes, query latency, indexes, quotas | Expensive queries, hot documents |
| Cloud SQL | Active connections, CPU, latency, failed connections | Oversized pools, database bottlenecks |
| Secret Manager | AccessVersion calls, access failures, quotas | Excessive secret reads, disabled versions |
| VPC egress | Connector throughput/instances or Direct VPC egress, firewall denials | Private IP timeouts, egress costs |

Read-only status/log example:

~~~bash
gcloud app versions list --service=orders
gcloud app versions describe VERSION_ID --service=orders
gcloud app logs tail --service=orders

# Use Cloud Logging/Monitoring Console to filter by
# service, version, 403/5xx status, and deployment timestamp.
~~~

### Real-world costs

App Engine Standard bills by instance class and automatic/basic/manual scaling; Flexible bills by VM/vCPU/RAM and related resources. **Do not count HTTP requests alone**:

~~~text
Approximate total operating cost
  = App Engine instance hours / compute
  + Cloud Storage bytes + API operations + egress
  + Firestore reads/writes/indexes/storage
  + Cloud SQL instance + storage + backups + networking
  + Secret Manager operations
  + VPC connector (if used) / networking / NAT
  + Cloud Logging, Monitoring, and dependent resources
~~~

**Example:** App Engine scales from 5 to 30 instances, each holding up to 10 SQL connections → up to **300 connections**. Increasing App Engine capacity can overload Cloud SQL and drive backend charges. Tune pool and instance limits using load tests, DB quotas, and latency rather than treating `max_instances` as a sole cost guarantee.

Set **Cloud Billing budgets/alerts**, track owners of buckets/connectors/databases, and watch charges from **versions still running** after a canary. Budget alerts do not shut down services automatically; deleting a version does not delete buckets, Cloud SQL, or connectors.

## 13. Common troubleshooting table

| Symptom | Possible cause | First checks |
|---|---|---|
| `403` reading Storage | Runtime SA lacks Object Viewer, wrong bucket/project, or IAM Deny | `gcloud app versions describe`, bucket IAM policy |
| Works locally, App Engine returns `403` | Local uses user ADC with broader roles than runtime SA | Compare both principals; never upload local keys |
| Part of requests fail after deploy | Two versions use different service accounts/permissions | App Engine traffic splits and per-version permissions |
| `403` reading Secret Manager | Missing Secret Accessor on target secret, wrong project | Secret IAM, enabled version, and runtime SA |
| Cloud SQL Java Connector reports `permission denied` | Missing `roles/cloudsql.client`, wrong instance connection name | Cloud SQL project IAM, connector logs |
| Cloud SQL `connection timeout` over private IP | Missing VPC egress, bad firewall/router/subnet | `vpc_access`/connector, private IP, and network path |
| Cloud SQL `Access denied` or auth failed | Wrong DB user/password/IAM DB auth | DB user, secret version, in-DB grants |
| `Too many connections` | Autoscaling multiplies JDBC pools, leaked connections | Cloud SQL active connections, pool size per instance |
| Firestore `PERMISSION_DENIED` | Missing Datastore User or wrong database project | Runtime SA, database/project IAM |
| Firestore index/quota error | Query needs composite index, hot document, or quota exceeded | Firestore error code, indexes, and usage |
| Object not found in bucket | Wrong prefix/name, not uploaded, 404, or filtered access | Storage list/BlobId, project/bucket |
| App deploy fails with `actAs` | Deployer cannot impersonate runtime SA | `roles/iam.serviceAccountUser` on target SA |
| Cannot build deployment artifact | Cloud Build/Artifact Registry service agent/permissions insufficient | Build logs, deployer and service agent IAM |
| VPC connector still billed | Removed from new version config, yet connector still exists | Inventory versions and connector lifecycle |
| Bill climbs after canary | Multiple active versions, min instances, DB/networking | Billing by SKU, traffic, and instance counts |

**Diagnostic rule:** on `403` from Storage/Firestore/Secret Manager, read **the exact API and principal being denied** rather than granting Editor to test. On private IP `timeout`, inspect the VPC path before changing IAM roles. If Cloud SQL reports an invalid password, do not add `roles/cloudsql.admin`.

## 14. Scenario: Orders API needing multiple data sources

The development team deploys `orders-api` to App Engine Standard Java:

~~~text
App Engine service orders, version v2
  Runtime SA: orders-runtime@shop-prod.iam.gserviceaccount.com
     ├── Object Viewer → bucket product-images (data project)
     ├── Datastore User → Firestore orders (data project)
     ├── Secret Accessor → secret sql-password (security project)
     └── Cloud SQL Client → Cloud SQL orders-db (data project)
                                    ↑
                        Direct VPC egress → private IP
~~~

Deployment workflow:

1. Platform team creates the SA in the **App Engine project** and confirms the Standard region and valid VPC/subnet.
2. Data/security teams grant IAM **on the exact resources** in target projects; Cloud SQL DB admin creates DB user `orders_app` with needed schema privileges.
3. Java code uses ADC, Secret Manager, and Cloud SQL Java Connector; no passwords live in `app.yaml`.
4. CI/CD builds the JAR, deploys version v2 with `--no-promote`, attaches the SA via `service_account`, and adds `vpc_access` for private IP if needed.
5. Team tests **object reads**, **Firestore reads**, **secret reads**, and **SQL queries**, and confirms out-of-scope access is denied.
6. Monitor P95/5xx, IAM denials, SQL connections, and costs; shift traffic via canary with rollback ready.

When a reporting service needs permission to **write reports** without reading payment secrets, create a separate `report-runtime`. **Never grant a shared “app-engine-runtime-editor” role to both services.**

## 15. Checklist and exercises

### Pre-production checklist

- [ ] Verified the **effective service account of every version** and which versions still receive traffic.
- [ ] Dedicated runtime SA per responsibility; default Editor avoided when unnecessary.
- [ ] Deployers can `actAs` only approved SAs.
- [ ] Java clients use ADC; no JSON private keys in images, Git, or `app.yaml`.
- [ ] Every Cloud Storage bucket, Firestore database, secret, and Cloud SQL instance has scoped permissions.
- [ ] Cross-project IAM references the runtime SA from the App Engine project without mixing up project IDs.
- [ ] Cloud SQL has **IAM + DB auth + network path**; pool size and timeouts tested.
- [ ] Standard private IP uses Direct VPC egress/connector per support status; Flexible uses its configured VPC.
- [ ] App Engine config holds only **non-secret env vars**; passwords come from Secret Manager with a rotation plan.
- [ ] Per-service/version monitoring, IAM denial alerts, DB connection metrics, and cost tracking are active.
- [ ] New version verified before traffic cutover; rollback and unused-resource cleanup plans exist.

### Practice exercises

**Exercise 1 — Choose IAM permissions.** A Java service only needs to (a) read images in bucket `catalog-images`, (b) publish to topic `orders-created`, and (c) read secret `db-pass`. Pick the role and **scope** for each resource; explain why `roles/editor` must not be used.

**Exercise 2 — ADC and local/prod differences.** The app reads Cloud Storage fine on a developer laptop, yet App Engine v2 returns `403`. List at least four inspection steps, including `gcloud app versions describe` and bucket IAM policies.

**Exercise 3 — Cloud SQL.** App Engine Standard reaches private-IP Cloud SQL MySQL via the Java Connector. Diagram the three layers **IAM, database user, and VPC**, write a HikariCP configuration with `ipTypes=PRIVATE`, and explain why having the Client role can still time out.

**Exercise 4 — Calculate connection counts.** A service has `max_instances=15`, and each instance opens a JDBC pool with `maximumPoolSize=12`. Compute the nominal maximum SQL connections and propose how to cap them when Cloud SQL allows fewer connections after subtracting other services.

**Exercise 5 — Version identity.** Version v1 uses the default SA; v2 uses `orders-runtime`, with traffic split 80/20. After changing the app-level default SA, has v1's identity changed? Describe how to verify and safely shift traffic/revoke old permissions.

**Exercise 6 — Secrets and cross-project access.** App Engine is in project A, Secret Manager in B, and Firestore in C. Tabulate which project hosts the **runtime SA** and which hosts each **resource**, where IAM bindings belong, and how to prevent leaking passwords in logs.

**Exercise 7 — Choose VPC egress.** A Java service needs private-IP Redis and an Internet API. Compare `private-ranges-only` vs. `all-traffic`, Direct VPC egress vs. a connector, factor in Cloud NAT/firewalls/cost, and note the Preview status of Direct VPC egress.

## Official references

- [Configure App Engine service accounts](https://cloud.google.com/appengine/docs/standard/configure-service-accounts) — app-level default, per-version, IAM, and CLI/YAML precedence.
- [App Engine app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml) — runtime, `service_account`, scaling, `vpc_access`.
- [App Engine Java runtime configuration](https://cloud.google.com/appengine/docs/standard/java-gen2/configuring-your-app-with-app-yaml) — Java second-generation and `app.yaml`.
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) — how client libraries discover credentials.
- [Use Cloud Storage with App Engine](https://cloud.google.com/appengine/docs/standard/using-cloud-storage) — object storage and Java clients.
- [Use Firestore with App Engine](https://cloud.google.com/appengine/docs/standard/using-firestore) — Native/Datastore mode and database connectivity.
- [Connect App Engine Standard to Cloud SQL MySQL](https://cloud.google.com/sql/docs/mysql/connect-app-engine-standard) — Java Connector/JDBC, pooling, and auth.
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory) — SocketFactory properties, private/public IP.
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control) — IAM Secret Accessor and secret versions.
- [Direct VPC egress for App Engine Standard](https://cloud.google.com/appengine/docs/standard/vpc-direct-vpc) — network config and Preview limits.
- [Serverless VPC Access for App Engine](https://cloud.google.com/appengine/docs/standard/connecting-vpc) — connectors, firewalls, and egress settings.
- [App Engine Flexible environment](https://cloud.google.com/appengine/docs/flexible) — VM networking and runtime model.
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit) — tracking IAM changes and Data Access.
- [App Engine pricing](https://cloud.google.com/appengine/pricing) — instance classes, scaling, and usage.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing), [Firestore pricing](https://cloud.google.com/firestore/pricing) — storage and database operation costs.
