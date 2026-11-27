# Application Default Credentials in Development Environments

When writing a Java application that accesses Google Cloud Storage, Cloud SQL, Pub/Sub, or calls Google Cloud APIs, a developer must provide an **identity** to the client library. Having to manually inject access tokens or bundle secret keys into source code for each environment makes the application both hard to deploy and hard to secure. Google Cloud solves this with **Application Default Credentials (ADC)**: a unified mechanism for libraries to locate credentials from the running environment.

This lesson belongs to the **GCP Tools and Development Environment** chapter of the `CLOUD_PROVIDERS_GCP` module. It is a preparatory skill before building applications using IAM, VPC, Compute Engine, GKE, Cloud Run, storage services, and databases. Through an application development scenario, you will configure ADC locally, verify permissions, and understand why the same code can run on both a personal machine and Google Cloud environments.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what ADC is, what it does, and what still must be configured outside ADC.
2. State the exact credential lookup order used by ADC.
3. Set up ADC on a development machine using the Google Cloud CLI without downloading a service account key.
4. Distinguish the identity used by `gcloud` commands from the identity an application uses via ADC.
5. Write a Java application using a client library and ADC to access Google Cloud services.
6. Choose between user credentials, service account impersonation, and federation depending on the scenario.
7. Diagnose common authentication, authorization, project, and quota errors.

## 1. What Is ADC and What Problem Does It Solve?

**Application Default Credentials** is how Google Cloud auth libraries **automatically search for an appropriate credential source** in a defined order. The client library takes the discovered credential, requests or refreshes an access token when needed, and attaches the credentials to requests sent to the service.

For example, instead of a Java application having configuration containing a private key:

~~~java
// Do not write or load private keys into application source code.
// String privateKey = "...";
~~~

we use an SDK that supports ADC:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

When running on a developer's machine, the application can use the credentials of the developer who signed in with `gcloud auth application-default login`. When deployed to Cloud Run, Compute Engine, or GKE with a configured workload identity, the library typically obtains credentials from the Google Cloud environment.

**ADC is not an account type or an IAM role.** It is a **credential-lookup mechanism**. The final identity may be a user, a service account, or a federated identity, depending on the credential source and configuration.

For an API call to succeed, four factors must be kept distinct:

| Factor | Question to Answer | Example |
| --- | --- | --- |
| **Authentication** | Who is the application acting as? | Developer or service account |
| **Authorization** | What is that identity allowed to do? | `roles/storage.objectViewer` on a bucket |
| **Resource project** | Which project owns the accessed resource? | Project containing the bucket to read |
| **Quota/billing project** | Which project is billed or charged for quota per API rules? | Development project configured for user ADC |

**Having valid ADC does not guarantee the application has permissions.** An account can authenticate successfully yet still receive `403 PERMISSION_DENIED` if IAM does not permit access to the resource.

## 2. In What Order Does ADC Search for Credentials?

When a client library needs default credentials, ADC follows this precedence order:

1. **`GOOGLE_APPLICATION_CREDENTIALS` environment variable**: if set, the library reads the credential/configuration file that this variable points to.
2. **Local ADC file in the user configuration directory**: typically created by `gcloud auth application-default login`.
3. **Identity attached to the Google Cloud runtime environment**: for example, a service account attached to Compute Engine or Cloud Run, retrieving tokens via the metadata server; GKE also has its corresponding workload identity mechanism.

~~~mermaid
flowchart TD
    A["App calls Google Cloud client library"] --> B{"GOOGLE_APPLICATION_CREDENTIALS set?"}
    B -->|Yes| C["Read specified credential/config file"]
    B -->|No| D{"Local ADC file exists?"}
    D -->|Yes| E["Read ADC created by gcloud application-default login"]
    D -->|No| F{"Credential source from Google Cloud environment?"}
    F -->|Yes| G["Use workload identity via metadata server"]
    F -->|No| H["ADC not found: raise authentication error"]
    C --> I["Obtain or refresh token"]
    E --> I
    G --> I
    I --> J["Call API; IAM and policies determine effective permissions"]
