# Automating the Same Deployment Process Across Environments

## Learning Objectives

After this lesson, learners can:

- Explain why dev, staging, and production should share a single controlled deployment process.
- Distinguish between application artifacts, environment configuration, and target infrastructure.
- Design a build-once, promote-the-same-artifact flow across environments.
- Organize per-environment configuration using schemas and overlays while managing secrets separately.
- Reuse pipelines via templates or reusable workflows while preserving auditability and customization.
- Apply gates, permissions, and approvals appropriate for each environment.
- Control deployment ordering, concurrency, post-deploy verification, and rollback.
- Trace artifacts, config revisions, and deployment results across the release lifecycle.

## 1. Why Use the Same Deployment Process?

Many teams start with a different deployment approach for each environment. Developers run a script on their local machines to deploy to dev; staging is updated through a CI workflow; production is updated by an operator running commands or editing configuration manually.

This approach may work early on, but as the number of environments grows, differences accumulate easily:

- Staging runs a different set of commands than production.
- The order of migrations, restarts, or health checks is not the same.
- A configuration step is only performed manually in production.
- Permissions and secrets are provisioned inconsistently.
- It is impossible to know which exact artifact staging tested.
- During an incident, rolling back each environment requires different manual steps.

If a bug only appears in production, the team struggles to determine whether the root cause lies in source code, configuration, infrastructure, or deployment process differences.

The goal of multi-environment automation is to use **the same deployment process, the same step order, and the same input/output contract**, while environment-specific values and policies are explicitly declared.

Using the same process does not mean every environment must have the same hostname, credentials, replica count, or permissions. Dev, staging, and production can differ in configuration, data, resources, and gates. What must remain consistent is how the pipeline identifies the artifact, validates conditions, applies configuration, deploys, verifies, and records results.

A core principle:

> Build once, verify and promote the same artifact across environments using a reusable process; vary only environment configuration and policies in a managed way.

## 2. Identifying the Deployable Unit

Before designing the workflow, you must agree on what components the pipeline deploys. A release may consist of multiple parts:

| Component | Examples | How to Identify |
|---|---|---|
| Application artifact | JAR, container image, package | Digest or immutable artifact ID |
| Deployment configuration | Helm values, manifest, task definition | Config revision or fingerprint |
| Infrastructure | Cluster, database, network, service account | IaC revision and infrastructure state |
| Database migration | Migration scripts or migration bundle | Migration version |
| Runtime configuration | Feature flags, timeout, endpoint | Config service revision |
| Secret | API key, password, certificate | Secret reference and version metadata |

Do not bundle all components into a single version string if they have different lifecycles. For example, an image can remain unchanged while timeout configuration is adjusted. Conversely, a database schema change may require coordination across multiple application versions.

A deployment request should identify at minimum:

- Which artifact will be deployed.
- Target environment.
- Config revision or how configuration is resolved.
- Related migrations or infrastructure changes, if any.
- Deployment strategy.
- Required gates.
- Executing identity and granted permissions.
- Post-deployment verification evidence.

A clear deployable unit lets the pipeline be re-run, compared, and traced without relying on individual manual actions.

## 3. Build Once and Promote the Same Artifact

A common mistake is rebuilding the application for each environment:

- Build image A for dev.
- Build image B for staging.
- Build image C for production.

Even if all three builds use the same commit, artifact contents can still differ due to dependencies, toolchain, build timestamp, build arguments, or environment data. When staging tested image B but production receives image C, the test results no longer directly prove anything about the released artifact.

The recommended model:

1. Build the artifact from an identified commit.
2. Generate the digest and metadata.
3. Run required checks.
4. Publish the artifact to a trusted registry.
5. Deploy that exact digest to dev or a test environment.
6. After gates pass, promote the same digest to staging.
7. After approval and policy checks, promote the same digest to production.

~~~mermaid
flowchart LR
    A["Reviewed commit"] --> B["Build once"]
    B --> C["Artifact + digest"]
    C --> D["Deploy dev"]
    D --> E{"Dev verify passed?"}
    E -- "Yes" --> F["Deploy staging"]
    E -- "No" --> X["Stop and investigate"]
    F --> G{"Staging verify + gate passed?"}
    G -- "Yes" --> H["Deploy production"]
    G -- "No" --> X
    H --> I["Post-deploy verify"]
~~~

In practice, verification is a transition condition between environments, not a decorative post-deploy step. Every promotion must identify the artifact digest and the evidence attached to that digest.

