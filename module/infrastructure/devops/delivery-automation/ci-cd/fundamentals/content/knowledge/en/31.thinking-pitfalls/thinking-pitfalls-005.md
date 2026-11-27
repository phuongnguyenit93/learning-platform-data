# Storing Secrets in Pipeline Configuration or Granting Full Privileges to Runners

## 1. Why Are These Two Dangerous Thinking Pitfalls?

CI/CD pipelines typically need access to source repositories, package registries, container registries, cloud accounts, deployment environments, and secret managers. Runners execute scripts supplied by the repository or pipeline. If secrets are placed directly inside configuration files or runners are granted overly broad permissions, a single small change in the pipeline can become an access path to numerous critical systems.

Two common flawed assumptions:

- "The pipeline is internal code, so we can put tokens/passwords into YAML or scripts."
- "The runner needs to deploy, so just give it admin permissions, broad cloud privileges, or use one shared credential for all jobs."

Both practices turn the pipeline into a concentration point for secrets and access privileges. When an untrusted pull request, compromised dependency, hijacked runner, or leaked log occurs, an attacker can extract credentials and use those privileges well beyond a single job's scope.

A secure CI/CD design must treat pipelines and runners as part of the security boundary. Secrets should be issued just-in-time, to the right job, for the right environment, and for the shortest possible lifetime. Runners should only possess the exact permissions required to carry out a specific task.

## 2. Distinguishing Pipeline Configuration from Secrets

Not every configuration value is a secret. Classify values before deciding where to store them:

| Data Category | Examples | How to Manage |
|---|---|---|
| Non-sensitive configuration | Build mode, service name, public region, timeouts | Pipeline YAML, config files, or environment variables |
| Resource identifiers | Registry host, cloud project ID, namespace | Controlled configuration; may be internally visible |
| Authentication credentials | Passwords, API tokens, private keys, client secrets | Secret manager or CI secret store |
| Signing material | Signing keys, certificate private keys | KMS/HSM or signing service with tightly restricted access |
| Sensitive operational data | Recovery codes, emergency credentials | Dedicated vault, break-glass procedure, and auditing |

A URL may not be a secret if it contains no username/password or token. Conversely, an innocuously named variable like `DEPLOY_CONFIG` might contain a private key or credential. Classify based on content and abuse potential, not just variable name.

Never commit secrets to a repository, even a private one. Git history, forks, clones, caches, artifacts, logs, and backups can retain those values long after the file is deleted.

## 3. Why Hardcoding Secrets in Pipelines Is Wrong

Insecure example:

~~~yaml
deploy:
  script:
    - cloud-cli login --token "actual-token"
    - deploy --environment production
~~~

Token values can leak through:

- Git history and pull request diffs.
- Repository forks or clones.
- Logs when commands are echoed.
- Error messages or debug traces.
- Artifacts, caches, or temporary files.
- Screenshots, support bundles, or workspace copies.
- Users with repository read access who do not need deploy privileges.

Rotating a token after removing it from a file is necessary but insufficient if the token was ever committed. Treat the credential as compromised: revoke or rotate it, scope its usage, and inspect audit logs. A new commit deleting a secret does not erase the value from history or existing clones.

## 4. Do Not Treat Environment Variables as a Default Secret Store

Passing secrets via environment variables is generally better than hardcoding them in scripts, yet it does not automatically make secrets safe. Environment variables can be read by:

- Child processes running with the same privileges.
- Debug commands that print the full environment.
- Crash dumps or diagnostic bundles.
- Test reports or scripts that inadvertently serialize configuration.
- Other processes running under the same user on a shared runner.
- Plugins or actions with permission to read the job's environment.

Environment variables are a mechanism for passing data to a process, not a secret manager. When used, scope them strictly to the job, disable shell tracing, never dump the environment, avoid passing secrets to jobs that do not need them, and clean up the workspace after execution.

For high-sensitivity secrets, prefer fetching them directly from a secret manager inside an authorized job, using file descriptors or temporary files with strict permissions if a tool requires a file. Delete temporary files immediately after use and ensure they are never included in artifacts or caches.

## 5. Log Masking Does Not Guarantee Secrets Cannot Leak

Many CI platforms support masked variables to replace registered values with masking characters in logs. This is a leak-reduction layer, not a security boundary.

Masking can fail or not apply when:

- Values are encoded, split, transformed, or concatenated.
- Scripts write secrets to files and upload them as artifacts.
- Tools generate crash dumps or debug bundles.
- Secrets appear inside exceptions or differently formatted output.
- A process authorized to read the secret exfiltrates it over the network.
- Values were not registered or do not meet the platform's masking criteria.