~~~

**This order is a precedence order, not a security ranking.** If `GOOGLE_APPLICATION_CREDENTIALS` points to a nonexistent or invalid file, the application may fail immediately; do not expect the system to skip it and try the next source.

### 2.1. First Source: `GOOGLE_APPLICATION_CREDENTIALS`

This environment variable holds a **file path**, not an access token and not raw JSON text. Supported files may be:

- A **credential configuration file** for Workload Identity Federation or Workforce Identity Federation.
- A JSON **service account key file**, if the system is forced to use a key. This option should be minimized because keys are long-lived and carry exposure risk.
- Other credential formats supported by the auth library; do not assume every JSON file is a valid ADC credential.

Example path on Linux/macOS:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/home/dev/.config/gcp/dev-credential-config.json"
~~~

In PowerShell:

~~~powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\gcp\dev-credential-config.json"
~~~

Both commands set the variable only for the respective shell session. The file in the example is a legitimately provisioned credential configuration, **not a file you craft by pasting keys into JSON**.

### 2.2. Second Source: Local ADC File

After running:

~~~bash
gcloud auth application-default login
~~~

Google Cloud CLI creates a credential file at the user's default location, typically:

| Operating System | Local ADC File Location |
| --- | --- |
| Linux, macOS | `$HOME/.config/gcloud/application_default_credentials.json` |
| Windows | `%APPDATA%\gcloud\application_default_credentials.json` |

This is a sensitive file because it may contain credentials capable of refreshing access tokens. **Do not put this file into Git, Docker images, build artifacts, shared documents, or logs.**

Note: If `GOOGLE_APPLICATION_CREDENTIALS` is set on the machine, ADC prioritizes the environment variable path over this default ADC file.

### 2.3. Third Source: Identity from the Google Cloud Environment

In deployment environments, a service account can be attached to the workload. The client library contacts Google Cloud's credential-issuing infrastructure to obtain short-lived tokens. The exact mapping differs across Compute Engine, Cloud Run, and GKE Workload Identity Federation.

When deployed properly, Java code using ADC **does not need to change** just because it moves from a developer's laptop to Cloud Run. The important change is configuring the workload's identity and IAM, not copying a local credential file onto the server.

## 3. Setting Up ADC on a Development Machine

Scenario: the Commerce team writes a Java application running on a laptop to read metadata of an object in Cloud Storage. The development environment uses project `atlas-shop-dev`; the bucket is already created. The developer has been granted appropriate object-read permissions by an administrator.

### Step 1: Prepare CLI, Project, and APIs

Install Google Cloud CLI and verify:

~~~bash
gcloud version
~~~

Sign in to the CLI with the appropriate account:

~~~bash
gcloud auth login
gcloud auth list
~~~

Select the project for CLI commands:

~~~bash
gcloud config set project atlas-shop-dev
gcloud config get-value project
~~~

The Project ID is an example only; replace it with the real ID. If the application needs to read Cloud Storage, verify the service/API is enabled and account permissions are satisfied. Enabling APIs, linking billing, or granting IAM are separate steps; ADC does not perform them automatically.

### Step 2: Create User ADC for Local Development

~~~bash
gcloud auth application-default login
~~~

This command usually opens a browser sign-in flow to obtain user credentials for ADC. Once finished, Google Cloud libraries can use the newly created ADC file.

**A very common point of confusion:** `gcloud auth login` and `gcloud auth application-default login` create or use **two different credential sources**. Signing in successfully to the CLI does not mean a Java program already has ADC with the intended identity.

If the browser prompts you to choose an account while running the command, pick the account authorized for the dev environment.

### Step 3: Configure a Quota Project If Needed

With user credentials, some APIs and client libraries require specifying a **quota project**. It can be set with:

~~~bash
gcloud auth application-default set-quota-project atlas-shop-dev
~~~

The account may need the `serviceusage.services.use` permission on the selected project; a commonly used role to grant this is `roles/serviceusage.serviceUsageConsumer`. If the command is denied, ask an administrator for appropriate permissions or select a valid quota project.

