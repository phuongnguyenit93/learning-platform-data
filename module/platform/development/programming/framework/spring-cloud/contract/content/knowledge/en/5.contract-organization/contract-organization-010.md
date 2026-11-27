# Ownership and Change Review in a Contract Repository

## Learning Objectives

In the **Spring Cloud Contract** ecosystem, a contract is an executable specification of communication behavior between a **producer** (the service providing an API or emitting messages) and a **consumer** (the service calling the API or receiving messages). Contracts can be written in **Groovy/YAML DSL**, used to generate producer-side tests and produce stubs for consumers to run with **Stub Runner**.

When multiple teams collaborate, writing a contract is only part of the problem. You also must determine **who owns the contract**, **who can propose and approve changes**, **how to identify affected consumers**, and **which risks CI must block**. This lesson in the **Contract Organization** chapter helps you:

- Distinguish interface ownership, contract proposal rights, approval authority, and verification responsibilities.
- Compare two common storage models: co-located inside the producer repository or hosted in a shared contract repository.
- Establish pull request (PR), code review, branch management, and access-control workflows suited for multiple teams.
- Classify compatible changes versus changes that risk breaking consumers, even when producer contract tests stay green.
- Combine **generated tests**, **stub artifacts**, **Stub Runner**, versioning policies, and CI gates to reduce integration failures.

## 1. Why Does a Contract Repository Need Clear Ownership?

Suppose an ordering system has three services:

- **Inventory Service** is the producer of `GET /api/inventory/{sku}` and the `StockChanged` event.
- **Checkout Service** is a consumer of the inventory API.
- **Recommendation Service** is also a consumer of the inventory API, reading only a few fields.

All three teams can modify their code independently. The Inventory team wants to simplify the response, the Checkout team relies on the old data type to decide order placement, and Recommendation has not upgraded yet. If anyone can edit the DSL and publish a new stub unilaterally, builds may report green while the live system loses compatibility.

A contract repository must answer three questions simultaneously:

1. **Decision:** Who has the authority to commit that the producer will provide a specific behavior?
2. **Impact:** Who depends on that behavior and must be consulted before changing it?
3. **Evidence:** Which checks confirm the producer actually satisfies the contract and the consumer understands the intended stub version?

**Ownership does not mean the right to change everything unilaterally.** The producer is responsible for implementing the interface; the consumer is responsible for specifying and testing what it depends on; cross-team review protects the shared agreement.

## 2. Dividing Responsibilities: Producer, Consumer, and Repository Maintainer

| Role | Can Propose | Primary Responsibility | Must Not Assume Unilaterally |
|---|---|---|---|
| **Producer team** | Endpoints, message structures, bug fixes, compatibility options | Implementing contracts, generated contract tests, publishing stubs, deprecation plans | That consumers are unaffected simply because producer tests pass |
| **Consumer team** | Required fields, error cases, new contract requests, upgrade plans | Testing consumer logic against stubs, confirming dependencies and migration timelines | That the producer can commit to any behavior before assessing feasibility |
| **Contract repo maintainer** | Path conventions, naming rules, PR templates, review workflows | Change control, access permissions, structural consistency, and history | Deciding business semantics on behalf of the API owner |
| **CI/build owner** | Verification rules, artifact publishing, versioning policies | Keeping test generation, stub builds, and release-readiness checks running | That automated tests catch every business-breaking change |
| **Product/API owner** (if separate from producer) | Compatibility policy, version lifecycle, migration decisions | Resolving conflicts across multiple consumers, announcing deprecations | Overriding technical verification results |

A **RACI** matrix can assign responsibilities, where:

- **R – Responsible:** the party doing the work directly.
- **A – Accountable:** the party holding final decision accountability.
- **C – Consulted:** the party asked for input.
- **I – Informed:** the party kept updated.

Example policy for the inventory API:

| Activity | Inventory (producer) | Checkout/Recommendation (consumer) | Repo Maintainer |
|---|---|---|---|
| Propose new behavior | A/R when proactively adding | R when requesting a need | I |
| Confirm field semantics and HTTP status | A/R | C | I |
| Implement and run generated tests | A/R | I | I |
| Test client against candidate stub | C | A/R per consumer | I |
| Approve breaking change and migration schedule | A together with API owner | C, must confirm upgrade plan | C on process |
| Branch protection, PR templates, and review rules | C | C | A/R |

