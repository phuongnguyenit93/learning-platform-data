# Preserving Independent Testing and Release When Architecture Allows

In a system composed of multiple projects or services, a change in one repository can affect another repository. An API change can break consumers; an upgraded shared library version can affect multiple applications; a new database schema can require multiple services to update together. If every change triggers pipelines across every project, CI/CD becomes slow, wastes resources, and creates unnecessary release coupling.

The goal of multi-project pipelines is to organize testing, coordination, and releases across repositories/services according to their true dependency relationships. **A project should be able to test and release independently when contracts, data, and architecture allow; when real dependencies exist, pipelines must express and govern that coordination.**

This competency belongs to **DEVOPS_CI_CD_FUNDAMENTALS**: building a CI/CD mindset from Git events, pipelines as code, automated builds, and testing through artifact management, environments, quality gates, traceable releases, secret protection, post-deployment verification, and rollback capability.

## 1. What Problem Do Multi-Project Pipelines Solve?

An organization may split source code across multiple repositories:

- `web-frontend`: user interface.
- `orders-api`: order processing.
- `catalog-api`: provides products and pricing.
- `shared-contracts`: schemas or API contracts.
- `platform-infra`: infrastructure and deployment configurations.

Projects have their own pipelines, yet they are not completely independent. The frontend calls `orders-api`; `orders-api` reads from `catalog-api`; multiple services share contracts or libraries; `platform-infra` manages deployment environments.

If every commit in one repository triggers builds and deployments in all other repositories, even a documentation edit in the frontend could cause backend pipelines to rerun. This approach increases wait times and obscures actual dependency relationships.

Multi-project pipelines help:

- Run checks in the exact repository that changed.
- Trigger dependent projects when related contracts or artifacts change.
- Share results and artifacts across project boundaries in a controlled way.
- Coordinate releases that require sequencing or shared approvals.
- Track releases from source projects to consumers and environments.
- Keep team ownership and accountability clear.

Multi-project pipelines do not mean every repository must deploy together. The goal is coordinating along the actual dependency graph and contracts, without introducing extra coupling merely because projects belong to the same system.

## 2. Distinguishing Repository, Project, Service, and Deployment Unit

These concepts may overlap in a small organization, but should not be assumed identical:

| Concept | Meaning | Example |
| --- | --- | --- |
| Repository | Where source code and change history are stored | `orders-api` Git repository |
| Project | Unit for managing code, pipelines, owners, or permissions | Commerce Orders project |
| Service | Component that runs and provides functionality | Orders API |
| Package/library | Component built and consumed by other projects | `order-client` |
| Deployment unit | Unit that is deployed or rolled back | `orders-api` container image |
| Product/system | Multiple services working together to deliver value | Commerce platform |

A monorepo can contain multiple services and multiple deployment units. A service can also draw code from multiple repositories. Therefore, pipeline design must be grounded in ownership, dependencies, and deployment boundaries—not merely folder names.

An independently releasable unit should be a component that can be built, tested, configured, deployed, and rolled back under a clear contract. If two modules always have to change together due to shared state or incompatible schemas, they likely do not yet have independent release boundaries.

## 3. Monorepo and Multirepo

The two common source-organization models have different trade-offs:

| Criterion | Monorepo | Multirepo |
| --- | --- | --- |
| Source | Multiple projects in one repository | Each project or component group has its own repository |
| Synchronized changes | Can modify multiple components in a single commit/PR | Requires multiple PRs or coordinated workflows |
| Permissions and ownership | Requires folder/project conventions | Can isolate permissions at the repository level |
| Pipeline | Requires path filtering and a dependency graph | Requires cross-repository triggers and artifact handoffs |
| Dependencies | Can use workspace/local packages | Typically via versioned packages/APIs or artifacts |
| Releases | Can be independent if build/deploy units are separated | Can be independent per repository, yet still contract-dependent |

