# Adding Quality Gates and Source-Trust-Based Permission Checks

In this hands-on lab, you will add a quality gate to your CI/CD workflow and design execution permissions based on the trust level of the pipeline's trigger source. The goal is to ensure every change is checked automatically while preventing code from pull requests or forks from accessing publish permissions, deployment permissions, or production secrets.

You will build two layers of control:

1. **Quality gate:** allows the pipeline to proceed only when required checks pass.
2. **Trust gate:** grants elevated permissions only to events and refs protected by the organization, such as a push to a protected branch after review.

A green pipeline does not automatically prove the source code is trustworthy. Nor does a commit from an internal branch inherently warrant production deployment rights. Permission decisions must be based on the event, repository, ref, protection policy, approvals, and job purpose.

This lab belongs to **DEVOPS_CI_CD_FUNDAMENTALS**: building a CI/CD mindset spanning Git events, pipeline-as-code, automated builds and testing, artifact management, environments, and quality gates.

## 1. Expected Outcomes

After completing this lab, you will be able to:

- Classify pipeline trigger sources by trust level.
- Define mandatory quality gates before merging or releasing.
- Separate untrusted code testing jobs from publish/deploy jobs.
- Grant least-privilege permissions per job instead of using a broad token across the entire workflow.
- Block a release whenever any required quality check fails.
- Verify behavior using both an untrusted PR scenario and a push-to-protected-branch scenario.
- Explain the risks of `pull_request_target`, self-hosted runners, and shared caches.

## 2. Lab Context and Architecture

Suppose the `sample-service` repository has a GitHub Actions pipeline. The service includes lint/format checks, unit and component tests, coverage thresholds, dependency vulnerability/license audits, secret scanning, and artifact builds. After merging into protected `main`, the pipeline may publish the artifact. Production deployment uses environment approvals and workload identity when supported by the platform.

Desired flow:

~~~mermaid
flowchart TD
    A["Pull request / fork"] --> B["Quality gate<br/>read-only token"]
    B --> C{"All checks pass?"}
    C -- "No" --> X["Fail checks<br/>no publish/deploy"]
    C -- "Yes" --> R["Review and branch protection"]
    R --> M["Merge into protected main"]
    M --> Q["Quality gate re-runs on main"]
    Q --> D{"Quality gate passes?"}
    D -- "No" --> X
    D -- "Yes" --> P["Build and publish<br/>scoped package permissions"]
    P --> E["Protected production environment"]
    E --> A2["Approval + deploy identity"]
    A2 --> V["Smoke test and post-deploy verification"]
~~~

A PR from a fork may run code supplied by an external contributor. Therefore, the PR testing job must be treated as executing untrusted code, even when the PR lives inside the organization's repository. This job receives only the permissions needed to read source and run tests; it never receives production secrets, publish permissions, or deploy permissions.

Once the change has been reviewed and merged into a protected branch, the pipeline can execute release steps with dedicated, job-scoped permissions.

## 3. Preparing the Repository

Create or verify a structure similar to:

~~~text
sample-service/
├── .github/
│   └── workflows/
│       └── ci.yml
├── scripts/
│   └── ci/
│       ├── lint.sh
│       ├── test.sh
│       ├── coverage-check.sh
│       ├── dependency-audit.sh
│       ├── secret-scan.sh
│       ├── quality-gate.sh
│       ├── build-release.sh
│       └── publish.sh
├── src/
├── tests/
└── README.md
~~~

The scripts serve as integration points with your project's toolchain. Replace the illustrative commands with the formatter, compiler, test runner, coverage tool, dependency scanner, and secret scanner used by your team.

Before starting:

- You have permission to create branches and pull requests.
- The repository has a `main` branch.
- You can run equivalent checks locally or on a runner.
- You know which scripts require dedicated dependencies and which require no secrets.
- You have a test registry/package destination if you want to exercise the publish step.

Do not use production credentials in this lab. If you do not have a test registry, use dry-run mode for the publish step.