This matrix is an **illustrative assignment example**, not an automatic Spring Cloud Contract setting. In small teams, one person may wear multiple hats; for public interfaces or many consumers, clearer separation is needed. In particular, the process should define **who resolves disputes when a consumer objects to a change** rather than merely adding reviewer names to a PR.

## 3. Choosing Where to Store Contracts: Co-Located with Producer or Separate Contract Repo?

Both organizational models work with Spring Cloud Contract. The main differences lie in ownership, contribution workflow, and how builds locate DSL files.

| Storage Model | Best Suited When | Strengths | What Must Be Controlled |
|---|---|---|---|
| **Inside producer repository** (e.g., `src/test/resources/contracts`) | Producer owns API releases and consumer teams submit PRs to the same repo | Implementation code and contracts evolve in one history; producer runs generated tests conveniently | Consumers need a path to propose/review; prevent producers from overlooking legacy consumer impact |
| **Shared contract repository** | Multiple services/teams want joint contract governance or independent consumer contributions | Centralizes decision history and review policy; makes cross-team interfaces visible | Pipelines must fetch the exact contract revision; producer, stub, and consumer must not drift to mismatched revisions |

### Model A: Contracts Live with the Producer

~~~text
inventory-service/
├── pom.xml
├── src/main/...
├── src/test/java/...
└── src/test/resources/contracts/
    ├── http/
    │   ├── stockAvailable.groovy
    │   ├── stockNotFound.groovy
    │   └── stockInvalidSku.groovy
    └── messaging/
        └── stockChanged.groovy
~~~

The Checkout team can open a PR against `inventory-service` proposing an added `reservedQuantity` field, while the Inventory team reviews feasibility and commitment semantics. Checkout also reviews to confirm the response meets its needs and does not break existing logic.

### Model B: Shared Contract Repository

~~~text
service-contracts/
├── contracts/
│   ├── inventory/
│   │   ├── http/
│   │   │   ├── stockAvailable.groovy
│   │   │   └── stockNotFound.yml
│   │   └── messaging/
│   │       └── stockChanged.groovy
│   └── payment/
│       └── http/
│           └── paymentStatus.groovy
├── docs/
│   └── compatibility-policy.md
└── .github/
    └── CODEOWNERS
~~~

These paths are **illustrative governance conventions**. Spring Cloud Contract does not automatically know which producer owns `contracts/inventory/http/stockAvailable.groovy` merely because the folder is named `inventory`. Builds must be **configured to locate the right contract source and layout**. With an external repository, the producer must check out the exact contract version/revision and generate tests and stubs from that revision; never let two pipelines silently grab whatever happens to be latest at runtime.

Pick one **authoritative source of truth** per interface. If the same endpoint maintains two independent DSL copies in the producer repo and a shared repo, they can diverge and contradict each other. If copying is needed for builds, establish explicit synchronization and source traceability.

## 4. Directory-Based Ownership and Review Rules

In a multi-team repository, per-area owners can be declared via a `CODEOWNERS` file when the Git hosting platform supports it. On GitHub, for example, place it at `.github/CODEOWNERS`:

~~~text
# Example: organization/team names are illustrative only
/contracts/inventory/  @example-org/inventory-team
/contracts/payment/    @example-org/payment-team
/docs/                 @example-org/platform-api
~~~

This routes PRs modifying `inventory` contracts to the right producer team for review. However, **`CODEOWNERS` only assists with reviewer assignment** per platform capabilities; it neither discovers all impacted consumers automatically nor guarantees that both producer and consumer agreed.

Specifically on GitHub:

- Enable appropriate **branch protection/rulesets** requiring code-owner reviews if you want this to be a mandatory gate; the mere presence of `CODEOWNERS` is not enough.
- If a pattern lists multiple owners, do not assume **every** owner must approve by default. Cross-team approval rules must be defined and enforced via additional review/ruleset mechanisms.
- Check pattern ordering and precedence rules in your actual platform; avoid overlapping rules while assuming one reviewer approval suffices.

With contracts co-located inside the producer, most PRs naturally go to the producer team. For multi-consumer APIs, also maintain a **dependency registry**: who uses which endpoint, event, or field, and who to contact when making changes.

