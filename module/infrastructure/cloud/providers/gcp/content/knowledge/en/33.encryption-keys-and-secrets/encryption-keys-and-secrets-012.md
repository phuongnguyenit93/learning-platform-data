# Hands-On: Removing Keys and Passwords from Java Source Code

In a Java application running on Google Cloud, database passwords, API keys, access tokens, and encryption keys can all be exposed if written directly in source code or configuration files and committed to Git. Once a secret enters Git history, simply deleting that line of code does not make the secret safe again: older copies, other branches, CI/CD logs, and artifacts may still retain the exposed value.

This hands-on lesson belongs to the **CLOUD_PROVIDERS_GCP** module. The module helps learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; while also selecting services, protecting resources, automating releases, and monitoring reliability and cost. Within the scope of this lesson, we focus on removing passwords and credentials from Java source code, storing them in **Secret Manager**, granting access with **IAM**, and using the workload's identity so the application fetches secrets at runtime.

## Objectives

After this lesson, you will be able to:

- Identify which information is a secret and which is merely regular configuration.
- Distinguish the roles of Secret Manager and Cloud Key Management Service (Cloud KMS).
- Create secrets and secret versions on Google Cloud.
- Grant read access to the exact secret for the service account running the application.
- Use the Google Cloud Java client library and Application Default Credentials (ADC) to read secrets.
- Plan rotation, revocation, and verification for exposed secrets.

## 1. Identifying Data to Remove from Source Code

A value needs protection if someone else could use it to log in, call an API, access data, or perform actions on behalf of the application. Common examples include:

| Data | Example | Appropriate Management Approach |
|---|---|---|
| Passwords | Database password | Secret Manager |
| API keys or access tokens | Key for calling a third-party service | Secret Manager |
| Client secrets | OAuth client secret | Secret Manager |
| Private keys or certificates with private keys | Private key used for authentication | Secret Manager or an appropriate identity/certificate management service |
| Data encryption keys | Key used to encrypt or decrypt application data | Cloud KMS |
| Project name, region, secret name | my-project, asia-southeast1, orders-db-password | Application configuration; these values are generally not secrets |

Not every unreadable-looking string is a secret. Conversely, a short string like a password or token can still grant extensive access. Classify by the access capability granted, not by string length or appearance.

### Example of insecure source code

~~~java
public final class DatabaseConfig {
    private static final String DB_URL =
            "jdbc:postgresql://10.20.0.5:5432/orders";
    private static final String DB_USERNAME = "orders_app";
    private static final String DB_PASSWORD = "change-me-in-production";
}
~~~

The password in the example above can end up in Git, build outputs, container images, debug logs, or developers' local source copies. Renaming the variable, Base64-encoding it, or moving the string to another Java class does not solve the problem if the secret value remains inside the artifact or repository.

A committed configuration file carries similar risk:

~~~yaml
database:
  username: orders_app
  password: change-me-in-production
~~~

A configuration file is safe only when it contains no actual secret values. You may commit secret names, project names, or configuration variable names; never commit actual passwords or tokens.

## 2. Choosing the Right Service: Secret Manager or Cloud KMS?

The two services are often mentioned together, yet address two different needs.

**Secret Manager** stores and distributes secret data such as passwords, tokens, API keys, and certificate contents. A secret can have multiple versions; access is controlled via IAM and access activity can be recorded in Cloud Audit Logs. Applications needing to retrieve secret values to connect to databases or call APIs typically use Secret Manager.

**Cloud KMS** manages cryptographic keys and provides cryptographic operations such as encrypting, decrypting, signing, or verifying signatures. Applications typically call Cloud KMS to execute operations using service-managed keys rather than embedding long-lived encryption keys in source code. Cloud KMS can also supply customer-managed encryption keys (CMEK) for supported Google Cloud services.

Selection examples:

- Application needs a password to open a PostgreSQL connection: store the password in Secret Manager.
- Application needs to call a payment API using a token: store the token in Secret Manager.
- Application needs to encrypt business data with a centrally controlled key: use Cloud KMS; for large data, consider the envelope encryption pattern.
- Secret Manager needs to be encrypted with an organization-controlled key: configure CMEK with Cloud KMS if security requirements and service support align.

Do not use Cloud KMS as a password vault that applications repeatedly read back. Nor should you store a long-lived encryption key in Secret Manager and consider that complete key lifecycle management. Choose the service based on the purpose of the data.

## 3. Secret Access Flow on Google Cloud

Applications do not need to bundle a service account key to call Secret Manager. When deploying on Cloud Run, Compute Engine, or GKE, attach an appropriate runtime identity to the workload. The Java client library uses ADC to obtain credentials from the runtime environment.

