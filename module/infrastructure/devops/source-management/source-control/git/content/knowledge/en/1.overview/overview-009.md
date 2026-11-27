# Limitations of Git for deployment, backups, and secret management

Git is a distributed version control system. It records versions of files, organizes history with commits, and supports multi-person collaboration through branches, merges, rebases, remotes, and tags. As a result, a development team can know what changes happened, who made them, which version a change was based on, and can return to an earlier source code milestone.

However, version control is only one part of the software lifecycle. A commit does not automatically turn into a safely deployed release; a remote does not automatically serve as a disaster recovery backup system; and a file deleted from the working tree does not mean a secret has disappeared from history. To operate software reliably, you must understand Git's boundaries and combine it with appropriate deployment, backup, and secret management systems.

## 1. What problems does Git solve?

Git manages content residing inside the repository. When creating a commit, Git saves a state milestone of tracked files along with author, timestamp, message, and parent commit information. Branches and tags are references that help humans name commit milestones. Remotes allow exchanging commits and references between repositories.

Git can store source code, documentation, configuration, deployment scripts, and infrastructure definitions in text form. That history is very useful for review, traceability, and reproducing the source code state at a specific commit.

Git does not directly manage the entire system running the software. It does not inherently know what configuration a server has, which services are running, how far database migrations have progressed, which build is serving users, or whether a release passed health checks. Nor does Git itself provide a build artifact repository, independent backups, or an access-controlled secret vault.

You can distinguish three questions:

- **Version control:** How have source code and configuration changed? Git answers this question well.
- **Deployment:** Which version was packaged, delivered to which environment, and is it running properly? You also need CI/CD, release tooling, and monitoring mechanisms.
- **Data and secret protection:** Can you recover from an incident, and are credentials protected? You need separate backup systems and secret managers.

## 2. Limitations of Git in software deployment

### 2.1. A commit is not a complete release

A commit identifies repository contents at a point in time. It does not guarantee that the source code will build successfully or behave identically across all environments. Build outcomes also depend on many other factors:

- Compiler, runtime, SDK, and build tool versions.
- Downloaded dependencies, resolved versions, and registry availability.
- Environment variables, per-environment configuration, and service access permissions.
- Operating system, CPU architecture, system libraries, and external services.
- Data, database state, and migration execution order.

If two machines check out the same commit but use different dependencies or build environments, the results can differ. Git only records committed files; it does not lock down the entire execution environment on its own. Therefore, projects should manage dependencies with lockfiles, standardize build environments, record tool versions, and verify builds in CI.

A good release process typically builds once, stores the artifact with an identifier or checksum, and deploys that exact artifact across environments. This avoids the situation where rebuilding in production yields a different package from the one that was tested.

### 2.2. Git does not orchestrate deployments

Commands such as checkout, pull, and merge modify repository contents. They do not automatically perform the full set of release steps such as:

1. Running quality checks and tests.
2. Building, packaging, and storing artifacts.
3. Supplying the right configuration and secrets for the target environment.
4. Updating services using rolling, blue-green, or canary strategies.
5. Checking health checks, logs, metrics, and errors after deployment.
6. Halting a rollout or rolling back when an incident occurs.

Running git pull directly on a production machine might be an option in a very simple setup, but the command itself is not a safe deployment workflow. It does not guarantee that dependencies are installed properly, the build is complete, processes have restarted, multiple machines are updated in sync, or the new version is compatible with the database schema. If a step fails midway, the system can end up half-old and half-new.

Let a CI/CD pipeline or deployment platform execute these steps. Git provides the source code and version milestone as input; the pipeline is responsible for testing, building, releasing, and recording results.

### 2.3. Branches and tags do not automatically guarantee the running version

A branch name like main is a reference that can advance to new commits. If you deploy from the tip of a branch at different times, each run can pick up a different commit. A tag is also a named reference; depending on server permissions and policies, a tag can be deleted or moved.

When releasing, record the specific commit SHA, artifact version, and target environment. Do not merely record "deployed main", because a branch name does not precisely identify what ran. You can create a tag for the release version, protect tags on the server, and sign tags if the workflow requires provenance verification.

Example of creating and verifying a signed tag:

~~~
git tag -s v1.4.0 -m "Release v1.4.0"
git tag -v v1.4.0
git rev-parse "v1.4.0^{commit}"
~~~

Signed tags let recipients verify the tag's signature against configured trusted keys. They do not replace tag write protection, pipeline checks, or artifact verification. The pipeline should still record the commit SHA and checksum of the deployed package.

### 2.4. Git does not manage the actual state of an environment

A repository can contain Terraform, Kubernetes manifests, config files, or deployment scripts. These files describe the desired state, but actual state can drift due to manual changes, network errors, missing permissions, resources created out-of-band, or a failed deployment.

Git does not automatically detect and fix all such drift. In a GitOps model, Git stores the desired configuration while a controller such as Argo CD or Flux watches the repository, reconciles against the cluster, and performs synchronization. The controller, application runtime platform, and observability system remain separate components.

