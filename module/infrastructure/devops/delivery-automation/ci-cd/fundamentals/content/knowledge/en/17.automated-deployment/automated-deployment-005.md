# Verifying Pre-Deployment Conditions and Target Access Permissions

A pipeline can build and test successfully yet still not be eligible to deploy. The artifact may be the wrong version, the target environment may be unstable, configuration may be incomplete, the schema may be incompatible, or the job identity may lack permissions to perform the required operation. Discovering these issues mid-deployment can leave the system in a broken partial state or cause a service outage.

Before modifying an environment, the pipeline must run a preflight step to verify both sets of conditions: whether the environment is ready to accept the change, and whether the workload has the proper identity and permissions to modify that environment. Checks must be tied to a specific artifact and target, produce clear results, be traceable, and run close enough to deployment time to avoid relying on stale results.

This lesson belongs to the automated deployment section of CI/CD. It connects verified artifacts, environment configuration, workload identity, and environment protection mechanisms into a decision gate prior to deployment.

## 1. Why Are Pre-Deployment Gates Needed?

A pre-deployment gate is the set of conditions that must be met before a pipeline is allowed to start modifying a target environment. A gate may run automated checks, require human approval, or combine both.

Typical errors a gate must catch:

- The artifact does not belong to the expected commit or release.
- Artifact digest or signature does not match trusted metadata.
- The artifact has not passed required checks or has vulnerabilities exceeding policy thresholds.
- The target environment is experiencing an incident, overload, or maintenance window.
- Runtime, database schema, or API versions are incompatible.
- Required configuration or secret references are missing.
- The job is targeting the wrong cluster, namespace, account, region, or tenant.
- The deployer identity lacks required permissions or holds permissions beyond the scope of work.
- Another release is concurrently modifying the same resources.
- Required approval or change record is missing per policy.

If a gate only checks a generic state such as "CI is green," it does not prove that the specific artifact and target environment are ready. A pipeline must know exactly which artifact it will deploy, where it will deploy, under which identity, and with what operation.

## 2. Distinguishing Deployment Conditions from Access Permissions

These two check groups are related but do not replace one another.

**Deployment conditions** answer: "Should this change be executed right now?" For example, the artifact is verified, the environment is healthy, configuration is valid, migrations are compatible, and approval has been granted.

**Target access permissions** answer: "Is the job's identity permitted to perform this exact operation on that resource?" For example, the job has permission to update a Deployment in the staging namespace, but not to delete a Secret or modify the production namespace.

An environment may be ready while the job lacks deploy permissions. Conversely, a job with deploy permissions may still be rejected by the gate because the environment is in maintenance or the artifact fails quality checks.

Keep both checks independent. Never use human approval as a substitute for machine permission checks, and never treat successful authentication as proof that a release is safe to deploy.

## 3. Defining the Deployment Request Clearly

Before running checks, the pipeline needs a deployment request with enough information for every step to evaluate a consistent target.

A request typically includes:

- Application or service name.
- Target environment: development, staging, or production.
- Target cluster/account/region/namespace/tenant.
- Artifact name, version, and digest.
- Source commit and build run that produced the artifact.
- Configuration or deployment manifest version.
- Operation type: fresh deploy, update, migration, rollback, or scale.
- Intended executing workload identity.
- Change ID or approval record, if any.
- Deployment strategy and rollout limits.

Do not derive the target from an unvalidated free-form string entered by a user. A typo in a namespace or account name can cause the pipeline to deploy somewhere unintended. Use predefined choices, allowlists, or controlled mappings from environment to target.

For example, selecting production must map to the exact production account, cluster, and namespace. Never let a script infer the target from a branch name or an uncontrolled variable.

## 4. Groups of Conditions to Verify

A thorough preflight can be divided into the following groups:

