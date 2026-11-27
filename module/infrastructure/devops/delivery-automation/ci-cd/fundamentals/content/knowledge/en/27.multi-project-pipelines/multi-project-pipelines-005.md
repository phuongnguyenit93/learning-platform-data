# Designing Reusable Pipelines That Still Allow Clear Configuration

## Learning Objectives

After this lesson, learners can:

- Explain the benefits and limitations of standardizing CI/CD across multiple repositories or multiple projects.
- Distinguish between pipeline templates, reusable workflows, composite action/task modules, and shared pipeline libraries.
- Identify which parts of a workflow should be shared and which project-specific differences should be declared per project.
- Design contracts for inputs, outputs, permissions, secrets, and artifacts in a reusable pipeline.
- Organize configuration using schemas, defaults, profiles, and governed overrides.
- Create extension points so projects can add custom steps without copying the entire pipeline.
- Manage versioning, compatibility, deprecation, and upgrade rollouts for shared pipelines.
- Test, observe, and govern reusable pipelines across multiple projects.

## 1. Why Are Reusable Pipelines Needed?

When an organization has many repositories, each team often builds its own pipeline for linting, testing, building, scanning, publishing, and deploying. Initially those pipelines look quite similar, but over time they diverge:

- One repository checks dependencies while another forgets that step.
- One project publishes artifacts by digest while another uses mutable tags that can be overwritten.
- Token permissions and secret-retrieval methods become inconsistent.
- A workflow bug is fixed in one repository while other repositories still carry the bug.
- When security policies change, the platform team has to edit dozens of files.
- Newcomers cannot tell which steps are mandatory and which are project-specific options.

Reusable pipelines standardize what is meaningfully shared, reduce duplication, and allow process changes to be managed centrally.

However, not every project is identical. A Java library, a Spring Boot service, a frontend SPA, and a message-processing worker may need different build, test, packaging, and deployment steps. Forcing all of them into one workflow full of hidden conditionals makes the pipeline harder to understand than the original copies.

The goal is to create **a standardized workflow with a clear contract, explicit configuration, and controlled extension points**.

A well-designed reusable pipeline should answer:

- Which steps must every project execute?
- What information must a project provide?
- Which differences are configurable?
- Where can a project insert custom steps?
- By what principles are permissions and secrets granted?
- When a shared pipeline changes, which projects are affected?
- How is a project's configuration validated before execution?

## 2. Principle: Standardize the Process, Declare the Differences

Start by classifying the parts of a pipeline.

**Shared parts** typically include:

- Resolving source revision and pipeline context.
- Setting up the build environment consistently.
- Restoring dependencies through organization-approved mechanisms.
- Running mandatory checks.
- Collecting and verifying reports.
- Producing artifacts with immutable identifiers.
- Attaching provenance and metadata.
- Enforcing quality gates.
- Publishing evidence and deployment records.
- Controlling permissions, secrets, and auditing.

**Parts that can vary per project** typically include:

- Language and runtime.
- Build tool and build command.
- List of modules or packages.
- Test suites to execute.
- Supported runtime version.
- Artifact type and packaging method.
- Deployment environments and rollout strategies.
- Business-specific checks.
- Resources or dependencies required for integration tests.

**Parts projects should not arbitrarily alter** typically include:

- Least-privilege permission policies.
- Artifact provenance verification methods.
- Mandatory pre-production gates.
- Secret protection mechanisms.
- Audit and evidence retention rules.
- Controls preventing untrusted code from running with elevated privileges.

The architecture can be visualized as:

~~~mermaid
flowchart TD
    A["Project repository"] --> B["Project pipeline config"]
    B --> C["Reusable pipeline contract"]
    C --> D["Shared build and test workflow"]
    C --> E["Shared security and evidence workflow"]
    C --> F["Shared release and deploy workflow"]
    D --> G["Project artifact"]
    E --> H["Quality decision"]
    G --> H
    H --> I["Release workflow"]
    I --> J["Deployment and verification"]
    K["Organization policy"] --> C
    K --> H
~~~

Repositories supply configuration and source code. Shared pipelines execute the defined rules. Organization policies govern conditions that cannot be bypassed arbitrarily.

## 3. Levels of Pipeline Reuse