Rolling back source code also does not mean rolling back the entire system. A database migration may have deleted or transformed data irreversibly. An external service may already have received events or transactions. Therefore, design backward-compatible migrations, maintain a data recovery plan, and verify behavior after rollback.

## 3. Limitations of Git in backup and recovery

### 3.1. A repository includes only what has been recorded in history

Git primarily protects contents that have been committed and remain reachable through references or objects in the repository. A repository copy does not automatically include:

- Uncommitted changes in the working tree or staging area.
- Untracked files, files ignored by .gitignore, and data located outside the repository.
- Build artifacts, runtime data, databases, volumes, uploaded files, or object storage.
- Actual Git LFS content if you only copy the repository portion containing pointer files.
- Contents of submodule repositories if you only copy the parent repository.
- Hosting platform metadata such as pull requests, issues, release assets, access permissions, CI secret variables, and project settings.

A full clone typically has the commit history of references the remote exposes, whereas a shallow clone contains only part of the history. A clone also cannot carry uncommitted changes from the source machine. Therefore, before treating a clone as part of a backup plan, define the exact scope of data that needs to be recovered.

### 3.2. A remote does not equal an independent backup

Pushing commits to GitHub, GitLab, or another Git server keeps data outside your personal machine. That is a useful layer of protection, yet a remote can still face the same risk groups as the primary system:

- Compromised accounts or tokens.
- Deleted repositories, overwritten references, or altered permissions.
- Operational errors or provider outages.
- Malware or destructive actions affecting both the source and synced copies.
- History force-pushed, leaving commits unreferenced.

A continuously updated mirror can also receive reference deletions from the remote. Thus, a single mirror does not replace snapshots with separate retention history. Backups should reside on a system or account with independent administrative privileges, retention policies, and immutable or offline copies if data criticality requires them.

### 3.3. Creating repository copies and testing recoverability

You can create a mirror to copy the references published by a remote:

~~~
git clone --mirror <remote-url> project-backup.git
~~~

For small repositories or when you need a point-in-time archive, you can create a Git bundle from existing references:

~~~
git bundle create project-2026-11-17.bundle --all
git bundle verify project-2026-11-17.bundle
~~~

The bundle can be stored in an independent backup location. You can test cloning from the bundle to verify readability:

~~~
git clone project-2026-11-17.bundle project-restore-test
~~~

The commands above only handle Git data reachable through the bundled references. They do not automatically back up Git LFS objects, submodule repositories, databases, artifacts, platform configuration, or uncommitted changes. For Git LFS, back up the LFS storage as well; for submodules, back up each child repository and ensure referenced commits still exist.

You can use the following command to check the consistency of the object database in a repository:

~~~
git fsck --full
~~~

A clean fsck result is a signal of object database integrity, not proof that the entire system can be recovered. Backup testing is complete only when the team performs a test restore into a separate environment and verifies history, files, LFS, submodules, and related data.

### 3.4. Designing backups around recovery objectives

A backup plan should specify:

- **Scope:** Which repositories, LFS storage, submodules, artifacts, databases, user files, configurations, and metadata need protection.
- **RPO (Recovery Point Objective):** The maximum amount of data loss or time window of changes that can be tolerated.
- **RTO (Recovery Time Objective):** How quickly the system needs to be operational again.
- **Frequency and retention:** Hourly, daily, or event-driven backups; how long snapshots are kept.
- **Independence:** Which separate account, storage system, or privilege domain holds the copy.
- **Permissions and encryption:** Who can read, delete, or restore backups; where encryption keys are stored.
- **Testing:** Who performs the restore test, what is verified, and how often it runs.

A backup that has never been restore-tested is merely copied data. Regular restore drills frequently catch gaps early, such as missing keys, missing LFS objects, missing submodules, or missing access permissions.

## 4. Limitations of Git in secret management

### 4.1. .gitignore is not a security mechanism

Files such as .env, private keys, tokens, database passwords, and certificates can enter a repository by mistake. Adding a filename to .gitignore tells Git to ignore untracked files on future adds, but does not automatically remove an already-tracked file from the index or history.

For example, if .env was already committed, adding .env to .gitignore alone is not enough. You can remove the file from the index while keeping it on your working machine:

~~~
echo .env >> .gitignore
git rm --cached -- .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

After this operation, new commits no longer track .env, but older commits may still contain the file's content. Anyone with read access to old history can retrieve that secret.

### 4.2. Deleting a secret from a new commit does not erase old history

Git commits reference content objects. A change that deletes a token from the current file only creates a new state; old objects and commits can still exist in history, reflogs, collaborators' clones, forks, caches, or backups.

If a secret has been committed or pushed to a remote, treat it as a secret exposure incident:

1. **Revoke or rotate the secret immediately.** Invalidate the old token, password, key, or certificate; issue new credentials and review usage logs. This directly reduces immediate risk.
2. **Determine the exposure scope.** Check commits, branches, tags, pull requests, forks, CI logs, artifacts, and copies that may have received the content.
3. **Purge the content from history when needed.** Use a dedicated tool such as git-filter-repo to rewrite history, then update remote references according to a coordinated plan.
4. **Resynchronize clones.** Collaborators must follow team instructions because rewritten history can cause pull, push, or merge operations on old clones to reintroduce the commit containing the secret.
5. **Check replicas and related systems.** Contact platform administrators to handle caches, forks, or stored copies according to the provider's policies; audit logs and artifacts.

