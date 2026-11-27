# Designing a Minimal Pipeline Before Scaling Up

## Learning Objectives

After completing this lesson, learners will be able to:

- Define the minimal scope of a pipeline based on product type, risk profile, and how the team ships software.
- Design a flow from Git events through testing, packaging, deployment, and post-deployment verification.
- Distinguish mandatory correctness safeguards from optimizations or advanced capabilities that can be added later.
- Organize pipelines as code using immutable artifacts, managed secrets, and controlled access permissions.
- Define success criteria, failure handling, and required evidence before expanding the pipeline.
- Recognize signs that a pipeline is becoming overly complex or still lacks essential capabilities.

## 1. Why Start with a Minimal Pipeline?

When building CI/CD, teams easily get swept up in platform feature checklists: build matrices, multiple test suites, security scanners, artifact signing, multi-environment promotion, canary, blue-green, multi-stage approvals, dashboards, and dozens of integrations. Each capability can be useful, yet cramming everything in from day one multiplies configuration complexity, failure modes, access permissions, and operational overhead.

An initial pipeline should answer one core question: **can a source code change be verified, packaged, and delivered to the target environment through a repeatable process with evidence and clear failure handling?**

A minimal pipeline is not the one with the fewest lines of YAML or the fewest jobs. It is the smallest flow that still produces reliable outcomes for the software being delivered. An internal library, a customer-facing API, and a payment service require different levels of control. Never force an identical set of steps onto every product.

Think of pipeline design as building one working end-to-end vertical slice:

1. Receive a change from Git.
2. Validate the change with high-value checks.
3. Produce an identifiable, traceable artifact.
4. Deliver the artifact to the required environment.
5. Verify the outcome and retain evidence.
6. Halt, fix, or recover whenever conditions fail.

Only once this slice operates reliably does the team have solid grounding to decide which tests, environments, policies, or release strategies to add next.

## 2. Defining Scope Before Writing the Pipeline

Before picking a platform or writing configuration, align on several facts about the product and release workflow.

| Question | What to Determine | Examples |
|---|---|---|
| What is the product? | Type of output to produce | Library, web app, API, container image |
| Which events trigger it? | When verification should run | Pull request, push to main branch, tag creation |
| What is the source of truth? | Commits and branches eligible for release | Protected `main` branch |
| Which checks are mandatory? | Minimum evidence of correctness and safety | Linting, unit tests, dependency checks |
| What is the artifact? | Package to store and deploy | JAR, package, image by digest |
| What is the target environment? | Where verification and release happen | Test environment, staging, production |
| What are the release conditions? | Who or which policy authorizes release | Staging checks pass, risk-based approval |
| What happens on failure? | How to notify, stop, and recover | Block merge, keep prior artifact, roll back |

This scope must be clear enough for anyone to answer: which changes run which pipeline, which artifact is produced, what gates permit deployment, and who owns failures.

Do not start by asking "how many features does our platform support?". Start with operational requirements and the evidence you need to collect. Only then pick the platform mechanisms that fulfill them.

## 3. The Smallest Viable Structure

For a typical service, the initial pipeline can be organized into four logical parts:

- **Validate:** check source code and required conditions before accepting changes.
- **Package:** build and produce an immutable artifact linked to the commit and pipeline run.
- **Deploy:** deliver that exact artifact to the appropriate environment.
- **Verify:** check the live service post-deployment, record outcomes, and decide whether to proceed or stop.

These logical parts do not have to map to four separate tools or workflows. A single stage may contain multiple jobs, or a single platform may handle the entire flow. What matters is keeping input, output, and transition boundaries explicit.

~~~mermaid
flowchart TD
    A["Pull request / commit"] --> B["Validate"]
    B --> C{"Checks passed?"}
    C -- "No" --> X["Report error and block change"]
    C -- "Yes" --> D["Build and package"]
    D --> E["Immutable artifact + metadata"]
    E --> F["Deploy to test environment"]
    F --> G["Smoke / integration checks"]
    G --> H{"Verification passed?"}
    H -- "No" --> Y["Halt release and investigate"]
    H -- "Yes" --> I["Release policy"]
    I --> J["Deploy production"]
    J --> K["Post-deploy verification"]
    K --> L{"Service stable?"}
    L -- "No" --> M["Roll back or remediate"]
    L -- "Yes" --> N["Record release"]
~~~

