# Storing Secrets in Environment-Dedicated Systems

Applications and CI/CD pipelines often need sensitive information to authenticate or access resources: database passwords, API tokens, private keys, certificates, signing keys, and registry credentials. If these values are stored directly in source code, configuration files, or shared pipeline variables, they can easily be copied into logs, artifacts, caches, backups, or unintended environments.

The secure approach is to store secrets in a **dedicated secrets management system (secret manager or vault)**, bind access permissions to workload identities, and inject values only for the specific job or application at the time they are needed. Each environment must have its own secret scope, permissions, and lifecycle processes. This enables teams to control which user or component can read a secret, track usage, rotate credentials, and revoke access during an incident.

## 1. Distinguishing Secrets from Regular Configuration

Not every configuration value is a secret. Data must be classified before choosing where to store it and how to provision it.

| Data Type | Examples | Appropriate Management Approach |
|---|---|---|
| Non-sensitive configuration | Service name, log level, timeout, public feature flag | Configuration files, environment variables, or config store |
| Resource identifiers | Database host, bucket name, region, endpoint | Environment-controlled config store |
| Secrets | Password, API token, private key, signing key | Secret manager or vault |
| Short-lived credentials | Tokens with TTL, temporary database credentials | Dynamic issuance from a secret manager or identity provider |
| Certificates and keys | TLS certificate, private key, encryption key | Key/certificate management system or appropriate secret manager |

An endpoint like `db.internal.example` might not be a secret, whereas the accompanying password is. Avoid bundling everything into one encrypted file and treating the entire file as a single data category. Clear classification helps apply the right read permissions, retention periods, and rotation mechanisms to each type.

A secret can be stored as a single value or as a structured dataset. For example, a database connection secret may contain a username and password; however, avoid storing unnecessary information alongside it. If the host, database name, and port are not sensitive, manage them in separate configuration.

## 2. Why a Dedicated Secrets Management System Is Needed

Storing secrets in repositories or configuration files often creates multiple copies that are hard to track. Even if a file is encrypted or a value is removed in a new commit, the secret may still remain in Git history, forks, clones, logs, and old artifacts.

A secret manager provides a centralized control point with common capabilities:

- Encrypting secrets in transit and at rest.
- Authenticating users, services, or workloads before allowing read access.
- Enforcing access control by secret, namespace, project, or environment.
- Recording audit logs for read, write, rotation, and revocation operations.
- Managing secret versions and states.
- Automatically rotating secrets or issuing time-bound credentials.
- Integrating with KMS/HSM or platform key protection mechanisms.
- Supporting access revocation and incident response.

Common systems include AWS Secrets Manager, Azure Key Vault, Google Secret Manager, and HashiCorp Vault. Some CI/CD platforms also have built-in secret stores. They can be useful for pipeline-only secrets, but they do not always replace a shared secrets management system for workloads running in development, staging, and production.

Establish a single authoritative source of management for each secret. If the same credential is copied into multiple places, rotation and revocation become difficult to synchronize.

## 3. Separating Secrets by Environment

Development, test, staging, and production have different purposes, data, and trust levels. Therefore, credentials must not be shared across environments.

Example identifier structure in a secret manager:

~~~text
/app-name/
  dev/
    database/password
    payment/api-token
  test/
    database/password
    payment/api-token
  staging/
    database/password
    payment/api-token
  production/
    database/password
    payment/api-token
~~~

This is a conceptual organization; a secret manager may use separate projects, vaults, namespaces, folders, paths, or resources. The goal is to ensure that a development workload can only read development secrets and a production job can only read production secrets when authorization conditions are met.

| Environment | Secret Source | Principle |
|---|---|---|
| Development | Individual or development team secrets | Must not contain production credentials |
| Test/CI | Dedicated credentials for tests and mock services | Short-lived permissions, synthetic data |
| Staging | Staging service secrets | Matches near-production configuration while remaining isolated |
| Production | Production vault or secret manager | Least privilege, strict audit and approval |

Never place production secrets in a `.env` file and commit them or share them over chat. A `.env` file can be useful for local development if generated from a secret manager, kept outside Git, and protected with appropriate file permissions; however, it is not a central store.

