# Explicitly Document the Scope, Owner, and Expiry of Temporary Measures

In **Java Advance Compatibility Migration**, a system cannot always fix every compatibility issue completely before the deployment date. An older library might still need JDK reflective access; a temporary adapter might have to translate data between `javax.*` and `jakarta.*` services; a message consumer might need to accept two schema versions; or an integration test might have to be separated because tooling does not yet support the target JDK.

Such measures can help a team **reduce disruption during migration**, yet they also create technical debt and operational risk. The greatest danger is not necessarily that a workaround is written, but a workaround **with no clear scope, no owner, no expiration date, and no evidence required for removal**. After a few months, a flag may get copied across every service, an old dependency may stay pinned forever, a feature flag may gradually become the default logic branch, or a skipped test may remain disabled after everyone forgets why.

The lesson **Explicitly Document the Scope, Owner, and Expiry of Temporary Measures**, in the chapter **Migration Strategy**, explains how to turn interim solutions into exceptions that are **controlled, searchable, testable, revocable, and closable**. It covers defining scope, assigning accountability, establishing deadlines and exit criteria, storing decisions in the repository, enforcing controls through CI, conducting periodic reviews, handling overdue measures, and removing workarounds without causing regressions.

## 1. What Is a Temporary Measure?

A **temporary measure** (temporary workaround, mitigation, or compatibility bridge) is a change that keeps a system operating while the root cause has not yet been resolved or while two versions coexist. Its active lifespan is bounded by a **calendar date, technical condition, deployment event, or a combination of those factors**.

Examples in Java migration:

- Adding `--add-opens` for a specific package so a legacy library can continue using reflection on a newer JDK.
- Pinning a library to a version confirmed to support the target JDK while waiting to upgrade to another official release.
- Using an adapter to translate requests/responses or events between protocol v1 and v2.
- Keeping two data read paths during database migration under the expand–migrate–contract pattern.
- Holding off on enabling a new enum/status for producers while legacy consumers remain active.
- Temporarily applying a Jakarta binary transformer to a JAR that has no upstream Jakarta release yet.
- Keeping a feature flag that enables logic rollback during canary rollout.
- Substituting a mock/fake for an integration unavailable in CI, paired with real tests in another pipeline.
- Running an older code generation tool inside an isolated build container while toolchain upgrades are incomplete.
- Temporarily restricting traffic to an endpoint or cohort during compatibility verification.

Not every interim solution is a bad workaround. Some **compatibility layers are deliberate migration designs**. The key point is that they must have a lifecycle: once the next migration step finishes, the intermediate layer must be evaluated for removal or converted into a long-term contract backed by a formal design decision.

### 1.1. How Temporary Workarounds Differ from Hotfixes, Fallbacks, and Permanent Designs

| Concept | Primary purpose | Must it necessarily expire? |
|---|---|---|
| Hotfix | Fix an urgent bug; may be a complete solution | No, if it fixes the true root cause |
| Temporary workaround | Bypass or mitigate impact before fixing the root cause | **Yes**: deadline and exit criteria |
| Compatibility adapter | Allow two versions/contracts to interoperate | Yes if only serving migration; may be long-term if it is a supported API |
| Migration feature flag | Control rollout/rollback of a change | Usually has a removal deadline after stabilization |
| Fallback/resilience pattern | Tolerate failures during regular operation | Can be a permanent design if backed by a clear contract |
| Security exception | Conditionally accept a deviation from policy | Must have an expiry, approver, and compensating controls |
| Technical debt | Unpaid technical trade-off | Needs management; temporary workarounds must have a more concrete roadmap |

If a mechanism has already been accepted as a **permanent design**, stop labeling it “temporary” indefinitely. Convert it into an architectural decision with its corresponding contract, owner, tests, support policy, and maintenance documentation.

## 2. Why Is a Workaround Without a Lifecycle Dangerous?

A small example:

~~~text
Migration JDK 11 -> 17
   |
   +-- Library A needs deep reflection
   |
   +-- Add --add-opens to startup script
   |
   +-- Production returns to normal
   |
   +-- Owner, reason, and deadline are not recorded
   |
   +-- Startup option gets copied to 8 services
   |
   +-- Library A is later upgraded
   |
   +-- Flag stays in config and nobody knows whether it is still needed
~~~

Potential problems:
- **Security:** opens reflective access broader than necessary.
- **Compatibility:** the option may stop working or no longer be supported in later JDKs.
- **Debugging:** difficult to tell whether a service uses a flag intentionally or copied it by mistake.
- **Upgrades:** whoever performs the next JDK upgrade does not know the condition for removing the flag.
- **Ownership:** when the proposer switches teams, the exception becomes “orphaned”.
- **Auditing:** unable to prove the exception was approved and tracked.
- **Testing:** no verification that the system still works when the flag is removed.

Similarly, a `javax` → `jakarta` transformer in the build pipeline might unblock deployment today yet cause the organization to overlook that the original library is EOL or has unpatched vulnerabilities. A temporary measure must therefore be treated as **an obligation that must be completed**, not merely a commit.

## 3. Three Mandatory Questions: Scope, Owner, Expiry

Every measure must clearly answer at least three questions:

1. **Scope:** which services/modules/runtimes does it affect, in which environments, and for which traffic/data/versions? What is out of scope?
2. **Owner:** who is responsible for monitoring, assessing risk, implementing the replacement, and removing the measure?
3. **Expiry:** by what date or after what event must the measure be removed or formally re-approved? How is the closure condition verified?

A good record should also include:
- **Reason:** what incident/gap made the measure necessary.
- **Risk:** security, compatibility, data, performance, and compliance hazards.
- **Compensating controls:** scope reduction, monitoring, permissions, fallback.
- **Exit criteria:** what upstream fix/test/deployment allows removal.
- **Evidence:** tickets, PRs, logs, tests, release notes, and deployments.
- **Rollback plan:** what to do if removing the workaround causes a regression.

### 3.1. An Easy-to-Understand One-Sentence Template

A measure should be summarizable in one sentence:

> The Orders service temporarily uses `--add-opens` **only** in the JVM running integration tests on JDK 17–21 while waiting to upgrade the reflection library LegacyMapper. Owned by the Platform/JVM team, review deadline 2027-01-15 (illustrative date). Exit: upgrade the library, remove the flag, run tests on both JDKs, and confirm no `InaccessibleObjectException`. Does not apply to production JVMs.

That sentence is far more useful than:

> Temporarily added JVM flag to fix error, deal with later.

It states the exact scope, owner, deadline, and verification condition; readers immediately know not to copy it to production.

## 4. Documenting Scope Across Multiple Dimensions

“Applies to project X” is usually too broad. In Java systems with multiple runtimes and environments, scope should be sufficiently specific.

| Dimension | Question | Example |
|---|---|---|
| Repository/module | Which module contains the workaround? | `orders-api`, `legacy-client` |
| Service | Which process or job is affected? | Orders web service, batch reconciliation |
| Environment | Dev, CI, staging, production? | CI integration only |
| JDK | Which version/vendor? | JDK 17/21, HotSpot |
| Framework | Which version? | Boot 3.2.x, Tomcat 10.1 |
| Dependency | Which JAR or plugin needs the workaround? | `legacy-mapper:2.4` |
| Operation | Which endpoint/task? | Startup plugin load, async export |
| Traffic cohort | Who receives different behavior? | 5% canary, pilot tenant |
| Data scope | Which schema/message/table? | Topic `order-events-v1` |
| Security boundary | Which processes/actors receive opened permissions? | Package opened to unnamed modules |
| Deployment | Which image/script/Helm chart? | `charts/orders/values-staging.yaml` |
| Lifetime | From which release until which milestone? | Starts 2026-11, expires 2027-01 |