Early on, do not build a complex orchestration engine just to mirror this diagram. Use the platform's built-in primitives and keep the flow readable, re-runnable, and easy to investigate.

## 4. Designing Each Part of the Pipeline

### 4.1. Validate: Early Feedback on Changes

Validation usually runs on pull requests or when commits are pushed to the main branch. The objective is catching problems before changes become part of a release.

An initial check suite typically includes:

- Formatting or lint checks to enforce code conventions.
- Basic static analysis to catch common defects.
- Unit tests or fast tests suited to the project.
- Secret scanning to catch exposed credentials in the change.
- Dependency vulnerability checks aligned with project policy.

Prioritize checks that are fast, stable, and surface actionable remediation details. Heavy integration tests, performance benchmarks, or multi-runtime matrix builds can wait until a concrete need arises.

Do not turn every warning into an immediate merge blocker. Distinguish clearly between:

- **Required check:** must pass for the change to be accepted.
- **Advisory check:** surfaces information without blocking changes during trial adoption.
- **Controlled waiver:** an exception carrying an approver, justification, scope, and expiration.

Critical integrity or secret checks need strict blocking rules. Uncalibrated code quality warnings can start in advisory mode while you measure false-positive rates and tune rules. Never leave checks in perpetual "warning" status with no accountable owner.

### 4.2. Package: Build and Produce an Identifiable Artifact

Once mandatory checks pass, the pipeline builds the software package. Artifacts may be JARs, binaries, packages, frontend bundles, or container images.

From the very first pipeline, record at minimum:

- Source commit hash or revision.
- Pipeline run ID and build timestamp.
- Application version or release tag if applicable.
- Artifact type and immutable identifier, such as a digest.
- Outcomes of mandatory checks tied to that artifact.

Store artifacts in a repository with explicit access control and retention policies. Never rely solely on files sitting inside a runner workspace, as workspaces can be wiped or overwritten between runs.

An essential rule is **build once, use the exact same artifact across downstream environments**. If staging and production rebuild separately, the team loses certainty that the tested package is the released package. Manage environment-specific configuration separately so it never alters the built artifact's contents.

### 4.3. Deploy: Deploy According to Environment and Policy

A minimal pipeline should include at least one environment where the team can deploy automatically and test safely. For most projects, this is a test or staging environment.

Deployment must explicitly specify:

- Which artifact is deployed, ideally by digest or immutable identifier.
- Target environment and configuration.
- Deployment identity and granted permissions.
- How configuration and secrets are supplied.
- How the running version is recorded.
- Stopping criteria if the deployment step fails.

Never put passwords, tokens, or private keys in pipeline files, logged CLI flags, or artifacts. Use a secret store or the platform's workload identity mechanism, enforce least privilege per environment, and prefer short-lived credentials whenever possible. Staging or test deploy jobs must not hold broader permissions than necessary, and production deploy jobs must also stay tightly scoped.

Production may require approvals or release policies. Approvals should bind to a specific version or artifact and log who approved, when, and on what evidence. Avoid mandating manual approvals everywhere if risk is low and policy allows automation.

### 4.4. Verify: Post-Deployment Verification

A deploy command returning success only proves the deployment tool finished applying changes. It does not prove the application works properly.

A minimal verification suite can include:

- Smoke tests exercising critical endpoints or core functions.
- Readiness/health checks confirming the application is up.
- Confirming the running version or digest matches the intended artifact.
- Checking baseline operational signals such as error rate or latency.

For critical services, observe telemetry over a post-deployment window or watch canary metrics before shifting full traffic. Stop and rollback thresholds should be defined in advance rather than improvised mid-incident.

Also consider data compatibility. If a new release alters database schemas, rolling back application code alone may not restore the system. Prefer backward-compatible incremental migrations—such as expanding the schema first, shifting the application, and removing old structures only once no running version depends on them.

## 5. Separating Change-Validation Pipelines from Release Pipelines

Not every Git event needs to run the entire end-to-end process. Separate the two concerns:

**Change-validation pipelines** run on pull requests or commits. They deliver fast feedback and determine whether a change qualifies to enter the main branch.

**Release pipelines** run on accepted commits, tags, or release requests. They produce or retrieve the identified artifact, deploy according to policy, and verify the target environment.

This separation prevents deploying unapproved commits to production. It also helps teams distinguish defects caught in change testing from deployment or environment issues.