~~~mermaid
flowchart LR
    A["Java Application<br/>Cloud Run / GKE / Compute Engine"]
    B["Workload service account"]
    C["IAM<br/>secretAccessor on required secret"]
    D["Secret Manager API"]
    E["Secret version"]
    A -->|"ADC"| B
    B -->|"granted permission"| C
    A -->|"reads secret via API"| D
    D --> E
~~~

This flow has three key components:

1. **Workload identity** identifies which application is requesting access.
2. **IAM** determines which secrets that identity is allowed to read.
3. **Secret Manager** returns the requested secret version after checking permissions.

Create dedicated service accounts per application or workload with distinct permission boundaries. Avoid using one service account with permission to read every secret in the project across all services.

## 4. Creating a Secret and Granting Least-Privilege Permissions

The commands below use the Google Cloud CLI. Replace identifiers with your deployment environment's project, secret, and service account. Never pass real passwords directly in commands that could be recorded in shell history.

### Step 1: Select the project and enable the Secret Manager API

~~~bash
export PROJECT_ID="your-project-id"
export SECRET_ID="orders-db-password"
export RUNTIME_SA="orders-api@your-project-id.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

The project ID and secret name are identifiers, not secret contents. Verify you are operating on the right project before creating resources or granting permissions.

### Step 2: Create the secret and add a version

~~~bash
gcloud secrets create "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --replication-policy="automatic"

gcloud secrets versions add "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --data-file="/secure/path/orders-db-password.txt"
~~~

Input files must be created and protected under an organization-approved process; never place the file in a repository, build directory, or publicly synced folder. If secret provisioning uses a pipeline, retrieve the value from the pipeline's secret store and avoid printing values to logs.

A secret can have multiple versions. When changing a password, add a new version rather than editing source code to hold the new password. After the application has switched to the new version and been verified, disable or destroy the old version according to your organization's retention policy.

### Step 3: Grant read access only to the required service account

~~~bash
gcloud secrets add-iam-policy-binding "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

The **roles/secretmanager.secretAccessor** role grants permission to read a secret's payload. Granting the role at the secret level scopes permissions much better than granting the same role across the entire project. Operators who create secrets and manage IAM may need separate administrative permissions; do not grant those permissions to the application's runtime service account if the application only needs to read secrets.

If using Cloud Run, configure this service account as the service's runtime service account. For Compute Engine, attach the appropriate service account to the VM. For GKE, configure Workload Identity Federation for GKE so the Kubernetes workload uses the designated Google Cloud identity. Identity names and attachment mechanisms vary by platform, but the principle remains that the workload receives the right identity and only the permissions it needs.

## 5. Reading Secrets from a Java Application

### Add the dependency

With Maven, add the Google Cloud Secret Manager client library. Projects should manage library versions via the Google Cloud Libraries BOM in **dependencyManagement** so Google Cloud libraries use compatible versions.

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

### Create a secret reader class

The following example creates the client once and reuses it across the application lifecycle. The project, secret ID, and version parameters are identifying configurations; the returned payload is the actual secret content.

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

import java.io.IOException;

public final class SecretReader implements AutoCloseable {
    private final SecretManagerServiceClient client;

    public SecretReader() throws IOException {
        // Client automatically uses Application Default Credentials.
        this.client = SecretManagerServiceClient.create();
    }

