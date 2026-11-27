# Secret Manager Secrets, Versions, and Access Policies

Secret Manager is a Google Cloud service for storing and controlling sensitive information that applications need at runtime, such as database passwords, API keys, tokens, certificates, and credentials for external services. The service helps separate sensitive data from source code, container images, and configuration files deployed with the application.

To use Secret Manager safely, you must understand three tightly coupled elements: a **secret** is the management resource containing metadata; a **secret version** stores the actual secret value; and an **IAM policy** determines which identities can view metadata, add versions, or read payloads. A sound deployment workflow must also manage version lifecycles, roll out changes in a controlled manner, and record access activity.

After this lesson, you will be able to:

- Distinguish a secret from a secret version and explain why a version's value cannot be edited in place.
- Create a secret, add versions, read a specific version, and use version aliases.
- Design least-privilege IAM policies for users and service accounts.
- Organize rotation, rollback, disabling, and destruction of versions safely.
- Connect a Java application on Google Cloud to Secret Manager using Application Default Credentials.

## 1. What Problem Does Secret Manager Solve?

An application typically needs values such as:

- Passwords to connect to PostgreSQL or MySQL.
- API keys for payment gateways, email services, or partner systems.
- Access tokens and refresh tokens for an external service.
- Private keys or certificate contents that the application must read at startup.
- Connection strings containing credentials.

If these values are placed directly in source code, `.env` files, Docker images, or broadly shared configuration variables, they can leak through Git, build logs, artifacts, backups, or improper access permissions. When a credential is compromised, changing the value also often requires modifying configurations and redeploying the application.

Secret Manager provides a centralized repository with encryption, IAM, versioning, and audit logging. Applications authenticate using the workload's Google Cloud identity and call the API to fetch the exact secret needed. Operators can grant permissions per secret and change values by adding new versions.

### How do Secret Manager and Cloud KMS differ?

The two services are often used together but solve two different problems:

| Service | Primary Role | Examples |
|---|---|---|
| Secret Manager | Stores and distributes sensitive data to applications | Database passwords, API tokens, private keys stored as data |
| Cloud Key Management Service (Cloud KMS) | Manages encryption keys and performs cryptographic operations | Creating, rotating, granting permissions, and using keys to encrypt/decrypt data |

Secret Manager encrypts sensitive data in transit and at rest. If an organization needs customer-managed key control, secrets can use Customer-Managed Encryption Keys (CMEK) from Cloud KMS. Using CMEK does not turn Secret Manager into an application key management service: payloads are still stored and accessed through Secret Manager.

## 2. Resource Model: Secret and Secret Version

A secret is a resource containing metadata and a collection of versions. Metadata can include name, labels, annotations, replication configuration, rotation details, and IAM policy. The actual payload resides in each version.

~~~mermaid
flowchart TB
    P["Google Cloud project"] --> S["Secret: orders-db-password"]
    S --> M["Metadata, labels, replication, IAM"]
    S --> V1["Version 1: immutable payload"]
    S --> V2["Version 2: immutable payload"]
    S --> V3["Version 3: immutable payload"]
    W["Application / service account"] -->|IAM allows| S
    W -->|AccessSecretVersion(version 3)| V3
~~~

For example, a secret named orders-db-password might contain:

- Version 1: initial password.
- Version 2: password updated during the first rotation.
- Version 3: password currently used by the production workload.

When a password changes, Secret Manager creates a new version. Older versions remain until disabled or destroyed according to lifecycle policy. Because a version's payload is immutable, you can determine exactly which value a workload read and roll back to a previous version if needed.

The resource name of a secret version in the global service has the form:

~~~text
projects/PROJECT_ID/secrets/SECRET_ID/versions/VERSION_ID
~~~

For example:

~~~text
projects/acme-prod-123/secrets/orders-db-password/versions/3
~~~

