# Releasing Features by User Cohorts or Stages

A new build does not have to make a new feature visible to every user immediately. A team can deploy code to production while keeping the feature turned off, then enable it for internal employees, a group of beta customers, or a small percentage of users. Once operational data shows that the feature is stable and delivering expected outcomes, the team gradually expands it to subsequent cohorts.

This release approach typically uses **feature flags** combined with a **staged rollout** (or **progressive rollout**). It separates the moment code is deployed from the moment users gain access to the new behavior, limiting the blast radius and creating an opportunity to halt or narrow the rollout if issues arise.

This is part of the **DEVOPS_CI_CD_FUNDAMENTALS** capability: building CI/CD thinking from Git events, pipelines as code, automated builds and testing to artifact management, environments, quality gates, traceable releases, secret protection, post-deployment verification, and rollback capability.

## 1. Distinguishing deploy, release, and exposure

These three moments are often grouped together under "releasing", yet they represent distinct activities:

- **Deploy:** placing an artifact or application version into an environment.
- **Release:** allowing a product capability or change to be used.
- **Exposure:** users or user cohorts actually seeing or using the feature.

For example, a team deploys version 2.4.0 to production on Monday while keeping the e-wallet payment feature turned off. On Tuesday, the team opens it to internal employees. On Wednesday, it opens to 5% of eligible accounts. If metrics remain stable, the team continues increasing the percentage over subsequent days.

In this example, the artifact was already deployed before the feature was widely released. The team can fix bugs, verify configurations, and prepare operations before turning the feature on for a broad user base.

Separating these concepts gives the pipeline two distinct types of decisions:

1. Quality gates determine whether an artifact is eligible to be deployed.
2. Rollout gates determine whether a feature is eligible to expand to the next user cohort.

Feature flags do not replace testing, quality gates, or rollback procedures. They are a mechanism for controlling exposure while the code already exists inside the application.

## 2. What is a feature flag?

A feature flag is a configuration condition that lets an application select behavior at runtime. Instead of creating a new build to turn a feature on or off, the application reads the flag state and decides which execution branch to take.

Simple example:

~~~java
if (featureFlags.isEnabled("new-checkout", userContext)) {
    return newCheckoutService.checkout(request);
}

return legacyCheckoutService.checkout(request);
~~~

Flags can be stored in application config, a database, a feature flag management service, or a progressive delivery platform. What matters is that the application can evaluate the flag against a defined context and the team can adjust exposure scope through a controlled workflow.

### 2.1. Common flag types

| Flag type | Purpose | Typical lifecycle |
| --- | --- | --- |
| Release toggle | Hide a new feature until ready for release | Temporary; should be removed after rollout completes |
| Experiment toggle | Split users into variants to measure impact | Time-bound by the experiment plan |
| Operational kill switch | Quickly disable behavior risking an incident | May live longer, but must be tested and governed |
| Permission/entitlement toggle | Control access by service plan or entitlement | Usually tied to the business permission model |

Do not use a single flag for multiple unrelated goals. For instance, a flag used to enable a feature during release should not simultaneously serve as a mechanism granting access to sensitive data. Business permissions must be checked by an independent authorization policy.

## 3. Releasing by user cohorts and by percentage

There are two common ways to restrict exposure:

**Cohort targeting:** enabling only for users who satisfy specific conditions, such as internal employees, test accounts, an opted-in customer group, or selected tenants.

**Percentage rollout:** enabling for a defined percentage of the eligible population, such as 1%, 5%, 10%, 25%, 50%, and then 100%.

Both can be combined. For example, first only internal employees have access; next, 5% of customers in one region; then 20% of paid accounts; and finally all eligible users.

Commonly selected cohorts include:

- Employees or internal accounts (dogfooding).
- Customers enrolled in a beta program.
- Partner tenants or organizations that agreed to test early.
- Users in a specific region or on a specific platform.
- A controlled random sample percentage of users.
- Users on an application version meeting compatibility requirements.

The team must define criteria that are clear, testable, and have an owner. Avoid vague conditions like "some important customers" without a deterministic list or rule.

## 4. The staged rollout workflow

A staged rollout typically moves through the following steps:

1. **Dark launch:** deploy code to production with the flag off; verify the application starts and the legacy branch still works.
2. **Internal rollout:** open to employees or test accounts.
3. **Limited cohort:** open to a small, pre-selected group.
4. **Small percentage:** open to a small percentage of eligible users.
5. **Progressive expansion:** step up the percentage along planned milestones.
6. **General availability:** open to the entire eligible audience.
7. **Cleanup:** remove the legacy code branch and release flag when no longer needed.

