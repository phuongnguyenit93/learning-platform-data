# Evaluating Complexity Before Adding Multi-Pipeline Orchestration

Multi-pipeline orchestration splits software delivery into independent parts: building services, testing contracts, publishing artifacts, provisioning infrastructure, and releasing applications. Yet every pipeline boundary also introduces data contracts, triggers, access permissions, waiting states, retries, and error-handling logic. If you split one large pipeline into multiple workflows without a genuine need for independence, the system can become harder to operate than before.

Before adding orchestration, identify the current problem, the degree of coupling across projects, and the coordination costs that will arise. Only add an orchestration layer when gains in ownership, speed, reusability, fault isolation, or independent releasability outweigh coordination costs. The goal is choosing an architecture that is just enough for teams to understand, control, and trace the entire flow.

## 1. What Is Multi-Pipeline Orchestration?

A single pipeline typically handles steps within one repository or one product: checking source code, building, testing, packaging, and deploying. Multi-pipeline orchestration emerges when a release flow must trigger or coordinate multiple pipelines that have separate lifecycles.

For example, a product consists of:

- Web frontend in its own repository.
- Backend API in its own repository.
- Database migrations owned by a team.
- Kubernetes infrastructure managed via an IaC repository.
- Shared contract and end-to-end test suites.
- A release pipeline that aggregates compatible artifacts and deploys.

Each pipeline can run independently, yet a complete release needs to know which versions of each component are combined and which conditions permit advancing to the next step.

A conceptual flow:

~~~mermaid
flowchart TD
    A[Release request] --> B[Build frontend]
    A --> C[Build backend]
    A --> D[Validate infrastructure]
    B --> E[Publish frontend artifact]
    C --> F[Publish backend artifact]
    D --> G[Publish infrastructure plan]
    E --> H[Integration and contract tests]
    F --> H
    G --> I[Environment preparation]
    H --> J[Release coordination]
    I --> J
    J --> K[Deploy and verify]
~~~

Orchestration does not have to be a central workflow invoking every job sequentially. It can use reusable workflows, parent-child pipelines, downstream triggers, event buses, or a release service. The choice depends on coupling levels and project autonomy.

## 2. Start from the Problem to Solve

Do not start with the question "which orchestration tool should we use?". Identify the concrete problem in the current workflow.

Signs that may indicate multi-pipeline orchestration is needed:

- A release requires artifacts from multiple repositories.
- Teams want to build and test independently while needing a unified release coordination point.
- Pipelines duplicate the same logic across many projects.
- A contract change needs to trigger checks across relevant consumers.
- Infrastructure and applications follow different release cadences yet must coordinate in sequence.
- A consolidated release record is needed containing exact digests/versions of multiple artifacts.
- Approvals, promotions, or rollbacks are required at a product level spanning multiple services.

Conversely, if a single repository simply runs sequential build-test-deploy steps, adding an orchestrator pipeline may yield no benefit. A clean job graph or a simple reusable workflow may already suffice.

Frame the problem in terms of observable outcomes:

- Reduce wait time between builds and integration tests.
- Prevent deploying backend when frontend contracts are not yet compatible.
- Let service teams release independently while still producing a unified release record.
- Eliminate duplicated build logic across repositories.
- Guarantee only one release modifies the same production environment at a time.

If you cannot state the problem or desired outcome, you do not yet have a sound basis for adding orchestration.

## 3. Distinguishing Splitting Pipelines from Orchestrating Pipelines

Splitting pipelines means reorganizing steps inside a workflow. Multi-pipeline orchestration means coordinating workflows that can start, be tracked, and fail independently.

| Model | Characteristics | When Appropriate |
|---|---|---|
| Single pipeline with multiple jobs | One DAG containing build, test, publish, and deploy | Steps share repository, ownership, and lifecycle |
| Reusable workflow/template | Multiple pipelines invoke a standard process | You want to reuse logic without a separate release coordinator |
| Parent-child pipeline | Parent pipeline spawns child pipelines and aggregates results | One repository has multiple modules or work branches |
| Multi-project/downstream pipeline | One project triggers another project's pipeline | Dependencies exist across repositories or teams |
| Event-driven choreography | Pipelines emit events; other systems decide how to react | Independent services, no controller needed to own the whole flow |
| Central release orchestration | A release controller picks versions, coordinates, and records overall state | Must coordinate multiple artifacts, approvals, and promotions into one release |