Secret Manager also offers a regional service with paths containing locations/LOCATION. Choose the resource type based on data residency requirements and deployment scope; most examples in this lesson use the default global service.

## 3. Creating a Secret and Adding Versions

### 3.1. Preparing the project and API

First, select the right project and enable the Secret Manager API:

~~~bash
gcloud config set project acme-prod-123
gcloud services enable secretmanager.googleapis.com
~~~

The user creating the secret needs appropriate administrative permissions, typically roles/secretmanager.admin or a custom role containing the required permissions.

Separate projects by environment, such as acme-dev, acme-staging, and acme-prod. This organization reduces the risk of a project-level binding accidentally allowing a test application to read production secrets.

### 3.2. Creating the secret

Create a secret with automatic replication:

~~~bash
gcloud secrets create orders-db-password --replication-policy="automatic" --labels="app=orders,environment=production"
~~~

This command creates the secret resource and metadata. If no initial payload is supplied, the secret does not yet have a version for applications to access. You can add a version afterward.

Secret Manager supports two common replication policies for the global service:

- **Automatic replication**: Google Cloud chooses appropriate replica locations. This is typically the simplest choice when workloads have no specific location constraints.
- **User-managed replication**: you specify the regions where replicas should be stored. This allows location control but requires accounting for per-location costs.

If regulatory compliance requires data residency, evaluate regional secrets and organizational location policies rather than relying solely on workload region names.

### 3.3. Adding a version from a file

Place the payload in a permission-protected file on an administrative machine or within a secure release workflow. Then add the version:

~~~bash
gcloud secrets versions add orders-db-password --data-file="./db-password.txt"
~~~

Secret Manager returns the new version ID. Record this ID in the release configuration or deployment management system.

Avoid passing secret values directly on the command line like this:

~~~bash
echo -n "my-real-password" | gcloud secrets versions add orders-db-password --data-file=-
~~~

Passing values directly can expose them in shell history or process listings. Input files must also be protected, deleted according to an appropriate procedure, and never committed to Git or included in build artifacts.

**Important principle:** every time a value changes, add a new version. Do not design workflows around modifying the payload of an old version.

## 4. Lifecycle and Referencing Secret Versions

### 4.1. Three version states

A secret version is in one of three states:

| State | Can read payload? | Does payload still exist? | Can be recovered? |
|---|---:|---:|---:|
| Enabled | Yes, if IAM allows | Yes | No recovery needed |
| Disabled | No | Yes | Can be re-enabled |
| Destroyed | No | No, data has been purged | No |

New versions are created in the Enabled state. When you disable a version, applications cannot read its payload, but the data remains and can be re-enabled. When destroyed, the payload is permanently purged; this operation cannot be undone once completed.

Enabled and Disabled versions still incur storage charges under service terms; Destroyed versions no longer have payloads to incur storage fees. Therefore, maintain a clear version retention and cleanup policy.

### 4.2. Accessing by version ID

To read version 3:

~~~bash
gcloud secrets versions access 3 --secret="orders-db-password"
~~~

You can use latest to read the newest version:

~~~bash
gcloud secrets versions access latest --secret="orders-db-password"
~~~

latest is convenient in testing, but use caution in production. When a new version is added, workloads using latest may receive the new value immediately on their next read. If the new value is wrong or not yet accepted by the external system, multiple instances may fail simultaneously.

For production deployments, pin configurations to a specific version ID, such as version 3. When releasing version 4, verify the new value and then update the deployment configuration following your existing release process. This makes every deployment reproducible and rollback unambiguous.

### 4.3. Using version aliases

Secret Manager allows assigning user-defined aliases to a version. For example, assign the stable alias to version 3:

~~~bash
gcloud secrets update orders-db-password --update-version-aliases=stable=3
~~~

Read the payload through the alias:

~~~bash
gcloud secrets versions access stable --secret="orders-db-password"
~~~