Not every shared piece should be packaged the same way. There are four common forms.

| Form | How It Works | Best Suited When | Points to Watch |
|---|---|---|---|
| Pipeline template | Generates initial starter files for repositories to copy | You want to standardize initial scaffolding | After copying, instances can drift |
| Reusable workflow | Caller workflow invokes a shared workflow | You need centralized logic and controlled updates | Requires careful input/output and permission design |
| Composite action/task module | Packages a small group of steps | You want step/job-level operation reuse | Do not bundle an entire lifecycle into one opaque action |
| Shared pipeline library/plugin | Shares functions or abstractions across pipelines | Platform has suitable library/plugin mechanisms | Requires strict API and version management |

### 3.1. Pipeline Template

A template generates starter scaffolding consisting of workflows, configurations, and documentation. Repositories can tailor their copy to their needs.

Pros:

- Easy to understand because files reside directly in the repository.
- Projects control their own changes.
- No runtime dependency on an external workflow.

Limitations:

- Copies can gradually diverge.
- Policy updates require synchronization or drift-detection tooling.
- Fixing a bug in the template does not automatically fix previously created repositories.

Templates fit bootstrapping or platforms that do not support invoking shared workflows.

### 3.2. Reusable Workflow

A reusable workflow keeps logic in one place and lets repositories invoke it via a contract. This is usually the right choice when multiple projects need the same versioned process.

Pros:

- Centralized logic fixes.
- Straightforward version control.
- Can standardize permissions and evidence collection.
- Reduces duplication across repositories.

Limitations:

- Requires understanding inputs, outputs, secrets, and permission propagation.
- One change can affect many consumers.
- Debugging requires inspecting both caller and callee workflows.

Keep each reusable workflow focused on a single clear responsibility, such as `build-and-test`, `publish-artifact`, or `deploy-environment`. A higher-level orchestrator workflow can invoke specialized workflows.

### 3.3. Composite Action or Task Module

This is a smaller unit of reuse, typically wrapping a single operation such as:

- Resolving a toolchain.
- Validating a project manifest.
- Fetching reports by run ID.
- Computing digests and generating an evidence manifest.
- Verifying artifact provenance.
- Publishing a deployment record.

They fit when logic is needed across multiple workflows without wrapping an entire pipeline lifecycle.

A small action should have simple inputs and outputs. If an action installs tools, builds, tests, publishes, deploys, and sends notifications all by itself, it hides too much behavior and makes failures hard to diagnose.

### 3.4. Shared Library or Plugin

Some platforms support pipeline libraries, plugins, or task frameworks. This form fits when an organization needs complex abstractions, logic testable as code, and broad reuse across many pipelines.

You must manage:

- Public APIs.
- Versioning and compatibility.
- Library dependencies.
- Permissions when the library executes.
- How to debug and identify which library revision ran.

Do not build custom abstractions when existing reusable workflows or actions already meet requirements.

## 4. Defining Reuse Boundaries

Before building reusable pipelines, inspect existing pipelines and identify genuine repetition.

Group by capability:

- Source preparation.
- Build and test.
- Security analysis.
- Artifact publishing.
- Release verification.
- Deployment.
- Post-deploy verification.
- Evidence collection.

A shared process does not have to be a single monolithic file. Splitting by capability lets consumers invoke only what they need and reduces coupling.

Example:

| Capability | Shared | Project Configuration |
|---|---|---|
| Build | Standardized logging, caching, artifact upload | Build tool, command, modules |
| Test | Report collection, result aggregation | Test suites, profiles, runtime |
| Security | Scanners and baseline policies | Scope or approved exceptions |
| Package | Attaching metadata, computing digests | Artifact type and package coordinates |
| Publish | Permissions, registry validation, evidence | Permitted registry/project namespace |
| Deploy | Preflight, approvals, verification | Permitted target environments and strategies |

A piece should only be abstracted when at least one clear reason exists: it is reused across multiple places, has rules requiring consistency, or undergoes changes that need centralized management.

Do not create a reusable abstraction merely because two files share a few lines. If behavioral differences outweigh commonalities, a small module or template may be a better fit.

## 5. Designing the Input Contract

The contract is the interface between calling repositories and shared workflows.