Never rely on masking to permit untrusted code to access secrets. The primary defense is not granting the secret to that job at all. Masking, redaction, and log reviews are supplemental defenses.

## 6. Secrets Can Leak Through Artifacts and Caches

A job might never print a secret to the console yet still accidentally embed it into files:

- Config files rendered from templates containing credentials.
- Test reports containing request headers.
- Debug archives containing environment or process dumps.
- Docker build contexts copying credential files into an image layer.
- Caches saving home directories or workspaces containing credentials.
- Packages containing `.env` files or signing material.

Before uploading, explicitly define an allowlist of files permitted for publishing. Use an artifact allowlist rather than archiving the entire workspace. Inspect image layers, package manifests, and cache paths; never cache directories holding secrets or credential helpers.

If a secret appears in an artifact, remove the artifact from distribution stores per procedure, revoke the credential, and check any replicas or downloads if applicable. Deleting a file on a runner does not make an already-published artifact disappear.

## 7. Store Secrets in a Secret Manager or CI Secret Store

Centralized secret managers provide control over read permissions, rotation, auditing, and credential lifecycles. A CI secret store can fit secrets scoped tightly to a repository or environment, provided you understand who has access to modify pipelines and jobs.

A practical division:

| Need | Appropriate Storage |
|---|---|
| Project-scoped internal build credentials | CI secret store with narrow scope |
| Production credentials shared across services under governance | Central secret manager with workload-identity policies |
| Private signing keys | KMS/HSM or signing service; restrict key export |
| Emergency credentials | Vault/break-glass store with approvals and audit |
| Developer secrets | Personal/organizational password manager; never in pipelines |

A secret manager does not make the system secure on its own if every runner can read every secret. Policies must bind to specific identities, environments, services, and operations.

## 8. Scope Secrets by Job and Environment

Do not expose all repository secrets to every job. Lint or unit test jobs generally do not need production credentials. Staging deploy jobs only need staging permissions. Package publish jobs need write access only to the target package namespace.

Principles:

- Grant secrets at the job/step that needs them, not at the workflow level unnecessarily.
- Separate secrets across development, staging, and production environments.
- Never pass production secrets to pull requests from forks or untrusted branches.
- Restrict read access by repository, branch, tag, environment, and actor where supported by the platform.
- Require approvals/environment protection before issuing production credentials.
- Prevent child jobs or unrelated actions from inheriting secrets.

A pipeline may contain many jobs while only one release job requires production credentials. Isolating that job shrinks the blast radius if a build or test step is compromised.

## 9. Prefer Short-Lived Credentials and Workload Identity

Long-lived credentials such as personal access tokens or static access keys can persist for months. If leaked, they can continue being abused until discovered and revoked.

When supported by the platform, prefer:

- OIDC federation between the CI platform and cloud/secret managers.
- Workload identities bound to repository, branch, workflow, or environment.
- Short-lived tokens with minimal scope.
- Credentials issued per job that expire automatically.
- KMS/signing services handling signing requests without exporting private keys to runners.

Example OIDC flow:

~~~mermaid
sequenceDiagram
    participant CI as CI Job
    participant IdP as CI Identity Provider
    participant Cloud as Cloud STS
    participant API as Target API
    CI->>IdP: Request OIDC identity token
    IdP-->>CI: Short-lived signed token
    CI->>Cloud: Exchange token with trust policy
    Cloud-->>CI: Temporary scoped credentials
    CI->>API: Perform permitted deployment
    API-->>CI: Result
    Note over CI,Cloud: Temporary credentials expire automatically
~~~

Trust policies must verify issuer, audience, subject, and relevant claims. Do not merely verify that a token was signed by the right issuer; restrict which tokens may assume production roles. For example, only workflows from a specific repository, protected branch/tag, and approved environment may assume the role.

## 10. Do Not Grant Runners Admin Privileges Just Because They Deploy

Runners execute code and scripts. If a runner holds administrator privileges over a cloud account, cluster, or subscription, any job running on that runner can become an access vector to all those resources.

Examples of overly broad permissions:

- A cloud access key with Owner permissions across the entire account.
- Kubernetes `cluster-admin` used across all namespaces.
- A personal access token with admin access to every repository.
- A registry credential allowed to delete/publish any image.
- A runner with production database access when it only needs to deploy the application.

Instead, identify the exact operations: updating one deployment, pushing to one repository, reading one secret, or creating one release. Grant corresponding permissions on the exact resources for the duration needed.

## 11. Least Privilege for Each Job Type

Least privilege means an identity holds only the permissions required to complete its assigned task.