A monorepo does not require a single monolithic pipeline. You can use path filters, build graphs, and caches to run pipelines only for affected projects and relevant consumers.

Likewise, a multirepo setup does not automatically create independence. If every deployment of `orders-api` must wait for `catalog-api` to release a new version even when the contract did not change, the pipelines remain coupled.

Choose the structure suited to your scale, ownership, change velocity, and dependency-management capabilities. Both models still require versioning, contract testing, artifact identity, and release traceability.

## 4. Drawing the Dependency Graph Before Designing Triggers

A dependency graph describes which project depends on which project, package, or contract. Distinguish:

- **Build dependency:** requires a package/tool/artifact to build.
- **Test dependency:** requires a service or fixture to run tests.
- **Runtime dependency:** a service calls another service at runtime.
- **Deployment dependency:** requires deploying one component before another.
- **Ownership dependency:** requires approval or action from another team.

Example:

~~~mermaid
flowchart TD
    C["shared-contracts"] --> O["orders-api"]
    C --> K["catalog-api"]
    K --> O
    O --> W["web-frontend"]
    I["platform-infra"] --> O
    I --> K
    I --> W
~~~

The diagram shows `orders-api` depends on contracts and `catalog-api`; the frontend depends on `orders-api`; and deployed components run on infrastructure managed by `platform-infra`.

Not every edge in the graph needs to trigger a pipeline immediately. For example:

- Editing a README in `catalog-api` does not necessarily require building `orders-api`.
- Changing `catalog`'s API schema may require contract tests with `orders-api`.
- Updating a shared base image may require rebuilding dependent images.
- Changing production infrastructure may require integration tests or approvals across multiple services.

Each edge should carry its dependency type, version/contract, owner, and trigger conditions. This avoids running redundant pipelines or missing affected consumers.

## 5. Preserving Project Boundaries Through Stable Contracts

Independent releasability depends on the stability of contracts between components:

- API contract: endpoints, methods, request/response schemas, status codes, and semantics.
- Event contract: event names, schemas, versions, and compatibility rules.
- Library contract: public APIs, package versions, and supported behavior.
- Data contract: data ownership, schemas, and read/write rules.
- Operational contract: timeouts, retries, authentication, rate limits, and SLOs.

Consumers should depend on published contracts, not on a provider's internal implementation. Providers need to know which consumers actively use their contracts before retiring legacy behavior.

### 5.1. Backward-Compatible Changes

Changes that typically introduce less coupling:

- Adding a new endpoint without altering old endpoints.
- Adding an optional response field.
- Adding an enum value when consumers are designed to handle unknown values.
- Adding an optional event field with a sensible default.
- Adding a library method without altering old API behavior.

Changes that risk breaking consumers:

- Removing or renaming a field currently in use.
- Changing a field's data type or business meaning.
- Changing an endpoint, authentication, or status code.
- Making an optional field required.
- Changing event semantics or processing order.
- Removing a package method or bumping a major version incompatibly.

Compatibility is not just valid syntax. A field that still exists but changes its business meaning can still break consumers.

### 5.2. Expand-Contract

When a change cannot be made in one step, apply the expand-contract strategy:

1. Expand: add the new API/field/schema in a way that old versions keep working.
2. Migrate: update consumers to read/write according to the new contract.
3. Verify: confirm no critical consumers still use the old contract.
4. Contract: remove the old field/API/schema in a separate release.

Do not delete an old contract merely because the provider pipeline passed. Require evidence from consumer inventory, telemetry, or migration records proving legacy usage has ended.

## 6. Contract Testing for Independent Verification

Contract tests verify that providers and consumers share the same understanding of a contract without running the whole system for every change.

There are two testing directions:

- **Consumer-driven contracts:** the consumer publishes the interactions it requires; the provider verifies its implementation satisfies those expectations.
- **Provider contract/schema validation:** the provider verifies its responses/events conform to published schemas and compatibility rules.

Example:

1. `orders-api` declares it needs `GET /catalog/items/{id}` with `id`, `price`, and `currency`.
2. The consumer contract is stored as a versioned artifact.
3. `catalog-api`'s pipeline fetches the published contract and runs provider verification.
4. If a response change fails the contract, the pipeline blocks the change before release.
5. When the contract passes, the provider can release without deploying the consumer simultaneously.

Contract tests do not replace complete integration tests. They verify interfaces and expectations between two components; bugs involving networking, auth, timeouts, databases, message brokers, or environment configs still need testing at other layers.

## 7. Selecting Tests by Change Scope

Multi-project pipelines should use multiple testing layers, each with different scope and speed:

| Test Layer | Scope | When to Run |
| --- | --- | --- |
| Unit test | Modules/classes/functions within a project | Every relevant change |
| Component test | One service with mocked or local dependencies | Every PR or merge |
| Contract test | Provider/consumer interface | When relevant contracts or implementations change |
| Integration test | A group of services and real dependencies | On key PRs, merges, or schedules |
| End-to-end test | Cross-system user flows | In integration environments or pre-release |
| Compatibility test | Consumer with multiple provider versions or vice versa | When APIs/schemas/packages change |
| Deployment smoke test | Critical flows on deployed artifacts | Post-deployment |

Do not run the entire system's end-to-end suite every time someone edits an error message in one service. Conversely, do not run only unit tests when a shared contract changes.

A sample policy could be:

- Internal change with no contract change: unit + component tests.
- API/event schema change: unit + provider/consumer contract tests.
- Database migration change: migration compatibility + integration tests.
- Base image or shared library change: build/test affected consumers per the dependency graph.
- Production release: quality gates + deployment smoke + post-deploy observation.

## 8. Running Selective Pipelines

A selective pipeline runs only projects and checks relevant to a change. Distinguish:

- Directly modified files.
- Modified project dependencies.
- Consumers impacted by contracts or packages.
- Policy-mandated tests even without modified files.

In a monorepo, each project can declare the set of paths affecting its pipeline. For example, the `orders` project workflow runs when `orders` code or shared contracts change:

~~~yaml
name: Monorepo checks

on:
  pull_request:
    paths:
      - 'services/orders/**'
      - 'contracts/**'
      - 'libs/order-client/**'

jobs:
  orders:
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/test-orders.sh
~~~

This is a GitHub Actions example for a dedicated `orders` project workflow. The `catalog` workflow can declare its own paths such as `services/catalog/**` and `contracts/**`. Path filter syntax and rename handling can differ across CI platforms; verify behavior on your target platform. If a single shared workflow needs to decide per job, create a changed-files detection step that emits structured output rather than misusing a file-count field as if it were a list of paths.

Selective pipelines require a dependency graph. If `shared-contracts` changes, the pipeline can run contract verification for `orders-api` and `catalog-api` even if neither consumer's source files changed.

When impact scope cannot be determined, run a broader test set or require review rather than skipping checks by default.

## 9. Orchestrating Pipelines Across Multiple Repositories

There are two common coordination styles:

**Orchestration:** a central pipeline triggers pipelines of dependent projects, waits for results, and aggregates statuses. Fits when release trains, multi-service coordination, or a shared approval gate are needed.

**Choreography/event-driven:** each project emits an event when a new artifact or contract is published; consumers decide independently whether to run their pipelines. Fits when teams hold independent ownership and no coordinator needs to control every step.

Both can be combined: events announce new artifacts, while a release orchestrator handles releases requiring coordination.

### 9.1. GitLab Multi-Project Trigger Example

One project can trigger a pipeline in another project:

~~~yaml
stages:
  - verify
  - downstream

verify-contract:
  stage: verify
  script:
    - ./scripts/validate-contract.sh

test-orders-consumer:
  stage: downstream
  trigger:
    project: commerce/orders-api
    branch: main
    strategy: depend
~~~