Do not use mutable tags such as **latest**, branch names, or aliases as the final identifier for production. Tags can help locate an artifact, but the pipeline should resolve them to a digest and use that digest throughout the promotion process.

Nor should you rebuild just to swap an endpoint or credential. Environment-specific values should be passed through deployment configuration or runtime configuration, depending on the architecture. If a value truly must be baked into the artifact at build time, make clear why and accept that changing that value will require a new artifact.

## 4. Same Process, Environment-Specific Configuration

Each environment can have its own configuration:

| Attribute | Dev | Staging | Production |
|---|---|---|---|
| Purpose | Fast feedback for development | Production-like verification | Serving real users |
| Database | Development data | Managed test data | Real data, with backups and controls |
| External endpoints | Mock or sandbox | Sandbox or integration systems | Production endpoints |
| Replicas | Low, cost-optimized | Close to production configuration | Sized for load and SLOs |
| Secrets | Dev credentials | Staging credentials | Dedicated credentials, least privilege |
| Approval | Usually automatic | May require gates | Per release policy |
| Rollout | Fast, can be reset | Tighter control | Canary, rolling, or blue-green based on risk |

Configuration should be organized around a shared contract. For example, all three environments have a database URL, request timeout, replica count, and feature flags, but with different values.

~~~text
deploy-config/
├── base/
│   └── service.yml
├── environments/
│   ├── dev/
│   │   └── values.yml
│   ├── staging/
│   │   └── values.yml
│   └── production/
│       └── values.yml
└── schema/
    └── deployment-config.schema.json
~~~

The base directory holds shared structure and defaults. Overlays declare only intentional differences. The schema defines which fields are required, data types, value ranges, and validation rules.

The pipeline must resolve the final configuration for the target environment, validate it, and record its revision or fingerprint. Do not assume an individual overlay file represents the actual configuration if the runtime also receives values from environment variables, a config service, or a secret manager.

Secrets must not appear in overlays in plaintext. Configuration can hold secret references; the pipeline or workload identity fetches the actual values from the secret manager according to granted permissions.

## 5. Designing a Shared Deployment Contract

A deployment contract describes the inputs and outputs supported by the deployment process. When the contract is clear, the same workflow can serve multiple environments without duplicating all the logic.

Example inputs:

| Field | Meaning | Rules |
|---|---|---|
| artifact_digest | Artifact to deploy | Required, immutable, exists in a trusted registry |
| target_environment | Target environment | Only accepts environments in the allowlist |
| config_revision | Applied configuration | Resolved revision or fingerprint |
| release_id | Release identifier | Unique, used for traceability |
| deployment_strategy | Rolling, canary, or blue-green | Must be supported by the environment |
| change_reference | Ticket or change record | Required by policy |
| dry_run | Preview changes | Can be enabled by default for risky operations |

Deployment outputs should include:

- Deployment ID and release ID.
- Actual artifact digest.
- Actual config revision.
- Environment ID.
- Start and completion timestamps.
- Result of each gate and verification step.
- Previous and post-deployment versions.
- Executing user or workload.
- Final status and log links.

The contract lets the workflow be invoked from either automated events or manual triggers while sharing the same validation and recording logic.

## 6. Structuring a Multi-Environment Deployment Process

A workflow can be divided into logical stages:

1. **Preflight:** verify the request, permissions, environment, and current state.
2. **Resolve:** fetch the artifact by digest, resolve configuration, and gather required dependencies.
3. **Validate:** check schema, policy, compatibility, and evidence.
4. **Acquire:** acquire the deployment lock or resource coordination rights.
5. **Deploy:** apply the artifact and configuration using the environment's strategy.
6. **Verify:** check the actual running version, health, smoke tests, and operational signals.
7. **Record:** save deployment evidence, release metadata, and results.
8. **Recover:** stop rollout or recover when conditions are not met.

~~~mermaid
flowchart TD
    A["Deployment request"] --> B["Preflight: actor, target, state"]
    B --> C["Resolve artifact by digest"]
    C --> D["Resolve environment configuration"]
    D --> E["Validate policy and evidence"]
    E --> F{"Gate passed?"}
    F -- "No" --> X["Block and record reason"]
    F -- "Yes" --> G["Acquire environment lock"]
    G --> H["Deploy using environment strategy"]
    H --> I["Verify actual artifact and config"]
    I --> J{"Healthy?"}
    J -- "No" --> K["Stop rollout / recover"]
    J -- "Yes" --> L["Record release evidence"]
~~~