Never use multiple pipelines merely to replace one long YAML file. If parts still must deploy together, share secrets, share owners, and cannot run independently, splitting may simply move complexity from config files into inter-workflow communication.

## 4. Evaluating Across Complexity Dimensions

An orchestration decision should examine multiple dimensions simultaneously. No single metric alone proves a system needs multiple pipelines.

| Evaluation Dimension | Question to Answer | Signs of Rising Complexity |
|---|---|---|
| Dependency graph | Which pipeline needs results from which pipeline? | Many dependency branches, fan-in/fan-out, and long chains |
| Ownership | Who owns pipelines, artifacts, and environments? | Multiple teams, permissions, and release cadences |
| Contract | Which inputs/outputs do pipelines exchange? | Unstable payloads, implicit reliance on branches or tags |
| Trigger | What triggers the next pipeline? | Many events, duplicate webhooks, trigger loops, or unclear trigger origins |
| Versioning | How is a compatible artifact set identified? | Moving tags, independent versions, and missing release manifests |
| Failure handling | When one pipeline fails, what do other pipelines do? | Partial success, retries, compensation, and ambiguous states |
| Concurrency | Can two releases run simultaneously? | Contention over environments, registries, migrations, or release pointers |
| Security | Which pipeline is allowed to read secrets and deploy? | Trust boundaries across repositories, runners, projects, and environments |
| Observability | Can an entire release be traced? | Disconnected run IDs, scattered logs, and missing correlation |
| Cost/latency | How much extra time and resources does orchestration add? | Long queues, waiting runners, repeated artifact transfers |

Evaluate against real workflows and document assumptions. A multi-repository system does not automatically require central orchestration; likewise, a monorepo may still benefit from multiple pipelines when modules have independent ownership and lifecycles.

## 5. Draw the Dependency Graph Before Designing Triggers

Before writing workflows, draw a DAG describing necessary relationships. Each node represents a job or pipeline; each edge represents a required input condition or output.

Example:

~~~mermaid
flowchart LR
    A[API source] --> B[Build API]
    B --> C[API artifact]
    D[Web source] --> E[Build Web]
    E --> F[Web artifact]
    C --> G[Contract tests]
    F --> G
    H[Infrastructure source] --> I[Validate IaC]
    I --> J[Infrastructure plan]
    G --> K[Release candidate]
    J --> K
    K --> L[Deploy]
~~~

When inspecting the graph, verify:

- Whether any dependency cycles exist.
- Which nodes genuinely must wait for other nodes.
- Which tasks can run in parallel.
- Whether any node is merely an unnecessary pass-through step.
- Which outputs must be durably stored for downstream pipelines.
- When one node fails, which nodes must stop and which still provide diagnostic value.

If pipeline A triggers B, and B triggers A back upon receiving results, a trigger loop can occur. If multiple branches wait on one aggregator pipeline, explicitly define correlation and timeouts for when a branch fails to report.

Never build a DAG assuming "the earlier pipeline has surely finished by now". Represent that condition via explicit dependencies or event/result contracts.

## 6. Distinguishing Mandatory vs. Optional Dependencies

Not every component in a product must complete for a release to proceed.

Example:

| Dependency | Type | Behavior on Failure |
|---|---|---|
| Backend artifact | Mandatory | Do not create release candidate |
| Frontend contract test | Mandatory if related contract changed | Block promotion |
| Documentation site | Optional depending on product | May warn or release separately |
| Security policy scan | Mandatory per release policy | Block release if gate fails |
| Analytics dashboard | Potentially independent | Does not necessarily block application deploy |
| Database migration | Mandatory if artifact needs new schema | Do not deploy dependent code before migration succeeds |

Clear classification prevents an unimportant secondary pipeline from blocking the entire release. Conversely, never mark a mandatory dependency as optional merely to keep pipelines moving.

Each dependency must specify pass, fail, timeout, and missing-result conditions. "Result not received yet" is never equivalent to "succeeded".

## 7. Choosing an Orchestration Model Matched to Coupling

Models range from simple to complex:

### 7.1. Single Pipeline with Multiple Jobs

This is the simplest option when steps share a repository and ownership. A DAG within one workflow usually suffices to express dependencies, concurrency, and outputs.

Pros:

- One overall run ID.
- Easy to inspect logs and statuses.
- No need to pass outputs through external events.
- Few cross-pipeline contracts.

