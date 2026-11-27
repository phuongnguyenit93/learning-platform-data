# ConfigMap, Secret, and ServiceAccount

## 1. Why do these three components matter for Spring Cloud Task?

**Spring Cloud Task** is used to build Spring Boot applications with a **finite runtime**: start up, receive parameters, perform work, record outcomes in **`TaskRepository`**, and terminate. When deployed to Kubernetes, a `Job` can spawn a Pod to run the task once, and a `CronJob` can create Jobs on a schedule.

An end-of-day reconciliation task typically needs at least:

- **Non-secret operational configuration:** profiles, task name, report output location, processing thresholds.
- **Credentials:** metadata database connection URL or account, passwords, tokens for external services.
- **Identity when interacting with the Kubernetes API:** is the Pod allowed to read other Pods, create Jobs, or read ConfigMaps via the API?
- **Termination policy:** when is a Job considered succeeded/failed, how does it retry, when does it expire, and where are logs and metadata retained?

Kubernetes provides three core objects for these needs:

1. **`ConfigMap`:** holds **non-secret** configuration separated from the container image.
2. **`Secret`:** stores or references sensitive data and exposes it to Pods when needed.
3. **`ServiceAccount`:** the workload's identity when calling the **Kubernetes API**; permissions are granted via RBAC or platform identity federation.

This lesson in the **Deployment** chapter brings all three together into a `Job` running Spring Cloud Task, explaining configuration flow, least privilege, and what to verify before production.

### Learning objectives

After this lesson, you will be able to:

- Pick the right object among `ConfigMap`, `Secret`, and `ServiceAccount` for each kind of data.
- Read and write Kubernetes manifests supplying configuration and credentials to a finite task.
- Explain `serviceAccountName`, `automountServiceAccountToken`, `Role`, and `RoleBinding`.
- Distinguish **Kubernetes ServiceAccount**, **database account**, **`imagePullSecret`**, and cloud workload identity.
- Configure a persistent `TaskRepository` connection and explain why in-memory H2 does not belong in production.
- Deploy the same image as an on-demand Kubernetes `Job` or a scheduled `CronJob`.
- Verify config loading, Secret/RBAC failures, exit codes, Job status, and task metadata.
- Plan secret rotation, retries, idempotency, and monitoring when a Pod terminates abnormally.

## 2. Comparison table: ConfigMap, Secret, ServiceAccount

| Object | Holds or represents | Good fit for | Should NOT be used to |
| --- | --- | --- | --- |
| **ConfigMap** | **Non-secret** key-value pairs or config files | `SPRING_PROFILES_ACTIVE`, `APP_REPORT_BUCKET`, processing mode | Store passwords, API tokens, private keys |
| **Secret** | Protected data exposed to containers via env or volumes | `SPRING_DATASOURCE_PASSWORD`, external tokens | Treat base64 as encryption |
| **ServiceAccount** | Kubernetes identity of a Pod | `daily-task-sa` | Store PostgreSQL passwords or replace SQL privileges |
| **Role/RoleBinding** | Permissions for an identity against Kubernetes API resources | Allowing `get` on one resource only when truly needed | Grant `cluster-admin` to every task |
| **DB role** | Database identity, **distinct from ServiceAccount** | `task_writer` with `INSERT/UPDATE` on `TASK_EXECUTION` | Access the Kubernetes API |
| **`imagePullSecret`** | Credentials for kubelet to pull private images | Registry secrets | Pass database passwords to the Java app |

**Important separation:** A `ServiceAccount` **does not grant PostgreSQL `SELECT/INSERT` privileges**. It is an identity solely for the Kubernetes API. For a task to write to `TaskRepository`, you still must configure a `DataSource` and proper database privileges.

For tasks that do not call the Kubernetes API, create a dedicated ServiceAccount yet **disable automatic API token mounting**. Having Kubernetes inject `ConfigMap`/`Secret` values into Pod environment variables **does not require the application itself to call the API to read those objects**.

## 3. Sample architecture

Assume the `daily-reconciliation` task reads business data for `2026-11-23` and records execution status in PostgreSQL.