Example team-maintained tracking table:

| Interface / Behavior | Producer Owner | Known Consumers | Contact on Change |
|---|---|---|---|
| `GET /api/inventory/{sku}`, field `available` | Inventory | Checkout | Checkout lead |
| `GET /api/inventory/{sku}`, field `quantity` | Inventory | Checkout, Recommendation | Leads of both consumers |
| `StockChanged` event | Inventory | Analytics, Notifications | Leads of Analytics, Notifications |

This registry is **operational metadata**, not fully generated from DSL. Update it whenever a new consumer integrates or an existing consumer stops using an interface. At larger scale, combine an API catalog, telemetry, and integration docs, noting that telemetry only shows partial runtime usage and cannot replace explicit cross-team agreements.

## 5. Lifecycle of a Contract Change via Pull Request

~~~mermaid
flowchart TD
    A["Consumer/producer proposes a need"] --> B["Open PR modifying Groovy/YAML DSL"]
    B --> C["Identify owner and impacted consumers"]
    C --> D["Assess compatibility and transition plan"]
    D --> E["Producer runs generated contract tests"]
    E --> F["Build candidate stub from the same revision"]
    F --> G["Consumers run tests against candidate stub"]
    G --> H{"Review + CI pass?"}
    H -->|No| I["Adjust contract, implementation, or migration"]
    I --> D
    H -->|Yes| J["Approve and merge per policy"]
    J --> K["Build producer, publish versioned stub"]
    K --> L["Consumers upgrade in a controlled rollout"]
~~~

A practical review workflow follows these steps.

### Step 1: Describe the Reason for Change

The PR author states:

- Which business scenario is not yet supported?
- Who uses this interface and how are users impacted?
- Where exactly does the request/response or message change?
- Is this an additive change, a behavioral bug fix, or an incompatible breaking change?
- Must the old interface stay active during a transition period?

Never write merely "refactor JSON" if field names, data types, or semantics are actually changing.

### Step 2: Review Semantics Before Reviewing Syntax

Syntactically valid DSL can still express wrong semantics. The producer team evaluates:

- Can the scenario be implemented consistently?
- Do error statuses, headers, and returned payloads align with API standards?
- Are internal details or sensitive data exposed in bodies or error messages?
- Are matchers too rigid for dynamic data or too loose for critical fields?

The consumer team evaluates:

- Does the contract match what the client actually relies on or will rely on?
- Are JSON/message shapes and data types usable?
- Are there success, empty, or error cases the consumer must handle that are still missing?
- If breaking, where must the client upgrade and by what deadline?

### Step 3: Verify Against Real Code and Stubs

Spring Cloud Contract supports generating **generated contract tests** so producers prove implementations obey contracts. It also produces **stubs** so consumers can test integration logic, typically via **Stub Runner**.

Crucially, both sides must verify **the exact same candidate contract**. If producer tests run against a new commit while consumer tests pull an older stub from an artifact repository, both can appear green while the change actually breaks compatibility.

### Step 4: Record Decisions and Publish Versions

Once review completes, the PR should preserve **rationale, impact scope, compatibility strategy, CI evidence, and approving parties**. After merging, publish stubs only from verified revisions. Protect the main branch, version artifacts cleanly, and communicate upgrade instructions to consumers.

## 6. Classifying Changes Before Approval

Compatibility cannot be concluded simply because new DSL compiles and generates tests cleanly. Examine **what consumers actually depend on**.

| Example Change | Initial Assessment | Review Questions to Ask |
|---|---|---|
| Add optional field `warehouseCode` to JSON response | Potentially compatible | Do consumers ignore unknown fields, or are parsers strict? |
| Change `available` from boolean to string `"yes"/"no"` | High risk, usually breaking | Are consumers deserializing it as a boolean? |
| Change `GET /api/inventory/{sku}` to a new path and drop old path | Breaks old requests | Can an alias or older version be kept? |
| Change `404` to `200` + error body for non-existent SKU | High risk | Do consumers branch on HTTP status codes? |
| Add validation requiring a previously optional header | Potentially breaking | Do existing consumers send this header? |
| Rename internal Java method while keeping request/response identical | Usually contract-neutral | Do generated tests still represent the exact behavior? |
| Change `quantity` from integer to string in `StockChanged` event | High risk | Can subscribers deserialize both old and new events? |
| Add a new enum value in a message | Depends on consumer logic | Do consumers handle unknown enum values safely? |
| Remove or reorder JSON object fields | Removing breaks; key order is usually uncommitted | Did any consumer accidentally depend on undocumented ordering? |