This example illustrates an upstream pipeline waiting for downstream results using GitLab's mechanism. Exact syntax and `strategy` options depend on the GitLab version in use; consult the documentation for your deployed version.

Do not default to branch `main` for production releases when exact reproducibility is needed. For coordinated releases, pass or reference an approved immutable version/ref so you know exactly which contract or artifact downstream tested.

Downstream triggers do not automatically forward all artifacts, secrets, or context. Define what data is passed, how downstream fetches artifacts, which tokens are used, and least-privilege permissions for cross-project pipelines.

### 9.2. Platform-Neutral Orchestration Example

~~~yaml
release:
  id: commerce-release-2026-08
  projects:
    - name: catalog-api
      ref: v3.6.1
      required: true
      action: verify-and-publish
    - name: orders-api
      ref: v2.8.0
      required: true
      action: verify-and-publish
    - name: web-frontend
      ref: v5.2.0
      required: false
      action: compatibility-test
  gates:
    - wait_for_required_projects
    - verify_contracts
    - verify_artifact_digests
    - require_release_approval
    - deploy_approved_artifacts
~~~

This is an illustrative model, not the schema of a specific CI platform. In practice, define immutable refs, artifact digests, dependency order, timeouts, retries, approvals, and how failures in one project are handled.

## 10. Avoiding Trigger Loops and Pipeline Explosions

When A triggers B, and B publishes an artifact that triggers A back, the system can create a pipeline loop. If each downstream triggers multiple other projects, pipeline volume can grow exponentially.

Safeguards:

- Record trigger source and upstream pipeline ID.
- Use event IDs or idempotency keys to prevent duplicate processing.
- Trigger only when artifacts/contracts actually change.
- Distinguish source-change pipelines from downstream-triggered pipelines.
- Enforce fan-out, concurrency, and timeout limits.
- Establish clear rules for retries and cancellation.
- Prevent republishing the same digest from generating endless new events.

A pipeline should know whether it is running due to a source change, a new contract, a release orchestrator, or a schedule. Trigger reasons help enforce policies and investigate abnormal pipeline runs.

## 11. Managing Artifacts and Versions Across Projects

When a project supplies a library or service artifact to consumers, publish in a way that clearly identifies:

- Package name and version.
- Artifact URI and digest.
- Source commit and pipeline run.
- Provenance/SBOM/signatures when required by policy.
- Contract/schema version.
- Compatibility support and deprecation schedule.

Consumers should explicitly pin dependency versions rather than pulling `latest` in production builds. Version upgrades should occur through reviewed changes with compatibility tests.

For service-to-service APIs, consumers typically do not pin the provider's container image, yet still need to know which API contracts/versions are supported. Use API versioning, schema registries, or contract repositories to track this.

Build once and promote the same artifact digest across environments. If artifacts are rebuilt per project or environment, having the same version string does not guarantee identical contents.

## 12. Preserving Independent Releasability

A project can release independently when the following conditions are met:

- Clear ownership and its own build/test pipeline.
- Dedicated artifact versions and digests.
- Consumer contracts are compatible or properly versioned.
- Database/data ownership does not force simultaneous deployments.
- Configs and feature flags allow toggling behaviors per release plan.
- Deployment and rollback can happen without breaking running consumers.
- Observability distinguishes service versions and deployments.

For example, `catalog-api` adds a new endpoint that `orders-api` does not use yet. The provider can deploy the new endpoint first; the consumer upgrades later. Once the consumer has migrated, the provider can deprecate the old endpoint per policy.

Conversely, if a change prevents existing consumers from running, the two projects need a coordinated plan. Do not call it an independent release merely because the pipeline has two separate jobs.

### 12.1. Using Feature Flags to Decouple Deploy from Release

Feature flags let you deploy compatible code before enabling new behavior:

1. Deploy the provider with the new API or schema without activating the new flow yet.
2. Deploy consumers capable of using the new contract.
3. Run contract/integration tests and observe.
4. Enable the feature per cohort or per service.
5. Once old consumers stop using the old contract, plan removal.

