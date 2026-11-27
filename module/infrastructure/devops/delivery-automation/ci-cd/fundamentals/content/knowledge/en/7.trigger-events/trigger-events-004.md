# Distinguishing Trusted Source Events from External Contributions

A CI/CD pipeline is typically triggered by multiple event types: pushes to the main branch, pull requests, release tags, schedules, or manual runs. These events do not carry the same level of trust. A push to a protected branch after review can be processed according to release policy; a pull request from a fork may contain code, scripts, and configurations controlled by an external party.

If a pipeline treats all events identically, an unverified contribution can cause a job to execute arbitrary code on the runner, read sensitive data, or abuse tokens with write permissions to the repository and deployment environments. Trigger design must therefore start by identifying **who can generate the event, which data in the event can be controlled by them, and what the job is permitted to do**.

## 1. Trigger Events and Trust Levels

A trigger event is the signal that causes the CI/CD platform to create a pipeline run. The event typically contains metadata such as repository, branch or tag, commit SHA, pull request, initiator, and operation type.

Common triggers include:

| Trigger | Common Purpose | Trust Considerations |
|---|---|---|
| Push | Verify changes just pushed to the repository | Who has permission to push to that ref? Is the branch protected? |
| Pull request / Merge request | Verify contributions before merging | Source code and workflows may be controlled by the contributor |
| Tag or release | Build artifacts and release a version | Who can create, edit, or delete tags? Are tags protected? |
| Schedule | Run periodic checks | Which ref are the workflow and configuration fetched from? |
| Manual dispatch | Allow operators to intentionally trigger a run | Who can launch it and what parameters can they pass? |
| Workflow completion | Trigger a flow after another workflow finishes | Is the prior workflow trustworthy and is the passed artifact verified? |
| External webhook | Receive events from external services | How are signatures, sender identity, and replay protection verified? |

An event cannot be assumed safe solely from its trigger name. For example, a push is an internal repository event, yet it may come from an experimental branch created by a contributor. Conversely, an external pull request may contain valid and helpful changes, yet the code within it must still be treated as untrusted until it passes checks and review.

Three concepts must be distinguished:

- **Event source:** the system or person that generated the trigger signal.
- **Code source:** the commit, branch, tag, and files that the job will check out or execute.
- **Run permissions:** the tokens, secrets, write permissions, network access, and resources granted to the job.

These three concepts are related but not identical. A workflow triggered by a legitimate event can still check out untrusted code. A contributor having an organizational account does not mean all of their changes have been reviewed. Trust levels must be determined by ref, review status, protection policies, and the actions the pipeline intends to perform.

## 2. Defining Trust Boundaries

Within a repository, input sources can be grouped to design policies. This is a reference model; organizations should adapt it to their actual permissions and review workflows.

| Source Group | Example | Default Handling |
|---|---|---|
| Protected release branch | main, release branch with required reviews | Can run internal jobs according to granted permissions |
| Protected release tag | v2.4.0 created by the release process | Can run build/publish after verifying the tag and creator permissions |
| Contributor branch in same repository | feature branch, newcomer's branch | Treat code as unapproved; do not grant production secrets |
| Pull request from fork | Forked repository submitting changes upstream | Treat code, scripts, and metadata as untrusted data |
| External workflow or template | Reusable workflow, action, or template from another repository | Pin versions and evaluate the permissions that component needs |
| External webhook | Registry, ticketing system, or deployment service | Verify signature, sender source, scope, and event freshness |

Trust boundaries do not necessarily align with organizational boundaries. A branch created by an employee can still contain unreviewed code, malicious dependencies, or altered build commands designed to exfiltrate data. Conversely, an external contribution can become trusted code after being tested, reviewed, and merged into a protected branch. Policies should rely on state and evidence rather than solely on identity or branch names.

A useful principle is that **the trust level of a run must never exceed the trust level of the inputs the job executes**. If a job runs scripts from an unreviewed pull request, that job must be restricted accordingly, even if the workflow itself is stored in the main repository.

## 3. Pull Requests from the Same Repository vs. from Forks