Aliases make configurations easier to read, but an alias is a mutable mapping. If stable is moved from version 3 to version 4, an application reading the alias on the next request receives version 4. Therefore, control who is allowed to modify aliases and when changes happen.

Custom alias names must start with a letter, be at most 63 characters long, and may contain letters, digits, hyphens, or underscores. Do not use latest or new as custom alias names because those are reserved names. A secret can have multiple aliases, but names should clearly reflect their purpose.

A safe release process can use aliases for testing or promotion stages, then write the explicit version ID into production configuration. Do not let changing an alias become an unreviewed action that impacts an entire workload.

## 5. Designing IAM Access Policies

Secret Manager uses Identity and Access Management (IAM) to determine which principal can perform which operation. A principal can be a user, Google Group, or service account. An IAM role is a collection of permissions; when a role is granted to a principal on a resource, the principal receives the corresponding permissions across that scope.

### 5.1. Common roles

| IAM role | Purpose | Can read payload? |
|---|---|---:|
| roles/secretmanager.secretAccessor | Read the payload of a secret version | Yes |
| roles/secretmanager.viewer | View metadata and secret/version listings | No |
| roles/secretmanager.secretVersionAdder | Add a version to an existing secret | No |
| roles/secretmanager.secretVersionManager | Add, enable, disable, and destroy versions | No |
| roles/secretmanager.admin | Administer Secret Manager, including managing policies and versions | Yes |

Pay attention to the distinction between viewing metadata and reading payloads. An operations engineer may need to know that a secret exists, its version states, and when it was updated without needing to see the actual password. In that case, Viewer suits the need better than Accessor.

Similarly, a CI/CD pipeline that only needs to add versions can use Secret Version Adder. If the pipeline must also disable or destroy versions, evaluate Secret Version Manager. Avoid granting Admin to every workload simply to simplify configuration.

### 5.2. Granting permissions at the narrowest scope

IAM roles can be granted at the secret, project, folder, or organization level. The higher the scope, the more resources the permissions cover:

| Where roles/secretmanager.secretAccessor is granted | Scope of payloads the principal can read |
|---|---|
| A single secret | Only that secret |
| Project | All secrets in the project |
| Folder | Secrets across projects in the folder |
| Organization | Secrets across projects in the organization |

If a service account only needs the Orders service password, grant Accessor directly on the orders-db-password secret. Do not grant read access to the entire project when a workload only needs a single value.

For example, granting permissions to the service account running the Orders application:

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password --member="serviceAccount:orders-runtime@acme-prod-123.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
~~~

IAM roles are granted on the secret, not individually on each secret version. When a principal has Accessor on a secret, that permission applies to the payloads of versions belonging to the secret under the active policy.

### 5.3. IAM Conditions and identity controls

IAM Conditions allow restricting permissions based on resource attributes or time. Suitable scenarios include:

- Granting temporary access up to a specified timestamp.
- Allowing a principal to act only on secrets matching a specific name prefix.
- Limiting a set of permissions to the required resources or scope.

In environments with multiple application teams, combine separate projects, secret-level bindings, and IAM Conditions to reduce blast radius if a service account or human account is compromised.

Beyond IAM, organizations can use VPC Service Controls to establish an API security perimeter and organization policies to restrict the domains of principals allowed in IAM policies. These are complementary control layers and do not replace designing least-privilege roles.

### 5.4. Using the workload's service account

Applications running on Google Cloud should authenticate using the workload's own runtime identity via Application Default Credentials (ADC). For example:

- Cloud Run uses the service account attached to the service.
- Compute Engine uses the VM's service account.
- GKE can use Workload Identity to map Kubernetes workloads to a Google service account.

This approach avoids creating and distributing service account key files. If an application runs outside Google Cloud, consider Workload Identity Federation to leverage identities from your existing provider.

For workloads on Compute Engine or GKE, check the VM/node OAuth access scopes; the Secret Manager API requires the cloud-platform scope. Having the right IAM role without the necessary scope can still cause API calls to fail.