### 4.1. Scope Includes What Does *Not* Apply

Examples:
- “Only for `integrationTest`, **not** for regular `test` or production”.
- “Only on the transition topic `orders-v1-bridge`, **not** changing all producers”.
- “Only for canary tenants, **not** enabled system-wide”.
- “Only transforms `javax.servlet` in this WAR, **not** altering Java SE's `javax.xml.parsers`”.

Negative boundaries (explicit exclusions) prevent **scope creep**. Another migration team might spot a handy workaround and copy it without understanding its original constraints.

### 4.2. Scope Should Point to Actual Code/Config

Do not rely solely on prose descriptions. Record:
- File paths/config keys or module/PR references.
- Deployment manifests and service versions.
- Affected launch arguments.
- Dependency coordinates and version ranges.
- Feature flag identifiers.
- Schemas/topics/endpoints when relevant.

Because file paths can change, attach both **the measure ID and issue/PR link**; paths help locate things quickly while the ID preserves traceability across refactors.

## 5. Choosing Clearly Accountable Individuals

A workaround should not list “the general team” or “whoever is free” as its owner. Roles can be assigned as follows:

| Role | Responsibility |
|---|---|
| **Technical DRI** | Owns implementation, monitors risks, and prepares the removal PR |
| **Service owner** | Ensures the measure does not cause operational failures and coordinates releases |
| **Risk/security approver** | Approves policy exceptions and compensating controls when required |
| **Migration lead** | Tracks deadlines, cross-team dependencies, and coordinates removal |
| **Reviewers** | Verify scope and exit tests; do not replace the DRI |
| **Backup owner** | Maintains accountability when the DRI is away or switches teams |

The **DRI (Directly Responsible Individual)** must be an individual or direct role identifiable via the organization/team directory, alongside an owning team. Assigning only a personal name without team backup can result in losing ownership when that person takes leave or moves projects.

### 5.1. Practical Ownership Rules

- Each measure has **one primary DRI** to avoid diffused accountability.
- Include an **owning long-term team** and a backup person.
- Security exceptions must have **approval from an authorized role**, not just the commit author.
- If a workaround affects multiple services, assign a **coordinating owner** plus individual service owners.
- When an owner switches teams, **hand off ownership before their departure date**.
- The deadline must sit in the owner's backlog/cadence, not buried in a rarely read wiki.

### 5.2. Ownership Does Not Equal Whoever Wrote the Workaround

The person creating the initial hotfix may be an on-call engineer. They are not necessarily the person with authority to replace a library, upgrade a framework, or accept security risk. Therefore distinguish:
- **Implemented by:** who authored the change.
- **Owned by:** who is accountable for maintaining/removing it.
- **Approved by:** who accepted the exception.
- **Removal assignee:** who creates the exit PR; usually the DRI or a specifically designated person.

Without explicit documentation, teams easily assume “whoever added the flag will remove it later”.

## 6. Documenting Expiry: Dates, Events, and Exit Criteria

A workaround with only an expiration date and no replacement plan easily becomes an ignored warning. Conversely, writing only “wait for new library” without a review date can stretch on forever.

There should be **two tiers of expiry**:

1. **Expiration date / decision deadline:** by this date the measure must be removed or receive a transparent re-approval decision.
2. **Exit criteria/trigger:** the technical condition enabling removal, such as the dependency being upgraded and tests passing without the flag.

Example:

~~~text
createdAt: 2026-11-12
nextReviewAt: 2026-12-01
expiresAt: 2027-01-15
exitTrigger: "legacy-mapper >= 3.x is accepted in the app"
exitTests:
  - "No more InaccessibleObjectException when removing --add-opens"
  - "Integration tests pass on JDK 17 and JDK 21"
  - "Production canary has no regressions"
~~~

The dates above are **examples**, not deadlines of a real project.

### 6.1. Expiry Is Not a Promise That a Framework Will Release a Patch on Time

An upstream dependency may slip its release. When that happens:
- The owner must review before the deadline.
- Evaluate current risk, impact level, and replacement options.
- Choose an option: replace the library, narrow scope, pause rollout, isolate workloads, or extend with approval.
- Record **the extension reason, new date, approver, and control changes**.

Do not silently change the expiration date in a file without recording history/approval. If the measure is no longer safe or violates a non-extendable policy, it must be escalated with a remediation plan.

### 6.2. Use Consistent Calendar Dates and Timezones

For date-managed measures:
- Use ISO 8601 such as `2027-01-15`.
- Define whether expiry takes effect at the start or end of the day, and in which timezone, if enforced automatically.
- For multi-region deployments, prefer timestamps with timezone offsets or UTC for automated events.
- Set deadlines ahead of when a runtime/dependency loses support rather than waiting until the exact end-of-support date.

In CI policy, a date-only `expiresOn` field might define “overdue as of 00:00 UTC the day after the stated date” or another rule. **State the convention explicitly** so different scripts do not interpret it inconsistently.

### 6.3. Deadlines Must Not Live Only in a YAML File

There must be at least one reminder/blocking mechanism:
- An issue with a due date and owner.
- A migration board/dashboard.
- A CI lint check or periodic report.
- Review scheduling in sprint/release planning.
- A gate requiring approval for extensions.

A “TODO remove later” entry without a ticket and deadline is **insufficient** for managing workarounds.

## 7. Minimum Record for a Temporary Measure

A temporary-measure register can be stored in the repository at a team-defined path, for example `migration/temporary-measures.yml`. Below is an **illustrative data sample**, not the schema of a standard tool:

~~~yaml
schemaVersion: 1
measures:
  - id: "JAVA-MIG-042"
    title: "Limit reflective access for LegacyMapper"
    status: "active"
    reason: "LegacyMapper 2.4 uses reflective access incompatible with newer JDKs"
    category: "jvm-option"

    scope:
      repositories: ["orders-platform"]
      modules: ["orders-integration"]
      environments: ["ci", "staging"]
      jdks: ["17", "21"]
      runtimeProcesses: ["integration-test-jvm"]
      excludedEnvironments: ["production"]

    implementation:
      type: "jvm-argument"
      value: "--add-opens=java.base/java.lang=ALL-UNNAMED"
      codeLocations:
        - "orders-integration/build.gradle.kts"
      introducedBy: "PR-1234"

    ownership:
      technicalDri: "owner-in-team-directory"
      owningTeam: "platform-jvm"
      backupTeam: "orders"

    risk:
      severity: "medium"
      securityImpact: "Opens deep reflection access inside the test process"
      compensatingControls:
        - "Do not use in production"
        - "Keep dependencies/test tools from approved sources"

    lifecycle:
      createdOn: "2026-11-12"
      nextReviewOn: "2026-12-01"
      expiresOn: "2027-01-15"
      removalTicket: "MIG-567"
      exitTrigger: "Upgrade LegacyMapper to a version that does not require opens"
      exitEvidence:
        - "Run tests without --add-opens on JDK 17 and JDK 21"
        - "Integration tests pass"
      rollbackPlan: "Restore the flag in the test runner only if tests regress"

    approvals:
      - role: "migration-lead"
        reference: "APPROVAL-089"
