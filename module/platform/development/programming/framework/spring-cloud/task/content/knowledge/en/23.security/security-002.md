# Managing Connection Information via Secrets or Secret Services

## 1. Why Is Secret Management Especially Important for Spring Cloud Task?

**Spring Cloud Task** builds Spring Boot applications with a finite lifetime: receiving a request, starting up, processing work, recording status and results into a database via `TaskRepository`, and then terminating. Tasks can run on a schedule or on demand, coordinate with Spring Batch, connect to multiple databases, and exchange data through brokers or external APIs.

To do their work, Tasks often require sensitive information:

- JDBC credentials for `TaskRepository`, `JobRepository`, or business databases.
- Connection strings containing tokens, Kafka/AMQP access keys, API keys, or OAuth client secrets.
- Private keys, mTLS certificates, and keystore/truststore passwords.
- Credentials for object storage or data import/export services.

If these values are placed directly in code, an `application.yml` packaged inside a JAR, command-line arguments, or logs, unauthorized users may obtain them. Some locations are especially dangerous for Spring Cloud Task: **execution parameters can be persisted in `TASK_EXECUTION_PARAMS`**, and errors can appear in `ERROR_MESSAGE`, logs, or orchestration systems.

Objectives of the lesson **“Managing Connection Information via Secrets or Secret Services”** in the **Security** chapter:

1. Classify secrets, regular configuration, and access identities.
2. Keep credentials out of Git, images, command lines, metadata, and logs.
3. Configure Spring Boot to read secrets from Kubernetes Secrets via environment variables or mounted files.
4. Use external secret services such as HashiCorp Vault or cloud secret managers based on workload identity.
5. Understand the secret lifecycle: provisioning, access restriction, refresh/rotation, revocation, and incident handling.
6. Design separate least-privilege permissions for TaskRepository, Spring Batch, migrations, and business services.
7. Establish safe testing and operational procedures for both short-lived Tasks and long-running Jobs.

## 2. Threat Model: Which Boundaries Do Secrets Cross?

```mermaid
flowchart TD
    U["Scheduler / launch request API"] --> L["TaskLauncher / Kubernetes Job"]
    L --> P["Pod or Spring Cloud Task JVM"]
    K["Kubernetes Secret or Secret Manager"] -->|Valid identity and permissions| P
    P --> R["TaskRepository JDBC"]
    P --> B["JobRepository / Business DB"]
    P --> E["Broker, API, object storage"]
    P --> O["Logs, traces, metrics, TaskExecution"]
    X["Unauthorized actor"] -.-> L
    X -.-> O
    X -.-> K
```

Every arrow is a **trust boundary**. Someone permitted to call an API to launch a Task does not necessarily have permission to read database passwords. Someone viewing logs to investigate an incident does not necessarily have permission to read cluster Secrets. A running process should be granted **just enough permissions to complete its specific job**, not administrative privileges over an entire database or secret store.

### 2.1. Configuration Data Classification

| Value | Is it a secret? | Where should it be managed? |
| --- | --- | --- |
| `--business-date=2026-11-23` | Usually no | Business parameter; safe to store in metadata |
| `--source=marketplace` | Usually no, if it contains no sensitive identifier | Business parameter |
| `spring.application.name` | No | ConfigMap / `application.yml` |
| JDBC host/port/schema | Usually no, though it may be internal info needing restriction | Environment configuration |
| JDBC username | May be sensitive regarding identity/privileges | Secret or policy-protected configuration |
| JDBC password | **Yes** | Kubernetes Secret / secret manager |
| Bearer token or OAuth client secret | **Yes** | Secret manager; prefer short-lived issuance |
| Private key / keystore password | **Yes** | Secret file or secret manager |
| Public CA certificate | Typically not a secret | ConfigMap or managed truststore |
| Cloud role / workload identity | Identity and permission policy, not a traditional “password” | IAM / ServiceAccount |

**Do not assume every URI is safe to expose.** For example, `jdbc:postgresql://db.example/taskdb` usually carries no password, whereas `jdbc:postgresql://user:password@host/...` or a URL with a query token contains secrets. If a URL contains credentials, the entire URL must be treated as a secret.

### 2.2. Common Places Where Secrets Leak

| Channel | Risk Example | Why is it dangerous? |
| --- | --- | --- |
| Git | `password: actual-password` in YAML | Commit history and clones can persist long-term |
| Image / JAR | Packaging `application-prod.yml` containing passwords | Anyone who downloads the image/JAR can extract it |
| CLI | `--spring.datasource.password=...` | Exposed via argv, events, orchestrators, and Task metadata |
| `TaskRepository` | `TASK_EXECUTION_PARAMS` containing password | Execution history inadvertently becomes a secret store |
| Spring Batch | JobParameters or ExecutionContext containing tokens | Secrets can be serialized into `BATCH_*` |
| Logs / tracing | Printing full `Environment` or request headers | Many people or systems have permission to view logs |
| Actuator | Exposing `/actuator/env`, `/actuator/configprops` without controls | Even with value masking, creates a risky access surface |
| Kubernetes API | Base64 Secrets or arbitrary Pod creation permissions | Base64 is decodable; Pods can mount Secrets in the namespace |
| Dumps / snapshots | Heap dumps, core dumps, etcd backups | May contain secret strings currently in memory or config |

You must protect not just **where values are stored**, but also **transmission, usage, logging, backups, refresh, and revocation**.

## 3. Strategies for Providing Secrets to a Task

| Approach | Secret Source | How Task Receives It | Strengths | Caveats |
| --- | --- | --- | --- | --- |
| Kubernetes Secret → `env` | Secret in namespace | `secretKeyRef` | Simple, suitable for short Tasks | Env does not auto-update in process; risk of reading via process/debug |
| Kubernetes Secret → volume | Secret in namespace | Read-only file | Keeps secret out of argv; works well with certs/`configtree:` | Needs file permissions; mount updates do not auto-refresh beans |
| Vault / secret manager → Spring Boot | Centralized secret store | `spring.config.import` / SDK | Auditing, RBAC, dynamic secrets/TTL depending on service | Auth, HA, networking, startup failure, lease/refresh |
| Secrets Store CSI Driver | External secret store | Volume file via CSI provider | Supplies Pod files from secret store | Rotation depends on config; app must consume new content |
| External Secrets controller | External secret store | Syncs into Kubernetes Secret | Reuses existing `secretKeyRef`/volumes | Secrets are copied into cluster; review RBAC, sync delay |
| Cloud workload identity + IAM | IAM, no static keys stored | SDK receives short-lived tokens automatically | Reduces private keys/long-lived secrets | Configure audience, role, permissions, and rotation properly |

