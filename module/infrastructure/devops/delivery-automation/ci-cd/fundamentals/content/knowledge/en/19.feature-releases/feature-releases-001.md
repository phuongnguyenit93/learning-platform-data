# Distinguishing Software Deployment from Feature Release to Users

In CI/CD, two activities that are often lumped together are **software deployment** and **feature release**. Deployment delivers an application version to the runtime environment. Release decides which users are allowed to see or use a new capability. The two can happen at the same time, but they do not have to.

A team can deploy new code to production in the morning while keeping the feature turned off. After verifying operations, the team enables the feature for internal employees, then a small group of users, and gradually expands. This separation reduces the pressure to make every product and operational decision in a single deploy, while also allowing control over the blast radius when issues occur.

## 1. Deployment and feature release solve two different questions

**Deployment** answers: which version of the software is installed or running on the environment?

**Feature release** answers: who gets to use which feature, at what time, and under what conditions?

| Aspect | Deployment | Feature release |
|---|---|---|
| Subject of change | Binary, container image, package, manifest | Flag state, rule, cohort, or release configuration |
| Scope | Instance, cluster, service, region, or environment | User, tenant, group, request, or traffic percentage |
| Typical tools | CI/CD, orchestrator, deployment controller | Feature flag service, config service, release control plane |
| Outcome | New code version is present in the environment | A target group gains access to the new capability |
| Way to revert | Rollback or roll forward artifact | Disable flag, narrow audience, or change rule |
| Primary risks | Startup, rollout, resource, or compatibility failures | Wrong audience targeting, new logic causing errors, degraded metrics |

For example, a payment application version 2.8 contains both the legacy payment flow and the new payment flow. The pipeline deploys image 2.8 to production. The `new-payment-flow` flag remains off, so everyone continues using the legacy flow. After the team runs smoke tests and enables it for internal staff, the new feature begins rolling out without rebuilding or redeploying.

Separating the two activities allows the engineering team to verify that the code runs properly before the product team decides to expand the user experience.

## 2. The deploy-first, release-later model

A common workflow can be divided into the following stages:

1. Build an immutable artifact and run tests in CI.
2. Deploy the artifact to the target environment with the new feature turned off.
3. Verify service startup, health checks, logs, and baseline metrics.
4. Enable the feature for an internal group or test accounts.
5. Observe errors, latency, conversion, and business metrics.
6. Expand the audience step by step when criteria are met.
7. Release to full availability once sufficient evidence is gathered.
8. Remove the legacy code path and temporary flag when toggle-based rollback is no longer needed.

Conceptual diagram:

~~~mermaid
flowchart TD
    A[Build and test artifact] --> B[Deploy to production]
    B --> C[Feature flag default OFF]
    C --> D[Smoke test and operational verification]
    D --> E[Internal enablement]
    E --> F[Cohort-based rollout]
    F --> G{Metrics and guardrails met?}
    G -- No --> H[Disable flag or narrow rollout]
    G -- Yes --> I[Expand audience]
    I --> J[Release complete]
    J --> K[Remove flag and legacy code]
~~~

In this model, deploying does not mean users already see the feature. The feature is only exposed when the release policy allows it.

Separating stages does not mean every release requires a feature flag. A documentation update, a minor bug fix, or a feature with no audience risk can be deployed and released simultaneously. Feature flags are useful when you need control over timing, audience, or the ability to turn something off quickly.

## 3. How do feature flags work?

A feature flag is a condition that determines whether a branch of behavior in an application is executed. The application evaluates the flag by key and context, then selects the corresponding code path.

Example configuration:

~~~yaml
flags:
  new-payment-flow:
    enabled: false
    description: "New payment flow"
    owner: payments-team
    environment: production
    defaultValue: false
~~~

The application can check the flag before choosing the processing flow:

~~~java
public PaymentResult processPayment(
        PaymentRequest request,
        EvaluationContext context) {

    if (featureFlags.isEnabled("new-payment-flow", context)) {
        return newPaymentProcessor.process(request);
    }

    return legacyPaymentProcessor.process(request);
}
~~~

In this example, the flag decides which code path is invoked. Both processors are packaged in the deployed artifact. Changing the flag state does not require rebuilding the image if the flag system supports independent configuration updates.

A feature flag typically includes the following components:

- **Key:** a stable identifier, for example `new-payment-flow`.
- **Default value:** fallback value if rules cannot be retrieved.
- **Environment:** the environment to which the rule applies.
- **Targeting rules:** conditions for selecting users or tenants.
- **Rollout percentage:** percentage of eligible targets enabled.
- **Owner:** the team responsible.
- **Description:** rationale and purpose.
- **Lifecycle metadata:** creation date, review date, and planned removal date.