Inputs need:

- Clear name and meaning.
- Data type.
- Required vs. optional status.
- Default value, if applicable.
- Allowed domain or allowlist.
- Compatibility conditions.
- Validation rules.
- Sensitivity level if it is a secret reference.

Example:

| Input | Type | Required | Rules |
|---|---|---|---|
| `project_type` | Enum | Yes | `service`, `library`, `frontend`, `worker` |
| `runtime_version` | String/Enum | Yes | Accepts only supported versions |
| `build_tool` | Enum | Yes | `maven`, `gradle`, `npm`, or approved tools |
| `build_command` | String | Yes or via profile | Must conform to project contract |
| `test_profile` | Enum | No | Defaults based on `project_type` |
| `artifact_name` | String | Yes | Must not contain arbitrary paths |
| `deploy_target` | Enum | No | Accepts only declared environments |
| `deployment_strategy` | Enum | No | Accepts only strategies supported by target |

Avoid vague inputs like `mode`, `custom`, `extra`, or `options` without an exact schema describing them. A generically named input capable of altering any behavior makes workflows hard to review and hard to secure.

Never accept an arbitrary shell command string from a repository and execute it with publish or production privileges. When custom commands are needed, run them in a least-privilege job without sensitive secrets. Privileged release steps must remain isolated.

## 6. Output and Status Contracts

Reusable pipelines must emit structured outputs so downstream workflows can consume them without scraping logs or guessing filenames.

Useful outputs:

- `source_commit`.
- `pipeline_run_id`.
- `project_id`.
- `artifact_uri`.
- `artifact_digest`.
- `build_result`.
- `test_summary`.
- `evidence_manifest_uri`.
- `quality_gate_decision`.
- `release_id`.
- `deployment_id`.
- `deployment_status`.

Clearly define output semantics:

- Is the output always produced?
- Can it be empty?
- Which job produces it?
- Does it contain secrets?
- Can it serve as input to downstream workflows?
- Is it scoped to the current attempt?

A workflow can finish with status `success` while an artifact output does not exist if publishing was skipped. Therefore, output contracts must distinguish `success`, `skipped`, `failed`, `partial`, and `unavailable`.

Never require consumers to parse prose sentences in logs to extract an artifact version. Use structured outputs with explicit schemas and versions.

## 7. Explicit Per-Project Configuration

A repository should maintain a configuration file describing permitted choices. Configuration should be easy to read, reviewed alongside source code, and validated before the pipeline executes.

Example directory layout:

~~~text
project/
├── .ci/
│   ├── pipeline.yml
│   └── schema/
│       └── pipeline-config.schema.json
├── src/
├── tests/
└── build files
~~~

Example configuration file:

~~~yaml
pipeline:
  schema_version: 1

  project:
    name: billing-service
    type: service
    owner: payments-team

  build:
    tool: gradle
    runtime: "21"
    command: "./gradlew clean build"
    modules:
      - api
      - application

  tests:
    unit:
      enabled: true
      command: "./gradlew test"
    integration:
      enabled: true
      profile: ci

  artifact:
    type: container
    name: billing-service

  deployment:
    enabled: true
    targets:
      - staging
      - production
    strategy:
      staging: rolling
      production: canary
~~~

This is an illustrative structure, not the schema of a specific CI tool. Fields should be defined and validated by the organization's schema.

Configuration files must not contain tokens, passwords, private keys, or credentials. Store only secret reference names or identity profiles when genuinely necessary and allowlisted.

## 8. Schema Validation and Early Configuration Errors

Misconfigurations should be caught before the pipeline starts building or acquires deployment permissions.

A schema can check:

- Required fields.
- Data types.
- Valid enums.
- Name patterns.
- Numeric ranges.
- Nested structures.
- Disallowed fields.
- Cross-field constraints.

Examples:

- If `project_type` is `library`, `deploy.enabled` must be `false`.
- If `artifact.type` is `container`, an image name is required.
- If `deployment.enabled` is `true`, at least one target must be specified.
- `deployment.strategy` must be supported by the target.
- Runtime version must belong to the platform's supported list.
- If integration tests are enabled, a test profile or service dependencies must be declared.

