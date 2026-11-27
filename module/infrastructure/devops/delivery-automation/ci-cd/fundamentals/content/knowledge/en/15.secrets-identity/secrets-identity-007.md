# Restricting Permissions for Untrusted Pull Request Pipelines

A Pull Request (PR) can contain changes to application code, build scripts, tests, dependencies, Dockerfiles, and even pipeline configurations. When CI runs a PR, the system does more than read the diff for review: it executes code supplied by the PR author. A Gradle build task, Maven plugin, npm lifecycle script, or test can execute system commands, read files on the runner, and make network requests.

If a PR comes from a fork or an untrusted contributor, the pipeline must treat all code and data supplied by the PR as untrusted input. If even a single job has repository write access, access to production secrets, internal network connectivity, or shares a machine with release jobs, a small change in the PR can become an escalation path.

This lesson explains how to restrict permissions for untrusted PR pipelines: defining trust boundaries, issuing minimal tokens, keeping secrets out of validation jobs, selecting isolated runners, protecting caches and artifacts, controlling high-privilege workflows, and separating PR validation from the release process.

## 1. Why a PR Pipeline Is a Security Boundary

A PR is meant to propose changes before merging. From CI's perspective, however, a PR can alter any file consumed by the build system. For example:

- A Gradle build script can declare arbitrary tasks.
- A Maven POM can add plugins that execute during the build lifecycle.
- An npm package can run scripts during dependency installation.
- Tests can read files, spawn processes, or send outbound requests.
- A Dockerfile can execute commands during image builds.
- Deploy or helper scripts can be modified to run different commands.
- Workflows can alter triggers, permissions, actions, or secret usage.

Therefore, "just running tests" does not make a job safe. Tests typically execute the exact source code and build logic that the PR just modified.

### Basic Trust Model

Workflows can be divided into two zones:

- **Untrusted workflow:** validates PRs from forks or untrusted sources. Its goal is providing build/test feedback with tightly restricted permissions.
- **Trusted workflow:** publishes artifacts, creates releases, accesses sensitive secrets, or deploys to environments. It runs only from source code and events that satisfy trust policies.

Reference flow:

~~~text
Pull Request from fork / untrusted contributor
                    |
                    v
          Untrusted CI workflow
          - Read-only source access
          - No production secrets
          - Isolated disposable runner
          - Build and test only
                    |
                    v
           Status checks and reports
                    |
              Review / approval
                    |
                    v
             Merge to protected main
                    |
                    v
           Trusted release workflow
           - Rebuild trusted commit
           - Publish immutable artifact
           - Obtain scoped identity
           - Deploy with approval
~~~

The critical boundary lies in what permissions and data are allowed across it. PR test results can be surfaced for review, but they must never automatically become high-privilege inputs to publish or deploy steps.

## 2. Assets That Must Be Protected

Before configuring workflows, list the assets a job might reach:

| Asset | Risk If Accessed by an Untrusted PR |
|---|---|
| Repository write token | Modifying branches, tags, releases, or repository contents |
| API tokens and credentials | Accessing external services or impersonating identities |
| Cloud credentials | Reading data, provisioning resources, or modifying infrastructure |
| Production secrets | Accessing live systems and sensitive data |
| Registry write permission | Replacing published images or packages |
| Self-hosted runners | Reading leftover files, credentials, or data from other jobs |
| Shared caches | Injecting forged data into subsequent trusted builds |
| PR artifacts | Introducing untrusted binaries or scripts into the release flow |
| OIDC identities | Obtaining cloud credentials if trust policies are overly broad |
| Internal network | Accessing databases, control planes, or private services |

Not every job should have access to every asset. The design goal is ensuring PR jobs receive only the exact permissions needed to validate code and publish check results.

### Treat Every PR-Controlled Component as Executable Code

Executable behavior is not limited to `.java` or `.js` files. Treat all of the following as inputs capable of altering job behavior:

- Build scripts, plugins, and dependencies.
- Test code, fixtures, and test data.
- Dockerfiles, shell scripts, PowerShell scripts.
- Invoked workflows or reusable workflows.
- Git submodules, package install hooks, and code generators.
- Configuration files loaded by parsers or tools at runtime.

If a job runs a command from the repository, assume the PR can change how that command behaves.

## 3. Permission Design Principles for Untrusted Pipelines

### Least Privilege

Grant minimum permissions per job. Compile/test jobs typically need only read access to source. They do not need permissions to write to the repository, create releases, publish packages, or deploy to production.

Declare `permissions` explicitly rather than relying on broad repository or organization defaults.

### Never Give Secrets to Untrusted PRs