These stages do not have to be separate jobs. You can use one job or multiple jobs depending on the platform. What matters are permission boundaries, step transition conditions, and observable outputs.

## 7. Reusing Workflows Instead of Copying Configuration

When you have multiple environments or services, copying an entire workflow and editing a few lines causes drift. Over time, dev gets a new check that production lacks; one workflow gets a bug fix while its copies remain broken.

There are three common reuse patterns:

**Reusable workflow:** packages a process or group of jobs that can be called from another workflow. Ideal when multiple repositories need the exact same sequence of steps and input contract.

**Pipeline template:** provides a standard structure for projects to create new workflows. Ideal when an organization wants standardized deployment practices while allowing controlled repository customization.

**Composite action or task module:** packages a small group of operations such as resolving artifacts, validating manifests, or publishing evidence. Ideal when reusing logic at the step level.

Separate shared parts from environment-specific parts:

- Shared logic: request validation, digest resolution, provenance checks, audit logging.
- Environment configuration: endpoints, namespaces, replicas, resource quotas.
- Environment policy: approvals, change windows, rollout thresholds.
- Deployment adapter: how to invoke Kubernetes, VMs, serverless, or other platforms.

Avoid building a monolithic template with dozens of meaningless parameters. A good template has a small contract, safe defaults, explicit versioning, and documented extension points.

When updating a template, follow a version upgrade process. Do not silently change the behavior of every pipeline using a mutable reference. For production environments, pin the template version or commit SHA and upgrade through review.

## 8. Environment Configuration Should Not Alter Security Logic

A shared workflow can accept an environment name as input, but callers must not be able to arbitrarily pick a value and gain the corresponding deployment permissions.

Distinguish between:

- **Target selection:** which environment the deployment is targeting.
- **Authorization:** whether the actor or workload is permitted to perform it.
- **Approval:** whether an authorized approver must sign off.
- **Execution identity:** which identity the pipeline uses to modify resources.

For example, a developer can request a staging deployment but has no access to production credentials. The production job only receives its identity after the corresponding gates and approvals pass.

Rules to enforce:

- Environment must be a configured enum value or ID, not an arbitrary URL.
- Permissions are verified server-side or by the platform, not based on self-reported user inputs.
- Secrets are scoped per environment and job.
- Production jobs have a dedicated identity with least-privilege permissions.
- Approvals are bound to a specific artifact, config revision, and target.
- Never grant production secrets to jobs running code from untrusted pull requests.

A reusable workflow must never become a way for a low-privilege actor to indirectly invoke high-privilege permissions without passing policy.

## 9. Different Gates, Same Unified Process

Environments can require different levels of control. Dev can deploy automatically after build; staging needs integration tests; production needs approvals, change windows, and rollout monitoring.

This does not break workflow consistency. The same process can read per-environment policy and enforce the appropriate gates.

| Gate | Dev | Staging | Production |
|---|---|---|---|
| Valid artifact digest | Required | Required | Required |
| Build/test evidence | Required | Required | Required |
| Integration/smoke test | Depends on service type | Usually required | Post-deploy or pre-release by design |
| Security policy | Baseline | Full per release policy | Full with appropriate freshness |
| Manual approval | Usually no | Per policy | Per policy/risk |
| Change window | Not usually needed | May be needed | May be mandatory |
| Rollout observation | Basic health | Integration checks | Enhanced monitoring and abort thresholds |

Do not hard-code every difference with tangled conditional branches. Policies can be described in versioned configuration, but production policies must be protected and checked independently.

If a required gate cannot be verified, the pipeline should stop or transition to a blocked state per policy. Do not automatically skip a gate simply because a verification service is failing.

## 10. Sequential, Concurrent, and Conflict-Controlled Deployments

A release typically requires a clear sequence: deploy to dev, verify, promote to staging, verify, and only then production. However, some projects may deploy multiple regions or services in parallel.

Identify dependencies between steps:

- Must database migrations run before the application?
- Is the new API compatible with older consumers?
- Can multiple instances be deployed concurrently?
- Must the canary meet thresholds before rolling out globally?
- Is there a shared environment modified by multiple pipelines concurrently?

Use concurrency groups or deployment locks scoped to the resources that actually conflict. Locking an entire organization reduces throughput; locking too narrowly fails to prevent two pipelines from modifying the same database or service simultaneously.

Options:

- Queues to deploy sequentially.
- Locks per environment or service.
- Dedicated namespaces for previews and tests.
- Conditional updates that deploy only if the current revision still matches what was checked.
- Canceling or marking older requests stale when superseded by a newer release, if policy permits.