| Job | Permissions Needed | Permissions Not Needed by Default |
|---|---|---|
| Lint/unit test | Checkout source, read needed dependencies | Production deploy, cloud admin, signing keys |
| Build/package | Read source/dependencies, write artifacts to project namespace | Deleting other artifacts, registry admin |
| Security scan | Read source and metadata required for scanning | Production deploy, reading runtime secrets |
| Publish image | Push to a specific repository/image | Deleting entire registry or modifying IAM |
| Deploy staging | Update workloads in the staging namespace | Cluster-wide `cluster-admin`, production access |
| Deploy production | Narrow deploy rights after approval, read required secrets | Cloud account-wide Owner |
| Sign release | Invoke signing service per policy | Exporting private keys or KMS administration |

Permissions must be checked across cloud IAM, Kubernetes RBAC, registry ACLs, repository tokens, secret managers, and the runner operating system. Narrowing one layer while leaving another wide open still fails least privilege.

## 12. Runners with Host Admin Privileges Are a Security Boundary

A runner executes shells, containers, build tools, and repository scripts. If a job runs with root/administrator privileges on the host, it can:

- Read files and credentials from other jobs if workspaces or processes are shared.
- Modify the runner agent or configuration to hijack future jobs.
- Access the Docker socket or container runtime.
- Install persistence mechanisms, malicious binaries, or SSH keys.
- Reach metadata services or internal networks.
- Steal host/runner manager tokens if stored on the machine.

Therefore, never use high-privilege runners as a shared pool for untrusted code. Runners for pull requests from forks need isolated, ephemeral environments with no production secrets or privileges.

## 13. Ephemeral Runners and Isolation

An ephemeral runner is provisioned for a single job or short-lived workload and then destroyed. This reduces the risk of leftover data across jobs and limits persistence on shared hosts.

However, ephemeral does not automatically equal secure. You must:

- Provision runners from controlled, reproducible images.
- Use distinct identities per runner/job or trust tier.
- Avoid mounting host paths, Docker sockets, or unnecessary credentials.
- Restrict network egress to required dependencies.
- Never reuse workspaces containing sensitive data.
- Destroy the instance and revoke its identity after the job completes.
- Persist necessary logs/evidence off-runner before termination.
- Monitor orphan runners and cleanup failures.

Container runners still share a kernel with the host. For untrusted workloads or those needing elevated capabilities, consider VM isolation or stronger sandboxing. Choose isolation levels according to the threat model and the kind of code executed.

## 14. Never Run Fork/Untrusted PR Code on Runners Holding Secrets

Pull requests from forks can modify workflows, build scripts, tests, or dependencies. If a workflow passes production secrets to that job, a contributor can edit scripts to read and exfiltrate them.

Safety rules:

- Never grant secrets to jobs executing code from untrusted forks.
- Never use persistent runners with internal network access for untrusted PRs.
- Separate untrusted and trusted pools by identity, network, and filesystem.
- Carefully inspect event triggers and default token permissions.
- Run high-privilege steps only after changes pass review and branch/environment policies.
- Never automatically trust artifacts/caches created by untrusted jobs inside release jobs.

Even if the platform masks secrets in logs, malicious scripts can still send secrets over the network. Withholding secrets is the decisive control.

## 15. Restrict CI Token Permissions

Tokens issued by the CI platform to workflows are also credentials. Default tokens should not hold write access to every repository or administrative control over the entire project when a job only needs to check out source code.

Principles:

- Default to read-only permissions when workflows only read.
- Grant write permissions explicitly to jobs that publish or create releases.
- Scope tokens to specific repositories/projects and lifetimes.
- Never use a personal access token as a shared automation credential.
- Never share tokens across developers, runners, and service accounts.
- Rotate and revoke tokens when owners change or exposure is suspected.
- Audit actions performed by bot identities.

Token scope must consider both API permissions and resource scope. A token with only package-write permissions across an entire organization is still much broader than a token allowed to write to a single package namespace.

## 16. Prevent Secrets from Leaking Through Caches, Docker Build Context, and Image Layers

Frequently overlooked leak paths:

- Dependency caches containing configuration files with credentials.
- Docker build contexts including `.env` files or home directories.
- Build arguments containing secrets that persist in image history or build metadata.
- Image layers created in earlier steps retaining secret files even if deleted in later steps.
- Artifacts built from workspaces containing credentials.

With Docker/BuildKit, use the build tool's secret mount when secrets are required during build rather than passing secrets as standard build arguments. Restrict build context with ignore files and copy only needed files. Never package credential files into final images.

Principle example:

~~~dockerfile
# Do not pass tokens via ARG or ENV.
# Use a builder-supported secret mount on the command requiring auth.
RUN --mount=type=secret,id=package_token \
    ./download-private-dependency.sh