~~~mermaid
flowchart LR
    U["Operator / CronJob controller"] --> J["Kubernetes Job"]
    J --> P["Spring Cloud Task Pod"]
    C[("ConfigMap: profile, task name, non-secret config")] --> P
    S[("Secret: DataSource credentials")] --> P
    SA["ServiceAccount daily-task-sa"] --> P
    P --> T[("PostgreSQL: TASK_EXECUTION / TASK_EXECUTION_PARAMS")]
    P --> B[("Business database")]
    P -. "Only if actively calling API" .-> K["Kubernetes API"]
    R["Role/RoleBinding if needed"] -. "Authorizes" .-> K
~~~

There are three security boundaries:

1. **Kubernetes control plane:** who or which controller may create Jobs, Pods, ConfigMaps, Secrets, ServiceAccounts, and RoleBindings.
2. **Container runtime:** which env vars/config files the Java process receives and whether a Kubernetes API token is mounted.
3. **Database and external systems:** whether the connecting account may write `TaskRepository` metadata and run business logic; this permission boundary is **independent** of Kubernetes RBAC.

Never grant cluster-admin permissions to a task process merely because the orchestrator must create Pods. When Spring Cloud Data Flow or a Kubernetes controller creates Jobs, **the orchestrator's identity** and **the task Pod's identity** must be authorized separately.

## 4. Preparing a finite Spring Cloud Task application

The Spring Boot example below parses a date argument, runs synchronous business logic, and returns. Business logic is abbreviated to focus on deployment.

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReconciliationApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyReconciliationApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(
                DailyReconciliationApplication.class, args);
    }

    @Bean
    ApplicationRunner reconcile() {
        return args -> {
            List<String> dates =
                    args.getOptionValues("businessDate");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                        "Required: --businessDate=yyyy-MM-dd");
            }

            LocalDate day = LocalDate.parse(dates.get(0));
            log.info("RECONCILIATION_BEGIN day={}", day);

            // Execute synchronous business logic.
            // If it fails, do not silently swallow exceptions.

            log.info("RECONCILIATION_DONE day={}", day);
        };
    }
}
~~~

Configuration baked into the image, e.g., `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      initialize-enabled: false
~~~

- `web-application-type: none` avoids launching an unnecessary HTTP server for a CLI task.
- `initialize-enabled: false` means the `TaskRepository` schema **must already exist** via migrations; use only when schemas are managed externally.
- `@EnableTask` enables Spring Cloud Task integration in the example.
- `ApplicationRunner` returns only once business logic finishes; do not spawn background work and return before results are written.
- Package compatible versions of Spring Cloud Task, JDBC drivers, and configuration matching the project's Spring Boot version. The container image must contain the JAR at the path referenced by the Kubernetes manifest.

To persist metadata across multiple Pods, use PostgreSQL/MySQL or a suitable database rather than an isolated in-memory H2 instance per Pod. **`TaskRepository`** tracks timing and outcomes per launch; business data and retry checkpoints must still be managed explicitly.

## 5. ConfigMap: non-secret configuration

Example `task-config.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: daily-task-config
  namespace: batch-jobs
data:
  SPRING_APPLICATION_NAME: "daily-reconciliation"
  SPRING_PROFILES_ACTIVE: "task"
  APP_REPORT_BUCKET: "reports-demo"
  APP_RECONCILE_MODE: "safe"
~~~

Every value under `data` is a string. With `envFrom.configMapRef`, each valid key becomes an environment variable inside the container.

| Key | Purpose |
| --- | --- |
| `SPRING_APPLICATION_NAME` | Application name used by Spring Boot and Spring Cloud Task for task naming |
| `SPRING_PROFILES_ACTIVE` | Activates a profile already packaged in the image |
| `APP_REPORT_BUCKET` | Example non-secret business bucket name |
| `APP_RECONCILE_MODE` | Illustrative business mode interpreted by the app |

**Never put secrets into a ConfigMap.** Even if labeled "configuration", passwords, private keys, bearer tokens, or credentialed connection strings remain sensitive data.

### Two ways to consume values from a ConfigMap

Import **all** valid keys:

~~~yaml
envFrom:
  - configMapRef:
      name: daily-task-config
~~~