Pull requests are a collaboration mechanism, yet the two common cases differ in source code control.

**Pull requests from a branch in the same repository** typically have their source branch within the same repository. A contributor may have permission to push to that branch, but this does not mean the changes are approved. The pipeline must still verify the commit and never assume all new scripts or workflows are safe.

**Pull requests from forks** originate from a repository controlled by another owner. The submitter can modify source code, build scripts, dependency manifests, tests, and even workflow files included in the pull request. If the pipeline executes these files with privileged tokens or secrets, malicious code can exploit those privileges.

Example risk: a pull request modifies a test script to read environment variables and send their contents to an external server. If the job holds registry or cloud credentials, running the tests can leak those credentials. A pull request purporting to fix a single line of documentation does not eliminate the risk if the pipeline still executes the change's full script suite.

Therefore, for external contributions:

- Run required checks on isolated runners.
- Issue tokens with least privilege, typically read-only access to source code.
- Never pass release secrets, cloud credentials, or signing keys.
- Restrict artifact write permissions and repository modification permissions.
- Control network access if runners process high-risk code.
- Store logs and reports for reviewers to inspect before merging.
- Execute privileged tasks only after changes are reviewed and reside on a protected ref.

## 4. Distinguishing Triggers in GitHub Actions

GitHub Actions clearly illustrates how triggers affect execution context and permissions.

### 4.1. pull_request

The pull_request trigger is generally suitable for checking contributions before merging. For pull requests from forks, GitHub applies security restrictions to tokens and secrets according to repository settings. Nevertheless, teams must still design workflows so code inside the pull request receives no sensitive privileges.

Example CI workflow that only reads source code and runs Maven verify:

~~~yaml
name: Validate pull request

on:
  pull_request:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Check out pull request
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run tests
        run: ./mvnw --batch-mode verify
~~~

This example declares no secrets or write permissions. Because the job executes build and test code from the pull request, the runner must still be treated as an execution environment for untrusted code. For high-risk projects, use ephemeral runners with network isolation and no shared workspace reuse across runs.

### 4.2. push

The push trigger can run on multiple branches. If a pipeline needs release permissions, restrict branches and validate refs explicitly. Never assume every push comes from the main branch or an authorized releaser.

Example running a verification job only on the main branch:

~~~yaml
name: Validate main

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./mvnw --batch-mode verify
~~~

This is merely a ref selection condition. For main to truly be trustworthy, the repository needs branch protection, required checks, and appropriate review rules. If direct pushes are uncontrolled, restricting the trigger by the name main is insufficient to establish a security boundary.

### 4.3. pull_request_target

pull_request_target runs the workflow in the context of the target repository and can receive the target repository's permissions and secrets depending on configuration. This is helpful for certain pull request management tasks, but particularly sensitive when handling contributions from forks.

Risk arises when a privileged workflow checks out or executes code from the pull request. In that case, contributor-controlled code runs in a privileged context. This vulnerability class is commonly known as a **pwn request**.

Do not use pull_request_target to run tests, builds, scripts, or packages from an untrusted source branch. If you must use this trigger for metadata management tasks:

- Process only the necessary metadata from the event.
- Do not check out or execute pull request code.
- Do not interpolate titles, branch names, or user-controlled content directly into shell commands.
- Validate and escape data before passing it into APIs or display outputs.
- Grant only the exact permissions required for the task, such as pull request management permissions only if genuinely needed.
- Separate code-verification workflows (pull_request) from privileged status-management workflows.

### 4.4. workflow_run

workflow_run can trigger a workflow after another workflow completes. This is a useful mechanism for separating unprivileged CI from privileged tasks, yet outputs from the earlier workflow do not automatically become trusted data.

The second workflow must verify:

- The source workflow matches an allowed name or identifier.
- The source repository and ref are within scope.
- The source run corresponds to the intended commit or pull request.
- Downloaded artifacts have the expected origin, name, and content.
- Artifact data is never executed as scripts unless verified.
- Tokens and secrets of the second workflow are granted only after conditions pass.

Never download an artifact produced by an untrusted pull request and execute scripts inside it with high privileges. Artifacts must be treated as potentially tampered input data.