~~~

The snippet above illustrates a BuildKit secret mount; exact syntax and access controls depend on the builder. The script should read the secret from the mount path, avoid printing it to logs, and never copy it into output layers.

## 17. Pipeline Injection and Untrusted Workflows

Pipeline-as-code can be exploited if workflows interpolate user-controlled data directly into shell commands. For example, branch names, pull request titles, or unvalidated inputs may contain characters that alter command execution.

Principles:

- Never interpolate untrusted data directly into shell scripts.
- Pass values via properly quoted inputs/arguments validated against an allowlist.
- Use dedicated script files rather than dynamically constructing complex shell commands.
- Restrict workflow token permissions.
- Never use privileged runners for workflows receiving input from forks.
- Review workflow and shared-action changes as sensitive code.
- Pin third-party actions/plugins by version or immutable commit SHA where appropriate.

A job without secrets can still cause harm if the runner can reach internal networks or host tokens. Input sanitization and runner privileges must be enforced together.

## 18. Secret Rotation and Handling Suspected Exposure

When a secret is discovered in a commit, log, or artifact, treat that credential as compromised until proven otherwise.

Response procedure:

1. Identify the secret type, owner, scope, and systems accepting the credential.
2. Revoke or rotate the credential based on urgency.
3. Inspect audit logs for anomalous activity since the earliest possible exposure time.
4. Locate everywhere the value appeared: Git history, artifacts, caches, logs, runner disks, or backups.
5. Delete/withdraw distributed copies per retention and incident policy; recognize clones may still exist.
6. Update the secret manager and consumers requiring the new credential.
7. Verify workflows no longer read the old credential.
8. Add secret scanning and redaction tests to prevent recurrence.

Do not simply delete the secret line from YAML and consider the incident closed. Git history may still contain the old value; force-pushing rewritten history may reduce exposure in some cases, yet it never replaces revoking the credential.

## 19. Separate Build, Publish, Deploy, and Sign Permissions

A single pipeline may span multiple stages with different privilege needs. If the entire workflow receives production permissions from the start, every pre-deploy step can expose those privileges.

A better design separates identities:

| Stage | Identity | Permissions |
|---|---|---|
| Build/test | Build identity | Read source/dependencies, create temporary outputs |
| Publish artifact | Publisher identity | Write artifacts to a specific namespace |
| Sign | Signing identity | Request artifact signing per policy |
| Deploy staging | Staging deploy identity | Update staging |
| Deploy production | Production deploy identity | Update designated production workloads |

Artifacts must link to digests, source revisions, and build provenance. Deploy jobs should receive verified artifacts instead of rebuilding from source in an environment carrying production privileges.

## 20. Example of a Safer Pipeline

This pseudocode illustrates separating privileges:

~~~yaml
jobs:
  test:
    permissions:
      repository: read
    secrets: []
    steps:
      - checkout
      - run-unit-tests

  publish:
    needs: [test]
    permissions:
      repository: read
      artifact: write
    steps:
      - build-package
      - publish-artifact

  deploy-staging:
    needs: [publish]
    environment: staging
    identity: staging-deployer
    steps:
      - download-artifact-by-digest
      - deploy-staging
      - verify-staging

  deploy-production:
    needs: [deploy-staging]
    environment: production
    approval: required
    identity: production-deployer
    steps:
      - verify-approved-artifact
      - request-short-lived-credentials
      - deploy-production
      - verify-production
~~~

This is a conceptual configuration, not direct syntax for a specific CI platform. Real systems must map permissions, secret scopes, environment protections, and OIDC trust policies according to platform semantics. The core point is that the test job holds no production secrets, and only the production deploy job receives the corresponding identity after passing gates.

## 21. Kubernetes RBAC Example for Namespace-Scoped Deployments

Do not grant `cluster-admin` to every runner merely to update a Deployment. Create a `ServiceAccount` and `Role` allowing only required operations inside the target namespace.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ci-deployer
  namespace: staging
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-updater
  namespace: staging
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ci-deployer-binding
  namespace: staging
subjects:
  - kind: ServiceAccount
    name: ci-deployer
    namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: deployment-updater
~~~

This is an illustrative example. Check the exact resources and verbs required by your deploy tool; Helm, rollout controllers, or ConfigMap/Secret operations may need additional permissions. Never add delete permissions, secret creation, or cross-namespace access without justification. Production should use separate identities and namespace policies.

## 22. Verify Effective Permissions, Not Just Declared Permissions

A YAML file might declare narrow permissions while the job still inherits broad access from the runner host, cloud metadata service, mounted credentials, or default service account.