Import **a specific key**, optionally under a different env var name:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    valueFrom:
      configMapKeyRef:
        name: daily-task-config
        key: SPRING_PROFILES_ACTIVE
~~~

When complex configs require files rather than env vars, a ConfigMap can also be mounted as a volume. With Spring Boot, explicitly configure the app to read that mount path; mounting alone does not make Spring auto-load arbitrary files.

### Update behavior

ConfigMaps injected via **environment variables** are resolved only when the container is created; editing the ConfigMap **does not update env vars in already-running Pods**. For finite task apps, a cleaner approach is creating a new Job pinned to an explicit image/config version. ConfigMap volume mounts update differently, though the app still needs reload logic if changes during execution matter.

**Never rely on mutating a ConfigMap mid-flight to alter parameters of a running `TaskExecution`.** Doing so undermines reproducibility.

## 6. Secret: passwords and tokens must never be hardcoded

A task targeting a PostgreSQL metadata database may receive:

- `SPRING_DATASOURCE_URL` — JDBC URL (may be treated as sensitive infrastructure info depending on policy).
- `SPRING_DATASOURCE_USERNAME` — database principal.
- `SPRING_DATASOURCE_PASSWORD` — password requiring protection.

In the example, all three live in a Secret named `daily-task-db` in namespace `batch-jobs`. Those **key names** are the interface expected by the Job manifest; **real values must come from an approved secret manager or provisioning workflow**.

### 6.1. Creating Secrets from a secure source

Lab example commands (**not executed during authoring of this guide**):

~~~bash
kubectl create namespace batch-jobs

kubectl create secret generic daily-task-db \
  --from-env-file=./daily-task-db.local.env \
  --namespace=batch-jobs
~~~

`daily-task-db.local.env` is created temporarily from an authorized secret source with exact keys `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD`. **Never commit that file to Git, print its contents to console/logs, and dispose/store it per security policy.** In production, prefer syncing Secrets from a secret vault or protected CI/CD pipeline.

If storing Secret YAML manifests, never mistake `stringData` or base64-encoded `data` for real security: anyone able to read Secrets via the Kubernetes API can decode them. **Enable encryption at rest for Kubernetes Secrets (cluster config), enforce RBAC, auditing, and restrict access to etcd backups.**

### 6.2. Injecting Secrets into a Pod

Example importing all matching environment variable names:

~~~yaml
envFrom:
  - secretRef:
      name: daily-task-db
~~~

Or a single variable:

~~~yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: daily-task-db
        key: SPRING_DATASOURCE_PASSWORD
~~~

Kubernetes injects the value into the container; Spring Boot binds `SPRING_DATASOURCE_PASSWORD` to `spring.datasource.password`. **Never pass Secrets via CLI flags like `--spring.datasource.password=...`**, as command-line arguments leak readily via process metadata and observability tools.

### 6.3. Mounting Secrets as files

Some libraries require certificates or credentials on disk. In those cases, use `volume.secret` and `volumeMounts` instead of env vars. However, **Spring Boot does not auto-read arbitrary file paths**: configure specific properties/config trees or library code to load the certificates.

Update differences:

| Injection method | When the Secret changes | How to handle |
| --- | --- | --- |
| **Environment variable** | Running Pods **do not pick up new values** | Launch a new Pod/Job or perform controlled restarts |
| **Secret volume** | Kubelet may refresh mounted files after a delay | App must support reloading; avoid `subPath` if updates are needed |
| **Already-open connections** | Rotating a Secret password does not auto-refresh pools or active sessions | Plan credential rotation and connection recreation |

For finite tasks, binding each run to an immutable config/secret version until exit is far cleaner than changing parameters mid-flight.

## 7. ServiceAccount: the Pod's identity for the Kubernetes API

Every Pod runs under a `ServiceAccount` in its namespace. If unspecified, Pods fall back to the `default` ServiceAccount. Create a **dedicated ServiceAccount for the task app** so it does not inherit overly broad permissions attached to `default`.

Example `task-sa.yaml`:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: daily-task-sa
  namespace: batch-jobs
automountServiceAccountToken: false
~~~

