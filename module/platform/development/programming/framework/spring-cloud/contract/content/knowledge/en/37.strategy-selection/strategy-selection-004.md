# Choosing Where to Store Contracts and the Change Proposal Process

As the number of microservices grows, the question is no longer just **how to write Groovy/YAML contracts**. Teams must decide which repository stores contracts, who owns their content, how consumers propose changes, how producers approve them, and which artifacts CI uses for testing. If each team keeps its own copy of a contract, producer tests and consumer tests can end up running against different definitions. If everything is dumped into one central repository without clear ownership, even a small change may stall waiting on multiple teams with nobody accountable at the end.

With **Spring Cloud Contract**, three questions must be separated:

1. **Where is the contract source managed?** This is the Groovy/YAML source that can be reviewed, version-controlled, and used to generate tests.
2. **Where are stub/generated artifacts distributed?** Consumers typically download the `stubs`-classifier JAR from a Maven repository or configured distribution mechanism for Stub Runner.
3. **How is the change workflow coordinated?** Who proposes, reviews, verifies compatibility, merges, publishes, and notifies consumers?

These three questions are related but not identical. A Maven repository storing `stubs` JARs does not automatically become the place to manage all contract sources and business decisions. A Git repository storing DSL files does not automatically prove the producer implementation satisfies the contract. A contract broker or developer portal, if an organization uses one, is a separate governance/distribution layer; do not confuse it with a mandatory built-in requirement of Spring Cloud Contract.

This article belongs to the **Strategy Selection** chapter of the **SPRING_CLOUD_CONTRACT** module. The module teaches contract testing between producers and consumers over HTTP or messaging, defining behavior with Groovy/YAML DSL, generating producer verification tests, publishing stubs, using Stub Runner, and integrating with CI to catch incompatible API changes. The goal is to pick a storage model suited to ownership and team scale, then design a change proposal process that is verifiable, traceable, and scalable.

## 1. Start by distinguishing three types of data

A Spring Cloud Contract setup typically has at least three layers of data:

| Type | Example | Purpose | Suitable storage |
| --- | --- | --- | --- |
| **Contract source** | `get_paid_order.groovy`, `order-created-v1.yml` | Describes requests, responses, messages, matchers, and scenarios. | Git repository with reviews and history. |
| **Generated tests and mappings** | JUnit/Spock tests, WireMock mappings | Tests the producer and defines stub behavior. | Usually build output; can be packaged into the `stubs` artifact. |
| **Published stub artifact** | `com.acme:order-service:1.4.2:stubs` | Consumers download the exact versioned stubs for Stub Runner. | Maven-compatible artifact repository or configured distribution mechanism. |

In addition, organizations may store **governance metadata**: owners, consumer inventory, compatibility decisions, deprecation dates, approvals, and release provenance. This metadata can live in PRs, CODEOWNERS, catalogs, contract registries, or governance systems; it should not be stuffed arbitrarily into the DSL if it is not part of API behavior.

The **source of truth** must make clear:

- Which contract file is the one reviewed and edited.
- Who has authority to approve behavioral changes.
- Which build generated producer tests/stubs from that source.
- Which artifact consumer tests use.
- Which versions are deployed and still supported.

Never let two copies of the DSL be treated as canonical without an explicit synchronization rule.

## 2. Common storage models

There are five primary models:

1. Contracts stored in the **producer repository**.
2. Contracts **proposed/owned by consumers** in the consumer repository or a dedicated area.
3. Contracts stored in a **central contract repository**.
4. Contracts stored in a **monorepo** alongside services.
5. **Hybrid** model: sources follow ownership, while artifacts and metadata are distributed centrally.

No single model fits every organization. The choice depends on consumer count, release independence, ownership workflows, CI capabilities, and audit requirements.

## 3. Model A: storing contracts in the producer repository

This is the natural default for many Spring Cloud Contract projects. The producer manages the DSL right alongside the code that must implement it:

~~~text
order-service/
├── pom.xml
└── src/
    └── test/
        ├── java/com/acme/orders/contract/
        │   └── BaseContractTest.java
        └── resources/contracts/
            ├── orders/
            │   ├── get-paid-order.groovy
            │   └── order-not-found.groovy
            └── messaging/
                └── order-created-v1.groovy
~~~

The producer team reviews contract changes as part of code changes. The Spring Cloud Contract Maven/Gradle Plugin reads the contracts directory, generates producer tests and mappings, and the build can package mappings into a `stubs`-classifier JAR for consumers.

### Pros

- **Clear ownership:** the team owning the API and implementation reviews together.
- **Atomic changes:** code and contract can merge in a single commit/PR.
- **Producer verification close to code:** generated tests run directly against the implementation.
- **Full history:** Git blame/log shows why the contract changed alongside the code.
- **Convenient releases:** stubs are tied to the producer's version/build.
- **Minimal infrastructure:** no separate contract server is needed just to store DSL files.