A simple flow might look like this:

~~~mermaid
flowchart LR
    A["Pull request"] --> B["Lint + tests + security checks"]
    B --> C{"Required checks pass?"}
    C -- "No" --> D["Fix change"]
    D --> A
    C -- "Yes" --> E["Merge to main"]
    E --> F["Build + publish artifact"]
    F --> G["Deploy and verify"]
    G --> H["Release under policy"]
~~~

If the platform supports reusing build outputs, ensure the artifact comes from the exact accepted commit. If rebuilding post-merge is required, the release pipeline must record both the commit and digest to preserve traceability to prior check results.

## 6. Pipeline as Code: Keeping Configuration Reviewable

Pipeline as code means storing CI/CD configuration in version control alongside source code or in a governed configuration repository. This gives pipeline changes full history, peer review, rollback capability, and testing just like application code.

An initial pipeline should prioritize:

- Stage and job names that clearly reflect their purpose.
- Explicitly declared trigger conditions.
- Pinned versions for actions, plugins, or base images at an appropriate level.
- Timeouts on jobs that could hang.
- Logs showing which steps ran, their outcomes, and links to artifacts.
- Avoiding copy-pasted configuration when a simple template suffices.
- Keeping secrets and sensitive data completely out of the repository.

The example below is pseudocode YAML illustrating the structure, not ready-to-run configuration for GitHub Actions, GitLab CI, or Jenkins:

~~~yaml
pipeline:
  triggers:
    - pull_request
    - push_to_main

  validate:
    required: true
    steps:
      - checkout_source
      - lint
      - unit_tests
      - dependency_check
      - secret_scan

  package:
    requires: validate_passed
    steps:
      - build_once
      - create_immutable_artifact
      - attach_commit_and_run_metadata
      - publish_artifact

  test_environment:
    requires: artifact_published
    steps:
      - deploy_artifact_by_digest
      - run_smoke_tests
      - record_deployed_version

  production:
    requires:
      - test_environment_passed
      - release_policy_satisfied
    steps:
      - deploy_same_artifact
      - verify_health
      - stop_or_rollback_on_failure
      - record_release
~~~

Do not copy this example verbatim into a project without mapping steps to real tools and conditions. Treat it as a logical contract: each section's inputs, conditions, outputs, and failure handling must be explicitly defined.

## 7. Failure Policies: Defining What Happens Next

A reliable pipeline has deterministic behavior when a step fails. A red job with no clear next step breeds manual workarounds and trains teams to ignore alerts.

| Scenario | Minimum Expected Behavior |
|---|---|
| Lint or unit test fails | Block change per policy; display logs and failing test details |
| Scan detects a secret | Block the flow appropriately; guide remediation and secret revocation |
| Build fails | Do not publish incomplete artifacts; retain logs for investigation |
| Artifact publish fails | Do not advance to deploy; allow safe retry |
| Deploy fails | Halt rollout, preserve identifiable current state, and alert |
| Smoke test fails | Do not mark release successful; halt traffic ramp or roll back per policy |
| Service degrades post-deploy | Trigger pre-defined alert thresholds and recovery procedures |

Distinguish retryable transient failures from bugs that must be fixed. Transient network hiccups while downloading dependencies can use bounded retries. A unit test failing due to a regression must never be blindly re-run until red turns green. Unbounded retries mask real defects and bloat pipeline duration.

Every job needs a sensible timeout. If a step hangs, the pipeline must terminate cleanly and surface enough context to investigate. Publish and deploy steps should be idempotent or detect already-completed state before retrying.

## 8. Protecting Secrets and Access from Day One

Security is not an optional add-on saved until a pipeline grows large. Even a minimal pipeline requires strict trust boundaries.

Fundamental rules:

1. Never store tokens, passwords, private keys, or credentials in the repository.
2. Never expose production secrets to pipelines triggered by untrusted pull requests.
3. Separate artifact read permissions, staging deployment permissions, and production deployment permissions.
4. Use short-lived identities or native platform federation wherever available.
5. Scope permissions by repository, environment, and job.
6. Mask sensitive data in logs and purge credentials from runners after execution.
7. Record which user or workload deployed each production version.

A pipeline with only a few jobs still carries a huge blast radius if every job shares one admin token. The baseline standard is ensuring each step holds only the permissions needed to complete its task.

## 9. Measuring the Pipeline Before Scaling Up