    public String read(
            String projectId,
            String secretId,
            String versionId) {
        SecretVersionName versionName =
                SecretVersionName.of(projectId, secretId, versionId);

        AccessSecretVersionResponse response =
                client.accessSecretVersion(versionName);

        return response.getPayload().getData().toStringUtf8();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

**SecretManagerServiceClient.create()** uses ADC. When running on Google Cloud, ADC can obtain the identity from the service account attached to the workload. During local development, developers can set up ADC using an account permitted to access secrets in the development environment:

~~~bash
gcloud auth application-default login
gcloud config set project "$PROJECT_ID"
~~~

Do not download a service account JSON key to your machine just to make the example run. File-based service account keys are long-lived credentials; if copied or committed, anyone with the file can use that identity until the key is revoked. Prefer ADC backed by a managed identity, or Workload Identity Federation when workloads run outside Google Cloud.

### Calling the secret reader during application startup

~~~java
public final class Application {
    public static void main(String[] args) throws Exception {
        String projectId = requiredEnvironmentVariable(
                "GOOGLE_CLOUD_PROJECT");

        // Secret ID and version do not contain secret payloads.
        String secretId = "orders-db-password";
        String versionId = System.getenv()
                .getOrDefault("DB_PASSWORD_SECRET_VERSION", "latest");

        try (SecretReader secrets = new SecretReader()) {
            String databasePassword =
                    secrets.read(projectId, secretId, versionId);

            // Pass the password directly to the connection pool configuration.
            // Do not log the password and do not include it in exception messages.
            startApplication(databasePassword);
        }
    }

    private static String requiredEnvironmentVariable(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required configuration variable: " + name);
        }
        return value;
    }

    private static void startApplication(String databasePassword) {
        // Initialize DataSource/connection pool with a secure configuration.
        // Example abbreviated; do not print databasePassword to logs.
    }
}
~~~

In a real application, pass the secret into the initialization of a **DataSource**, connection pool, or API client. Never pass secrets in URLs, query strings, metric names, trace attributes, or error messages. Observability systems routinely collect those fields and can leak secrets.

**latest** lets the application read the newest enabled version. This is convenient when designing an automatic pickup mechanism, though behavior can vary across restarts. For releases requiring reproducibility, configure a specific version ID and update the deployment configuration alongside the rotation workflow. Either way, never write secret payloads into configuration.

## 6. Error Handling, Caching, and Rotation

Do not call Secret Manager on every database query or every HTTP request. Reading secrets is typically appropriate during startup or when refreshing configuration on a controlled interval. Consider:

- Reusing the client rather than creating one per request.
- Keeping secrets in memory only within the necessary scope; never store them in temporary files or unprotected shared caches.
- Setting cache refresh intervals aligned with rotation requirements and system load.
- When a required secret cannot be read, halting startup or rejecting operations dependent on the secret. Never silently fall back to a default password or hardcoded value.
- Logging only necessary error codes, resource names, or correlation IDs; never logging secret payloads.

A safe rotation workflow can follow this order:

1. Create a new credential in the target system, such as creating a new password for the application account in the database.
2. Add the new payload as a version of the secret.
3. Deploy or refresh the application to read the new version.
4. Verify connectivity and business behavior using the new version.
5. Revoke the old credential at the target system.
6. Disable or destroy the old secret version according to retention policy.

The sequence may need adjustment based on whether the target system supports multiple simultaneous passwords. If the database allows only one password at a time, design a cutover window and recovery plan before proceeding. Do not delete the old version before confirming the application has switched over successfully.

## 7. When an Application Needs Encryption Keys: Use Cloud KMS

Secret Manager suits passwords and tokens that applications must retrieve as values. If the goal is encrypting business data with a centrally managed key, use Cloud KMS to perform cryptographic operations. The following example illustrates encrypting a small payload with a symmetric key in Cloud KMS:

~~~java
import com.google.cloud.kms.v1.CryptoKeyName;
import com.google.cloud.kms.v1.EncryptResponse;
import com.google.cloud.kms.v1.KeyManagementServiceClient;
import com.google.protobuf.ByteString;

import java.io.IOException;

public final class KmsEncryption {
    public byte[] encrypt(
            String projectId,
            String locationId,
            String keyRingId,
            String keyId,
            byte[] plaintext) throws IOException {

        CryptoKeyName keyName = CryptoKeyName.of(
                projectId, locationId, keyRingId, keyId);

        try (KeyManagementServiceClient kms =
                     KeyManagementServiceClient.create()) {
            EncryptResponse response = kms.encrypt(
                    keyName, ByteString.copyFrom(plaintext));
            return response.getCiphertext().toByteArray();
        }
    }
}
~~~

This is a minimal example demonstrating an application sending data to Cloud KMS and receiving ciphertext. In production applications, manage client lifecycles, IAM permissions such as encryption permissions on the CryptoKey, ciphertext storage formats, error handling, and decryption workflows. Never send large data directly through KMS encryption calls; for large data, use envelope encryption: generate a data encryption key (DEK), encrypt the data with the DEK in the application, and then use Cloud KMS to protect the DEK. Store only the ciphertext and wrapped DEK; never store plaintext DEKs in repositories.

The workload's service account should have the right permissions on the CryptoKey needed, such as encrypt/decrypt roles matching actual operations. Permission to access secrets in Secret Manager and permission to use keys in Cloud KMS are separate permissions; grant permissions on the exact resources and with the exact roles.

## 8. Integrating with CI/CD and Deployment Environments

Build and release pipelines can also expose secrets. Check the following points:

- Never pass secret payloads via command-line arguments that may appear in shell history or process listings.
- Never enable debug modes that print all environment variables or sensitive configurations.
- Use short-lived identities or Workload Identity Federation for pipelines accessing Google Cloud; avoid JSON service account keys.
- Grant secret read permissions only to pipeline steps that genuinely need them. Separate build, deploy, and runtime permissions when responsibilities differ.
- Never bundle secrets into JARs, WARs, Docker images, source maps, `.env` files, or release artifacts.
- On Cloud Run or platforms supporting Secret Manager integration, secrets can be configured via environment variables or volumes per application requirements. Assess exposure risks via dumps, process inspection, and logs; expose secrets only to revisions that need them.
- On GKE, consider integrating Secret Manager following an organization-approved pattern and controlling permissions at the workload level.

Environment variables can pass non-secret configuration values such as project IDs, secret IDs, or version IDs. If the platform provides secrets directly via environment variables, understand that processes and diagnostic tools may inspect that environment; avoid dumping the entire environment and consider volumes or direct API access where appropriate.

## 9. Verifying After Migrating Secrets

After updating the application, check both source code and operational processes:

1. Search for field names commonly containing secrets such as password, apiKey, clientSecret, accessToken, and privateKey in Java code and config files. Search matches are leads for review; read context to distinguish variable names from secret values.
2. Run secret scanning tools across repositories and pipelines. Remediate real alerts and configure scanning across appropriate branches and history.
3. Confirm repositories contain only secret names or configuration references, with no payloads remaining.
4. Confirm the runtime service account can read the exact required secret and cannot read secrets outside its granted scope.
5. Inspect application logs, build logs, crash dumps, and traces to ensure no payloads appear.
6. Test rotation in a test environment to verify the application picks up new versions and handles missing-permission errors cleanly.
7. Inspect Cloud Audit Logs to review secret access activity under your organization's monitoring workflow.

If a secret was ever committed or sent to an untrusted location, treat it as compromised. Revoke or rotate the secret at the target system even if the commit was deleted. Rewriting Git history reduces the chance of accidentally redistributing the value, but cannot recall existing clones, forks, caches, logs, or artifacts. Coordinate handling of related copies according to your organization's incident response process.

## 10. Common Anti-Patterns

| Practice | Why It Is Insecure | Remediation |
|---|---|---|
| Putting passwords in static final variables | Values reside in source or bytecode | Read from Secret Manager at runtime |
| Adding .env to .gitignore only after committing | Tracked file remains in Git history | Remove from repository and rotate the secret |
| Base64 encoding or string reversal | Trivially reversible; not access control | Use a secret store and IAM |
| Storing service account JSON keys in repositories | Anyone with the file can use that identity | Use ADC, workload-attached service accounts, or Workload Identity Federation |
| Granting secretAccessor project-wide to all applications | Overly broad secret read scope | Grant permissions per secret and separate service accounts |
| Logging secret values for debugging | Logs may be accessible to many users and systems | Log error codes, resource names, or correlation IDs |
| Deleting secrets from code without rotating | Old values may still be usable from other copies | Revoke or replace secrets at the target system |
| Reading latest without a rollout plan | Restarts may load different versions | Design version, cache, and rollout policies |

## 11. Hands-On Exercise

Suppose a Java application named orders-api connects to PostgreSQL. Currently, the database password resides in a configuration class and the repository already has commit history containing that value.

Perform the following tasks in a test Google Cloud project:

1. Identify the service account that orders-api will use at runtime.
2. Create a secret named orders-db-password, add a version containing a test password, and grant roles/secretmanager.secretAccessor at the secret level to the application's service account.
3. Add the Secret Manager Java client library and implement an ADC-based secret reader class.
4. Replace the hardcoded password configuration with the value read from Secret Manager. Keep the project ID, secret ID, and version ID in non-secret configuration.
5. Run the application with the authorized identity and confirm the connection succeeds.
6. Revoke secret read permission in the test environment, restart the application, and confirm the error is handled explicitly without using a default password.
7. Re-grant permission, add a new secret version, and test the transition workflow.
8. Review the repository, logs, and artifacts to confirm no secret payloads remain.

### Self-Check Questions

**1. Why is removing a password from the latest commit insufficient when the password previously appeared in Git?**

Because commit history, other branches, forks, clones, caches, and artifacts may still retain the old value. You must rotate or revoke the secret at the target system.

**2. Where should a Java application on Cloud Run obtain credentials to call Secret Manager?**

From ADC backed by the service account attached as the runtime identity for the Cloud Run service. The application does not need to embed a service account JSON key.

**3. Which role allows a workload to read a secret's payload?**

roles/secretmanager.secretAccessor. Grant it at the secret level when a workload only needs to read specific secrets.

**4. When should Cloud KMS be used instead of Secret Manager?**

When you need to manage cryptographic keys and perform operations such as encrypting, decrypting, or signing. Passwords and tokens that applications must retrieve as values generally fit Secret Manager.

**5. Should secret contents be written to logs when connection errors occur?**

No. Log non-sensitive diagnostic details such as error codes, resource names, and correlation IDs.

## Conclusion

Removing keys and passwords from Java source code requires a complete workflow: identifying and classifying data, storing secrets in Secret Manager, granting least-privilege permissions with IAM, using workload identities and ADC for access, and then rotating and monitoring. For encryption keys, use Cloud KMS for key lifecycles and cryptographic operations. Once a secret has been exposed, it must be revoked or replaced at the target system; fixing the repository is only part of remediation.