### Limitations

- Consumers may **not know a contract changed** without a notification/compatibility workflow.
- Consumer-driven proposals must go through the producer's repository or an authorized PR workflow.
- When many consumers have divergent needs, the producer repo can accumulate many scenarios, making it hard to tell which consumer depends on which.
- The producer may define contracts from its own viewpoint and miss behavior consumers truly need.

### Fits best when

- The producer is the primary owner of the API.
- Consumer teams can review PRs or participate in the change process.
- Consumer count is moderate and releases are well coordinated.
- Contracts and implementations frequently change together.

**Recommendation:** if there are no special requirements, start with producer-owned contracts in the producer repo. It is the simplest model for integrating generated verification and stub packaging. As the organization grows, add a consumer inventory, compatibility tests, and governance before migrating all sources to a separate repo.

## 4. Model B: consumer-driven contracts

In the consumer-driven model, **consumers specify the concrete interactions** they depend on. Consumers describe the required request/response or message behavior; the producer reviews and confirms it can provide that behavior. With Spring Cloud Contract, contract DSL can still generate producer verification tests; the difference lies in **initiation authority and the ownership workflow**.

For example, Billing needs the Order API:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billingReadsPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

This contract expresses Billing's need. The producer must review and confirm:

- Are the endpoint/method/headers supported?
- Do `status`, amount, and currency have the right semantics?
- Is this response actually guaranteed or just incidental data?
- Is Billing asking for behavior tailored solely to itself?
- Will other consumers be affected by adding or changing this behavior?

### Pros

- Consumer requirements are explicit, reducing the risk of producers guessing needs.
- Consumers can proactively propose changes and provide reproducible test cases.
- Contract reviews become discussions about real behavior rather than vague docs.
- Helpful when consumers release independently or one producer serves many teams.

### Limitations

- Multiple consumers can create duplicate or conflicting contracts.
- If every consumer demands bespoke behavior, the producer may end up maintaining overly specialized APIs.
- The producer still needs authority over behavior and implementation feasibility.
- There must be a mechanism to consolidate needs into an authoritative contract source.

**Consumer-driven does not mean consumers unilaterally dictate the API to the producer.** Consumers propose needs with evidence; producer owners confirm the contract can be supported; other consumers are evaluated when changes have broad impact.

### 4.1. Where to store consumer contracts?

Drafts/consumer proposals can live in:

- The consumer's repository, alongside client code.
- A dedicated proposal directory in a central contract repository.
- A pull request against the producer repository.
- A contract registry/portal supporting versioning and approvals.

What is mandatory is **a clear path from proposal to producer-accepted contract**. Never let Stub Runner consume unverified proposals as if they were official producer releases.

## 5. Model C: central contract repository

A central repository storing contracts for multiple services:

~~~text
service-contracts/
├── README.md
├── ownership/
│   ├── order-service.yml
│   └── billing-service.yml
├── order-service/
│   ├── v1/
│   │   ├── http/
│   │   └── messaging/
│   └── v2/
│       └── http/
├── payment-service/
│   └── v1/
└── inventory-service/
    └── v1/
~~~

A central repository can use Git as the contract source, while producer pipelines check out/fetch contracts at a configured commit/tag. Exact integration depends on how the project configures `contractsDirectory`, build plugins, submodules, artifacts, or checkout scripts; **Spring Cloud Contract does not require every organization to use a central repository**.

### Pros

- Easy global visibility into contracts across services.
- Uniform review, ownership, naming, and versioning rules can be enforced.
- Consumer-driven proposals have a shared venue for collaboration.
- Easier to generate consumer inventories and compatibility matrices when metadata is standardized.
- Useful when organizations require centralized audits or governance.

### Limitations

- The central repository can become a bottleneck for every change.
- Producer builds gain an extra dependency on checking out/versioning another repository.
- Harder to keep contract sources and producer code atomically synchronized.
- A platform team must maintain repository structure, permissions, CI, and tooling.
- If write permissions are too broad, one team could modify another service's contract without the owner noticing.

### Fits best when

- Many teams share APIs/events and need shared governance.
- A platform/API enablement team maintains the tooling.
- Consumer-driven proposals require a cross-team workflow.
- The organization already has a catalog/registry/approval process and can integrate it.

**A central repository does not solve ownership by itself.** Each contract still needs a producer owner, consumer stakeholders, and review rules. Without ownership, a central repo merely moves ambiguity from many repos into one big repo.

## 6. Model D: monorepo

When multiple services reside in a single repository:

~~~text
platform/
├── services/
│   ├── order-service/
│   │   ├── src/main/
│   │   └── src/test/resources/contracts/
│   ├── billing-service/
│   │   └── src/test/
│   └── inventory-service/
├── shared-contract-test/
└── pom.xml
~~~