No solution eliminates the responsibility to protect secrets **after the Task has read them**. A secret manager cannot stop an application from printing credentials into logs.

## 4. Designing Spring Boot Configuration: Keeping Secrets Out of the Code Repository

### 4.1. Store Only Placeholders in application.yml

Example of a Task using PostgreSQL:

```yaml
spring:
  application:
    name: orders-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
      closecontextEnabled: true
  batch:
    jdbc:
      initialize-schema: never
```

Where:

- The file in Git **contains no real passwords**.
- `TASK_DB_URL`, `TASK_DB_USER`, and `TASK_DB_PASSWORD` are supplied by the launch environment.
- `spring.cloud.task.initialize-enabled=false` assumes `TASK_*` tables were already created via migrations.
- `spring.batch.jdbc.initialize-schema=never` is only needed if the application uses Batch and the `BATCH_*` schema is also managed via migrations.

**Do not set real default values for passwords**, such as `${TASK_DB_PASSWORD:productionPassword}`. If a required secret is missing, the Task should **fail fast** and log a message **without containing any secret value**, rather than silently connecting with a shared account.

### 4.2. How Spring Boot Reads Environment Variables

Spring Boot provides externalized configuration, allowing environment variables to bind to properties. Common direct variable forms include:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

Or use custom placeholders like `TASK_DB_PASSWORD` in YAML to decouple the deployment contract from framework property names. Property sources have a **precedence order**; a CLI argument `--spring.datasource.password=...` can override a value fetched from a secure source. Therefore, you must control which arguments launchers/APIs are allowed to pass.

### 4.3. Do Not Put Secrets in ApplicationArguments

**Incorrect:**

```bash
java -jar orders-import.jar \
  --business-date=2026-11-23 \
  --spring.datasource.password=<real-password>
```

**Correct in principle:**

```bash
java -jar orders-import.jar \
  --business-date=2026-11-23 \
  --source=marketplace
```

Passwords are supplied via environment/volume/secret manager, **not in argv**. Spring Cloud Task has the `TASK_EXECUTION_PARAMS` table storing execution arguments. `ApplicationArguments`, shell history, `ps` commands, Pod specs, or launch systems can also expose argv depending on access permissions.

If a system previously stored secrets in legacy arguments, do not just patch new code: inspect **persisted metadata**, logs, backups, and credential issuance channels to plan revocation.

## 5. Option A — Kubernetes Secret as Environment Variables

### 5.1. Creating Secrets Safely

A Kubernetes `Opaque` Secret holds key-value pairs such as passwords, tokens, and connection info. The `data` field in a manifest represents data using Base64; **Base64 is not security encryption**. Secret data may be stored unencrypted in `etcd` if the cluster does not have encryption at rest enabled.

In documentation, **never put real passwords** into manifests or command examples with literal value flags. During testing, you can prepare a secret file on a secure admin workstation and use `--from-file`:

```bash
# The file below must be created by a secure secret management workflow,
# never committed to Git or printed to the terminal.
kubectl -n batch-jobs create secret generic orders-task-db \
  --from-file=password=/secure/path/orders-db-password.txt
```

This is an **illustrative** operation, not something to run automatically in this lesson. The input file needs restricted permissions, secure deletion per organizational policy, and protection so command history or system logs do not capture secret contents. If your organization uses GitOps, use appropriate secret management tools such as a secret manager + controller, or platform-supported encrypted secret manifests, rather than committing plaintext/Base64 Secrets.

### 5.2. Job Using secretKeyRef

Assume Secret `orders-task-db` exists in namespace `batch-jobs` and contains key `password`. Example:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import-example
  namespace: batch-jobs
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: orders-task-runner
      containers:
        - name: orders-import
          image: registry.example.com/tasks/orders-import:1.4.2
          args:
            - "--business-date=2026-11-23"
            - "--source=marketplace"
          env:
            - name: TASK_DB_URL
              value: "jdbc:postgresql://postgres.internal:5432/taskdb"
            - name: TASK_DB_USER
              value: "task_runtime"
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-task-db
                  key: password
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "768Mi"
```

Prerequisites:

1. Namespace `batch-jobs`, Secret `orders-task-db`, and ServiceAccount `orders-task-runner` have already been created.
2. The image entrypoint runs the Spring Boot Task and forwards `args` properly.
3. The Pod has network connectivity to PostgreSQL; the database and `TASK_*` tables are prepared in advance.
4. The password for account `task_runtime` has just enough privileges on the repository and no unnecessary DDL privileges.
5. No debug/logging code automatically prints all of `env`.

`env[].valueFrom.secretKeyRef` **only references** the Secret name and key; the Pod manifest does not need to contain the password. However, Pod access permissions or permissions to create Pods in the same namespace can indirectly open a path to read Secrets. Proper RBAC and admission control policies are required, not merely hiding values from YAML files.

### 5.3. What Happens If a Secret Is Missing?

If a **required** referenced Secret or key does not exist, Kubernetes typically prevents the container from starting and emits related events. In that case, **the Task may not have a `TaskExecution` record yet**, because the JVM never started.

Do not conclude “the Task was never invoked” simply because the `TASK_EXECUTION` table is empty. Inspect:

```bash
kubectl -n batch-jobs get job orders-import-example
kubectl -n batch-jobs get pods
kubectl -n batch-jobs describe job orders-import-example
kubectl -n batch-jobs describe pod <pod-name>
```

Replace `<pod-name>` with the actual Pod name. Do not casually run `kubectl get secret ... -o yaml` or `-o json` for debugging: it can expose `data` in easily decoded Base64. To confirm a Secret exists, use appropriate metadata permissions and inspect events/Pod status without printing values.

### 5.4. Limitations of Env When Secrets Change

Kubernetes **does not automatically update environment variables** of a running container when a Secret is edited. New Secrets are typically picked up only when **a Pod is recreated** or a new process starts. For finite Tasks running a few minutes, using env vars can be suitable if credentials remain valid throughout the entire run.

For multi-hour Batch Jobs:

- A Secret revoked while a Job is still running can cause JDBC reconnects to fail.
- If the Task holds a connection pool with old credentials, existing connections and new connections can behave differently during rotation.
- Do not assume editing a Secret in the API server causes `HikariDataSource` to change its password automatically.

You need a rotation/credential overlap, drain, and Task restart plan aligned with business boundaries.

## 6. Option B — Mounting Secrets as Files

### 6.1. When Should Files Be Used?

Mounting Secrets as files fits well for:

- Private keys, client certificates, truststores/keystores, and TLS configuration.
- Secret managers/CSI drivers providing files to a Pod.
- Applications wanting to avoid copying passwords into environment variables.
- Spring Boot's `configtree:` mechanism to bind files by key name.

File mounts do not make secrets “invisible”: any process/container permitted to read that path can still obtain the value. Protect them with namespaces, Pod security contexts, POSIX permissions, and by mounting only into **containers that truly need them**.

### 6.2. Using Spring Boot configtree

Suppose you want Spring Boot to bind directly to `spring.datasource.username` and `spring.datasource.password`. In the Kubernetes Secret, create two keys **with the exact property names**:

```text
orders-task-db-properties
  spring.datasource.username
  spring.datasource.password