## 4. Classifying Sources by Trust Level

Build a permission matrix before writing YAML:

| Source/Event | Default Trust Level | Appropriate Permissions | Do Not Grant |
| --- | --- | --- | --- |
| PR from fork | Untrusted | Read source, run quality checks on isolated runner | Secrets, publish, deploy, repository write access |
| PR from internal branch | Not yet authorized to release | Quality checks, read token | Production secrets, publish/deploy |
| Push to protected main after merge | Reviewed per branch policy | Build and publish artifact with narrow permissions | Broad organization or cloud admin privileges |
| Protected release tag | Trusted per release policy | Sign/publish/deploy after verifying tag and approval | Unnecessary long-lived credentials |
| Manual workflow dispatch | Depends on actor, ref, and approval | Only permissions matching protected ref and initiator | Treating all manual runs as trusted by default |
| Scheduled scan | Controlled workflow source | Read source, scan, and generate reports | Deploy permissions without a clear purpose |

**Internal does not mean trusted.** An internal PR can still contain unreviewed code. Only elevate release permissions after the change is merged into a protected branch/tag and satisfies policy.

### 4.1. Lab Trust Policy

- PR events run only the quality gate job.
- The workflow default is `contents: read`.
- Never pass secrets to jobs running PR code.
- Publish runs only when the event is a push to `main` and the repository matches the official repository.
- Publish must depend on the quality gate succeeding.
- Production deployment runs only through a protected environment and approval.
- OIDC permissions are granted only to jobs that genuinely require a cloud identity.

Do not rely solely on user-chosen branch names. Check the event type, repository identity, and ref together.

## 5. Building the Quality Gate

A solid quality gate has mandatory checks and clear pass/fail outcomes. Keep each step separate so you know which condition failed.

### 5.1. Defining Pass/Fail Criteria

| Check | Pass Condition | Blocking Condition |
| --- | --- | --- |
| Lint/format | No errors per project configuration | Lint or format errors present |
| Unit/component tests | All required tests pass | Any test fails |
| Coverage | Meets agreed threshold for measured scope | Below threshold or report missing |
| Dependency audit | No vulnerabilities exceeding policy; allowed licenses | Policy-prohibited findings present |
| Secret scan | No valid secrets detected in changes | Unhandled credentials detected |
| Build | Artifact created from current source revision | Build fails or artifact undefined |

Coverage thresholds should be based on a baseline and code criticality. Never inflate coverage with empty test assertions or exclude hard-to-test files from reports without review.

Dependency audits should distinguish new findings from time-bound accepted findings. Exceptions require an owner, rationale, scope, and expiration date; do not create permanent allowlists just to keep the pipeline green.

Secret scanners may flag credential-like strings that are not real secrets. Findings must be verified; if a credential was exposed, revoke/rotate it before recording a justified exception.

### 5.2. Creating the Quality Gate Orchestration Script

