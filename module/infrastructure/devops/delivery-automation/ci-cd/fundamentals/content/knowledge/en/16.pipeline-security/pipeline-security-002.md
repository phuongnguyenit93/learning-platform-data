# Protecting Main Branches, Pipeline Configurations, and Reusable Components

A CI/CD pipeline typically has permissions to read source code, fetch dependencies, produce artifacts, access secrets, and deploy applications. If an uncontrolled change can alter a workflow, bypass checks, or use an overly permissive token, an attacker can turn the pipeline into a path to modify release code or access internal systems. Therefore, pipeline security must start where changes are accepted, continue through how workflows are defined, and extend to every reused component.

Three areas require strict protection:

- **Main branches:** where reviewed source code is stored and which typically serve as the source for creating releases.
- **Pipeline configurations:** workflows, build scripts, policies, manifests, and runner configurations that determine what code is executed with what privileges.
- **Reusable components:** reusable workflows, actions, plugins, templates, build images, and shared scripts that multiple repositories may trust.

A change in any of these areas can affect many teams or multiple releases. This lesson covers how to configure branch protection, control changes to pipeline-as-code, manage reusable components, restrict permissions, isolate untrusted code, and maintain traceability during incidents.

## 1. The Pipeline Risk Model

A pipeline is not just a tool for running automated tests. It is a system with privileges to execute code and access resources. Those resources can include repositories, package registries, artifact stores, cloud accounts, deployment environments, secret managers, and internal systems.

An attack path often begins with a seemingly minor change:

1. An attacker submits a pull request or compromises a developer account.
2. A change is introduced into a workflow, build script, dependency, or shared component.
3. The pipeline runs the modified code on a runner that has secret access or network access.
4. Malicious code steals tokens, alters artifacts, modifies packages, or calls deployment APIs.
5. The tampered artifact or change enters the main branch or release environment.

The goal of pipeline security is to break this chain through multiple layers of control: branch protection, independent review, least-privilege permissions, component verification, runner isolation, and deployment approvals.

~~~mermaid
flowchart TD
    A["Source code or workflow change"] --> B["Pull request"]
    B --> C["Branch protection and review"]
    C --> D{"Required conditions met?"}
    D -- "No" --> E["Keep change out of main branch"]
    D -- "Yes" --> F["Merge into main branch"]
    F --> G["Protected pipeline"]
    G --> H["Verified reusable components"]
    H --> I["Job runs with least privilege"]
    I --> J["Traceable artifact and evidence"]
    J --> K["Environment approval / deploy gate"]
    K --> L["Release"]
~~~

Layers of control must reinforce each other. Branch protection does not help if reviewers do not know what permissions a workflow changed. A secure workflow is not enough if it invokes an uncontrolled external action. A version-pinned shared component still requires least-privilege permissions and review upon update.

## 2. Protecting Main Branches

Main branches are typically the source of integration and release. If anyone can push directly, force push, or delete the branch, checks and reviews can be bypassed. Branch protection or rulesets define the conditions required for a change to enter this branch.

### 2.1. Requiring Pull Requests Instead of Direct Pushes

For main branches, require changes to go through a pull request or merge request. This creates a control point to review contents, discuss risks, and verify check statuses before merging.

Policies typically include:

- Blocking direct pushes from regular accounts.
- Allowing merges only through the defined process.
- Requiring one or more independent approvals.
- Requiring all required status checks to pass.
- Requiring necessary conversations or review threads to be resolved.
- Restricting force pushes and branch deletions.
- Limiting who is allowed to bypass rules.

Having pull requests alone is not sufficient. If an author can self-approve sensitive changes or bypass checks on their own, the process still has weaknesses.

### 2.2. Number and Independence of Reviews

The required number of reviewers depends on the impact of the repository and the change. A shared library, release workflow, or script with deployment privileges may require a reviewer from the corresponding owning team.

Reviews must be independent of the change author. For sensitive changes, require at least one person with appropriate expertise or ownership. Do not allow the same person to author a change and self-approve an exception for that change when policy requires two-person control.

You can use CODEOWNERS or an equivalent ownership mechanism to require responsible teams to review specific paths, such as:

- CI/CD workflows.
- Build and deploy scripts.
- Dependency or plugin definition files.
- Infrastructure manifests and policies.
- Reusable components.
- Secret or environment protection configurations.

CODEOWNERS is only valuable when properly protected and reviewed. If a PR author can edit the ownership file to remove required reviewers in the same change, the mechanism can be neutralized. Protect the owner definition file itself and verify the platform's actual ownership enforcement rules.

### 2.3. Enforcing Critical Status Checks

Required status checks serve as conditions for merging. They should include checks that protect the shared branch, such as:

- Linting, static analysis, and unit tests.
- Build or compilation checks.
- Mandatory security checks.
- Workflow and configuration validation.
- Ownership or policy checks if supported by the system.

Check names must be stable, owned, and produced by trusted workflows. Watch out for duplicate check names: if multiple workflows or apps can emit the same check name, reviewers can mistake the result of an unrelated job for the required protection check.

Do not turn every warning into a required check. Select only checks with clear goals and sufficient stability to act as merge gates. Extended checks can run post-merge or pre-release, but must never silently replace a failed required check.

### 2.4. Testing Against the Latest Merged State

A pull request may pass checks on the source branch commit yet fail when combined with an updated main branch. You can require the source branch to be up to date with the target branch before merging, test a merge candidate, or use a merge queue/merge train.

When the target branch changes, old check results may no longer represent the state about to be merged. Re-run or confirm results for the exact merge candidate. With a merge queue, the pipeline must test the exact combination of changes the system intends to land on the main branch.

### 2.5. Protecting History and Commit Identity

In addition to reviews and status checks, you can enforce:

- Blocking force pushes on main branches.
- Blocking deletion of main branches.
- Requiring signed commits or verified identities per organizational policy.
- Restricting administrative privileges that can bypass branch protection.
- Recording audit logs for rule changes, bypasses, and merge actions.

Commit signing verifies that a commit was signed by an accepted key or identity. It does not prove the commit's contents are safe, so review and automated checks remain necessary. Likewise, protecting history does not replace artifact verification and release controls.

## 3. Protecting Pipeline Definition Files

Pipeline-as-code places workflows and automation configurations inside the repository. This enables changes to be reviewed and versioned, but also means a pull request can alter the checks and execution privileges themselves.

Files that must be treated as sensitive components:

- Workflow YAML or Jenkinsfile.
- Pipeline templates and reusable workflows.
- Build, test, package, and deploy scripts.
- Dockerfiles, build containers, and runner images.
- Action, plugin, or extension configuration files.
- IaC, deployment manifests, and network policies.
- Permission, environment, and secret reference declarations.

### 3.1. Reviewing Workflow Changes as Privileged Code Changes

A workflow change can grant jobs additional permissions, switch runners, access secrets, or trigger deployments. Reviewers should examine:

- Which events trigger the workflow?
- Which branches, tags, or PR sources are allowed to trigger it?
- Which jobs have read or write access to the repository?
- Which secrets can be accessed?
- Which networks or resources can the runner reach?
- Which actions or plugins are invoked?
- Where are artifacts created and published?
- Can gates or approvals be bypassed?

Do not review only YAML syntax. Examine the actual operational effect of the workflow and the privileges it creates.

### 3.2. Ownership and Sensitive Changes

You can assign ownership to workflow directories and deployment scripts. Changes in these areas should require reviewers accountable for the CI/CD platform or security.

For large repositories, shared workflows can be separated from application repositories, provided update permissions and the release process of the workflow repository are strictly controlled. If many projects call a single workflow, a change in that workflow can have a wide blast radius.

### 3.3. Pre-Merge Validation

Validate workflow structure and behavior before allowing a merge:

- Parse YAML and validate against schema.
- Verify that referenced actions/plugins exist.
- Check permissions and event triggers.
- Check input parameters and outputs.
- Verify no literal secrets exist in files.
- Detect dangerous shell commands or excessive permissions.
- Run tests for build and deploy scripts.
- Review diffs affecting runners, networks, and environments.

Automated validation does not replace human review. It catches common structural and policy violations, while reviewers evaluate the intent and impact of the change.

## 4. Restricting Workflow and Token Permissions

Workflows typically receive tokens or identities to read repositories, write statuses, download packages, publish artifacts, or call APIs. Broad default permissions increase the impact if a job is compromised.