Diagram:

~~~mermaid
flowchart TD
    A["Deploy artifact with flag OFF"] --> B["Smoke test and verify legacy branch"]
    B --> C["Enable for internal employees"]
    C --> D["Evaluate metrics and feedback"]
    D --> E{"Guardrails met?"}
    E -- "No" --> X["Halt rollout / disable flag"]
    E -- "Yes" --> F["Open small cohort"]
    F --> G["Evaluate over observation window"]
    G --> H{"Guardrails met?"}
    H -- "No" --> X
    H -- "Yes" --> I["Increase percentage incrementally"]
    I --> J{"Ready for GA?"}
    J -- "Not yet" --> G
    J -- "Yes" --> K["Open to full eligible audience"]
    K --> L["Monitor and clean up release flag"]
~~~

No single rollout schedule fits every product. A service handling millions of requests per hour can gather enough data quickly; a B2B product with a few dozen transactions per day requires a longer observation window. Every stage must have explicit criteria to proceed, halt, or revert.

## 5. Establishing stable and consistent cohorts

When selecting users by percentage, the same person should receive the same decision throughout the rollout, unless policy deliberately changes the assignment.

If every request chooses randomly and independently, a user may see the new UI on one request and the old UI on the next. That causes confusion, breaks sessions, or makes analytics inconsistent.

### 5.1. Deterministic bucketing

A common approach computes a bucket from the flag key and a stable identifier for the user or tenant:

~~~text
input = flag_key + ":" + stable_subject_id + ":" + rollout_salt
hash_value = SHA256(input)
bucket = unsigned_first_64_bits(hash_value) mod 10000
enabled = bucket < rollout_percentage * 100
~~~

With 10,000 buckets, each bucket represents 0.01%. If the rollout percentage is 5%, the system enables the flag for buckets 0 through 499. The same subject ID, flag key, and salt always yield the same bucket.

The subject identifier can be an internal user ID or tenant ID depending on rollout scope. Do not put emails, phone numbers, or direct identifiers into keys sent to external services. Hashing an email does not automatically make that data anonymous; use proper pseudonymous identifiers and control access.

### 5.2. Preserving assignment when increasing percentage

Using the same algorithm, key, and salt, increasing the percentage from 5% to 10% retains the original 5% cohort and adds subjects in the next buckets. This is a valuable property of deterministic bucketing.

Do not change the salt or bucketing function between stages if you want existing cohorts preserved. If you intentionally need to reshuffle cohorts, create a new rollout or experiment and record the timestamp of the change.

### 5.3. Choosing the right bucketing unit

For consumer products, bucketing by user ID works well. For B2B products, consider tenant/account ID so everyone in the same organization has a consistent experience. For multi-device systems, assignment may need to be tied to the account rather than the device.

If a tenant has multiple users and only some see the new feature, they may be unable to share data or workflows with colleagues. The bucketing unit should match business boundaries.

## 6. Designing targeting rules

Targeting rules decide who is eligible before percentage rollout applies. Example:

~~~yaml
feature:
  key: new-checkout
  enabled: true
  targeting:
    allowlist:
      - user-test-001
      - tenant-beta-042
    rules:
      - attribute: region
        operator: in
        values: [vn, sg]
      - attribute: app_version
        operator: greater_than_or_equal
        value: 2.4.0
    rollout:
      percentage: 5
      subject: tenant_id
      salt: checkout-rollout-2026-01
~~~

This is an illustrative configuration; the exact precedence combining allowlists, rules, and percentages must be clearly defined in the flag system. Never assume rules in a list combine with OR or AND unless the tool specifies it.

Questions to answer:

- Does the allowlist take precedence over general rules?
- How are users missing a required attribute handled?
- Are multiple rules combined using AND or OR?
- Can an excluded tenant still enter via the allowlist?
- When targeting is updated, do prior assignments change?
- Can you trace which config version determined a given exposure?

Targeting should be verified automatically with test cases covering enabled, disabled, missing attributes, malformed formats, and conflicting rules. Never allow a config parsing error to accidentally expose a feature to all users.

## 7. Making expansion decisions based on guardrails

Every stage needs evaluation criteria agreed upon before expanding. Do not raise percentages just because "nobody has complained yet."

### 7.1. Technical guardrails