| Group | Question | Example Evidence |
|---|---|---|
| Artifact | Is this the exact approved package? | Version, digest, signature, provenance |
| Quality | Have required checks passed? | Test report, scan, quality gate |
| Environment | Is the target ready to receive changes? | Health, capacity, maintenance state |
| Compatibility | Is the new version compatible with runtime and dependencies? | Runtime matrix, schema compatibility |
| Configuration | Are required values present and valid? | Config validation, secret references |
| Dependencies | Are required databases, brokers, networks, or services available? | Health/readiness and dependency checks |
| Permissions | Does the job have the right permissions on the right target? | Identity claims, IAM/RBAC check |
| Coordination | Is another release modifying the same target? | Lock, deployment queue |
| Policy | Are approval, change window, or compliance conditions met? | Approval record, policy result |
| Recovery | Is a feasible rollback or forward-fix plan in place? | Previous version, backup, rollback plan |

Not every application needs every check. Teams should select based on system type, blast radius, and change risk. However, mandatory conditions must be written explicitly so the gate makes consistent decisions.

## 5. Verifying the Artifact Before Targeting an Environment

The deployed artifact must be the one built and verified in the pipeline. Do not rebuild a different version at deploy time just because production needs different configuration.

Typical checks include:

- Version or release identifier matches the deployment request.
- Digest matches release metadata.
- Signatures and provenance are valid per policy if required.
- Artifact originates from an authorized repository and revision.
- Required tests, security scans, and quality gates passed.
- Artifact matches the required OS/architecture/runtime variant.
- Package or image is pullable from the target registry.

For container images, reference the digest rather than relying only on mutable tags. For JARs or ZIPs, verify checksums against trusted metadata. Checking only a checksum downloaded alongside the file from an untrusted source may be insufficient if both were replaced.

The gate should record the verified artifact digest and pass that exact identifier to the deploy step. If the artifact changes after preflight, prior gate results no longer apply.

## 6. Checking Target Environment Health and State

Before deploying, know the current state of the target environment. Common checks include:

- Are the control plane or API endpoints reachable?
- Is the current service healthy or experiencing an incident?
- Is there sufficient CPU, memory, disk, pod quota, or connection capacity?
- Are the database and message broker available?
- Are critical maintenance or backup jobs currently running?
- Is another deployment currently rolling out or migrating?
- Is the environment in a degraded state that should be preserved for investigation?

Health checks should rely on signals meaningful for deployment decisions. An HTTP endpoint returning 200 does not necessarily prove the database, queue, or downstream dependencies are healthy. If the service is already in an incident, a new change can complicate root-cause analysis or add load to the system.

Do not apply one generic capacity threshold to every application. Account for requests/limits, autoscaling, replica counts, remaining headroom, and dependency load tolerance. If a rollout runs old and new replicas concurrently, the environment must have enough capacity for that overlap phase.

## 7. Checking Runtime and Dependency Compatibility

A valid artifact can still fail to run in the target environment if runtime or dependencies are incompatible.

For Java applications, checks may include:

- Supported JRE/JDK version.
- OS and native library versions.
- Database driver and database version.
- Current schema and post-migration schema.
- APIs or message schemas consumed by other services.
- CPU architecture and base image.
- Sidecar, agent, or service mesh versions, if applicable.

Compatibility checks must consider both application changes and current environment state. A migration adding only a nullable column may be compatible with the old version; dropping or renaming a column in the same release can break running old instances before the rollout finishes.

Prefer the expand-and-contract strategy for schema changes when multiple application versions coexist: add the new structure, deploy compatible code, migrate data and usage, and only then remove the old structure in a later release.

If compatibility cannot be proven, the gate should halt or require a separate migration plan. Never assume a successful build implies runtime compatibility.

## 8. Validating Configuration and Secret References

Configuration must be valid before updating the application. Checks may include:

- Required variables are declared.
- Values match expected formats, enums, and bounds.
- URLs point to the right service or environment.
- Ports and hostnames are reachable.
- ConfigMaps or configuration bundles exist.
- Secret references exist and are readable by the runtime workload.
- Feature flags and rollout settings are appropriate.
- Dangerous default values are not accidentally used in production.

A deploy pipeline typically does not need to read secret contents. It can validate references, access permissions, or existence via authorized mechanisms without printing secrets to logs. The application or runtime workload is the component that consumes secrets at runtime.

Separate secret-read permissions from deployment-update permissions. For instance, a deployer may be allowed to update a Deployment referencing an existing Secret without having permission to read that Secret's value. This reduces the risk of credentials leaking through a deploy job.

