# Coordinating Artifacts and Contracts Across Multiple Repositories

In a system consisting of multiple services or libraries, a change in one repository can affect how another repository builds, tests, or deploys. Service A might publish a library used by Service B; a producer might change an event schema read by multiple consumers; or frontend and backend might be developed in separate repositories yet need to be compatible upon release.

If each repository only validates its own source code, pipelines can be green in every repo while the overall system still fails. The root cause is often mismatched artifact versions, broken communication contracts, improper release ordering, or downstream pipelines mistakenly testing an unverified latest build.

For multi-project CI/CD, two closely coupled things must be coordinated: **the produced artifacts and the contracts those artifacts must adhere to**. Artifacts need immutable identifiers so other repositories can fetch the exact content. Contracts must be versioned, compatibility-checked, and linked to the corresponding artifact version. This lets repositories evolve independently while still forming a traceable release flow.

## 1. Roles of Producer, Consumer, Artifact, and Contract

In a multi-repository flow, a project can act as a producer in one relationship and a consumer in another.

- **Producer:** a repository that produces an asset used by other projects, such as a package, container image, API, event schema, or configuration set.
- **Consumer:** a repository that uses that asset, calls the API, or reads data according to the contract provided by the producer.
- **Artifact:** a built and packaged output, such as a JAR library, container image, frontend assets, package, or deployment bundle.
- **Contract:** a testable agreement about communication or artifact usage, such as an API schema, event schema, public interface, configuration format, validation rules, or operation semantics.
- **Release metadata:** information identifying the origin of an artifact and its verification process, such as commit, pipeline run, digest, contract version, and test results.

A simple example:

    repository payments-api
        -> build payments-api image
        -> publish artifact and OpenAPI contract
        -> repository checkout-service fetches contract
        -> verify client and contract tests
        -> verify integrated version

Artifacts and contracts can be published together or as two linked packages. What matters is that the consumer knows exactly which contract describes which artifact. If it merely downloads a schema file named `latest`, the consumer cannot prove it is testing the exact interface of the version about to be deployed.

## 2. Defining Boundaries and Dependencies Between Repositories

Before designing pipelines, map out relationships between projects. A dependency can be build-time, test-time, or runtime:

| Relationship | Example | What the Pipeline Must Guarantee |
| --- | --- | --- |
| Build-time | Application depends on a shared library | Fetch the exact package version and checksum |
| Contract-time | Consumer generates client from OpenAPI or Protobuf | Validate schemas and compatibility rules |
| Test-time | Service requires another service to run integration tests | Use a defined test-environment version |
| Runtime | Frontend calls backend, or service A calls service B | Versions can communicate during deployment rollouts |
| Release-time | A group of services must be released in the same train | Coordinate order, conditions, and release state |

Not every relationship requires direct pipeline triggers. A library may simply publish a new package; consumers then update dependencies on a schedule or via pull requests. An API changing a critical contract may need to trigger checks across all supported consumers. Determine which relationships need automated feedback and which only need version tracking.

Model dependencies as a directed graph. If A produces an artifact for B and B produces an artifact for C, the verification order is A, then B, then C. Dependency cycles such as A waiting for B to release while B waits for A can deadlock pipelines or force teams to release multiple projects simultaneously. When a cycle is detected, review module boundaries, extract an independent contract, or establish a clearly versioned integration point.

## 3. Publishing Immutable Artifacts

Consumers must download the exact artifact the producer tested. Therefore, artifacts shared across repositories must have stable identifiers and immutable contents after publishing.

A reliable workflow typically includes these steps:

1. Check out the exact producer commit.
2. Build the artifact once using a version-locked toolchain and dependencies.
3. Run required checks against that artifact.
4. Compute a checksum or digest and store build metadata.
5. Publish the artifact to a controlled registry or repository.
6. Provide consumers with the version and digest to fetch accurately.
7. Promote the exact same verified artifact across environments.

For example, an image tagged `payments-api:2.4.1` can still be overwritten if the registry allows tag reuse. In that case, a consumer pulling this tag at two different times may receive different contents. A digest such as `sha256:...` identifies exact image content and is better suited for pinning an integration or deployment.