Verify:

- What scopes does the workflow token actually have?
- Which user does the runner process run under, and does it have sudo/admin rights?
- Does the container mount any Docker socket, host filesystem, or kubeconfig?
- Can the instance reach the cloud metadata endpoint?
- Can network egress reach databases or production subnets?
- Does the default `ServiceAccount` have broader permissions than expected?
- Are credentials cached in the home directory or workspace?
- Can a prior job leave processes or files affecting the next job?

Test permissions using the job's actual identity in a test environment. Compare permitted and denied actions against expected policy. A policy only has value when effective runtime permissions match the intended design.

## 23. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Committing tokens/passwords in YAML | Secrets persist in Git history and clones | Use a secret manager; revoke/rotate if exposed |
| Assuming a private repo is safe enough | Everyone with repo read access can see secrets | Separate code read access from secret usage |
| Relying on masked logs | Secrets can leak via encoding, artifacts, or network | Withhold secrets from untrusted jobs |
| Exposing all secrets to the whole workflow environment | Every job can read unnecessary secrets | Scope by job/environment |
| Using personal PATs for automation | Privileges and lifecycle tie to a user account | Use scoped bot/workload identities |
| Granting cloud Owner or `cluster-admin` to runners | One compromised job controls broad resources | Least privilege per resource/operation |
| Using persistent runners for fork PRs | Persistence and cross-job access | Ephemeral, isolated untrusted pools |
| Sharing runners between trusted and untrusted jobs | Workspace, process, and credential leakage | Separate trust boundaries and host identities |
| Saving secrets in caches, artifacts, or image layers | Credentials outlive the job | Allowlist outputs, secret mounts, and scan |
| Only deleting secrets in a new commit | Git history and distributed outputs still hold old values | Revoke/rotate, audit, and clean up artifacts/logs |
| Using the same identity for build and deploy | Build/test jobs hold production permissions | Separate identities per stage |
| Assuming containers equal total isolation | Host kernel, sockets, or network may still be reachable | Use VMs/sandboxes and restrict host privileges |

## 24. Checklist Before Granting Pipelines Secret Access or Deploy Permissions

Before enabling a credential or runner pool, verify:

- [ ] Data is classified: regular configuration vs. secret.
- [ ] No hardcoded secrets exist in source, YAML, Dockerfiles, scripts, or test fixtures.
- [ ] Secrets are stored in an appropriate CI secret store or secret manager.
- [ ] Secrets are granted only to the specific job, branch, environment, and actor that need them.
- [ ] Pull requests from forks/untrusted sources do not receive secrets or privileged runners.
- [ ] Short-lived credentials/OIDC are preferred when supported by the platform.
- [ ] Tokens have minimal scope and appropriate lifetimes.
- [ ] Runners do not have admin, cluster-wide, or cloud-wide permissions by default.
- [ ] Trusted and untrusted runner pools are separated.
- [ ] Unnecessary host sockets, credentials, and filesystems are not mounted.
- [ ] Network egress and metadata access are restricted as needed.
- [ ] Artifacts, caches, build contexts, and image layers contain no secrets.
- [ ] Log masking/redaction and access controls are verified.
- [ ] Rotation/revocation and audit procedures are ready.
- [ ] Effective permissions are verified using the job's real identity.
- [ ] Build, publish, sign, and deploy use separate identities where needed.

## 25. Core Practice Principles

1. Pipeline YAML is reviewable configuration stored in Git; secrets do not belong in repositories.
2. Masking only reduces log leakage; it does not protect secrets from code allowed to read them.
3. Scope secrets by job/environment and withhold them from workflows triggered by untrusted sources.
4. Prefer workload identities, OIDC, and short-lived credentials over static keys.
5. Apply least privilege across tokens, cloud IAM, Kubernetes RBAC, registries, and secret managers.
6. Treat runners as security boundaries because they execute scripts and may access host resources.
7. Separate trusted and untrusted runners; enforce ephemeral isolation and restrict network/host access.
8. Control artifacts, caches, Docker build contexts, and image layers to avoid unintended secret retention.
9. When a secret is suspected exposed, revoke/rotate and audit; deleting the file is not enough.
10. Separate build, publish, sign, and deploy permissions; verify runtime effective permissions rather than just reading YAML.

Storing secrets in pipeline config and granting full privileges to runners both stem from viewing CI/CD purely as an automation tool. In reality, pipelines execute code and carry identities capable of touching critical resources. When secrets are tightly scoped, credentials are short-lived, runners are isolated, and permissions are limited to the task, automation speed is preserved while the risk from a compromised job is dramatically reduced.