## 5. Designing Two Flows: Contribution Validation and Trusted Release

A common architecture separates the CI flow for contributions from the privileged release flow. The two flows have different goals and permissions.

The **contribution validation flow** runs on pull requests or unprotected branches. It can check out source code, lint, test, run static analysis, and generate reports. This flow requires only read permissions, receives no release secrets, and never deploys to production.

The **release flow** runs only after changes are merged into a protected branch or when a valid release tag is created. This flow can build official artifacts, publish to registries, and deploy through approval gates. Before granting permissions, verify the ref, commit, and release conditions.

~~~mermaid
flowchart TD
    A[Pull request or fork] --> B[Unprivileged CI]
    B --> C[Lint, test, scan]
    C --> D{Checks passed?}
    D -- No --> E[Return report to contributor]
    D -- Yes --> F[Review and merge]
    F --> G[Protected branch]
    G --> H[Release pipeline]
    H --> I[Build and verify artifact]
    I --> J[Approval / quality gate]
    J --> K[Deploy target environment]
    K --> L[Post-deploy verification]
~~~

Separating flows reduces the likelihood of unreviewed code accessing secrets and release permissions. However, the release flow still must verify artifacts, provenance, and usage permissions. Do not rely solely on a prior workflow having a green status.

## 6. Protecting Tokens, Secrets, and Runners by Trust Level

Each job should receive the minimum permissions sufficient to complete its task. Workflow or token permissions must match the event type and ref.

| Task | Typically Required Permissions | Permissions to Avoid Granting by Default |
|---|---|---|
| Pull request lint and unit tests | Read source | Write repository, publish packages, deploy |
| Generate verification reports | Read source, store artifacts per policy | Production secrets, signing keys |
| Post results or comments | Write permission scoped to the exact required resource | Full repository write access |
| Publish official artifacts | Write permission scoped to the target registry | Unrelated cloud admin permissions |
| Deploy staging | Credentials scoped to staging | Production credentials |
| Deploy production | Controlled production deployment permissions | Permissions broader than the service scope |

Practical rules:

- Declare permissions explicitly rather than relying on broad default permissions.
- Set permissions at the job level if different jobs have different needs.
- Use short-lived credentials or OIDC/workload identity when supported by the platform.
- Grant secrets only to jobs that genuinely need them, after trust conditions have been verified.
- Never print tokens, secrets, or sensitive content to logs.
- Never store credentials in caches or artifacts.
- Use ephemeral runners or clean workspaces for untrusted code.
- Never run privileged jobs on self-hosted runners with internal network access if input source code is untrusted.

Self-hosted runners require special attention. If a job from a fork can run on a runner shared with release jobs, malicious code may attempt to read leftover files, inspect other processes, steal host credentials, or probe internal networks. Segregate runners by trust level, wipe workspaces, and restrict OS permissions.

## 7. Verifying Events from External Systems

Beyond Git events, a pipeline may receive webhooks from registries, work-tracking systems, deployment platforms, or security services. Never trust a payload merely because an endpoint received a request.

A trustworthy webhook should verify at a minimum:

1. **Signature:** verify HMAC signatures or authentication mechanisms supported by the provider.
2. **Sender identity:** verify the configured endpoint, account, or application identifier.
3. **Freshness:** validate timestamps, nonces, or event IDs to mitigate replay risk.
4. **Scope:** accept only repositories, projects, event types, and resources on an allowlist.
5. **Consistency:** query resource state via a trusted API when the payload alone is insufficient evidence.
6. **Execution permissions:** map the event type to a bounded action; never let payloads arbitrarily choose shell commands.

For example, a webhook reporting that an image was published is not sufficient to deploy immediately. The pipeline should verify the registry, image repository, digest, build provenance, and scan policies before promotion.

If a webhook lacks a signature or proper verification mechanism, treat it merely as a signal prompting further verification. Never authorize deployments based solely on JSON content supplied by the sender.

## 8. Event Data Fields to Validate

A pipeline can use event data to choose execution paths, yet fields controlled by contributors must be treated as untrusted data.