You can use JSON Schema, CUE, YAML schemas, or a custom validator. Whichever tool you choose, version the schema and surface error messages clear enough for project owners to know which field failed.

Prefer failing fast. Never let a pipeline spend 15 minutes building only to discover that `project_type` is invalid or the `production` target is disallowed.

## 9. Precedence Rules and Configuration Sources

Configuration can come from multiple layers:

1. Organization policy.
2. Shared pipeline defaults.
3. Project configuration.
4. Environment-specific configuration.
5. Permitted runtime inputs.
6. Secret manager or identity provider.

Without defined precedence rules, two projects can interpret the same configuration differently.

Reference model:

- Organization policy sets non-overridable guardrails.
- Shared workflows provide safe defaults.
- Project config declares build/test characteristics.
- Environment config supplies endpoints, quotas, and permitted deployment strategies.
- Runtime inputs can only select from declared options.
- Secret manager supplies secret values bound to identity.

Never let runtime inputs override organization policy. For instance, a repository must not be able to set `security_scan.required=false` when scanning is mandated by the organization.

Record the resolved configuration, schema version, and policy revision in pipeline evidence. This explains why one run behaved differently from a previous run.

## 10. Separating Configuration from Logic

Configuration should describe choices; workflows contain execution logic.

For example, configuration selects Java 21 runtime. The workflow is responsible for installing the right toolchain, verifying the version, and running the build.

Configuration selects `canary` as the deployment strategy. The workflow checks whether the target supports canary, acquires the appropriate permissions, executes the rollout, and evaluates metrics.

If configuration starts containing embedded scripts, nested conditionals, and business logic, the config file has likely turned into an uncontrollable programming language.

Guiding principles:

- Configuration chooses among supported behaviors.
- Shared logic implements the behavior.
- Policy determines which behaviors are permitted.
- Extension points handle justified special cases.
- Secrets are retrieved from a secret manager.
- Resolved values are recorded for traceability.

Do not overload a single boolean variable with too many meanings. For instance, `skip_checks` could accidentally disable linting, testing, and security scanning all at once. Use distinct, clearly named options paired with corresponding policies.

## 11. Profiles for Project Groups

Some projects share similar characteristics. Profiles can reduce repetitive configuration:

- `java-library`.
- `java-service`.
- `frontend-spa`.
- `container-worker`.
- `serverless-function`.

Profiles supply sensible defaults while still making clear which values are inherited and which are overridden by the project.

Example:

~~~yaml
pipeline:
  profile: java-service

  overrides:
    build:
      runtime: "21"

    tests:
      integration:
        enabled: true

    deployment:
      targets:
        - staging
        - production
~~~

Avoid creating excessive profiles tailored to individual repositories. A profile should represent a stable architectural or lifecycle archetype, not an alias for each project.

When a profile changes, record the profile version or resolved configuration so you know which defaults a pipeline run used.

## 12. Controlled Extension Points

Some projects require custom steps that shared pipelines cannot cover. Extension points can be supported, but their placement and permissions must be strictly bounded.

Reasonable extension point examples:

- Pre-build validation without publish permissions.
- Custom test job running in an isolated environment.
- Post-build verification with read-only artifact access.
- Pre-deploy check with read-only target state access.
- Post-deploy smoke test within a granted scope.

An extension point must define:

- When it is invoked.
- Inputs and outputs.
- Timeout.
- Runner/permission scope.
- Which secrets are permitted.
- Success/failure conditions.
- Whether it can block the pipeline.
- How logs and reports are collected.

Do not allow projects to inject arbitrary commands before or after privileged steps. A custom hook running right before publish with a registry-write token could become a path for arbitrary code to release unauthorized artifacts.

High-privilege extensions require review, pinned revisions, and dedicated policies. Use a separate protected workflow or a reusable component approved by the platform team.

## 13. Separating Build/Test from Privileged Publish/Deploy

A shared pipeline must not grant every permission to every job just because a final stage needs to publish or deploy.

Split into zones:

- Validation jobs: read source, run tests and scans.
- Build job: produce artifacts on controlled runners.
- Evidence job: aggregate reports and provenance.
- Publish job: write permissions scoped to the exact registry/project.
- Deploy job: dedicated identity for the target environment.

