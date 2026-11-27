# Managing Time-Bound Exceptions and Justifying Evidence

Quality gates define the criteria that source code, builds, or deployments must satisfy before advancing through a pipeline. For instance, a pipeline may require unit tests to pass, zero security vulnerabilities above a threshold, minimum test coverage, dependency license compliance, and traceable artifacts.

In practice, a change sometimes cannot immediately satisfy every gate. A scanner may uncover a vulnerability awaiting a vendor patch; a legacy test may be flaky and not fixable right away; a third-party component may lack a compatible replacement version. Teams may still need to keep work moving while addressing the underlying issue. In such cases, a **time-bound exception** permits accepting a specific risk within an approved scope and timeframe, backed by justifying evidence and compensating controls.

An exception is an auditable risk-governance decision. It does not erase scan results, make defects vanish, or turn a failing pipeline into an issue-free one. A proper pipeline preserves the original finding, clearly surfaces which exception applies, who is accountable, why it was accepted, what evidence supports the decision, and when the exception automatically expires.

This is part of **DEVOPS_CI_CD_FUNDAMENTALS**: building CI/CD workflows with quality gates, traceability, secret protection, post-deployment verification, and rollback capability. Exceptions must help teams handle real-world situations while preserving release discipline.

## 1. Why do we need an exception mechanism?

Quality gates establish a shared standard for deciding whether a change is eligible to advance. If every finding blocks indefinitely, teams may be unable to handle situations needing prompt decisions. Yet if anyone can bypass gates arbitrarily, gates lose all meaning.

A controlled exception mechanism helps address scenarios such as:

- A confirmed vulnerability for which the vendor has not yet released a safe patch.
- A scanner false positive or a code path unreachable/unexploitable in the current context, requiring supporting evidence.
- An integration test flaking due to an external dependency; the team needs time to fix it while keeping visibility.
- A library with an unclassified license; a temporary decision is needed while the responsible team completes review.
- A quality threshold impacted by legacy code while the new change makes nothing worse; the team needs a technical debt reduction roadmap.

Exceptions are not the default response to every gate failure. First look to fix the root cause, update tooling, correct misconfigured rules, or supply evidence for a false positive. Use an exception only when genuine risk or an unmet criterion remains that requires an explicit acceptance decision.

Certain requirements may be non-waivable under internal policy, contracts, or regulation. For example, an organization may forbid releasing when an active secret is detected in the repository or a confirmed critical vulnerability exists. No exception approval may override a non-waivable requirement.

## 2. Distinguishing exceptions from other dispositions

The statuses below have distinct meanings and must be stored separately:

| Disposition | When to use | What happens to the gate |
| --- | --- | --- |
| Remediation | The finding is valid and fixable | Rerun checks; the gate passes only when conditions are met |
| Policy correction | A rule is misconfigured or no longer appropriate | Update policy with review; rerun checks across the affected scope |
| Confirmed false positive | The finding poses no real risk, backed by technical evidence | Record disposition and evidence; keep audit trail so it is not silently ignored |
| Time-bound exception | The finding or unmet condition is real, yet the risk is temporarily accepted | Permits only the approved scope; retains the finding and expiration date |
| Manual bypass | Skipping checks without records or controls | Not a valid exception mechanism; destroys auditability |

False positives and risk-acceptance exceptions must not be used interchangeably. With a false positive, the team asserts the detection is incorrect in the given context and provides proof. With an exception, the team acknowledges the condition or risk exists but accepts it temporarily with rationale and compensating controls.

For example, suppose a scanner flags a dependency CVE. If the team verifies the application does not use the affected module and configures packaging to exclude it, a false-positive or not-affected disposition may be appropriate per tool policy. If the application does use the affected module but enforces a compensating control, that is temporary risk acceptance; the finding must still be tracked.

Never alter severities, delete findings, or edit scan outputs just to make the pipeline green. Preserve raw original evidence and store disposition decisions as separate records.

## 3. Principles of a valid exception

An exception should adhere to the following principles:

1. **Specific:** applies strictly to one clearly identified finding, rule, or condition.
2. **Justified:** explains why immediate remediation is not feasible and why proceeding is acceptable.
3. **Evidenced:** links scan results, logs, impact analysis, tickets, or supporting technical documentation.
4. **Accountable:** identifies an owner responsible for remediation and an authorized risk approver.
5. **Time-bound:** records start and expiration timestamps; never grant open-ended exceptions.
6. **Compensated:** reduces likelihood or impact while awaiting remediation.
7. **Auditable:** retains history of creation, approval, renewal, revocation, and usage.
8. **Revocable:** when conditions shift or evidence becomes invalid, the exception must be invalidated.