Limitations include large workflows, access permissions and schedules tied to one repository, and difficulty letting other teams manage parts independently.

### 7.2. Reusable Workflows or Pipeline Templates

Used when multiple projects share build, scan, sign, or deploy workflows. The called workflow accepts explicit inputs and returns outputs per contract.

GitHub Actions reusable workflow example:

~~~yaml
name: Build service

on:
  workflow_call:
    inputs:
      java-version:
        required: true
        type: string
    outputs:
      artifact-digest:
        description: Digest of the published artifact
        value: ${{ jobs.build.outputs.digest }}

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.publish.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ inputs.java-version }}
      - name: Build
        run: ./mvnw --batch-mode verify
      - id: publish
        name: Publish artifact
        run: |
          digest="$(./scripts/publish-artifact.sh)"
          echo "digest=$digest" >> "$GITHUB_OUTPUT"
~~~

Caller workflow:

~~~yaml
jobs:
  build-api:
    uses: ./.github/workflows/build-service.yml
    permissions:
      contents: read
      packages: write
    with:
      java-version: '21'
~~~

This example illustrates an input/output contract. The publish script must write only the registry-confirmed digest to stdout; diagnostic logs should go to stderr. Permissions in the called workflow cannot exceed what the caller grants. Real-world workflows need least-privilege permissions, explicit secret inheritance, and pinned actions per organization policy. When calling a reusable workflow from another repository, reference a trusted, immutable ref per policy rather than a moving branch. Reusable workflows share logic, but are not by themselves a release orchestrator.

### 7.3. Parent-Child or Downstream Pipelines

Used when one pipeline must trigger other pipelines and wait for outcomes. This model works well for multi-module monorepos or repositories with direct dependencies.

Define:

- Does the parent wait for the child to finish?
- How does the child return results?
- How does the parent handle child failures, cancellations, and timeouts?
- Who is allowed to trigger the child?
- Can events be redelivered?
- Can the child also run standalone?

A parent should never fire a trigger and assume the child succeeded. Require a run identity and a way to read final status.

### 7.4. Event-Driven Choreography

One pipeline emits an event such as `ArtifactPublished`; other consumers subscribe to the event and perform their own work. This reduces direct coupling across repositories.

Pros:

- Producers do not need to know every consumer.
- Teams can evolve pipelines independently.
- Easy to add new consumers when event contracts are stable.

Limitations:

- Hard to see the overall status of an entire release.
- Events can arrive delayed, duplicated, or out of order.
- Requires deduplication, correlation IDs, retries, and dead-letter handling.
- Investigations must trace across multiple systems.

Choreography fits when services are genuinely independent. If a release must wait for all components to pass before promoting through a central gate, a coordinator can track state more cleanly.

### 7.5. Central Release Orchestration

A release controller receives release requests, pins the artifact set, checks policies, awaits approvals, coordinates deployments, and records the release record.

It fits when multiple components must be released as one unified product. However, it also introduces another critical system that must be operated, secured, upgraded, and recovered.

Build one only when simpler workflows cannot meet needs for consolidated status, approvals, promotions, or auditing.

## 8. Defining Contracts Between Pipelines

Pipelines should not depend on internal details of other pipelines. They need a contract clearly specifying inputs, outputs, statuses, and versions.

A contract can include:

| Field | Meaning |
|---|---|
| Event type | Event kind, e.g., `ArtifactPublished` |
| Schema version | Payload structure version |
| Producer | Repository/project and pipeline emitting the event |
| Run identity | Workflow run ID and attempt |
| Source revision | Commit SHA or immutable tag |
| Artifact coordinate | Registry, package, version, digest |
| Provenance | Build origin evidence |
| Target | Environment or release channel, if applicable |
| Correlation ID | Links steps within the same release |
| Idempotency key | Identifies duplicate requests |
| Result/status | Succeeded, failed, canceled, or unknown |

Example event:

~~~json
{
  "eventType": "ArtifactPublished",
  "schemaVersion": 1,
  "producer": {
    "repository": "org/payments-api",
    "runId": "8421",
    "attempt": 1
  },
  "source": {
    "commit": "a1b2c3d4"
  },
  "artifact": {
    "name": "payments-api",
    "version": "2.8.1",
    "digest": "sha256:0123456789abcdef..."
  },
  "release": {
    "correlationId": "release-2026-11-18-001",
    "idempotencyKey": "payments-api:2.8.1"
  }
}
~~~

