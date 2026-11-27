# Passing Configuration, Secrets, and Identity into Containers

A container image should hold the application and the dependencies needed to run it, while environment-specific values should be supplied at deployment time. The same image can run in development, staging, and production when endpoints, feature flags, resource limits, and connection details are injected from outside. Passwords, tokens, private keys, and private certificates must be protected as secrets. Applications also need a dedicated identity to call databases, object storage, queues, or other APIs with strictly scoped permissions.

If production configs or credentials are baked into an image, every environment change or secret rotation can force a rebuild. Secrets written into image layers, source repositories, build logs, or inspect outputs can also persist long after the application is updated. Therefore, separate configuration, secrets, and identity cleanly, and pick injection mechanisms suited to the container platform.

This lesson belongs to the **Container Fundamentals** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module explores cloud compute models—from virtual machines and containers to serverless—how to choose CPU, memory, networking, and security settings, and how to deploy applications, scale under load, maintain availability, and optimize operating costs. Within that context, managing configuration, secrets, and identity helps containers run consistently across environments, connect to the right dependencies, and reduce credential-exposure risk.

## 1. Distinguishing Configuration, Secrets, and Identity

### 1.1. Application Configuration

Configuration defines how an application behaves in a given environment. Examples:

- Endpoint addresses for databases, caches, or internal APIs.
- Queue, bucket, or schema names.
- Port the application listens on.
- Feature flags and operating modes.
- Log levels, timeouts, and worker counts.
- Batch sizes, concurrency limits, and retry settings.
- Region, environment, or tenant identifiers.
- Paths to configuration files and public certificates.

Configuration usually does not require secrecy, yet it still requires integrity and change control. A wrong endpoint can route data to the wrong system; an overly verbose log level can inflate costs or inadvertently record sensitive payloads.

### 1.2. Secrets

A secret is sensitive data that unauthorized parties could use to access systems or impersonate an identity. Examples:

- Database passwords.
- API tokens and OAuth client secrets.
- Private keys, signing keys, and certificates paired with private keys.
- Credentials for registries or package repositories.
- Encryption keys and key-encryption keys.
- Third-party service tokens.
- Credentials used during deployment tasks.

Not every config value is a secret. Database names, service hostnames, or ports are usually not secrets, though they may still be internal details you prefer not to publish. Proper classification avoids stuffing everything into a secret store while also preventing credentials from being treated as ordinary environment variables.

### 1.3. Workload Identity

Workload identity defines who a workload is when accessing other resources. It answers "which container is calling this service?" and is used by target systems to authenticate callers and enforce authorization.

Examples:

- An API permitted to read only a specific prefix in a bucket.
- A worker permitted to receive and acknowledge messages from one specific queue.
- A backup job permitted to create snapshots without deleting the vault.
- A deployment container permitted to pull images from a registry without accessing the production database.

Workload identity is typically tied to a service account, task role, managed identity, or platform workload identity mechanism. Prefer short-lived platform-issued credentials over static access keys embedded in images or stored long-term in files.

### 1.4. Authentication and Authorization

- **Authentication:** verifies who the caller or workload is.
- **Authorization:** decides what actions that identity may perform on which resources.

Holding a valid token does not mean a workload should hold administrative rights. After authentication, systems must evaluate policies following the principle of least privilege.

### 1.5. Comparison Table

| Category | Examples | Appropriate Store | Common Injection Method |
|---|---|---|---|
| Non-secret configuration | Port, endpoint, log level | Config file, ConfigMap, deployment config | Environment variable or file mount |
| Secret | DB password, API token | Secret manager, vault, or platform secret store | File mount, volume, secret reference, or env when needed |
| Workload identity | Service account, task role | Identity provider and cloud/cluster control plane | Short-lived token or automatically provisioned credentials |
| Artifacts | Images, packages, public certificates | Registry, artifact repository, PKI | Pull by digest or mount per policy |
| Permission policies | IAM/RBAC policies | Control plane, IaC, and policy repository | Attached to workload identity, never baked into images |

## 2. Design Principles

### 2.1. One Image, Many Environments

An image should be built once and promoted across environments. Environment-specific configuration is injected at deploy time.

For example, the exact same API image can serve:

- Development: test database and test queue.
- Staging: production-like dependencies for validation.
- Production: production endpoints and resources.

Do not build separate images merely to change URLs, log levels, or queue names. Doing so multiplies artifacts and risks running different code across environments.

### 2.2. Never Bake Secrets into Images

Never place secrets in:

- Dockerfiles via `ENV` or `ARG`.
- Source code, committed `.env` files, or startup scripts.
- Image layers created via `COPY`.
- Build logs or command-line arguments.
- Image labels, annotations, or metadata.
- Test fixtures bundled into production images.

Deleting a secret file in a later layer does not purge it from earlier layers. Image history, caches, registries, and older image builds can still retain the contents.