```

In the Pod, mount those keys as two files at:

```text
/run/secrets/task-db/
  spring.datasource.username
  spring.datasource.password
```

In `application.yml`:

```yaml
spring:
  application:
    name: orders-import-task
  config:
    import: "configtree:/run/secrets/task-db/"
  datasource:
    url: ${TASK_DB_URL}
  cloud:
    task:
      initialize-enabled: false
```

With `configtree:`, the **filename** becomes the property name and the **file contents** become the property value. This is a Spring Boot Config Data feature, not a file-reading mechanism exclusive to Spring Cloud Task.

**Why not use `optional:configtree:` for required secrets?** The `optional:` prefix allows startup to continue if the location does not exist. If a password is required, startup should fail clearly when the mount is missing, rather than silently picking up unintended configuration elsewhere. Application-level property validation is still needed.

### 6.3. Job Manifest Using a Secret Volume

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import-from-files
  namespace: batch-jobs
spec:
  backoffLimit: 0
  template:
    spec:
      serviceAccountName: orders-task-runner
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 2000
      containers:
        - name: orders-import
          image: registry.example.com/tasks/orders-import:1.4.2
          args:
            - "--business-date=2026-11-23"
          env:
            - name: TASK_DB_URL
              value: "jdbc:postgresql://postgres.internal:5432/taskdb"
          volumeMounts:
            - name: task-db-credentials
              mountPath: /run/secrets/task-db
              readOnly: true
          resources:
            requests:
              memory: 256Mi
            limits:
              memory: 768Mi
      volumes:
        - name: task-db-credentials
          secret:
            secretName: orders-task-db-properties
            defaultMode: 0440
            items:
              - key: spring.datasource.username
                path: spring.datasource.username
              - key: spring.datasource.password
                path: spring.datasource.password
```

The example above assumes the cluster's volume permission mechanism allows the specified user/group to read the files. `defaultMode: 0440` is **octal notation in Kubernetes YAML** (in JSON, the corresponding decimal integer must be used). Verify effective file permissions inside the container environment and `fsGroup` behavior.

Notes:

- The Secret and Pod must belong to the **same namespace**.
- Do not mount secret files into unnecessary sidecars.
- Do not let the Task write secrets back out to log files or output directories.
- Do not mount with `subPath` if you expect Kubernetes to update file contents after the Secret changes.
- During rotation, mounted contents may update **eventually consistently**, but an already-initialized `DataSource` bean **does not auto-refresh** simply because the file changed.

### 6.4. When Secret Keys Do Not Match Property Names

You can name the files `username` and `password`, then use:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/task-db/"
  datasource:
    username: ${username}
    password: ${password}
```

However, names like `username` and `password` are too generic and can **collide** with other property sources. In applications using multiple databases, use namespaced keys such as `task.db.username`/`task.db.password` or mount under paths structured to produce full names.

With multiple configtrees, check location precedence and prevent one system's secret from overriding another system's properties.

## 7. Option C — Fetching Secrets from an External Service

### 7.1. What Does a Secret Manager Add?

A secret management service such as **HashiCorp Vault**, AWS Secrets Manager, Azure Key Vault, or Google Secret Manager can provide:

- Fine-grained access policies by identity and secret path.
- Change history, auditing, versioning, and rotation workflows.
- Encrypted connections and server authentication.
- Short-lived/dynamic credentials in supported systems.
- Access separation across development, staging, and production environments.

Not every service offers the **same lease, renewal, or dynamic database credential mechanisms**. Check your specific service and SDK/framework integration instead of assuming all secrets auto-refresh inside the JVM.

### 7.2. Task Startup Flow with Vault

```mermaid
sequenceDiagram
    participant K as Kubernetes Job / Pod
    participant T as Spring Cloud Task
    participant V as Vault
    participant D as PostgreSQL
    K->>T: Start container with ServiceAccount
    T->>V: Authenticate Kubernetes identity
    V-->>T: Policy-scoped token/lease
    T->>V: Read config or DB credentials
    V-->>T: Secret over TLS connection
    T->>D: Open JDBC connection
    D-->>T: Connection accepted
    T->>T: Run Runner, write TaskExecution
    T->>T: Close context and terminate
```

The goal is to avoid putting a **Vault root token** or static application secret into the image. The workload uses its **Kubernetes ServiceAccount identity** so Vault authenticates it and returns only the secrets allowed by policy.

### 7.3. Configuring Spring Cloud Vault with Kubernetes Authentication

Illustrative example using `Spring Cloud Vault` and `Config Data API`:

```yaml
spring:
  application:
    name: orders-import-task
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: KUBERNETES
      kubernetes:
        role: orders-task-reader
        kubernetes-path: kubernetes
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
      kv:
        enabled: true
    task:
      initialize-enabled: false
  datasource:
    url: ${TASK_DB_URL}