Exceptions must bind to a concrete target. An approval for CVE-2026-12345 in dependency X at version 2.4.1 must not automatically cover all CVEs in dependency X, version 2.5.0, or another repository. Likewise, an exception for one test may apply by test ID and suite scope; never waive the entire integration test suite.

## 4. Classifying risk before requesting an exception

Not all findings carry equal severity. Before requesting an exception, assess residual risk in real context:

- **Severity:** technical or business impact if the issue is exploited or triggered.
- **Exploitability/likelihood:** is there a practical access path, what preconditions exist, can tests reproduce it?
- **Exposure:** is the component accessible from the Internet, internal network, privileged users, or only inside an isolated environment?
- **Blast radius:** one job, one service, one user segment, or the entire system?
- **Detectability:** will logs, alerts, and monitoring detect issues before impact spreads?
- **Recoverability:** can features be disabled, artifacts rolled back, or data restored within an acceptable timeframe?

A simple matrix can help classify requests:

| Risk level | Examples | Typical handling |
| --- | --- | --- |
| Low | Low-impact finding, tightly bounded, unrelated to sensitive data | Owner remediates on a short timeline; approval per team policy |
| Medium | Impacted component has compensating controls and limited exposure | Requires owner and security/domain specialist approval |
| High | Practical exploit path or major impact on data/services | Blocked by default; considered only if permitted by policy with appropriate approval tier |
| Critical or non-waivable | Exposed active production secret, exploitable critical flaw prohibited from waivers | No exception granted; remediate or isolate before proceeding |

This matrix is solely a process design example. Severity thresholds, durations, and approval tiers must align with organizational policy, system type, and compliance obligations. Do not impose a single uniform threshold across every product.

If an exception alters production risk, the approver must understand the production environment and real impact. A test passing in staging does not by itself prove production risk is controlled.

## 5. What should an exception record contain?

An exception record should hold enough detail for someone outside the original conversation to understand the decision. Minimum fields:

| Field | Contents to record |
| --- | --- |
| Exception ID | Unique identifier referenced in logs, tickets, and pipelines |
| Finding/control ID | Specific CVE, rule ID, test ID, policy ID, or gate criterion |
| Resource and version | Affected repository, service, artifact, dependency, or commit |
| Scope | Applicable branch, environment, product, version, and boundary |
| Rationale | Why immediate fix is blocked and why accepting risk briefly is justified |
| Evidence | Scan reports, logs, reproductions, impact analysis, tickets, or technical docs |
| Risk assessment | Severity, exploitability, exposure, impact, and residual risk |
| Compensating controls | Temporary measures reducing risk |
| Owner | Person accountable for remediation and progress updates |
| Approver | Person or role authorized to accept the risk |
| Created/approved at | Creation and approval timestamps |
| Expires at | Timestamp when the exception automatically expires |
| Remediation plan | Work items, ticket, and target completion milestone |
| Status/history | Pending, approved, expired, revoked, remediated, or rejected with change history |

Evidence must never be a vague line like "checked and safe." Attach timestamped scan results bound to the commit/artifact, reproduction logs, affected-module analysis, network configuration, test outputs, or linked tickets with owners and due dates. If evidence contains sensitive data, store it in an access-controlled system and reference only authorized IDs or locations.

### 5.1. Example exception record

The YAML below is an illustrative schema for discussion, not a built-in format for every CI platform:

~~~yaml
exception:
  id: EXC-2026-0042
  finding:
    control_id: DEP-VULN-123
    type: dependency-vulnerability
    component: com.example:legacy-client
    version: 2.4.1
  scope:
    repository: order-service
    branch: main
    environment: staging
    artifact_digest: sha256:example-digest
  rationale: >
    A compatible patch has not yet been released by the vendor.
    The component is used only through an internal adapter with restricted endpoints.
  risk:
    severity: high
    exposure: internal-only
    residual: medium
  evidence:
    - scan-report-id: SEC-SCAN-8821
    - analysis-ticket: SEC-314
  compensating_controls:
    - Restrict outbound access to approved endpoint
    - Add request validation and enhanced monitoring
  owner: team-order-platform
  approver: application-security-lead
  approved_at: "2026-11-18T09:00:00Z"
  expires_at: "2026-12-02T09:00:00Z"
  remediation_ticket: SEC-314
  status: approved