Project configuration may select a build tool or test profile, but must never grant itself registry write access or production permissions.

Scope permissions by:

- Repository/project.
- Job or workflow.
- Protected branch/tag.
- Artifact repository.
- Environment.
- Credential lifetime.
- Specific permitted actions.

When the platform supports OIDC or workload identity, use short-lived credentials bound to verified claims. Static secrets must be scoped per job and environment rather than passed across entire workflows.

## 14. Reusable Pipelines and Artifact Contracts

Shared workflows should communicate using artifact references and digests.

Example return output from a build workflow:

~~~yaml
outputs:
  artifact:
    uri: registry.example.invalid/team/billing-service
    digest: sha256:0123456789abcdef
  source:
    commit: 8f4c2a1
  evidence:
    manifest_uri: evidence://release-123/manifest.json
~~~

This is illustrative data. In a real system, digests must be computed from actual artifacts and outputs must be protected under the trust model.

Downstream deploy workflows should accept the artifact digest directly. Never look up the latest artifact via mutable tags or rely on filenames left in a previous job's workspace.

An artifact contract should specify:

- Permitted registries and repositories.
- Digest format.
- Required metadata.
- Provenance or signature policies.
- Retention.
- Cross-environment promotion rules.
- Behavior when an artifact is revoked.

This enables a single reusable deploy workflow to deploy artifacts from many projects while still verifying their origin.

## 15. Versioning Shared Pipelines

A reusable workflow is a dependency of consumer repositories. When the workflow changes, consumer pipeline behavior can change too.

Version all of the following:

- Reusable workflows.
- Composite actions/task modules.
- Shared libraries/plugins.
- Configuration schemas.
- Project profiles.
- Policy bundles.

Use semantic versioning when the contract has clear compatibility rules:

- Patch: bug fixes that do not alter the contract.
- Minor: backward-compatible feature additions.
- Major: input/output or semantic changes that may break existing consumers.

Where supported by the platform, pin reusable components to protected version tags or immutable commit SHAs. For production pipelines, revision pinning ensures reproducibility and aids investigation.

Do not point all production consumers at a mutable branch like `main` without change controls. Consumers need to know the exact revision that executed.

## 16. Evolving Contracts and Managing Compatibility

When renaming inputs, removing outputs, or changing defaults, follow a migration path.

A safe process:

1. Add the new input while keeping the old input.
2. Support both during a transition period.
3. Warn consumers still using the old input.
4. Update project configs and test.
5. Release the version containing the contract change.
6. Remove the old input only in the next major version.
7. Publish a migration guide and support timeline.

Pay special attention to default changes. Changing a default from test profile A to B can alter behavior across dozens of projects even though their config files did not change.

Therefore, defaults are part of the contract and must be versioned. Pipeline runs should record resolved configs so historical outcomes remain explainable.

## 17. Managing Consumer Adoption and Upgrades

When a new reusable pipeline version is released, do not blindly update every repository at once.

Roll out in stages:

- Internal test repositories.
- A few representative projects with diverse structures.
- Pilot project group.
- Expand by team or portfolio.
- Monitor errors and roll back versions if needed.

Track for each consumer:

- Current pipeline version in use.
- Config schema version.
- Project owner.
- Last upgrade date.
- Compatibility status.
- Active exceptions.
- Link to the migration guide.

Bots or automation can open version-bump pull requests, but builds/tests and reviews still apply per policy. Opening a PR does not mean the consumer has already upgraded.

For mandatory security changes, set deadlines and track consumers that have not yet updated. Do not maintain end-of-life versions indefinitely.

## 18. Testing Reusable Pipelines

Shared pipelines are code operating across many projects. Test contracts and behaviors, not merely whether YAML parses cleanly.

Testing layers:

**Schema tests**

- Valid configurations are accepted.
- Wrong field types are rejected.
- Invalid enum values are rejected.
- Conflicting field combinations are rejected.
- Secrets are disallowed inside config files.

**Contract tests**

- Inputs/outputs conform to schema.
- Output artifacts carry digests.
- Reports link to the exact run.
- Permissions do not escalate beyond the contract.
- Errors propagate back to callers with proper statuses.

**Integration tests**