~~~

Benefits:
- **Structured scope** helps scripts verify the measure is not copied into the wrong environment.
- **Named ownership** enables automated reminders.
- **Dated expiry** enables automatic detection of overdue measures.
- **Exit evidence** gives removal code reviews concrete standards.
- **Implementation paths** make active flags traceable.
- **Approval references** help audits explain why an exception was accepted.

Do not put tokens, passwords, account secrets, or personal data into the register. When linking private tickets/incidents, enforce need-to-know access permissions.

### 7.1. Where Is the Source of Truth?

Options include:
- YAML/JSON in the repository.
- Issue tracker with custom fields.
- ADR (Architecture Decision Record).
- Service catalog or risk exception system.
- A team-maintained migration tracking table.

Pick **one primary source of truth** for ID, owner, deadline, and status, and have other places link to it. If multiple systems hold copies, synchronization mechanisms are needed so deadlines in a wiki do not drift from ticket deadlines.

For multi-repository projects, you can manage a centralized register while still embedding **the ID in code/config** for quick discovery. Example comment:

~~~properties
# TEMP-MIGRATION JAVA-MIG-042; owner=platform-jvm; expires=2027-01-15
# Only for the integration-test JVM; do not put into production.
org.example.testJvmOpens=--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

This is only a metadata/comment example, **not a standard Gradle property**; how options are actually passed depends on the test task/build script. Do not use comments as the sole enforcement mechanism.

## 8. ADRs for Significant Exceptions

For a workaround with wide impact, a single line in a register may be insufficient. Use an **Architecture Decision Record (ADR)** to capture rationale and trade-offs.

An ADR should contain:

~~~text
ADR-017: Compatibility bridge for Order Events v1/v2

Status: Accepted (temporary)
Context:
  - New producer emits v2 events
  - v1 consumer is still within the support window
Decision:
  - Adapter reads both v1 and v2 in the new consumer
  - Producer does not emit new required fields to the v1 consumer
Scope:
  - Kafka topic orders-v1-migration
  - Orders/Billing in staging and production
Owner:
  - Messaging DRI, with Orders/Billing service owners
Expiry:
  - 2027-02-28, reviewed every sprint
Exit:
  - No remaining v1 consumers
  - All old events have passed retention or have a compatible replay path
  - Contract/integration tests pass after removing the adapter
Risks:
  - Duplicate handling, schema drift, replay
Controls:
  - Schema registry checks, idempotency, consumer lag alerts
Rollback:
  - Keep producer v1 contract during the committed window
References:
  - PR, deployment, runbook, test evidence
~~~

An ADR explains **why the organization made the decision**; the register **manages current status and deadlines**. An approved ADR does not mean the workaround automatically renews indefinitely.

### 8.1. Decision Log and Audit Trail

When changing scope/expiry/owner, record:
- Who proposed the change and the date.
- Why the change is needed.
- New or changed risks.
- Approver.
- Related events/issues.
- New controls.
- Updated exit criteria and deadline.

Avoid rewriting history to make it look as if the workaround was approved from the start. With Git-backed data, commit/PR history helps auditing, though stricter regulatory requirements call for an exception-tracking system with appropriate access controls and retention.

## 9. Approval Process Before Activation

A good workaround should not receive `active` status merely because its code was merged. A decision is needed confirming it is safe enough for its **specific scope**.

Suggested flow:

~~~text
Detected migration blocker
           |
           v
Propose temporary measure
           |
           v
Document scope + owner + expiry + risk + exit criteria
           |
           v
Technical / Security / Operations review (by risk level)
           |
       +---+----+
       |        |
    Reject    Approve
       |        |
  Pick an      v
alternative  Limited deploy
                |
                v
           Monitor + review
                |
          +-----+-------+
          |             |
       Remove        Extend?
          |             |
          v             v
       Verify       Reassess risk
          |         and approvals
          v
         Close
~~~

### 9.1. Criteria for Accepting an Exception

Ask:
1. What is the specific blocker? Are there logs/a reproducer?
2. Is an immediate root-cause fix feasible?
3. To what extent does the workaround reduce impact, and what guarantees does it weaken?
4. Is the scope as narrow as possible?
5. Is there a way to detect when the workaround stops working or causes failures?
6. Is there a removal plan and realistic deadline?
7. Can deployment/behavior/data be rolled back?
8. Who accepts the residual risk?
9. What would trigger revoking the measure earlier than its expiry?

If answers remain vague around security/data, do not mark the status approved just to “unblock” rollout.

### 9.2. Workarounds That Should Never Be Approved

Examples of “get it running temporarily” hacks that violate safety:
- Disabling certificate validation or hostname verification when calling production systems.
- Disabling authentication/authorization on real endpoints.
- Writing secrets into Git/logs to work around migration configs.
- Disabling artifact signature verification or bypassing supply-chain controls indefinitely.
- Allowing deserialization of untrusted data without proper policies/guards.
- Running destructive database migrations with no backup/recovery plan.
- Running an unsupported JDK runtime with critical vulnerabilities in production without approved mitigation.

For security risks, **a deadline does not make a dangerous practice safe**. You may need to block the release, isolate the system, upgrade the library, or change protocols instead of creating an exception.

## 10. Common Workaround Types in Java Migration

### 10.1. JVM Module Access: --add-opens

Since Java 9, JPMS has enforced module boundaries. On modern JDKs, strong encapsulation causes some legacy reflection libraries to throw `InaccessibleObjectException`.

Example temporary flag:

~~~bash
java \
  --add-opens=java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

It grants deep reflective access to the `java.lang` package of module `java.base` from **unnamed modules** in that process. This permission may be broader than what a specific library needs; if the application uses named modules, target module selection may differ.

**Do not treat `--add-opens` as a root fix.** It does not restore removed APIs and does not solve all binary compatibility errors. For production workloads, review the risk of opening internals, pick the narrowest feasible package/target, and prioritize upgrading the library.

The record must specify:
- The error/root cause and dependency requiring the flag.
- Which processes receive the flag: Gradle daemon, test JVM, or application runtime?
- Which JDK versions need the flag.
- Which environments are permitted.
- Owner of the dependency upgrade.
- Exit: upgrade library, remove flag, re-test runtime.
- Deadline and approvals if enabled in production.

#### Do Not Copy Flags from Tests to Production

An `--add-opens` in `Test.jvmArgs` affects only the test JVM. Adding it to container/system-wide `JAVA_TOOL_OPTIONS` can affect every Java process and unnecessarily broaden permissions. Scope must distinguish **build JVM, test forks, and production JVMs**.

### 10.2. Temporary Dependency Pin or Fork

For example, a library does not yet support JDK 21, so the project:
- Pins to a version verified to work on the target JDK.
- Temporarily uses an internal patched fork for compatibility.
- Excludes a conflicting transitive dependency.

Risks:
- Missing security patches.
- Degrading binary/API compatibility with frameworks.
- Fork diverging from upstream.
- Unmanaged licensing/SBOM/provenance.
- Tests running on only one JDK vendor/build.

The record needs coordinates, pinned version, CVE policy, upstream issue, owner, review cadence, exit version, and test matrix. **Do not pin old versions indefinitely** just because the build is currently green.

### 10.3. Jakarta Namespace Transformation