### 4.1. Job-Level Least Privilege

Grant permissions at the narrowest scope possible:

- Jobs that only checkout and test should primarily need source read access.
- Jobs updating check statuses only need write access to the corresponding status.
- Package publishing jobs need write access only to the designated package namespace.
- Deploy jobs only need permission to deploy to allowed environments.
- Release jobs need dedicated release permissions and protective conditions.

If the platform supports declaring permissions at both workflow and job levels, set a minimal default and expand permissions only on the specific job that needs them. Never use a repository-wide admin token for every step.

### 4.2. Do Not Pass Tokens Across Unnecessary Jobs

Do not write tokens into outputs, artifacts, caches, or workspace files for downstream jobs to reuse. If another job needs permissions, issue a separate identity to that job. This limits the blast radius if a job runs untrusted code or leaks logs.

Tokens should be short-lived and narrowly scoped. When the platform supports OIDC or workload identity, prefer issuing temporary credentials bound to the repository, ref, environment, and workflow rather than storing long-lived cloud keys in secrets.

### 4.3. Distinguishing Platform Tokens from Application Secrets

CI-issued tokens are typically used to interact with the repository or platform APIs. Application secrets may include database passwords, signing keys, or external service credentials. These two groups serve different purposes and require different policies.

Never expose production secrets to pull request jobs from forks or untrusted sources. Masking secrets in logs provides no protection if malicious code can read the value from process memory or send it over the network.

## 5. Handling Pull Requests from Untrusted Sources

Pull requests from forks or external contributors may contain modified build scripts, tests, or workflows. When the pipeline executes this code, it must be treated as untrusted code.

Required safeguards:

- Use ephemeral runners or a dedicated pool for untrusted PRs.
- Never provide production secrets or write-privileged credentials.
- Restrict tokens to minimal read permissions.
- Block access to management networks and internal services.
- Disallow jobs from publishing official packages or deploying to shared environments.
- Destroy workspaces and temporary resources after the job completes.
- Grant elevated privileges only after review or through an explicit approval mechanism.

Some platforms have events or workflow modes that run in the context of the target repository even when the PR content originates from a fork. For example, exercise extreme caution with mechanisms like `pull_request_target`: the workflow may hold target repository privileges while processing externally controlled metadata or content. Never check out and execute scripts from an untrusted PR inside a job that holds secrets or write permissions.

If trusted operations are needed after a PR is reviewed, separate them into a distinct workflow or job with its own conditions, identity, and permissions. Do not rely on who opened the PR or which label was applied as proof that the code is safe.

## 6. Protecting Reusable Components

Reusable workflows, actions, plugins, pipeline templates, and shared scripts reduce duplication and standardize build/test/deploy practices. However, they also create a trust chain: a repository invokes an external component and grants that component permission to execute inside the pipeline.

If a shared component is altered or hijacked, many repositories can be affected simultaneously.

### 6.1. Pinning Versions to Immutable Identifiers

Do not reference external components by mutable branches like `main` or movable tags when strict control is needed. Pin to specific versions or immutable commit SHAs in accordance with platform policy.

Example of referencing an action by commit:

~~~yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<COMMIT_SHA_40_HEX>
~~~

This is an example for GitHub Actions; the placeholder must be replaced with a verified commit SHA. Pinning by SHA prevents the component's contents from changing silently when a branch or tag is updated. It does not prove the commit itself is safe, so source verification, change review, and security update monitoring remain necessary.

On other platforms, use the equivalent immutable version-pinning mechanism. If a platform only supports version tags, establish a process to verify tags, release sources, and registry immutability.

### 6.2. Inspecting Component Sources and Permissions

Before adopting an external action, plugin, or workflow, inspect:

- Repository owner and maintenance history.
- Executable source code and component dependencies.
- Permissions requested by the component.
- Whether it downloads scripts or binaries from dynamic URLs.
- Whether it sends data externally or alters runner configuration.
- Whether it provides release signatures, provenance, or a trustworthy release process.
- Update policy when vulnerabilities are discovered.

Prefer components from official sources or internal sources approved by the organization. For third-party components, maintain an allowlist or approval process before introducing them into critical workflows.