Contracts usually sit next to the producer module. The build can coordinate dependent modules via a reactor or task graph.

### Pros

- One PR can update the producer contract, implementation, and consumer together.
- Easy to run compatibility tests across modules in the same commit.
- No need to synchronize commits across multiple repositories for coordinated changes.
- Easy to apply code owners/path filters and shared build standards.

### Limitations

- Large repos can have slow builds unless affected-module builds are optimized.
- Merge permissions and independent releases must be carefully designed.
- One PR can unintentionally pull changes across many services.
- Artifact versions still need separate management if deployed independently.

**A monorepo does not eliminate the need for artifact versioning.** Consumers on older releases still need stubs matching the corresponding producer version; CI inside a monorepo does not automatically prove every binary running in production has been updated.

## 7. Model E: hybrid — sources by ownership, artifacts distributed centrally

A common practical model in organizations with many services:

~~~mermaid
flowchart TD
    A["Producer repository: canonical DSL"] --> B["Producer CI + Contract Verifier"]
    C["Consumer proposal / PR"] --> A
    B --> D["Immutable stub JAR"]
    D --> E["Maven artifact repository"]
    D --> F["Provenance + compatibility metadata"]
    E --> G["Consumer CI + Stub Runner"]
    F --> H["Catalog / contract registry / portal"]
    G --> I["Consumer test report"]
    H --> I
~~~

In this model:

- **Producer's Git** holds accepted contract sources.
- **Consumers** submit proposals via PRs or an agreed workflow.
- **Producer CI** generates tests, runs verification, and packages stubs.
- **Maven repository** distributes immutable `stubs` JARs.
- **Registry/catalog** can store owners, consumers, deprecations, compatibility decisions, and provenance.

This is often a solid balance: clear producer ownership, consumer participation, standard artifacts for Stub Runner, and holistic metadata for the platform team.

## 8. Contract repository vs. artifact repository vs. contract broker

Three concepts that are easily confused:

| Component | What does it store? | What does it do? | Does it verify the producer automatically? |
| --- | --- | --- | --- |
| **Git contract repository** | Groovy/YAML DSL, review history, ownership files. | Source control and collaboration. | No; requires a producer verification pipeline. |
| **Maven artifact repository** | JAR/POM, `stubs` classifier, version/checksum. | Distributes artifacts to Stub Runner/build tools. | No; only stores published artifacts. |
| **Contract broker/registry** | Contract metadata, consumer/provider relationships, verification results depending on product. | Governance, compatibility visibility, workflows, and reporting. | Depends on platform/integration; not automatic. |

**Spring Cloud Contract supports generating and distributing stubs**, yet does not mandate a central broker to function. An organization can operate effectively with Git + a Maven repository. If an external contract broker/registry is added, clearly define which data is synchronized, what the source of truth is, and how statuses are verified.

Do not use the term `broker` for every Maven repository. A repository serving JARs does not necessarily know which consumers verified against a JAR, nor does it make compatibility decisions on its own.

## 9. Storage model selection matrix

| Criterion | Producer repo | Consumer-driven repo | Central repo | Monorepo | Hybrid |
| --- | --- | --- | --- | --- | --- |
| API ownership | Clear when producer owns | Requires producer acceptance | Requires owner metadata | By module/path | Clear in source, centralized in metadata |
| Consumer proposals | Via PR to producer | Natural | Natural | Same PR or proposal path | Via PR/workflow |
| Code + contract atomicity | High | Low across separate repos | Lower when producer code is separate | High | Source stays close to producer |
| Centralized governance | Medium | Depends on setup | High | Via repo policy | High in metadata |
| Initial operational overhead | Low | Medium | High | Depends on monorepo | Medium |
| Stub distribution | Maven repo | Maven repo after producer verifies | Maven repo | Maven repo or CI artifact | Maven repo |
| Fit for independent teams | Good with PR coordination | Good when CDC is strong | Good when platform team is capable | Depends on structure | Very good with defined workflow |

### Decision hints

- **Few services, clear single producer owner:** start in the producer repository.
- **Consumers have proactive API needs and independent releases:** add a consumer-driven proposal workflow.
- **Many teams/domains with complex audit/ownership:** consider a central metadata/contract repository.
- **Many services sharing release trains or frequent coordinated changes:** a monorepo can simplify reviews.
- **Large organization needing both distributed ownership and central governance:** choose hybrid.

Do not pick a central repository just to “have one place to store everything.” Choose it when staffing, ownership rules, and coordination benefits justify it.

## 10. Who owns the contract?

A contract may be used by many groups, yet there must be **one producer owner ultimately accountable for published behavior**.