Flags do not replace versioning or authorization. Backends must still enforce permissions and request validation.

## 13. When Is a Coordinated Release Required?

Some changes genuinely require coordinating multiple projects:

- Contract-breaking changes where a transition period is impossible.
- Database migrations requiring provider and consumer to change together.
- Authentication protocol or certificate changes affecting multiple services.
- Event schema changes that older consumers cannot process.
- Business launches requiring multiple services to reach a specific state before opening traffic.

In those cases, prepare a release plan containing:

- List of projects and owners.
- Approved versions/refs or commits for each project.
- Dependency order and start conditions.
- Contracts and compatibility matrix.
- Artifact digests for each project.
- Integration testing environment.
- Approvals, deployment timing, and on-call contacts.
- Rollback/forward-fix plans for each service and shared data.

Whenever possible, use expand-contract to split a breaking change into multiple compatible releases. When impossible, the release orchestrator must coordinate the exact sequence and provide aggregated status.

## 14. Data and Databases Are the Hardest Independence Boundary

Two services with separate pipelines that write to the same database or share ownership of a table can remain tightly coupled. A migration in service A can break service B even when B's source code never changed.

To reduce coupling:

- Each service should own its own data and schema where architecture allows.
- Avoid letting multiple services write directly to tables managed by another service.
- Use API or event contracts instead of internal database access.
- Migrate using expand-contract.
- Preserve read/write compatibility during transition windows.
- Maintain migration tests and appropriate backup/restore plans.
- Record migration versions in release manifests.

If the database cannot yet be separated, manage schema ownership, migration order, and consumer compatibility explicitly. Pipelines must check dependent services before permitting contract-breaking migrations.

Never roll back destructive migrations merely by redeploying an old image. Data restores, forward fixes, or compensating migrations may be required; this plan must be determined before release.

## 15. Protecting Access Across Projects

Cross-project pipelines often need to read source, download artifacts, or trigger pipelines in other projects. This is a permission boundary that must be controlled.

Practices:

- Use dedicated tokens/service identities for automation.
- Grant trigger or artifact-read permissions only to necessary projects.
- Prefer short-lived credentials or workload identities where supported by the platform.
- Avoid passing secrets via pipeline variables when unnecessary.
- Never log tokens or sensitive values.
- Verify downstream project, ref, and artifact digest before use.
- Restrict who can edit shared pipeline templates and release orchestrators.
- Separate build/test permissions from production publish/deploy permissions.

Do not blindly trust every pipeline triggered from an internal project. A project might receive changes from forks or unprotected branches. Downstream pipelines must verify source identity, trigger context, and artifact provenance per policy.

## 16. Managing Shared Pipeline Templates and Reusable Workflows

Teams frequently share templates to standardize building, testing, scanning, publishing, and deploying. Templates reduce duplication but also create dependencies across projects.

Recommended practices:

- Keep templates or reusable workflows in a dedicated repository.
- Document owners, versions, changelogs, and support scope.
- Pin templates to controlled versions/refs.
- Test templates against several representative projects.
- Release template changes through a reviewed process.
- Maintain an upgrade schedule and a way to roll back to prior versions.
- Avoid silently changing production behavior via `main`.

A template change can affect hundreds of pipelines. Therefore, distinguish bug-fix patches, compatible changes, and breaking changes; use versioning or migration guides so projects upgrade deliberately.

Avoid building one giant template containing business logic for every project. Keep shared parts focused on build conventions, security, artifact metadata, and quality gates; project-specific business logic belongs to project owners.

## 17. Tracking Aggregated Status Without Losing Per-Project Detail

A release orchestrator can summarize:

| Project | Pipeline | Contract | Artifact | Deployment |
| --- | --- | --- | --- | --- |
| `catalog-api` | Passed | Verified | Digest A | Staging verified |
| `orders-api` | Passed | Verified | Digest B | Staging verified |
| `web-frontend` | Running | Pending | Not available | Not deployed |