Version tags are human-readable and convenient, while digests serve as content-identity proof. Store both: versions for release management, and digests for exact artifact verification.

    producer commit 7fa31c2
        -> build image
        -> image tag 2.4.1
        -> digest sha256:abc...
        -> publish
        -> consumer pin digest sha256:abc...

Do not use moving labels such as `latest`, `stable`, or branch names as the sole identifier for an artifact in an approved release. You can use such labels to discover new versions, but once a version is selected, record its specific version and digest.

## 4. Versioning Contracts

Contracts must be versioned and linked to their corresponding producer and artifact. Depending on the communication mechanism, a contract can be:

- OpenAPI or AsyncAPI for HTTP APIs and asynchronous messaging.
- Protobuf, Avro, or JSON Schema for payloads and events.
- Public APIs or package metadata for shared libraries.
- Database schemas and migration rules for data accessed by multiple services.
- File structures, configuration variables, exit codes, or CLI protocols for internal tools.

Not every contract change requires bumping the major version. Evaluate impact on existing consumers:

| Change | Typical Compatibility | What Needs Verification |
| --- | --- | --- |
| Adding an optional field with a safe default | Usually backward-compatible if consumers ignore unknown fields | Do older consumers accept the new payload? |
| Adding an enum value | May break consumers using closed enums | Do consumers handle unknown values? |
| Removing or renaming a field | Usually breaks older consumers | Have a transition period and usage telemetry been completed? |
| Changing data type or semantics | May break both compile-time and runtime | Contract tests and testing with realistic data |
| Adding a new endpoint or operation | Usually compatible if existing behavior is unchanged | Access permissions, authentication, and new semantics |
| Tightening validation or changing defaults | May break consumers even when surface schema is unchanged | Test against supported requests and payloads |

Semantic Versioning can be helpful for packages or contracts with clear compatibility rules: patch for compatible fixes, minor for compatible additions, major for breaking changes. However, do not rely on version numbers alone. A minor syntactic change can still break consumers if semantics shift; conversely, a major version does not necessarily force all consumers to migrate on the same day if the system supports multiple versions in parallel.

For APIs or events, evaluate both read-side and write-side compatibility. A new consumer may read old payloads, while an old producer might not handle new payloads. In event systems, schema registries often support backward, forward, or full compatibility policies; teams must choose the policy matching their deployment order and message retention period.

## 5. Contract Testing Between Producers and Consumers

Producer unit tests prove internal logic works, but do not prove consumers use the API correctly. Consumer integration tests can also pass green if they rely on mocks that fail to reflect the real interface. Contract tests verify the boundary between two projects.

There are two common verification approaches:

- **Provider verification:** the producer verifies that the actual API or schema version satisfies published contracts and supported consumers.
- **Consumer-driven contract tests:** the consumer describes the interactions it relies on; the producer runs verification to ensure it does not break those expectations.

A basic workflow:

1. The consumer creates or updates contract tests from the requests, responses, and behaviors it uses.
2. The contract is published as a versioned artifact linked to the consumer's commit.
3. The producer fetches active contracts of supported consumers.
4. The producer runs verification against its candidate build.
5. Verification results are stored alongside the producer version and contract.
6. The consumer upgrades its dependency or deploys only when contract and related checks pass.

Contract tests do not replace all integration tests. They focus on communication agreements and usually run faster than standing up the entire system. Integration or end-to-end tests are still needed to verify authentication, networking, databases, environment configuration, and multi-component behavior.

To avoid testing an obsolete set of consumers, define a contract lifecycle policy: who owns the contract, which consumers are active, when contracts expire, and under what conditions support can be retired. Do not delete a contract merely because a repository has no recent builds; it may be a consumer deployed on a schedule or in a separate environment.

## 6. Designing Producer and Consumer Pipeline Flows

A common pattern is for the producer to build and publish the artifact first, then trigger consumer pipelines with immutable version information.