~~~

This example illustrates recording a specific finding, a specific artifact, the staging environment, compensating controls, and an expiration date. In real systems, use accessible evidence IDs, exact digests, real approvers, and system-generated timestamps. Never copy example values verbatim into release records.

## 6. What questions must justifying evidence answer?

An exception acceptance decision requires evidence covering both why remediation cannot happen immediately and how risk is controlled:

**About the finding**

- Which tool detected it, what tool version, and what rule ID?
- Which commit, image, or artifact contains the finding?
- Is it reproducible? What is the data path or trigger condition?
- Is the scan result still fresh relative to the artifact scheduled for deployment?

**About the impact**

- Is the affected component invoked in actual execution paths?
- From where and by whom is it reachable?
- What data or functionality could be impacted?
- What happens if the risk materializes during the exception window?

**About compensating controls**

- Which measures lower exploitability or limit impact?
- Have those measures been deployed and verified?
- Do logs/alerts exist to detect anomalous signs?
- Can the feature be toggled off or rolled back?

**About the remediation plan**

- Which ticket tracks the work?
- Who is the owner?
- What milestone is targeted for completion?
- If the deadline arrives and the fix is not ready, what is the next action?

Evidence must match the exact scope. A scan report from an older branch does not prove a new artifact is clean; a staging test does not prove production shares the same configuration. If commits, dependency versions, or artifact digests change, check whether the exception still applies or requires re-approval.

## 7. Expiration, renewal, and automatic revocation

Exceptions must carry an explicit expiration date. Never use values like "until fixed," "temporary," or "when time permits" as the sole duration. You may note completion criteria, yet a concrete deadline is still required.

Durations should scale with risk:

- High risk requires very short durations and frequent monitoring.
- Medium risk may carry slightly longer durations if compensating controls are strong.
- Low risk still needs a review date and expiration date.

For example, an internal policy might cap waivable high-risk findings at 7 days, medium risk at 14 days, and low risk at 30 days. These are only examples; organizations must set their own limits based on risk levels and compliance obligations.

When an exception expires:

1. The system transitions its status to `expired` or invalid.
2. The quality gate re-enforces the original policy for that finding.
3. New pipeline runs block if the finding persists and no valid new decision exists.
4. Owner and approver receive notifications per organizational channels.
5. Exception history stays preserved for audits.

Do not let the pipeline automatically treat an old exception as active simply because the finding ID matches. The system must evaluate expiration timestamp, status, scope, and associated artifact/commit on every run.

### 7.1. Renewal is not a mechanical date extension

If renewal is needed, the owner must update:

- Remediation progress and why completion was delayed.
- Latest evidence confirming risk remains within the assessed bounds.
- Effectiveness of compensating controls.
- New expiration date and next remediation milestone.
- Any changes to scope, severity, exposure, or artifact.

Renewals must be re-approved under policy. Never let owners self-renew their own exceptions when policy mandates separation of duties. Renewal counts should be capped or require higher-level sign-off past a threshold.

### 7.2. Early revocation

An exception can be revoked prior to expiration if:

- New intelligence increases severity or exploitability.
- Compensating controls stop functioning.
- Usage expands into production or sensitive data paths.
- Artifacts or dependencies change, invalidating the original assessment.
- The owner fails to execute the remediation plan.
- Supporting evidence is discovered to be wrong or incomplete.

Upon revocation, the gate must immediately re-enforce on the next run, and the organization must decide whether to halt rollouts or pull back deployed artifacts.

## 8. Workflow for creating and approving exceptions

A workflow can follow these steps:

1. **Detection:** pipeline surfaces a finding and stores scan/test results alongside the commit, artifact, or release ID.
2. **Triage:** owner determines whether the finding is a true defect, false positive, policy misconfiguration, or risk requiring temporary acceptance.
3. **Remediate first:** if safely fixable, fix and rerun the gate.
4. **Request exception:** if unfixable immediately, file a record with scope, rationale, evidence, risk assessment, controls, owner, approver, and expiry.
5. **Independent review:** a qualified reviewer inspects evidence, risk level, and compensating controls.
6. **Approve or reject:** system logs identity, timestamp, and decision.
7. **Pipeline evaluation:** policy engine applies the exception only when finding matches exactly, status is `approved`, scope matches, and expiry has not passed.
8. **Tracking:** owner drives remediation, updates evidence, and receives pre-expiry reminders.
9. **Closure:** once fixed and passing the gate, mark `remediated`; if expired or revoked, the gate reverts to blocking per policy.