Rewriting history affects everyone using the repository and does not guarantee reclaiming every distributed copy. Nor does it replace revoking the old secret. Never just force-push and assume the incident is resolved.

### 4.3. Appropriate places to store secrets

A repository should contain variable names, configuration structure, and non-sensitive sample values. For example, you can commit a .env.example file with placeholders:

~~~
DATABASE_HOST=localhost
DATABASE_USER=app_user
DATABASE_PASSWORD=replace-me
API_TOKEN=replace-me
~~~

Real values should be injected from a secret manager or the CI/CD platform's and runtime environment's secret management mechanism. Helpful principles:

- Grant secrets only to the specific application, environment, and time window required.
- Use short-lived tokens or workload identity mechanisms such as OIDC when supported by the platform.
- Apply least privilege; separate read permissions for production secrets from everyday development permissions.
- Never print secrets into logs, error messages, URLs, or pipeline outputs.
- Rotate keys according to policy and maintain a revocation process for suspected exposure.
- Enable secret scanning where appropriate and resolve alerts before merging.

In some workflows, teams may store encrypted configuration in Git using tools like SOPS. In that case, decryption keys must be managed independently and granted only to authorized people or workloads. Encryption protects data at rest, but does not protect it if plaintext gets written to logs, build machines, or insecure temporary files.

Pre-commit hooks can help catch secrets before committing, yet users can bypass hooks and local hooks are not enforced uniformly across every contributor. Combine server-side or CI checks, branch protection policies, and a secret manager. Restricting repository access permissions is also vital because anyone with read access to a repository can read all history the platform exposes.

## 5. Choosing tools by responsibility

| Need | What can Git do? | Components to add |
|---|---|---|
| Tracking source code and configuration | Commits, branches, merges, tags, diffs, and history | Review rules, branch protection, and repository permissions |
| Releasing software | Provide a commit or tag as input | CI/CD, build runners, artifact registry, deployment controller, and monitoring |
| Tracking infrastructure configuration | Store desired configuration as text | Terraform or config tooling, GitOps controller, and drift detection |
| Backing up source code | Clone, mirror, bundle, and object verification | Independent backups, snapshots, retention, delete protection, and restore drills |
| Backing up the entire application | Does not automatically include runtime data | Database backups, object storage, volumes, LFS, submodules, and required metadata |
| Managing secrets | Store placeholders or configuration references | Secret manager, CI/CD secret variables, OIDC, access control, and secret scanning |

No single Git command replaces the components above. Git excels when used as a traceable source of history and a versioned input to specialized workflows.

## 6. Recommended practical workflow

A workflow can combine Git with other systems as follows:

1. Developers create a branch, commit changes, and open a pull request. Reviews focus on the diff, tests, and impact of the change.
2. CI checks source code, dependencies, secrets, and policies. Once requirements pass, the pipeline builds the artifact and tags it with the commit SHA.
3. Releases are marked with protected tags; the pipeline records the tag, commit SHA, artifact checksum, and approver.
4. CD deploys the tested artifact to the target environment, pulls configuration and secrets from managed sources, then runs health checks and monitors metrics.
5. During an incident, the team identifies the running artifact and commit, and evaluates rollback feasibility for the application, migrations, and data before acting.
6. Backups run on a defined schedule and scope. Copies are stored independently with retention, deletion access controls, and periodic restore tests.
7. If a secret is committed, the team revokes or rotates the secret first, then handles history and copies per incident response procedures.

This workflow creates a traceable link between source code changes, artifacts, deployments, and environments. It also helps distinguish source code bugs, build failures, deployment errors, configuration drift, and data incidents.

## 7. Checklist to remember

**Before deploying**

- [ ] Identify the exact commit SHA and artifact to deploy.
- [ ] Verify tests, dependencies, configuration, and build output.
- [ ] Ensure secrets are supplied from a secret manager or equivalent mechanism.
- [ ] Have health checks, monitoring, and a plan for migrations or rollback.

**When designing backups**

- [ ] List repositories, LFS storage, submodules, databases, user files, and metadata requiring protection.
- [ ] Define RPO, RTO, backup frequency, and retention period.
- [ ] Store independent copies with separate access and deletion permissions.
- [ ] Perform test restores and document results.

**When a secret is found in Git**

- [ ] Revoke or rotate the secret immediately.
- [ ] Identify affected commits, branches, tags, forks, logs, and artifacts.
- [ ] Coordinate rewriting history if needed and guide collaborators to resynchronize.
- [ ] Check replicas, strengthen secret scanning, and review the root cause.

The core takeaway is to use Git for version history and traceability. Deployment requires pipelines and operational controls; recovery requires independent, tested backups; secrets require dedicated vaults and provisioning/revocation workflows. Understanding these boundaries helps a team leverage Git effectively without placing responsibilities on it that a version control system was never designed to handle.
