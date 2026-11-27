# Learning Roadmap from Source Code Change to Verification in the Target Environment

A change in Git becomes a trustworthy release only when we can answer: which change triggered the workflow, how the source code was built and tested, which artifact was created, which environments that artifact passed through, who or what condition authorized deployment, and how the system behaves after deployment.

This lesson builds an end-to-end CI/CD roadmap from a Git event to verification in the target environment. The focus is treating a pipeline as a process that can be read, controlled, and traced through code. The roadmap covers automating builds and tests, managing artifacts, separating environment configuration, quality gates, protecting secrets, post-deployment verification, and rollback plans. This is the foundation for designing repeatable release flows backed by evidence at every step.

## 1. Seeing the Whole Picture of a CI/CD Flow

CI (Continuous Integration) brings source code changes into a frequent integration workflow. Each change is automatically checked to catch bugs early and reduce merge risk. CD is commonly used in two senses:

- **Continuous Delivery:** every change passing verification steps is ready for release; pushing to production may still require a decision or approval.
- **Continuous Deployment:** changes passing all automated gates are deployed to production without manual approval for each release.

A basic flow can be described as follows:

~~~mermaid
flowchart TD
    A["Source code change"] --> B["Git event"]
    B --> C["Pipeline triggered"]
    C --> D["Build and testing"]
    D --> E{"Quality gate"}
    E -- "Failed" --> F["Report failure, retain evidence"]
    E -- "Passed" --> G["Package artifact"]
    G --> H["Store immutable artifact"]
    H --> I["Deploy to test environment"]
    I --> J["Smoke tests and verification"]
    J --> K{"Eligible for release?"}
    K -- "No" --> L["Stop, investigate, or fix"]
    K -- "Yes" --> M["Approve / auto-release"]
    M --> N["Deploy to target environment"]
    N --> O["Monitor health and verify"]
    O --> P{"System stable?"}
    P -- "No" --> Q["Roll back or remediate"]
    P -- "Yes" --> R["Record release"]
~~~

A pipeline is more than a sequential list of commands. It is an operational contract: defining start conditions, inputs, processing steps, pass criteria, permissions used, outputs, and failure handling. A strong pipeline ensures the same change is checked under the same rules and leaves enough information to explain the outcome.

## 2. Starting from a Git Event

Git provides natural events to trigger automation. Picking the right event ensures workflows run at the right time and risk level.

| Event | Common Purpose | Appropriate Behavior |
|---|---|---|
| Push to feature branch | Verify changes early | Build, lint, and fast tests |
| Open or update pull request | Evaluate before merging | Run mandatory checks, report results to reviewers |
| Merge to main branch | Confirm integration status | Run full tests, package artifact |
| Create tag or release | Mark a release version | Create or confirm version-linked artifact |
| Manual trigger | Handle controlled releases or operational tasks | Verify permissions, parameters, and target environment |
| Periodic schedule | Vulnerability scans, dependency checks, or maintenance tasks | Run independently of code changes when needed |

Not every event should hold production deployment privileges. For instance, a pull request from an untrusted branch can run tests but should never receive production credentials. Production deployments should typically be permitted only from protected branches or tags after mandatory checks pass.

When designing triggers, clarify:

1. Which events are allowed to initiate the pipeline?
2. Which branches, tags, or change sources are accepted?
3. Which pipelines only verify, and which can deploy?
4. Can a run be triggered twice or run concurrently?
5. When a new commit arrives, should older runs be canceled?

Avoid overly broad trigger configs that deploy minor edits to sensitive environments. Conversely, overly narrow triggers can leave critical changes unchecked. Trigger rules must reflect the team's actual branching strategy and release workflow.

## 3. Bringing Pipelines Under Code Management

Pipeline as Code describes CI/CD workflows in configuration files stored alongside the repository or in a version-controlled repository. Consequently, pipeline changes can be reviewed, tested, traced, and reverted like application code changes.

A maintainable pipeline configuration typically exhibits these traits:

- **Versioned:** change history reveals who modified which step and why.
- **Reviewable:** edits to permissions, triggers, environments, or quality gates are reviewed before taking effect.
- **Well-structured:** separates build, test, package, deploy, and verify steps; reuses shared logic where appropriate.
- **Explicit conditions:** each step declares inputs, outputs, and execution conditions.
- **Least privilege:** jobs receive only permissions needed for their specific task.
- **Repeatable:** identical inputs and tool versions must yield equivalent results.
- **Timeouts and error handling:** prevent jobs from hanging indefinitely or continuing to deploy after a mandatory step fails.

The example below is a conceptual model illustrating the order and conditions of stages. It is not executable syntax for a specific CI/CD platform:

~~~yaml
pipeline:
  trigger:
    - pull_request
    - push_to_main

  jobs:
    validate:
      steps:
        - checkout_source
        - install_locked_dependencies
        - lint
        - unit_tests

    package:
      needs: [validate]
      steps:
        - build
        - integration_tests
        - create_artifact
        - calculate_artifact_digest
        - publish_artifact

    deploy_test:
      needs: [package]
      environment: test
      steps:
        - deploy_published_artifact
        - smoke_tests

    deploy_production:
      needs: [deploy_test]
      environment: production
      approval: required
      steps:
        - deploy_same_artifact
        - verify_release
~~~

Actual configurations for GitHub Actions, GitLab CI, Jenkins, or other platforms have their own syntax and permission mechanisms. When implementing, use the platform's exact syntax, consult documentation for the version you run, and do not copy a conceptual model verbatim into an executable config file.

Treat pipelines like production code: assign owners, enforce review rules, test changes safely, and have a rollback plan if a new configuration disrupts releases.

## 4. Automating Builds and Testing

Builds transform source code and dependencies into runnable or deployable outputs. Testing supplies evidence that outputs satisfy expected behavior. Both activities are typically automated right after the pipeline receives source code.

A practical verification order is:

1. **Static checks and formatting:** catch convention violations, syntax errors, or obvious issues without running the application.
2. **Unit tests:** verify small components in isolation.
3. **Build:** compile or package using locked tool versions and dependencies.
4. **Integration tests:** test interactions across components, services, or databases.
5. **System or end-to-end tests:** verify critical business flows spanning multiple components.
6. **Security and dependency checks:** identify known vulnerabilities, risky configurations, or disallowed components.
7. **Packaging:** produce release artifacts only after mandatory conditions pass.

Not every project needs every test type on every event. Pull request pipelines can prioritize rapid feedback; post-merge pipelines can add integration tests and deeper checks. However, checks that determine releasability must complete before permitting deployment.

Principles that keep build and test results trustworthy:

- Lock dependency and build tool versions; avoid relying on unpinned latest versions.
- Use clean or deterministically recreated execution environments.
- Never let tests depend on shared data that another job could mutate.
- Separate product bugs from test infrastructure errors; capture logs and evidence sufficient for investigation.
- Track flaky tests (tests that pass and fail inconsistently). Never mask recurring failures with infinite automatic retries.
- Archive test reports, build logs, and exit codes so developers know exactly which step failed.

Speed matters too. Cheap, fast checks should run early for quick feedback. Longer checks can run later, but must never be skipped if they are mandatory release conditions.

## 5. Managing Artifacts as Outputs with Identity

An artifact is a built and packaged output ready for testing or deployment, such as an application package, container image, library, or deployment bundle. Artifacts need stable identities so teams know precisely what is running in each environment.

Core principles:

- **Build once, deploy to many environments:** build an artifact from a specific commit, then promote that exact artifact through test, staging, and production. Do not rebuild separately for production if the goal is verifying the same output.
- **Immutability:** once published, never overwrite artifact contents under the same version or tag. If contents change, create a new identity.
- **Cryptographic hashes:** store digests or checksums to verify artifacts on download and deployment.
- **Metadata:** record commit SHA, pipeline run, application version, build tool version, and creation timestamp.
- **Proper storage:** use an artifact repository or container registry with clear access controls, retention policies, and cleanup rules.
- **Traceability:** from any deployment, trace back to the artifact, pipeline run, and source commit.