For example, a downstream trigger payload can carry these fields:

    event_type: artifact_published
    producer: payments-api
    producer_commit: 7fa31c2
    artifact:
      name: payments-api
      version: 2.4.1
      digest: sha256:abc...
    contract:
      name: payments-openapi
      version: 2.4.1
      digest: sha256:def...
    producer_pipeline_run: ci-1842

Consumers use this event to fetch the exact artifact and contract, run compatibility checks, build the application with the pinned dependency, and record results. Events should not pass only a branch name or the keyword `latest`, because downstream jobs might run later and receive a different version than the one that triggered them.

High-level flow diagram:

    Producer repository
        | checkout commit
        v
    Build + unit test + provider contract verification
        |
        v
    Publish immutable artifact + contract + metadata
        |
        v
    Emit artifact_published event
        |
        +--------------------+
        |                    |
        v                    v
    Consumer A CI         Consumer B CI
        |                    |
        v                    v
    Pin digest + test     Pin digest + test
        |                    |
        +---------+----------+
                  |
                  v
          Integration status
                  |
                  v
          Release decision

If a producer has multiple consumers, you can fan out events so each consumer tests independently. When a release requires all critical consumers to pass, a fan-in step aggregates statuses. If a consumer is outside the scope of the current release, policy may mark it optional, but this decision must include a rationale and be recorded in release metadata.

## 7. Choosing the Right Orchestration Model

There are two main models, which can be combined within the same system.

### Central Orchestration

An orchestrator pipeline knows the dependency graph and invokes pipelines or jobs in order. This model fits when a release must coordinate multiple repositories, has shared approval gates, or must guarantee a set of services is verified together.

Advantages include end-to-end visibility and a single place to aggregate results. Disadvantages are that the orchestrator can become a concentration of privilege, a bottleneck, or a home for overly specialized logic. Keep dependency configuration explicit, break pipelines into reusable steps, and avoid putting every repository's build details inside the orchestrator.

### Event-Driven Orchestration

The producer publishes an artifact or contract and emits an event. Consumers subscribe to the event and decide independently which checks to run. This model fits when repositories release independently and multiple consumers do not need to wait on one another.

Advantages include reduced direct coupling between pipelines and easy fan-out scaling. Disadvantages include distributed release state, events arriving late or duplicated, and difficulty knowing when all critical consumers have completed verification.

With an event-driven model, consumers must handle events idempotently: redelivering the same event must not create duplicate releases or status updates. Use an event ID or a composite key of producer, artifact digest, and consumer version to identify a single integration attempt.

### Combining Both Models

A system often uses events to announce new artifacts, then uses an orchestrator or status aggregator to track mandatory consumers. This hybrid approach preserves repository autonomy while still providing a unified release decision when needed.

Never let pipeline A wait on B, B wait on C, and C wait back on A. Clearly define which step is publishing, which is verification, and which is the release gate. Each trigger must carry explicit versions so it can complete independently and remain traceable.

## 8. Managing the Dependency Graph and Release Order

Build order and deployment order are not always identical. Builds can run in parallel if they only rely on already-published contracts. Deployments may need sequencing if a consumer requires a new endpoint or schema to exist first.

For example, when the backend adds an optional response field, you can deploy the backend first and update the frontend later. When the backend removes an old field, you must deploy the frontend stopping its use of that field first, verify via telemetry that old requests are gone, and only then remove the field in the backend. This is a multi-step transition, not a simultaneous version swap.

For databases shared across multiple services, apply the expand-and-contract strategy:

1. Expand: add new columns or structures in a way still compatible with old application versions.
2. Deploy: release applications capable of reading/writing the new structure during the transition period.
3. Migrate: backfill/transform data and verify results.
4. Contract: only after all consumers have switched over and stopped accessing the old structure, remove the old part.

The dependency graph must capture both version constraints and rollout ordering. Topological order of the build graph alone is insufficient when runtime requires phased compatibility.

## 9. Attaching Artifacts, Contracts, and Evidence to a Release Manifest

A release manifest brings together the components of an integration pass. It shows which commits built the system, which artifacts and contracts were used, and what verification results were produced.