When the Pod does not call the Kubernetes API, `automountServiceAccountToken: false` prevents automatically mounting an API token inside the container. This setting can also be placed on the **Pod spec**; if both the Pod spec and ServiceAccount specify it, the Pod spec wins.

### 7.1. Three identities often confused

| Identity | Example | Verified by |
| --- | --- | --- |
| Kubernetes **ServiceAccount** | `system:serviceaccount:batch-jobs:daily-task-sa` | Kubernetes API |
| **Database user** | `task_writer` | PostgreSQL, MySQL, etc. |
| **Cloud workload identity** | IAM role/service account bound to a Kubernetes ServiceAccount | Cloud provider and its federation mechanism |

A Kubernetes ServiceAccount **does not automatically become** an IAM role or DB user. If the app uses workload identity federation to read a cloud bucket, configure the trust relationship/binding per cloud provider. If using a DB password in a Secret, the DB user still needs the right SQL grants.

### 7.2. Does this task need a Role/RoleBinding?

**No**, if the Java app simply reads env vars, reads/writes databases, and exits **without calling the Kubernetes API**. Kubernetes still injects ConfigMaps and Secrets into the Pod per spec; the Java process does not need `get secrets` API permissions.

**Possibly yes**, if application code explicitly calls the Kubernetes API—such as querying another Pod's status or fetching a dynamic ConfigMap via a client. In that case:

1. Grant a **Role** restricted to the exact verbs/resources within the namespace.
2. Create a **RoleBinding** attaching that Role to the specific ServiceAccount.
3. Ensure the Pod receives Kubernetes API auth credentials (controlled token mount or projected token).
4. Never grant permissions to create/modify Pods, Jobs, or read Secrets unless business logic truly requires them.

Example **solely for a worker needing to read Pods via the Kubernetes API** (not needed for the sample task in the next section):

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-status-reader
  namespace: batch-jobs
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: task-pod-status-reader
  namespace: batch-jobs
subjects:
  - kind: ServiceAccount
    name: daily-task-sa
    namespace: batch-jobs
roleRef:
  kind: Role
  name: pod-status-reader
  apiGroup: rbac.authorization.k8s.io
~~~

`Role` scopes permissions to a namespace; `RoleBinding` binds it to an identity. If an app needs the K8s API via a default service account token, configure `automountServiceAccountToken` deliberately. **Do not apply this Role/RoleBinding to tasks that never call the Kubernetes API**, as that violates least privilege.

## 8. Complete Job manifest for Spring Cloud Task

Assumed prerequisites:

- Namespace `batch-jobs`.
- ConfigMap `daily-task-config` (Section 5).
- Secret `daily-task-db` (Section 6) containing the three JDBC keys.
- ServiceAccount `daily-task-sa` (Section 7).
- Image `registry.example.com/tasks/daily-reconciliation:1.4.2` containing the Java runtime, `/app/task.jar`, and JDBC driver compatible with the metadata DB/schema.
- Database already initialized with migrations for your Spring Cloud Task version.

Manifest `daily-task-job.yaml`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-reconciliation-20261123
  namespace: batch-jobs
  labels:
    app: daily-reconciliation
    business-date: "2026-11-23"
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: daily-reconciliation
    spec:
      serviceAccountName: daily-task-sa
      automountServiceAccountToken: false
      restartPolicy: Never
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: task
          image: registry.example.com/tasks/daily-reconciliation:1.4.2
          imagePullPolicy: IfNotPresent
          command: ["java", "-jar", "/app/task.jar"]
          args:
            - "--businessDate=2026-11-23"
          envFrom:
            - configMapRef:
                name: daily-task-config
            - secretRef:
                name: daily-task-db
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
~~~

### 8.1. Explaining each choice