Human-readable tags like 2.4.1 are convenient, yet tags can be moved if the registry allows it. Digests represent exact contents and are better suited for ensuring environments run the exact artifact that was tested. In strict workflows, add an SBOM (Software Bill of Materials), artifact signatures, and provenance (evidence of origin and build process).

## 6. Separating Artifacts from Environment Configuration

Environments are where artifacts run and get verified. A common progression includes development, test, staging, and production. Names can vary across organizations, but every environment needs a clear purpose and control level.

| Environment | Goal | Common Controls |
|---|---|---|
| Development | Rapid feedback for development teams | Test data, frequent deployments |
| Test / QA | Functional and integration verification | Test datasets, production-like configuration |
| Staging | Rehearse releases under production-like conditions | Regression tests, smoke tests, configuration verification |
| Production | Serve real users | Strict access controls, full observability, recovery plans |

The same artifact can run in multiple environments, while environment configurations differ: service addresses, resource limits, domains, connection parameters, and credentials. Configuration should be supplied at deployment or startup rather than hardcoding secrets and production-specific parameters into the artifact.

Pay special attention to database changes. A release may deploy application code alongside schema migrations. If a migration breaks backward compatibility with the old version, rolling back application code may not restore the system. One way to reduce risk is multi-step schema evolution: expand compatibly first, deploy new code, migrate data as needed, and remove old structures only after safety is confirmed.

Promotions across environments should clearly record the artifact digest, authorizing person or rule, timestamp, and verification results. This prevents cases where staging tested one build while production ended up running another.

## 7. Designing Quality Gates

A quality gate is a set of conditions that must be met before a pipeline can proceed. Quality gates turn team expectations into rules that can be checked consistently.

A gate may include:

- All mandatory tests pass.
- No critical issues remain above agreed thresholds.
- Test coverage meets project policy, if the project uses coverage as a criterion.
- Dependencies or container images contain no policy-prohibited vulnerabilities.
- Artifacts were built and stored successfully, with digests recorded.
- Post-deployment smoke tests pass.
- Authorized approval is recorded for controlled environments.

Avoid picking thresholds merely because a tool can measure them. Every condition must tie to a risk the team intends to reduce. For example, high coverage does not automatically prove test quality; a test can execute many lines without verifying critical outcomes. Similarly, a clean security scan does not guarantee an application is completely secure.

Gates should produce clear outcomes: pass, fail, or controlled decision required. If exceptions are allowed, document the reason, scope, approver, and review deadline. Never let bypassing gates become default behavior, as the gate then loses all protective value.

## 8. Protecting Secrets and Access Permissions

Pipelines routinely need access to registries, cloud providers, deployment servers, databases, or external services. Consequently, pipelines are also a potential point of credential exposure.

Practices to apply:

- Store secrets in a secret manager or secret vault supported by the CI/CD platform; never commit tokens, passwords, private keys, or `.env` files containing secrets to Git.
- Grant least privilege per job and per environment. A job running only unit tests does not need production deploy permissions.
- Prefer short-lived credentials or identity federation such as OIDC where supported, instead of hard-to-rotate long-lived keys.
- Isolate secrets by environment; restrict which jobs can read production secrets.
- Never print secrets to logs, command lines, or error messages. Log masking is only a secondary safeguard, not a substitute for keeping secrets out of output.
- Check permissions on pull requests from forks or untrusted sources before allowing jobs to access secrets.
- Maintain revocation and rotation procedures for credentials when exposure is suspected.

An easy rule to remember: source code and artifacts can be shared per repository policy, whereas secrets must be issued just in time, to the right job, for the right environment, with the right permissions.

## 9. Controlled Deployment

Deployment strategy governs how a new version replaces the running version. The choice depends on architecture, downtime tolerance, infrastructure cost, and risk level.

| Strategy | How It Works | When Appropriate |
|---|---|---|
| Rolling update | Replaces groups of instances or pods in batches | Systems with multiple replicas supporting concurrent versions |
| Blue-green | Maintains two environments; verifies the new one, then switches traffic | Need rapid cutover and ability to keep the old environment for fallback |
| Canary | Shifts a small fraction of traffic to the new version, then ramps up | Want to observe impact on a slice of users before expanding |