If a pipeline is canceled mid-run, determine which resources changed and what the current state is. Never assume cancellation equals rollback.

## 11. Selecting a Rollout Strategy Based on Environment Capabilities

The same workflow can support multiple deployment strategies:

- **Rolling update:** replaces instances incrementally; suitable when old and new versions can coexist.
- **Blue-green:** prepares a new environment or instance group and then shifts traffic; requires extra capacity and a traffic-switching mechanism.
- **Canary:** exposes the new version to a subset of traffic or users, observes metrics, and gradually increases share.
- **Recreate:** stops the old version before deploying the new one; simple, but can cause downtime.

Not every environment supports every strategy. Dev may use simple rolling updates; staging may simulate canary; production chooses a strategy based on SLOs, architecture, and recovery capabilities.

The pipeline should accept a policy-allowed strategy, verify environment capabilities, and record the actual strategy used. Do not allow arbitrary input to choose a strategy unsupported by the target.

## 12. Database Migrations and Version Compatibility

Automating the same deployment process does not mean migrations always execute identically in every release. Databases have their own lifecycle and risks.

A safe strategy is expand-and-contract:

1. Add the new schema in a way compatible with the currently running application.
2. Deploy the application capable of reading/writing the new structure.
3. Migrate data or traffic according to plan.
4. Remove the old structure only when no running version depends on it.

The pipeline needs to know which migrations have run, whether migrations are idempotent, and whether the old application can operate against the new schema.

Do not automatically roll back the application if a migration has made irreversible changes. In such cases, a forward fix or dedicated data recovery procedure may be required.

## 13. Post-Deployment Verification Must Use the Same Core Criteria

Every environment should share a common set of checks to verify:

- The service is ready.
- The running artifact digest matches the requested digest.
- The config revision was applied correctly.
- Critical endpoints or functions respond.
- Required dependencies are reachable.
- Errors or latency do not exceed defined thresholds.
- Migrations and data state are consistent.

Some checks can vary by environment. Production may monitor live traffic and error rates; staging may run a full integration suite; dev may only need a quick smoke test.

Results should be recorded using the same structure so environments can be compared. If dev reports a successful deployment without recording the artifact digest or config revision, that evidence is insufficient to compare against staging and production.

## 14. Idempotency, Retry, and Rollback

A deployment workflow can be re-run due to timeouts, network drops, or repeated user triggers. Steps must therefore be designed for safe re-execution.

**Idempotency:** resubmitting the same deployment request does not create an invalid state or duplicate resources. Release IDs, deployment IDs, and state checks can detect an already completed run.

**Retry:** retry only transient, recoverable errors with bounded attempts and backoff. Never blindly retry migrations or destructive data operations.

**Rollback:** revert to a known-good artifact/configuration if compatible with the current schema and state. For irreversible data changes, use a forward fix or dedicated recovery plan.

A rollback process should follow the same deployment contract and capture the same audit trail as a normal deployment. Do not maintain an ad-hoc rollback script that runs only in production without input validation.

## 15. Observing and Tracing Releases Across Multiple Environments

To see how the same artifact moved through environments, link records with a release ID or correlation ID.

Each deployment should record:

- Release ID and deployment ID.
- Artifact digest and source commit.
- Workflow/template revision.
- Environment ID.
- Config revision/fingerprint.
- Migration version, if any.
- Deployment strategy.
- Actor or workload identity.
- Approval and policy results.
- Timestamps, status, and verification results.
- Previous version and rollback details, if applicable.

This enables the team to answer:

- Which artifact ran in staging?
- Is production running the exact digest that was tested?
- Which configurations differ between staging and production?
- Who requested or approved the deployment?
- Which step failed, and was the environment partially modified?

Never write plaintext secrets into deployment records. Store only the necessary reference/version metadata.

## 16. Multi-Environment Workflow Example

The YAML below describes generic logic, not direct syntax for any specific CI/CD platform:

~~~yaml
deployment:
  inputs:
    artifact_digest: required
    target_environment:
      allowed:
        - dev
        - staging
        - production
    release_id: required

  common_steps:
    - verify_artifact_digest
    - verify_provenance_and_evidence
    - resolve_environment_configuration
    - validate_configuration
    - evaluate_environment_policy
    - acquire_environment_lock
    - deploy_artifact_and_configuration
    - verify_running_digest_and_config
    - record_deployment_evidence

  environments:
    dev:
      approval: automatic
      strategy: rolling
      verification:
        - health_check
        - smoke_test

    staging:
      approval: policy_based
      strategy: rolling
      verification:
        - health_check
        - smoke_test
        - integration_tests

    production:
      approval: required_by_policy
      strategy: canary
      verification:
        - health_check
        - critical_journey
        - error_rate_threshold
        - latency_threshold