There is no rule saying "**adding fields is always safe**." For consumers using strict decoders, even a new field can cause failures. Conversely, internal producer refactorings can leave the interface completely intact.

### Review Example: Changing Field Type and Name

Currently published contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory for valid SKU'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 12
        )
    }
}
~~~

A PR proposes replacing `available: true` with `availability: 'IN_STOCK'` and removing `available`. The producer can update both its implementation and the new contract so generated tests pass. Yet Checkout, which reads boolean `available`, will stop working.

Three common options should be evaluated:

1. **Preserve compatibility during transition:** producer returns `availability` while still keeping `available`; consumer teams upgrade, then schedule removal of the old field.
2. **Introduce a new interface version:** preserve the old API/message and publish a new API/message version per system policy.
3. **Coordinated simultaneous cutover:** viable only when all affected consumers can deploy together and rollback/compatibility plans have been vetted.

Whichever option is chosen, the PR must state **which contract revision produced the stub**, which consumers tested that version, and the deprecation milestone for old behavior.

## 7. Who Approves a Compatibility-Breaking Change?

An actionable governance rule:

- **Additive changes assessed as compatible:** producer owner approves semantics; CI must run. Affected consumers are notified or consulted according to risk level.
- **Changes removing or altering committed behavior:** producer owner and impacted consumers must agree on a migration plan; the API owner or release authority makes the final call per organizational policy.
- **Changes to repository structure or verification workflow:** repo maintainer approves tooling/convention edits while consulting producers/consumers if build flows are affected.

**Spring Cloud Contract does not enforce human approval policies on its own.** That belongs to Git hosting, branch protection, review policies, and team workflows. CI proves specific technical properties, never replacing human accountability for business semantics.

If a consumer does not respond, never assume silence equals consent to a breaking change. Establish response SLAs and an agreed escalation/decision owner upfront.

## 8. PR Template Helping Reviewers Decide Quickly

A PR modifying contracts should include enough context for non-authors to assess impact:

~~~markdown
## Goal
Checkout needs to distinguish in-stock from temporarily out-of-stock without inferring from quantity.

## Changed Interface
- Producer: Inventory Service
- HTTP: GET /api/inventory/{sku}
- Contract: contracts/inventory/http/stockAvailable.groovy

## Before / After
- Before: available: boolean
- After: add availability: "IN_STOCK" | "OUT_OF_STOCK"
- Keep available during transition period

## Impacted Consumers
- Checkout: tested against candidate stub
- Recommendation: does not read availability yet; parser compatibility checked

## Compatibility and Transition
- Assessment: conditional addition; check consumer strict parsing
- Planned removal of old field: scheduled only after all consumers migrate
- Rollback plan: retain old response if rollout encounters errors

## Verification Evidence
- Producer generated contract tests: PASS
- Candidate stub artifact/revision: <fill actual version/commit>
- Consumer tests with Stub Runner: <fill actual link and status>

## Required Approvals
- Producer owner
- Impacted consumers
- API owner if compatibility/version policy changes
~~~

`PASS` lines in the example are **placeholders to fill with real results**, not actual executed results. Reviews should link to concrete build logs/artifacts or commits rather than generic status text.

When inspecting diffs, highlight edits that affect semantics:

~~~diff
 body(
     sku: 'SKU-101',
-    available: true,
+    availability: 'IN_STOCK',
     quantity: 12
 )
~~~

Such a diff needs review for **removing the old field and introducing the new data type**, even though the snippet is small. In Groovy/YAML DSL, reviewers must also check matchers and request conditions: relaxing a matcher from "digits only" to "any string" weakens bug detection even if the sample body barely changed.

## 9. Managing Contract Versions and Stub Artifacts

Revisions must maintain end-to-end traceability:

~~~mermaid
flowchart LR
    A["Contract Commit/Tag"] --> B["Producer generated tests"]
    B --> C["Verified producer build"]
    C --> D["Versioned stub artifact"]
    D --> E["Consumer test with Stub Runner"]
    E --> F["CI results tied to that version"]
~~~

In Maven projects, stub artifacts are typically published alongside the producer under the `stubs` classifier, such as the illustrative coordinates `com.example:inventory-service:1.4.0:stubs`. Consumers must know **the exact coordinates and version** they tested against.

For a review record to be valuable, it should link:

| Item | What to Record |
|---|---|
| Contract revision | Approved Groovy/YAML DSL commit/tag |
| Producer build | Producer commit where generated contract tests passed |
| Stub artifact | Coordinates, version, and checksum or build ID if available |
| Consumer verification | Which consumer, commit, stub version, and tests ran |
| Release decision | Who approved, when new interface is supported, how long old behavior stays |

Never write merely "tested with latest stub." An alias pointing to latest can shift between CI runs, making failures hard to reproduce. For **release-gating** tests, prefer explicitly pinned stub or candidate artifact versions.

### Release Principles

1. **Publish only verified stubs:** producer generated contract tests must pass on the exact contract revision being published.
2. **Do not overwrite immutable artifacts:** the same stub version should always return identical contents so builds remain reproducible.
3. **Maintain older versions while consumers still depend on them:** especially for breaking changes.
4. **Communicate upgrade paths:** consumers must know when to adopt the new stub and how long legacy behavior remains supported.
5. **Apply a consistent versioning policy:** SemVer or an organizational release scheme helps, though version numbers never replace compatibility review.

When contracts live in a shared repository, the producer should record **the contract repository revision used to generate tests**. If contract and producer repos have independent lifecycles, recording only the producer version may be insufficient to trace the source.

## 10. Controlling Changes with CI

A well-designed pipeline combines repository structure checks and behavioral verification:

| Check Gate | When It Runs | Purpose |
|---|---|---|
| File and review-permission checks | PR opened/updated | Right contract placement, right owners, branch rules respected |
| DSL validation and test generation | Producer PR or contract PR | Catch DSL syntax/config issues breaking test generation |
| Run generated producer tests | Before merge and release | Verify producer implements the target contracts |
| Build candidate stub from PR revision | After producer tests pass | Let consumers test against exact proposed behavior |
| Run consumer tests with Stub Runner | Affected consumers, prioritized by risk | Verify client requests and response parsing against candidate stub |
| Backward-compatibility checks | On changes or releases | Catch removals/edits to fields older consumers still need |
| Release and stub artifact checks | On merge/release | Prevent publishing stubs from wrong revisions or overwriting releases |

A general workflow can be expressed as:

~~~text
Contract PR
    |
    +-- Identify owners, dependent consumers, and change scope
    |
    +-- Parse DSL -> generate tests and stubs
    |
    +-- Run producer generated contract tests
    |       |
    |       +-- FAIL -> block merge/release, investigate contract or implementation
    |
    +-- Produce candidate stub tied to PR commit
    |
    +-- Consumer tests via Stub Runner + candidate stub
    |       |
    |       +-- FAIL -> resolve compatibility or migration plan
    |
    +-- Required approvals -> merge -> publish versioned stub
~~~

This is a **reference workflow**, not a copy-pasteable pipeline file. With Maven, producer builds can run `./mvnw verify` when the plugin is properly configured; with Gradle, invoke the plugin tasks appropriate for your version. In multi-producer/multi-consumer setups, CI can run a targeted test matrix driven by the dependency registry instead of running every service on every small edit.

**Important limitations:**

- Producer generated tests can turn green after **both the contract and producer code changed**, while older consumers still break. Check compatibility against active contracts/stubs in production.
- Consumer tests using stubs only verify consumer logic against the stub, not that the real producer behaves properly. Both sides are required.
- Tests protect only explicitly specified scenarios. Omitting an error code, message type, or critical field leaves a blind spot.
- Reviewer rules, version lifecycles, and deprecation policies **are not automatically enforced by Spring Cloud Contract**.

## 11. Common Governance Mistakes