Safe deployments define start criteria, traffic scope, halt conditions, and recovery procedures in advance. With canary, for example, start at a small percentage, monitor errors and latency, and increase traffic only while metrics stay within thresholds. With blue-green, verify the new environment before switching traffic.

Also verify cross-version compatibility when multiple instances coexist. APIs, database schemas, message formats, and cache keys may be accessed by both old and new versions during the transition window.

## 10. Post-Deployment Verification in the Target Environment

A successful deploy command only proves the deployment platform executed the operation. It does not prove users can use the system normally. Therefore, independent post-deployment verification is mandatory.

Verification can be organized in layers:

1. **Deployment status:** the platform reports the expected version, instances, or pods are ready.
2. **Health checks:** processes and essential dependencies satisfy readiness conditions.
3. **Smoke tests:** core flows such as login, data reads, or test transactions succeed.
4. **Integration or synthetic tests:** verify interactions with external services using controlled requests.
5. **Operational observability:** monitor error rates, latency, throughput, resources, and logs over an appropriate window.
6. **Version identity confirmation:** match the running commit or artifact digest against the intended release.

Health checks should distinguish between process liveness and readiness to serve traffic. An application may stay alive while failing to connect to its database or finish loading configuration. Checking only process liveness can cause the pipeline to declare success prematurely.

Verification criteria must align with system behavior and risk. For a transactional service, error rates and transaction completion matter more than simply receiving an HTTP success code. For background processing systems, monitor queues, processing latency, and task failure rates.

Verification results must be archived alongside the release. If checks fail, the pipeline should halt rollout expansion, notify accountable owners, and trigger the predefined recovery plan.

## 11. Preparing Rollback and Remediation

Rollback returns the system to a prior version known to be stable. Rollback capability must be designed before release, because during an incident operators rarely have time to invent a new procedure.

A rollback plan must answer:

- Which artifact is the most recent stable version? Can it be retrieved by digest?
- Who or what condition is authorized to trigger rollback?
- How fast can traffic be shifted back or the old artifact redeployed?
- Are configurations and data schemas still compatible with the old version?
- How will we verify that the system has recovered?
- Does data written by the new version require special handling?

Not every error warrants a rollback. If a bug can be fixed quickly with a safe patch and rolling back would lose data or cause additional disruption, a forward fix may be better. For irreversible data changes, a dedicated data recovery plan is required. Feature flags can also quickly disable a new capability without redeploying the entire application.

After recovery, record the detection timestamp, blast radius, involved artifact, remediation decision, and verification results. This information supports root-cause analysis and improves quality gates for future releases.

## 12. Maintaining Traceability from Commit to Runtime Environment

A reliable CI/CD flow must connect these milestones:

**Commit SHA → Git event → pipeline run → build/test results → artifact digest → deployment → environment → verification results.**

Each link should have an identifier and point to corresponding evidence. For example, when a user reports a production bug, the team can identify the running version, look up the artifact digest, open the pipeline that built it, inspect the source commit, and read test reports.

A minimal release record should contain:

| Information | Meaning |
|---|---|
| Version and commit SHA | Identifies the source code change |
| Pipeline run ID | Locates logs and automation results |
| Artifact name and digest | Pinpoints the exact deployed output |
| Environment and timestamp | Shows where and when the artifact was deployed |
| Approver or approval policy | Traces the release decision |
| Test and verification results | Provides evidence of quality and post-deploy health |
| Rollout or rollback status | Shows how the release concluded |

Traceability is not just for audits. It accelerates incident investigation, enables comparing two releases, and identifies whether an issue stemmed from code changes, artifacts, configuration, or the environment.

## 13. Walking Through a Sample Release Scenario

Suppose a team develops a web service and is ready to merge a change into the main branch.