- Error rate and failed request ratio.
- p50, p95, and p99 latency.
- Timeouts, retries, and connection errors.
- CPU, memory, thread pools, and connection pools.
- Database load, locks, and query latency.
- Queue lag and dead-letter/failed message counts.
- Crash rate on mobile or desktop clients.

### 7.2. Business guardrails

- Completion rate of the core workflow.
- Payment or transaction success rate.
- Cancellation, refund, or abandonment rate.
- Volume of support tickets and negative feedback.
- Rate of returning users or desired action completion.

A feature's success metric must be distinguished from guardrails. For example, the goal may be increasing checkout completion rate, while the guardrails ensure payment errors, response times, and refund rates do not worsen.

### 7.3. Setting thresholds and observation windows

Thresholds should reflect baselines, SLOs, and the criticality of the business flow. Illustrative example:

| Signal | Proceed condition | Halt/re-evaluate condition |
| --- | --- | --- |
| HTTP 5xx | Does not exceed baseline plus allowed margin | Exceeds defined threshold during observation window |
| p95 latency | Within SLO | Continuously breaches SLO or spikes sharply over baseline |
| Payment success | No significant degradation | Drops beyond threshold or produces incorrect transactions |
| Crash-free sessions | Within quality target | Crashes rise for the version or cohort |
| Queue lag | Stable within limits | Sustained growth causing business delays |

Concrete numbers must be set by the service owner using real-world data. With low traffic, allow a longer observation window to avoid drawing conclusions from a handful of requests. For severe incidents such as data corruption or duplicate payments, do not wait for the statistical window to finish before halting the rollout.

## 8. Observing exposure and behavior per cohort

To understand whether a feature is performing well, you need to know which users evaluated the flag, who actually received exposure, and what outcomes they experienced.

Record the following events:

- Flag evaluation: what result the system returned when evaluating the flag.
- Assignment: which cohort or variant the subject was placed in.
- Exposure: the feature was actually rendered or used.
- Outcome: business actions following exposure.

Not every flag evaluation counts as an exposure. A backend request might check a flag before the user ever sees the UI or takes an action. Using evaluation events as the conversion denominator can skew results.

Metrics and logs should include:

- Flag key and configuration version.
- Cohort/variant or rollout stage.
- Application version and artifact digest where relevant.
- Region, platform, or tenant segment per policy.
- Request/correlation ID for investigation.

Avoid putting personal identifiers directly into metric labels, as this causes high cardinality and leaks data. Use pseudonymous IDs or appropriate aggregates, and limit retention and access permissions.

## 9. How does feature rollout differ from A/B testing?

Staged rollouts and A/B testing can both use feature flags, yet they answer different questions:

| Aspect | Staged rollout | A/B testing |
| --- | --- | --- |
| Goal | Reduce release risk and verify stability | Measure relative causal impact across variants |
| User groups | Gradually expanded by allowlist or percentage | Grouped according to experimental design |
| Expansion criteria | Technical/business guardrails pass | Sufficient sample size and planned statistical analysis |
| Duration | Based on risk and stability | Based on duration needed to gather sample size |
| Outcome | Decide to continue, pause, or expand release | Select a variant or conclude no reliable difference |

Do not claim a feature is superior simply because a 10% rolled-out cohort shows higher conversion than the rest. Cohorts can differ by region, timing, account type, or prior behavior. A/B testing requires randomized assignment by design, a defined primary metric, sample size, duration, and handling of multiple comparisons.

In a staged rollout, teams can use cohort data to catch bugs, but the primary objective is release safety. If you want to measure product impact, design a dedicated experiment or apply appropriate analytical methods.

## 10. Kill switches and halting rollouts

A kill switch is a mechanism to rapidly disable a behavior during an incident. It is invaluable when a rollout uncovers severe errors, provided it is designed and tested beforehand.

An effective kill switch:

- Can be triggered by authorized personnel or policy-driven automation.
- Has a known, measurable configuration propagation delay.
- Has safe default behavior when the flag service is unreachable.
- Has logs/audits capturing who changed it, when, and why.
- Does not depend on the failing feature itself in order to turn off.
- Has been rehearsed in staging or a test environment.

The default when a flag cannot be read must be chosen based on risk. For an unproven new feature, default OFF is usually safer. For an essential, stable operational capability, defaulting to off could take the system down. Define fallbacks per flag rather than applying a blanket rule.

Turning off a flag also does not always reverse side effects that have already happened. If a feature wrote data in a new schema, emitted messages, created transactions, or sent emails, the kill switch only stops future executions. You still need procedures for handling already-generated data and transactions.