This payload is illustrative. Never place secrets inside events. Events should carry references and digests; consumers fetch artifacts from registries using authorized identities.

Contracts need compatibility rules for adding, modifying, or removing fields. Consumers must not break merely because a producer adds a new optional field. Breaking changes require a new schema version or a transition period.

## 9. Using Immutable Artifacts to Connect Pipelines

A common mistake is having downstream pipelines check out the latest branch and rebuild, rather than consuming the artifact produced by the upstream pipeline. When that happens, releases no longer guarantee which exact build was tested.

Follow these principles:

1. The source pipeline builds the artifact once.
2. The artifact is published with a version and digest.
3. The test pipeline pulls that exact digest.
4. The release pipeline records the tested digest.
5. The deploy pipeline deploys the exact same digest across environments.
6. Each step records provenance and associated run IDs.

Never rely on branch names or moving tags as the sole contract. If an event says version `2.8.1` while tags can be overwritten, consumers can receive different contents than what was tested.

A release manifest can link multiple artifacts:

~~~yaml
releaseId: payments-suite-2026.11.18.1
components:
  api:
    version: "2.8.1"
    digest: sha256:api...
  web:
    version: "5.4.0"
    digest: sha256:web...
  infrastructure:
    revision: "a1b2c3d4"
    planDigest: sha256:infra...
compatibility:
  apiContract: "v3"
  webRequiresApi: ">=2.8.0"
~~~

Manifests identify the exact set of components combined and deployed. Store them immutably alongside the release record.

## 10. Managing Fan-Out and Fan-In

Fan-out happens when one pipeline triggers multiple child pipelines or consumers. Fan-in happens when one step must aggregate results from multiple branches.

Fan-out examples:

- Building API, web, worker, and migrations in parallel.
- Running tests across multiple runtimes.
- Validating across multiple regions or environments.

Fan-in examples:

- Aggregating contract test results.
- Confirming all artifacts have been published.
- Validating policies across the entire release manifest.
- Awaiting approvals before promotion.

Fan-out increases concurrency and can overload runners or registries. Fan-in creates a synchronization point where one slow pipeline can delay the entire release.

Design for:

- Concurrency limits on running jobs.
- Per-branch timeouts.
- Explicit statuses for success, failure, canceled, and missing.
- Rules for handling optional branches.
- Aggregating reports even when some branches fail.
- Blocking promotion when mandatory dependencies have not passed.

Never use a fixed sleep interval to wait for child pipelines. Wait on identifiable statuses or receive callbacks/events carrying correlation IDs.

## 11. Avoiding Trigger Loops and Implicit Dependencies

Trigger loops can occur when:

- Pipeline A publishes an artifact, emitting an event that triggers B.
- Pipeline B updates a file or tag, generating an event that triggers A.
- A publishes again or emits a new event.

Ways to reduce risk:

- Distinguish event sources and event types.
- Do not trigger publishing when a commit only modifies generated files.
- Use idempotency keys to discard duplicate requests.
- Cap trigger counts per release correlation.
- Separate automation branches/tags from source branches.
- Verify the actor and token type creating a commit.
- Record trigger causes in run metadata.

Implicit dependencies are equally dangerous. For instance, a deploy pipeline pulling an image tagged `latest` assuming "the build pipeline usually runs first". Without an explicit contract or dependency, actual order can shift under queuing, retries, or manual runs.

Every mandatory dependency needs explicit inputs/outputs and a way to verify its result.

## 12. Handling Failures, Retries, and Partial Success

Across multiple pipelines, part of the work can complete while another part fails. For example, API and web published successfully, but migration validation failed. The release controller must recognize that produced artifacts still exist, yet have not been promoted.

Define:

- Does a failure halt the entire release?
- Which pipelines can be rerun independently?
- Does a retry create a new artifact/version or reuse the existing digest?
- Are duplicate events deduplicated?
- If a pipeline timed out yet side effects may have completed, where is truth checked?
- Are compensating or rollback steps required?
- Are partial artifacts kept for debugging or cleaned up by policy?

Retries fit transient failures only and must be bounded. For validation errors or version conflicts, retrying with the same inputs rarely resolves the issue.

Never assume rolling back one pipeline automatically rolls back all other pipelines. When multiple services have deployed, recovery may require specific ordering and may use roll-forward rather than simultaneous rollbacks.