Never write secrets into manifests stored inside shared artifacts. Use a secret manager, workload identity, or platform runtime injection.

## 9. Checking Dependencies and Operational Readiness

A deployment may require multiple systems to be ready before starting:

- The database can accept connections and migrations can run safely.
- The message broker has sufficient quota or topics are already created.
- The registry can serve images/packages.
- DNS, network policies, firewalls, and service endpoints permit connectivity.
- The secret manager can issue credentials to the runtime workload.
- Certificates are valid with an intact trust chain.
- Monitoring, logging, and alerting can ingest signals from the new version.

Not every dependency must be called from the runner. Some checks must run from the target environment's network or identity because the runner may have different network paths and permissions than the application. For example, a runner being able to pull an image does not guarantee cluster nodes have permission to pull it.

For dependencies accessed only by the workload, verify them using appropriate mechanisms such as pre-deployment probes, canaries, or post-deployment verification. Avoid granting extra production permissions to runners solely to probe network paths used only by the runtime workload.

## 10. Authentication and Authorization at the Target

When accessing the target environment, the pipeline must prove its identity and receive strictly scoped permissions.

**Authentication** verifies who the job is. This can use OIDC federation, workload identity, service accounts, or platform-issued credentials.

**Authorization** determines which actions that identity may perform on which resources. For example, a role may allow updating Deployments in the staging namespace while forbidding creating RoleBindings or reading Secrets.

Do not share a single kubeconfig, cloud access key, or service account with administrative privileges across all pipelines. Build identities, publish identities, and deploy identities have different needs. Separating them limits the blast radius if a job is compromised or misconfigured.

Verify the target identity after authentication. A valid token mapped to the wrong account or cluster can still perform dangerous actions. Before deploying, the pipeline should check the account/project, cluster endpoint, namespace, and environment label against a defined allowlist.

## 11. Using Short-Lived Credentials Whenever Possible

If the CI platform and cloud support it, prefer workload identity federation/OIDC over storing long-lived access keys.

Typical flow:

1. The job requests an ID token from the CI platform's issuer.
2. The target provider validates issuer, audience, subject, and claims.
3. The trust policy maps authorized workloads to a role.
4. The job receives a short-lived access token.
5. The IAM policy restricts actions and resources.
6. The token expires after its granted lifetime.

Trust policies should bind repository, branch/tag, workflow, and environment whenever the issuer provides those claims. Do not trust every job in an organization or every branch in a repository if only one release workflow is allowed to deploy to production.

Short-lived tokens can still be abused while valid. Issue tokens only in jobs that need them, keep runners isolated, never log tokens, and never pass tokens through artifacts/outputs. If the platform does not yet support federation, use credentials in a secret store with least privilege, clear ownership, and a defined rotation schedule.

## 12. Separating Permissions by Environment and Role

Staging and production deploy permissions should be separated. A test job should not receive permissions to modify production simply because it resides in the same workflow.

| Identity | Environment | Permissions |
|---|---|---|
| staging-deployer | Staging | Update applications in the staging namespace |
| production-deployer | Production | Update production applications after approval |
| migration-runner | Target database | Run approved migrations within a specific schema scope |
| release-reader | Artifact registry | Read artifacts by digest |
| build-publisher | Artifact registry | Push artifacts to designated repositories |

Grant least-privilege permissions by action and resource. Never grant cluster-admin, full cloud account owner, or read-all-secrets permissions just to make a pipeline work.

Separating permissions also makes audits clearer: which operations were performed by the deployer, which by the migration runner, and which by the publisher. If a job needs multiple permission sets, consider splitting it into separate steps or identities rather than merging all permissions into one broad role.

## 13. Checking Kubernetes Permissions Before Deploying

With Kubernetes, kubectl auth can-i checks whether the current identity is permitted to perform a verb on a resource in a specific namespace.

Example:

```bash
kubectl auth can-i create deployments --namespace staging
kubectl auth can-i patch deployments --namespace staging
kubectl auth can-i get deployments --namespace staging
kubectl auth can-i watch deployments --namespace staging
kubectl auth can-i get pods --namespace staging
```

These commands check the permissions of the current identity. They do not by themselves verify that the identity points to the right cluster or account. Therefore, verify the context, API endpoint, and namespace against the allowed configuration first.