```

For dependencies, include the Spring Cloud Vault starter compatible with your project's Spring Boot/Spring Cloud BOM, such as `org.springframework.cloud:spring-cloud-starter-vault-config` matching your supported release train. **Do not invent versions** outside the compatibility matrix.

Mandatory prerequisites:

1. Vault is deployed, configured with TLS/certificates, and has a Kubernetes auth mount matching `kubernetes-path`.
2. Vault role `orders-task-reader` is **bound** to the valid ServiceAccount and namespace.
3. The Vault policy grants read-only access solely to this Task's secret path, never Vault admin permissions.
4. The Pod actually has the ServiceAccount token at the path used by the application (do not disable token projection when authentication still relies on it).
5. The Vault path/version and keys are defined to supply the required Spring properties, such as `spring.datasource.username` and `spring.datasource.password`.
6. Infrastructure permits HTTPS connectivity from the Pod to Vault and verifies the server certificate.

Here `vault://` imports enabled secret backends via Spring Cloud Vault's Config Data mechanism; how the **KV context path**, profiles, or mount paths are selected must be verified per version—do not assume any Vault KV named `orders-import-task` will be read without configuration.

**Do not build production examples with `spring.cloud.vault.token=<root-token>`.** A static root token grants excessive privileges and risks exposure through YAML, environment variables, logs, or snapshots. When experimenting with a Vault dev server, clearly separate the demo setup from production.

### 7.4. KV Secrets vs. Dynamic Database Credentials

Two common models:

| Model | Returned Secret | Lifecycle |
| --- | --- | --- |
| Versioned KV | Managed username/password or API key | Rotated via external workflow; application may require restart |
| Dynamic database credentials | Role-based, leased username/password | Has a TTL, may require renewal or re-issuance; DB user can be revoked when lease ends |

When using dynamic credentials, consider the Task's **maximum** runtime, renewal intervals, networking, and `DataSource` behavior when connections are reacquired. Do not assume Vault automatically changes passwords on existing JDBC connections or that a service can keep using revoked credentials.

For very short-lived Tasks, issuing credentials at startup with a TTL **longer than expected runtime** (plus a safety margin) is a simple strategy, though deadlines and hung-Task handling are still necessary. For Batch Jobs lasting many hours, you need an **end-to-end verified** renew/refresh mechanism or shorter work units to reduce risk.

### 7.5. Direct Cloud SDK Integration

When using AWS/Azure/GCP, the application can retrieve secrets via SDK:

```text
Spring Cloud Task
    |
    +-- Workload identity / IAM role
    |
    +-- Cloud Secret Manager SDK
            |
            +-- Fetch secret by resource name / version
            +-- Cache only as long as needed
            +-- Emit service-side audit logs
```

API names and configuration vary by provider, so no single Java snippet runs across all three clouds. The core rules are to **prefer short-lived workload identities**, avoid distributing static access keys, use TLS, grant read-only access to the specific secret, and design fail-safe handling if the secret store is unreachable.

## 8. Secrets Store CSI Driver and External Secrets: Two Different Integration Paths

### 8.1. Secrets Store CSI Driver

The **Secrets Store CSI Driver** lets Pods mount secrets from an external secret manager through a CSI provider. Typically:

1. Administrators install the CSI Driver and appropriate provider.
2. A `SecretProviderClass` is created describing which secret objects to fetch per that provider's schema.
3. The Pod attaches the CSI volume and mounts the secret files.
4. Spring Boot can read the files directly or via `configtree:`.

Example **volume snippet** (not a standalone runnable manifest without the provider):

```yaml
volumeMounts:
  - name: secret-store
    mountPath: /mnt/secrets-store
    readOnly: true
volumes:
  - name: secret-store
    csi:
      driver: secrets-store.csi.k8s.io
      readOnly: true
      volumeAttributes:
        secretProviderClass: orders-import-secrets
```

The `SecretProviderClass` must exist **in the Pod's namespace** and match the provider configuration. The CSI Driver has an optional **auto rotation** feature; do not assume it is enabled by default or has a fixed latency. Even if the mounted file updates, Spring Boot beans/connection pools still need a reload and connection replacement mechanism to adopt the new secret in a running process.

### 8.2. External Secrets Controller

A controller such as **External Secrets Operator** can synchronize secrets from an external store into **Kubernetes Secrets**. Pods then use `secretKeyRef` or volumes as in sections 5–6. Key differences:

- Secrets are **copied into Kubernetes Secrets**; you must still protect RBAC and `etcd` encryption.
- Synchronization runs periodically and can experience latency or errors if the provider disconnects.
- Pods using `env` do not automatically receive updated values after the Kubernetes Secret updates.
- The controller's permissions to read the secret store must be scoped; do not grant org-wide permissions across every namespace.

Do not equate CSI Driver and External Secrets as identical mechanisms: one primarily **mounts files from the provider**, while the other **syncs Kubernetes Secrets**; real deployments may combine them, which introduces more points to audit.

## 9. Workload Identity and the Principle of Least Privilege

### 9.1. Separating Permissions by Role

A Spring Cloud Task system has at least four distinct roles:

| Role | What permissions are needed? | What should it NOT have? |
| --- | --- | --- |
| **Launcher / orchestrator** | Create Jobs/Pods from allowlisted artifacts in permitted namespaces | Read access to all Secrets / cluster-admin |
| **Task runtime** | Read only its assigned secrets; required DML/sequences on `TASK_*` and business tables | Create/drop tables, read other apps' secrets |
| **Migration job** | DDL privileges per reviewed migrations | Passwords/secrets of unrelated environments |
| **Operator / auditor** | View Job status, filtered logs, needed metadata/metrics | Access to plaintext secrets unless explicitly required |

When integrating Spring Batch, `JobRepository` has separate `BATCH_*` tables. The runtime user needs read/write permissions on the appropriate tables/sequences; do not use a DBA account for every worker. If TaskRepository and JobRepository live in different databases, use **separate** credentials and explicitly define which `DataSource` is authorized to access what.

### 9.2. Pod ServiceAccounts Do Not Automatically Need `get Secret` Permission

If a Pod only declares `secretKeyRef` or a Secret volume, the kubelet handles delivering the data to the container. **Do not blindly grant RBAC `get/list/watch secrets` to the runtime ServiceAccount** just because the Pod needs a Secret in its environment.

Even so, anyone permitted to **create Pods** in a namespace can design a Pod that mounts Secrets from that namespace in many configurations. Consequently, Pod/Job creation rights, ServiceAccount modification rights, admission policies, and namespace segmentation are all part of the security model.

### 9.3. Use a Dedicated ServiceAccount per Task

Example:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-task-runner
  namespace: batch-jobs