A legacy JAR still using `javax.servlet.*` can be temporarily converted using Eclipse Transformer or the Apache Tomcat Jakarta migration tool when no official Jakarta release exists yet.

Scope should specify:
- Input JAR/WAR checksum and publishing source.
- Transformer version/rules.
- Output artifact hash.
- Target Jakarta EE/platform/container.
- Which classes/resources are actually transformed.
- Which Java SE `javax.*` packages must remain untouched.
- Deadline before replacing with an upstream Jakarta artifact.

Exit: vendor release or Jakarta source rebuild, remove binary transformation, run contract/integration tests on the target container.

Do not assume rewriting bytecode automatically fixes reflection, XML, ServiceLoader, signatures, serialization, or behavior. If the original artifact was signed, transformation alters bytes and requires an appropriate provenance/signing workflow.

### 10.4. Compatibility Adapters and Dual-Read

During parallel v1/v2 execution, a new consumer can temporarily read both old and new schemas:

~~~text
Producer v1 --- event v1 ---+
                            |
                            v
                      Dual-version reader
                            |
                            v
                      New domain model
                            ^
                            |
Producer v2 --- event v2 ---+
~~~

Scope must state:
- Topics/event types/schema versions.
- Consumer groups and service versions.
- Retention/replay policy.
- Handling of unknown enums/fields.
- Idempotency and duplicate messages.
- Business semantics during mapping.
- When legacy consumers remain and when the adapter is removed.

Exit is not merely “producer v2 deployed”. You must prove **no v1 consumers still require support**, old events have been processed or have a safe replay path, and rollback remains planned if switching to forward-only.

### 10.5. Migration Feature Flags

Feature flags can enable new logic per tenant/cohort during canary rollouts:

~~~yaml
features:
  use-new-json-parser: false
~~~

If the flag is temporary:
- ID and configuration location.
- Default value per environment.
- Owner and who is authorized to toggle it.
- States/contracts produced by both branches.
- Metrics and rollback path.
- Deadline to remove the old code branch.

A flag left at 100% traffic yet remaining in code for two years causes **complexity leaks**: tests must cover both branches, old dependencies cannot be removed, and someone might accidentally re-enable unsupported behavior later.

### 10.6. Test Quarantine or Suppression

Some tests whose older tooling does not support a newer JDK may require a separate pipeline or temporary quarantine. This is a **high-quality-risk** exception because it reduces regression detection coverage.

The record must include:
- Exact list of tests.
- Failure details and reproduction conditions.
- Functional area no longer checked.
- Replacement check or manual validation.
- Owner fixing the tool/tests.
- Deadline to restore tests.
- CI reporting showing tests are still quarantined.

Do not hide skipped tests from reports and claim all tests pass. A disabled test **is not evidence of compatibility**.

### 10.7. JVM Flags and Agent Policy

During JDK 21+ upgrades, some test frameworks or tools may trigger dynamic Java agent loading warnings under JEP 451. Teams sometimes want to temporarily enable `-XX:+EnableDynamicAgentLoading` for compatibility, which requires explicit scope review.

When tests genuinely need inline mocking, configuring an explicit **startup `-javaagent` for the test JVM** is usually a more intentional approach than broadly permitting dynamic attach. A `-javaagent` configuration can be a **sustainable test design**, not necessarily a temporary workaround. Do not assume every JVM flag must be removed; classify them by purpose, policy, and lifecycle.

In particular, **do not add a flag no longer supported by the JDK** as a “temporary compatibility fix”. For example, `--illegal-access` no longer acts as a useful mechanism for relaxing access in modern JDKs; verify exact flags per release and fix root causes.

## 11. Risks to Evaluate Before Applying

A workaround can alter:
- **Security posture:** module access, agent permissions, auth/TLS.
- **Data integrity:** schema dual-write, replay, idempotency.
- **Correctness:** parser fallback, enum mapping, timezone.
- **Reliability:** timeouts, retries, failure propagation.
- **Performance:** reflection, serialization, GC, memory.
- **Operations:** logging, metrics, manual steps, restart needs.
- **Maintainability:** extra code branches/adapters, dependency forks.
- **Compliance/supply chain:** unsupported artifacts, source provenance, licensing.

A qualitative matrix:

| Risk level | Example | Management conditions |
|---|---|---|
| Low | Flag for a noncritical CI test, with replacement test | Owner, deadline, CI warning |
| Medium | Dependency pin in an internal service | Release review, SCA scan, test matrix |
| High | Data adapter affecting financial transactions | Business owner approval, reconciliation, alerts, rollback |
| Critical | Disabling auth/TLS checks in production | Disallowed by default; requires alternative or ultra-strict policy approval |

This is only an **illustrative classification**; an organization may maintain a more detailed risk framework. Do not downgrade risk labels merely to pass gates.

### 11.1. What Are Compensating Controls?

They are mechanisms reducing risk while the measure exists:
- Restricting to CI/test environments only.
- Limiting to a single service/tenant/endpoint.
- Appropriate network isolation or rate limiting.
- Alerting when the fallback is triggered.
- Checking dependency versions every release.
- Canary rollout and conditional rollback.
- Data reconciliation during dual-writes.
- Role-based approval permissions.
- Contract/integration tests compensating for missing checks.

Compensating controls **do not replace** fixing the root cause; they keep risk within an acceptable level for an approved period.

## 12. Designing Lifecycle and States

Do not rely on just two states (“yes/no”). A suggested lifecycle:

~~~text
proposed -> under_review -> approved -> active
                                  |
                                  v
                           removal_planned
                                  |
                                  v
                              removed
                                  |
                                  v
                               closed
~~~

Exception states:
- `rejected`: not allowed for use.
- `revoked`: must be stopped early due to risk.
- `expired`: overdue, not validly extended.
- `extension_requested`: pending review/approval, not automatically extended.
- `blocked`: cannot be removed yet because an unmet dependency remains; requires escalation.

### 12.1. Difference Between Expired and Removed

- **Expired**: the deadline has passed and the obligation is unclosed. Must not be marked completed.
- **Removed**: the change removing the workaround has been merged/deployed.
- **Closed**: evidence across required environments proves the workaround is gone, exit tests pass, monitoring is stable, and registers/tickets are updated.

Simply deleting a YAML line from the register does not prove the option disappeared from Helm, systemd, Dockerfile, CI, or config services.

### 12.2. Rule: Never Erase the Audit Trail

After removal, retain a closed record or audit reference containing:
- Removal date.
- PR/commit.
- Artifact/deployment version.
- Test evidence.
- Verifying person.
- Residual risks if any.

If the system needs to declutter active lists, move entries to `closed`/archive instead of erasing all history.

## 13. CI Guardrails: Turning Deadlines into Technical Signals

Writing an expiration date in a README is not enough if nobody looks at it. CI can be used to:
1. Verify every active workaround has an ID, owner, scope, expiry, and exit ticket.
2. Warn as deadlines approach.
3. Block adding workarounds missing mandatory fields.
4. Detect expired records according to policy.
5. Require review if dates change or scope widens.
6. Verify flags/dependencies in code reference an ID.
7. Generate automated reports for the migration lead.

### 13.1. Example JSON Register and Expiry Check Script

To demonstrate checking with the **Python standard library**, JSON can be used instead of YAML if the pipeline prefers not installing a YAML parser. Sample:

~~~json
{
  "schemaVersion": 1,
  "measures": [
    {
      "id": "JAVA-MIG-042",
      "status": "active",
      "owner": "platform-jvm",
      "scope": ["ci:orders-integration"],
      "expiresOn": "2027-01-15",
      "removalTicket": "MIG-567"
    }
  ]
}
~~~

Example script checking required fields and expiration dates:

~~~python
import json
import sys
from datetime import date
from pathlib import Path

path = Path("migration/temporary-measures.json")
register = json.loads(path.read_text(encoding="utf-8"))

required = ("id", "owner", "scope", "expiresOn", "removalTicket")
today = date.today()
errors = []

for measure in register.get("measures", []):
    if measure.get("status") not in ("active", "approved"):
        continue

    missing = [
        key for key in required
        if not measure.get(key)
    ]
    if missing:
        errors.append(
            f"{measure.get('id', '<missing id>')}: "
            f"missing {', '.join(missing)}"
        )
        continue

    try:
        expires_on = date.fromisoformat(measure["expiresOn"])
    except (TypeError, ValueError):
        errors.append(f"{measure['id']}: invalid expiresOn")
        continue

    if today > expires_on:
        errors.append(
            f"{measure['id']}: expired on {expires_on}"
        )

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

print("Temporary measures: mandatory fields and expiry OK")
~~~

This is an **illustrative script**; it reads a single JSON file and uses the runner's local date. Production CI should standardize timezones (e.g., UTC), validate full schemas, and handle missing files, duplicate IDs, valid scopes, and policies for `extension_requested` or `expired`. If using YAML, use an appropriate parser with equivalent validation rules.

### 13.2. Do Not Use a CI Expiry Gate Without a Controlled Escape Hatch

If every pipeline is blocked solely due to a calendar deadline, teams may delete records or arbitrarily change dates. Provide a workflow:
- Fail or warn by default depending on risk level.
- For production-critical systems, provide a **time-boxed exception approval** path.
- Every extension includes owner, reason, scope, approver, and new date.
- Log changes and create tickets.
- Disallow silent bypasses via ID deletion.

The purpose of the gate is to **drive accountable decisions**, not incentivize circumventing controls.

## 14. Static Inventory in Repositories and Runtime

A temporary measure may appear in:
- Java/Kotlin source and test helpers.
- Gradle/Maven build scripts and compiler flags.
- Dockerfiles and container entrypoints.
- Kubernetes manifests/Helm.
- Systemd units or service scripts.
- CI variables and pipeline templates.
- Remote configuration services.
- Feature flag platforms.
- Java agent launch configs.
- Deployment descriptors and XML.
- Infrastructure-as-code.