Illustrative example:

    release_id: platform-2026.11.18-rc2
    components:
      - repository: payments-api
        commit: 7fa31c2
        artifact: registry.example/payments-api@sha256:abc...
        version: 2.4.1
        contract: payments-openapi@2.4.1
        provider_verification: passed
      - repository: checkout-service
        commit: 18bd902
        artifact: registry.example/checkout-service@sha256:789...
        version: 5.8.0
        consumer_verification: passed
    integration:
      contract_suite: passed
      smoke_test: pending

Manifests must be generated from actual pipeline data and stored alongside the release record. Never manually fill in unverified values. When smoke tests or approvals complete, append the corresponding results via the system's release management mechanism.

A manifest helps answer:

- Which version of each service is included in the release?
- Do artifacts match the exact digests that were built and tested?
- Which contracts were used to verify compatibility?
- Which consumers verified successfully and which remain pending or failed?
- Which commits and pipeline runs produced that evidence?
- If a rollback is needed, what was the previous artifact set?

For systems with high traceability requirements, you can attach SBOMs, build provenance, artifact signatures, vulnerability scan results, and the identity of the publishing workflow. Bind this evidence to the digest so it cannot become detached from the actual artifact content.

## 10. Protecting Access Across Repositories

Multi-repository pipelines frequently read packages, publish artifacts, fetch contracts, or trigger workflows in other projects. This is a security boundary that must be designed explicitly.

- Grant least-privilege permissions to each workflow: a consumer that only reads artifacts should not have permission to write or delete packages.
- Use short-lived tokens or workload/OIDC identities where supported by the platform, rather than storing a broad personal token across multiple repositories.
- Separate producer publishing permissions from production deployment permissions.
- Never pass secrets via event payloads, logs, public artifacts, or command-line arguments that could be logged.
- Verify artifact origin and signatures before consumers use them in sensitive releases.
- Do not allow pipelines triggered by untrusted pull requests to access release secrets or credentials.
- Audit the repository, workflow identity, artifact digest, and timestamp for publish/consume operations.

When one repository triggers a workflow in another repository, authenticate both the caller's identity and the event payload. Do not treat a repository name or branch name inside a payload as trustworthy proof if the payload can be spoofed.

## 11. Handling Failures, Retries, and Canceling an Integration

In distributed pipelines, a consumer can fail after the producer has already published an artifact. This does not necessarily mean the producer artifact is invalid. Distinguish between:

- Producer build or provider verification failure: the artifact is not yet eligible for release.
- Consumer contract verification failure: likely a contract-breaking change or the consumer is using an outdated contract.
- Consumer build failure from an internal bug: determine whether the error relates to the new dependency.
- Downstream infrastructure unavailable: retry the verification step under a bounded retry policy.
- Release aggregator has not received all results: status must remain pending or incomplete, never assumed successful.

Each integration needs a stable correlation ID or release ID to link logs from producer to consumer. When retrying an event, keep the same logical operation ID and ensure consumers do not create duplicate releases. If a consumer fails, preserve artifacts and metadata for investigation; do not delete or overwrite already-published artifacts.

If a release is canceled, record the `canceled` status along with the reason and any already-deployed components. Canceling an orchestrator pipeline does not automatically revert completed deployments. Rollback actions must be explicit steps with their own status and verification.

## 12. Rolling Back When Multiple Projects Have Been Deployed

Rolling back in a multi-repository system is more complex than rolling back a single application because versions may have changed compatibility relationships.

A good release manifest helps identify the exact previous artifact set. However, before rolling back, verify:

1. Can the older version of each service still communicate with currently running services?
2. Were database schemas or events migrated in a reversible manner?
3. Do old artifacts still exist, can their digests still be verified, and do runtime configs still match?
4. Will rolling back one service break a contract or endpoint another consumer is already using?
5. Should you roll forward with a fix instead of reverting the entire release?

If a database change was destructive or new events have already been emitted, a simple binary rollback may be unsafe. You may need a forward-compatible version, compensating migrations, or a roll-forward. Rollback policies must be grounded in data state and compatibility relationships, not solely on previous version tags.