Secret names can remain consistent across environments while their values and access permissions differ. This allows applications to use the same logical configuration without hardcoding per-environment credentials.

## 4. Separating Secrets by Application and Purpose

Do not grant a single overly broad account to multiple applications just for configuration convenience. If one service is compromised, shared credentials can open a path to other systems.

Each workload should have its own identity and purpose-specific secrets:

- An API service has credentials to read its own database.
- A migration job has the required schema permissions only during the migration window.
- A publish pipeline has write permissions only to the specific registry.
- A deploy job has permissions to update only the target cluster or namespace.
- A monitoring agent has a read-only token for permitted metrics or endpoints.

For example, an application may require three independent sets of permissions:

| Component | Required Permissions | Should Not Be Granted |
|---|---|---|
| Runtime API | Read/write business data in the database | Database administrative permissions |
| Migration job | Modify schema during the deployment window | Access to all databases |
| CI build | Read dependencies and produce artifacts | Production database password |

Separating credentials limits the blast radius when a secret is exposed and helps auditing identify which component used which permission.

## 5. Authenticating with Workload Identity

Secure secret provisioning should not rely on a static password stored in the pipeline to access the secret manager. Whenever possible, let the workload prove its identity using the platform's identity mechanism and receive short-lived access.

Common mechanisms:

- OIDC federation from the CI provider to the cloud provider.
- Workload Identity on Kubernetes or cloud platforms.
- Managed Identity for cloud services.
- Service accounts bound to workloads.
- Certificate-based authentication or equivalent machine authentication mechanisms.

Conceptual access flow:

~~~mermaid
sequenceDiagram
    participant W as CI job or application
    participant I as Identity provider
    participant S as Secret manager
    participant R as Target resource

    W->>I: Request identity token
    I-->>W: Token with issuer, subject, and audience
    W->>S: Authenticate token and request secret
    S->>S: Check policy and permission scope
    S-->>W: Secret or short-lived credential
    W->>R: Connect using issued credential
~~~

The secret manager must verify the issuer, subject, audience, expiration, and relevant claims against its policy. For example, a workflow should only access production secrets when running from an authorized repository, branch, or environment. Do not check only the repository name if any branch or workflow in that repository could request production access.

OIDC avoids storing long-lived cloud access keys in CI. However, an OIDC token is still a time-bound credential and must have its audience, subject, and obtainable permissions restricted.

## 6. Least Privilege and Access Control

A workload should only read the exact secrets it needs, for the duration it needs them. Access control should follow the principle of least privilege.

Define the following:

- **Principal:** which user, service account, runner, or workload requests the secret.
- **Resource:** the secret or group of secrets being accessed.
- **Action:** read, write, create version, rotate, or delete.
- **Condition:** environment, branch, repository, namespace, time, or approval status.
- **Scope:** a specific application, service, or resource.

Example permission matrix:

| Identity | Development Secrets | Staging Secrets | Production Secrets |
|---|---|---|---|
| Local developer | Only assigned dev secrets | Not by default | No |
| CI pull request from fork | No sensitive secrets | No | No |
| CI main branch | Necessary test secrets | Per workflow and policy | Not by default |
| Protected release workflow | Broad access not needed | Allowed for promotion | Only when policy is satisfied |
| Production workload | No | No | Only that workload's secrets |

Do not use secret manager administrative permissions for every job. Permissions to create or delete secrets are typically more sensitive than read permissions. Operators may need management permissions, whereas workloads only need read access to specific secrets.

Periodically review unused identities, stale service accounts, wildcard permissions, and temporary access grants. Revoke permissions when a workload is decommissioned or migrated to a new identity.

## 7. Integrating a Secret Manager with CI/CD Pipelines

Pipelines need credentials to publish artifacts or deploy, but long-lived credentials should not be stored directly in YAML. A sound pattern is for CI to use OIDC or workload identity to authenticate with the secret manager and fetch secrets only when a job needs them.

Conceptual example with GitHub Actions and AWS Secrets Manager:

~~~yaml
name: Deploy staging

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - uses: actions/checkout@v4

      - name: Obtain short-lived AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/ci-staging-deploy
          aws-region: ap-southeast-1

      - name: Fetch secret and deploy
        shell: bash
        run: |
          set +x
          secret="$(aws secretsmanager get-secret-value \
            --secret-id app/staging/deploy-token \
            --query SecretString \
            --output text)"

          echo "::add-mask::$secret"
          DEPLOY_TOKEN="$secret" ./scripts/deploy-staging.sh
~~~

This example illustrates OIDC role federation and secret retrieval. The ARN, role trust policy, region, secret ID, and IAM permissions must be provisioned for the actual environment. The role should only be allowed to read the exact secret required (plus KMS decrypt permission if the secret uses a customer-managed key). The secret is passed directly to the deployment process within the same step rather than written to a shared environment file for subsequent steps. Pin actions according to your organization's security policy; the example uses version tags for readability, while environments requiring strict control may pin commit SHAs.

Do not enable shell tracing when handling secrets. Never print values to stdout, pass secrets in URLs or command-line arguments, or include them in job outputs unnecessarily. The `add-mask` command helps mask values in GitHub Actions logs after registration, but it does not replace preventing secrets from entering logs in the first place.

If a secret can contain newlines or complex data, do not write it directly to an environment file in the simple manner shown above. Use an appropriate data-passing mechanism, a temporary file with restricted permissions, or a dedicated action, and delete temporary data after use.

## 8. Providing Secrets at Runtime to Applications

Secrets needed by a running application should be provided at runtime based on the workload's identity. The pipeline can deploy the application and policies, while the application fetches credentials on startup or when establishing connections.

Common integration approaches:

- Secret manager SDK/API: the application calls the API using workload identity.
- Agent or sidecar: an agent fetches secrets and exposes them via files or a local endpoint.
- CSI driver: mounts secrets into a pod as a volume.
- External Secrets Operator: synchronizes secrets from an external system into a Kubernetes Secret.
- Managed platform integration: the platform injects secrets into runtime per protected configuration.

Each approach has trade-offs. Calling the API directly gives the application fine-grained refresh control, but requires error handling and secure caching. Mounting files lets applications use standard file-reading libraries, but the application must detect when secrets change. Syncing into a Kubernetes Secret is convenient for existing applications, but creates another copy of the secret inside the cluster.

Do not bake secrets into container images or build arguments. Images are commonly stored in registries, cached, and shared across environments. If a credential is present in an image layer, deleting the file in a later layer does not remove the value from earlier layers.

## 9. Storing Secrets Properly in Kubernetes

A Kubernetes Secret is a resource used to supply sensitive data to workloads. However, values in the `data` field are Base64-encoded; **Base64 is not encryption**.

When using Kubernetes Secrets, you should:

- Enable encryption at rest for Secret data in etcd using an appropriate encryption configuration.
- Restrict RBAC so only the required service accounts or groups can read Secrets.
- Limit `list`/`watch` permissions on Secrets because they can expose many values at once.
- Do not grant broad Kubernetes API access to a container just to fetch a single secret.
- Avoid mounting secrets into containers that do not need them.
- Never place Secrets in logs, public manifests, or images.
- Control etcd backups and access to backup data.
- Use an external secret manager when centralized management, rotation, and auditing across multiple clusters are required.

Example of mounting a Secret as a file:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-api
spec:
  serviceAccountName: order-api
  containers:
    - name: app
      image: example/order-api:1.2.0
      volumeMounts:
        - name: database-credentials
          mountPath: /var/run/secrets/database
          readOnly: true
  volumes:
    - name: database-credentials
      secret:
        secretName: order-api-database
        items:
          - key: username
            path: username
          - key: password
            path: password
~~~

This manifest only illustrates how to mount an existing Kubernetes Secret. It does not automatically make the secret secure and does not replace encryption at rest, RBAC, or fetching secrets from a dedicated system. The application should read the files with restricted permissions and avoid printing their contents to logs.

## 10. Lifecycle Management: Creation, Distribution, Rotation, and Revocation

Secrets have their own lifecycle. A provisioned credential should not be treated as permanent until an incident occurs.