If a secret was ever committed to a repository or baked into an image, treat it as compromised: revoke or rotate the credential, audit access, and purge affected artifacts per policy. Simply removing the line in a newer version does not invalidate the leaked secret.

### 2.3. Supply Configuration at Runtime

Configuration should be supplied by the deployment system, orchestrator, or secret manager. The application reads config on startup and validates values before accepting traffic.

A well-behaved application should:

- Document a schema or list of supported config keys.
- Distinguish required values from optional ones.
- Provide safe defaults for non-sensitive settings.
- Fail fast if a required secret or endpoint is missing.
- Never print secret values in error messages.
- Provide a way to validate config without revealing secret contents.

### 2.4. Prefer Identity Over Static Credentials

When the cloud or orchestrator supports workload identity, bind an identity to the workload to obtain short-lived tokens. Avoid creating long-lived access keys and copying them into every replica.

Static credentials expand the blast radius if an image, log, backup, or developer machine is compromised. Short-lived tokens and least privilege constrain both the exposure window and scope.

### 2.5. Separation of Duties

Separate responsibilities across roles:

- Image builders do not need read access to production secrets.
- Deployment pipelines only receive permissions to supply config for authorized environments.
- Workloads only have access to their required dependencies.
- Operators can trigger rotations without automatically being able to read secret values.
- Backup/recovery identities hold restore privileges under separate procedures.

Separation of duties prevents a compromise in the build pipeline from automatically granting access to production data.

## 3. Passing Configuration via Environment Variables

### 3.1. How It Works

Environment variables are key/value pairs passed to a process when a container starts. Applications read them via runtime APIs or configuration libraries.

Example configuration names:

~~~text
APP_ENV=production
HTTP_PORT=8080
LOG_LEVEL=info
DB_HOST=db.internal
DB_PORT=5432
REQUEST_TIMEOUT_SECONDS=5
~~~

These values illustrate non-secret configuration only. Never use this pattern as-is for database passwords.

Advantages:

- Easy integration across most languages and frameworks.
- Suitable for small, flat values.
- Easily changed per deployment without rebuilding images.
- Integrates cleanly with container orchestrators and CI/CD.

Limitations:

- Child processes can inherit the environment.
- Users with sufficient privileges on the host or control plane can inspect values.
- Environment variables generally do not auto-refresh inside a running process.
- Multi-line values or complex structures are awkward to manage.
- Logs, crash dumps, diagnostic bundles, or inspect commands can accidentally expose values.

Environment variables are not a secret manager. If you must inject a secret via env, restrict metadata inspection permissions, avoid printing the environment, control host/debug access, and prefer file mounts or workload identity where appropriate.

### 3.2. Reading and Validating Config at Startup

Python example illustrating non-secret config loading only:

~~~python
import os

app_env = os.getenv("APP_ENV", "development")
port_value = os.getenv("HTTP_PORT", "8080")
log_level = os.getenv("LOG_LEVEL", "info")

try:
    http_port = int(port_value)
except ValueError as exc:
    raise RuntimeError("HTTP_PORT must be an integer") from exc

if not 1 <= http_port <= 65535:
    raise RuntimeError("HTTP_PORT is outside the valid range")

print(f"Starting service in {app_env} on port {http_port}")
~~~

Never dump the entire environment for debugging. When config is invalid, error messages should cite the variable name and validation rule—never secret values.

### 3.3. Configuration Precedence

Applications can receive configuration from multiple sources:

1. In-app defaults.
2. Default config file inside the image.
3. Mounted config file.
4. Environment variables.
5. Startup flags or control-plane-injected settings.

No single precedence order applies universally across frameworks. Document your application's precedence clearly so operators never face conflicting values across two sources without knowing which wins.

### 3.4. When to Use Env Vars vs. Files

| Scenario | Environment Variable | File Mount |
|---|---|---|
| Ports, log levels, small feature flags | Suitable | Can be used |
| Endpoints or queue names | Suitable | Suitable when many settings exist |
| Multi-line JSON/YAML | Hard to manage | Usually more suitable |
| Private keys or certificate bundles | Not preferred | Usually preferred with explicit file permissions |
| Secrets needing rotation | Requires process restart or custom mechanism | File can update, though app still needs reload |
| Large configs | Unsuitable | More suitable |

File mounts must also be secured. Configure file permissions, directory permissions, read-only mounts, and backing stores properly; never assume secret files are automatically safe simply because they are not in environment variables.

## 4. Passing Configuration and Secrets with Docker

### 4.1. Dockerfile: ENV and ARG

Dockerfiles support two common mechanisms:

- **ARG:** variables scoped to the build process.
- **ENV:** default variables saved in the image and present when containers run.

Non-secret configuration example:

~~~dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV HTTP_PORT=8080
ENV LOG_LEVEL=info

USER 10001:10001
EXPOSE 8080