Aggregated status shows where the release train stands, but does not replace each project's underlying status. When a project fails, link directly to its specific pipeline run, logs, test reports, and owner.

Each project should emit structured results:

- Project name and source revision.
- Pipeline run ID.
- Verified contract/schema version.
- Artifact URI and digest.
- Quality gate results.
- Deployment ID and environment, if deployed.
- Status, timestamp, and evidence links.

The release orchestrator should store both passing and failing results, not just green jobs.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Every commit triggers every project | Slow pipelines and wasted resources | Dependency graph and selective triggers |
| Using `main` branch as input to coordinated releases | Downstream may run different revisions across retries | Pin immutable refs/versions |
| Running only unit tests inside a project | Misses contract bugs with consumers | Dependency-driven contract and integration tests |
| Deploying all services together by default | Creates unnecessary release coupling | Release independently when contracts allow |
| Assuming multirepo means independence | Runtime/data coupling still exists | Evaluate contracts and ownership |
| Sharing an unowned database | One service's migration breaks another | Schema ownership and expand-contract |
| A→B→A trigger loops | Pipeline storms or infinite runs | Trigger reasons, event IDs, and idempotency |
| Passing artifacts by tag name | Consumers may fetch wrong contents | Artifact digests and provenance |
| Using broad-privilege tokens across projects | One pipeline compromise impacts many repositories | Least privilege and isolated identities |
| Uncontrolled changes to shared templates | Multiple projects impacted unexpectedly | Versioning, pinning, and migration process |
| Release orchestrator hides project status | Hard to find owners and root causes | Preserve links to source pipelines/evidence |
| Rolling back image while forgetting migrations | Old app cannot read new data | Separate data and forward/rollback plans |

## 19. Multi-Project Pipeline Design Checklist

**Boundaries and dependencies**

- [ ] Repository, project, service, and deployment unit are clearly distinguished.
- [ ] A dependency graph exists with dependency types and owners.
- [ ] Contracts/APIs/events/libraries/data are versioned or compatibility-managed.
- [ ] Projects capable of building, testing, and releasing independently are identified.
- [ ] Changes requiring coordination have dedicated release plans.

**Testing and triggers**

- [ ] Selective triggers run only relevant projects/tests.
- [ ] Contract changes trigger required consumer/provider verification.
- [ ] Appropriate unit, component, contract, integration, and post-deploy tests exist.
- [ ] A fallback exists when impact scope cannot be determined.
- [ ] Downstream triggers have timeouts, retries, and loop prevention.

**Artifacts and releases**

- [ ] Each project has its own artifact versions and digests.
- [ ] Build once and promote the same digest across environments.
- [ ] Provenance/SBOM/scan evidence meets policy.
- [ ] The release orchestrator pins exact refs and artifacts.
- [ ] Deployments/rollbacks can be performed per service where architecture permits.

**Security and operations**

- [ ] Cross-project identities have least-privilege permissions.
- [ ] Secrets are not passed or logged outside necessary scopes.
- [ ] Shared templates have owners, versions, and upgrade processes.
- [ ] Aggregated release status links back to per-project evidence.
- [ ] Database migrations and side effects have compatibility/recovery plans.
- [ ] Release IDs, pipeline run IDs, deployment IDs, and incident linkage exist.

## Conclusion

Multi-project pipelines must accurately reflect dependency graphs and component contracts. When a project has clear ownership, artifacts, contracts, data boundaries, and rollback procedures, it can build, test, and release independently. When changes break compatibility or share state, pipelines must coordinate deliberately with explicit sequencing, approvals, and data plans.

Selective triggers, contract testing, immutable artifact digests, versioned shared pipeline templates, and release orchestration balance speed with control. The goal is not cramming every project into one giant pipeline, but empowering each team to release within safe boundaries while providing clear evidence whenever cross-team coordination is required.