Finding no flags via repository grep does not prove none are running. Startup options can be injected via `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Helm values, CI secrets, or orchestration platforms.

### 14.1. Searching for Common Signals

Example search commands when a team proactively audits a repository:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'TEMP-MIGRATION|JAVA-MIG-[0-9]+|TODO.*remove|--add-opens|--add-exports' .

rg -n --hidden -g '!**/.git/**' \
  'EnableDynamicAgentLoading|mock-maker-inline|skipTests|test\.enabled|feature\.' .
~~~

Classify results rather than deleting mechanically. `--add-opens` might be part of a long-term supported toolchain for a documented use case; a feature flag might be a permanent resilience feature. **Inventory must be driven by intent and policy**, not raw keywords.

### 14.2. Comparing Actual Runtime Against the Register

A runbook can inspect:
- Effective JVM flags of a process via `jcmd <pid> VM.flags` when permissions and environment support it.
- `java -version` and container image digest.
- Rendered Kubernetes manifests.
- Active feature flag configuration.
- Dependency tree of released artifacts.
- Tests and condition evaluation/actuator data when relevant.

Do not log raw env vars/secrets to “prove” config. You only need evidence showing whether a specific option/key/version still exists within its intended scope.

## 15. Marking Code Without Cluttering the Codebase

A brief comment near the workaround should state the ID and purpose. Example:

~~~java
public final class LegacyStatusAdapter {

    // TEMP-MIGRATION JAVA-MIG-057
    // Owner: messaging-platform; expiry: 2027-02-28
    // Only used for v1 events during the parallel-run phase.
    public String toNewStatus(String legacyStatus) {
        if ("WAITING".equals(legacyStatus)) {
            return "PENDING";
        }
        return legacyStatus;
    }
}
~~~

A comment does not prove this mapping is business-correct. Contract tests across all enums/statuses and v1/v2 consumer checks are required. However, the ID makes it easy to find code to delete later.

### 15.1. Do Not Embed Deadlines That Cause Abrupt Runtime Changes

Avoid code such as:

~~~java
if (LocalDate.now().isAfter(expiryDate)) {
    throw new RuntimeException("Workaround expired");
}
~~~

if doing so could halt production on the expiration date. Expiry should primarily be enforced at **governance/CI/release gates** alongside escalation workflows. If a security policy genuinely demands runtime expiry, fail-closed/fallback behavior, monitoring, and approvers must be explicitly designed; do not plant time bombs in services.

### 15.2. Do Not Hide New Logic Behind an Old Branch Indefinitely

With a feature flag:

~~~java
if (flags.useNewSerializer()) {
    return newSerializer.encode(order);
}
return legacySerializer.encode(order);
~~~

Once all consumers have migrated, branches can be consolidated and the flag removed. Leaving it forever forces teams to maintain two data paths, test both, and risk accidentally re-enabling legacy behavior later.

Exit criteria should include:
- All supported consumers have migrated.
- Old events/data have completed replay/backfill handling.
- New logic is sufficiently stable.
- Removal PR deletes flag, code path, tests, config, and docs.
- No dependencies remain that only serve the old branch.

## 16. Explicitly Stating Removal Criteria by Workaround Type

| Temporary type | Minimum exit criteria |
|---|---|
| `--add-opens` | Dependency fixed/upgraded; tests pass without the flag on target JDKs |
| Dependency pin | Upstream version verified; security/API/ABI tests pass |
| Binary Jakarta transformer | Upstream Jakarta artifact or source rebuild available; runtime/integration tests pass |
| Legacy API adapter | No remaining old consumers; schema/event replay plan completed |
| Dual-write | Data reconciled; single source of truth; failure handling verified |
| Feature flag migration | 100% cohort on new branch; rollback/data risks resolved; old branch deleted |
| Test quarantine | Tests re-enabled or replaced with equivalent approved coverage |
| GC/JVM tuning workaround | Performance benchmarks on target runtime show it is no longer needed |
| Agent dynamic-loading workaround | Startup agent/mock strategy configured properly; tests pass without dynamic attach |
| Temporary config alias | No processes reading old key; env/Helm/config service migrated |

### 16.1. Removal Evidence Is Not “No Errors for One Day”

Depending on the workaround, evidence is needed such as:
- CI passing across the exact JDK/framework matrix.
- v1/v2 contract tests and integration tests.
- Bytecode/dependency checks.
- Runtime canary metrics.
- Negative security tests.
- Database reconciliation.
- No unsupported flags in startup configs.
- Verified build artifact checksum and deployed version.

Concluding “removed flag, local tests pass” is insufficient when the flag also applied to production and bugs only surface under rare workloads.

## 17. A Safe Two-Step Removal Plan

For workarounds affecting production, split removal into two steps:

**Step 1: Controlled test disablement**
- Prepare an equivalent staging environment.
- Remove the workaround or enable the new branch for a canary cohort.
- Run tests, monitor logs/metrics, and verify business invariants.
- Keep a clear rollback path ready.

**Step 2: Full removal**
- Remove code/flags/config/dependencies/transformers.
- Delete old compatibility paths and associated tests per policy.
- Verify no references remain in runtime, build, or deployment configs.
- Update register/tickets and operations documentation.
- Deploy to all environments in scope.
- Close the measure once evidence is verified.

### 17.1. Avoid Removing Early While Old Consumers or Data Still Exist

If an adapter serves v1 events, “seeing no v1 traffic today” does not prove it is unneeded. There may still be:
- Dead-letter queues holding older events.
- Weekly batch consumers.
- Un-upgraded mobile/partner clients.
- Caches/sessions containing old schemas.
- Replays from backups.
- Long-retention workflow retries.

Exit criteria must evaluate **retention, replay, support windows, and external consumer contracts**.

### 17.2. Rollback of Removal May Differ from App Rollback

If removing an adapter also deletes an old schema, rolling back the binary may no longer be safe. Define:
- Milestones before/after deleting old data.
- Whether backfill or a reverse adapter exists.
- When the change becomes forward-only.
- Who approves the point of no return.
- Backup/restore/reconciliation plans when needed.

Do not take “we can redeploy the old JAR” as proof that the entire system can roll back.

## 18. Tracking Deadlines and Reporting to Owners

Every sprint/release or appropriate cadence, the migration lead should maintain a table:

| ID | Measure | DRI | Scope | Expiry | Status | Next action |
|---|---|---|---|---|---|---|
| JAVA-MIG-042 | Opens for LegacyMapper | Platform/JVM | CI test | 2027-01-15 | Active | Upgrade library |
| JAVA-MIG-057 | Event v1 bridge | Messaging | Orders/Billing | 2027-02-28 | Active | Measure remaining v1 consumers |
| JAVA-MIG-061 | Pin ORM build plugin | Build infra | 2 modules | 2027-01-31 | Under review | Test new plugin |
| JAVA-MIG-073 | Serializer feature flag | Orders | Canary | 2026-12-20 | Removal planned | Open removal PR |

**Dates and IDs above are examples.** Dashboards should link to the real register/tickets rather than creating a second manually updated data source.

### 18.1. Useful Governance Metrics

- Active workarounds by service/team/category.
- Overdue workarounds.
- Active high-risk exceptions.
- Median and maximum age.
- Number of extensions/exceptions granted.
- Workarounds removed per release.
- Workarounds lacking a DRI or exit criteria.
- Consistency rate between CI/ticket status and actual runtime state.

Do not optimize counts by encouraging superficial record deletion. **Reducing workarounds must accompany risk reduction and genuine implementation removal**.

### 18.2. Review Cadence by Risk Level

Example policy:
- High/critical: review every release or on the security-approval cadence.
- Medium: review every sprint/month.
- Low: review on an approved release cycle.
- Upcoming expiry: notify far enough in advance to complete removal work.
- Overdue: escalate and reach an explicit decision.

Do not apply these intervals rigidly across every organization. Thresholds/cadences should derive from actual risk policies and release velocity.

## 19. How to Extend a Workaround Responsibly

A common real scenario: an upstream library promised a Jakarta-compatible release but is delayed, while the service must stay running.

An extension request should answer:
1. When was the old deadline?
2. Why was exit not achieved?
3. Did current scope or risk change?
4. Is a lower-risk alternative workaround available?
5. Are any security/support deadlines approaching?
6. How long an extension is needed and why?
7. What new compensating controls apply?
8. Who approves, and when is the next review?
9. What intermediate milestones demonstrate progress?

### 19.1. Extension Request Template

~~~text
Extension Request: JAVA-MIG-042
Previous expiry: 2027-01-15
Proposed expiry: 2027-02-15
Reason: Upstream release candidate still fails on the JDK 21 test workload.
Scope: CI integration-test only; unchanged.
Risk delta: Does not expand production permissions.
Compensating controls: Pin test image and scan dependencies.
Evidence: Upstream issue, failed CI run, and compatibility report.
Owner: platform-jvm DRI
Approver: migration lead
Next checkpoint: 2027-01-31
Exit: Upgrade library + remove --add-opens + pass JDK matrix tests.
~~~

**Do not turn extensions into a way to legitimize indefinite delay.** If an exception keeps getting extended, re-evaluate the design: swap libraries, split services, contribute upstream fixes, or choose a different migration strategy.

## 20. Distinguishing Workarounds Appropriate for Each Environment

A single issue may warrant different interim solutions by environment:

| Environment | Example measure | Constraints |
|---|---|---|
| Local developer | Temporarily pick an older JDK to run codegen | Do not use unverified artifacts in production |
| CI | Startup agent for tests, controlled test quarantine | Do not hide test failures |
| Staging | Adapter/feature flag to test new contract | Representative workloads/data |
| Production canary | Enable only for limited tenants/cohorts | Business metric alerts and rollback |
| Production general | Only approved measures | Clear scope/time/risk and tight controls |

A solution tested only in CI is not automatically qualified for production. Conversely, production workarounds should be exercised in staging/CI so removal has evidence.

### 20.1. Do Not Let Test-Only JVM Flags Leak into Service Launchers

For example, test forks use `-javaagent` or `--add-opens` to support mocking/legacy test frameworks. Those options must not be copied into `JAVA_TOOL_OPTIONS` of production images simply because they made CI pass.

Specify clearly:
- Which JVM needs the flag.
- In which task/process.
- Under what conditions it must appear.
- Exact configuration source.
- How to verify it does **not** appear outside scope.

## 21. Integrating the Register with the PR/Release Process

A pull request adding a workaround should include an information template:

~~~text
Temporary Measure ID:
Migration blocker:
Why permanent fix cannot be done now:
Exact scope:
  - repository/module:
  - service/process:
  - JDK/framework versions:
  - environments:
  - excluded environments:
Technical DRI:
Owning team / backup:
Risk assessment:
Compensating controls:
Introduced by PR:
Created on:
Next review:
Expiry:
Exit trigger:
Removal ticket:
Tests/evidence:
Rollback plan:
Approvers:
~~~

### 21.1. Code Reviews Must Expose Trade-Offs

Reviewers should confirm:
- The workaround genuinely addresses the stated blocker.
- No lower-risk alternative was overlooked.
- Scope is not overly broad.
- Deadline is reasonable and tied to a milestone.
- Owner has the authority and capacity to execute.
- Exit tests can run on the target JDKs.
- CI/monitoring can detect regressions.
- Old consumer data/security/contracts are not adversely impacted.

Do not judge a patch solely by a green build if it grants broad permissions or disables tests.

### 21.2. Release Notes and Runbooks

If a workaround affects production behavior, release notes/runbooks must state:
- Which option, flag, or adapter is enabled.
- Traffic and deployment scope.
- Known limitations.
- Signals to monitor.
- Rollback/cutoff conditions.
- DRI/on-call escalation.
- Links to register ID/ADR.

Sensitive security details do not necessarily belong in public release notes; record them in access-controlled internal documentation.

## 22. Combining Workarounds with a Multi-Phase Migration Plan

Example:

~~~text
Phase A: Inventory + baseline
   |
   v
Phase B: Approved temporary bridge
   |
   v
Phase C: Deploy new JDK via canary
   |
   v
Phase D: Upgrade dependencies, migrate consumers/data
   |
   v
Phase E: Remove bridge, drop flags, delete legacy paths
   |
   v
Phase F: Verify + close temporary measures
~~~

A workaround should not exist outside this plan as an unscheduled “do later” item. Tie its exit deadline to concrete milestones:
- Which sprint upgrades the dependency.
- When old consumers reach end of support.
- When data migration/backfill completes.
- Which contract tests must pass.
- Which release cleans up the feature flag.

### 22.1. Critical Path and Cross-Team Dependencies

Suppose removing the v1 event bridge depends on:
- Billing upgrading its consumer.
- A CRM partner confirming the new contract.
- Kafka retention/replay windows clearing out.
- Orders stopping emission of the old schema.

The bridge's DRI cannot finish alone if other teams have not completed their work. Therefore the record should list **dependency tickets and owners**, placed on the migration board for the Prime/migration lead to coordinate. Still, one DRI must remain responsible for **tracking and reporting progress on the measure**.

## 23. Practical Example 1: --add-opens for Tests on a Newer JDK

**Context:** when upgrading build/tests to JDK 21, an integration test using the `LegacyMapper` library throws `InaccessibleObjectException`. The team cannot upgrade the library in the same release.

**Temporary approach:** pass `--add-opens` only to the integration test JVM.

### 23.1. Scope

~~~text
Measure: JAVA-MIG-101
Repository: orders-platform
Module: integration-tests
JDK: 21 HotSpot
Environment: CI, staging test runner
Excluded: production, general developer launcher
Root cause: legacy reflection into java.base/java.lang
Risk: opens reflective access in the test process
~~~

### 23.2. Owner and Expiry

~~~text
DRI: JVM migration engineer (owner identified via directory)
Owning team: Platform
Removal ticket: MIG-1012
Review: every sprint
Expiry: 2027-01-15 (illustrative)
Exit: upgrade LegacyMapper, remove opens flag,
      run JDK 21 integration tests and confirm no exceptions remain
~~~

### 23.3. How to Implement and Remove

If using Gradle, the flag must live on the **JVM test execution task**, not globally in production `JAVA_TOOL_OPTIONS`. Example placement (illustrative DSL):

~~~groovy
tasks.named('integrationTest', Test) {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

A real project must define the `integrationTest` task and appropriate configurations. Once the upstream library is fixed:
1. Delete the flag line.
2. Run the test matrix on target JDKs.
3. Inspect logs/exceptions.
4. Merge the removal PR.
5. Verify deployed artifacts/configs no longer contain the option.
6. Close the ticket and record.

### 23.4. What Not to Do

- Adding the flag to all JVMs on a host.
- Using `--add-opens` as an attempted fix for removed APIs.
- Copying the flag to production without review.
- Deleting failing tests instead of addressing the dependency.
- Extending indefinitely because “nobody remembers why anymore”.

## 24. Practical Example 2: Temporarily Supporting Two Event Formats

**Context:** the new Orders producer is ready, yet the older Billing consumer needs one more release cycle. Both sides cannot deploy simultaneously.

**Temporary approach:** the new consumer accepts both v1 and v2 event schemas, while the producer preserves the v1 contract for old consumers during the support window.

### 24.1. Scope and Risks

~~~text
Measure: JAVA-MIG-118
Systems: Orders producer, Billing consumer
Topic: order-events
Schemas: v1, v2
Environments: staging, production
Traffic: all order events during coexistence window
Owner: Messaging platform DRI
Dependency: Billing consumer upgrade
Risks: schema drift, duplicate processing, out-of-order events
Controls: schema registry, idempotency, DLQ monitoring, contract tests
Expiry: 2027-02-28 (illustrative)
~~~

Saying only “Bridge will be deleted after v2 deploys” is insufficient. Exit requires:
- Billing v1 has stopped production processing.
- No batch/partner consumers remain outside the support window.
- Any v1 events remaining in retention/DLQ are handled or have a valid replay path.
- Zero traffic on the bridge path over an accepted measurement window.
- Post-removal tests verify business invariants.
- Rollback policy no longer requires v1 producer/consumer compatibility.

### 24.2. Signals to Observe

- Counts of v1/v2 events processed.
- Consumer lag and DLQ depth.
- Duplicate event IDs.
- Mapping failures/unknown enums.
- Reconciliation mismatches.
- Retries and timeouts.
- Consumer client/service versions.

Only when all conditions are confirmed can the adapter be removed and the measure closed.

## 25. Practical Example 3: Temporary Jakarta Artifact Transformer

**Context:** an internal library still contains `javax.servlet.*` in compiled bytecode, while the application moves to Jakarta Servlet.

**Temporary approach:** apply a binary transformer with a pinned rule set to produce a namespace-compatible artifact. This can serve as a stepping stone while the library team updates the source.

The record should describe:

~~~text
ID: JAVA-MIG-132
Input: legacy-filter-2.3.jar (checksum...)
Output: legacy-filter-2.3-jakarta-transformed.jar (checksum...)
Tool: Eclipse Transformer version pinned
Rules: Jakarta migration rule set pinned
Scope: only Orders WAR; not all shared libraries
JDK/Server: JDK 21, Jakarta Servlet container supported version
Owner: Shared Libraries DRI
Risk: reflection, ServiceLoader, XML, signatures, EOL library
Expiry: 2027-03-31 (illustrative)
Exit: official Jakarta release + contract/integration tests
~~~

Do not use a “-jakarta” suffix to disguise the fact that an artifact is an unofficial fork/transform. Maintain provenance and dependency scans per policy, and never assume namespace rewriting automatically implies behavioral compatibility.

## 26. When to Halt Migration Instead of Adding a Workaround?

Workarounds are appropriate only when residual risk is acceptable and an exit path exists. Consider **blocking rollout** if:

- No owner exists with capability/authority to remove it.
- The scope or affected systems are unclear.
- The change bypasses core security controls.
- There is no way to detect data corruption or duplicate transactions.
- A compatibility adapter relies on ambiguous business mappings.
- A binary transformer yields artifacts without trustworthy provenance.
- An unsupported dependency carries security risks that cannot be mitigated within current scope.
- Removing the workaround eliminates the rollback path without an alternative plan.
- Old consumers cannot read new data while rollback to the old version is still expected.
- Expiration dates repeatedly slip with zero progress.

**Deadline pressure does not make a workaround safe.** You need to adjust the migration plan: split scope, upgrade dependencies first, accept partial migration, or move the release date.

## 27. Brief Report Template for Release Review

Reporting a measure should answer:

~~~text
ID: JAVA-MIG-042
Status: active
What: Temporary --add-opens for LegacyMapper
Scope: orders-integration CI/staging test JVM, JDK 17/21
Owner: Platform/JVM DRI
Created: 2026-11-12
Next review: 2026-12-01
Expires: 2027-01-15
Current risk: medium; test-only reflective access
Latest evidence: JDK 21 integration tests pass with workaround
Exit blocker: upstream mapper version upgrade pending
Next action: validate candidate library without flag
Removal ticket: MIG-567
Decision needed: none / escalate if upstream misses milestone
~~~

A good report **does not duplicate the full ADR**, yet immediately shows decision-makers the scope, owner, deadline, risk, and next action.

## 28. Common Mistakes

- **Writing only “TODO remove” in code:** no owner/deadline/exit.
- **Listing only a team name as owner:** no accountable DRI.
- **Writing only an expiration date:** no technical removal criteria.
- **Writing only “when upstream fixes it”:** no review/escalation date.
- **Keeping the “temporary” label on a design that became permanent:** failing to make a formal architectural decision.
- **Not restricting environments:** test options get copied to production.
- **Omitting JDK/framework versions:** workarounds stay applied erroneously after upgrades.
- **Applying one broad JVM flag to every service:** increases security exposure.
- **Silently extending by editing YAML:** loses audit trail and risk approval.
- **Closing the ticket upon code merge:** runtime/deployment may still retain the workaround.
- **Quarantining tests without reporting skipped tests:** creates a false green CI impression.
- **Pinning dependencies without CVE/upstream review:** prolongs risk.
- **Deleting an adapter the moment new traffic hits 100%:** event replays or legacy consumers may still remain.
- **Deleting records after closure:** loses provenance and decision rationale.
- **Calculating deadlines in different timezones across pipelines:** blocks or ignores on the wrong date.
- **Relying solely on grep without inspecting runtime effective flags:** configuration may come from outside the repository.
- **Using a CI expiry gate with no exception-handling process:** pressures teams into deleting records or changing dates arbitrarily.
- **Approving security-reducing workarounds with only technical review:** lacks risk approval.
- **Ignoring rollback/data compatibility:** removing the workaround may prevent returning to older versions.
- **Measuring reduced workaround counts without verifying code/config removal:** dashboards look clean while risk persists.
- **Hardcoding date-based runtime “time bombs” without design:** expiration can trigger outages.
- **Omitting compensating controls:** unaddressed risks go unmonitored.

## 29. Temporary Measure Acceptance Checklist

Before enabling a workaround:

- [ ] Has a unique ID and links to an issue/PR.
- [ ] States a clear rationale and reproducible migration blocker.
- [ ] Root-cause fixes or lower-risk alternatives were evaluated.
- [ ] Scope specifies concrete service/module/environment/runtime/JDK versions.
- [ ] Includes **explicit exclusions** preventing copy-pasting beyond scope.
- [ ] Has one technical DRI, owning team, and backup.
- [ ] Has a risk/security approver when affecting policy.
- [ ] Includes a risk assessment covering security, data, reliability, and operations.
- [ ] Defines appropriate compensating controls.
- [ ] Records creation date, next review date, and expiry date.
- [ ] Has verifiable exit triggers/criteria.
- [ ] Has a removal task and dependency owners.
- [ ] Includes a rollback plan and regression-detection method.
- [ ] Includes a way to observe whether the workaround is still used.
- [ ] Has a CI/ticket/dashboard mechanism reminding or enforcing the deadline.
- [ ] Contains no secrets/PII in the register or logs.
- [ ] Explicitly records status and approval reference.

Before closing a workaround:

- [ ] Exit condition is met or replaced by an approved architectural decision.
- [ ] Related code, flags, configs, dependencies, and legacy branches are properly removed.
- [ ] Tested without the workaround on target JDKs/frameworks.
- [ ] Verified runtime effective config/deployment no longer contains the workaround.
- [ ] For schemas/adapters, old consumers, retention/replay, and rollback windows were all checked.
- [ ] Risk-appropriate canary/integration/security/performance evidence exists.
- [ ] Runbooks, docs, and sample configs are updated.
- [ ] Ticket/register closed with removal commit/deployment version.
- [ ] Audit trail preserved instead of erasing all records.

## 30. Applied Exercise for a Java Migration Project

**Context:** a team is upgrading the Order service from JDK 11 to JDK 21 while migrating Spring Boot 2 to 3. There are three blockers:

1. One library using deep reflection requires opening a JDK package in tests.
2. One legacy filter only has a `javax.servlet` version, with no Jakarta release yet.
3. Billing still has a consumer reading v1 events.

**Requirement:** design a register for three temporary measures without lumping them into a single “Java 21 workaround”.

### 30.1. Suggested Record Split

| ID | Measure | Scope | DRI | Exit |
|---|---|---|---|---|
| JAVA-MIG-201 | `--add-opens` in test JVM | JDK 21 integration tests, not production | Platform/JVM | Upgrade library and pass without flag |
| JAVA-MIG-202 | Temporary Jakarta filter transform | Orders WAR/Tomcat target | Shared libraries | Official Jakarta filter available |
| JAVA-MIG-203 | Event v1/v2 adapter | Orders/Billing message flow | Messaging | Billing consumer v1 retired + replay plan |

Each measure has its own expiry, risk, approval, ticket, and tests because **they depend on different people and can be removed at different times**.

### 30.2. Questions to Complete the Exercise

- Which measures require security approval?
- Which measures affect production runtime?
- If the filter library gets a new CVE, who decides to halt the transformer?
- When the event adapter is removed, how are messages in DLQ/retention handled?
- If JDK 21 tests fail after removing `--add-opens`, which exit criterion is unmet?
- Can CI detect whether a test flag was copied into production config?
- If an owner leaves before the deadline, what is the ownership handoff workflow?
- Which workarounds might require extension, and who has authority to approve?

The exercise does not prescribe a fixed set of deadlines for every organization; what must be demonstrated is that **each exception has an independent decision structure and a closable lifecycle**.

## 31. References and Supporting Sources

- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): background on module encapsulation and why certain legacy libraries need upgrading.
- [Oracle Java Launcher Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM arguments such as `--add-opens`, which must be checked per JDK release.
- [OpenJDK JEP 451 — Dynamic Agent Loading](https://openjdk.org/jeps/451): considerations for agent permissions and test infrastructure on JDK 21+.
- [OpenRewrite](https://docs.openrewrite.org/): structured source/dependency transformation tooling to replace workarounds with formal migrations.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): binary transformation and artifact migration limits.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration): converting certain web artifacts from Java EE to Jakarta.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API/platform targets and compatibility across the Jakarta ecosystem.
- [Semantic Versioning](https://semver.org/): mental model for managing API version changes; does not replace compatibility tests.
- [Google SRE Workbook — Eliminating Toil](https://sre.google/workbook/eliminating-toil/): context on managing ongoing manual work and operational risk.
- [Architecture Decision Records](https://adr.github.io/): format for documenting architectural decisions and consequences.

These documents serve as directional guidance, not as a mandatory standard turning the sample register into a rigid rule. Every organization should apply its own change-management, security, incident, and release policies. When consulting JVM/framework/tooling docs, always check the documentation for the **exact version pinned** in the project.

## 32. Conclusion

**A temporary measure is only safe during migration when it has boundaries and someone accountable for ending it.** Before adding a JVM flag, dependency pin, compatibility adapter, binary transformer, or feature flag, document **the exact scope, DRI, owning team, deadline, exit criteria, risks, compensating controls, and rollback plan**. Without that information, today's blocker fix can become next year's unowned mystery dependency.

The practical workflow is **propose → assess risk → approve → deploy in narrow scope → monitor/review → verify removal → archive evidence and close**. Use registers/ADRs, issue tracking, and CI guardrails so exceptions are never forgotten; use integration/contract/security tests to prove removal does not break compatibility. When every workaround has a clear owner and deadline, an organization can migrate Java systems step by step without sacrificing long-term maintainability, security, and operations.