CMD ["python", "-m", "src.server"]
~~~

`HTTP_PORT` and `LOG_LEVEL` are non-secret defaults that can be overridden at runtime. Never add `DB_PASSWORD`, `API_TOKEN`, or private keys via `ENV`.

`ARG` is also unsafe for passing passwords or tokens. Build arguments can appear in metadata, build history, caches, or logs depending on the builder and usage.

### 4.2. Build Secrets with BuildKit

If a build step must access a private package registry, use BuildKit secret mounts instead of `ARG`/`ENV` or `COPY`ing credentials into the image.

Example:

~~~dockerfile
# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./

RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm ci

COPY . .
RUN npm run build
~~~

A secret mount is exposed only to that `RUN` instruction and is not committed into image layers by the mount mechanism. Still, build scripts could read or print the secret; trust your dependencies, sanitize logs, and never run untrusted build code with sensitive credentials.

Build secrets are for credentials needed during the build. They do not replace runtime secrets needed after the container launches.

Supply the secret file to BuildKit during build, for example:

~~~bash
docker build --secret id=npmrc,src=./secrets/npmrc -t my-api:build .
~~~

Protect the source path and never `COPY` it into the image. Add entries such as these to `.dockerignore` to reduce the risk of leaking local files into the build context:

~~~text
.env
.env.*
secrets/
*.pem
*.key
~~~

### 4.3. Passing Configuration at Runtime

Example passing non-sensitive configuration:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -e APP_ENV=staging \
  -e HTTP_PORT=8080 \
  -e LOG_LEVEL=debug \
  my-api:1.0
~~~

Never pass secrets directly in shell commands or terminal history. Command lines can be captured in shell history, process listings, CI logs, and audit systems.

In test environments, you may use a protected, uncommitted env file. In production, prefer a secret manager, orchestrator secrets, or workload identity over static env files.

### 4.4. Docker Compose

Compose supports declaring environments and file secrets for services. The example below uses a secret file managed outside the repository:

~~~yaml
services:
  api:
    image: registry.example.com/team/api:1.0
    environment:
      APP_ENV: production
      HTTP_PORT: "8080"
      DB_HOST: db.internal
      DB_PORT: "5432"
    secrets:
      - db_password
    read_only: true
    user: "10001:10001"

secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

Inside the container, the secret is mounted at Compose's default path, typically `/run/secrets/db_password`. The application must read that file without printing its contents to logs.

This example does not automatically secure the source file. `./secrets/db_password.txt` must have strict file permissions, stay out of Git and the build context, and be managed via secure secret workflows. Local Docker Compose file secrets also differ from a secret manager or Docker Swarm; verify the actual security guarantees of your platform.

### 4.5. Docker Swarm Secrets

Docker Swarm has a dedicated secrets mechanism for services. Secrets are distributed to nodes authorized to run tasks and mounted inside containers, typically under `/run/secrets`. This avoids passing secrets through environment variables and allows service-level secret lifecycle management.

Distinguish Swarm secrets from local Compose file secrets. Do not assume both share the same control plane, encryption, replication, or access controls. Design around your actual deployment model.

### 4.6. Reducing Exposure Surface on the Docker Host

- Run containers as a non-root user whenever the application allows.
- Never grant Docker socket access to application containers.
- Restrict access to the Docker daemon; daemon control generally equates to very high privileges on the host.
- Avoid inspect commands or debug dumps that print environments containing secrets.
- Never pass secrets on the command line.
- Mount secrets read-only and scope them strictly to services that need them.
- Never copy secret directories into the image build context.
- Use `.dockerignore` to exclude local files and secrets from the build context.

## 5. Kubernetes ConfigMap and Secret

### 5.1. ConfigMap for Non-Secret Configuration

`ConfigMap` stores non-sensitive configuration and can be injected into containers via environment variables or volumes.

Example:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
data:
  APP_ENV: "production"
  HTTP_PORT: "8080"
  LOG_LEVEL: "info"
  DB_HOST: "postgres.database.svc"
~~~

A Deployment can reference the ConfigMap:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: registry.example.com/team/api:1.0
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: api-config
~~~

This example is abbreviated for illustration. Production manifests must add resource requests/limits, probes, security contexts, service accounts, and appropriate deployment policies.

### 5.2. Kubernetes Secrets

Kubernetes `Secret` stores sensitive key/value pairs. Data in YAML manifests is commonly Base64-encoded; Base64 is merely encoding, not encryption.

Structural example containing no real credentials:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-db-credentials
type: Opaque
data:
  username: <BASE64_USERNAME>
  password: <BASE64_PASSWORD>
~~~

Never commit real secrets into manifests or Git simply because values are Base64-encoded. Anyone authorized to read the Secret can decode its contents.

For production, ensure:

- Encryption at rest is enabled for Kubernetes Secrets using a cluster-supported provider.
- RBAC permissions for `get`/`list`/`watch` on Secrets are tightly scoped by namespace and workload.
- Arbitrary Pod creation is restricted in namespaces holding sensitive Secrets.
- Secrets are segregated by application and environment.
- Secret access and modifications are audited.
- External secret managers or CSI drivers are evaluated.
- Backups of etcd/cluster state and their encryption keys are protected.

### 5.3. Injecting Secrets into Environment Variables

You can reference a specific key from a Secret:

~~~yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: api-db-credentials
        key: password
~~~

This is convenient for applications that only read environment variables at startup. Values already injected into a running process's environment typically do not update when the Secret changes. A Pod rollout/restart or custom refresh mechanism is required.

If the application logs its environment, writes crash dumps, or exposes diagnostic endpoints, secrets can leak. Use this approach only after assessing risks and locking down debugging access.

### 5.4. Mounting Secrets as Files

Example:

~~~yaml
volumes:
  - name: db-credentials
    secret:
      secretName: api-db-credentials
      defaultMode: 0440

containers:
  - name: api
    volumeMounts:
      - name: db-credentials
        mountPath: /var/run/secrets/app
        readOnly: true
~~~

This snippet sits inside a Pod spec, where `volumes` and `containers` are sibling fields under `spec`. In a full Deployment, they reside under `spec.template.spec`.

The application can read `/var/run/secrets/app/password`. File mounts avoid putting values in the environment and allow explicit file permissions.

Verify the process UID/GID and file read permissions. Secret volumes update via Kubernetes eventual propagation; the application must reopen or watch the file to load new values. Mounts using `subPath` do not receive automatic Secret updates like standard volume projections. Never assume a changed file means the application has adopted the new secret.

### 5.5. Do Not Expose Secrets to Every Container

Within a Pod, volumes can be mounted selectively only into the containers that need them. Never mount database credentials into a logging or proxy sidecar if they do not require those credentials.

Separate workloads with differing trust levels into distinct Pods or services when needed. One container in a Pod should not be treated as a strong security boundary against another container in the same Pod if they share namespaces, volumes, or access rights.

## 6. Secret Managers and External Secrets

### 6.1. Secret Manager as the Central Source of Truth

A secret manager or vault can provide:

- Encrypted secret storage.
- Identity-based access control.
- Auditing of reads, writes, and rotations.
- Secret versioning.
- Lease expirations or rotation policies.
- Dynamic credentials for certain databases/services.
- Replication or resilience depending on the product.

Containers should not need an administrative password for the secret manager. They should authenticate via workload identity and read only the specific secret or path granted to them.

### 6.2. Two Common Integration Patterns

**Syncing secrets into the orchestrator:** a controller reads the secret manager and creates/updates Kubernetes Secrets. Pods reference the Secrets as usual.

The advantage is simple integration with existing applications. The risk is creating an extra copy of the secret in the Kubernetes API/etcd, requiring protection of both the secret manager and the cluster.

**Direct mounting via CSI or agent:** workloads receive secrets as files through a driver or agent governed by platform policies.

The advantage is reducing secret storage inside Kubernetes Secret objects. However, the driver, node plugin, identity, and connection path to the vault become critical dependencies to secure and test.

Neither pattern is automatically safer in all cases. Evaluate permissions, auditing, caching, rotation, availability, and how secrets are stored on nodes.

### 6.3. Do Not Reuse Build Secrets at Runtime

Build pipelines and runtime workloads have different purposes:

- Builds may need a token to read a package registry.
- Runtime may need credentials to access a database.
- Deployment controllers may need permissions to create resources.
- Workloads only need permissions to call their own dependencies.

Never share a single credential across all four roles. Revoke and rotate each credential independently along its own lifecycle.

## 7. Workload Identity and Cloud Access Permissions

### 7.1. Why Should Access Keys Not Be Embedded in Containers?

A legacy pattern was creating long-lived access keys and placing them in environment variables or config files. Whenever an image or Pod is copied, the credentials get copied too. When multiple workloads share one key, it becomes hard to tell who accessed a resource and hard to revoke a single workload safely.

Workload identity lets the platform identify the Pod/task/instance and issue short-lived credentials or perform token exchange. Applications do not need long-lived private keys inside images.

### 7.2. Identity Issuance Model

General flow:

~~~mermaid
sequenceDiagram
    participant W as Container workload
    participant P as Platform identity
    participant I as Identity provider
    participant S as Cloud service
    W->>P: Request workload identity token
    P->>I: Validate workload identity / exchange token
    I-->>P: Short-lived credential
    P-->>W: Credential scoped to workload
    W->>S: Call API with credential
    S->>S: Authenticate and authorize
    S-->>W: Response if policy allows
~~~

Specific APIs and mechanisms differ by platform—such as service account token projection, task roles, managed identities, or workload identity federation. The common thread is binding identity to the workload and granting permissions via policy.

### 7.3. Kubernetes ServiceAccount