You can check identity and target with read-only commands:

```bash
kubectl config current-context
kubectl cluster-info
kubectl get namespace staging
```

Never print the entire kubeconfig or tokens to logs. The command kubectl config current-context only displays the context name; compare that name against an allowlist or expected target configuration. Context names are arbitrary, so for higher-assurance requirements also verify the cluster endpoint or cloud account through the corresponding management tool.

If the pipeline uses Helm, Argo CD, or a deployment controller, required permissions may differ from kubectl apply. Check the exact APIs/resources the tool actually uses. Never expand permissions to Secrets or other resources without a verified need.

## 14. Example RBAC Scoping Deployments to One Namespace

A ServiceAccount dedicated to staging deployments can be granted permissions to update Deployments and read rollout status in the staging namespace. Example:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: staging-deployer
  namespace: staging
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: staging-deployment-writer
  namespace: staging
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: staging-deployer-binding
  namespace: staging
subjects:
  - kind: ServiceAccount
    name: staging-deployer
    namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: staging-deployment-writer
```

This is a minimal example for a typical Deployment workflow. Depending on the tool, the pipeline may need additional permissions for specific resources such as Services, Ingresses, or ConfigMaps. Add permissions only after confirming the actual operations needed. Do not grant read access to Secret contents if the deployer only needs to reference an existing Secret.

A Role is namespace-scoped, unlike a ClusterRole which can apply across multiple namespaces or cluster-wide. For production, use a separate identity and binding; do not reuse the staging ServiceAccount.

If CI runs outside the cluster, authenticating to Kubernetes depends on the cloud provider or the cluster's OIDC/authentication mechanism. The ServiceAccount in this example represents the cluster-side RBAC subject; it does not imply storing a long-lived ServiceAccount token in CI. Prefer short-lived token issuance and avoid creating unnecessary static tokens.

## 15. Running Server-Side Dry-Run and Manifest Validation

Before applying real manifests, ask the API server to check structure and admission policies using server-side dry-run.

Example:

```bash
kubectl apply --dry-run=server -f k8s/
```

Server-side dry-run sends the request to the API server without persisting changes. It can detect invalid schemas, unsupported fields, admission rejections, or certain permission issues.

Dry-run does not prove a rollout will succeed. It does not guarantee the image can be pulled, the container can start, readiness probes will pass, or runtime dependencies are ready. Some admission webhooks must also properly declare dry-run support. Dry-run results are only one part of preflight.

Supplement this with static manifest checks before calling the API server:

- Validate YAML/JSON and schemas.
- Verify namespaces and resource names are on the allowlist.
- Verify images are referenced by digest.
- Check security contexts, resource requests/limits, and health probes.
- Enforce policies on privileged containers, hostPath, or capabilities.
- Verify no literal secrets exist in manifests.
- Verify API versions are compatible with the cluster.

Never run dry-run against an unverified context. If kubeconfig points to the wrong cluster, the request still hits an unintended API server. Target identity and context must be confirmed first.

## 16. Checking Approvals and Change Windows

Some environments require approval before changes, especially production or systems with sensitive operating hours.

An approval can confirm:

- The change was reviewed and has an accountable owner.
- The proposed artifact and digest are correct.
- Deployment, monitoring, and rollback plans are ready.
- Deployment timing falls within the change window.
- Dependent teams have been notified or prepared.
- Risks and impact have been assessed.

Approvals do not replace automated checks. An approver cannot look at a generic "CI passed" status and infer that the target is healthy or that the job holds the right permissions. The system should present the artifact, target, change ID, and gate evidence so the approver decides on the exact deployment request.

Do not require approval for every minor operation if policy does not demand it. However, when approval is mandatory, the pipeline must verify real approval state rather than relying on a job-supplied variable.

Change windows must also be checked close to deployment time. A job approved at 9:00 AM might start at 11:00 AM after the deployment window has closed or a new incident has begun. Time-based conditions should be re-verified right before the mutating step.

## 17. Controlling Concurrency and Preventing Concurrent Target Edits

Two pipelines can target the same environment simultaneously. If both preflights observe the target as ready and apply updates concurrently, one release can overwrite the other's state.

Coordination mechanisms are needed:

- Deployment queues or concurrency groups per target.
- Locks with leases and expiration.
- Environment-level deployment serialization.
- Checking the current revision before updating.
- Canceling or blocking older releases according to published rules.

Locks need timeouts and release mechanisms when a job fails or a runner is lost. Never hold locks indefinitely. If using leases, the job must renew while still working, and the system must handle cases where a lease expires while an older job is still running.

Do not lock solely by workflow name. Two different workflows might modify the same cluster or database. Locks should reflect the resources actually at risk of contention: application, namespace, database schema, or environment.

## 18. Re-Checking Conditions Immediately Before Making Changes

Preflight results can go stale between validation and deployment. For example:

- Capacity drops as another workload scales up.
- A new incident is opened.
- Another release updates the resource version.
- Credentials expire.
- Approval is revoked.
- The change window closes.
- An image tag changes if the pipeline failed to pin a digest.

This is the time-of-check to time-of-use (TOCTOU) problem: the state checked earlier may differ from the state at the moment of use.

How to reduce this risk:

1. Check expensive conditions early, such as artifact, compatibility, and policy checks.
2. Acquire a lock or enter a deployment queue before mutating the target.
3. Re-check fast-changing conditions: target, approval, health, capacity, credentials, and current revision.
4. Use immutable versions/digests for artifacts.
5. Perform conditional updates or use APIs supporting optimistic concurrency.
6. If state changed, halt and re-evaluate instead of pushing ahead with stale results.

Preflight cannot freeze every aspect of an environment. The goal is to shrink the gap between check and mutation while using concurrency controls and versioning to avoid unintended overwrites.

## 19. Gates Should Produce Clear Outcomes

A gate should not just dump a long log without a machine-readable conclusion. Outcomes can be categorized as:

| Outcome | Meaning | Action |
|---|---|---|
| PASS | All mandatory conditions met | May proceed if near-deploy checks remain valid |
| DENY | Policy violation or missing permissions | Stop; fix permissions or policy via proper process |
| BLOCKED | Missing approval, outside change window, or temporary dependency | Wait until conditions are met, then re-check |
| INCONCLUSIVE | Unable to verify due to infrastructure or data-source failure | Do not deploy; repair check systems and re-run |
| WAIVED | Approved exception following formal process | Proceed only within waiver scope and expiration |

Never collapse infrastructure errors into PASS. If the API server is unreachable, the pipeline has not proven permissions or target validity. If the approval service is down, the gate lacks proof of approval.

A waiver must have an owner, reason, scope, expiration, and approver. Never allow an arbitrary SKIP_PREFLIGHT=true variable to bypass the entire gate, especially in production. Any break-glass mechanism must be audited and reviewed post-incident.

## 20. Example Pre-Deployment Preflight Pipeline

A job can order its checks as follows:

```yaml
jobs:
  preflight:
    steps:
      - name: Verify release metadata
        run: verify artifact version, digest and provenance

      - name: Resolve target
        run: validate account, cluster and namespace against allowlist

      - name: Authenticate
        run: obtain short-lived deployment identity

      - name: Check target permissions
        run: verify required actions on the target namespace

      - name: Check environment health
        run: query health, capacity and active deployment state

      - name: Validate configuration
        run: validate configuration and required secret references

      - name: Validate manifests
        run: run schema and policy checks

      - name: Server-side dry-run
        run: submit manifests with server-side dry-run

      - name: Check approval and change window
        run: verify approval and current deployment window

  deploy:
    needs: [preflight]
    steps:
      - name: Recheck mutable conditions
        run: revalidate target, approval and current revision

      - name: Deploy verified artifact
        run: deploy the exact artifact digest