## 13. Coordinating Concurrency and Shared Environments

Independent pipelines can still contend for the same resources:

- Two releases deploying the same service to production simultaneously.
- Two migrations modifying the same schema.
- Two pipelines updating the same channel pointer or tag.
- Multiple test runs writing to a shared database.
- Two workflows applying the same Terraform state.

Define resource-scoped lock keys:

~~~text
deploy:production:payments-api
migration:production:payments-db
publish:registry.example.com/payments-api:2.8.1
terraform:production:network-state
~~~

Never use a single global lock when independent resources can proceed in parallel. Never key locks by run ID because every run gets a different key and fails to prevent contention.

For distributed locks, require an owner, a lease/TTL, and fencing mechanisms to stop stale workers from writing after losing the lock. Side-effecting operations should be idempotent or conditional so retries remain safe.

## 14. Security Boundaries Between Repositories and Pipelines

Each pipeline can run with different tokens, runners, and permissions. When pipeline A triggers pipeline B, verify who is authorized to send triggers and which data B can trust.

Principles:

- Use tokens with least privilege and appropriate lifetimes.
- Prefer OIDC/workload identities for cloud access where supported by the platform.
- Never pass secrets in event payloads or artifact metadata.
- Consumers authenticate events themselves and verify allowed producers.
- Never trust a branch, repository, or actor solely because its name appears in a payload.
- Scope deployment permissions by environment and resource.
- Separate build, publish, approve, and deploy permissions where needed.
- Never allow pull requests from forks to access production secrets.
- Audit triggers and privileged actions.

If a central pipeline holds permissions to deploy every service, it becomes a massive trust boundary. A bug or compromise in the coordinator could impact many projects. Minimize privileges and partition scopes by environment or product domain.

## 15. Tracing a Release Across Multiple Pipelines

When a release spans multiple repositories, individual pipeline run IDs are not enough to connect them. Establish a shared correlation ID or release ID while retaining individual run IDs for each producer/consumer.

A release record should capture:

- Release ID and correlation ID.
- Source commit of each component.
- Artifact version and digest.
- Pipeline run ID, attempt, and producer.
- Contract test and security gate results.
- Approver identity and timestamp.
- Target environment and deployment revision.
- Post-deployment validation results.
- Rollback/roll-forward events, if any.

Relationships can be modeled as:

~~~mermaid
flowchart LR
    A[Release ID] --> B[API run ID]
    A --> C[Web run ID]
    A --> D[Infra run ID]
    B --> E[API digest]
    C --> F[Web digest]
    D --> G[Infra revision]
    E --> H[Deployment record]
    F --> H
    G --> H
    H --> I[Post-deploy evidence]
~~~

Without a correlation ID, investigations have to hunt across workflows by timestamps and tag names, making it easy to mislink overlapping runs.

## 16. Evaluating Costs and Benefits

Multi-pipeline orchestration carries both direct and indirect costs.

Direct costs:

- Runner minutes and queue wait times.
- Artifact storage and network transfer.
- Event delivery, queues, or release controllers.
- Monitoring, logging, and audit storage.
- Operating integrations and credentials.

Coordination costs:

- Designing and maintaining contracts.
- Handling schema evolution.
- Investigating cross-repository failures.
- Managing permissions across teams.
- Handling retries, duplicates, and partial successes.
- On-call support for coordinators or event infrastructure.

Benefits can include:

- Teams releasing independently.
- Parallel builds/tests reducing wait times.
- Reuse of standardized workflows.
- Better fault and privilege isolation.
- Unified release records.
- Clear promotions and approvals.
- Easier scaling to more services once contracts stabilize.

Measure before and after changes: lead time, queue time, pipeline duration, retry rate, duplicate trigger count, investigation time, and failed deployment rate. Never judge success solely by whether the number of workflows decreased or increased.

## 17. Decision Matrix: Should You Add Orchestration?

Use the following qualitative matrix to discuss with teams:

| Dimension | Separate Orchestration Not Yet Needed | Orchestration Likely Warranted |
|---|---|---|
| Repository | One repo, or parts change together | Multiple repos with separate release lifecycles |
| Ownership | One team owns everything | Multiple teams with distinct permissions and release schedules |
| Dependency | Simple job chain | Multiple branches, fan-in/fan-out, or cross-project dependencies |
| Artifact | One primary artifact | Multiple artifacts must be locked into a release |
| Approval | One simple gate | Per-component or per-environment approvals/promotions |
| Failure | One overall pass/fail outcome | Partial success, retries, and compensation must be managed |
| Traceability | One run ID suffices | Need a release ID linking multiple runs |
| Security | Shared trust boundary | Must separate producer/consumer privileges |
| Scale | Few pipelines, infrequent changes | Many services and high release frequency |

If most criteria fall in the left column, keep a single pipeline or use reusable workflows. If many fall in the right column and are causing measurable pain, trial a narrowly scoped orchestration setup.

Do not mechanically add up points and pick an arbitrary threshold to decide. The matrix is a tool for asking questions and clarifying trade-offs; a single severe security or consistency risk can outweigh many other criteria.

## 18. Signs of Over-Engineering

You may be over-building orchestration if:

- A release controller merely forwards commands between two workflows with no logic.
- Multiple layers of workflows call each other without creating clear ownership boundaries.
- Every job must wait on a central coordinator even when tasks could run independently.
- Event payloads carry large amounts of internal data instead of stable references.
- A minor fix forces editing multiple repositories just to update contracts.
- Retries and states are reimplemented inconsistently at each layer without shared rules.
- Nobody understands the complete current state of a release.
- The coordinator holds overly broad privileges just to reduce configuration steps.
- Investigation time exceeds the time saved by parallelism.
- The team maintains multiple queues, databases, and services for a workflow that rarely changes.

If orchestration does not yield clearer autonomy, reusability, or release control, consider simplifying.

## 19. Step-by-Step Adoption Roadmap

You do not need to migrate the entire system to multi-project orchestration all at once. Adopt incrementally:

1. **Document current state:** map existing pipelines and dependency graphs; measure duration, queues, and failures.
2. **Pick one pain point:** e.g., needing to coordinate API and web before release.
3. **Define contracts:** inputs, outputs, artifact digests, event schemas, and correlation IDs.
4. **Choose the simplest model:** reusable workflow, parent-child, or event-driven depending on needs.
5. **Pilot in staging or on one service:** keep the old process as a reference fallback during transition.
6. **Test failure modes:** duplicate events, timeouts, partial successes, cancellations, retries, and concurrency.
7. **Add security and auditing:** identities, least privilege, secret scoping, and approvals.
8. **Measure results:** compare lead time, cost, reliability, and debuggability.
9. **Expand selectively:** scale out only once contracts and ownership are clear.
10. **Retire legacy paths:** once the new flow is stable and release records are complete.

Each step should have completion criteria. Avoid running two trigger mechanisms side-by-side long-term without a rule defining which source is authoritative.

## 20. Checklist Before Adding Multi-Pipeline Orchestration

Before designing or implementing orchestration, verify:

- [ ] Current problems are described in terms of measurable outcomes.
- [ ] You verified whether a single pipeline or reusable workflow is sufficient.
- [ ] The DAG is drawn and mandatory/optional dependencies are identified.
- [ ] No trigger loops or implicit dependencies exist.
- [ ] Each pipeline has an explicit owner and responsibility boundary.
- [ ] Input/output contracts have schema versions and compatibility rules.
- [ ] Artifacts are identified by immutable versions and digests.
- [ ] Release manifests accurately link artifacts requiring coordination.
- [ ] Fan-out/fan-in defines timeouts, concurrency limits, and explicit missing states.
- [ ] Duplicate events and retries are handled idempotently.
- [ ] Failures, cancellations, and partial successes have clear rules.
- [ ] Publishing, deploying, and migrations have resource-scoped concurrency controls.
- [ ] Identities and secret scopes are restricted per producer/consumer.
- [ ] Approvals and promotions bind to exact release manifests.
- [ ] Correlation IDs link runs, artifacts, and deployments.
- [ ] Auditing, dashboards, and runbooks exist for cross-pipeline failures.
- [ ] Runner, queue, artifact transfer, and operational costs have been evaluated.
- [ ] A migration, rollback, and legacy-trigger retirement plan is ready.

Multi-pipeline orchestration is an architectural decision, not merely a way of splitting YAML files. When dependencies, ownership, contracts, failure semantics, and trust boundaries become complex enough to cause delays or risk, orchestration delivers clear value. When those needs are not yet present, keeping workflows simple lets teams release faster and with tighter control.