| Role | Responsibility |
| --- | --- |
| **Producer owner** | Confirms behavior, implementation, generated tests, and version support. |
| **Consumer owner** | States request/response/message needs, tests clients/listeners, and confirms compatibility. |
| **API/domain owner** | Decides semantics, schema evolution, deprecations, and breaking changes. |
| **Platform/build team** | Maintains plugin versions, artifact repositories, CI templates, and provenance. |
| **Security owner** | Reviews auth, sensitive fields, data exposure, and secret handling when applicable. |
| **Release owner** | Confirms gates, promotion, deployment evidence, and rollback. |

In small teams, one person may hold multiple roles. What matters is that **the decision owner is explicitly named** in PRs and workflows.

### 10.1. Ownership metadata

Ownership files can be stored in Git, for example:

~~~yaml
service: order-service
contractOwner: team-orders
apiOwner: commerce-platform
consumers:
  - billing-service
  - analytics-batch
channels:
  - http
  - messaging
support:
  - api-v1
review:
  requiredProducerApproval: true
  requiredConsumerReviewForBreakingChanges: true
~~~

This is **illustrative governance metadata**, not a Spring Cloud Contract schema. Do not place this file into YAML contracts unless required by the task/project; it can live in a catalog/ownership directory depending on your model.

## 11. Contract change proposal workflow

A well-run change goes through these steps:

1. **State the need:** consumer or producer describes the behavior to add/change and why.
2. **Identify affected consumers:** check consumer inventory, running versions, and owners.
3. **Create proposal:** edit contract DSL or open a draft PR with example request/response/message.
4. **Review semantics:** required fields, types, enums, statuses, errors, headers, auth, ordering, retries, and nullability.
5. **Classify compatibility:** additive, policy-compatible, breaking, or unclear.
6. **Producer acceptance:** owner confirms the behavior can be supplied and how it will be implemented.
7. **Generated verification:** producer tests are generated and run against the implementation.
8. **Consumer verification:** Stub Runner tests run with the new artifact across supported consumers.
9. **Version/publish:** package immutable stubs, record coordinates/checksums/provenance.
10. **Release/migration:** promote/deploy per policy, keep v1 or deprecate on a schedule.
11. **Communicate:** publish release notes, consumer migration steps, and deadlines if any.

~~~mermaid
flowchart TD
    A["Consumer/producer states need"] --> B["Identify owners and affected consumers"]
    B --> C["Contract proposal PR"]
    C --> D["Review semantics + compatibility"]
    D --> E{"Breaking or unclear?"}
    E -->|Yes| F["Design versioning/migration + consumer review"]
    E -->|No| G["Producer acceptance"]
    F --> G
    G --> H["Generate + run producer verification"]
    H --> I{"Producer tests pass?"}
    I -->|No| X["Fix implementation/contract"]
    I -->|Yes| J["Package immutable stubs"]
    J --> K["Consumer Stub Runner matrix"]
    K --> L{"Supported consumers pass?"}
    L -->|No| Y["Block release / migration plan"]
    L -->|Yes| M["Publish/promote + notify consumers"]
~~~

**A contract proposal is not a contract release.** A PR can remain in draft until the producer owner approves and CI verifies the implementation. Never allow consumers to pull draft proposals as official stub versions.

## 12. Choosing contract-first or implementation-first

Both approaches work:

### Contract-first

1. Consumer/producer agree on the contract first.
2. Producer implements according to the contract.
3. Generated tests verify the implementation.
4. Consumer runs Stub Runner with stubs generated from the contract.

Fits best for new APIs, new event schemas, or when multiple teams need alignment before coding.

### Implementation-first

1. Producer changes code within controlled boundaries.
2. Contract is updated to reflect the intended supported behavior.
3. Contract diff is reviewed as an API change.
4. Producer verification and consumer compatibility tests run.
5. Release proceeds according to gates.

Fits best for internal refactorings or existing APIs with established behavior. However, **never write contracts after coding purely to make tests pass**; consumer owners must still confirm semantics.

### Risk-based hybrid

For breaking changes, contract-first with consumer review is usually beneficial. For internal changes that preserve behavior, implementation-first can be faster. When adding optional fields, still verify consumers' unknown-field policies.

## 13. Structure of a good contract proposal

A proposal should answer:

| Item | Content |
| --- | --- |
| Problem | Consumer/business problem to solve. |
| Producer | Service and API/message owner. |
| Consumers | Existing and new consumers affected. |
| Scenario | Specific request, response, or message. |
| Contract DSL | Groovy/YAML files and paths. |
| Semantics | Meaning of fields, units, timezones, enums, nullability. |
| Compatibility | Additive/compatible/breaking/unknown and rationale. |
| Test evidence | Producer generated tests, consumer Stub Runner results. |
| Versioning | Artifact version, API/event version, migration window. |
| Rollout | Producer/consumer deployment order, rollback. |
| Deprecation | Which consumers must migrate, deadline, and owner. |

### 13.1. PR description template