Do not confuse these three values:

- `gcloud config set project`: sets the default project for many CLI commands.
- `gcloud auth application-default set-quota-project`: writes the quota project for the active local ADC where applicable.
- Project ID in application code: specifies the resource or request project depending on the API.

The three values may match in a lab exercise, **but they are not inherently the same thing**.

### Step 4: Verify ADC

You can verify token retrieval with:

~~~bash
gcloud auth application-default print-access-token
~~~

**The output is a sensitive access token.** Do not paste tokens into chats, issues, screenshots, logs, or monitoring systems. For a fuller real-world check, run a small API call against dev resources using the SDK as shown in the Java section below.

If `GOOGLE_APPLICATION_CREDENTIALS` was previously set, check which file it points to; it may take precedence over the local ADC you just created.

### Step 5: Verify Actual Identity and Permissions

Separate your checks:

1. **Authentication:** can the SDK find ADC and obtain a token?
2. **Identity:** are credentials coming from the developer, an impersonated service account, or another source?
3. **IAM:** does that identity have the right permissions on the specific bucket/object?
4. **Project:** are you calling the right resource in the dev project?
5. **Quota/API:** is the API enabled and is the quota project valid if required?

`401`, `403`, or `404` errors can stem from different root causes; do not resolve them by granting `roles/owner` to a development account.

## 4. Why Does a Command Work in `gcloud` While Java Errors Out?

The two credential systems serve different purposes:

| Operation | Credential Typically Used | Verification Command |
| --- | --- | --- |
| `gcloud storage ls`, `gcloud projects list`, and similar CLI commands | Logged-in CLI account or CLI-specific impersonation config | `gcloud auth list` |
| Java app via Google Cloud client library | **ADC** following the search order | Run an API call from the app; inspect ADC configuration |
| `gcloud auth application-default login` | Creates/updates local ADC file | `gcloud auth application-default print-access-token` |
| Cloud Run/GCE/GKE workload with configured identity | Workload credential in the runtime environment | Check service account/workload identity and IAM attached to the workload |

For example, you run `gcloud auth login` with `dev-a@example.com`, while `GOOGLE_APPLICATION_CREDENTIALS` still points to a file for service account `old-test@example.iam.gserviceaccount.com`. In that case:

- The CLI calls resources using `dev-a@example.com`.
- The Java application may call resources using the identity from the old configuration file.

Therefore, "CLI works" is useful evidence, **not proof that Java is authenticating with the same identity**.

Also note: CLI commands may carry their own project, impersonation, and quota settings. Do not infer the program's actual credentials solely from the account displayed in `gcloud auth list`.

## 5. Java Example: Reading Cloud Storage Object Metadata with ADC

Suppose you have configured ADC and have permission to read an object in a dev bucket. In Maven/Gradle, add `com.google.cloud:google-cloud-storage` at a version compatible with your project's BOM/libraries; the SDK will locate ADC automatically when creating the service client.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReadObjectMetadata {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                "Usage: ReadObjectMetadata <PROJECT_ID> <BUCKET_NAME> <OBJECT_NAME>"
            );
            System.exit(1);
        }

        String projectId = args[0];
        String bucketName = args[1];
        String objectName = args[2];

        // Storage client library automatically looks up Application Default Credentials.
        Storage storage = StorageOptions.newBuilder()
            .setProjectId(projectId)
            .build()
            .getService();

        Blob blob = storage.get(BlobId.of(bucketName, objectName));

        if (blob == null) {
            System.out.println("Object does not exist or was not found.");
            return;
        }

        // Print metadata; do not print tokens, private keys, or credential JSON.
        System.out.println("Name: " + blob.getName());
        System.out.println("Size: " + blob.getSize());
        System.out.println("Content type: " + blob.getContentType());
    }
}
~~~

**How it works:**