| Field | Safe Usage |
|---|---|
| Repository / project | Compare against allowed repositories or projects |
| Event type | Accept only event types the workflow is designed to handle |
| Branch / ref | Match the full ref; never use arbitrary strings as commands |
| Commit SHA | Use as the source code identifier; verify the commit belongs to the expected repository and ref |
| Actor | Use for auditing and policy; never treat actor name as sole proof of trust |
| Pull request number | Verify it belongs to the right repository before calling APIs |
| Title, body, branch name | Treat as untrusted data; avoid interpolating directly into shells or queries |
| Artifact identifier | Verify source, digest, and access permissions before downloading or executing |

Never concatenate event data into shell commands via string interpolation. If data must be passed into scripts, use dedicated parameters, structured parsing libraries, and proper escaping rules. For branch names or pull request titles, do not assume they contain only letters, digits, and hyphens.

## 9. Criteria for Moving from Untrusted to Trusted

A contribution does not become trusted simply because its pipeline run succeeded. Passing tests is evidence of the checks that ran, not proof that code is non-malicious or bug-free.

A promotion process may require:

- The pull request has been reviewed according to policy.
- Required checks completed on the exact commit to be merged.
- The commit was merged into a protected branch.
- Dependencies and artifacts passed required security checks.
- The artifact is bound to a specific commit SHA and pipeline run ID.
- Verifiable provenance or build attestation if required by the organization.
- Authorized approval for release when required.
- Deployment uses the exact verified digest.

After merging, the release pipeline should build or retrieve artifacts through the official process. Do not reuse an artifact from a low-privilege pull request run as if it were a trusted release artifact, unless explicit provenance verification and promotion policies exist.

## 10. Situations Prone to Creating Vulnerabilities

| Situation | Risk | Mitigation |
|---|---|---|
| Using pull_request_target to run scripts from forks | Untrusted code executes in a privileged context | Use pull_request for tests; keep pull_request_target metadata-only |
| Granting secrets to all jobs | Pull requests can expose credentials | Separate jobs; scope secrets and permissions by ref |
| Checking only branch names | Branches may be contributor-controlled or refs altered | Verify ref, commit, branch protection, and review status |
| Using shared self-hosted runners | Malicious code may access workspaces or internal networks | Segregate runners by trust level; use ephemeral runners |
| Trusting artifacts from another workflow | Artifacts may contain tampered data or scripts | Verify source run, digest, and provenance |
| Interpolating titles or branch names into shells | Can lead to command injection | Pass parameters safely and sanitize untrusted data |
| Trusting unverified webhooks | Attackers can spoof events | Verify signature, timestamp, and scope |
| Using actor as sole trust criterion | Legitimate accounts can still submit unreviewed changes | Rely on ref, approvals, checks, and policy |

## 11. Secure Trigger Design Checklist

Before enabling a trigger or adding a new event-handling job, verify:

- [ ] Who can generate the event and which refs can trigger the pipeline are defined.
- [ ] The event source is distinguished from the code source the job will check out.
- [ ] Code from pull requests or forks is treated as untrusted before review.
- [ ] Jobs handling contributions have only the minimum necessary permissions.
- [ ] No release secrets or cloud credentials are granted to jobs executing untrusted code.
- [ ] Risks of pull_request_target and workflow_run are assessed if used.
- [ ] Runners executing untrusted code are isolated and cleaned after each run.
- [ ] Event fields such as title, body, branch, and actor are handled as untrusted inputs.
- [ ] External webhooks are verified for signature, sender source, and freshness.
- [ ] Artifacts from other workflows are verified for origin and digest before use.
- [ ] Release flows accept only commits and artifacts that have passed promotion criteria.
- [ ] Logs retain sufficient event type, repository, ref, commit SHA, and pipeline run ID for investigation.

Secure trigger design begins with understanding what each event represents and which data can be controlled by the sender. By separating contribution checks from privileged releases, scoping tokens and secrets per job, and verifying refs and artifacts before promotion, a pipeline can accept contributions from diverse sources while preserving security boundaries and traceability.