PR validation jobs should run without sensitive secrets. If integration tests require authentication, use test accounts with very narrow permissions, synthetic data, and an isolated environment. Never use production credentials merely for test convenience.

### Isolate Execution Environments

Every job should run in a clean environment without sharing workspaces, credentials, or sensitive volumes with other jobs. Prefer ephemeral runners torn down upon completion.

### Separate Validation from Release

PRs only produce verification evidence. Publishing and deployment are performed by separate workflows after changes are merged into a protected branch and satisfy release policies.

### Re-verify Inputs at the Trust Boundary

Never treat artifacts, caches, reports, or metadata produced by a PR as trustworthy simply because PR CI passed. When releasing, rebuild from the merged commit using a trusted workflow and verified dependencies.

## 4. Pipeline Tokens and Repository Permissions

Many CI platforms automatically provide a token to jobs. This token can check out source, read PR metadata, download artifacts, or call APIs. If the token carries write permissions, PR code may attempt to abuse those permissions.

### Grant Only Read Permissions to PR Validation Workflows

GitHub Actions example:

~~~yaml
name: pr-validation

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - name: Checkout pull request
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle

      - name: Build and test
        run: ./gradlew --no-daemon check
~~~

This example highlights key practices:

- Trigger is `pull_request`.
- Token has only `contents: read`.
- Checkout does not persist Git credentials in the local repository config.
- Job receives no production secrets.
- Job builds and tests on a standard hosted runner.

Action versions in this example use major tags for readability. Repositories with strict supply-chain requirements should pin actions to full commit SHAs and review updates.

On GitHub, fork PRs generally receive restricted tokens and are denied repository secrets by default. However, verify repository/organization settings and exact event types; never rely on defaults without explicitly declaring `permissions`. Dependabot and similar automation flows also have their own restriction rules.

### Do Not Grant Write Permissions Just to Post Comments

A workflow might need to post test results or labels on a PR. Do not grant `pull-requests: write` to the entire build/test job just for that need.

Split it into two jobs:

- Code validation job: read-only source access, no secrets, no write permissions.
- PR update job: handles only required metadata, holds limited write permissions, and neither checks out nor executes PR code.

If the PR update job must read PR-supplied data, pass it strictly as plain data, validate it, and bound its length; never interpolate it into shell commands or executable code.

## 5. Distinguishing `pull_request` and `pull_request_target`

GitHub Actions provides two events commonly discussed when designing PR workflows.

### `pull_request`

The `pull_request` event is suited for PR build/test runs. For forks, workflows typically execute under restricted token and secret policies. Default checkout in a PR context typically checks out the merge ref to test the combined change against the target branch; if checking out the head SHA instead, understand that you are testing only the source branch's commit in isolation.

This is usually the right choice for CI that needs no write permissions or secrets.

### `pull_request_target`

`pull_request_target` runs the workflow in the context of the target repository. It can receive target repository permissions and secrets according to configuration. This is useful for controlled metadata operations like labeling or commenting on PRs, but dangerous if the workflow downloads and executes code from the PR branch.

**Never check out and execute PR code inside a privileged `pull_request_target` job.** If PR build scripts, tests, or actions execute in this job, untrusted code can attempt to access available tokens or secrets.

Example of behavior to avoid:

~~~yaml
on:
  pull_request_target:

jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: ./gradlew check
~~~

This workflow checks out code from the PR and executes build scripts inside the `pull_request_target` context. This is a high-risk pattern.

If `pull_request_target` is needed for metadata:

- Use only reviewed workflows from the default branch.
- Never check out the PR head.
- Never run scripts, actions, or build tools from PR contents.
- Never interpolate event data unsafely into shell commands.
- Grant only the exact API permissions required for metadata actions.
- Keep logic simple and easy to audit.

If building/testing is needed, use a `pull_request` workflow with read-only permissions and an isolated environment.

## 6. Avoiding Command Injection from PR Data

PR titles, branch names, commit messages, usernames, and descriptions are all controlled by the submitter. Interpolating these values directly into shell scripts allows data to be interpreted as command syntax.

Unsafe example:

~~~yaml
- name: Print PR title
  run: echo "${{ github.event.pull_request.title }}"
~~~

Expressions are substituted before the shell runs. If the title contains shell metacharacters, the resulting command can diverge from the workflow author's intent.

A safer approach is passing values via environment variables and treating them as data:

~~~yaml
- name: Print PR title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: printf '%s\n' "$PR_TITLE"
~~~

Key principles:

- Never interpolate event data directly into `run` scripts.
- Pass data via controlled environment variables or input files.
- Quote variables when referencing them in shells.
- Validate type, length, and character set before using values as arguments.
- Never use `eval` or concatenate data into commands.
- Never write unfiltered PR data into `GITHUB_ENV` or `GITHUB_OUTPUT` in a way that could inject extra directives.
- In PowerShell, pass via environment variables and treat as literal string data; avoid direct concatenation into command strings.
- Never embed titles, branch names, or commit messages into filenames/paths without sanitization.

Environment variables prevent shell parsing at script-generation time, but they do not automatically make data trustworthy. If a value is later passed to a shell command, SQL query, template, or sensitive API, it must still be validated and encoded appropriately for that context.

## 7. Never Give Production Secrets to PR Builds/Tests

Build tools and tests can run arbitrary code. If a job holds secrets, PR code can read environment variables, credential files, process arguments, workspaces, or metadata services and exfiltrate them.

### Use Test Data and Test Credentials

If integration tests require authentication:

- Create dedicated test accounts.
- Grant access only to synthetic data or test namespaces.
- Enforce tight quotas and short lifetimes.
- Never share passwords or tokens with staging/production.
- Revoke credentials once no longer needed.
- Restrict runner network egress to only the exact test services.

Whenever possible, use mocks, service containers, or ephemeral environments so tests need no external secrets.

### Do Not Rely on Secret Masking

Masking only hides exact strings in logs using platform filters. It does not stop malicious code from reading secrets or exfiltrating them over the network. Code can encode, split, or transform values before output. Therefore, the primary control is withholding secrets from untrusted jobs entirely.

### Be Careful with Reusable Workflows

Reusable workflows can receive secrets from callers or be configured to inherit secrets. Never use `secrets: inherit` with an untrusted caller if the called workflow holds broad privileges. Explicitly declare which secrets are passed, which jobs use them, and which conditions authorize invocation.

## 8. Selecting Runners and Isolation Levels

The runner is where PR code executes. If a runner caches credentials or can reach internal systems, host-level privileges can matter more than repository token permissions.

### Prefer Ephemeral Runners

For PRs from forks or untrusted sources, prefer standard hosted runners or ephemeral runners created exclusively for the job. After the job finishes, the environment and temporary storage are destroyed.

Runners should provide:

- A dedicated workspace per job.
- No pre-stored production credentials.
- No unnecessary mounts of home directories or privileged sockets.
- Restricted network egress per requirements.
- No shared data volumes across jobs in different trust zones.
- Post-run cleanup of files, processes, and containers.

### Avoid Long-Lived Self-Hosted Runners for Untrusted PRs

A long-lived self-hosted runner may contain:

- Runner registration tokens or cloud credentials.
- Caches and workspaces from previous jobs.
- SSH keys or internal configuration files.
- Network reachability to databases, registries, and control planes.
- Access to the Docker daemon or Kubernetes cluster.

If an untrusted PR runs on that host, code may attempt to read leftover data or tamper with future jobs. Shell executors are especially vulnerable because commands run directly on the host. Container executors also do not guarantee isolation if containers run privileged, mount the Docker socket, or hold broad host permissions.

Only use self-hosted runners for untrusted PRs when proper isolation is engineered: ephemeral single-use runners, zero long-lived secrets, no sensitive network access, and tested security boundaries.

### Runner Labels Are Not a Standalone Security Boundary

Labels/tags only select runners. They do not replace repository access controls, protected runners, network policies, and isolation. Configure the platform so untrusted repositories or pipelines cannot claim a privileged runner simply by adding a label in YAML.

## 9. Protecting Caches Against Poisoning

Caches accelerate dependency resolution and builds, yet caches store job-generated data. If an untrusted job writes a cache that a trusted release job later reads, tampered data can corrupt downstream builds.

Risk scenarios:

- A PR writes poisoned files into a shared cache.
- A release job restores a cache containing PR-created artifacts.
- Caches contain modified executables, scripts, or dependencies.
- Caches contain credentials or sensitive config files.
- Overly broad cache keys cause multiple branches or trust zones to share data.

Safeguards:

- Separate caches by trust zone and repository/branch scope.
- Use cache keys incorporating lockfile hashes, toolchains, and relevant inputs.
- Never allow PR jobs to write to caches consumed by trusted release jobs.
- Never cache secrets, credentials, or home directories.
- Treat caches as untrusted mutable data; verify dependencies via lockfiles and checksums.
- For critical releases, consider clean builds or restoring only from tightly controlled caches.

Cache scoping mechanisms vary across platforms. Understand exactly which jobs can read and write which caches, especially for fork PRs and merge request pipelines.