Flags should have meaningful names and an assigned owner. A generic key like `enable-new` or `flag-123` is hard to understand during incident investigation.

## 4. Types of feature flags and how to use them

Not every flag has the same lifecycle or purpose.

| Flag type | Purpose | Typical lifespan |
|---|---|---|
| Release flag | Keep new code turned off until ready for release | Temporary; should be removed after release |
| Operational flag | Toggle functionality to protect the system under load or dependency issues | Can live longer; requires an owner |
| Experiment flag | Split cohorts to compare user experience or experiment results | Duration of the experiment |
| Permission/entitlement flag | Control capabilities by service plan or product entitlement | Can be long-term; requires proper authorization integration |
| Kill switch | Quickly disable a high-risk capability | Can be long-term; requires operational controls |

Some systems call all of the above feature flags, but teams should categorize them to know which flags need cleanup, which need regular audits, and which relate to access control policies.

Flags should not replace an authorization system. For instance, a flag enabling an admin feature does not prove the caller has admin privileges. The application must still verify identity and access permissions on the server for every sensitive action.

## 5. Releasing by user cohorts

Targeting rules determine which audience gets the feature enabled. Selection can be based on:

- Internal employee groups.
- Lists of test accounts.
- Specific tenants or organizations.
- Geographic regions if appropriate for the product and policy.
- Service plan or subscription status.
- Client version or device type.
- Cohorts selected by percentage.

Example policy:

~~~yaml
flags:
  new-payment-flow:
    enabled: true
    targeting:
      - name: internal-users
        attribute: userGroup
        operator: equals
        value: employee
        variation: on
      - name: pilot-tenants
        attribute: tenantId
        operator: in
        values:
          - tenant-104
          - tenant-208
        variation: on
    defaultVariation: off
~~~

These rules are illustrative examples only. A production system must define evaluation precedence, how overlapping rules are handled, and the default value when context is absent.

For percentage-based rollouts, use deterministic bucketing based on a suitable identifier such as user ID or tenant ID. If you randomize on every request, the same user might see the new feature one moment and the old feature the next; that causes an inconsistent experience and skews measurement data.

Do not include sensitive personal information in the targeting context unless strictly necessary. Use internal identifiers or minimized attributes, with controlled access and retention limits.

## 6. Incremental rollout and progressive delivery

Progressive delivery is the practice of expanding changes step by step, using metrics and guardrails to decide whether to proceed or stop. Feature flags can control the percentage of users receiving a feature, while deployment strategies control which code version receives traffic.

An illustrative rollout plan:

| Stage | Audience | Promotion criteria |
|---|---:|---|
| Internal | Employees and testers | Core flow works, no critical errors |
| Pilot | A selected group of tenants | Error rate, latency, and feedback meet thresholds |
| Small rollout | 1-5% of eligible users | Metrics remain stable over the defined observation window |
| Medium rollout | 10-25% | No increase in errors or drop in business metrics |
| Broad rollout | 50-75% | Guardrails continue to pass |
| General availability | 100% of target audience | Approved with an operational plan in place |

The percentages above are examples only. Features with low traffic or high risk may require longer stages; lower-impact features can use a simpler progression.

Each stage needs:

- A specific audience or percentage.
- A minimum observation period.
- Success metrics.
- Stop thresholds.
- A designated decision-maker.
- Actions to take if guardrails are breached.

Do not increase the percentage just because no errors appear in the first few minutes. Some bugs only surface under high traffic, when users hit rare paths, or when the system processes real-world data.

## 7. Distinguishing feature rollout from canary deployment

Canary deployment and feature rollout both expand changes incrementally, but they control two different things.

- **Canary deployment:** controls the amount of traffic routed to a new application version or a new set of instances.
- **Feature rollout:** controls which audience executes a specific feature within the code.

| Scenario | Canary deployment | Feature rollout |
|---|---|---|
| Two binary versions coexist | Usually yes | Not required |
| Split traffic by instance or route | Yes | Possibly not |
| Select users by tenant or cohort | Possible | Common use case |
| Turn off a single feature independently | Not necessarily | Yes |
| Revert to legacy code | Shift traffic or roll back deployment | Turn off flag if legacy code remains |
| Observation scope | Version/service | Feature/audience |

Both mechanisms can be combined. For example, deploy a new image to 10% of instances, then enable the new feature for only 1% of tenants hitting those instances. This way, the team separates risk from the new binary from risk caused by the new feature logic.

Avoid calling every percentage-based rollout a canary deployment. Clearly state whether the percentage represents traffic, instances, tenants, or users.

## 8. Kill switches and rapid disablement