A Pod can run under a Kubernetes `ServiceAccount`. The `ServiceAccount` defines the workload's identity inside the cluster and can be used for RBAC or integration with external identity providers.

Example:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-reader
  namespace: production
automountServiceAccountToken: false
~~~

A Pod referencing the service account:

~~~yaml
spec:
  serviceAccountName: api-reader
  automountServiceAccountToken: false
  containers:
    - name: api
      image: registry.example.com/team/api:1.0
~~~

This example disables automatic token mounting when the application does not need to call the Kubernetes API using the default token. If workload identity federation requires a projected token with a specific audience, configure token projection per platform guidance rather than enabling broad default tokens.

### 7.4. RBAC and IAM

A `ServiceAccount` does not automatically gain access to all resources. Scope permissions strictly to:

- Required namespaces and resource types.
- Minimal verbs: `get`/`list`/`watch`/`create`/`update`/`delete`.
- Specific resource names or label scopes where supported.
- Specific cloud resources such as buckets, queues, or secret paths.
- Conditions tied to environment, cluster, or workload identity.

Avoid granting `cluster-admin`, wildcard permissions, or delete privileges to read-only workloads. Audit both Kubernetes RBAC and cloud IAM policies, as these two systems govern different resource layers.

### 7.5. Short-Lived Tokens and Rotation

Short-lived tokens limit how long a leaked credential remains usable. Applications or SDKs must refresh tokens before expiration and retry safely on authentication errors caused by stale tokens.

Never cache credentials past their lifetime or silently ignore refresh errors. Skewed system clocks can also cause tokens to be rejected as not-yet-valid or expired.

### 7.6. Identities Across Environments

Use separate identities for development, staging, and production. Never let staging workloads assume production roles simply for testing convenience.

If production-permission testing is necessary, use an approval workflow and test accounts with strictly scoped data. Separating accounts/projects/subscriptions or namespaces reduces the chance of lower-environment credentials reaching sensitive resources.

## 8. Permissions Inside Containers

### 8.1. Running Non-Root

Container processes should run under an unprivileged UID/GID whenever root privileges are unnecessary.

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --chown=10001:10001 app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ensure data directories, temporary directories, and certificates have appropriate permissions. Do not switch to root merely to silence permission errors without identifying which files or paths genuinely require write access.

### 8.2. Read-Only Filesystem and Selective Mounts

Make the root filesystem read-only and mount only the directories requiring writes:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
~~~

Place this block inside the container's `securityContext` (`spec.containers[].securityContext`). Provide writable volumes for temporary data if needed. Keep secret volumes read-only. Never enable privileged mode or mount host paths solely to make an app work without understanding the security impact.

### 8.3. UID, GID, and File Permissions

When secrets are mounted into a container, verify:

- Which UID/GID the process runs as.
- File owner/group and mode bits.
- Whether `fsGroup` or an equivalent permission mechanism is needed.
- Whether the container can traverse parent directories.
- Whether sidecars share the same volume mount.
- Whether secrets get copied onto a writable filesystem.

Overly permissive modes like `0777` expand the set of processes that can read secrets. Overly restrictive modes can prevent startup; test with the exact production user.

## 9. Secret Rotation and Revocation

### 9.1. Why Is Rotation Necessary?

Secrets can leak, personnel or vendors change, policies mandate periodic rotation, or credentials expire. Rotation replaces an old secret with a new one and revokes the old value once all consumers have transitioned.

Rotation requires a transition plan. Rotating a database password immediately while some replicas still hold the old password will break requests.

### 9.2. Safe Rotation Workflow

1. Identify the secret, owner, consumers, and blast radius.
2. Generate a new credential or version using the service's mechanism.
3. Authorize workloads to use the new credential.
4. Update the secret manager or orchestrator.
5. Trigger application reload or a controlled rollout.
6. Verify every replica is using the new version.
7. Monitor authentication errors and dependency health.
8. Revoke the old credential only after confirming zero remaining consumers.
9. Record timestamps, versions, and rotation evidence.

For databases supporting only one active password per user at a time, create a second user, transition workloads, and then disable the old user. This prevents a window where replicas fail authentication.

### 9.3. Reloading Secrets in Applications

Environment variables are typically captured at process launch. Updating a Kubernetes Secret does not change the environment of an already running process. A Pod rollout is usually required for processes to pick up new values.

For secrets mounted as files, the platform can update volume contents on its schedule, though the application must reopen the file or watch for changes. Certain mount styles such as `subPath` do not receive automatic updates. Test the exact runtime and CSI driver behavior.

### 9.4. Revocation Upon Suspected Compromise

When a credential shows signs of compromise:

- Revoke or disable the affected credential.
- Issue a new credential through a secure channel.
- Review audit logs to determine usage scope.
- Check related images, registries, repositories, CI logs, and backups.
- Verify running workloads are no longer using the old credential.
- Consider rotating dependent credentials or previously issued tokens.
- Document the incident and update policies.