### 6.3. Wrapping External Components in Internal Workflows

An organization can create internal reusable workflows to standardize builds, tests, scans, or deployments. Internal workflows help:

- Enforce minimal default permissions.
- Standardize runners and environments.
- Control internal action versions.
- Define allowed inputs and outputs.
- Record consistent logs and metadata.
- Apply security updates in a single reviewed location.

However, internal reusable workflows are also high-impact components. The repository hosting them needs dedicated branch protection, owner reviews, testing, and versioned releases. Never allow callers to pass arbitrary shell commands, broad token permissions, or unrestricted secrets into a shared workflow.

### 6.4. Designing Clear Inputs and Secrets

Reusable workflows should declare typed inputs with safe defaults and validation. Avoid accepting an arbitrary shell command string and executing it directly.

Pass only the secrets the workflow actually needs. Avoid mechanisms like `secrets: inherit` when a workflow only needs one or two specific secrets, as this widens the exposure of sensitive data. Never write secrets to outputs or artifacts.

Outputs from reusable components must also be treated as untrusted input if they could contain content controlled by PR code. When passing outputs into a shell, sanitize or handle them properly rather than concatenating strings arbitrarily.

## 7. Controlling Versions and Updates of Shared Components

Pinning a version provides stability, but does not mean staying on old versions forever. Shared components receive security patches, API updates, and compatibility fixes.

A sound update workflow includes:

1. Monitoring component releases and security advisories.
2. Verifying the source and new version.
3. Reviewing the diff from the currently pinned version to the new version.
4. Checking changes to permissions, network usage, dependencies, and scripts.
5. Updating the pin in a pull request.
6. Running validation and tests on representative repositories.
7. Obtaining review from pipeline owners.
8. Releasing a new internal reusable workflow version if applicable.
9. Tracking adoption and retiring deprecated versions on schedule.

Dependency update bots can open PRs to update actions or plugins, but changes should not be auto-merged blindly. Updating executable components requires risk-based review.

### 7.1. Versioning Internal Workflows

Internal reusable workflows can be released using version tags or commit SHAs. Callers should pin tested versions. When broad updates are needed, create batch PRs or execute a planned upgrade rollout.

Avoid changing the security behavior of a workflow consumed by many projects without notice. If a vulnerable version must be revoked, maintain an emergency procedure to identify affected callers and swap out the version.

### 7.2. Avoiding Floating References for Release-Critical Workflows

Referencing a default branch is convenient for experimentation, but causes subsequent runs to execute different code without any change in the caller repository. For critical builds and deployments, use immutable references and upgrade via reviewed pull requests.

## 8. Protecting Runners and Deployment Environments

Runners are where code actually executes. If multiple trust levels share persistent runners, one job can leave behind files, processes, or credentials that affect the next job.

You should:

- Separate runners handling untrusted PRs from release/deploy runners.
- Prefer ephemeral runners for low-trust or high-privilege jobs.
- Avoid mounting the Docker socket or sensitive host filesystems for jobs that do not need them.
- Restrict outbound network traffic to required endpoints.
- Keep runner images and agents updated.
- Purge workspaces, tokens, containers, and temporary volumes after jobs.
- Monitor for anomalous processes and network connections.
- Prevent production runners from having broad access across all environments.

Deploy jobs need dedicated permissions and network paths. A regular build job should not be able to call production APIs simply because the runner sits on the same network.

### 8.1. Environment Protection

Staging and production environments can enforce protection rules such as manual approvals, allowed deployment branches, authorized deployers, or wait timers. These rules must be managed outside untrusted PR source code.

Approvals must be bound to the exact artifact, commit, and environment. If the artifact or configuration changes after approval, the approval conditions must be re-evaluated. Never reuse a single approval across multiple builds that do not share the same digest.

## 9. Protecting Artifacts and Pipeline Outputs

Artifacts produced by a pipeline become inputs to the release system. You must guarantee they originate from authorized workflows and commits.

Essential controls:

- Build artifacts from verified and accepted commits.
- Attach pipeline run ID, commit SHA, and builder identity.
- Compute digests and verify them after download.
- Restrict registry write permissions and prevent overwriting release versions.
- Separate temporary PR artifacts from release artifacts.
- Generate SBOMs or provenance when required by the process.
- Promote only artifacts that have passed all gates.
- Never rebuild a separate binary after testing and treat it as the same artifact.