A kill switch is a mechanism that allows disabling a function during an incident. It is useful for capabilities that can heavily impact latency, cost, data, or downstream dependencies.

Examples:

- Disable payment processing through a new provider.
- Stop generating heavy reports when the system is overloaded.
- Disable a new search flow causing elevated latency.
- Stop sending notifications when a provider experiences an outage.
- Fall back to the legacy code path when a new feature malfunctions.

A kill switch must be designed before release:

1. Have a clear key and owner.
2. Have an appropriate default value when the flag system is unreachable.
3. Have designated people or processes authorized to toggle it.
4. Changes are recorded in an audit log.
5. The application receives updates within the expected timeframe.
6. Have metrics confirming the functionality is actually disabled.
7. Have a runbook detailing side effects when turned off.

A kill switch does not guarantee every in-flight request will stop immediately. If the application caches flags, define the TTL, push update mechanism, and behavior on connection loss. For sensitive functions, you may need more frequent flag checks or service-level circuit breaking.

Do not let a kill switch corrupt data flows. For example, disabling a consumer can cause message backlogs to grow; disabling writes can affect data consistency. The runbook must describe the consequences and how to recover after re-enabling.

## 9. Monitoring metrics and guardrails during release

Feature rollouts should be evidence-driven. Before enabling a feature, determine which metrics reflect technical quality and business outcomes.

| Metric category | Examples | Purpose |
|---|---|---|
| Reliability | Error rate, exception count, timeouts | Detect functional failures |
| Performance | p50/p95/p99 latency, throughput | Detect performance degradation |
| Resource | CPU, memory, connection pool, queue depth | Detect infrastructure pressure |
| Business | Checkout completion, payment success, conversion | Measure user outcomes |
| Experience | Crash rate, abandonment, support tickets | Evaluate user experience |
| Dependency | Provider errors, API 429/5xx | Detect external service failures |

Compare the flag-enabled group against an appropriate control group, while accounting for differences in time, user segments, and load. A system-wide aggregate metric can mask errors occurring only within the pilot cohort.

For example, a drop in payment success rate from 99.8% to 97.5% in the new cohort is a signal worth investigating, even if the overall error rate has barely increased. Specific thresholds must be grounded in baselines and service requirements.

Set guardrails before rolling out. If error rates exceed thresholds, p95 latency spikes, or conversion drops abnormally, halt expansion and consider disabling the flag. Do not wait until the entire audience is enabled to review the metrics.

## 10. Evaluating flag safety in the application

A flag is a conditional branch running in the application, so it must be tested like regular code.

Verify:

- Behavior when the flag is off.
- Behavior when the flag is on.
- Behavior when the flag service is unreachable.
- Behavior when context is missing or invalid.
- Overlapping rules and evaluation precedence.
- Caching and change propagation delay.
- Consistency across instances.
- Compatibility with existing data and schemas.
- That the client cannot dictate sensitive access permissions.

On the backend, evaluate flags on the server using authenticated context. Do not trust user ID or role values sent by the client without verification. On the frontend, flags can control UI visibility, but server-side APIs must still enforce authorization.

When the flag service fails, there is no single fallback value suitable for all flags. Release flags can usually default to off to keep the stable code path. An operational flag protecting the system may need a different fallback. Define defaults based on the safety impact of each feature and test that failure mode.

## 11. Data and database compatibility when decoupling deploy from release

A new feature may require adding columns, tables, indexes, or message structures. If a migration breaks the ability of the old version to run, simply keeping the flag off is not safe enough.

Use the expand-and-contract strategy:

1. **Expand:** add the new schema in a backward-compatible way without removing old structures.
2. Deploy code capable of working with both old and new schemas.
3. Keep the flag off, and verify the new code and migration.
4. Enable the feature for a small cohort.
5. Monitor data and verify no legacy consumers remain.
6. **Contract:** remove old structures only after all relevant versions have transitioned and rolling back to old code is no longer needed.

For example, if the new feature needs a `payment_method_v2` field, add the field first, make the new code read/write compatibly, and then enable the flag. Only after the release is stable and old versions are no longer running should you plan to drop the old field.

Do not delete data or schemas just because a flag is at 100%. Background jobs, legacy consumers, or other application versions may still depend on the old structure.

## 12. Managing flags as governed configuration with permissions and audit

Feature flags can alter production behavior without a deployment. Therefore, permission to modify a flag can be equivalent to permission to modify system behavior.

Control the following:

- Who is allowed to create, edit, enable, or disable flags.
- Who can modify targeting rules and rollout percentages.
- Which flags require approval for production changes.
- Who owns each flag.
- All changes have audit logs and timestamps.
- Ability to restore previous values.
- Rules are scoped to specific environments and audiences.
- API tokens for flag management are protected like secrets.