Without a baseline, it is nearly impossible to tell whether a pipeline change helped or hurt. Before optimizing, track a handful of simple metrics:

| Metric | Meaning | Question It Helps Answer |
|---|---|---|
| Time to first feedback | From PR open until first check results arrive | How long do developers wait to learn about errors? |
| Total pipeline duration | From start to completion | Is the overall flow too slow? |
| Runner wait time | Time jobs spend queued for compute | Is the bottleneck runner capacity or slow scripts? |
| Pipeline failure rate | Failed runs over total runs, grouped by cause | Which jobs are chronically unstable? |
| Merge-to-deploy time | Duration for an integrated change to reach target env | Where is the release process stalling? |
| Change failure rate | Share of releases causing incidents or emergency fixes | Does speed come with stability? |
| Recovery time | From incident detection to service restoration | Is the recovery process effective? |

Never optimize every metric simultaneously. Pick one high-impact bottleneck, adjust one part of the pipeline, and compare before vs. after. For example, if the pipeline lags reinstalling dependencies every run, caching helps. If time goes into integration tests fighting over one shared environment, throwing more runners at the queue will not fix the root cause.

## 10. When Should You Expand the Pipeline?

Add stages, jobs, or tools only when concrete needs arise that the current pipeline cannot satisfy. Valid signals include:

| Observed Signal | Capability to Consider Adding |
|---|---|
| Bugs appear only when services integrate | Integration tests or contract tests |
| Multiple runtimes or OS targets are supported | Scoped matrix testing |
| Dependencies or images carry high security exposure | Deeper vulnerability scanning and policy gates |
| Artifacts must prove origin or integrity | SBOMs, cryptographic signing, and provenance |
| Deployments impact large user bases | Canary, blue-green, or progressive delivery |
| Schema changes risk compatibility breaks | Migration checks and expand-contract workflows |
| Product faces compliance mandates | Audit trails, approval policies, and evidence archiving |
| Multiple repositories duplicate identical setups | Pipeline templates or reusable workflows |
| Pipeline contains error-prone manual steps | Automate the exact handoff boundaries |

Every new capability should answer four questions:

- Which risk or bottleneck does this solve?
- What evidence proves the new capability works?
- Who owns and operates it?
- What new cost, access permissions, and failure modes does it introduce?

If you cannot answer those yet, log the need and gather data before adding complexity.

## 11. Staged Maturity Roadmap

Pipelines can evolve through the following stages. Treat this as a reference roadmap rather than a mandate that every project must adopt all stages.

### Level 1: Change Validation

- Trigger on pull requests or commits.
- Run linting, unit tests, and basic dependency/secret checks.
- Block merges when required checks fail.
- Surface clear logs and results.

This level gives teams automated feedback before accepting changes.

### Level 2: Artifact Creation and Storage

- Build from a deterministic commit.
- Attach metadata and immutable identifiers.
- Publish artifacts to an access-controlled repository.
- Retain links connecting commit, pipeline run, and artifact.

This level ensures the team knows exactly which package was built and can reuse it reliably.

### Level 3: Automated Deployment and Verification

- Deploy the exact artifact to a test environment.
- Run required smoke tests or integration tests.
- Record the running version.
- Mark success only after verification passes.

This level establishes a repeatable end-to-end software delivery flow.

### Level 4: Release Control and Recovery

- Apply risk-based approvals or release policies.
- Enforce isolated production permissions.
- Introduce traffic-percentage or cohort rollouts where needed.
- Set halt thresholds and rehearse rollbacks.

This level strengthens control over release blast radius.

### Level 5: Optimization and Standardization

- Introduce data-driven caching and parallelism.
- Create shared templates across repositories.
- Add SBOMs, signing, provenance, and policy enforcement as required.
- Track delivery metrics and run periodic improvements.

Standardize broadly only after a representative pipeline proves stable in practice. Templating a flawed design merely multiplies maintenance cost and errors across every repository.

## 12. Common Mistakes When Designing a First Pipeline