| Property | Meaning | Deployment note |
| --- | --- | --- |
| `apiVersion: batch/v1`, `kind: Job` | Runs a finite workload | Avoid `Deployment` unless a continuous service is needed |
| `metadata.namespace` | Scopes resources and permissions | Referenced Secrets/ConfigMaps must live in the same namespace |
| `backoffLimit: 0` | Lab avoids auto-spawning retry Pods on failure | Increase in production only if retries are **idempotent** |
| `activeDeadlineSeconds: 1800` | Caps total Job duration (illustrative 30 minutes) | Hitting the deadline can kill the task before `TaskRepository` updates |
| `ttlSecondsAfterFinished: 86400` | Job eligible for cleanup 24 hours after completion | Does not delete `TaskRepository` rows; Pods and local logs may disappear |
| `restartPolicy: Never` | Failed container does not restart inside the same Pod | Job controller can still spawn a replacement Pod if retries are enabled |
| `serviceAccountName` | Selects the task's Kubernetes identity | Does not grant SQL or Cloud IAM rights by name alone |
| `automountServiceAccountToken: false` | Omits API token for tasks not calling the API | Change if the app calls the API using an approved auth model |
| `envFrom` | Imports env vars from ConfigMap and Secret | Missing refs/keys prevent the Pod from starting properly |
| `resources` | CPU/RAM limits | `OOMKill` can leave `TaskExecution` without an end timestamp |
| `runAsNonRoot` | Restricts container process privileges | Image/JAR must allow the specified UID to execute and read files |
| `command`/`args` | Launches Java JAR with business arguments | Never put passwords in `args` |
| `terminationGracePeriodSeconds` | Window to handle `SIGTERM` | Does not guarantee completion before `SIGKILL` or deadlines |

**This Job is a learning example, not a default production spec.** Tune timeouts, resources, and image versions from real load tests. `runAsNonRoot` works only if image file permissions allow that UID. If the app writes temporary files, mount an appropriate volume or writable path rather than disabling security controls.

### 8.2. Illustrative apply workflow

Commands below are **illustrative**, run in a test cluster by an operator with proper permissions:

~~~bash
kubectl apply -f task-config.yaml
kubectl apply -f task-sa.yaml

# Ensure Secret daily-task-db was created securely.
kubectl get secret daily-task-db -n batch-jobs

kubectl apply -f daily-task-job.yaml

kubectl get job daily-reconciliation-20261123 -n batch-jobs
kubectl describe job daily-reconciliation-20261123 -n batch-jobs
kubectl logs job/daily-reconciliation-20261123 -n batch-jobs
~~~

`kubectl get secret` merely confirms the object name; **never run commands dumping decoded Secret values** into logs or shared docs. If multiple retry Pods exist, collect logs per Pod and ship them to centralized storage before TTL cleanup removes Jobs/Pods.

**Never invoke these `kubectl` commands from inside a business task process just to inspect itself.** Operations and `kubectl` access belong to pipelines/controllers or administrators, not business containers.

## 9. From on-demand Job to scheduled CronJob

When work must run periodically, move the Pod template into a `CronJob`. Abbreviated example preserving `ConfigMap`, `Secret`, and `ServiceAccount`:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
  namespace: batch-jobs
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          serviceAccountName: daily-task-sa
          automountServiceAccountToken: false
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example.com/tasks/daily-reconciliation:1.4.2
              command: ["java", "-jar", "/app/task.jar"]
              args:
                - "--runMode=daily"
              envFrom:
                - configMapRef:
                    name: daily-task-config
                - secretRef:
                    name: daily-task-db
~~~

**Important:** `--runMode=daily` is only an illustrative business argument; Section 4's sample app only reads `--businessDate=...`. To use this CronJob, **add deterministic logic resolving the target processing period from the schedule or work key**. Never compute "yesterday" blindly off the Pod's wall clock without defining timezone, late-start handling, and backfill behavior. A stricter approach uses an orchestrator passing an explicit business date.

`concurrencyPolicy: Forbid` only prevents overlapping Jobs **created by that same CronJob**; manual launches, other CronJobs, or Spring Cloud Data Flow can still start the same task name. If multiple triggers can target the same job, enforce idempotency/business locks at the data layer.

Older Kubernetes versions do not support `timeZone` on CronJobs; verify your cluster version before relying on it.

## 10. TaskRepository and Kubernetes Job outcomes are not identical

Even once a Job is created, multiple distinct stages remain:

~~~mermaid
sequenceDiagram
    participant K as Kubernetes Job Controller
    participant P as Pod / Spring Boot Task
    participant R as TaskRepository
    participant B as Business Database

    K->>P: Create Pod, inject env + identity
    P->>R: Record TaskExecution START_TIME
    P->>B: Execute business logic
    B-->>P: Commit results
    P->>R: Record TaskExecution END_TIME / EXIT_CODE
    P-->>K: Exit process with OS exit code
    K->>K: Evaluate Job status / retries
~~~

| Signal | Source | Limitation to understand |
| --- | --- | --- |
| `Pod Running` | Kubernetes | Java app may still be bootstrapping or not yet connected to DB |
| `TaskExecution START_TIME` | `TaskRepository` | Task recorded start metadata; does not prove business completion |
| `TaskExecution EXIT_CODE/END_TIME` | `TaskRepository` | Framework records lifecycle outcome if reached in time |
| **OS exit code** | Process/container | Kubernetes relies on exit status; can diverge from business reality if exceptions were mishandled |
| `Job Complete` / `Job Failed` | Kubernetes Job controller | Reflects Pod/retry/deadline policy; does not verify business data |
| Table/report output | Target database or system | Verify by business key to avoid duplicate side effects |

**A Pod killed by `OOMKilled`/`SIGKILL` may fail to write `TASK_EXECUTION.END_TIME`.** Metadata may then appear stuck running even though the Pod is dead. Operators must cross-check Pod/Job status, logs, and business outputs.

### When integrating Spring Batch

If the task runs Spring Batch, `JobRepository` stores `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION` alongside `TaskRepository`. A failed Batch Job **must never silently map to process exit 0**; configure error/exit-code propagation appropriate for your integration version and verify with integration tests before Kubernetes uses exit codes to decide retries.

Never call `System.exit(0)` unconditionally at the end of a runner to "close the task", as it can report false success.

## 11. API permissions, Secrets, and separation of responsibilities

### 11.1. Permissions of the Job creator differ from the task Pod

When the Kubernetes CronJob controller spawns a Job, the controller uses its own infrastructure identity and permissions. When **Spring Cloud Data Flow** or an orchestrator app uses `TaskLauncher` to create Jobs, **the deployer/SCDF identity** needs Kubernetes API permissions to create Jobs/Pods in the target namespace.

**Never grant `create jobs` to `daily-task-sa` simply because the task runs inside a Job.** The task container only needs that permission if its own business logic calls the API to spawn other Jobs.

### 11.2. Are Kubernetes API permissions needed to use a Secret?

With `envFrom.secretRef`, the container **does not** call `GET /api/v1/namespaces/.../secrets/...` to fetch environment values. Kubelet performs the injection per Pod spec within platform controls. Hence, a Role granting `get secrets` is usually **excessive and risky** for apps that do not actively call the Kubernetes API.

If an application truly needs dynamic Secrets via the Kubernetes API, revisit the architecture; using an external secret manager, projected volumes, or workload identity is often safer than granting broad RBAC Secret read access.

### 11.3. Secrets do not replace NetworkPolicies or DB grants

A Pod holding the right password can still fail to reach the DB if:

- DNS fails to resolve `metadata-db.internal`.
- NetworkPolicies block egress or DNS traffic.
- Database firewalls/VPC rules reject the Pod's source IP.
- The DB role lacks grants on `TASK_EXECUTION` tables or ID sequences.
- The metadata schema has not been migrated to the matching version.
- TLS certificates or truststores mismatch.

Conversely, allowing egress to the DB **does not** grant SQL privileges. Verify all three: **network, credentials, and schema/grants**.

## 12. Rotating configuration and Secrets safely

### 12.1. Recommended workflow

1. **Provision new credentials** in the DB or secret manager, keeping a transition overlap window where needed.
2. **Update the Secret** through an approved pipeline and confirm key names remain compatible.
3. **Launch a new Job** or replace Pods to pick up updated env vars; running Pods never refresh env vars automatically.
4. **Monitor connectivity and `TaskRepository` results** across new runs.
5. **Revoke old credentials** once no active Pods or connection pools still use them.
6. **Audit** changes, access permissions, and which environments received the updated secret.

Never rotate a password mid-long-transaction while expecting existing connection pools to re-authenticate instantly. Whenever updating a `ConfigMap` or `Secret`, tag deployments with a revision/label so every run traces back to its exact configuration.