## 6. Reading Secrets in a Java Application

Java applications can use the Google Cloud Secret Manager client library. The client library uses ADC to locate credentials; in production, attach a service account with Accessor permission on the exact secret.

The library dependency uses the google-cloud-secretmanager artifact. Manage library versions using the Google Cloud Libraries BOM in Gradle or Maven projects.

Example reading a specific version:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DatabaseSecretLoader {
    public String loadPassword(
            String projectId,
            String secretId,
            String versionId) throws Exception {

        SecretVersionName versionName =
                SecretVersionName.of(projectId, secretId, versionId);

        try (SecretManagerServiceClient client =
                     SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                    client.accessSecretVersion(versionName);

            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

Here, versionId is a specific version ID such as 3. To test with the latest version, you can use the string latest, but production should receive the version ID from a verified release configuration.

In a real application, handle scenarios such as the API not being enabled, missing principal permissions, nonexistent versions, or Disabled/Destroyed versions. Never log payloads in application logs, exception messages, tracing attributes, or metric labels. Minimize the duration values are kept in memory and pass them only to the component that actually needs them.

Prefer calling the Secret Manager API directly from the application. If a product integration requires mounting a secret as a file or injecting it as an environment variable, carefully evaluate filesystem read permissions and potential exposure via debug endpoints, crash dumps, and process logs.

## 7. Rotation: Changing Secrets Without Service Disruption

Rotation is the process of changing credentials periodically or when signs of compromise appear. Secret Manager supports rotation schedules and sends notifications via Pub/Sub. **Rotation notifications do not automatically change passwords in external databases or APIs.** A subscriber or rotation worker must execute the update steps on the target system, add a new version to Secret Manager, and coordinate application deployment.

Overview flow:

~~~mermaid
sequenceDiagram
    participant SM as Secret Manager
    participant PS as Pub/Sub
    participant RW as Cloud Run rotation worker
    participant DB as External database or API
    participant APP as Application

    SM->>PS: SECRET_ROTATE notification
    PS->>RW: Deliver rotation event
    RW->>DB: Create or activate new credential
    DB-->>RW: Return new credential
    RW->>SM: Add new secret version
    RW-->>APP: Trigger release/deploy workflow
    APP->>SM: Read approved version ID
    APP->>DB: Connect with new credential
    RW->>DB: Revoke old credential after verification
~~~

A rotation workflow should include:

1. Receive the notification from Pub/Sub and identify the secret needing rotation.
2. Create a new credential in the external system. If possible, keep the old credential valid during the transition period.
3. Add the new credential as a secret version. Record the created version ID.
4. Test the new credential via a health check or safe authentication test.
5. Roll out configuration so workloads use the new version ID. This can be deployed progressively across instance groups.
6. Monitor connection errors and recovery capability. If errors occur, roll back configuration to the known-good version.
7. Only revoke the old credential after workloads have switched over and no longer depend on the old value.

There are three common ways workloads retrieve a version:

- **Resolve during the release process**: the pipeline identifies the new version, writes the version ID into the deployment configuration, and deploys the application. This is the easiest way to control rollout and rollback.
- **Resolve at application startup**: each instance reads the latest version when starting. This is simpler for pipelines, but newly started instances might pick up a faulty version.
- **Resolve continuously**: the application continually polls for new versions. This can cause all instances to switch credentials nearly simultaneously, so it must be controlled very carefully.

For production, selecting a specific version ID during the release process usually produces the most predictable behavior. Design for forward compatibility: the target system should accept both old and new credentials during the rollout window.

## 8. Encryption, Replication, and Auditing

### 8.1. Data encryption

Secret Manager encrypts data in transit with TLS and encrypts data at rest by default. If customer-managed key control is required, CMEK from Cloud KMS can be configured for eligible secrets.

When using CMEK, you must also manage the Cloud KMS key lifecycle. Disabling or deleting a key version needed for decryption can make the secret inaccessible. The key location must also match the location of encrypted replicas. Verify this requirement before modifying key rotation or key states.

### 8.2. Replication and data residency

With global Secret Manager, automatic replication is a suitable default for many workloads. User-managed replication is helpful when specific locations must be designated. If the organization must store data within a specific geographic region, evaluate regional Secret Manager together with organizational location constraints.

Replication increases the availability of secret data, but does not replace backups, credential recovery procedures on target systems, or controls over who is allowed to read secrets.

### 8.3. Audit logs

Enable Data Access audit logs to record payload access operations, especially AccessSecretVersion. This can be configured at the folder or organization level so logging policies apply consistently across multiple projects.

When investigating an incident, determine:

- Which principal called the API.
- Which secret/version was accessed.
- Timestamp and caller origin.
- Whether the activity aligns with a deployment or rotation schedule.

Do not place secret payloads in application logs. Audit logs help trace identities and actions, while application logs should record only necessary metadata such as secret name, version ID, success/failure status, and correlation ID.

## 9. Disabling, Destroying, and Protecting Against Accidental Actions

Before destroying a version, consider disabling it first. A Disabled version cannot be read, yet can still be re-enabled. Keeping a version in the Disabled state for a period helps detect older workloads or jobs that still depend on it.

Destroy is an operation that permanently removes the payload. When an extra layer of protection is needed, Secret Manager supports **delayed destruction**: administrators configure a waiting period from 1 to 1000 days; when destruction is requested, the version is immediately disabled and scheduled for permanent deletion after the waiting period. During the waiting window, administrators can restore the version by enabling or disabling it again. Once the waiting period ends, the payload is irrecoverably destroyed.

Example disabling version 2:

~~~bash
gcloud secrets versions disable 2 --secret="orders-db-password"
~~~

If read access needs to be restored:

~~~bash
gcloud secrets versions enable 2 --secret="orders-db-password"
~~~

Destroy only after confirming no dependencies remain:

~~~bash
gcloud secrets versions destroy 2 --secret="orders-db-password"
~~~

Operational procedures should separate permissions to add versions, permissions to disable/enable/destroy, and permissions to read payloads. Configuring delayed destruction reduces risk from accidental or malicious actions, but does not replace change reviews and notification monitoring.

## 10. Real-World Scenario: Managing Database Passwords for Orders

Suppose the Orders service runs on Cloud Run and connects to a production database. A possible design is:

1. The production project holds the orders-db-password secret.
2. The orders-runtime service account is attached to the Cloud Run service.
3. The secret's own IAM policy grants roles/secretmanager.secretAccessor to orders-runtime.
4. The release pipeline has permission to add versions using an appropriate role, without needing to read older payloads.
5. The Java application reads the version ID passed from the release configuration.
6. A rotation worker receives Pub/Sub notifications, creates a new credential in the database, adds a new version, and triggers deployment through the release process.
7. After confirming instances have switched to the new version, the operations team disables the old version; it is destroyed after the policy-defined retention period.

Example states during a rotation cycle:

| Stage | Version in use | Action |
|---|---|---|
| Before rotation | 3 | Production workload reads version 3 |
| Create new credential | 3 and 4 | Add version 4, verify connectivity |
| Rollout | 4 for new instance group | Update configuration in waves |
| Completion | 4 | Monitor errors and confirm no workload uses version 3 |
| Retirement | 4 | Disable version 3; destroy after waiting period if no dependencies remain |

If version 4 causes errors, the pipeline can redeploy the configuration using version 3 while the old credential remains valid. This is why database rotation must be coordinated with application rollout; merely adding a new version to Secret Manager is not enough to complete rotation.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Remedy |
|---|---|---|
| PERMISSION_DENIED when reading a secret | Service account lacks secretmanager.versions.access or IAM binding is at the wrong scope | Check the workload's actual principal and grant Accessor on the exact secret |
| IAM granted but workload still errors | Workload uses a different service account, lacks OAuth scope, or runs old configuration | Verify ADC, the attached service account, and the cloud-platform scope if using Compute Engine/GKE |
| NOT_FOUND | Wrong project ID, secret ID, or version ID | Check the resource name and project the application is accessing |
| Version unreadable | Version is Disabled or Destroyed | Check version state; re-enable only if payload still exists and is permitted |
| Application connection fails after rotation | Target system credential is out of sync, new version is wrong, or rollout was too fast | Check rotation worker, test the new credential, and roll back to a verified version |
| Sudden spike in API calls | Many instances reading secrets simultaneously during autoscaling or restarts | Evaluate quotas, startup timing, controlled caching strategies, and rate limiting |

When troubleshooting, do not print secret payloads to terminals or logs for a "quick check." Instead, inspect the version ID, state, IAM principal, audit logs, and authentication results against the target system.

## 12. Production Design Checklist

- [ ] Separate production secrets from dev/test environments using dedicated projects or IAM boundaries.
- [ ] Each workload uses a dedicated service account and ADC/Workload Identity.
- [ ] Grant roles/secretmanager.secretAccessor only on secrets the workload actually needs.
- [ ] Separate payload read permissions from version creation, disabling, and destruction permissions.
- [ ] Use explicit version IDs in production release configurations.
- [ ] Maintain a procedure to verify new credentials before rollout and keep old credentials valid during transition.
- [ ] Enable Data Access audit logs for payload read operations.
- [ ] Establish rotation schedules and a subscriber handling Pub/Sub notifications.
- [ ] Disable old versions before destroying; consider delayed destruction.
- [ ] Evaluate replication, regional secrets, CMEK, and VPC Service Controls per security/compliance requirements.
- [ ] Check quotas and behavior when many instances start simultaneously.
- [ ] Never commit, log, or pass plaintext secrets on the command line.

## 13. Self-Check Questions

**1. How do a secret and a secret version differ?**

A secret is the resource managing metadata, policies, and a set of versions. A secret version contains the actual secret payload along with the version's state. When a value changes, add a new version instead of editing an old payload.

**2. Why should Accessor be granted on a single secret rather than at the project level?**

A secret-level binding allows the principal to read only that secret's payload. A project-level binding can grant read access to all secrets in the project, increasing the blast radius if the service account is compromised.

**3. How do Disabled and Destroyed differ?**

Disabled blocks access while the payload still exists and can be re-enabled. Destroyed permanently removes the payload; once complete, it cannot be recovered.

**4. Does a Secret Manager rotation schedule automatically change passwords inside a database?**

No. The rotation schedule emits notifications via Pub/Sub. A subscriber or rotation worker must update credentials in the target system, add a new version, deploy the application, and revoke old credentials after verification.

**5. Why should production pin a specific version ID?**

A specific version ID ensures each release uses a deterministic value that can be tested, tracked, and rolled back. Using latest may cause workloads to pick up an untested new value.

## 14. References

- [Secret Manager overview](https://cloud.google.com/secret-manager/docs/overview)
- [Secret Manager best practices](https://cloud.google.com/secret-manager/docs/best-practices)
- [Access control with IAM](https://cloud.google.com/secret-manager/docs/access-control)
- [Add a secret version](https://cloud.google.com/secret-manager/docs/add-secret-version)
- [Access a secret version](https://cloud.google.com/secret-manager/docs/access-secret-version)
- [Assign an alias to a secret version](https://cloud.google.com/secret-manager/docs/assign-alias-to-secret-version)
- [About rotation schedules](https://cloud.google.com/secret-manager/docs/rotation-recommendations)
- [Delay destruction of secret versions](https://cloud.google.com/secret-manager/docs/delay-destruction-of-secret-versions)
- [Enable customer-managed encryption keys](https://cloud.google.com/secret-manager/docs/cmek)