Do not merely delete the secret from manifests or Git. Git history, image layers, caches, logs, and backups may still contain the old value.

## 10. Managing Configuration During Rollouts and Autoscaling

### 10.1. Replicas Must Receive the Same Desired Configuration

When an autoscaler launches additional containers, new instances must receive the exact same config version, secret references, and workload identity as existing replicas.

Version or checksum your configuration. When config changes, trigger a fresh rollout so all replicas converge to the same state.

Do not let individual containers fetch uncontrolled configs independently or rely on divergent local caches. That creates inconsistent behavior within a single service.

### 10.2. Config Changes and Rollouts

A configuration change can impact an application just like a code deploy:

- Changing an endpoint can shift traffic to a different dependency.
- Changing pool size can overload the database.
- Changing timeouts can tie up request workers longer.
- Toggling a feature flag can activate an untested code path.
- Changing a secret can cause authentication failures on a subset of replicas.

Review, version, test in staging, and roll out via canary or rolling updates. Maintain a clear path to roll back to the previous config version if errors spike.

### 10.3. Do ConfigMap/Secret Updates Restart Pods Automatically?

Kubernetes does not automatically restart Pods simply because a `ConfigMap` or `Secret` is updated. Volume projections may update after a delay, whereas environment variables stay unchanged and applications may not reload files.

A common pattern is adding a checksum or version identifier of the `ConfigMap`/`Secret` to Pod template annotations. When the version changes, the Deployment creates a new ReplicaSet and rolls out Pods. Never put raw secret values into annotations; use only non-sensitive version identifiers or hashes designed not to leak secrets.

### 10.4. Avoiding Config Drift

Useful practices:

- Tie config versions to releases.
- Reference explicit config versions in deployment manifests.
- Roll out in batches while monitoring health.
- Validate configuration on container startup.
- Alert if replicas report differing config versions.
- Automatically roll back if health checks fail.

For secret rotations, version references can update through a dedicated workflow while ensuring old credentials stay valid during the transition window.

## 11. Networking and TLS Configurations Involving Secrets

### 11.1. Certificates and Private Keys

Containers may need certificates to serve HTTPS or authenticate mutual TLS. Public certificates are not necessarily secret, but private keys must be protected.

Best practices:

- Obtain certificates/private keys from a PKI or secret manager.
- Mount them read-only into only the required containers.
- Restrict UID/GID and file permissions.
- Monitor expiration dates.
- Rotate certificates ahead of expiration.
- Never embed private keys into images or repositories.

### 11.2. Trust Stores

A trust store holds CA certificates used to verify peers. Public CAs are generally not secret, yet altering a trust store changes which systems are trusted.

Version-control trust bundles and test updates. Never disable TLS verification to "fix" certificate errors; diagnose the hostname, certificate chain, system clock, and proper CA instead.

### 11.3. Proxies and Endpoints

Proxy URLs, `no_proxy` lists, and endpoints can be non-secret config. Proxy passwords or tokens are secrets. Avoid embedding usernames/passwords directly into URLs that get logged.

Verify proxy configuration across both application processes and sidecars. One container might route via a proxy while another calls directly, creating divergent network paths and policies.

## 12. Observability and Auditing

### 12.1. Never Log Secret Values

Logs may record:

- Secret name or secret reference.
- Version identifier.
- Load/refresh timestamp.
- Success/failure status.
- Sanitized error codes.

Never log passwords, tokens, private keys, authorization headers, or full environments. During debugging, mask sensitive fields and restrict log access.

### 12.2. Tracking Configuration State

Helpful metrics:

- Active config version per replica.
- Secret version and last refresh timestamp.
- Secret manager read failure counts.
- Token refresh failures.
- Dependency authentication/authorization error rates.
- Certificate expiration countdowns.
- Pod restarts caused by invalid configuration.
- Count of workloads using soon-to-expire credentials.

Never attach raw secret values to metric labels or trace attributes. Use non-sensitive identifiers only.

### 12.3. Permission Auditing

Track:

- Who creates or modifies Secrets.
- Which workload identities read which secrets.
- Which policies are altered.
- When tokens are issued or revoked.
- Who uses break-glass access.
- Which secrets are overdue for policy rotation.
- Which workloads hold broader permissions than required.

Protect audit logs from tampering or deletion by the very workloads being monitored.

## 13. Deployment Workflow from Development to Production

A reference workflow:

1. Define a configuration schema and classify non-secret vs. secret values.
2. Build images containing no runtime credentials.
3. Scan the image and audit the Dockerfile/build context.
4. Create separate configurations for development, staging, and production.
5. Provision secrets in a secret manager or approved store.
6. Bind workload identities and grant least-privilege permissions.
7. Deploy to staging using the exact same config-injection mechanism as production.
8. Test config loading, secret reading, dependency access, and failure behavior on missing config.
9. Roll out to production via canary or rolling update.
10. Monitor config versions, auth errors, secret refreshes, and application health.
11. Test credential rotation and revocation.
12. Document owners, versions, audit trails, and operational runbooks.