## 11. Consistency when flags are evaluated in multiple places

A distributed application may evaluate the same flag across frontend, backend, workers, and multiple services. If different components receive different configuration versions, users can experience inconsistent behavior.

Decide on:

- Is the flag evaluated on the client or server?
- Is the server the source of truth for sensitive actions?
- How long is configuration cached?
- When the flag service disconnects, use the last known value or the fallback?
- How do frontend and backend agree on the same cohort?
- Should assignment be passed in request context or an internal token?

For data access, payments, or security-sensitive actions, the backend must enforce authorization independently. Never trust flag decisions sent by the client, as users can tamper with requests or run older client builds.

For mobile apps, clients may go un-updated for weeks or months. The backend must remain compatible with older versions; you cannot assume every device receives new configs and code simultaneously.

## 12. Data compatibility and side effects during rollout

Rolling out features by cohort means multiple versions of behavior coexist. Some users may write data in a new format while others still use the old format.

Apply these principles:

- Expand schemas first; remove old schemas only after no client needs them.
- Keep APIs backward-compatible throughout the rollout window.
- Use idempotency keys for operations with side effects.
- Ensure event schemas are versioned and consumers handle all active versions.
- Avoid splitting the same tenant across two incompatible data flows.
- Have a backfill and data-remediation plan if the feature must be turned off.

For example, a new checkout feature adds a `payment_method_v2` field. Before enabling it for customers, the database can add the new field as nullable while the backend continues reading legacy data. Only after the rollout completes and all flows have migrated does the team plan to drop the legacy field in a separate change.

If the feature only presents a new UI calling the same stable API, data risk may be lower. If it modifies logic that writes money, inventory, or access permissions, deeper review and stricter business guardrails are needed.

## 13. Security and privacy in targeting

Targeting may use region, tenant, plan, app version, or account attributes. This data can affect user entitlements and occasionally involves sensitive information.

Recommended practices:

- Use only attributes strictly necessary for the rollout goal.
- Avoid sensitive attributes or personal data without proper justification and approval.
- Do not let clients self-assert attributes that unlock entitlements.
- Resolve tenant/user context from trusted server-side sources.
- Restrict who can modify targeting rules and percentages.
- Audit all flag changes, especially flags affecting payments, access, or data.
- Never write PII into logs or metric labels.

Feature flags are not authorization. If a flag opens for a cohort, the backend must still check whether the user is authorized to access the resource. Users outside the cohort must not be able to call the API directly to bypass hidden UI.

## 14. Integrating staged rollouts into CI/CD

The pipeline can be split into two connected streams:

**Build and deploy stream**

1. Check out the reviewed commit.
2. Build the artifact and run tests.
3. Run quality gates, scans, and generate provenance/SBOM if required by policy.
4. Deploy the artifact to production with the release flag OFF.
5. Run smoke tests on the legacy branch and verify flag evaluation works.

**Feature expansion stream**

1. Verify owner, goal, cohort, and guardrails.
2. Approve targeting or rollout percentage changes.
3. Update versioned, audited flag configuration.
4. Observe metrics by cohort and application version.
5. Automatically or manually evaluate expansion criteria.
6. Increase percentage, hold steady, halt, or disable the flag.
7. Upon reaching GA, schedule removal of the flag and legacy code.

Not every percentage change requires rebuilding the artifact. Flag config can be managed separately, provided it has access controls, reviews, auditing, and configuration rollback capability.

### 14.1. Example rollout configuration

~~~yaml
release:
  feature: new-checkout
  owner: team-commerce
  artifact:
    version: 2.4.0
    digest: sha256:example-digest
  stages:
    - name: internal
      target: allowlist
      approval: product-and-engineering
    - name: beta
      target:
        tenants: [tenant-beta-01, tenant-beta-02]
      observation_window: 24h
    - name: percentage-5
      percentage: 5
      observation_window: 2h
    - name: percentage-25
      percentage: 25
      observation_window: 4h
    - name: general-availability
      percentage: 100
      approval: release-owner
  guardrails:
    max_error_rate: defined-by-service-slo
    latency_slo: defined-by-service-slo
    business_metric: checkout_success_rate
  rollback:
    action: disable-feature-flag
    owner: on-call-commerce
~~~

This is an illustrative configuration, not a schema for a specific CI platform. Threshold values must be replaced with real SLOs. In an actual system, you must define stage ordering, promotion conditions, percentage calculation, handling when the flag service is unavailable, and who can approve.

### 14.2. Automating expansion conditions