~~~markdown
## Purpose
Describe the consumer need and the behavior to change.

## Producer / API
- Producer:
- Endpoint or destination:
- Contract files:

## Affected consumers
- Consumer:
- Supported version:
- Owner/reviewer:

## Contract changes
- Request/message:
- Response/message:
- Fields/types/headers:
- Error scenarios:

## Compatibility
- [ ] Additive per policy
- [ ] Backward compatible verified
- [ ] Breaking change
- [ ] Unclear, needs further review

## Evidence
- Producer generated tests:
- Consumer Stub Runner matrix:
- Stub coordinates/checksum:

## Release and migration
- Version:
- Rollout order:
- Deprecation date:
- Rollback:
~~~

This is a PR template for teams to adopt. It is not a mandatory file generated by Spring Cloud Contract.

## 14. Reviewing contract diffs by semantics

Do not merely count changed Groovy/YAML lines. Check:

- HTTP method/path/query/headers.
- Status codes and error responses.
- Required/optional/nullable fields.
- JSON types and enum values.
- Units, precision, timezones, and ordering.
- Request validation and authorization.
- Message destination, event type, schema version, key/partition if applicable.
- Retries, idempotency, and delivery semantics if included in the contract.

For example:

**Before**

~~~json
{
  "id": 42,
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

**After**

~~~json
{
  "id": 42,
  "amountMinor": "125000",
  "currency": "VND"
}
~~~

The JSON diff changes only a pair of quotes, yet changes **number to string** and can break typed consumer DTOs. Reviews must catch this as breaking for strict clients.

Conversely, changing JSON object key order or pretty-printing is not necessarily a contract change. Adding an optional field can be additive, though strict deserializers and consumer schema policies must still be checked.

## 15. Compatibility classification

| Change | Common classification | Condition to verify |
| --- | --- | --- |
| Add optional response field | Potentially additive | Do old consumers ignore unknown fields? |
| Add required request field | Usually breaking for old consumers | Do old clients send the field? |
| Remove an in-use response field | Breaking | Consumer inventory and DTO usage. |
| Number to String | Breaking for typed consumers | JSON schemas/DTOs/converters. |
| Add enum value | May break strict enum consumers | Unknown enum policy. |
| Change status 200 to 202 | May break workflow semantics | Do consumers understand async/pending? |
| Change error code/body | Potentially breaking | Error decoders/business mapping. |
| Change endpoint path | Breaking unless old alias/version kept | Routing and consumer migration. |
| Change timezone/units | Potentially severe even with unchanged type | Domain semantics. |
| Add event header/schema version | Depends on consumer policy | Listeners and schema registry. |
| Change destination/topic | Usually breaking | Consumer subscriptions/routing. |
| Change message ordering | Breaking if ordering is guaranteed | Partition/key/sequence semantics. |

**There is no universal rule that “adding a field is always compatible.”** Compatibility is a relationship between the change, consumer behavior, and the organization's schema policy.

## 16. Versioning: contract, service, and stub artifact

Distinguish between:

1. **Service version:** version of the producer application.
2. **Stub artifact version:** Maven version consumers use to download mappings.
3. **API version:** version published to consumers, such as `/api/v1` and `/api/v2`.
4. **Message schema/event version:** version inside payload/headers, if used by the protocol.
5. **Git commit:** identity of contract source and implementation.

For example:

~~~text
Producer:
  com.acme:order-service:1.4.2

Stub artifact:
  com.acme:order-service:1.4.2:stubs

HTTP API:
  /api/v1/orders/{id}

Message:
  eventType = OrderCreated
  schemaVersion = 1

Source:
  Git SHA = <full-commit-sha>
~~~

A `stubs` artifact can be tied to the producer version according to build configuration. When multiple API/event versions are supported concurrently, contract sources must be organized clearly and the build artifact must include the exact published mappings.

**Never use a Git branch name as an immutable artifact version.** Branches move; release versions, checksums, and source SHAs are what make consumer tests reproducible.

## 17. Deprecation and retiring old contracts

When the producer wants to retire API/event v1:

1. Identify the consumer inventory and owners.
2. Announce deprecation and target removal date.
3. Introduce v2 without altering v1 outside agreed guarantees.
4. Provide v2 contracts/stubs and migration notes.
5. Consumers update and run Stub Runner tests against v2.
6. Monitor v1 runtime usage/telemetry.
7. Remove v1 only once supported consumers have migrated or hold approved exemptions.
8. Retain old artifacts/reports per retention policy for historical investigation.

Do not delete old contract sources solely because they are absent from new PRs. Contract history is evidence for past releases and may be needed when reproducing incidents.

## 18. Cross-repository workflow when a consumer proposes a change

Suppose Billing needs a new `paymentReference` field from Order Service.

A clear workflow:

1. Billing creates an issue/proposal stating the business reason, expected type, required/optional status, and consumer fallback.
2. Billing opens a draft PR in the consumer repo or proposal area with a contract example.
3. Order owner reviews semantics, security/data exposure, and impact on other consumers.
4. If accepted, the canonical contract source is updated in the producer repo or central source per policy.
5. Producer implementation is updated.
6. Producer CI generates tests, runs verification, and packages stubs.
7. Consumer CI downloads the new artifact version and runs its real client.
8. Related consumers run the compatibility matrix.
9. Merge/publish/promote per release policy.
10. Billing deploys per migration plan and confirms completion.

**Never merge two cross-repo PRs without a synchronization point.** Use draft PRs, release-candidate artifacts, or coordinated merge windows. What matters is that both producer and consumer know the exact candidate commit/artifact under test.

## 19. Workflow when contracts live in a central repository

If a central repo is the source of truth:

1. Consumer/producer opens a PR in the contract repo.
2. CODEOWNERS/approval rules require producer owner review.
3. PR CI validates DSL parsing, naming, schema/policies, and diff.
4. Producer pipeline fetches the exact approved contract commit/tag.
5. Generated producer tests run against the corresponding implementation commit.
6. Producer publishes the stub artifact tagged with the contract revision.
7. Consumer matrix consumes that artifact.
8. Registry/manifest records the central contract commit, producer SHA, and stub checksum.

Pitfall to avoid: having the producer build pull contracts from a **moving branch head** instead of a pinned commit/tag. Builds must be reproducible: both source code and contract revision must be fixed before execution.

## 20. Workflow when contracts live in the producer repository

A typical PR:

~~~text
PR #482 — Add payment reference to paid order response

Changed:
  - OrderController / response mapper
  - contracts/orders/get-paid-order.groovy
  - BaseContractTest fixture

Required reviews:
  - Team Orders producer owner
  - Billing consumer owner

CI:
  - contract discovery / generation
  - generated producer verification
  - package stubs
  - Billing Stub Runner compatibility

Outputs:
  - producer commit SHA
  - stub artifact version + checksum
  - producer test report
  - consumer test report
~~~

The contract diff is reviewed alongside the implementation diff. If a sensitive field is added, security/data owners also review. If the change is breaking, the PR must include a versioning/migration plan.

## 21. Git policy: branches, CODEOWNERS, and protection

A practical policy:

- Contract sources sit under branch protection just like application code.
- The contracts directory has **CODEOWNERS** pointing to the producer API owner.
- Breaking changes require consumer owner approval.
- PR templates require compatibility classification.
- CI runs parser/generator and producer tests.
- Main/release branches never contain unreviewed contracts.
- Release tags bind to source commits; artifact coordinates are never overwritten.
- Generated sources/outputs are not manually edited if the generator can recreate them.

Illustrative CODEOWNERS example:

~~~text
/src/test/resources/contracts/ @team-orders-api
/src/test/resources/contracts/messaging/ @team-events
~~~

Paths/usernames must match the actual repository and teams. CODEOWNERS enforces review requests, yet **does not replace compatibility analysis** or consumer testing.

## 22. CI checks by repository type

| CI check | Producer repo | Consumer repo | Central contract repo |
| --- | --- | --- | --- |
| DSL parse/validate | Yes | If consumer stores proposals | Yes |
| Generated producer tests | Yes | No | Only if pipeline checks out producer implementation |
| Stub packaging | Yes | No | Not natively |
| Stub Runner tests | Can run consumer matrix | Yes | Can trigger downstream |
| Consumer DTO/business assertions | Not necessarily | Yes | Not natively |
| Ownership/approval | Producer owner | Consumer owner | Producer + consumer owners |
| Compatibility report | Producer release gate | Consumer result | Can aggregate |
| Provenance | Producer SHA/test/stub | Consumer SHA/stub checksum | Contract commit/revision |

**Do not dump every responsibility onto the central repository.** A contract repo can parse and lint DSL, but running producer verification requires the producer application/base tests and a suitable test environment.

## 23. Artifact repositories and immutability policy

The `stubs` JAR is the build output consumed downstream. A sound policy:

- Release coordinates are immutable; never overwrite the same version.
- Snapshots are used only in dev/test with awareness of their mutability.
- Consumers pin explicit versions; never use `latest` for release gates.
- Record the SHA-256 checksum from the actual JAR.
- Retain POMs/metadata and provenance per policy.
- Staging repositories let consumers test before promoting a release.
- Retention is long enough to reproduce older consumer builds.

For example:

~~~text
com.acme:order-service:1.4.2:stubs
SHA-256: <actual-jar-checksum>
Producer Git SHA: <full-commit-sha>
Producer CI run: <run-id>
Contract revision: <git-commit-or-tag>
~~~

Placeholders must be replaced with real values by the pipeline. **A Maven repository distributes bytes; it does not decide whether those bytes match source or passed consumer tests**—provenance must link the steps.

## 24. Is a contract broker/registry necessary?

A contract registry or broker can be helpful if the organization needs to:

- Look up producer/consumer relationships.
- View verification status by version.
- Track compatibility matrices.
- Manage deprecations/consumer migrations.
- Provide a portal and API discovery.
- Integrate approval/notification workflows.

However, it also introduces:

- Infrastructure and operational overhead.
- Identity/permissions/retention management.
- Synchronization across Git sources, artifacts, and verification results.
- Processes for handling stale/inconsistent data.
- Ongoing platform team ownership.

**Spring Cloud Contract does not require deploying a separate contract broker** to use Groovy/YAML DSL, generated tests, stub JARs, and Stub Runner. Only add a registry when governance/visibility problems genuinely call for that solution. If you only need source storage and stub distribution, Git + a Maven repository may suffice.

## 25. Security and access control by storage model

| Asset | Suggested permissions |
| --- | --- |
| Producer contract source | Producer owner write; consumer/platform read; PR approvals per policy. |
| Consumer proposals | Consumer owner write; producer owner review/accept. |
| Central contract repo | CODEOWNERS/path ownership; merge protection; audit. |
| Maven release stubs | CI publisher write; consumer CI read; immutable releases. |
| Staging artifacts | CI publisher write; compatibility jobs read; controlled cleanup. |
| Registry metadata | Owner update; platform maintain; organizational read access. |
| Secrets/credentials | Secret manager/CI identity; never stored in Git/contracts/stubs. |

Contracts are widely shared artifacts, so **never put tokens, passwords, customer PII, or sensitive production payloads** in DSL files. Use synthetic fixtures. When a contract includes an authorization header, use an appropriate matcher/placeholder rather than a real bearer token.

## 26. Common anti-patterns

| Anti-pattern | Consequence | Remedy |
| --- | --- | --- |
| Each consumer keeps its own contract copy with no canonical source | Parties test against different behaviors. | Consolidate proposals into a producer-accepted source. |
| Central repo with no owner | PRs stall or merge with wrong semantics. | CODEOWNERS and producer decision owners. |
| Using Maven repository as a DSL review venue | Lacks diff/review context and ownership. | Keep source in Git; Maven distributes artifacts. |
| Consumers fetch `latest` stubs | Non-reproducible tests. | Pin versions/checksums. |
| Editing mappings inside a JAR after publishing | Artifact no longer matches source/provenance. | Build a new version. |
| Producer tests pass using fake fixtures | Implementation is untested. | Base tests invoke real controllers/publishers. |
| Only producer contract tests exist | Clients/listeners go untested. | Add consumer Stub Runner tests. |
| Only consumer tests using hand-written mocks | Real stub artifacts go untested. | Use Stub Runner and the exact versioned artifact. |
| Contract source on an unpinned branch head | Builds may pull different content across runs. | Pin commit/tag. |
| No consumer inventory recorded | Unknown blast radius. | Maintain owner/consumer metadata and runtime discovery. |
| Deleting v1 as soon as v2 is ready | Breaks older consumers. | Deprecation and expand–migrate–contract. |
| Changing DSL without classifying compatibility | Reviews miss breaking changes. | Contract diff reviews and consumer matrices. |
| Every change requires whole-organization approval | Slow workflow, approval fatigue. | Scope approvals by risk and ownership. |

## 27. Choosing a model by maturity level

An evolutionary path might look like:

**Stage 1 — Team owning one service**

- Store DSL in the producer repo.
- Generate producer tests.
- Publish `stubs` JARs to a Maven repository.
- Consumers use Stub Runner with pinned versions.

**Stage 2 — Multiple consumers**

- Add consumer owners to reviews.
- Maintain a consumer inventory.
- Run a compatibility matrix for supported consumers.
- Use staging artifacts and release notes.

**Stage 3 — Multiple teams/domains**

- Standardize ownership metadata, CODEOWNERS, and proposal templates.
- Optionally create a central contract index/repository for visibility.
- Integrate CI results/provenance.
- Establish unified deprecation and versioning policies.

**Stage 4 — Organization-wide governance**

- Consider a registry/broker or developer portal.
- Automatically aggregate consumer relationships/verification statuses.
- Enforce risk- and domain-based approval policies.
- Audit artifacts, releases, and runtime deployment identities.

There is no need to jump straight to Stage 4. Pick the minimum level that solves current risks, and scale up as coordination costs grow.

## 28. Practice exercise: designing a workflow for Order and Billing

Suppose an organization has Order Service and three consumers: Billing, Analytics Batch, and Notification. Billing needs a new `paymentReference` field in the paid-order response.

### Part A — Choose where to store sources

1. Draw the current repository topology: producer repo, consumer repos, artifact repository, and CI.
2. Identify the producer API owner and each consumer's owner.
3. Choose a model: producer repo, consumer-driven proposal, central repo, monorepo, or hybrid.
4. Write the rationale covering ownership, release independence, governance, operations, and audit.
5. Identify the canonical source and stub artifact storage location.

### Part B — Propose the change

1. Billing opens a proposal stating the reason and how `paymentReference` will be used.
2. Determine whether the field is required or optional, plus type/format/nullability.
3. Determine whether Analytics and Notification are affected.
4. Producer owner reviews security/data exposure and semantics.
5. Classify the change as additive or breaking per consumer policy.
6. Update the canonical contract source via PR.

### Part C — Producer verification

1. Update the Groovy contract in the chosen repository.
2. Update the base test fixture/implementation so the field is present.
3. Run generated producer tests.
4. Test a mutation: remove the field or change its type to verify tests FAIL.
5. Package the new `stubs` JAR version.
6. Record the Git SHA, CI run, report, and checksum.

### Part D — Consumer compatibility

1. Billing CI downloads the new stub version and runs its real client via Stub Runner.
2. Analytics CI runs tests if it depends on the schema.
3. Notification CI confirms behavior is unaffected or marks NOT TESTED if no evidence exists yet.
4. Record the consumer commit, stub coordinates/checksum, and test report.
5. If an older consumer fails, fix the client or establish a migration plan; do not loosen contracts arbitrarily.

### Part E — Release and traceability

1. Publish to a staging repository.
2. Promote only after mandatory gates pass.
3. Build/promote the producer image from the verified source/build.
4. Deploy by image digest.
5. Record the release manifest and deployment revision.
6. Run an incident drill: trace from a trace ID back to the image, producer CI, contract commit, stub checksum, and consumer tests.

**Workshop deliverables:** a short ADR explaining the storage model choice; a sample proposal PR; a compatibility matrix; a release manifest; and CI evidence for producer/consumers.

## 29. Decision checklist

| Question | If the answer is… | Direction to choose |
| --- | --- | --- |
| Is the producer owner clear and the API mostly managed by one team? | Yes | Producer repository is a solid starting point. |
| Do consumers frequently need to propose behavior proactively? | Yes | Add a consumer-driven proposal workflow. |
| Do multiple domains need global visibility into ownership/compatibility? | Yes | A central index/registry can be helpful. |
| Do multiple services change together in the same commit? | Yes | Consider a monorepo. |
| Do teams release independently while needing centralized governance? | Yes | Hybrid: distributed sources, centralized metadata/artifacts. |
| Do you only need to distribute stubs for Stub Runner? | Yes | A Maven artifact repository may suffice. |
| Do you need to know which consumer verified against which stub? | Yes | Store consumer CI results/provenance; consider a registry. |
| Is there nobody to operate a central platform? | Yes | Avoid adding an unowned central service. |

## 30. Self-check questions

1. How do contract sources, generated tests/mappings, and published stub artifacts differ?
2. Why is the producer repository a natural default for Spring Cloud Contract?
3. How do consumer-driven contracts change who initiates and who reviews?
4. Why is a consumer proposal not an official contract release yet?
5. What benefits does a central contract repository provide and what bottlenecks can it create?
6. Does a monorepo eliminate the need to version stub artifacts?
7. How does the hybrid model separate source ownership and artifact distribution?
8. How does a Maven artifact repository differ from a contract broker/registry?
9. Does Spring Cloud Contract mandate a contract broker?
10. Who holds ultimate accountability for producer contract behavior?
11. How does a consumer inventory help compatibility decisions?
12. Why can adding an optional field still break a strict consumer?
13. Which types of changes fit contract-first vs. implementation-first?
14. What information should a proposal PR include for semantic review?
15. What can CODEOWNERS protect and what can it not replace?
16. Why should builds pin a central contract commit/tag?
17. How do stub artifact version, API version, message schema version, and Git SHA differ?
18. Why should `latest` stubs not be used for release gates?
19. What steps should a v1 deprecation process follow?
20. When should a central registry be added instead of using only Git + a Maven repository?
21. Why should untested consumers be recorded as NOT TESTED?
22. What data must be retained to trace from deployment back to contract source and test reports?

**Key takeaway:** **Choosing where to store contracts is a decision about ownership and workflow, not just directory layout.** With Spring Cloud Contract, keep Groovy/YAML sources in a Git location with a clear producer owner; give consumers a path to propose and review behavior; use Contract Verifier to check implementations; package immutable `stubs` JARs for Stub Runner distribution; and store consumer results/provenance so you know who verified which version. The producer repo is usually the simplest starting point; consumer-driven proposals, central governance, monorepos, or hybrid models are added based on topology and maturity. A change should become a contract release only after the owner accepts it, producer verification passes, consumer compatibility is assessed, and versions/artifacts are traceable.