- Workflow runs against a sample project for each profile.
- Artifacts are produced and published to a test registry.
- Evidence collector receives all expected reports.
- Deployment to a test environment can be verified and rolled back.

**Compatibility tests**

- Older consumers still work with the new version within the supported range.
- New config schemas handle legacy configs properly.
- Breaking changes are caught before release.

**Security tests**

- Untrusted jobs do not receive privileged secrets.
- Inputs cannot select targets outside the allowlist.
- Reusable components are pinned by revision.
- Custom hooks cannot inherit publish/deploy job permissions.

Maintain a set of fixture repositories representing services, libraries, frontends, and workers to test pipeline changes.

## 19. Observing Shared Pipelines

When a reusable pipeline serves many repositories, distinguish shared workflow bugs from consumer config or source failures.

Record:

- Shared workflow name and version/SHA.
- Project/repository ID.
- Config schema and profile version.
- Resolved configuration fingerprint.
- Pipeline run ID and attempt.
- Failed job and step.
- Artifact digest.
- Policy revision.
- Runner image and toolchain version.
- Consumer-specific extensions executed.
- Gate and deployment outcomes.

Track metrics:

| Metric | Meaning |
|---|---|
| Adoption rate | Percentage of repositories on supported versions |
| Upgrade lag | Delay before consumers upgrade |
| Workflow failure rate | Failure rate of the reusable workflow |
| Config validation failures | Pre-execution configuration errors |
| Time to repair | Time to fix shared pipeline defects |
| Exception count | Number of projects requiring exceptions |
| Version distribution | Revisions currently in active use |
| Pipeline duration by profile | Performance across project archetypes |

If a new version raises failure rates across multiple repositories, the bug is likely in the shared workflow. If only one project fails with a config validation error, inspect that project's configuration or profile.

## 20. Governance and Ownership

Shared pipelines typically involve multiple stakeholders:

- Platform team owns reusable workflows and runners.
- Security team owns policies and baseline scans.
- Project teams own source code and project configs.
- Release owners are accountable for release decisions.
- Operations team owns environments and deployment controls.

Define clearly:

- Who can modify shared workflows?
- Who reviews changes with security impact?
- Who releases new versions?
- Who approves exceptions?
- Who is responsible for upgrading consumers?
- Who handles incidents caused by shared pipelines?
- Who has authority to alter production policies?

Never allow a project team to alter centralized policies simply by editing a config file in their own repository. Mandatory policies must be managed where appropriate authority resides.

Clear ownership reduces investigation time when multiple projects hit the same failure.

## 21. Example Shared Pipeline Invocation Flow

The following YAML illustrates a repository declaring configuration and invoking shared workflows. Exact syntax depends on the CI/CD platform.

~~~yaml
project:
  name: billing-service
  profile: java-service
  config_schema: 2

pipeline:
  shared_components:
    build_and_test: v3.2.0
    security_analysis: v2.4.1
    publish_artifact: v1.8.0
    deploy: v4.1.0

  build:
    runtime: "21"
    tool: gradle
    modules:
      - api
      - application

  tests:
    unit: true
    integration:
      enabled: true
      profile: ci

  artifact:
    type: container
    repository: team/billing-service

  deployment:
    staging:
      enabled: true
      strategy: rolling
    production:
      enabled: true
      strategy: canary
      approval: required
~~~

High-level flow:

~~~mermaid
flowchart TD
    A["Project config"] --> B["Schema validation"]
    B --> C["Resolve defaults and policy"]
    C --> D["Build and test workflow"]
    D --> E["Security and evidence workflow"]
    E --> F["Artifact digest + manifest"]
    F --> G["Publish workflow"]
    G --> H["Release gate"]
    H --> I["Deploy workflow"]
    I --> J["Post-deploy verification"]
~~~

The key point is that project configuration selects supported capabilities and declares intentional differences. Shared workflows remain in control of execution logic, policies, and permissions.

## 22. Anti-Patterns in Designing Reusable Pipelines