### 12.2. Storing logs in the right place

If `ttlSecondsAfterFinished` removes Jobs/Pods, local Pod logs vanish too. Ship stdout/stderr to centralized logging indexed by Job name, Pod UID, business key, and `TASK_EXECUTION_ID` when available. **Never log all environment variables**, as they may contain Secret-injected passwords.

## 13. Common issues

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Pod stuck in `CreateContainerConfigError` | Referenced ConfigMap/Secret missing or missing required key | Run `kubectl describe pod` and check namespace/name; never dump secrets |
| Pod runs with wrong profile | `SPRING_PROFILES_ACTIVE` missing, typoed key, or overridden elsewhere | Check ConfigMap, app startup logs, and property precedence |
| Spring Boot missing JDBC URL | Secret lacks `SPRING_DATASOURCE_URL` or key name differs | Verify key names and env binding without printing secret values |
| PostgreSQL `authentication failed` | Stale username/password or wrong DB | Check rotation, SQL roles, and network |
| `permission denied for relation` | DB role lacks grants on `TaskRepository` | Check role grants on tables, sequences, and schema |
| `No suitable driver` | Image missing JDBC driver | Check dependencies/runtime image |
| `relation task_execution does not exist` | Schema not migrated or wrong namespace/schema/prefix | Verify DDL/version and DataSource |
| ServiceAccount `Forbidden` calling Kubernetes client | Missing RoleBinding, wrong namespace, or token disabled | Check `serviceAccountName`, `automount...`, and RBAC rules |
| Cannot pull image | Wrong registry credentials/`imagePullSecret` or missing image | Inspect Pod Events, `imagePullSecrets`, and registry |
| Job `Failed`, `TaskRepository` missing `END_TIME` | Pod killed before metadata update step | Inspect `terminated.reason`, exit code, logs, and business data |
| Job `Complete` yet business outcome wrong | Runner swallowed errors or Batch job failure didn't propagate exit code | Check real business state and error propagation |
| Task ran twice | Job controller retry, overlapping CronJob, manual run, or external trigger | Inspect Job history, business keys, and idempotency |
| Secret updated yet task uses old value | Existing Pod environment does not auto-refresh | Start a new Pod/rollout per policy |
| Logs missing after one day | TTL deleted Job/Pod | Collect logs centrally prior to cleanup |

### Safe inspection commands

~~~bash
kubectl get jobs -n batch-jobs
kubectl get pods -n batch-jobs -l app=daily-reconciliation
kubectl describe job daily-reconciliation-20261123 -n batch-jobs
kubectl logs job/daily-reconciliation-20261123 -n batch-jobs
kubectl get configmap daily-task-config -n batch-jobs
kubectl get serviceaccount daily-task-sa -n batch-jobs
~~~

Only authorized operators should run these commands. `describe` on a Pod typically shows Secret name references and non-secret configuration; still review output before sharing. **Never run `printenv`, `env`, or decode Secrets to debug in production.**

### Checking ServiceAccount permissions when actually calling the Kubernetes API

~~~bash
kubectl auth can-i get pods \
  --as=system:serviceaccount:batch-jobs:daily-task-sa \
  --namespace=batch-jobs
~~~

The `yes/no` output depends on active RoleBindings and the caller's impersonation permissions. For the `daily-task-sa` manifest that needs no API access, **there is no reason the answer must be `yes`**. `automountServiceAccountToken=false` controls credential mounting; RBAC `can-i` checks a separate authorization layer.

## 14. Deployment test scenarios

### Scenario A — Valid ConfigMap, Secret, and DB

1. Provision `daily-task-config`, `daily-task-db`, and `daily-task-sa` in the target namespace.
2. Verify the image/driver and migrated `TaskRepository` schema.
3. Apply the Kubernetes Job manifest.
4. Wait for the Pod to bootstrap, run business logic, and exit.
5. Reconcile Job/Pod exit codes against `TASK_EXECUTION` and business outputs.
6. Confirm no secrets appear in logs, command args, or shared docs.

### Scenario B — Missing Secret