After a rollback or roll-forward, re-run contract tests and smoke tests across the affected service set. Record the release ID, actual running digests, and verification results so release history accurately reflects system state.

## 13. Common Coordination Pitfalls

| Practice | Consequence | Fix |
| --- | --- | --- |
| Consumers fetch artifacts using `latest` tag | May receive different contents than tested | Pin versions and digests in manifests |
| Testing only within each repository | Misses broken contracts between producer and consumer | Add provider verification and cross-repo contract tests |
| Sharing schemas by manual copying | Schema copies gradually drift apart | Publish versioned contracts with checksums |
| Triggering downstream by branch name only | Delayed pipelines may pick up a different commit | Pass explicit commit, artifact digest, and contract version |
| Each consumer guesses producer version | Hard to reproduce and unclear what a release uses | Use dependency pinning or release manifests |
| Mutual triggers without a dependency graph | Creates loops or infinite pipeline runs | Design a DAG, event IDs, and loop-prevention rules |
| Giving all workflows broad tokens | Increases blast radius if credentials leak | Use least privilege and short-lived credentials |
| Treating an unresponsive consumer as passing | Release may lack compatibility evidence | Keep status pending/incomplete until criteria are met |
| Rolling back individual services without checking contracts | Remaining services may become incompatible | Check version matrix and data state before rollback |

## 14. Example: Releasing a Shared Library and Two Consumers

Suppose repository `pricing-core` publishes a Java library used by `checkout-service` and `invoice-service`. The producer creates package `pricing-core:3.2.0` along with metadata and a contract describing its public API. Both consumers have version-pinned dependencies.

When the producer changes:

1. The producer pipeline builds the package from a specific commit, runs unit tests, and checks the public API.
2. The pipeline publishes the immutable package with checksum and source metadata.
3. A release event carrying version, checksum, commit, and pipeline run is sent to both consumers.
4. Each consumer creates a branch or pull request updating its dependency, then runs compilation, unit tests, and relevant contract/integration tests.
5. Statuses from both consumers are aggregated. If `checkout-service` passes while `invoice-service` fails, the overall release is allowed to proceed only if policy declares `invoice-service` out of scope or an approved compatibility plan exists.
6. Once release criteria pass, the release manifest records package digests and versions for all three repositories.

If the producer discovers a bug after publishing, the team can publish a new patch version and emit a new event. Do not overwrite package `3.2.0` because consumers may already have downloaded and tested against the original checksum. History must retain both artifacts so prior integrations remain reproducible.

## 15. Checklist for Designing Multi-Repository Pipelines

Before putting a coordinated workflow into production, verify:

- [ ] Producers, consumers, and dependency types between each repository are identified.
- [ ] The dependency graph has no unhandled cycles and has clear build/verify/release ordering.
- [ ] Artifacts are built once, published immutably, and identified by both version and digest.
- [ ] Contracts are versioned, stored with metadata, and linked to corresponding artifacts.
- [ ] Provider verification and contract tests exist for supported consumers.
- [ ] Downstream triggers carry explicit commits, artifact digests, contract versions, and pipeline runs.
- [ ] Events have stable IDs and consumers handle duplicate deliveries safely.
- [ ] The release aggregator clearly distinguishes passed, failed, pending, canceled, and skipped.
- [ ] The release manifest records versions, digests, contracts, and verification evidence for every component.
- [ ] Cross-repository access follows least privilege; secrets are not passed through events or logs.
- [ ] Deployment order and data migration strategies preserve compatibility during transition windows.
- [ ] Rollback is evaluated against the compatibility matrix, data state, and artifact availability.
- [ ] Correlation IDs trace from producer commits to consumers, releases, and deployment environments.

Multi-repository coordination works effectively when each project can build and release independently, yet every integration uses immutable artifacts, versioned contracts, and clear test evidence. Pipelines can then give rapid feedback on changes, catch incompatibilities early, and base release decisions on an exact verified set of components.