Do not grant flag administration privileges to every developer or every pipeline. A deployment workflow does not necessarily need permission to enable a feature for all users. Separating deployment permissions from release permissions makes risk control clearer.

For emergency changes, establish an audited break-glass process. Once resolved, the team must review the change and revoke temporary privileges.

## 13. Avoiding stale, long-lived flags

Release flags are typically created to reduce risk during transitions. If not removed after the feature stabilizes, the codebase accumulates multiple old and new branches.

Consequences can include:

- Increased number of state combinations requiring testing.
- Dead legacy code paths that still have to be maintained.
- Nested conditionals reducing code readability.
- Outdated targeting rules.
- Operators unsure which flags still have an effect.
- An old flag accidentally re-enabled, triggering incompatible code.

Each flag should include metadata:

| Field | Example |
|---|---|
| Key | new-payment-flow |
| Type | release |
| Owner | payments-team |
| Created | 2026-11-01 |
| Review date | 2026-11-20 |
| Planned removal | 2026-12-15 |
| Default after release | true |
| Cleanup issue | PAY-482 |

Once a feature is fully rolled out and a toggle is no longer needed for rollback, the team should remove the flag, legacy code branches, and unused rules. Operational kill switches may be kept long-term if there is an operational justification, but they must have an owner and a dedicated review process.

## 14. When to roll back a deployment vs. just turning off a flag?

Turning off a flag and rolling back an artifact are two distinct actions.

| Situation | Typically appropriate action |
|---|---|
| New feature causes errors while legacy code still works in the same artifact | Turn off flag or narrow audience |
| New binary crashes before the flag is evaluated | Roll back or roll forward artifact |
| Error occurs only for a specific cohort | Turn off flag for that cohort and investigate |
| Misconfigured flag | Restore previous rule or configuration version |
| Incompatible database migration | Handle migration/data per runbook; code rollback alone may not suffice |
| Dependency or platform outage | Use kill switch, fallback, or traffic shifting as designed |

Before turning off a flag, verify whether the fallback behavior is safe. If the legacy code path has already been removed or new data is incompatible, turning off the flag could make the failure worse.

Before rolling back an artifact, check migrations, configs, and dependent changes. Rolling back an image does not automatically revert schemas, sent messages, or committed transactions.

## 15. End-to-end feature release example

Suppose a team is developing a new payment flow for a Java service:

1. Developers add the new code behind the `new-payment-flow` flag, keeping the default as `false`.
2. CI runs unit tests for both flag-on and flag-off branches, integration tests, and static analysis.
3. The build pipeline produces immutable image `2.8.1` and records its digest.
4. The deployment pipeline deploys the image to staging, then production.
5. Smoke tests verify the service and legacy payment flow work properly.
6. The release owner enables the flag for internal employees.
7. The team monitors payment success rate, latency, provider errors, and logs.
8. The flag is opened to a group of pilot tenants.
9. If guardrails pass, the rollout expands gradually by cohort.
10. If errors spike, the flag is turned off or narrowed while the team investigates.
11. Once the feature is stable, it is opened to the entire target audience.
12. The team removes the release flag and legacy code path in a separate, tested change.

Throughout the entire process, the artifact digest does not change as the audience expands. Release changes consist mainly of flag states and targeting policies. This makes it easier to distinguish bugs introduced by a new binary from issues caused by exposing a new feature to users.

## 16. Checklist for separating deployment and feature release

Before a controlled feature release, verify:

- [ ] Clearly defined which code version the deployment puts into the environment.
- [ ] Separately defined conditions and audience for the feature release.
- [ ] Artifact is built once and has an immutable identifier.
- [ ] Feature flag has a safe default value and a clear owner.
- [ ] Both flag-on and flag-off code paths are tested.
- [ ] Targeting rules use authenticated context and do not expose sensitive data.
- [ ] Rollout has defined cohorts, percentages, observation windows, and guardrails.
- [ ] Technical and business metrics are monitored across enabled/control groups.
- [ ] Kill switch and runbook are in place for high-risk features.
- [ ] Flag service fallback behavior and caching have been tested.
- [ ] Database migrations are compatible with both old and new code.
- [ ] Permissions to toggle production flags are restricted and audited.
- [ ] Stop criteria and a decision-maker are defined for the rollout.
- [ ] A plan exists to disable the flag, roll back the artifact, or roll forward.
- [ ] Temporary release flags have an expiration date and a cleanup issue.

Deployment gets code to where it runs; feature release controls who gets to use that code. When the two activities are managed separately, teams can verify a new version before exposing features, test with small cohorts, react quickly via flags, and release in a controlled way without rebuilding just to change the audience.