~~~

The key point is that common_steps runs for every environment. The environments section only declares the appropriate policy, strategy, and verification. In a real system, these values must be version-controlled and protected against unauthorized edits.

Do not let a shared workflow infer production purely from a user-entered string. The platform must verify the actor, environment protection rules, and deployment identity before granting access.

## 17. Common Anti-Patterns

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| Separate script per environment | Deployment behavior diverges | Use one workflow with controlled adapters |
| Rebuilding for staging and production | Tested artifact may differ from released artifact | Build once, promote the same digest |
| Copying workflows and editing manually | Copies drift apart over time | Use versioned reusable workflows or templates |
| Using mutable tags | Cannot be certain what content is deployed | Resolve and deploy by digest |
| Sharing secrets across all environments | A job can access overly broad credentials | Separate secret scopes and identities |
| Letting input choose arbitrary URL/cluster | May deploy to targets outside allowlist | Configured and authorized environment IDs |
| Identical gates for all environments | Too loose in production or too heavy in dev | Per-environment policies in the same workflow |
| Not checking resolved configuration | Runtime values may differ from source files | Validate resolved config and record fingerprint |
| No locks or state checks | Concurrent pipelines can overwrite each other | Resource-scoped concurrency control |
| Checking only that deploy command exited 0 | Application may still be broken | Post-deploy verification |
| Rolling back without considering migrations | May leave application incompatible with data | Schema- and state-aware recovery plan |
| Not recording release ID across environments | Hard to trace artifact journey | Use a shared correlation/release ID |

## 18. Multi-Environment Deployment Automation Checklist

Before using a single workflow across dev, staging, and production, verify:

- [ ] A deployment contract defines artifact, target, config, and strategy.
- [ ] Artifacts are built once and identified by immutable digest.
- [ ] The same artifact is promoted across environments.
- [ ] Shared configuration and environment overlays are version-controlled.
- [ ] Secrets are retrieved per environment and job, never stored in plaintext.
- [ ] Precedence rules and resolved configuration are validated.
- [ ] Workflow logic is shared, versioned, and reviewed.
- [ ] Each environment has appropriate policies, approvals, and permissions.
- [ ] Target selection is restricted via allowlists and authorization.
- [ ] Concurrency locks or queues protect conflicting resources.
- [ ] Migrations and cross-version compatibility are defined.
- [ ] Rollout strategies match each environment's capabilities.
- [ ] Post-deploy verification confirms the actual running artifact and config.
- [ ] Retries, cancellation, and rollback have deterministic behavior.
- [ ] Release IDs link evidence across environments.
- [ ] Ownership, audit trails, and partial-failure handling are defined.

## 19. Self-Assessment Exercise

A team has three environments: dev, staging, and production. Currently, each environment uses its own deployment script. Developers build an image for staging, and then the release manager rebuilds the image from the same branch for production. Configuration files are copied manually; production has several extra environment variables not stored in any repository. When a deployment fails, the team typically re-runs the script without knowing which resources were modified.

Redesign the process:

1. Which artifact should be built and stored after merge?
2. How can staging and production use the exact same digest?
3. Which configurations belong in base, overlays, and the secret manager?
4. Which steps should be shared in a reusable workflow?
5. Which gates and permissions differ among the three environments?
6. How do you verify the actual configuration after resolution?
7. Where are locks or queues needed?
8. How should migrations and rollbacks be controlled?
9. What information must release records capture to trace from dev to production?

A strong design must describe a single end-to-end flow, clearly identify what varies by environment, and prove that the tested artifact is the exact artifact deployed.

## Conclusion

Automating deployment across multiple environments reduces discrepancies between release paths and creates a repeatable, verifiable, and traceable flow. The core principles are building once, promoting the same artifact via immutable digests, resolving environment-specific configuration, and enforcing appropriate gates and permissions.

A shared workflow can still support different rollout strategies, approvals, and checks per environment. When the deployment contract is clear, configuration is versioned, concurrency is controlled, and post-deploy state is verified, teams can move the same release through dev, staging, and production with consistent evidence and controlled recovery.