1. `StorageOptions.newBuilder()` creates a Cloud Storage client.
2. Without calling `setCredentials(...)`: the client library uses the default ADC mechanism.
3. `setProjectId(projectId)` explicitly sets the project for the client context; the bucket is still specified via bucket name.
4. `storage.get(...)` sends a call to Cloud Storage using the credentials found by ADC.
5. IAM and service configuration decide whether the operation is allowed.

**Prerequisites:** the object must exist in the bucket, the credential must have the appropriate `storage.objects.get` permission (for instance via `roles/storage.objectViewer` at the required scope), and the environment must have appropriate network/API connectivity. If permissions are missing, the SDK may throw an exception with code `403` instead of returning `null`.

No private key, access token, or user email is hardcoded in the example. When deploying the same code to Cloud Run with a properly configured runtime service account, the SDK still locates credentials via ADC.

### When Do You Need to Call `GoogleCredentials` Directly?

Some situations require building a custom HTTP client or using an SDK without built-in ADC integration. With the Java Auth library, you can obtain credentials:

~~~java
import com.google.auth.oauth2.GoogleCredentials;

GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();
~~~

The library/API may require additional scopes or setup before issuing requests. Obtaining a `GoogleCredentials` object does not prove that identity has permission to access individual resources. When using official Google Cloud client libraries like Storage, Pub/Sub, or the Cloud SQL connector, prefer their built-in ADC integration and avoid managing token lifecycles manually.

## 6. User ADC or Service Account Impersonation?

Signing in to ADC with a developer account is a fast way to test on a laptop, but real applications typically run as a service account. If you want to **test locally closer to the runtime identity** without downloading a service account key, you can use **service account impersonation**.

### 6.1. How Impersonation Works

- The developer signs in with their own account.
- The developer is granted permission to mint tokens on behalf of the service account, typically via `roles/iam.serviceAccountTokenCreator` on the target service account.
- Google Cloud issues a short-lived token representing that service account.
- The API checks resource permissions against the service account's identity, while token issuance depends on the developer's impersonation permission.

~~~mermaid
sequenceDiagram
    participant D as Developer
    participant A as ADC / Auth library
    participant I as IAM Credentials API
    participant S as Google Cloud service
    D->>A: Run Java application
    A->>I: Request token impersonating service account
    I-->>A: Short-lived token when authorized
    A->>S: Send request with service account token
    S-->>A: Result per service account's IAM permissions
~~~

Command for a development environment using Google Cloud CLI:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=app-dev@atlas-shop-dev.iam.gserviceaccount.com
~~~

Java is one of the languages supported by Google Cloud for creating ADC via the CLI with service account impersonation; for other languages or libraries, verify support.

For this to work, you need:

1. Permission to impersonate the target service account; do not self-grant this permission without authorization.
2. The target service account holds the IAM roles needed to call the intended APIs.
3. The IAM Credentials API along with related quotas and service permissions configured properly.
4. The developer's underlying login session remains valid to request short-lived tokens.

Impersonation is helpful for testing application permissions during development; you must still separately evaluate differences in networking, runtime configuration, deployment location, and policies applied in the real environment.

### 6.2. When to Use Workload Identity Federation?

If development tools or CI/CD systems run outside Google Cloud and have a compatible identity provider (IdP), **Workload Identity Federation (WIF)** lets external identities obtain short-lived credentials instead of storing long-lived service account keys. ADC can read a WIF **credential configuration file** via `GOOGLE_APPLICATION_CREDENTIALS`.

Implementing WIF requires administrative trust/federation configuration, an IdP token source, and the necessary roles. Simply pointing the environment variable at a JSON file does not grant access by itself.

| Auth Approach | Best Suited For | Points to Watch |
| --- | --- | --- |
| **User ADC** (`application-default login`) | Developer laptops, labs, and short experiments | User identity; must manage quota project and appropriate permissions |
| **Service account impersonation** | Local development needing to simulate runtime service account permissions | Requires token creation permission and SDK support |
| **Workload Identity Federation** | Workloads/tools outside Google Cloud with an existing IdP | Requires federation config, identity source, and trust setup |
| **Service account attached directly to workload** | Compute Engine, Cloud Run, and many Google Cloud environments | Preferred for runtime; configure IAM for the workload |
| **Service account key file** | Exceptional cases with no safer option | Long-lived key risk; avoid whenever possible |