Requesters must not self-approve their own risk when separation of duties applies. For security findings, approvers need appropriate authority such as a security owner or risk owner. For data quality or test reliability issues, both system owners and quality owners may be needed.

Chat or verbal discussions may assist coordination, yet formal decisions must be recorded in a system with access controls and an audit trail. Pipelines must reference stored exception records rather than relying on free-form PR comments.

## 9. Evaluating exceptions in policy-as-code

The policy engine must evaluate findings and exceptions using verifiable rules. General logic:

~~~text
for each finding:
    if finding is resolved:
        continue

    if finding is explicitly non-waivable:
        block pipeline
        continue

    exception = find_exact_match(
        finding_id,
        repository,
        resource_version,
        environment
    )

    if exception is missing:
        block pipeline
    else if exception.status is not approved:
        block pipeline
    else if now >= exception.expires_at:
        block pipeline
    else if evidence is missing or scope does not match:
        block pipeline
    else:
        record accepted_exception
        continue with visible exception status
~~~

This is conceptual pseudo-code, not syntax for a specific CI product. When implementing, use UTC timestamps from a trusted source, compare expirations unambiguously, and prevent pipelines from mutating exception records themselves.

Evaluation outputs should distinguish:

| Outcome | Meaning |
| --- | --- |
| PASS | Zero blocking findings and no exceptions needed |
| BLOCKED | Unresolved findings exist or exception is invalid |
| ACCEPTED_WITH_EXCEPTION | Findings temporarily accepted under a valid record |
| EXPIRED | Exception expired; original gate re-enforced |
| REVOKED | Exception revoked prior to expiration |

If the organization permits proceeding under `ACCEPTED_WITH_EXCEPTION`, that status must appear prominently in pipeline results, release reports, and audit logs. Never rewrite it to plain `PASS`, as doing so hides from reviewers that the artifact carries accepted risk.

Some systems may require additional approval before production deployment even when an exception is valid. Accepting risk and authorizing a release are two distinct governance steps.

## 10. Integrating with pull requests and release workflows

Exceptions should surface wherever users make decisions:

- In PRs, display the finding, exception status, owner, and expiration date.
- Before merging, verify whether the exception applies to the intended commit.
- Before building artifacts, snapshot gate outcomes and exception IDs.
- Before deploying, recheck expiry, scope, and approval status.
- After deploying, link the release ID to used findings and exception records.

Do not check exceptions solely at PR creation time. An exception can expire between merge and production deployment. Pipelines must re-evaluate at every major gate, especially before granting deployment privileges.

If an exception applies only to staging, never carry it automatically to production. If an exception binds to a specific artifact digest, rebuilding the artifact with a new digest requires re-evaluation. If an exception binds to a commit but dependencies or security configs change, verify whether original evidence still holds.

## 11. Example: temporarily accepting a dependency vulnerability

Suppose a scanner flags a CVE in a library used by a service. The vendor has not released a compatible patch; upgrading immediately breaks API contracts with another system. The team needs to ship a small business-logic fix.

The workflow could look like:

1. Verify the CVE affects the exact packaged dependency version; record the scanner report and artifact SBOM.
2. Analyze usage paths: is the vulnerable module invoked, what data can reach it, and is the service Internet-exposed?
3. Try direct remediation first, such as a compatible patch upgrade, stripping unused modules, or safe configuration.
4. If unfixable immediately, file an exception for the exact CVE, dependency version, repository, and artifact digest.
5. Add compensating controls such as outbound restrictions, input validation, disabling affected endpoints, or heightened monitoring appropriate to the root cause.
6. Assign an upgrade ticket to the owner, set a short expiration date, and require a security approver to accept residual risk.
7. The pipeline keeps the finding visible as an exception and records the exception ID in release reports.
8. Once a compatible patch ships, upgrade the dependency, rerun scans/tests, and close the exception after the gate passes.

If compensating controls do not genuinely reduce risk, or organizational policy prohibits waiving that severity, never release solely because a ticket and approval signature exist.

## 12. Example: exception for a flaky test

Suppose an integration test occasionally times out due to a third-party service in the test environment. The test covers a critical flow and cannot be deleted permanently.

A valid exception needs to:

- Name the specific test ID or suite.
- Include failure logs and frequency statistics.
- Show the root cause lies in an environment dependency rather than a known product defect.
- Retain an alternative check or smoke test covering the related business flow.
- Assign an owner to fix synchronization, timeouts, or test fixtures.
- Set an expiry and track how often the test is skipped.

Never disable the entire integration suite or convert every timeout into success. If a test is temporarily quarantined, the pipeline must visibly mark it quarantined, show an accountable owner, and enforce a recovery deadline. A skipped test must never be reported as a passed test.

## 13. Tracking exceptions and auditing

Exceptions represent risk debt with an owner and a deadline. Teams should track at minimum:

- Active exceptions grouped by risk level.
- Exceptions nearing expiration and already overdue.
- Renewal counts for the same finding or owner.
- Mean time from exception creation to remediation.
- Percentage of exceptions closed on time.
- Gate blocks caused by mismatched exception scope or expiry.
- Findings that reoccur after being marked remediated.

The audit trail must record who created, who approved, who altered scope, old/new deadlines, renewal rationale, who revoked, and which pipeline/release used the exception. Never overwrite prior history when updating records; append new events or revisions.

A useful report does more than count total exceptions. It highlights long-lived risks, teams frequently requesting renewals, and controls failing to drive remediation. That insight helps teams improve platforms, upgrade dependencies, or refine quality gate rules.

## 14. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Exceptions without expiration dates | Temporary risks become permanent | Mandate expiry and mark expired automatically |
| Rationale says only "urgent release" | No evidence to assess risk | Record finding, impact, evidence, and controls |
| Owners self-approve all exceptions | Lacks independent review | Separate requester, owner, and approver per policy |
| Exceptions covering whole rules or repos | Ignores unrelated findings | Scope strictly by finding, version, scope, and environment |
| Editing scanners to hide findings | Loses raw evidence and history | Preserve raw findings; record disposition separately |
| Caches or stale artifacts covered by old exceptions | Evidence mismatches current inputs | Bind exceptions to commit/digest and recheck on change |
| Unlimited renewals | Risk debt accumulates | Cap renewals; require fresh evidence and higher-tier sign-off |
| Checking expiry only at merge | Exceptions may expire before deployment | Re-evaluate at every major gate |
| Reporting exceptions as PASS | Releasers cannot see residual risk | Use a distinct `ACCEPTED_WITH_EXCEPTION` status |
| Using exceptions to bypass non-waivable rules | Violates policy or compliance obligations | Define non-waivable controls and always block |

## 15. Pre-acceptance exception checklist

**Scope and rationale**

- [ ] Finding or control ID is precisely identified.
- [ ] Repository, resource, version, commit/artifact, and environment are explicitly stated.
- [ ] Direct remediation was attempted or evaluated.
- [ ] Reason immediate remediation is blocked is clearly explained.
- [ ] Confirmed this control is waivable under policy.

**Risk and evidence**

- [ ] Severity, exposure, impact, and residual risk are assessed.
- [ ] Supporting scan reports, logs, reproductions, or analyses are attached.
- [ ] Evidence matches the exact commit/artifact under review.
- [ ] Compensating controls are feasible and verified.
- [ ] Rollback or blast-radius containment plan exists if needed.

**Accountability and timeframe**

- [ ] Accountable owner and authorized approver are identified.
- [ ] Requester does not self-approve when separation of duties applies.
- [ ] Remediation ticket and milestone exist.
- [ ] Explicit UTC expiration timestamp is set.
- [ ] Reminders, renewal, revocation, and automatic gate re-enforcement exist.

**Pipeline and audit**

- [ ] Pipeline evaluates scope, status, and expiry at decision time.
- [ ] Original finding remains stored and visible.
- [ ] `ACCEPTED_WITH_EXCEPTION` outcome is distinguished from `PASS`.
- [ ] Exception ID links to commit, artifact, and release.
- [ ] History of creation, approval, renewal, and revocation is auditable.

## Conclusion

Time-bound exceptions provide a controlled way to accept risk when a quality gate cannot be satisfied immediately. A valid record must pinpoint the finding and scope, explain rationale, attach evidence, assess residual risk, establish compensating controls, and name an owner, approver, and expiration date. Pipelines must recheck exception status and scope at critical gates, preserve original findings, and clearly signal releases accepted under exception.

Once an exception expires, is revoked, or ceases to match the current artifact, the quality gate must re-enforce. Once the issue is fixed, rerun checks and close the record with fresh evidence. This approach helps teams handle practical constraints while upholding CI/CD traceability, accountability, and release discipline.