```

This is solely a **Pod identity**; it does not automatically grant access to Vault or cloud secret stores. Depending on your infrastructure, configure the corresponding Vault role, cloud workload identity, IAM binding, or projected token audience. Do not share an overly privileged default ServiceAccount across all Jobs.

When a workload **does not need** to call the Kubernetes API or Vault Kubernetes auth, consider disabling automatic ServiceAccount token mounting via the appropriate configuration. If it **does need** the token to authenticate with Vault, do not disable it mechanically; instead restrict permissions and audience/token scope by design.

## 10. Secrets in JDBC: Securing Connections Goes Beyond Passwords

### 10.1. Four Layers of Protection

A Task connecting to PostgreSQL should address:

1. **Authentication:** username/password or appropriate IAM/certificate mechanism.
2. **SQL authorization:** runtime account has only needed DML/sequence privileges, never superuser.
3. **Encryption in transit:** TLS with hostname and server certificate verification.
4. **Lifecycle management:** credential rotation, revocation, error monitoring, and closing pools when the Task exits.

A password fetched from a Secret can still be exposed in transit if the connection is unprotected. Driver configuration depends on the RDBMS; for PostgreSQL JDBC, an example with verification enabled is:

```text
jdbc:postgresql://postgres.internal:5432/taskdb?sslmode=verify-full
```

You must supply the CA/truststore and ensure the DNS name matches the certificate. This is a **design example** and does not guarantee every database already has valid certificates issued for the URL to work out of the box. Never use `sslmode=disable` or skip certificate verification just to bypass a production TLS error.

### 10.2. Database Credentials per Environment

| Environment | Permission Model | Management Approach |
| --- | --- | --- |
| Local dev | Sandbox credentials with no real data | Env/files outside Git; never use production passwords |
| CI | Test credentials scoped per job/pipeline | CI secret store, job isolation; clean up resources after tests |
| Staging | Dedicated role, separate database or schema | Separate secrets, independent policies |
| Production | Least-privilege runtime role | Secret manager/Kubernetes Secret, rotation, auditing, and alerts |

Never share production secrets with staging for convenience. If a CI pipeline is compromised, the blast radius must remain confined to the test environment.

### 10.3. A Separate DataSource for Migrations

In production, Flyway/Liquibase should use a separate **migration** account run as a release step. Runtime Spring Cloud Task instances only need permissions to use `TaskRepository`:

```yaml
spring:
  cloud:
    task:
      initialize-enabled: false
  sql:
    init:
      mode: never
  flyway:
    enabled: false
```

The snippet above assumes **migrations already ran separately**. If using Liquibase instead of Flyway, disable Liquibase in runtime accordingly. Do not let every short-lived Task run DDL with an administrative account when the deployment pipeline can separate that step.

## 11. Avoiding Leaks via Logs, Exceptions, TaskRepository, and Batch

### 11.1. What Does TaskRepository Store?

In the standard JDBC schema, `TASK_EXECUTION_PARAMS` records Task arguments, while `TASK_EXECUTION` stores exit codes and error info. That is useful for auditing, **not as a secret store**.

Do not pass arguments such as:

```text
--db-password=<secret-value>
--api-token=<secret-value>
--client-secret=<secret-value>
--jdbc-url=jdbc:postgresql://user:password@host/db
```

Every `<secret-value>` in these examples is a **placeholder**, not a real value. Even if a library offers parameter filtering, **exclude secrets from argv by design** rather than relying solely on filters.

### 11.2. Batch JobParameters and ExecutionContext Can Also Hold Secrets

When a Task invokes Spring Batch, `JobRepository` saves `JobParameters` and `ExecutionContext` to support restarts. Never put passwords, tokens, or private keys into them:

```text
JobParameters:
    businessDate=2026-11-23   (usually appropriate)
    source=marketplace        (usually appropriate)
    apiToken=<secret-value>   (inappropriate)
```

When a Job restarts, it may deserialize the context from the database; if that context holds expired credentials or secret values, it both creates a leak risk and causes the restart to use stale secrets. Store **non-sensitive resource identifiers/secret paths** or business metadata, and fetch credentials freshly through a secure mechanism on each startup.

### 11.3. Do Not Print Spring Environment or Full JDBC URLs

**Avoid:**

```java
// Do not use in real applications:
System.out.println(System.getenv());
System.out.println(dataSource.getConnection().getMetaData().getURL());
```

Even if a JDBC URL currently lacks a password, logging the URL can still expose internal hostnames or sensitive query parameters in other configurations. Never write tokens/headers into trace span attributes or metric tags.

**Prefer:** logging target system names, connection status, classified error codes, and correlation IDs **without credentials**. If you need to verify secret presence, log only **present/absent** at an authorized level; avoid printing values, lengths, hashes, or token prefixes because they still leak information.

### 11.4. Validating Secret Presence Without Logging Contents

Spring Boot example:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class SecretStartupValidation {
    @Bean
    ApplicationRunner validateDatabaseSecret(Environment env) {
        return args -> {
            String password = env.getProperty(
                    "spring.datasource.password");
            if (password == null || password.isBlank()) {
                throw new IllegalStateException(
                        "Missing required database authentication configuration");
            }
            // Do not log the password; Spring Boot uses it
            // via the configured DataSource.
        };
    }
}
```

This example demonstrates a **presence check**, not a complete credential verification workflow. In practice, `DataSource` may initialize or connect before this Runner executes; failing earlier should be enforced through required configuration and bind-time validation if the architecture demands it.

### 11.5. Keep Errors Useful Without Exposing Secrets

Do not build exceptions containing credentials:

```java
// Wrong: the secret value can enter ERROR_MESSAGE/logs.
throw new IllegalArgumentException(
        "Login failed with password=" + password);
```

Emit errors without revealing credentials, preserving necessary exception types/stack traces and restricting who can view logs. Check whether third-party drivers/clients automatically log URLs containing user/password; if so, configure log redaction and appropriate driver properties.

## 12. Rotation Lifecycle: Short Tasks vs. Long-Running Apps

### 12.1. Provision-at-Startup Model

For a Task running 1–3 minutes, a straightforward pattern is:

1. The scheduler creates the Job.
2. The Pod reads the Secret or authenticates to the secret manager.
3. The application sets up `DataSource`.
4. The Runner finishes before the secret expires.
5. The JVM closes connections and exits; new credentials are issued for the next Task run.

This model fits when **the TTL is designed to exceed the Task duration** and there is a plan if the Task runs slow. Do not issue a 60-second TTL credential for a Job that may run 20 minutes and expect the DB session to renew itself automatically.