## 7. Rules for `GOOGLE_APPLICATION_CREDENTIALS`

### Using Within a Single Shell Session

If an earlier step produced a valid credential configuration for federation, you can set the path:

~~~bash
# Linux/macOS
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credential-config.json"

# Inspect the environment variable value
printenv GOOGLE_APPLICATION_CREDENTIALS

# Remove override so applications fall back to default ADC lookup
unset GOOGLE_APPLICATION_CREDENTIALS
~~~

Equivalent in PowerShell:

~~~powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\credential-config.json"
$env:GOOGLE_APPLICATION_CREDENTIALS

# Remove override in the current PowerShell session
Remove-Item Env:GOOGLE_APPLICATION_CREDENTIALS
~~~

Keep configurations separated by environment: a dev setup must never accidentally apply to production.

### Common Configuration Mistakes

- Pointing the variable to a **directory** instead of a valid credential/config **file** path.
- Pointing the variable to an old project's file and forgetting to clear it, causing the app to use the wrong identity.
- Setting the variable in shell A while launching the IDE from environment B, so the Java process does not inherit the variable.
- Assuming `GOOGLE_APPLICATION_CREDENTIALS` is where you enter a **project ID**; in reality, it is a path to credentials.
- Copying `application_default_credentials.json` or a service account key into a source code repo or container image.
- Printing tokens, refresh tokens, or credential file contents into logs while debugging.

**For normal local development, you do not need to set `GOOGLE_APPLICATION_CREDENTIALS` manually just for ADC to work.** `gcloud auth application-default login` already places the file in the default location.

## 8. ADC Across Laptop, IDE, Containers, and GCP Environments

One codebase may run across the following environments:

| Where It Runs | Recommended Credential Source | How to Apply |
| --- | --- | --- |
| Laptop terminal | User ADC or impersonation | `gcloud auth application-default login` |
| IDE (IntelliJ IDEA, VS Code) | Same local ADC if the process can read the file | Check OS user, environment variables, and run configuration |
| Docker container on laptop | Credential/config passed into container via an approved method | Note the container filesystem **does not automatically have** the host's ADC directory |
| Cloud Run | Service account attached to service/revision | Let libraries obtain tokens from the runtime environment |
| Compute Engine | Service account attached to VM, with matching IAM and access scopes | Use metadata server; avoid copying keys onto the VM |
| GKE | Workload Identity Federation for GKE and Kubernetes workload permissions | Do not assume pod identity matches the node identity |
| CI/CD outside Google Cloud | WIF/impersonation when possible | Use short-lived tokens; do not commit long-lived keys |

### Docker: Why Does It "Work on Host, Fail in Container"?

ADC can find the file at `$HOME/.config/gcloud/application_default_credentials.json` on your laptop, but a container has its own filesystem. The same file does not automatically appear inside the container.

In a development environment where user ADC is permitted, one testing approach is to **mount read-only** the ADC file where libraries inside the container can find it, and set the environment variable to point to the path inside the container:

~~~bash
docker run --rm \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/var/run/gcp/adc.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/var/run/gcp/adc.json \
  my-java-dev-image
~~~

This example is for a Linux/macOS host with an existing image and ADC file. On Windows, adjust paths and mount syntax for Docker Desktop. The mounted file holds sensitive credentials; use this only with trusted dev containers. Do not bake credentials into images or carry this pattern into production.

If your organization already provides federation or container tooling that provisions identities automatically, prefer that mechanism instead of sharing personal credentials.

## 9. Common Errors and Diagnostic Workflow