Create `scripts/ci/quality-gate.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

echo "== Lint and format =="
./scripts/ci/lint.sh

echo "== Tests =="
./scripts/ci/test.sh

echo "== Coverage =="
./scripts/ci/coverage-check.sh

echo "== Dependency audit =="
./scripts/ci/dependency-audit.sh

echo "== Secret scan =="
./scripts/ci/secret-scan.sh

echo "Quality gate passed"
~~~

`set -e` stops the script if a command fails; `-u` errors on unset variables; `pipefail` fails a shell pipeline if any command in the pipe fails. Every sub-script must return a non-zero exit code when policy fails.

If you need to collect all check results rather than stopping at the first error, use an explicit exit-status aggregation mechanism and still return a failing exit code at the end. Never swallow errors with `|| true` for mandatory checks.

### 5.3. Local Verification

~~~bash
chmod +x scripts/ci/*.sh
./scripts/ci/quality-gate.sh
~~~

If your project uses PowerShell or Windows runners, create equivalent scripts and ensure exit codes propagate back to CI. The goal is to run the exact same policy locally and on runners.

## 6. Creating a Workflow with Read-Only Default Permissions

The following example uses GitHub Actions. Third-party actions must be pinned by verified full commit SHAs. The string `<VERIFIED_40_HEX_SHA>` is a placeholder, not an executable value.

Create `.github/workflows/ci.yml`:

~~~yaml
name: CI quality and release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  quality-gate:
    name: Required quality gate
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout source
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Run required checks
        shell: bash
        run: ./scripts/ci/quality-gate.sh

  publish:
    name: Publish trusted artifact
    needs: quality-gate
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      github.repository == 'ORG/REPOSITORY'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - name: Checkout trusted source
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Build release artifact
        shell: bash
        run: ./scripts/ci/build-release.sh

      - name: Publish artifact
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: ./scripts/ci/publish.sh
~~~

Replace `ORG/REPOSITORY` with the full name of your official repository. Replace the SHA placeholder with the verified full commit SHA of the checkout action. In a real workflow, use the standard GitHub Actions `${{ github.token }}` expression to supply a short-lived token. Never write real tokens into YAML or logs.

If you do not use GitHub Packages, adjust `packages: write` and the publish script for your target registry, granting only the permissions actually required. If the publish script does not need a GitHub API token, remove `GH_TOKEN` and unneeded permissions.

### 6.1. Why Is the Workflow Split This Way?

- The workflow default is `contents: read`.
- `quality-gate` only reads source and runs tests; it needs no publish token.
- `persist-credentials: false` prevents checkout from persisting Git credentials in repository config for subsequent commands.
- `publish` depends on `quality-gate` via `needs`, so if the quality gate fails, `publish` does not run.
- The `if` condition requires a push to `main` and the exact official repository.
- Only the `publish` job has `packages: write`.
- PRs from forks or unmerged internal branches do not satisfy the `publish` condition.

This condition illustrates a post-merge publish flow. If releases are triggered by tags, define separate rules verifying protected tags and approvals; do not open it up to arbitrary tags.

## 7. Adding a Production Deploy Gate

Publishing an artifact and deploying to production are two distinct actions. An artifact may be published after the quality gate, while production deployment requires separate conditions.

~~~yaml
  deploy-production:
    name: Deploy production
    needs: publish
    if: >-
      github.event_name == 'push' &&
      github.ref == 'refs/heads/main' &&
      github.repository == 'ORG/REPOSITORY'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Checkout deployment scripts
        uses: actions/checkout@<VERIFIED_40_HEX_SHA>
        with:
          persist-credentials: false

      - name: Deploy using workload identity
        shell: bash
        run: ./scripts/ci/deploy-production.sh
~~~

In repository settings, configure the `production` environment with required reviewers, branch/tag restrictions, and appropriate protection rules. `id-token: write` should only be granted to jobs needing an OIDC token to authenticate with a cloud provider; the cloud-side trust policy must restrict the exact repository, branch/environment, and audience.

If OIDC is not configured yet, do not add long-lived cloud access keys to the PR workflow. You can stop the lab at the publish dry-run step and document the deploy gate as an extension.

## 8. Never Use pull_request_target to Run Untrusted PR Code

`pull_request_target` runs the workflow in the context of the target repository and can receive elevated permissions/tokens/secrets compared to regular PR workflows. Dangerous anti-pattern:

1. The workflow is triggered by `pull_request_target`.
2. The workflow checks out the contributor's PR head commit.
3. The workflow runs scripts from that checkout.
4. Untrusted scripts can read tokens or secrets available to the workflow.

For this lab, use `pull_request` for quality checks and supply no secrets. If you need to automatically label or comment on PRs via `pull_request_target`, run only trusted logic from the base branch; never check out and execute code from the PR head.

PR code remains untrusted even when the workflow uses `pull_request`. Run it on isolated hosted runners or ephemeral runners designed for untrusted workloads. Never use shared self-hosted runners with internal network access, credentials, or shared workspaces for PRs from forks.

## 9. Configuring Branch Protection

Workflows produce checks; branch protection prevents merging when required checks have not passed.

In repository settings, configure a branch protection rule or ruleset for `main`:

- Require a pull request before merging.
- Require the appropriate number of approvals.
- Enable the required status check corresponding to the `Required quality gate` job.
- Require branches to be up to date with the base branch if policy requires it.
- Restrict who can bypass rules.
- Restrict direct pushes to `main`.
- Set the repository/organization default `GITHUB_TOKEN` to read-only if the platform supports it.
- Use `CODEOWNERS` and require owner review for `.github/workflows/**`, `scripts/ci/**`, reusable workflows, and sensitive policies.

Workflows and CI scripts are part of the security boundary. A PR can modify the workflow file itself to alter permissions or job conditions; therefore, changes to these files require dedicated ownership review and should never be merged solely based on the results of a workflow modified by that very PR.

The displayed check name may include the workflow/job name or context depending on the platform. Select the exact check from an actual run; avoid selecting stale checks or checks that are no longer updated.

If a workflow does not run due to path/event filters, a required check may remain pending. Design triggers so every PR subject to policy produces the required check; leave no path that bypasses the gate.

## 10. Testing an Untrusted Source

Create a test branch or PR from a fork if the repository supports it. Verify:

1. The `pull_request` workflow triggers.
2. The `quality-gate` job runs on an appropriate runner.
3. The job's token has source read permissions only.
4. No production secrets or package write permissions exist in the job.
5. The `publish` job is skipped because the event is not a push to protected `main`.
6. The `deploy-production` job does not run.
7. If the quality gate fails, the required check reports failure and branch protection blocks the merge.

Do not put payloads aimed at exfiltrating secrets into a PR to test defenses. You can verify permission configuration via workflow permissions, run metadata, and repository settings; there is no need to run malicious code to prove a job lacks permissions.

If no separate fork is available, create an internal PR branch and verify the same policy. Results must still show that an unmerged PR has no publish/deploy permissions.

## 11. Testing a Protected Source

After a valid PR is reviewed and merged into `main`:

1. Verify branch protection was enforced.
2. The workflow runs on the `push` event on `main`.
3. `quality-gate` re-runs on the merged commit.
4. Only after the gate passes does `publish` execute.
5. Inspect the `publish` job to confirm it has only the required permissions.
6. If the deploy gate is configured, verify the environment requires approval.
7. Verify the artifact is built from the exact commit with a traceable version/digest.

Do not assume merging implies the artifact was published or deployed. Each job must have its own status and evidence.

## 12. Testing a Failing Quality Gate

On a test branch, introduce a controlled failure:

- Cause a unit test to fail.
- Or introduce a reversible lint error.
- Or drop coverage below the defined threshold in a test change.

Open a PR and observe:

- `quality-gate` returns a non-zero exit code.
- The required check transitions to failed.
- `publish` does not run because `needs: quality-gate` failed.
- `deploy-production` does not run.
- Logs clearly indicate which check failed.

Afterward, fix the issue, push again, and verify the gate passes. Do not disable the required check to make a PR mergeable.

## 13. Expected Permission Matrix

| Job | PR from Fork | Internal PR | Push to Protected main |
| --- | --- | --- | --- |
| Quality gate | Runs, read-only | Runs, read-only | Runs, read-only |
| Build temporary test artifact | May run | May run | May run |
| Publish package | No | No | Only after quality gate, scoped package permissions |
| Deploy staging | No by default | No by default | Per separate policy |
| Deploy production | No | No | Protected environment + approval |
| OIDC cloud identity | No | No | Only deploy jobs that require it |
| Production secrets | No | No | Granted only to jobs/environments that truly need them |

This is the lab's target policy. If your organization uses release tags, manual dispatches, or a separate staging environment, add corresponding conditions; never generalize elevated permissions from one case to all events.

## 14. Common Mistakes

| Mistake | Risk | Remediation |
| --- | --- | --- |
| Granting write permissions at workflow level | Every job may inherit excessive permissions | Set default to read-only and grant per job |
| PR job receives secrets | PR code may exfiltrate credentials | Do not grant secrets to untrusted PRs |
| Using `pull_request_target` then running PR head | Executes untrusted code in privileged context | Use `pull_request`; if using target, run only trusted base code |
| Publish job does not depend on quality gate | Artifact may be published even when tests fail | Use `needs` and source-trust conditions |
| Checking only branch name | Forks can also have branches with the same name | Check event, repository identity, and ref |
| Treating internal PRs as trusted | Unreviewed code could gain elevated privileges | Elevate trust only after merge into protected ref |
| Sharing self-hosted runners with forks | PRs could access leftover resources or internal network | Use hosted/ephemeral runners and isolate workloads |
| Sharing caches between untrusted and release jobs | Risk of cache poisoning or data leakage | Separate cache scopes along trust boundaries |
| Missing branch protection | Failed checks still allow merging | Mark quality checks as required status checks |
| Overly broad or long-lived tokens | Increases blast radius if leaked | Use short-lived, narrowly scoped tokens and OIDC |
| Ignoring errors with `\|\| true` | Gate stays green despite check failures | Return proper exit codes and audit exceptions |

## 15. Lab Acceptance Checklist

**Quality gate**

- [ ] Orchestration script covers lint, tests, coverage, dependency audit, and secret scan.
- [ ] Each required check returns an accurate exit code.
- [ ] Gate fails when any required check fails.
- [ ] Required status check is configured for `main`.

**Source trust and permissions**

- [ ] PRs from forks run with minimal read permissions.
- [ ] Unmerged internal PRs also lack publish/deploy permissions.
- [ ] Publish runs only on the official repository and protected `main` under defined conditions.
- [ ] Publish job has properly scoped package write permissions.
- [ ] Deploy job uses a protected environment and approval.
- [ ] OIDC is granted only to jobs requiring workload identity.

**Runner and secret protection**

- [ ] No production secrets are passed into PR workflows.
- [ ] `pull_request_target` never checks out and executes PR head code.
- [ ] Untrusted PRs run on isolated runners.
- [ ] Caches provide no write path from untrusted jobs to trusted release jobs.
- [ ] Third-party actions are pinned by verified full SHAs.

**Evidence**

- [ ] Tested an untrusted PR and verified publish/deploy were skipped.
- [ ] Tested a failing quality gate and verified downstream jobs were blocked.
- [ ] Tested a push to protected `main` after review.
- [ ] Artifact has traceable commit, pipeline run, and digest.
- [ ] Logs/reports indicate which gates passed or failed.

## 16. Lab Result Report

Upon completion, record:

| Item | Information to Record |
| --- | --- |
| Repository and branch rule | Repository name, protected branch, and required check |
| Quality gate | List of checks, coverage threshold, and audit policy |
| Untrusted PR | Jobs executed, token permissions, whether publish/deploy were skipped |
| Trusted main push | Commit, pipeline run, artifact version/digest |
| Negative test | Which gate was intentionally failed and how downstream reacted |
| Production gate | Environment approval and workload identity if configured |
| Exceptions | Rationale, owner, scope, and expiration date |

The expected outcome is that an unmerged PR can be tested but cannot release; a commit merged into a protected branch is published only after passing the quality gate; and production deployment requires separate conditions and approval.

## Conclusion

Quality gates and trust gates solve two distinct questions: whether a change meets technical standards, and which actions the current source/event is permitted to perform. A secure pipeline requires both. Validate PR code with minimal permissions, isolate publish/deploy into separate jobs, require the quality gate to succeed, verify repository/ref/event, and protect production with approvals and workload identity.

You complete this lab when you have demonstrated three scenarios: an untrusted PR only runs checks; a failing quality gate blocks publish/deploy; and only a reviewed push to a protected branch proceeds with its scoped permissions. This evidence helps teams govern both code quality and pipeline trust boundaries.