~~~mermaid
flowchart TD
    A["Source code and config schema"]
    B["Build image without runtime secrets"]
    C["Scan image and verify artifacts"]
    D["Create per-environment config and secrets"]
    E["Attach workload identity and policies"]
    F["Deploy staging and test dependencies"]
    G["Canary / rolling rollout to production"]
    H["Monitor config, identity, and secret refreshes"]
    I["Rotate, revoke, and audit"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

## 14. End-to-End Example: API Accessing a Database and Object Storage

An API container needs:

- Non-secret config: port, log level, database host, and bucket name.
- Secret: database password or equivalent credential if the database does not yet support identity auth.
- Identity: read access to objects in a specific bucket.
- Certificate: trust bundle to verify TLS connections to the database.

Design:

| Component | Mechanism |
|---|---|
| `HTTP_PORT`, `LOG_LEVEL` | Environment variable |
| `DB_HOST`, `DB_NAME` | ConfigMap or deployment config |
| `DB_PASSWORD` | Secret manager, mounted read-only as a file |
| Object storage access | Workload identity scoped to reading the specific bucket |
| CA bundle | Read-only file mount from managed artifact/PKI |
| Secret rotation | Update version, roll out or reload, then revoke the old version |
| Audit | Log identity, secret reference/version, and access outcome without values |

When the container starts:

1. Validate required config keys and data types.
2. Read the password from the secret file if required by the database auth mechanism.
3. Obtain short-lived credentials via workload identity to call object storage.
4. Verify database connectivity and TLS.
5. Mark readiness healthy only after essential dependencies are ready.
6. When secrets rotate, reload or roll out according to procedure.
7. If identity lacks permission, fail closed and emit a sanitized error.

Never grant administrative object storage keys to an API that only reads a single bucket. Never let the application fall back to a default password if a secret cannot be read.

## 15. Common Troubleshooting Scenarios

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Container starts but DB connection fails | Missing env, wrong endpoint, bad secret, or network policy | Verify config names, secret version, DNS, routes, and permissions |
| Pod reports permission denied reading secret file | Mismatched UID/GID or file mode | Check `securityContext`, owner, group, and file mode |
| New secret created but app still uses old value | Env not refreshed or app not reloading file | Check rollout, volume projection, and file watcher |
| Workload identity fails to receive token | Wrong ServiceAccount/role binding or federation setup | Check audience, subject, issuer, trust policy, and clock skew |
| Cloud API call returns AccessDenied | Identity authenticated but lacks authorization | Inspect IAM/RBAC scope and resource policies |
| Only some replicas fail after config change | Replicas running different config versions or partial rollout | Compare Pod templates, versions, and rollout status |
| Secret leaked in logs | Debug dump of env/headers or exception with credentials | Mask logs, revoke secret, audit, and rotate |
| Build pipeline fails to access registry | Wrong build secret mount or registry permissions | Check secret ID, mount target, token scope, and sanitized logs |
| Certificate expired | Unsynchronized rotation or missing alerts | Check chain, expiry, volume reload, and rollout |
| Pod cannot access Kubernetes API | Token not mounted or missing RBAC | Check ServiceAccount, projected token, and policies |

When investigating, avoid running commands that dump the entire environment or print full Secrets to the terminal. Use commands that inspect only key names, versions, permissions, and statuses whenever possible.

## 16. Common Mistakes

**Putting passwords in Dockerfile `ENV` or `ARG`.** Values can linger in metadata, image history, or build caches. Use a secret manager or appropriate secret mount mechanisms.

**Committing `.env` files to Git.** Local files may hold production credentials. Commit a `.env.example` template with placeholders only and exclude real files from the repository.

**Assuming Base64 is encryption.** Base64-encoded Kubernetes Secrets can still be decoded trivially. Enforce encryption at rest, RBAC, and auditing.

**Using one access key for all workloads.** Hard to scope permissions and revoke individually. Use workload identity and separate roles.

**Granting admin roles to a service account.** One application bug can escalate into cluster or account compromise. Grant least-privilege permissions by resource and verb.

**Mounting the same secret into every container in a Pod.** Sidecars that do not need credentials become extra leakage paths. Mount secrets only into the containers that need them.

**Assuming a secret volume automatically updates the application.** File projection and process reloading are separate steps. Test reload behavior or trigger a rollout.

**Rotating only in the secret manager.** Consumers may still be using the old credential. Track running versions and revoke only after transition completes.

**Printing the environment or authorization headers while debugging.** Logs and diagnostic bundles persist and are widely copied. Mask data and log only necessary metadata.

**Using runtime credentials in build pipelines.** Build code could access unneeded runtime secrets. Separate credentials by role and lifecycle stage.

**Failing to test secret manager outages.** Decide whether the application should fail closed or use a bounded-TTL cache; never retain stale credentials indefinitely.

## 17. Deployment Checklist

### Configuration

- [ ] Separate normal config, internal metadata, and secrets.
- [ ] A single image can be promoted across all environments.
- [ ] Configuration schema, safe defaults, and startup validation exist.
- [ ] Precedence among defaults, files, env vars, and runtime flags is documented.
- [ ] Full environment variables are never printed to logs.

### Secrets

- [ ] No secrets appear in source code, Dockerfiles, image layers, or build logs.
- [ ] Approved secret manager or secret store is used.
- [ ] Secret files are mounted read-only where appropriate with scoped UID/GID.
- [ ] Source files, build context, registries, caches, and backups are secured.
- [ ] Versioning, ownership, rotation, and revocation processes exist.
- [ ] Secret refreshes and credential expirations are tested.
- [ ] Base64 is never treated as encryption.

### Identity and Permissions

- [ ] Workload identity is used wherever supported by the platform.
- [ ] Separate identities exist per workload and environment.
- [ ] Least-privilege permissions apply to cloud resources and the Kubernetes API.
- [ ] Static access keys and wildcard permissions are avoided.
- [ ] Permissions to read Secrets, create Pods, and access hosts are restricted.
- [ ] Auditing and controlled break-glass procedures are in place.

### Deployment and Operations

- [ ] Containers run non-root whenever possible.
- [ ] Read-only root filesystems and selective mounts are used.
- [ ] Config, secrets, and identities are tested in staging.
- [ ] Configuration and secret updates roll out by version.
- [ ] Token refreshes, auth errors, and certificate expirations are monitored.
- [ ] Rotation, revocation, and secret manager outages are tested.
- [ ] An incident runbook exists for compromised credentials.

## 18. Key Takeaways

- Configuration governs how an application runs; secrets are sensitive authentication data; workload identity identifies who a container is when calling resources.
- An image should be built once and receive environment-specific configuration at deploy time.
- Never place runtime secrets in Dockerfiles, source code, image layers, command lines, or logs.
- Environment variables work well for small configs, but they are not a secret manager and usually do not auto-refresh in running processes.
- File mounts help enforce permissions and handle multi-line data; still enforce read-only mounts, UID/GID scoping, and source protection.
- Docker Compose file secrets, Docker Swarm secrets, and Kubernetes Secrets offer different protection guarantees.
- Kubernetes Secret Base64 is not encryption; enforce RBAC, encryption at rest, and auditing.
- Workload identity with short-lived tokens eliminates static access keys inside containers.
- Rotation requires migrating consumers, verifying the new version, and only then revoking the old credential.
- Config/secret updates require controlled reloads or rollouts; a changed file on disk does not mean the application has adopted the new value.
- Run non-root, restrict permissions, and mount secrets only into containers that genuinely need them.
- Test scenarios where the secret manager, identity provider, or dependencies are temporarily unreachable.

## Glossary

| Term | Meaning |
|---|---|
| Configuration | Values controlling application behavior per environment. |
| Secret | Sensitive authentication data such as passwords, tokens, or private keys. |
| Workload identity | Identity bound to a running application or workload. |
| Authentication | Process of verifying the identity of a caller or workload. |
| Authorization | Process of determining what actions an identity is permitted to perform. |
| Environment variable | Variable passed to a process when launched. |
| Dockerfile ARG | Variable used during the image build process. |
| Dockerfile ENV | Default environment variable stored inside an image. |
| BuildKit secret mount | Mechanism exposing a temporary secret to a build step without adding it to image layers via the mount. |
| ConfigMap | Kubernetes object storing non-sensitive configuration. |
| Kubernetes Secret | Kubernetes object storing sensitive key/value data; requires additional controls for full protection. |
| Secret manager | Service for storing, distributing, auditing, and rotating secrets. |
| ServiceAccount | Identity for processes or workloads inside Kubernetes. |
| RBAC | Role-Based Access Control, a role-based authorization mechanism. |
| IAM | Identity and Access Management system for identities and access policies. |
| Workload identity federation | Mechanism exchanging workload identity for cloud/IdP credentials without long-lived keys. |
| Token rotation | Replacing tokens by lifetime or policy to limit risk if leaked. |
| Secret rotation | Workflow to replace a secret, transition consumers, and revoke the old value. |
| Least privilege | Principle of granting only the minimum permissions required. |
| CSI Secret Store | CSI mechanism allowing external secret providers to mount secrets into workloads. |
| Read-only filesystem | Root filesystem denying process writes except into explicitly mounted writable volumes. |
| Break-glass access | Emergency access strictly controlled and audited. |
| Config drift | Divergence between actual configuration across replicas or from desired state. |