| Symptom | Likely Cause | Diagnostic Step |
| --- | --- | --- |
| `Could not load the default credentials` / `DefaultCredentialsError` | No ADC file/source or variable points to an invalid path | Check `GOOGLE_APPLICATION_CREDENTIALS`; set up local ADC if needed |
| `401 UNAUTHENTICATED`, `invalid_grant` | Credentials expired, revoked, or cannot refresh | Re-login ADC; check system clock and account status |
| `403 PERMISSION_DENIED` | Token present but missing IAM permissions or blocked by deny/policy | Check actual identity, permissions, project/bucket scope, policies |
| `403` related to quota project or `serviceusage.services.use` | User ADC lacks permission to use the quota project | Check `set-quota-project` and IAM on the quota project |
| `API has not been used / is disabled` | Required service/API is not enabled on the corresponding project | Check Service Usage and API enablement permissions |
| CLI succeeds while Java fails | CLI and ADC use different credentials or projects | Compare `gcloud auth list` against ADC source, env vars, and project in code |
| Metadata server lookup error on laptop | No local ADC source; library tried runtime source and failed | Create local ADC or configure valid credentials |
| Works in IDE, fails in Docker | ADC file missing inside container or path differs | Check container filesystem, env vars, and credential provisioning |
| `404 NOT_FOUND` | Wrong bucket/object/project name or nonexistent; some APIs mask missing permissions with 404 | Verify exact resource ID, location, and permissions |
| `429 RESOURCE_EXHAUSTED` | Quota/rate limit exceeded | Check quota project, API limits, and request rate |

### Practical Debugging Sequence

~~~mermaid
flowchart TD
    A["API call fails"] --> B{"Did SDK find ADC?"}
    B -->|No| C["Check env vars, ADC file, and runtime environment"]
    B -->|Yes| D{"Could it obtain a token?"}
    D -->|No| E["Re-login / check impersonation, WIF, refresh"]
    D -->|Yes| F{"Did API return 403?"}
    F -->|Yes| G["Check principal, IAM, policies, API, and quota project"]
    F -->|No| H["Read error code: 404, 429, network, request payload..."]
~~~

Crucial when debugging: **never use access tokens as evidence in logs or issues**. Instead, record timestamp, project ID, target resource, error code, request ID if available, and credential source *by type* (user ADC/impersonation/federation/runtime). Avoid logging token values, refresh tokens, or private keys.

## 10. Protecting Credentials in Development Environments

### Principles to Follow

1. **Never commit credentials**: add appropriate ignore rules, review diffs before committing, and use a secret management mechanism if the app needs dedicated secrets.
2. **Prefer short-lived credentials**: user ADC for local work; impersonation or federation when acting as a service account; workload-attached identities on GCP environments.
3. **Grant least-privilege IAM**: if testing bucket reads, grant only the matching read permission rather than defaulting to Owner/Editor.
4. **Separate dev/prod environments**: use separate projects and identities; never use production credentials for practice labs.
5. **Never expose credentials in logs, screen shares, or screenshots**: both access tokens and ADC files are sensitive.
6. **Restrict permissions on local files**: set file read permissions appropriately for the developer account, and avoid shared folders that auto-sync or expose backups publicly.
7. **Revoke unused credentials**: for ADC created by local login, you can run `gcloud auth application-default revoke`; this affects the associated local ADC session and may require applications to sign in again.

### End-of-Lab Cleanup Routine

~~~bash
# Check local credentials if needed (never share the token)
gcloud auth application-default print-access-token

# Revoke local ADC credentials created by gcloud when no longer needed
gcloud auth application-default revoke
~~~

Revoking credentials does not delete buckets, VMs, or other Google Cloud resources you created. Billable resources and IAM bindings still need to be managed, revoked, or cleaned up through separate procedures.

## 11. Deployment Scenario: From Developer Laptop to Cloud Run

The Commerce team has a Java application that needs to read image file metadata in Cloud Storage. Development workflow:

**On the laptop:**

1. The developer has permission to read the dev bucket in project `atlas-shop-dev`.
2. Use `gcloud auth application-default login` or impersonate the development service account.
3. Run `ReadObjectMetadata` with the dev project ID, bucket, and object.
4. If receiving `403`, check permissions of the **ADC identity**; do not change code to embed keys.

**When deploying to Cloud Run:**