## 10. Treat PR Artifacts and Reports as Untrusted Data

A PR job can upload any permitted file. That artifact may contain intentionally crafted binaries, scripts, HTML reports, or archives.

Avoid:

- Downloading PR artifacts and executing scripts or binaries inside high-privilege jobs.
- Using JARs or container images from a PR as release artifacts.
- Letting trusted deploy workflows blindly consume artifacts based solely on filename.
- Extracting archives without path-traversal or size checks.
- Trusting HTML report contents that may contain scripts when rendered in privileged contexts.

If test reports must be retained for review, scope them to the PR and display them safely. When producing release artifacts, a trusted workflow should rebuild from the merged commit and generate fresh artifacts with explicit digests and provenance.

### Separate Artifact Namespaces

Use names or namespaces that indicate source and trust level, but never rely solely on naming for authorization. Metadata must include repository, commit SHA, workflow run, trigger source, and digest. Release jobs must verify these attributes before consuming artifacts.

## 11. Controlling OIDC and Cloud Permissions

OIDC lets jobs obtain short-lived identities from the CI platform to access cloud resources or secret managers without storing long-lived access keys. However, if trust policies are too broad, an untrusted PR could request a token and acquire unintended credentials.

### Grant `id-token` Only When a Job Genuinely Needs It

In GitHub Actions, `id-token: write` allows a job to request an OIDC token. Do not set this permission at the workflow level for all jobs when only a single deploy job requires it.

Example of job-level permission scoping:

~~~yaml
on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon check

  deploy:
    needs: verify
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      id-token: write
    environment: production
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Obtain deployment identity
        run: ./scripts/deploy-with-oidc.sh
~~~

This illustrative workflow runs only on pushes to `main`. The actual cloud authentication step depends on the provider and should use reviewed actions/CLIs. The `verify` job has no permission to request OIDC tokens; only the `deploy` job holds this permission and is further gated by the `production` environment.

### Trust Policies Must Restrict the Issuance Source

Cloud roles should verify appropriate claims, such as:

- Exact repository or project.
- Owner or organization.
- Protected branch or ref.
- Allowed workflow identity or reusable workflow.
- `production` environment if using environment claims.
- Exact audience matching the token-receiving service.
- Allowed event or pipeline type, if supported by claims and platform.

Never use overly broad wildcards like every repository in an organization or every branch if granted permissions can alter production infrastructure. Test and inspect token claims across each event type before enabling permissions.

### Approvals Are an Additional Layer of Control

Environment protections, required reviewers, and deployment approvals control when a job may reach production. They do not replace restricting tokens, runners, and source code. An approved job executing untrusted PR code can still abuse whatever permissions that job receives.

## 12. Separating PR Workflows from Release Workflows

A secure architecture typically separates workflows into two distinct privilege tiers.

### PR Workflow

- Triggered by `pull_request` or `merge_request_event`.
- Runs linting, builds, unit tests, and static checks.
- Has read-only source access.
- Has no production secrets.
- Has no publish or deploy permissions.
- Uses isolated runners.
- Treats artifacts and caches as untrusted.

### Post-Merge Workflow

- Triggered by pushes to protected branches or protected release tags.
- Checks out the exact merged commit.
- Builds artifacts in a trusted environment.
- Runs mandatory tests and security gates.
- Generates digests, provenance, and stores immutable artifacts.
- Grants publish or deploy permissions only to the specific jobs that need them.
- Enforces approvals and post-deployment verification.

This separation guarantees release artifacts are built from merged commits rather than relying on binaries uploaded by a PR.

### Be Careful with `workflow_run`

A trusted workflow triggered upon completion of a PR workflow can execute with higher privileges than the originating workflow. If it downloads a PR artifact and executes, extracts, or treats it as trusted code, the security boundary is broken.

If using `workflow_run`:

- Verify repository, workflow, event, branch, and run ID.
- Never execute artifacts or scripts from an untrusted workflow.
- Never pass secrets into steps processing PR-controlled content.
- Restrict the token permissions of the downstream workflow.
- Ideally use reports strictly as display data; rebuild from the merged commit before publishing.

## 13. GitLab Merge Request Pipelines and Runners

GitLab provides shared/instance runners and group-managed self-hosted runners. Merge request pipelines can run code supplied by the source branch, so variables, runners, and job permissions must be controlled.

Key areas to review:

- Use CI/CD variables with appropriate scopes and protections.
- Do not expose protected variables to merge requests that fail protection requirements.
- Protected runners only accept jobs from refs permitted by protection policies; check exact behavior for your GitLab version and project/group settings.
- Never run merge requests from forks on runners with internal network access or production credentials.
- Check settings allowing fork MR pipelines to run in the parent project, as that context can alter visible resources and permissions.
- Never enable write permissions or secrets just so an MR job can update the repository.
- Use protected environments and approvals for deployments.
- Never use shell executors on broadly privileged hosts for untrusted MR code.

Example validation job using a runner tag dedicated to routine unprivileged CI:

~~~yaml
stages:
  - verify

verify:
  stage: verify
  tags:
    - linux-ci-untrusted
  variables:
    GIT_STRATEGY: clone
  script:
    - ./gradlew --no-daemon check
~~~

The `linux-ci-untrusted` tag is illustrative. Register appropriate runners, ensure they carry no secrets or internal privileges, and configure projects so unrelated jobs cannot misuse them. Using `clone` creates a cleaner workspace, but it does not replace host isolation.

GitLab has specific settings for protected variables and runners in merge request pipelines whose behavior varies across versions. Verify actual behavior in your running version, especially when source and target branches belong to different projects.

## 14. Pre-Run Workflow Review Checklist for PRs

### Triggers and Permissions

- [ ] Fork PRs run on appropriate triggers such as `pull_request` or `merge_request_event`.
- [ ] Workflows declare minimal `permissions` and avoid `write-all`.
- [ ] Build/test jobs have no permissions to write to the repository, publish, or deploy.
- [ ] No production secrets are exposed to untrusted PRs.
- [ ] `id-token: write` is omitted unless a job genuinely needs cloud identity.
- [ ] `secrets: inherit` is never used for workflows callable from untrusted sources.

### Workflow Logic

- [ ] `pull_request_target` is never used to check out and run PR code.
- [ ] PR titles, branch names, and PR body fields are never interpolated directly into shell scripts.
- [ ] `eval` and turning data into executable commands are avoided.
- [ ] Actions, reusable workflows, and critical dependencies are reviewed/pinned per policy.
- [ ] Jobs with write permissions are separated from jobs executing PR code.

### Runners and Resources

- [ ] PRs run on hosted runners or isolated ephemeral runners.
- [ ] Runners contain no long-lived credentials or stale workspaces.
- [ ] Docker sockets, host paths, and internal networks are not mounted unnecessarily.
- [ ] Caches are separated by trust boundary and contain no secrets.
- [ ] PR artifacts are never used as trusted release inputs.

### Releases

- [ ] Release workflows run post-merge on protected branches/tags.
- [ ] Artifacts are rebuilt from merged commits.
- [ ] Publish/deploy steps use short-lived identities and restricted permissions.
- [ ] OIDC trust policies constrain repository, ref, workflow, and environment.
- [ ] Production enforces approvals and auditing.
- [ ] Deployment records store commit, artifact digest, and verification results.

## 15. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Remediation |
|---|---|---|
| Exposing all repository secrets to PR jobs | PR code can read and exfiltrate secrets | Withhold secrets from untrusted jobs |
| Granting a write token to the whole workflow | Build scripts can modify repository or releases | Grant read-only; isolate write jobs |
| Using `pull_request_target` to build PRs | PR code executes inside a high-privilege context | Use `pull_request` for builds/tests |
| Running PRs on long-lived self-hosted runners | Can compromise host or read other jobs' data | Use ephemeral, isolated, secret-free runners |
| Sharing caches between PRs and releases | Cache poisoning corrupts trusted builds | Separate cache scopes and verify dependencies |
| Deploying PR artifacts once checks turn green | Artifacts from untrusted sources get released | Rebuild post-merge |
| Using OIDC trust wildcards | PRs can obtain unexpected cloud credentials | Bind claims to repo/ref/workflow/environment |
| Interpolating titles or branches into `run` scripts | Command injection risk | Pass via env, quote, and validate |
| Using `workflow_run` and executing PR artifacts | Downstream workflow's higher privileges get abused | Never execute untrusted artifacts |
| Relying on log masking | Secrets can still be read or exfiltrated | Withhold secrets in the first place |
| Giving every job a `production` environment | Expands access surface and complicates auditing | Restrict environments per job with approvals |

## Conclusion

Untrusted PR pipelines must be designed as code execution environments outside the trust boundary. Issue read-only tokens, keep production secrets out of jobs, prevent high-privilege workflows from executing PR code, use isolated runners, separate caches and artifacts, and constrain OIDC by repository, ref, and environment. Only after a PR is reviewed and merged into a protected branch should release workflows rebuild from the trusted commit, produce artifacts with provenance, and publish/deploy using dedicated identities. This separation lets CI give fast feedback to contributors without extending privileges to the release system.