```

The commands in this example are conceptual descriptions and must be replaced with actions or commands for your real CI platform and deployment tool. Some platforms require environment-level approval before granting credentials to a job; in that case, approval precedes identity acquisition. What matters is that approval, target validation, and access permissions are bound to the same deployment request.

If preflight and deploy run in separate jobs or on different runners, do not rely on the first job's temporary filesystem or credentials. The deploy job must receive the artifact identity and verifiable gate outcome, then obtain its own credentials per its granted permissions.

## 21. Scenario Example: Deploying to Production but Hitting the Wrong Cluster

A team has two clusters: staging and production. Both contain a namespace named orders. A runner has a kubeconfig whose default context is staging. A pipeline is triggered to deploy to production, but the script simply runs kubectl apply without verifying the context.

The result may be that the release is applied to staging while the pipeline reports deployment success. Conversely, if the default context changes or kubeconfig is updated, the same command could accidentally affect production.

A strong preflight will:

1. Resolve the production environment to its declared cluster endpoint and namespace.
2. Verify the workload identity federated into the production role.
3. Verify the actual context or cloud account matches the intended target.
4. Check required permissions in the production namespace.
5. Run a server-side dry-run against the exact API server.
6. Verify the artifact digest and approval.
7. Acquire a concurrency lock scoped to the production target.
8. Re-check target and current revision.
9. Deploy the exact verified digest.
10. Record target identity, digest, and deployment revision in evidence.

The outcome of every step must be explicitly logged. If the target mismatches, the gate stops even if the identity has permissions on that cluster. Having access does not mean that target was requested.

## 22. Handling Preflight Failures and Retries

Not all failures should be handled the same way.

| Failure | Classification | Remediation |
|---|---|---|
| Digest mismatch | Artifact/trust failure | Reject artifact and investigate origin |
| Missing permission to patch Deployment | Authorization failure | Fix role following least privilege |
| Wrong cluster or namespace | Target mismatch | Stop and fix mapping/trigger |
| API server unreachable | Infrastructure error | Restore connectivity and re-run preflight |
| Missing approval | Policy blocked | Wait for valid approval |
| Outside change window | Time policy blocked | Wait for permitted window |
| Insufficient capacity | Environment not ready | Free/add resources or reschedule |
| Incompatible migration | Compatibility failure | Design phased migration or release |
| Expired credentials | Authentication failure | Obtain fresh credentials if identity remains valid |
| Another release holds lock | Concurrency blocked | Wait in queue or resolve active release |

Only retry recoverable errors such as transient timeouts, brief API server interruptions, or expired credentials when trust conditions still hold. Never repeatedly retry permission failures, target mismatches, or policy violations.

Before retrying, determine whether the prior attempt modified the environment. If deployment had started, inspect the current revision and rollout state before re-running. Retries must never trigger duplicate migrations or unintended side effects.

## 23. Recording Gate Evidence

Every preflight run should generate a traceable record. The record should attach to the specific deployment request, not just the workflow run.

Useful details:

- Application/service and release identifier.
- Artifact version and digest.
- Source commit and build run.
- Target account, cluster, namespace, region, or tenant.
- Deployment identity and role used.
- Conditions checked and individual results.
- Check timestamp and deployment start timestamp.
- Approval/change ID and approver, if applicable.
- Manifest/configuration revision.
- Lock or deployment queue ID.
- Dry-run and policy validation results.
- Pre-deploy current revision and post-deploy revision.

Never record tokens, passwords, or secret values in evidence. Record principal identifiers, roles, secret references, or versions per policy. If logs contain sensitive configuration, redact or omit it before storing.

Evidence helps investigate why the pipeline allowed a deployment, which job executed the action, and which artifact was used. It also helps separate release defects from environment or permission failures.

## 24. Common Anti-Patterns

| Poor Practice | Consequence | Improvement |
|---|---|---|
| Checking only that CI is green | Unknown whether specific artifact and target are valid | Gate on deployment request and digest |
| Relying on default kubectl context | Risk of deploying to wrong cluster | Explicitly verify target and context |
| One admin credential for all environments | Expands blast radius | Separate identities with least privilege |
| Approval replacing authorization | Human approvers cannot grant machine permissions | Verify approval and RBAC/IAM independently |
| Job permitted to read all Secrets | High risk of leaking sensitive data | Separate deploy permissions from secret consumption |
| Treating dry-run as proof of rollout success | Misses image, startup, or dependency failures | Combine with post-deploy smoke/readiness checks |
| Running preflight too early | Results go stale before use | Re-check mutable conditions right before deploy |
| Not locking concurrent deployments | Two releases can overwrite each other | Target-scoped queue or lock |
| Retrying all errors | Masks misconfiguration and policy violations | Classify errors and bound retries |
| Bypassing gates with arbitrary variables | Loses production control | Waivers with owner, scope, expiry, and audit |
| Logging full kubeconfig/tokens | Leaks credentials | Log only identities and non-sensitive metadata |
| Omitting target and digest from records | Hard to investigate misdeployments | Bind evidence to target and artifact identity |

## 25. Roadmap for Adopting Preflight in a Project

Adoption can proceed step by step:

1. **Define targets:** list environments, accounts, clusters, namespaces, and resources pipelines are allowed to modify.
2. **Define deployment requests:** standardize service, artifact digest, target, action, and release ID.
3. **List gate conditions:** categorize artifact, quality, environment, compatibility, configuration, approval, and permission checks.
4. **Design workload identities:** separate identities by role and environment; prefer short-lived credentials.
5. **Configure RBAC/IAM:** grant exact actions and resources, testing with the real principal.
6. **Automate validation:** validate manifests, configuration, schemas, health, and capacity.
7. **Add dry-run:** verify API/admission rules and permissions against the exact target.
8. **Add concurrency control:** lock or queue on contended resources.
9. **Re-check near deploy time:** re-verify mutable conditions.
10. **Record evidence:** tie results to artifact digest, target, identity, and approval.
11. **Rehearse failures:** test wrong target, missing permissions, expired credentials, unhealthy environments, and competing releases.

Start in staging to validate the process. Once the gate is stable, roll it out to production with dedicated approvals, change windows, and separate identities. Never introduce an untested gate directly into production and figure out how it behaves later.

## 26. Measuring Pre-Deployment Gate Effectiveness

A good gate blocks bad deployments and reduces incidents caused by environment conditions or permissions. Track metrics such as:

- Number of times the gate accurately blocked invalid artifacts or targets.
- Number of deployments failing due to missing permissions or wrong targets.
- Rate of preflight infrastructure errors or inconclusive results.
- Elapsed time from preflight to actual deployment.
- Number of re-checks triggered because environment state changed.
- Number of deployment conflicts prevented by queues/locks.
- Percentage of deployments with complete evidence and approvals.
- Waiver usage count and active waiver duration.
- Rollback or incident rate linked to unchecked conditions.

Do not optimize by removing critical gates just to shorten pipeline duration. Run fast checks early, parallelize independent checks, and run target-dependent checks only after the target has been resolved. Gates must balance feedback speed with necessary assurance.

## 27. Checklist Before Allowing Deployment

- [ ] Deployment request clearly specifies service, artifact, target, and action.
- [ ] Artifact version/digest matches trusted release metadata.
- [ ] Required tests, scans, and quality gates passed.
- [ ] Target account, cluster, namespace, or tenant is verified.
- [ ] Target environment is healthy with sufficient capacity for rollout.
- [ ] Runtime, schema, and dependencies are compatible with the new version.
- [ ] Configuration is valid and required secret references exist.
- [ ] Runtime dependencies are reachable by design.
- [ ] Workload identity is authenticated with the right issuer/audience/subject.
- [ ] IAM/RBAC grants only necessary permissions on the exact resources.
- [ ] Deploy job lacks unnecessary secret-read or admin privileges.
- [ ] Manifests passed appropriate validation and dry-run checks.
- [ ] Approvals and change windows remain valid.
- [ ] No other deployment is contending for the target.
- [ ] Mutable conditions are re-checked immediately before mutation.
- [ ] A suitable rollback or recovery plan is in place.
- [ ] Evidence records artifact digest, target, identity, and gate results.
- [ ] Tokens, passwords, and secrets never appear in logs.

## Conclusion

Checking pre-deployment conditions is the decision step that determines whether a specific artifact may be introduced to a specific target at the current moment. Gates must verify the artifact, quality, environment health and capacity, compatibility, configuration, dependencies, approvals, and concurrency state.

Target access permissions must be verified separately using workload identity and target-system policies. Authentication proves who the job is; authorization limits what the job can do and on which resources. By using short-lived identities, least-privilege RBAC/IAM, target allowlists, dry-runs, near-deploy re-checks, and traceable evidence, pipelines reduce the risk of misdeployment, privilege escalation, or modifying an unready environment.