An untrusted PR pipeline must never have permission to publish official packages. If preview artifacts are needed, store them in a temporary namespace with restricted access and short retention.

## 10. Controlling Policy Changes and Bypass Permissions

Branch protection, rulesets, default permissions, runner groups, and environment approvals are all security configurations. If someone can modify them without review or audit, all other controls can be disabled.

Define clearly:

- Who can create, edit, or delete branch protection/rulesets?
- Who can modify required status checks?
- Who can add or remove workflow owners?
- Who can register runners or modify runner groups?
- Who can grant access to secrets and environments?
- Who can bypass reviews or required checks?
- Are bypass actions audited and alerted?

Administrative privileges should be restricted to a small group using individual accounts with strong authentication. Break-glass emergency admin accounts must be managed separately, monitored, and used only with documented justification.

If an organization allows emergency bypasses, enforce a post-incident review process: record who performed the bypass, the reason, scope, affected commits/artifacts, and any follow-up checks required afterward. Bypasses must never become a routine shortcut for merging faster.

## 11. Conceptual Pipeline Protection Configuration Example

The following example illustrates a consolidated policy. It is not a complete executable configuration for any specific platform:

~~~yaml
repository_security:
  main_branch:
    direct_push: denied
    force_push: denied
    deletion: denied
    pull_request_required: true
    approvals:
      minimum: 2
      dismiss_stale_reviews: true
      require_code_owner_review: true
    required_checks:
      - lint
      - unit_tests
      - build
      - workflow_validation
      - security_scan
    require_up_to_date_or_merge_queue: true
    bypass:
      allowed_teams:
        - release_administrators
      audit_required: true

  pipeline:
    default_token_permissions: read_only
    job_level_permissions: true
    untrusted_pull_request:
      secrets: denied
      write_token: denied
      runner_pool: ephemeral_untrusted
      internal_network: denied
    release:
      runner_pool: isolated_release
      artifact_digest_required: true
      environment_approval: true

  reusable_components:
    external_actions:
      pin_to_immutable_revision: true
      approved_sources_only: true
      update_requires_review: true
    internal_workflows:
      code_owner_review: true
      versioned_release: true
      input_validation: true
      explicit_secret_mapping: true
~~~

In real implementations, map each item to the platform's branch rulesets, permissions, runner groups, environment protections, and reusable workflow mechanisms. Do not assume the field names in this example are standard configuration keys.

## 12. Responding When a Pipeline or Component Is Compromised

If a workflow, runner, or shared action is suspected of unauthorized modification, treat it as a software supply chain incident.

Response steps may include:

1. Identify affected repositories, workflows, runners, and time windows.
2. Pause affected workflows or revoke permissions of suspected components if needed.
3. Revoke tokens, secrets, or credentials that may have been accessed.
4. Inspect audit logs for branch rulesets, workflows, runners, and environments.
5. Identify commits, artifacts, packages, and deployments produced during that window.
6. Verify artifact digests, provenance, and release origins.
7. Isolate suspected runners; rebuild runners from trusted images.
8. Restore workflows or shared components to verified versions.
9. Rebuild artifacts from trusted sources if necessary.
10. Assess deployed environments and decide whether to roll back or deploy a clean build.
11. Document root causes and update policies to prevent recurrence.

Never merely revert a workflow commit and resume releasing without checking tokens, artifacts, and runners that may have been affected. A malicious workflow may have already exfiltrated secrets or altered packages before detection.

