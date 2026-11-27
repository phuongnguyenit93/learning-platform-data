# Authenticating Java with ADC Locally and on GCP Runtimes

A Java application may run on a developer's workstation, in Cloud Run, Google Kubernetes Engine (GKE), Compute Engine, or a CI/CD system. Each environment provides identity differently. If an application hardcodes a service account key path in code, moving across environments becomes hard to manage and increases the risk of credential exposure.

**Application Default Credentials (ADC)** is the mechanism Google Cloud libraries use to automatically locate credentials suitable for the current runtime environment. With ADC, an application can use the same Java code to call Cloud Storage, Pub/Sub, Secret Manager, or other Google Cloud APIs; the actual identity is configured externally.

This lesson explains how to authenticate Java with ADC during local development and when deploying to GCP runtimes, while covering how to combine IAM, service accounts, Workload Identity Federation, and quota project management to avoid common pitfalls.

## 1. What Problem Does ADC Solve?

Before calling a Google Cloud API, a client needs credentials. These credentials allow the library to obtain an appropriate OAuth 2.0 access token and send it with the request. The Google Cloud service then checks IAM permissions and related conditions.

For example, the same `orders-api` application may:

- Read objects from Cloud Storage.
- Publish messages to Pub/Sub.
- Read a secret version from Secret Manager.
- Send logs and metrics to Cloud Logging and Cloud Monitoring.

The application needs an identity granted the corresponding permissions. On a personal workstation, the identity may come from a developer login session or service account impersonation. On Cloud Run, Compute Engine, and GKE, the identity should be supplied by the platform to the workload.

ADC separates **application code**, **identity**, **access permissions**, and **execution environment**.

| Component | Role |
|---|---|
| Java Google Cloud client library | Calls service APIs and handles tokens automatically when ADC is configured |
| ADC | Discovers credential sources from the environment |
| Google Auth Library for Java | Provides credential classes and manages token refresh |
| IAM | Determines which operations a principal is allowed to perform |
| OAuth scope | Restricts token access scope when a service uses scopes |
| Project/quota project | Identifies the target resource or project used for API quota/billing |
| Service account | Identity for applications and workloads |
| Metadata server | Supplies short-lived credentials for supported GCP runtimes |

**ADC does not automatically grant IAM permissions.** Finding credentials only means the application has an identity source to authenticate with. If the principal lacks permissions on the target resource, the API can still return `PERMISSION_DENIED`.

## 2. ADC Credential Discovery Order

For many Google Cloud Java libraries, ADC searches for credential sources in the following primary priority order:

1. The file pointed to by the `GOOGLE_APPLICATION_CREDENTIALS` environment variable.
2. The local ADC file created by the Google Cloud CLI using `gcloud auth application-default login`.
3. Credentials from the metadata server in supported Google Cloud environments.

~~~mermaid
flowchart TD
    A[Java Google Cloud client] --> B[Application Default Credentials]
    B --> C{GOOGLE_APPLICATION_CREDENTIALS set?}
    C -->|Yes| D[Load credential configuration file]
    C -->|No| E{Local ADC file exists?}
    E -->|Yes| F[Load local user or impersonated credentials]
    E -->|No| G{GCP metadata server available?}
    G -->|Yes| H[Use attached workload identity]
    G -->|No| I[Credential discovery fails]
    D --> J[Obtain access token]
    F --> J
    H --> J
    J --> K[Google Cloud API]
    K --> L[IAM and API authorization checks]
~~~

This order leads to important behaviors:

- If `GOOGLE_APPLICATION_CREDENTIALS` is set, the specified file can take precedence even when running on Cloud Run or GKE.
- If the environment variable path is wrong or the file is invalid, ADC discovery may fail; do not assume the library will always ignore the error and fall back to the metadata server.
- During local development, the local ADC file is typically used if no environment variable specifies another source.
- In GCP runtimes, use the workload-attached identity to obtain tokens from the metadata server instead of copying a JSON key into the container.

ADC can load several types of credential configuration files: user credentials, service account credentials, or external account configurations used for Workload Identity Federation. Not every JSON file is a private key.

### Local ADC File Location

Common paths:

| Operating system | Path |
|---|---|
| Linux/macOS | `~/.config/gcloud/application_default_credentials.json` |
| Windows | `%APPDATA%\\gcloud\\application_default_credentials.json` |

These files contain authentication data and should not be committed to Git, copied into container images, or shared over chat. You do not need to open the file to inspect tokens; use `gcloud` ADC management commands.

## 3. Distinguishing gcloud CLI Login from ADC Login

The Google Cloud CLI and Java client libraries do not necessarily share the same set of credentials.

| Command or setting | Used for |
|---|---|
| `gcloud auth login` | Signs in an account so `gcloud` can run CLI commands |
| `gcloud auth application-default login` | Creates local ADC for applications via client libraries |
| `gcloud config set project PROJECT_ID` | Selects the default project for many CLI commands |
| `gcloud auth application-default set-quota-project PROJECT_ID` | Sets the quota project for local ADC |
| `GOOGLE_CLOUD_PROJECT` | Suggests a project to apps/libraries supporting this variable |
| `GOOGLE_APPLICATION_CREDENTIALS` | Specifies the highest-priority credential source for ADC |

A frequent mistake is that `gcloud storage ls` succeeds while the Java application reports no credentials found. The cause is usually that the developer logged into the CLI without creating local ADC.

Another mistake is having the CLI target project A while the Java client connects to project B. **The authenticating identity and the resource-hosting project are two separate concepts.** To avoid confusion, explicitly pass the project ID to the client in business flows requiring deterministic behavior.

## 4. Setting Up ADC on a Local Machine

### Step 1 — Sign in to ADC

In a development environment with Google Cloud CLI installed:

~~~bash
gcloud auth application-default login
~~~

This opens the user authentication flow and saves local ADC. It does not copy the user's IAM permissions onto a production service account.

### Step 2 — Set the Quota Project

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

Some Google APIs require a valid quota project. The principal billed for quota must have permission to use the service/quota, typically including `serviceusage.services.use` on the quota project. Without this permission, the client may authenticate yet receive quota-project errors from the API.

### Step 3 — Identify the Target Project

~~~bash
gcloud config set project PROJECT_ID
~~~

This sets the default project for the CLI. For Java applications, still declare the project ID explicitly or read it from an environment variable configured for the application.

Linux/macOS:

~~~bash
export GOOGLE_CLOUD_PROJECT="PROJECT_ID"
~~~

Windows PowerShell:

~~~powershell
$env:GOOGLE_CLOUD_PROJECT = "PROJECT_ID"
~~~

### Step 4 — Test the Application

Run the Java program using an ADC-enabled client library and perform a safe read operation against a test resource. If you get `403`, check IAM, API enablement, and the quota project rather than logging in repeatedly.

### Step 5 — Revoke ADC When Needed

When switching accounts or no longer using local ADC:

~~~bash
gcloud auth application-default revoke
~~~

This deletes/revokes local ADC credentials managed by the Cloud SDK. It does not sign out all accounts saved by `gcloud auth login` for the CLI.

## 5. Local Development with Service Account Impersonation

Using local user ADC is convenient, but a user's permissions may be broader than a production workload's permissions. A more production-realistic test method is **service account impersonation** with a restricted service account.

Suppose `orders-dev@PROJECT_ID.iam.gserviceaccount.com` is only allowed to read objects in a test bucket.

The developer needs permission to mint tokens on behalf of that service account, commonly granted via:

`roles/iam.serviceAccountTokenCreator`

Create local ADC using impersonation:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account="orders-dev@PROJECT_ID.iam.gserviceaccount.com"
~~~

Google Auth Library for Java supports CLI-generated impersonated ADC configurations in supported environments. With this setup, the Java program still calls `GoogleCredentials.getApplicationDefault()`, while access tokens are issued under the service account identity on behalf of the authorized user.

Advantages:

- No need to download service account JSON keys onto personal machines.
- Test permissions closely match runtime permissions.
- Impersonation permissions can be managed, revoked, and audited.
- Reduces the risk of developers accidentally relying on overly broad personal permissions.

Notes:

- The user must still have permission to impersonate the service account.
- The service account must be granted permissions on the target resource; the user's impersonation permission does not grant permissions to the service account itself.
- Certain libraries or specialized auth flows may have extra requirements; test with your Google Auth Library version.
- Do not use an overly privileged production service account just to run tests on a laptop.

For multi-member teams, create separate service accounts per dev/staging/prod environment and govern impersonation permissions on demand.

## 6. Using ADC in a Java Application

A Java application normally does not pass a service account key path directly into a client builder. Google Cloud libraries use ADC when no other credentials are configured.

### Maven Dependencies

Example using the Google Cloud Java Libraries BOM to align versions:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>REPLACE_WITH_VERIFIED_BOM_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
  </dependency>
</dependencies>
~~~

Replace `REPLACE_WITH_VERIFIED_BOM_VERSION` with a BOM version compatible with your JDK and build ecosystem. Do not pin an unverified example version into a production project.

### Example: Checking Object Read Access

The Java snippet below uses ADC to inspect object metadata in a lab bucket. It neither downloads object contents nor prints access tokens:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class AdcStorageCheck {
    public static void main(String[] args) throws Exception {
        String projectId = requiredEnv("GOOGLE_CLOUD_PROJECT");
        String bucket = requiredEnv("CHECK_BUCKET");
        String objectName = requiredEnv("CHECK_OBJECT");

        GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();

        Storage storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .setCredentials(credentials)
                .build()
                .getService();

        Blob object = storage.get(BlobId.of(bucket, objectName));
        System.out.println(object == null
                ? "Object not found"
                : "Object metadata is readable");
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

The application needs object read permission, such as `roles/storage.objectViewer` granted on the appropriate bucket. If the object does not exist, the program prints `Object not found`; if the principal lacks permission, the API returns an authorization error.

The library handles fetching and refreshing tokens as needed. Do not read the ADC file manually, parse credential JSON manually, or log tokens.

### Using the Default Client When Custom Configuration Is Unneeded

In concise applications:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

When credentials are not explicitly passed, the library uses ADC discovery. However, multi-project applications should explicitly set the project ID to avoid targeting the wrong resources or quota context.

### Access Tokens vs ID Tokens

- **OAuth access tokens** are used for Google APIs such as Cloud Storage or Pub/Sub.
- **OIDC ID tokens** are typically used when an HTTP service verifies the caller's identity by audience—for example, invoking an authenticated Cloud Run service.
- Do not use an access token in place of an ID token just because both are token strings.
- For HTTP services requiring ID tokens, use Google Auth Library APIs such as `IdTokenCredentials` and set the audience to the target service.

## 7. Integrating ADC with Spring Boot

A Spring Boot application can use Google Cloud Java client libraries directly or use Google Cloud Spring starters with auto-configuration.

When using a client library directly, declare a Spring bean:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CloudStorageConfiguration {
    @Bean
    public Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Business services can receive `Storage` via constructor injection:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ObjectMetadataService {
    private final Storage storage;

    public ObjectMetadataService(Storage storage) {
        this.storage = storage;
    }

    public boolean exists(String bucket, String objectName) {
        return storage.get(BlobId.of(bucket, objectName)) != null;
    }
}
~~~

Locally, the bean uses local ADC or impersonated ADC. When deployed to Cloud Run/GKE/Compute Engine, it uses workload credentials supplied by the environment, provided no other credential configuration overrides it.

### Google Cloud Spring Starters

Google Cloud Spring can auto-configure certain clients and project settings. If a starter already creates a `Storage` bean, avoid declaring another bean of the same type without verifying configuration to prevent duplicate beans or mismatched credentials.

Some applications configure project IDs and credentials locations via Google Cloud Spring properties. When choosing ADC as the default, avoid pointing directly to a JSON key in `application.yml` or `application.properties`.

Distinguish three configuration categories:

| Property | Where it is managed |
|---|---|
| Project ID or bucket name | Environment variables or application configuration |
| Workload identity | Cloud Run service account, GKE workload identity, Compute Engine attached service account |
| Access permissions | IAM on project, bucket, topic, or secret |

A Spring configuration may specify a bucket name, but **should not contain private keys or refresh tokens**.

### Testing Spring

For unit tests, mock the `Storage` bean or inject a mocked adapter/repository. Do not require every unit test to log in via ADC and reach GCP. For integration tests, use a lab project/bucket, a least-privilege service identity, and test data.

## 8. ADC on Cloud Run

Cloud Run lets you attach a service account as the **runtime service identity** of a service or job. Google Cloud provides short-lived access tokens via the metadata server to client libraries inside the container.

Example updating a Cloud Run service's identity:

~~~bash
gcloud run services update orders-api \
  --service-account="orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Before changing the service identity, verify the deployer's permissions (including permission to act as the service account) and the runtime identity's permissions. Changing a service identity is a deployment action that can impact the application if the new account lacks IAM roles.

Example granting object read access on a specific bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="serviceAccount:orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Authentication flow:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Auth as Google Auth Library
    participant Meta as Cloud Run metadata server
    participant API as Cloud Storage API
    App->>Auth: Create Storage client with ADC
    Auth->>Meta: Request workload access token
    Meta-->>Auth: Short-lived token
    Auth->>API: Call API with token
    API-->>App: Result or authorization error
~~~

The advantage is that the container does not store private keys. The library automatically manages tokens and refreshes. To adjust permissions, update the runtime service account's IAM and verify the app rather than issuing a new key.

**Do not set `GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run to point to a JSON key** when the app can use an attached service account. This variable can override the metadata server credential source and introduce operational risk.

### Cloud Run Jobs

Cloud Run Jobs also support service identities. Each job should carry permissions tailored to its specific task—for instance, a batch job reading one bucket or writing to one topic. Do not share one overly broad service account across all jobs and services out of convenience.

## 9. ADC on GKE with Workload Identity Federation

On GKE, Java applications normally run inside Pods. The recommended authentication method is **Workload Identity Federation for GKE**, allowing workloads to obtain an identity without mounting a service account JSON key.

Basic model:

1. The GKE cluster supports Workload Identity Federation for GKE.
2. The workload uses a Kubernetes ServiceAccount (KSA).
3. IAM grants permissions to the KSA principal on GCP resources, or maps the KSA to an IAM service account when needed.
4. The Pod calls the GKE metadata server to fetch credentials.
5. The Java client library uses ADC as usual.

### Declaring a Kubernetes ServiceAccount

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
~~~

In the Deployment:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
~~~

This is an illustrative `spec.template.spec` snippet. A complete Deployment still needs selectors, Pod labels, and other required Kubernetes fields.

### Granting IAM Directly to the KSA Principal

With direct resource access, you can grant bucket read permission to the KSA principal:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/orders/sa/orders-api" \
  --role="roles/storage.objectViewer"
~~~

Replace `PROJECT_NUMBER` with the project number, `PROJECT_ID` with the project ID hosting the cluster's workload identity pool, and the bucket with the actual resource. The cluster, node pool, and metadata server must be properly configured. On GKE Standard, verify that the node pool has the GKE metadata server enabled; Autopilot manages this automatically.

No service account key needs to be downloaded to the Pod. `StorageOptions.getDefaultInstance().getService()` continues to work via ADC.

### Linking a KSA to an IAM Service Account

Some requirements or services may call for a KSA impersonating an IAM service account. In that case, you must:

- Add the `iam.gke.io/gcp-service-account` annotation on the KSA.
- Grant `roles/iam.workloadIdentityUser` to the KSA principal on the IAM service account.
- Grant resource permissions to the IAM service account.

Example annotation:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    iam.gke.io/gcp-service-account: orders-gke@PROJECT_ID.iam.gserviceaccount.com
~~~

Choose direct resource access when APIs and policies allow; use IAM service account binding when genuinely needed. Avoid enabling both mechanisms haphazardly, as it becomes hard to tell which principal actually holds permissions.

### Limits to Verify

- The Pod must use the exact KSA that was granted permissions.
- Workload Identity Federation for GKE must be enabled and compatible with the running nodes.
- Kubernetes RBAC and Google Cloud IAM are separate authorization layers.
- Certain APIs have different auth requirements or principal formats; verify the specific case.
- NetworkPolicies and cluster networking must not block required access to the metadata server and Google APIs.

## 10. ADC on Compute Engine

Compute Engine lets you attach a service account to a VM. Client libraries on the VM fetch tokens from the metadata server, similar to Cloud Run.

Design points:

- Attach a dedicated service account per workload rather than the overly permissive default service account.
- Grant IAM to the service account only on resources the application genuinely needs.
- Check VM **access scopes**. Compute Engine scopes act as an additional restriction alongside IAM; an API call can still be rejected despite sufficient IAM if the VM scope does not allow it.
- Under modern IAM practices, VMs typically use the `cloud-platform` scope paired with least-privilege IAM to manage fine-grained access through IAM.
- Do not copy service account keys onto VMs; rely on the metadata server and short-lived tokens.

Example inspecting an instance configuration:

~~~bash
gcloud compute instances describe "VM_NAME" \
  --zone="ZONE" \
  --project="PROJECT_ID" \
  --format="yaml(serviceAccounts)"
~~~

A VM with a sufficient scope but a service account lacking IAM will still be denied bucket access. Conversely, a service account with bucket read IAM on a scope-restricted VM can also fail.

If the Java application runs in a container on a VM, verify the path to the metadata server and the VM identity. Do not assume that container automatically has a separate identity unless a dedicated isolation mechanism is configured.

## 11. Running Java Outside GCP with Workload Identity Federation

Applications may run on GitHub Actions, GitLab, external Kubernetes clusters, or private data centers. For workloads outside GCP, consider **Workload Identity Federation (WIF)** to exchange external identities for short-lived credentials instead of static service account keys.

High-level flow:

1. An external identity provider issues a token to the workload.
2. Google Security Token Service verifies the token against a configured workload identity pool/provider.
3. The workload obtains Google credentials via federation or authorized service account impersonation.
4. The Java client library consumes the external account credential configuration through ADC.
5. Google Cloud APIs enforce IAM as normal.

An external account credential configuration JSON can be referenced via:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/wif-credential-config.json"
~~~

A WIF configuration file does not contain a service account private key like a JSON key file, yet it still requires protection because it specifies the token source, audience, and authentication parameters. Do not arbitrarily alter endpoints or run untrusted executable credential sources.

### Distinguishing External WIF from WIF for GKE

- **External WIF** federates identities from an external identity provider into Google Cloud.
- **Workload Identity Federation for GKE** provides identities to Pods within a GKE cluster.
- Both reduce the need for long-lived service account keys, though principal formats, metadata server usage, and IAM configuration differ.

## 12. IAM, Quota Projects, and Access Permissions

For a Java API call to succeed, distinguish each verification layer:

| Layer | Question | Typical error |
|---|---|---|
| ADC discovery | Can the library find a credential source? | Default credentials not found |
| Token issuance | Can a valid token be obtained? | Token refresh or metadata server error |
| API enablement | Is the required API enabled? | Service/API disabled |
| IAM | Does the principal have permissions on the resource? | `PERMISSION_DENIED`, HTTP 403 |
| OAuth scope | Does the token carry the required scopes? | Insufficient authentication scopes |
| Quota project | Is the quota/billing project valid? | User project or service usage permission error |
| Resource address | Are the project, bucket, topic, and secret correct? | `NOT_FOUND`, HTTP 404 |
| Network | Can the runtime reach Google APIs? | Timeout, DNS, or proxy error |

### Least-Privilege Example

A service account that only reads objects in a bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="serviceAccount:orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

If the app also needs to publish to Pub/Sub, grant the appropriate role on the specific topic rather than `roles/editor` at the project level.

Do not grant `roles/owner`, `roles/editor`, or IAM admin roles just to silence a 403 error. Read the error message, identify the required API method and permission, and grant the narrowest possible role.

### IAM and OAuth Scopes

IAM expresses **what can be done on which resource**. OAuth scopes describe the breadth of operations an access token is allowed to perform. On Compute Engine, both scopes and IAM affect the outcome. With most Google Cloud Java client libraries, the library automatically requests appropriate scopes.

If constructing credentials manually or calling HTTP APIs directly, understand the specific API scopes required. Do not unconditionally add broad scopes to every application just because a single call failed.

## 13. Securing Credentials and Reducing Key Exposure

Recommended practices:

- Use ADC and attached workload identities on Cloud Run, GKE, and Compute Engine.
- Use local ADC impersonation or restricted user ADC for development.
- Use WIF for workloads outside GCP.
- Avoid creating service account JSON keys whenever a keyless alternative exists.
- Never commit `application_default_credentials.json`, JSON keys, refresh tokens, or access tokens.
- Never print `Authorization` headers, tokens, or credential file contents to logs.
- Grant IAM at the bucket, topic, secret, or resource level whenever possible.
- Separate identities across dev, staging, and production.
- Audit impersonation permissions and overly privileged service accounts periodically.
- Enable Cloud Audit Logs and monitor critical access events.
- Use Secret Manager for API keys or application secrets; do not use it to store service account keys if workload identity can be used.

### Why Avoid Downloading JSON Keys Locally?

A service account JSON key contains a long-lived private key. Anyone holding a copy of the key with API network access can impersonate the service account until the key is disabled or expires by policy. Keys can leak through Git history, build logs, image layers, or compromised personal laptops.

ADC using the metadata server or federation obtains short-lived tokens without distributing private keys to individual workloads. This shrinks the attack surface and simplifies identity rotation.

### Watch Out for High-Precedence Environment Variables

`GOOGLE_APPLICATION_CREDENTIALS` is useful in specialized environments, yet it is also a common reason runtimes accidentally use the wrong credentials. Before deploying, inspect images, manifests, Helm values, Cloud Run environment variables, and Spring configs to ensure the runtime identity is not unintentionally overridden.

## 14. Diagnosing ADC Errors in Java

Approach troubleshooting in order from identity source to resource permissions.

| Symptom | Common cause | Resolution |
|---|---|---|
| "Your default credentials were not found" | Local ADC not created, or no metadata server | Run local ADC login or check runtime identity |
| Java uses the wrong account | `GOOGLE_APPLICATION_CREDENTIALS` points to another file | Check env vars and actual credential source |
| CLI works, Java fails | CLI login and ADC login are separate | Create local ADC via `gcloud auth application-default login` |
| HTTP 401 | Missing, expired, or invalid token | Check credential source, refresh, and metadata server |
| HTTP 403 | Missing IAM, scope, or API/quota permission | Read permission/API in the error and grant the exact role |
| "insufficient authentication scopes" | Compute Engine VM scope missing | Check VM scopes and IAM |
| Local ADC reports quota project error | Missing quota project or `serviceusage.services.use` | Set quota project and grant appropriate permission |
| GKE Pod receives no credentials | Wrong KSA, WIF disabled, or metadata server unavailable | Check KSA, node pool, and IAM principal |
| Cloud Run uses wrong principal | Wrong attached service account or credential override | Check service identity and environment |
| Resource 404 | Wrong project, bucket, or resource name | Verify resource ID and target project |

### Controlled Verification Sequence

1. Confirm whether the program runs locally, on Cloud Run, GKE, Compute Engine, or outside GCP.
2. Check whether `GOOGLE_APPLICATION_CREDENTIALS` is set without printing file contents.
3. If local, confirm ADC was created with the application-default login command.
4. If on a GCP runtime, verify the attached service account or KSA and metadata server.
5. Verify the project, quota project, and API enablement.
6. Identify the actual principal in audit logs or workload configuration.
7. Check IAM on the target resource and scopes if required by the platform.
8. Execute a safe read request to confirm after updating configuration.

Do not print access tokens or full credential objects while debugging. You may log the credential class type, non-sensitive project ID, and a trace/correlation ID in accordance with organizational policy.

### Quota Project Errors

For local user ADC, some libraries require a configured quota project:

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

If the command is rejected, the user needs `serviceusage.services.use` on the quota project or must use an organization-approved project. Setting a quota project does not grant permission to read resources in the target project.

### 403 Errors on Cloud Run

If `orders-api` receives 403 when reading a bucket:

- Check which service account is attached to the service.
- Check whether `GOOGLE_APPLICATION_CREDENTIALS` is overriding the identity.
- Check whether bucket IAM grants `storage.objects.get` to that principal.
- Verify the actual bucket/project/object names.
- Check organization policies or VPC Service Controls if present.
- Inspect the API response and Cloud Audit Logs when available.

Never resolve this by granting Owner to the Cloud Run runtime service account.

## 15. Practical Scenario: One Java App Running in Three Environments

Suppose the `orders-api` team needs to read `healthcheck.txt` in bucket `orders-assets-lab` and publish events to a Pub/Sub topic. The same Java code must run on a developer laptop, Cloud Run, and GKE.

### Environment A — Local Development

1. Developer creates local ADC via `gcloud auth application-default login`.
2. Sets the quota project and target project.
3. When testing exact workload permissions, uses impersonation with a dev service account.
4. Runs `AdcStorageCheck` against the lab bucket and object.
5. Confirms the read succeeds without embedding credentials in source code.

### Environment B — Cloud Run

1. Creates a dedicated runtime service account `orders-api-runtime`.
2. Grants read access on the lab bucket and publish access on the specific topic.
3. Attaches the service account to the Cloud Run service.
4. Mounts no JSON keys and sets no env var pointing to a key.
5. Deploys the image and runs integration tests.
6. Checks Cloud Logging and Cloud Audit Logs to verify calls.

### Environment C — GKE

1. Enables or verifies Workload Identity Federation for GKE.
2. Creates KSA `orders-api` in namespace `orders`.
3. Grants IAM permissions on the bucket/topic to the KSA principal or maps KSA to an IAM service account if needed.
4. Configures `serviceAccountName` in the Deployment.
5. Deploys the same image and runs integration tests.
6. Inspects logs, IAM permissions, and metadata server behavior.

### Outcome Comparison

| Factor | Workstation | Cloud Run | GKE |
|---|---|---|---|
| Credential source | Local ADC or impersonated ADC | Metadata server and runtime service account | GKE metadata server and workload identity |
| Long-lived JSON key needed? | No | No | No |
| Bucket access granted to | User or dev service account | Runtime service account | KSA principal or linked IAM service account |
| Java code | Unchanged | Unchanged | Unchanged |
| What to verify | Quota project and dev principal | Service identity attached properly | KSA, node/pool, and WIF configured properly |

The success criterion is that all three environments run the same business logic while each environment keeps its own identity, IAM, and data boundary.

## 16. ADC Implementation Checklist for Java

### Local Development

- [ ] Google Cloud CLI installed and authenticated via `gcloud auth application-default login`.
- [ ] Appropriate project and quota project selected.
- [ ] Verified local ADC is not overridden by an unintended file.
- [ ] Impersonation used when testing exact service account permissions.
- [ ] ADC files and service account keys are never committed.
- [ ] Lab project/resources available for integration testing.

### Java and Spring Boot

- [ ] Client libraries use ADC instead of hardcoded key paths.
- [ ] Project ID is explicitly specified where needed.
- [ ] Tokens and secrets are never printed in logs.
- [ ] Unit tests mock clients and do not depend on real ADC.
- [ ] Spring auto-configuration does not create duplicate beans or pick unintended credentials.
- [ ] 401, 403, and 404 errors are handled separately according to cause.

### GCP Runtimes

- [ ] Cloud Run/Compute Engine uses a dedicated, appropriately scoped service account.
- [ ] GKE uses Workload Identity Federation for GKE and the correct KSA.
- [ ] Least-privilege IAM is granted at the resource level.
- [ ] Compute Engine access scopes are appropriate.
- [ ] Metadata server and Google APIs are reachable from the runtime.
- [ ] No service account private keys are placed in images or manifests.

### Operations and Security

- [ ] Service account and impersonation permissions are reviewed periodically.
- [ ] Identities are separated across dev, staging, and production.
- [ ] Quota/billing projects are managed according to policy.
- [ ] Audit logs and authentication errors are monitored.
- [ ] WIF is preferred for CI/CD outside GCP.
- [ ] Procedures exist for credential revocation or IAM permission changes.

ADC is a foundational authentication mechanism for Java on Google Cloud because it allows the same client libraries to run across environments without packaging private keys inside the application. When teams combine ADC with proper service identities, least-privilege IAM, quota project configuration, and runtime checks, developing, deploying, and operating Java or Spring Boot applications becomes more consistent and secure.