| Mistake | Consequence | Fix |
|---|---|---|
| Adding too many jobs upfront | Hard to understand, maintain, and slow feedback | Start with a short end-to-end slice and expand from evidence |
| Checking only that the build compiles | Zero proof of functional quality | Add risk-appropriate tests and checks |
| Rebuilding in every environment | No guarantee tested package equals released package | Build once, promote the same artifact |
| Sharing a high-privilege token | One compromised job threatens the entire system | Isolate identities and permissions per job/environment |
| Setting no timeouts | Stuck runners tie up capacity indefinitely | Enforce timeouts and alert on expiration |
| Retrying every failure | Hides regressions and flaky tests | Classify failures and cap retries to transient errors |
| Skipping post-deploy verification | Deploy turns green while service is broken | Add health checks and smoke tests |
| Templating too early | Scales an unvalidated setup everywhere | Prove design on one representative repo first |
| Having no pipeline owner | Broken jobs linger and alerts get ignored | Assign clear ownership and incident triage |

## 13. Practical Example: Minimal Pipeline for an API

Suppose a team maintains an API in Git, packages it as a container image, and deploys to staging before production.

They can start with the following scope:

| Trigger / Stage | Steps | Output Condition |
|---|---|---|
| Pull request | Lint, unit tests, secret scan, dependency check | Check results tied to commit |
| Merge to main | Build image once | Image tagged with commit and digest recorded |
| Post-build | Publish image | Artifact retrievable by digest |
| Staging | Deploy image by digest | Running version recorded |
| Post-staging deploy | API smoke tests and health checks | Verification evidence stored |
| Production release | Check release policy, approve if required | Approver/rule authorizing release recorded |
| Post-production deploy | Check health and error rates | Complete release or trigger halt/rollback |

During the first week, focus on exercising the primary paths: passing PR, failing PR, failing build, failing staging deploy, and failing smoke test. Do not spin up dozens of environment variants before they are needed. However, ensure every critical failure path behaves deterministically.

Once the baseline flow stabilizes, measure step durations. If unit tests dominate runtime, optimize tests. If runners queue constantly, evaluate runner capacity. If staging deploys still require manual tweaks, standardize configuration and permissions. Tie every improvement to an observed bottleneck.

## 14. Acceptance Checklist for a Minimal Pipeline

Before declaring your first pipeline production-ready, verify:

- [ ] Allowed Git events and branches are explicitly defined.
- [ ] Required checks have clear pass/fail criteria.
- [ ] Check results bind to the commit and are visible to the author.
- [ ] Builds produce artifacts with immutable identities.
- [ ] Artifacts are stored in an access-controlled, reachable location.
- [ ] The exact same artifact is promoted across environments.
- [ ] Secrets never appear in repositories, logs, or artifacts.
- [ ] Deployment permissions are scoped by environment and task.
- [ ] Failed deployments halt progression and emit clear alerts.
- [ ] Post-deployment checks run and confirm the live running version.
- [ ] Someone owns the pipeline and handles failures when they occur.
- [ ] Baseline metrics are collected for future comparison.

If an item is unmet, decide whether it is an acceptable risk for the current scope or a mandatory prerequisite before release. Never skip secret protection, artifact integrity, or production verification just to keep the pipeline shorter.

## 15. Self-Assessment Exercise

A team maintains a web service repository. Currently, developers merge to the main branch, then one person downloads the build file locally, logs into the staging server, and copies the file manually. Once testing finishes, that person repeats the same manual steps for production. The team wants to adopt CI/CD but only has time to build an initial pipeline.

Answer the following:

1. Which Git events should trigger the change-validation pipeline and the release pipeline?
2. Which three to five initial checks provide the highest value for this repository, and why?
3. What metadata must the artifact carry to trace back to the commit and build run?
4. How do you ensure staging and production deploy the exact same artifact?
5. How should secrets and deployment permissions be provisioned to jobs?
6. After deploying, what must be checked to confirm the application actually works?
7. If deployment succeeds yet smoke tests fail, what should the pipeline do?
8. After a few weeks of operation, what data would justify adding integration tests, canary rollouts, or shared templates?

A strong design demonstrates an end-to-end flow, stopping conditions, traceability, and clear ownership. You do not need a sprawling stack of tools to prove you have CI/CD.

## Conclusion

An initial pipeline should establish a short yet dependable path from a Git change to an artifact, deployment environment, and verification evidence. Core steps include validating changes, building once, storing an identifiable artifact, deploying with controlled permissions, and verifying post-deployment behavior.

Once the pipeline runs steadily, use timing, failure, and risk data to decide which capability to add next. Growing slice by slice lets teams preserve clarity, operability, and continuous improvement throughout the product's lifecycle.