| Anti-Pattern | Risk | How to Improve |
|---|---|---|
| One giant workflow for all projects | Many conditional branches and hard debugging | Split reusable workflows by capability |
| Copying templates and never updating | Consumers drift away from standards | Track versions and drift |
| Accepting arbitrary shell strings as inputs | Executes code with unclear privileges | Use enums/contracts and least-privilege jobs |
| Too many skip booleans | Unclear which mandatory checks were bypassed | Configure individual capabilities and policies |
| Silently changing defaults | Consumer behavior changes without config edits | Version defaults and log resolved configs |
| Reusable workflows pointing to mutable branches | Runs cannot be reproduced | Pin protected tags or SHAs |
| Projects supplying their own production secrets | Broadens privilege scope and leak risk | Centralize environment identities and approvals |
| Arbitrary hooks inside publish jobs | Project code can acquire elevated privileges | Isolate hooks from high-privilege jobs |
| No output contract | Consumers parse logs or guess filenames | Structured outputs with explicit schemas |
| Removing old inputs immediately | Multiple consumers break | Deprecation and migration window |
| Testing workflows on only one repository | Misses profile differences | Representative fixture projects |
| Not tracking consumer versions | Unknown who still runs outdated versions | Adoption inventory and upgrade automation |

## 23. Checklist for Designing Reusable Pipelines

Before rolling out across multiple projects, verify:

- [ ] Truly shared capabilities have been identified.
- [ ] Project-specific parts are expressed via explicit configuration.
- [ ] The right reuse mechanism is chosen: template, workflow, action, or library.
- [ ] Inputs have types, required/default rules, enums, and validation.
- [ ] Outputs are structured with clear schemas and semantics.
- [ ] Project configs are validated before execution.
- [ ] Precedence between organization, shared defaults, project, and environment is defined.
- [ ] Mandatory policies cannot be overridden by projects.
- [ ] Profiles represent stable project archetypes.
- [ ] Extension points restrict placement, permissions, timeouts, and outputs.
- [ ] Build/test is separated from privileged publish/deploy jobs.
- [ ] Secrets are retrieved per job and environment.
- [ ] Artifacts use immutable digests and proper provenance.
- [ ] Shared components, schemas, and profiles are versioned.
- [ ] Breaking changes include migration guides and deprecation windows.
- [ ] Fixture projects and contract/integration/security tests exist.
- [ ] Adoption inventory, owners, and upgrade processes are in place.
- [ ] Logs record shared workflow versions and resolved configurations.
- [ ] Mechanisms exist for approved exceptions and policy overrides.
- [ ] Rollback procedures exist if a new shared workflow version causes failures.

## 24. Self-Assessment Exercise

An organization has 40 repositories: 18 Java services, 8 Java libraries, 10 frontends, and 4 workers. Currently each repository has its own workflow. The platform team wants to create a unified shared pipeline setup.

Organizational requirements:

- Every project must run unit tests and dependency scans.
- Services and workers require integration tests.
- Libraries must publish packages but never deploy.
- Frontends must build bundles and deploy to a CDN.
- Production deployments require approvals and dedicated identities.
- Project teams may declare build commands and test profiles.
- Projects must not disable mandatory security policies.
- Some projects require custom post-deploy smoke tests.

Design the following:

1. Which capabilities should reusable workflows be split into?
2. How many profiles are needed and what does each profile describe?
3. Which fields does the input contract require?
4. Which settings can projects override and which are controlled by organization policy?
5. How do you prevent a library from accidentally invoking the deployment workflow?
6. At which extension point and with what permissions should custom smoke tests run?
7. How do artifact contracts differ across Java packages, container images, and frontend bundles?
8. How are versioning and deprecation managed?
9. Which fixture repositories must be tested before rollout?
10. How do you identify repositories that have not yet upgraded from older versions?

A good design does not force all 40 repositories into one complex tangle of conditionals. Use a foundational contract, capability-based workflows, archetype profiles, and explicit per-repository configuration.

## Conclusion

Reusable pipelines enable multiple projects to share workflows, policies, and evidence-collection mechanisms. To avoid creating an opaque abstraction, clearly separate mandatory shared parts, configurable differences, and controlled extension points.

Design typed input/output contracts, validate configurations early, establish precedence rules, separate build permissions from publish/deploy, and version workflows alongside schemas. When consumers know exactly which version they invoke, which inputs they supply, and which outputs they receive, the organization can upgrade CI/CD centrally while preserving transparent configurability for every project.