### 12.2. Safe Credential Rotation

A reference workflow:

```mermaid
flowchart TD
    A["Issue new credential"] --> B["Update Secret/secret manager"]
    B --> C["Verify new Pods/Tasks can authenticate"]
    C --> D["Monitor and drain Tasks using old credential"]
    D --> E["Revoke old credential after safe grace period"]
    E --> F["Verify auth errors, audits, and logs"]
```

Systems supporting **two concurrent credentials** can run an overlap window to avoid disruption. If the database permits only one password and updating it immediately invalidates the old one, plan for downtime/rolling restarts or alternate accounts per database policy.

Do not wait until hundreds of Pods fail with `Authentication failed` to discover a secret rotated or expired. Emit metrics and alerts on **secret expiry/lease TTL** from authorized sources, without placing secret values in metric labels.

### 12.3. Env and File Mounts Differ on Updates

| Mechanism | When the source secret changes | When does the app use the new secret? |
| --- | --- | --- |
| Secret → env | Existing process env does not change | When a new process/Pod is created |
| Secret → volume | File typically updates after a delay; auto-update does not apply when mounted via `subPath` | Only when code/binding **re-reads** it or a new process runs |
| CSI Driver | May update mounts if rotation feature/config is enabled | When the application actually reloads the file contents |
| Vault KV via Config Data | Properties are usually loaded at bootstrap/startup | When a designed refresh/restart occurs; beans do not auto-swap by default |
| Vault dynamic credential | Has a lease and renewal capability depending on integration | According to how credentials/connections are renewed/reissued; must be tested |

A Secret updated in the Kubernetes API **does not immediately become a new password inside a connection pool**. Verify all three layers: secret source → data visible to the Pod → new connections opened by the application.

### 12.4. Emergency Revocation

If a credential is suspected of leaking:

1. **Isolate the scope:** identify which secret, database/API, environment, and Tasks are affected.
2. **Revoke/rotate the credential** using service capabilities, prioritizing blocking unauthorized access.
3. **Issue new credentials** through the secret manager/Kubernetes Secret and perform controlled restarts of affected Tasks.
4. **Inspect running Jobs**, connection pools, and retries still holding the old secret.
5. **Audit traces and artifacts:** Git history, CI logs, Pod specs, `TASK_EXECUTION_PARAMS`, `BATCH_*`, logs, traces, backups.
6. **Verify business data** to prevent Job retries from writing duplicates after mid-run credential revocation.
7. **Record an incident audit** and tighten permissions/eliminate the original leak source.

Merely deleting a password in a new commit **does not erase it from Git history or copies already read**. Treat any exposed secret as compromised and rotate/revoke it according to incident procedures.

## 13. Failure Modes: Should a Task Run When the Secret Manager Is Unavailable?

For **required** credentials, the default answer should be **no**: missing a secret means the Task cannot complete safely. Never fall back to shared passwords or credentials embedded inside the JAR.

| Incident | Expected Behavior | What to Observe |
| --- | --- | --- |
| Secret missing a key | Startup fails, no data processed | Kubernetes events / bean binding errors |
| Invalid RBAC / Vault role | Auth fails with message revealing no token | Vault audit logs, role binding |
| Vault temporarily unreachable | Bounded retries at appropriate layer or fail fast | Timeouts, request IDs, alerts |
| Invalid Vault certificate | TLS verification fails | Chain/hostname/CA; never disable SSL verify |
| DB rejects credential | Fail and investigate rotation/privileges | SQLState/filtered logs, DB audit |
| Secret expires mid-Job | Stop/rollback appropriate transaction unit, recover from checkpoint | Lease TTL, pool reconnects |
| Secret rotated but Pod uses old env | Proactively create new Pods / drain | Pod age, Secret version, auth errors |

With secret managers, some frameworks allow `optional:` imports or disabling fail-fast. **Do not enable optional for required secrets** just to make the app “start.” If credentials cannot be retrieved, the Task must report failure instead of writing data to the wrong or unauthorized target.

### 13.1. A Task Can Fail Before Recording TaskExecution

If Spring Boot cannot read `spring.datasource.password` or Vault fails authentication, `TaskRepository` may **not be initialized yet**. In that case, an empty `TASK_EXECUTION` table **does not prove no launch request occurred**.

Investigation order:

1. Did the launcher/scheduler create the Job?
2. Did the Pod start, or did it hit `CreateContainerConfigError`?
3. Did the app fail on config/TLS/auth before the Runner?
4. Was `TaskRepository` able to write `START_TIME`?
5. How much business work did the Runner complete?

When an app fails during configuration, errors appear in startup logs/Pod events rather than Task metadata.

## 14. Running via Spring Cloud Data Flow or TaskLauncher

### 14.1. Separating Launcher Permissions from Runtime Permissions

`TaskLauncher` or Spring Cloud Data Flow accepts an artifact URI, command-line arguments, application properties, and deployment properties to launch a Task. A launch API user may be allowed to request `orders-import --business-date=...` but **should not be allowed to arbitrarily choose any ServiceAccount or secret reference**.

Appropriate architecture:

```text
Caller
  -> request: businessDate, source (allowlist)
  -> Launcher:
       selects approved artifact/version
       selects namespace + serviceAccount from policy
       selects Secret/secret manager reference
       creates Job / AppDeploymentRequest
  -> Spring Cloud Task:
       reads secret from runtime, NOT from the business request
       runs and records TaskExecution
```

Do not send plaintext passwords in `TaskLaunchRequest.environmentProperties` over a message broker: launch payloads can traverse brokers, tracing, or logs. When secret configuration is needed, prefer **references** to platform-provisioned Secrets/roles rather than embedding values.

### 14.2. Do Not Put Secrets into Deployment Properties

Some backends allow specifying environment variables through deployment properties. Putting plaintext credentials in the request can expose them in command history or deployer metadata.

Pass only **Secret names**, **service accounts**, **resource names**, or policy-approved secret manager identifiers. Exact property syntax depends on Kubernetes/Cloud Foundry/Local `TaskLauncher`; do not assume one generic property works across all backends.

### 14.3. Remote Partitioning: Each Worker Needs Appropriate Credentials

With Spring Batch remote partitioning, a manager deploys multiple workers. Workers must access the **same `JobRepository`** when required by architecture, yet do not necessarily need permission to read every manager secret. Permissions can be separated:

- Manager: permission to launch workers and access required metadata.
- Worker: permission to read its assigned partition and credentials needed for business DB/queues.
- Migration Job: separate DDL permissions; never granted to manager/workers.

If each worker uses short-lived tokens, TTL/rotation must cover Step execution duration and restarts. Do not pass passwords in `ExecutionContext` or JobParameters since metadata is persisted.

## 15. Security Observability Without Leaking Secrets

### 15.1. Recommended Logs and Metrics

| Signal | What to Record | What NOT to Record |
| --- | --- | --- |
| Startup config | Environment name, secret source kind, whether secret is mounted | Password / token / cert private key |
| Vault auth | Success/failure, non-sensitive role ID, correlation ID | Vault token or responses containing secrets |
| JDBC | Logical DB role, SQLState, connection success/failure | Connection URL with credentials, plaintext password |
| Rotation | Timestamp / version alias, rollout result | Old/new secret values |
| `TaskExecution` | ID, status, exit code, filtered message | Secrets in args/error message |
| Metrics | Auth errors by category, Task startup failure count, secret manager latency | Secret values as labels, token prefixes |

A core design principle: **operators must be able to verify a Task received proper access without reading the secret value**. Auditing is needed on both sides: the secret manager (who read the secret) and the scheduler/Task (who ran which artifact).

### 15.2. Actuator and Debugging

Spring Boot Actuator masks some configuration values, but do not rely on that alone to let everyone call `/actuator/env` or `/actuator/configprops`. You must control endpoint exposure, authentication, network access, and read permissions; sanitization behavior can vary by version/configuration.

Do not turn on full debug logging for Spring JDBC, HTTP clients, or request bodies in production just to investigate auth failures; start with error codes and redaction.

### 15.3. Auditing Task Secret Reads

On the Vault/cloud manager side, audit events show which identity read which secret, when, and at what path/version. On the Task side, record:

```text
taskName: orders-import
taskExecutionId: <id or correlation id>
artifactVersion: 1.4.2
environment: prod
secretReference: orders-task-db (only allowlisted name)
credentialVersion: <non-sensitive version alias>
result: success/failure
```

Do not treat `<credentialVersion>` as sole proof that the connection pool is actively using the corresponding credential; verify actual connections and rotation procedures.

## 16. Runbook: Task Cannot Connect to Database Due to Secret

Suppose a Kubernetes Job is created, but the Runner does not execute and logs report `FATAL: password authentication failed`.

### 16.1. Low-Leak Investigation Sequence

1. **Confirm the Task launched:** check Job/Pod status, start time, and image digest.
2. **Check the Secret reference:** verify Secret name, namespace, and key; never print `data` values.
3. **Check Pod env/mount configuration:** environment variable names, paths, file permissions, and `spring.config.import` config.
4. **Check identity and permissions:** confirm ServiceAccount, Vault role, or cloud IAM binding is valid.
5. **Check TLS/network:** DNS, CA, hostname, firewall/egress, endpoint.
6. **Check credential version/rotation:** has the new secret synced? Is an old Pod still using stale env?
7. **Check database role:** verify `CONNECT` privilege and required schema/table/sequence permissions.
8. **Cross-check metadata:** was any `TaskExecution` created; was any business data committed?
9. **Remediate via release/rotation workflows** instead of sending plaintext credentials over chat, logs, or CLI arguments.
10. **Bounded, idempotent retry**, confirming the old process stopped before rerunning.

### 16.2. Read-Only Kubernetes Status Commands

```bash
kubectl -n batch-jobs get jobs
kubectl -n batch-jobs get pods
kubectl -n batch-jobs describe pod <pod-name>
kubectl -n batch-jobs logs <pod-name> --tail=100
```

Use only when the operator is authorized and logs already have sensitive-data protections. `describe` can display Secret/key **names** or deployment details, so share output within an appropriate scope. Avoid commands that directly dump process environments or decode `Secret.data` over uncontrolled channels.

## 17. Common Failure Scenarios and Safe Remediation

| Symptom | Possible Cause | Safe Remediation |
| --- | --- | --- |
| `CreateContainerConfigError` | Required Secret/key missing | Check reference/namespace, provisioning, and events |
| `ConfigDataLocationNotFoundException` | Wrong `configtree:` path or unmounted volume | Fix mount/path; never fall back to hardcoded credentials |
| `AccessDenied` with Vault | ServiceAccount/role/policy mismatch | Check audit logs and least privilege; never use root token |
| TLS handshake failed | Missing CA, hostname mismatch, or expired cert | Fix certificate/truststore; never disable verification |
| DB authentication failed after rotation | Pod using old env, slow secret sync, old password revoked | Drain/restart, verify version and revocation timing |
| No row in `TaskExecution` | JVM failed before repository initialized | Check launcher/Pod/startup logs |
| Task terminated mid-chunk | Credential expired or connection dropped | Inspect checkpoint, transactions, and committed data before retry |
| Password found in `TASK_EXECUTION_PARAMS` | Secret was passed via CLI | Revoke credential, sanitize launch flow, audit old metadata |
| Secret found in logs | Printed `Environment`/HTTP headers/exceptions | Revoke, restrict access, add redaction, investigate copies |
| Secret updated but Task uses old value | Immutable process env or unrefreshed beans | Launch new Pod or integrate tested refresh mechanism |
| Two environments share credentials | Misconfigured Secret path/namespace/IAM | Separate roles and secrets by environment; controlled rotation |
| Worker lacks permission to write `BATCH_*` | Runtime user only granted `TASK_*` | Grant required DML/sequences for JobRepository |

## 18. Pre-Production Checklist for Tasks

| Check Question | Pass Criteria |
| --- | --- |
| Is any secret in Git/JAR/image/command line? | **No**, including Base64 forms |
| Are credentials isolated per environment? | Dev, CI, staging, and production have independent roles and secrets |
| Does the Pod/ServiceAccount have enough but not excess permissions? | RBAC/IAM/Vault policies follow least privilege |
| Are secrets delivered over a secure channel? | Secret reference/file or manager with TLS and verified identity |
| How are secret manager failures handled? | Fail safely; bounded retries; no plaintext fallback |
| Does JDBC use TLS and server verification? | Driver, CA/hostname/certificate configured properly |
| Does runtime have DDL privileges? | No, when using a separate migration account |
| Do TaskRepository/Batch store secrets? | CLI/JobParameters/ExecutionContext contain no credentials |
| Could logs/env/debug accidentally expose secrets? | Redaction and endpoint restrictions verified |
| Is secret rotation tested end-to-end? | Plan exists for dual credentials/drain/restart/lease |
| Are Tasks longer than secret TTL handled? | Renewal or proper deadlines configured; no assumption of auto-renewal |
| Is there an emergency revocation runbook? | Defined owner, revoke steps, audit, and safe retry |
| Could retries duplicate processed data? | Idempotency/checkpoints and business constraints in place |