A policy can express logic like:

~~~text
if all_required_metrics_are_available
   and error_rate <= approved_error_threshold
   and latency_p95 <= approved_latency_threshold
   and business_guardrails_pass
   and observation_window_completed:
       allow_next_stage
else:
       hold_rollout

if critical_incident_detected:
       disable_feature_flag
       notify_on_call
       create_incident_record
~~~

This is a pseudo-policy. In a real implementation, handle missing metrics, telemetry delay, low traffic, noisy alerts, and permissions for automated actions. Never auto-expand if the monitoring system lacks sufficient data to evaluate.

## 15. Managing feature flag lifecycle and cleanup

Flags make rollouts flexible, but every flag adds an extra logical branch that must be tested. Without cleanup, the codebase accumulates confusing states.

Every flag should carry metadata:

- Unique key and behavioral description.
- Flag type and rationale for existence.
- Technical/product owner.
- Creation date and planned review or expiration date.
- Safe default value.
- Cohorts and targeting conditions.
- Artifact/version using the flag.
- Rollout status and cleanup plan.

After the rollout completes:

1. Confirm the feature reached general availability or decide to retire it.
2. Record the final state and default configuration.
3. Delete legacy or experimental code branches no longer in use.
4. Remove the flag from the config service and delete obsolete tests.
5. Retain audit records and analytical data per retention policy.

Operational kill switches or permission flags may need to stay long-term. These flags still require owners, documentation, tests, and periodic checks. Do not delete a kill switch simply because release flags are being cleaned up.

## 16. Common mistakes

| Mistake | Consequence | How to address |
| --- | --- | --- |
| Opening to 100% right after deploy | New bugs affect all users | Start with small cohorts and guardrails |
| Randomizing on every request | Users see inconsistent behavior | Deterministic bucketing by a stable subject |
| Changing salt mid-rollout | Cohorts get reshuffled | Keep key/salt stable or intentionally create a new rollout |
| Using flags as access control | Users can call APIs directly | Independent backend authorization |
| Tracking only aggregate metrics | Errors in the new cohort get masked | Slice metrics by flag, stage, and version |
| Treating evaluation as exposure | Analysis denominator is skewed | Log exposure only when users actually encounter the feature |
| Missing a kill switch | Hard to stop quickly during an incident | Design, authorize, and rehearse turning off flags |
| Flag service failure turns new feature on | Unexpected behavior when dependency disconnects | Define safe fallbacks per flag |
| Two versions write incompatible data | Rollback causes errors or data loss | Expand-contract and compatibility testing |
| Never cleaning up release flags | Code and tests accumulate dead branches | Assign owners, expiry dates, and cleanup tasks |
| Using rollout data to draw A/B test conclusions | Biased product conclusions | Design dedicated experiments and statistical analysis |

## 17. Checklist before expanding a feature

**Flag and cohort design**

- [ ] Flag has a key, type, description, and owner.
- [ ] Appropriate user cohort or tenant unit is defined.
- [ ] Percentage rollout uses deterministic assignment.
- [ ] Targeting rules have clear precedence and combination logic.
- [ ] Fallback when the flag service fails is defined.
- [ ] Flag does not substitute for authorization.

**Safety and observability**

- [ ] Artifact passed quality gates and is traced by digest.
- [ ] Smoke tests exist for both legacy and new branches.
- [ ] Technical and business metrics are sliced by cohort/version.
- [ ] Stop thresholds and observation windows are defined.
- [ ] Kill switch and authorized responders are in place.
- [ ] No PII or secrets are logged in logs/metrics.

**Data and operations**

- [ ] APIs, database schemas, and events stay compatible during rollout.
- [ ] Side effects have idempotency or rate/scope limits.
- [ ] Older mobile/client versions are accounted for.
- [ ] Stage owners and approval processes are defined.
- [ ] A plan exists to roll back the flag and handle already-created data.
- [ ] A review/cleanup date is set for the release flag.

## Conclusion

Releasing features by cohorts or stages decouples deploying an artifact from delivering new behavior to users. Feature flags, cohort targeting, and deterministic bucketing control who gets to use a feature; staged rollouts expand exposure incrementally based on guardrails and operational data.

A reliable rollout requires proceed/halt criteria, per-cohort metrics, kill switches, data and side-effect controls, proper targeting permissions, and a flag cleanup plan. When these conditions are embedded into an audited, traceable CI/CD workflow, teams can release more frequently while bounding blast radius and recovering rapidly when issues surface.