A typical lifecycle includes:

1. **Create:** generate credentials using a controlled tool or system, preferring sufficiently strong random values.
2. **Store:** write the secret into the right vault, namespace, or project for the environment.
3. **Authorize:** attach read permissions to the specific workload identity.
4. **Use:** the workload retrieves the secret when needed and does not copy it to other storage locations.
5. **Rotate:** create a new version and transition workloads to the new version.
6. **Verify:** check that workloads operate properly with the new credential.
7. **Revoke:** disable the old credential once consumers have switched over.
8. **Delete:** remove versions or secrets according to retention and audit requirements.

Rotation should be designed to avoid downtime. For a database password, you can create a new credential, update permissions, switch workloads to the new credential, verify connectivity, and then revoke the old credential. If a system allows only one password at a time, establish an appropriate cutover procedure or use temporary credentials.

Do not rotate purely on a schedule without a way to verify that consumers have received the new value. Conversely, do not delay rotation indefinitely out of fear of service disruption. Track secret age, last rotation time, owner, and the list of consumers.

## 11. Preferring Short-Lived Credentials and Dynamic Secrets

Static secrets live long, are easy to copy, and make it hard to track where they are still used. When the platform supports it, use short-lived or dynamically issued credentials.

Examples:

- Time-bound cloud role session credentials.
- Lease-based database usernames/passwords issued by Vault.
- Short-lived API tokens generated through identity federation.
- Short-lived certificates issued by a PKI system.
- Registry tokens scoped to publish a single repository and expiring after the release.

Dynamic secrets typically have the following properties:

| Property | Meaning |
|---|---|
| TTL/lease | Validity duration |
| Scope | Permitted resources and actions |
| Renewal | Conditions for extending validity while the workload still needs it |
| Revocation | How to revoke before expiration |
| Owner/identity | The workload or identity receiving the credential |
| Audit | Issuance and usage trail |

Workloads must handle credential expiration: re-fetching, refreshing connection pools, or re-authenticating. Never assume a short-lived credential will remain valid for the entire lifetime of a process.

## 12. Handling Secrets in Logs, Shells, Artifacts, and Caches

Secrets can leak in many places outside the repository:

- CI logs when shell tracing is enabled or the full environment is printed.
- Error messages containing URLs with usernames/passwords.
- Command-line arguments that appear in process listings.
- Artifacts containing configuration files, dumps, or test reports.
- Caches containing home directories, credential files, or tokens.
- Docker image layers or build caches.
- Screenshots and videos capturing forms or terminal output.
- Crash dumps or heap dumps containing in-memory values.

Practical rules:

- Disable `set -x` or verbose mode when handling secrets.
- Do not use `echo` or debug print statements to inspect secrets.
- Do not pass secrets in URLs, query strings, or command-line arguments.
- Do not cache directories that contain credentials.
- Do not upload sensitive configuration files alongside reports.
- Redact Authorization headers, cookies, and connection strings before storing logs.
- Restrict read permissions on artifacts and logs.
- Use temporary files with minimal permissions when an application requires a file.
- Delete temporary files after the job finishes; remember that deleting a file does not replace revoking a credential if the value was exposed.

Platform masking is only an additional safeguard. It may fail to hide secrets that are transformed, split, encoded, or written in another format. The safest approach is to keep secrets out of logs entirely.

## 13. Auditing and Monitoring Secret Usage

The secret manager must record enough information to answer who accessed which secret, when, and from which identity. Audit logs should typically include:

- Principal or workload identity.
- Secret resource or secret path.
- Action: read, create, update, rotate, disable, or delete.
- Timestamp and success/failure outcome.
- Request source, project, environment, or workload context if provided by the platform.
- Request ID or correlation ID.

Audit logs must never record secret values. Forward logs to a monitoring system with restricted access and appropriate retention. Set up alerts when an identity reads secrets outside normal hours or environments, when a service account reads an unusual number of secrets, or when a production secret is accessed from an unexpected workflow.

Periodic reviews:

- Secrets no longer used by any workload.
- Stale identities that still retain read permissions.
- Secrets that are too old or lack a rotation schedule.
- Unnecessary wildcard or administrative permissions.
- Multiple copies of the same credential across different systems.
- Missing audit logs or logs not forwarded to central storage.

## 14. Responding to Secret Exposure or Secret Manager Unavailability

If secret exposure is suspected, respond in order of priority:

1. Identify the affected credential type, resources, and environments.
2. Revoke or disable the compromised credential.
3. Generate a new credential and provision it to the rightful workloads.
4. Update consumers, verify operation, and remove the old credential.
5. Inspect audit logs to determine the scope of access.
6. Restrict or remove copies containing the secret following procedure.
7. Document the root cause and fix the leak path.

Do not merely delete the secret from the current file. If a credential ever appeared in Git history, logs, or artifacts, treat it as compromised and rotate it. Rewriting history does not replace revoking the credential.

When a secret manager is temporarily unreachable, handling depends on the workload type:

- Workloads with still-valid credentials may continue operating within TTL and policy limits.
- Workloads needing new credentials should retry with limits and report clear errors.
- Do not fall back to hardcoding or using an unmanaged backup credential.
- Release or deployment jobs should block if they cannot verify identity or fetch required secrets.
- Production applications should implement secure in-memory caching and defined expiration behavior aligned with availability requirements.

Do not store secrets permanently in files as a fallback for secret manager outages. Instead, design high availability, backups, replication, and recovery procedures for the secrets management system itself.

## 15. End-to-End Design Example for a Service

Suppose a Java service runs on Kubernetes and a GitHub Actions pipeline deploys to staging and then production.

- Developers run locally using dedicated development credentials obtained from a secret manager or personal login mechanism.
- Pull requests run only lint, unit tests, and integration tests with synthetic data; jobs receive no production secrets.
- Upon merging to a protected branch, the workflow uses OIDC to assume a restricted build/publish role.
- An approved release workflow retrieves staging deploy credentials from the staging secret manager.
- The staging application uses workload identity to read the staging database password and API tokens at runtime.
- Once staging passes quality gates, an authorized approver approves production promotion.
- Production workloads use a dedicated identity to read production secrets.
- Credentials follow a rotation schedule; audit logs are centralized and alert on anomalous access.
- When rotating the database password, the team transitions consumers via an overlap or credential versioning procedure, verifies connectivity, and then revokes the old version.

In this model, the pipeline does not need to know all of the application's secrets. It only has permission to fetch credentials needed for specific job actions; the runtime application fetches its own secrets using its own identity. This separation limits the blast radius if either the pipeline or a single workload is compromised.

## 16. Secure Secret Storage and Usage Checklist

Before introducing secrets into CI/CD or runtime environments, verify:

- [ ] Secrets are stored in a dedicated secret manager or vault.
- [ ] Secrets are absent from source code, public YAML files, images, caches, or artifacts.
- [ ] Development, test, staging, and production use separate secrets.
- [ ] Each workload or job has its own identity and least-privilege permissions.
- [ ] OIDC, workload identity, or short-lived credentials are preferred over long-lived access keys.
- [ ] Policies verify the exact repository, branch, environment, audience, and workload.
- [ ] Secrets are fetched only in the step that needs them and are never printed to logs.
- [ ] The secret manager has encryption, auditing, backups, and access controls enabled.
- [ ] Kubernetes Secrets are protected with encryption at rest and appropriate RBAC if used.
- [ ] Processes exist for rotation, consumer verification, and revocation of old credentials.
- [ ] Expired, ownerless, or unused secrets can be detected.
- [ ] Logs, reports, screenshots, dumps, caches, and artifacts are checked for secret exposure risks.
- [ ] An incident response procedure exists for secret exposure.
- [ ] Appropriate fail-closed behavior is implemented when required secrets cannot be retrieved.
- [ ] Audit logs contain no secret values and trace the accessing identity.

Storing secrets in a dedicated system is only the first step. A secure CI/CD design ties secrets to workload identity, least privilege, environment isolation, lifecycle management, and auditing. When credentials are issued to the right place at the right time and can be revoked, pipelines and applications can access required resources without scattering secrets across source code or build files.