## 13. Common Design Mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Allowing direct pushes to main | Bypasses reviews and status checks | Enforce PRs and branch protection |
| Allowing force pushes or main branch deletion | Alters history, erases verified baselines | Block force pushes and deletion |
| Leaving workflow files unprotected | PRs can alter pipeline privileges and commands | CODEOWNERS, required reviews, and workflow validation |
| Broad default write permissions on tokens | Compromised job can modify repository or releases | Least privilege at workflow/job level |
| Running fork code with secrets | Leaks credentials or exposes internal resources | Isolated runners, no secrets or write tokens |
| Using actions on mutable branches | Execution contents change outside PRs | Pin immutable SHA/version and review updates |
| Reusable workflows accepting arbitrary shell commands | Callers can control privileged workflow behavior | Typed inputs, validation, and command restrictions |
| Unnecessary use of secrets inherit | Shares more secrets than required | Explicit per-secret mapping |
| Persistent runners shared across all trust levels | Leaks files, processes, or credentials across jobs | Separate pools and use ephemeral runners |
| PR artifacts published as releases | Untrusted outputs enter official registries | Separate namespaces and publish permissions |
| Unaudited bypasses | Cannot account for merge/release decisions | Restrict bypasses and enforce mandatory logging |
| Pinning versions without updating | Continues using components with known vulnerabilities | Monitor advisories and run an upgrade process |

## 14. Sample Scenario: Updating a Shared Action for a Release Pipeline

Suppose an organization has multiple repositories using an external action to log into the cloud and deploy applications.

1. The team discovers a suspicious change or security advisory affecting the current version of the action.
2. Workflow owners identify all repositories and workflows referencing that version.
3. The team pauses dependent deploy jobs if there is a risk of untrusted code execution.
4. Inspect the action source, referenced commit, token permissions, network access, and logs from recent runs.
5. Revoke potentially exposed credentials and audit produced artifacts.
6. Select a verified version or replace it with a vetted internal workflow.
7. Open a pull request updating the pinned SHA; CODEOWNERS requires review from the pipeline and security teams.
8. Workflow validation verifies permissions, inputs, outputs, and component sources.
9. Run tests on representative repositories using isolated runners and non-production credentials.
10. After approval, roll out the new version according to plan, monitor callers, and record the adopted version.

This scenario demonstrates that reusable components must be governed like executable dependencies. Sharing reduces duplication, but also expands the blast radius if a component is compromised.

## 15. Practice Roadmap

You can apply these steps on a sample repository:

1. **Inventory branches and permissions:** identify main branches and who can push, merge, bypass, and edit rulesets.
2. **Enable branch protection:** require pull requests, independent reviews, owner reviews, and required checks; block force pushes and deletion.
3. **Protect workflows:** identify CI/CD files, build/deploy scripts, and runner configs; assign owners and require reviews.
4. **Validate pipeline-as-code:** add YAML/schema checks, permission checks, trigger checks, secret reference checks, and action source checks.
5. **Reduce token permissions:** set defaults to read-only, granting write access only on jobs that need it.
6. **Test untrusted PRs:** confirm no production secrets, no write access, and no internal network access are available.
7. **Pin reusable components:** replace mutable references with verified immutable revisions; establish an update workflow.
8. **Separate runners:** create separate pools for PR, build, release, and deploy jobs by trust level.
9. **Protect artifacts:** separate preview and release artifacts, attach digests, and allow only trusted jobs to publish.
10. **Test bypasses:** exercise the emergency process in a test environment and verify audit logging works.
11. **Run an incident drill:** simulate a revoked reusable component and trace affected callers, credentials, artifacts, and runners.

### Completion Criteria

Learners can consider the lab complete when they demonstrate:

- Branch protection configured for main branches.
- Independent review and owner review required for sensitive pipeline files.
- Required status checks and merge-candidate verification configured.
- Workflows, build/deploy scripts, and policies protected from unreviewed changes.
- Tokens and secrets scoped per job.
- Pipelines processing code from forks or untrusted sources isolated.
- Reusable workflows/actions pinned and updated via immutable versions.
- Sources, permissions, and inputs/outputs of shared components verified.
- Runners, artifacts, and environment approvals protected.
- Bypasses, workflow changes, and artifacts traceable during an incident.

## Conclusion

Protecting main branches, pipeline configurations, and reusable components forms three interconnected layers of CI/CD security. Branch protection ensures changes are reviewed and verified before entering shared branches. Pipeline-as-code must be governed like privileged executable code, with ownership, validation, and least-privilege permissions. Reusable workflows and actions require trusted sources, immutable versions, explicit inputs, and reviewed update processes.

When combined with isolated runners, short-lived secrets, digest-bound artifacts, and audited bypasses, teams sharply reduce the chance that a compromised change or dependency can impact releases. More importantly, every decision from pull request to deployment becomes traceable and explainable with concrete evidence.