1. In a lab namespace, point the Job at a nonexistent Secret name.
2. Observe the Pod failing to create the container or reporting a config error.
3. Check `kubectl describe pod` to identify the broken Secret reference; **never print secret values**.
4. Fix the Secret name and create a **new Job** rather than patching the immutable Pod template of an existing Job.

### Scenario C — Missing SQL privileges

1. Use a lab DB role granted only `SELECT`.
2. Run the task; it will likely fail when the framework tries to insert/update `TaskExecution`.
3. Inspect `permission denied` logs and verify the DBA granted proper table/sequence privileges.
4. Restore the `task_writer` role with exact required grants rather than granting superuser.

### Scenario D — Disabled Kubernetes API token mount

1. Set `automountServiceAccountToken: false`.
2. Run a task that only reads env vars and writes to DB; it should run normally.
3. In a separate test app with a Kubernetes client, call the API and observe auth failing without other credentials.
4. If business logic genuinely needs the API, provision minimal identity and Role grants instead of enabling token mounting indiscriminately across workloads.

### Scenario E — Pod terminated mid-processing

1. In a lab cluster, run a long task on idempotent data.
2. Set a short deadline to test controlled failure.
3. Observe `Job Failed` alongside a potentially missing `END_TIME` in `TaskRepository`.
4. Verify committed outputs, business keys, and checkpoints before retrying.
5. Never treat `EXIT_CODE=0` or `Job Complete` as sole proof that business data is accurate.

## 15. Pre-production checklist

### Configuration

- [ ] Non-secret `ConfigMap` separated from credential `Secret`s.
- [ ] No passwords/tokens in ConfigMaps, Git manifests, images, or CLI args.
- [ ] Environment variable keys align with Spring Boot/Spring Cloud Task properties.
- [ ] Application runs as a finite process; no unnecessary HTTP server or background threads.
- [ ] Every run carries an explicit image/config version and business key.

### Identity and security

- [ ] Workload groups have dedicated ServiceAccounts where privilege isolation is needed.
- [ ] Tasks not calling the Kubernetes API disable automatic API token mounting.
- [ ] `Role`/`RoleBinding` granted only when application code genuinely calls the Kubernetes API.
- [ ] Launcher/deployer identity is not conflated with task Pod identity.
- [ ] DB role holds required DML grants, without broad DDL/superuser rights.
- [ ] Secret RBAC, encryption at rest, network/TLS, and rotation are enforced.
- [ ] Private registries use `imagePullSecret`/workload identity separate from DB credentials.

### Operations

- [ ] Job `restartPolicy`, `backoffLimit`, deadlines, and resource limits fit the workload.
- [ ] CronJob `concurrencyPolicy` matches requirements; remember its scope covers only that CronJob.
- [ ] `TaskRepository` schema is migrated to the matching version on a persistent DataSource.
- [ ] Business errors drive accurate Job/process exit status; exceptions are never swallowed.
- [ ] Idempotency/checkpoints support safe retries if a Pod is killed.
- [ ] Centralized logging is enabled since TTL deletes Jobs/Pods.
- [ ] Tested missing Secrets, RBAC errors, DB connectivity, OOMs, timeouts, and secret rotation.
- [ ] Clear runbook exists to reconcile Kubernetes Jobs with `TaskExecution` and business outputs.
- [ ] Team knows how to inspect Pod Events without exposing secrets or granting excessive permissions.

## 16. Key takeaways

**`ConfigMap` stores non-secret configuration; `Secret` delivers sensitive data; `ServiceAccount` defines Pod identity toward the Kubernetes API.** They solve distinct problems and are not interchangeable. For **Spring Cloud Task** running inside a Kubernetes Job/CronJob, use each for its intended purpose, separate infrastructure permissions from database permissions, and apply least privilege.

A healthy deployment means more than a Pod reaching `Succeeded`. It must **persist `TaskRepository` to a durable database**, surface failures cleanly, avoid leaking credentials, support idempotent retries, and retain enough operational evidence to investigate if a Pod is killed before completion metadata is saved.

### References

- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Kubernetes — RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — TTL-after-finished Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/)
- [Spring Cloud Task — Features / DataSource / TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/3.2/appendix-task-repository-schema.html)