| Situation | Consequence | How to Fix |
|---|---|---|
| Anyone can edit DSL and merge directly | Unaccountable changes slip in | Enable branch protection and assign interface owners |
| Producer acts as sole owner and skips consumer review | API matches new producer code while breaking old clients | List impacted consumers and enforce review/migration rules |
| Shared repo used, yet producer always pulls latest `main` | Non-reproducible builds, risk of grabbing unstable contracts | Pin contract tag/commit/version |
| Stubs built without running producer generated tests | Stubs may diverge from real implementation | Require producer verification before publishing |
| Reviewers inspect only sample JSON and ignore matchers | Tests become overly loose or brittle | Review request conditions, matchers, status codes, and headers |
| `CODEOWNERS` exists without requiring review | Merges proceed without required approvals | Configure branch protection/rulesets |
| Breaking change disguised as a minor/patch version | Consumers auto-upgrade and break | Assess compatibility and communicate versions clearly |
| No record of which stub version consumer tests used | Release decisions cannot be audited | Record artifact coordinates, version, and commit in PR and CI |
| All tests green so old field deleted immediately | Unlisted or unmigrated consumers fail | Update dependency registry and follow deprecation workflow |

## 12. Practice Scenario: Who Has Merge Authority?

The Inventory team wants to change `GET /api/inventory/{sku}` to return:

~~~json
{
  "sku": "SKU-101",
  "stockStatus": "IN_STOCK",
  "quantity": 12
}
~~~

Previously, the response was:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 12
}
~~~

Checkout reads `available` to allow ordering, whereas Recommendation reads only `quantity`. The Inventory team updates both the Groovy DSL and producer code; producer generated tests all pass. The PR has only one reviewer from Inventory.

Answer these questions before checking the hints:

1. **Is the PR safe to merge?** Not enough evidence. Generated tests only confirm the producer meets the new contract; Checkout may still break because `available` was removed.
2. **Who needs to review?** Inventory confirms semantics and implementation feasibility; Checkout confirms impact and upgrade plan. Recommendation should also verify unknown/missing-field parser tolerance even though it does not read `available`. Maintainers and API owners participate per repository policy.
3. **What is a less disruptive approach?** Keep `available` during transition while adding `stockStatus`; maintain contracts for both new behavior and backward compatibility. For major shifts, consider a new API/version.
4. **What evidence is needed?** Generated tests against the producer candidate; candidate stub tied to the PR revision; Stub Runner test results for affected consumers; recorded version and migration decision.
5. **When can `available` be removed?** Once agreed deprecation criteria are met, dependent consumers have migrated or have compatibility coverage, and review/release steps are completed.

### Short Pre-Approval Checklist

- [ ] Interface name and producer owner are clearly identified.
- [ ] Affected consumers and points of contact have been reviewed.
- [ ] PR accurately explains old behavior, new behavior, and compatibility impact.
- [ ] Success, empty data, error cases, and related messaging have been considered.
- [ ] DSL and matchers were reviewed for both syntax and semantics.
- [ ] Producer generated contract tests ran on the exact revision.
- [ ] Candidate stub was built/published with traceable coordinates.
- [ ] Consumer tests verified the real client against the exact candidate stub.
- [ ] A migration plan and deprecation milestone exist if compatibility breaks.
- [ ] Reviews, branch protection, and CI meet policy before merging.

## 13. Self-Check Questions

1. Why is the repository owner not necessarily the sole party allowed to decide a contract change?
2. What are the distinct advantages and risks of storing contracts with the producer versus in a standalone contract repository?
3. When `CODEOWNERS` exists, what else must be configured to enforce mandatory reviews?
4. Why can changing both Groovy DSL and producer code make generated tests pass while still breaking consumers?
5. What details must be recorded to prove consumer tests actually ran against the PR revision's stub?
6. For an event that drops an old field, why is consumer verification still vital even though there is no HTTP status code?

## Summary

**A contract repository is a cross-team coordination hub, not just a folder of Groovy/YAML files.** The producer owns implementing and releasing committed behaviors; consumers must confirm what they depend on; repository maintainers establish contribution rules and safeguard change history. A dependable review workflow combines **interface ownership, compatibility evaluation, producer generated tests, candidate stubs via Stub Runner, version management, and CI gates**. Together, they allow teams to negotiate API and messaging changes and surface risks before breaking consumers in production.