1. A developer opens a pull request. This triggers a pipeline checking formatting, linting, unit tests, and mandatory policies. Verification jobs receive no production secrets.
2. Once the pull request meets requirements and merges, the main branch pipeline re-runs required checks, builds the application, and executes integration tests.
3. The pipeline creates an artifact, computes its digest, and stores the artifact with metadata including commit SHA and pipeline run ID.
4. That exact artifact is deployed to test or staging. The pipeline runs health checks, smoke tests, and required regression checks.
5. When quality gates pass, the Continuous Delivery workflow may await production approval. Approvers inspect the commit, artifact, test results, and target environment.
6. Once authorized, the pipeline deploys the same artifact to production using the chosen rolling, blue-green, or canary strategy.
7. The pipeline verifies the running version, checks critical business flows, and monitors operational metrics. If metrics exceed thresholds, rollout stops and rollback or remediation triggers.
8. Final outcomes are recorded in the release record, linking back to the commit, pipeline, and artifact.

The key takeaway from this scenario is that every environment receives the exact same uniquely identified artifact. Every transition has clear conditions and leaves evidence. During an incident, the team never has to guess which build is running or manually hunt down who deployed it.

## 14. Common Errors and How to Investigate Them

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| Pipeline does not run | Trigger or branch filter mismatch; event not delivered | Check Git events, trigger conditions, and run history |
| Flaky builds | Unpinned dependencies, shifting build environments, or inconsistent caches | Compare tool versions, dependencies, and logs across runs |
| Tests fail in CI but pass locally | Differences in config, data, timezone, dependent services, or execution order | Reproduce CI environment and isolate external dependencies |
| Deploy cannot find artifact | Wrong name, version, access permissions, or registry | Cross-check metadata, digest, and artifact read permissions |
| Staging passes but production fails | Differences in config, data, permissions, or real traffic | Compare injected config, dependencies, and telemetry across environments |
| Job leaks sensitive info | Printing environment variables, enabling debug mode, or granting secrets to untrusted jobs | Check logs and access scope; revoke/rotate secrets if needed |
| Deploy reports success yet service is unusable | Checked deploy operation only; missing health checks or smoke tests | Check readiness, application logs, dependencies, and business flows |
| Rollback does not fully restore service | Incompatible schema or data changes | Check migrations, multi-version coexistence, and data plans |

When investigating, follow the evidence chain from the first failure point. Avoid simply re-running the pipeline repeatedly without identifying the root cause; re-running can mask timing-dependent bugs or introduce further environment changes.

## 15. Practice Roadmap and Completion Criteria

You can learn through the following progressive exercises:

1. **Map the flow from Git:** select push, pull request, merge, and tag events; specify which tasks each event is allowed to run.
2. **Create a verification pipeline:** automatically check out source code, install locked dependencies, lint, build, and run unit tests. Observe how the pipeline reports errors when a step fails.
3. **Package an artifact:** build an artifact from a specific commit, compute its digest, and store metadata. Verify that the exact artifact can be retrieved again.
4. **Promote across environments:** deploy the built artifact to test or staging; supply environment-specific configuration and run smoke tests.
5. **Add quality gates and permissions:** require passing tests, restrict job permissions, and add approvals for controlled environments.
6. **Controlled production verification:** choose a rollout strategy, monitor post-deployment metrics, and rehearse halting a rollout or rolling back in a safe environment.
7. **Verify traceability:** starting from a deployment, locate the commit, pipeline run, artifact digest, approver or approval policy, and verification results.

The practical exercises can be considered complete when the learner demonstrates the following:

- Explaining which Git event triggers each pipeline and why.
- Reading pipelines as code, identifying execution conditions and permissions per job.
- Automating builds and tests with repeatable inputs.
- Creating, storing, and identifying artifacts by version and digest.
- Promoting the same artifact across environments with separately managed configuration.
- Establishing quality gates and protecting secrets under least-privilege principles.
- Verifying version identity and system health after deployment.
- Tracing a release end-to-end and describing how to roll back or remediate.

## Conclusion

CI/CD is a continuous chain of controls linking source code changes to systems serving users. Git events determine when workflows start; pipeline-as-code describes how workflows run; builds and tests produce quality evidence; immutable artifacts ensure identifiable outputs; environment management and quality gates control releases; secret management protects access; and post-deployment verification with rollback enables recovery when real-world results fall short of expectations.

When every step has clear conditions, permissions, outputs, and evidence, teams can release more frequently while keeping risks under control and explaining precisely what is running in the target environment.