1. Create or select a runtime service account with permission to read authorized resources.
2. Configure the Cloud Run service to use that service account.
3. Deploy the exact same code using the client library and ADC.
4. Configure the appropriate project, bucket, location, networking, and operational observability.
5. Monitor `401/403` errors, request latency, quotas, and costs per project.

The desired outcome is **source code independent of where credentials are provisioned**. However, the deployer remains responsible for choosing the right runtime identity and granting least-privilege IAM.

~~~mermaid
flowchart LR
    A["Java source code"] --> B["Google Cloud client library"]
    B --> C{"Runtime environment"}
    C --> D["Laptop: user ADC / impersonation"]
    C --> E["Cloud Run: runtime service account"]
    D --> F["Cloud Storage API"]
    E --> F
    F --> G["IAM and resource configuration determine the outcome"]
~~~

The same principle applies as you study other parts of the GCP module: programs connecting to Pub/Sub, the Cloud SQL connector, GKE management APIs, or storage services can use ADC through the appropriate SDK. However, access permissions, endpoints, VPC connectivity, region/zone, APIs, and costs must always be configured for each service's needs.

## 12. Self-Check Exercises

**Question 1.** You ran `gcloud auth login` successfully, yet your Java app reports it cannot find default credentials. What could be the cause?

*Suggested answer:* CLI credentials and ADC are two separate sources. You need to configure ADC using `gcloud auth application-default login` or another valid credential source; check `GOOGLE_APPLICATION_CREDENTIALS` if set.

**Question 2.** The machine has a valid local ADC file, but `GOOGLE_APPLICATION_CREDENTIALS` points to a deleted file. Will ADC reliably ignore the error and fall back to the local file?

*Suggested answer:* No. The environment variable has higher precedence; an invalid path can cause the application to fail. Fix or unset that variable.

**Question 3.** A developer successfully obtained an access token, yet the API returns `403 PERMISSION_DENIED`. Did ADC fail?

*Suggested answer:* Not necessarily. ADC may have authenticated successfully, while IAM, a deny policy, quota project, or service policy disallows the request. Read the error message and inspect effective permissions.

**Question 4.** You want to test Java code with the permissions of a Cloud Run service account without downloading a service account key onto your laptop. Which option should you choose?

*Suggested answer:* Use service account impersonation when the account is authorized and the library supports it. Use a long-lived key file only after evaluation when no safer option exists.

**Question 5.** You move a Java app from your laptop to Cloud Run and keep `StorageOptions...getService()` unchanged. What must you do so the app obtains credentials?

*Suggested answer:* Configure the Cloud Run service account and grant appropriate IAM; the client library finds runtime credentials through ADC. Also verify project, bucket, billing/APIs, networking, and operational settings.

**Question 6.** Why does setting `gcloud config set project atlas-shop-dev` not always resolve a user ADC quota project error?

*Suggested answer:* That sets the CLI project, whereas the quota project tied to ADC may need to be set and verified separately with `gcloud auth application-default set-quota-project`.

## 13. Key Takeaways

- ADC is a **credential-lookup mechanism**; it does not grant IAM permissions itself.
- Lookup order: **`GOOGLE_APPLICATION_CREDENTIALS` → local ADC file → Google Cloud environment credentials**.
- `gcloud auth login` is for the CLI; `gcloud auth application-default login` creates credentials that local applications can use.
- During development, prefer user ADC or service account impersonation; avoid long-lived service account keys.
- When running on Google Cloud, prefer a service account or workload-attached identity; do not copy a laptop's ADC.
- Distinguish **identity**, **IAM**, **resource project**, and **quota project** when diagnosing errors.
- Java SDKs can use ADC automatically; configure permissions in Google Cloud instead of embedding tokens in code.

## References

- [How Application Default Credentials works — Google Cloud](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Set up Application Default Credentials for local development](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [gcloud auth application-default login](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login)
- [gcloud auth application-default set-quota-project](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/set-quota-project)
- [Service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation)
- [Authenticate for using client libraries](https://cloud.google.com/docs/authentication/client-libraries)