## 19. Hands-On Exercises

**Exercise 1 — Data Classification.** Given `--business-date`, JDBC password, API token, JDBC hostname, CA certificate, Kubernetes ServiceAccount name, and Vault role, classify each into secrets, regular configuration, and identity/permission metadata. Explain cases where metadata can still be sensitive even if it is not a password.

**Exercise 2 — Kubernetes Env.** Create a **test Secret** in a dedicated namespace (do not use real passwords), and configure `secretKeyRef` to supply `TASK_DB_PASSWORD` to a Pod. Verify the Pod receives the reference properly **without printing** the Secret value.

**Exercise 3 — Configtree.** Create a Secret with keys `spring.datasource.username` and `spring.datasource.password`, and mount it at `/run/secrets/task-db/`. Configure `spring.config.import=configtree:...`, verify the Task initializes `DataSource`, and ensure no credentials exist in Git.

**Exercise 4 — Env Rotation.** Run a test Job, modify the Secret in the cluster, and observe the running process. Why doesn't the existing env change? Propose a safe rollout/restart strategy.

**Exercise 5 — Vault.** Design role `orders-task-reader` bound to namespace `batch-jobs` and ServiceAccount `orders-task-runner`, granting read access to only a single KV path. Explain why a root token must not be embedded in `application.yml`.

**Exercise 6 — Dynamic Credentials.** A Task has a 40-minute timeout while dynamic database credentials expire after 15 minutes. Analyze the risks and propose renewal or splitting into bounded Steps/Tasks.

**Exercise 7 — SQL Privileges.** Separate two accounts: `task_migrator` and `task_runtime`. List the DDL privileges needed for migrations and the minimal DML/sequence privileges needed for TaskRepository/JobRepository.

**Exercise 8 — Secret Exposure Scenario.** A past run used `--api-token=...`. List every place that must be investigated (Git, shell history, Pod specs, `TASK_EXECUTION_PARAMS`, Batch, logs, backups) and the token revocation sequence.

**Exercise 9 — Remote Partitioning.** A manager deploys four workers. Design credentials for the manager and workers so workers read only their partitions and share `JobRepository`, without automatically having permission to read all secrets.

**Exercise 10 — Incident.** A Pod hits `CreateContainerConfigError` due to a missing Secret, with no `TASK_EXECUTION` row. Write an investigation checklist and explain why this is not yet a Runner bug.

**Exercise 11 — TLS.** A JDBC URL uses TLS but disables certificate verification. State the risks, how to configure trust, and why fetching a password from Vault alone does not guarantee a secure connection channel.

**Exercise 12 — Auditing.** Design safe logging with `taskName`, `taskExecutionId`, `businessDate`, `secretReference` (allowlisted name only), `artifactVersion`, and result. Explain why you should not log token prefixes or password hashes for debugging.

## 20. Key Principles to Remember

1. **Spring Cloud Task needs secrets to connect to repositories and external services, but `TaskRepository` is not a secret store.**
2. **Never put passwords/tokens into CLI arguments or JobParameters**, as they can be stored in `TASK_EXECUTION_PARAMS`, `BATCH_*`, and orchestration systems.
3. **Kubernetes Secrets encode values in Base64, which is not data encryption.** Enable encryption at rest for `etcd` and apply proper RBAC.
4. **`secretKeyRef` and Secret volumes solve delivery**, not authorization, transport encryption, or lifecycle management.
5. **Process env vars do not change automatically after a Secret updates**; volumes may update, yet `DataSource`/beans still require reloading or restarting to use new values.
6. **Spring Boot `configtree:` lets mounted files be read as properties**; ensure key names, paths, and file permissions are correct.
7. **Vault/cloud secret managers should be accessed via workload identity**, with least privilege and TLS; avoid root tokens/static access keys in JARs.
8. **Dynamic credentials have distinct TTLs and re-issuance mechanics**; long-running Jobs must design renewal, connection pool behavior, and deadlines.
9. **Separate runtime users from migration users**, and separate TaskRepository, JobRepository, and business DB permissions where appropriate.
10. **Rotation, revocation, auditing, and idempotent retries must be tested**, rather than only checking that a Pod has an environment variable.
11. **A secret failure can occur before `TaskExecution` is created**; investigate via the launcher, Pod, secret manager, and startup logs.
12. **Log/record only enough metrics to investigate without secret values**, including in exceptions, trace attributes, and Actuator endpoints.

## References

- [Spring Cloud Task — Reference](https://docs.spring.io/spring-cloud-task/reference/): Task lifecycle and `TaskRepository`.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html): `TASK_EXECUTION_PARAMS` and related metadata tables.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): environment variables, placeholders, `configtree:`, and precedence.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): `secretKeyRef`, volumes, synchronized updates, and `subPath`.
- [Kubernetes — Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/): Base64, encryption at rest, RBAC, and access restrictions.
- [Kubernetes — Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/): protecting Secret data in `etcd`.
- [Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/): Pod identities and permission-scoped tokens.
- [Spring Cloud Vault — Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): `spring.config.import=vault://` and Vault configuration sources.
- [Spring Cloud Vault — Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html): Kubernetes authentication and other auth models.
- [Spring Cloud Vault — Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html): Vault configuration, TLS, and dependencies.
- [Secrets Store CSI Driver — Usage](https://secrets-store-csi-driver.sigs.k8s.io/getting-started/usage.html): mounting external secrets and optional sync capabilities.
- [Secrets Store CSI Driver — Auto Rotation](https://secrets-store-csi-driver.sigs.k8s.io/topics/secret-auto-rotation): conditions for enabling rotation and CSI rotation latency.
- [Prometheus — Instrumentation Best Practices](https://prometheus.io/docs/practices/instrumentation/): recording appropriate metrics/labels and avoiding secrets as metric labels.
